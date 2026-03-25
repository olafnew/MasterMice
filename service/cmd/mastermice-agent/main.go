// mastermice-agent — User-session process for MasterMice.
//
// Runs in the interactive desktop session (not Session 0).
// Connects to mastermice-svc.exe via named pipes and handles:
//   - Real-time HID++ button events (haptic panel, gesture) → instant action execution
//   - WH_MOUSE_LL hook for OS-level buttons (xbutton, scroll) [Phase 4]
//   - Foreground app detection for profile switching [Phase 5]
//
// This binary is launched by the Python UI or by the Windows startup registry.
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"math"
	"net"
	"os"
	"os/signal"
	"strings"
	"sync"
	"time"

	winio "github.com/Microsoft/go-winio"

	"github.com/olafnew/mastermice-svc/internal/appdetect"
	"github.com/olafnew/mastermice-svc/internal/config"
	"github.com/olafnew/mastermice-svc/internal/hidpp"
	"github.com/olafnew/mastermice-svc/internal/input"
	mlog "github.com/olafnew/mastermice-svc/internal/logging"
)

// ── Gesture state machine (continuous detection) ─────────────
// Fires actions DURING hold when movement crosses threshold — no need to release.
// Like Logitech Options+: swipe right = instant desktop switch, keep swiping = switch again.
//
// Logic:
//   1. Button down → start tracking, record timestamp
//   2. Each gesture_move → accumulate dx/dy, check threshold
//      - If |accumulated| > swipeThreshold → fire action, reset accumulator, set swipeOccurred
//      - Skip first sample (noise spike from accumulated sensor data during press)
//   3. Button up:
//      - If swipeOccurred → do nothing (already handled)
//      - If !swipeOccurred AND holdTime < clickMaxMs AND totalMovement < clickDeadzone → fire click
//      - Otherwise → aborted gesture (ignored)
type gestureState struct {
	mu             sync.Mutex
	active         bool
	button         string
	startTime      time.Time
	totalDX        float64   // accumulated filtered movement since last action fire
	totalDY        float64
	swipeOccurred  bool      // at least one swipe was fired during this hold
	sampleCount    int       // number of gesture_move samples received
	totalMovement  float64   // total absolute movement (for click detection)
	kalman         *KalmanFilter2D
}

var gesture = &gestureState{
	kalman: NewKalmanFilter2D(),
}

const (
	swipeThreshold = 150.0  // accumulated FILTERED movement to trigger a swipe action
	clickMaxMs     = 300    // max hold duration for a click (milliseconds)
	clickDeadzone  = 50.0   // max total filtered movement for a click
)

func (g *gestureState) start(button string) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.active = true
	g.button = button
	g.startTime = time.Now()
	g.totalDX = 0
	g.totalDY = 0
	g.swipeOccurred = false
	g.sampleCount = 0
	g.totalMovement = 0
	g.kalman.Reset()
}

// accumulate processes a raw dx/dy sample through the Kalman filter and checks
// if the filtered accumulation has crossed the swipe threshold.
// Returns: direction ("left"/"right"/"up"/"down") if threshold crossed, "" otherwise.
func (g *gestureState) accumulate(dx, dy int) string {
	g.mu.Lock()
	defer g.mu.Unlock()
	if !g.active {
		return ""
	}

	g.sampleCount++

	// Run raw measurement through Kalman filter — outputs smooth, noise-free velocity
	filteredDX, filteredDY := g.kalman.Update(float64(dx), float64(dy))

	// Accumulate FILTERED values (not raw)
	g.totalDX += filteredDX
	g.totalDY += filteredDY
	g.totalMovement += math.Abs(filteredDX) + math.Abs(filteredDY)

	// Check if we've crossed the swipe threshold
	absDX := math.Abs(g.totalDX)
	absDY := math.Abs(g.totalDY)
	dominant := math.Max(absDX, absDY)

	if dominant >= swipeThreshold {
		var direction string
		if absDX > absDY {
			if g.totalDX > 0 {
				direction = "right"
			} else {
				direction = "left"
			}
		} else {
			if g.totalDY > 0 {
				direction = "down"
			} else {
				direction = "up"
			}
		}

		// Reset accumulator for the next potential swipe (allows repeated desktop switching)
		g.totalDX = 0
		g.totalDY = 0
		g.swipeOccurred = true

		return direction
	}

	return ""
}

// finish handles button release. Returns (button, "click") if it was a short still press,
// or (button, "") if swipe already handled or gesture was aborted.
func (g *gestureState) finish() (button string, direction string) {
	g.mu.Lock()
	defer g.mu.Unlock()
	if !g.active {
		return "", ""
	}
	g.active = false
	btn := g.button

	// If a swipe was already fired during hold → nothing to do on release
	if g.swipeOccurred {
		return btn, ""
	}

	// Check if this qualifies as a click: short hold + minimal movement
	holdMs := time.Since(g.startTime).Milliseconds()
	if holdMs <= clickMaxMs && g.totalMovement < clickDeadzone {
		return btn, "click"
	}

	// Aborted gesture — held too long or moved but not enough for a swipe
	return btn, ""
}

func (g *gestureState) isActive() bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.active
}

const (
	version        = "0.9.1"
	mainPipeName   = `\\.\pipe\MasterMice`
	eventPipeName  = `\\.\pipe\MasterMice-events`
	agentPipeName  = `\\.\pipe\MasterMice-agent`
)

func main() {
	// Initialize shared logging FIRST
	if err := mlog.Init("mastermice-agent"); err != nil {
		fmt.Fprintf(os.Stderr, "logging init failed: %v\n", err)
	}
	defer mlog.Close()

	mlog.Printf("[mastermice-agent] v%s — user session agent\n", version)

	// Kill ONLY old agent instances (never kill the service!)
	hidpp.KillOldMasterMiceByName("mastermice-agent.exe")

	// Load config for button mappings
	cfg, err := config.Load()
	if err != nil {
		mlog.Printf("[WARN] Config load failed: %v — using defaults\n", err)
		cfg = config.DefaultConfig()
	}
	mlog.Printf("[Agent] Config loaded: %d profiles, active=%s\n",
		len(cfg.Profiles), cfg.ActiveProfile)

	// Start agent health/version IPC server (for version checking by the Python app)
	go runAgentHealthServer()

	// Connect to event pipe (push stream from service)
	var eventConn net.Conn
	for attempt := 0; attempt < 60; attempt++ {
		timeout := 500 * time.Millisecond
		conn, err := winio.DialPipe(eventPipeName, &timeout)
		if err == nil {
			eventConn = conn
			mlog.Printf("[Agent] Connected to event pipe (attempt %d)\n", attempt+1)
			break
		}
		if attempt == 0 {
			mlog.Printf("[Agent] Waiting for service event pipe...\n")
		} else if attempt%10 == 0 {
			mlog.Printf("[Agent] Still waiting for event pipe (attempt %d: %v)\n", attempt+1, err)
		}
		time.Sleep(500 * time.Millisecond)
	}
	if eventConn == nil {
		mlog.Println("[ERROR] Could not connect to service event pipe after 30s")
		os.Exit(1)
	}
	defer eventConn.Close()

	// Connect to command pipe for sending haptic triggers
	var cmdConn net.Conn
	{
		timeout := 2 * time.Second
		c, err := winio.DialPipe(mainPipeName, &timeout)
		if err == nil {
			cmdConn = c
			mlog.Println("[Agent] Connected to command pipe (for haptic triggers)")
		} else {
			mlog.Printf("[WARN] Command pipe unavailable: %v — haptic feedback on actions disabled\n", err)
		}
	}
	if cmdConn != nil {
		defer cmdConn.Close()
	}
	// Make cmdConn accessible to action execution
	input.SetCmdPipe(cmdConn)

	// Handle Ctrl+C
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt)

	// Event reader goroutine — receives button events and executes actions
	go func() {
		scanner := bufio.NewScanner(eventConn)
		for scanner.Scan() {
			handleEvent(cfg, scanner.Text())
		}
		if err := scanner.Err(); err != nil {
			mlog.Printf("[Agent] Event pipe error: %v\n", err)
		}
		mlog.Println("[Agent] Event pipe disconnected")
		os.Exit(0)
	}()

	// Start WH_MOUSE_LL hook for OS-level buttons (xbutton, scroll)
	hook := input.NewMouseHook()
	hook.SetMappings(cfg.GetActiveMappings())
	hook.InvertVScroll = cfg.Settings.InvertVScroll
	hook.InvertHScroll = cfg.Settings.InvertHScroll
	globalHookRef = hook

	go func() {
		if err := hook.Start(); err != nil {
			mlog.Printf("[Agent] Mouse hook failed: %v\n", err)
		}
	}()
	mlog.Println("[Agent] Mouse hook started")

	// Start foreground app detection for profile switching
	detector := appdetect.NewDetector(func(exe string) {
		// Resolve profile for this app
		profileName := cfg.GetProfileForApp(exe)
		if profileName != cfg.ActiveProfile {
			cfg.ActiveProfile = profileName
			newMappings := cfg.GetActiveMappings()
			hook.SetMappings(newMappings)
			mlog.Printf("[Agent] App: %s → profile: %s\n", exe, profileName)
		}
	})
	detector.Start()
	defer detector.Stop()
	mlog.Println("[Agent] App detection started")

	mlog.Println("[Agent] Listening for events... (Ctrl+C to quit)")

	// Wait for shutdown
	<-sig
	hook.Stop()
	mlog.Println("[Agent] Shutting down")
}

func handleEvent(cfg *config.Config, line string) {
	var msg map[string]interface{}
	if err := json.Unmarshal([]byte(line), &msg); err != nil {
		return
	}
	eventName, _ := msg["event"].(string)
	data, _ := msg["data"].(map[string]interface{})

	switch eventName {
	case "button_event":
		handleButtonEvent(cfg, data)
	case "gesture_move":
		dx, _ := data["dx"].(float64)
		dy, _ := data["dy"].(float64)
		direction := gesture.accumulate(int(dx), int(dy))
		if direction != "" {
			// Threshold crossed mid-hold → fire action immediately
			mappings := cfg.GetActiveMappings()
			swipeKey := gesture.button + "_" + direction
			actionID := mappings[swipeKey]
			if actionID == "" || actionID == "none" {
				actionID = mappings[gesture.button]
			}
			if actionID != "" && actionID != "none" {
				mlog.Printf("[Agent] Gesture %s swipe %s → %s\n", gesture.button, direction, actionID)
				input.ExecuteAction(actionID)
			}
		}
	case "config_changed":
		handleConfigChanged(cfg, data)
	case "battery_update":
		level, _ := data["level"].(float64)
		charging, _ := data["charging"].(bool)
		mlog.Printf("[Agent] Battery: %.0f%% charging=%v\n", level, charging)
	case "device_connected":
		name, _ := data["name"].(string)
		mlog.Printf("[Agent] Device connected: %s\n", name)
	case "device_disconnected":
		mlog.Println("[Agent] Device disconnected")
	}
}

func handleButtonEvent(cfg *config.Config, data map[string]interface{}) {
	button, _ := data["button"].(string)
	state, _ := data["state"].(string)

	mappings := cfg.GetActiveMappings()

	// Check if this button has gesture mappings (gesture_left, gesture_right, etc.)
	hasGestures := false
	for _, dir := range []string{"_left", "_right", "_up", "_down"} {
		key := button + dir  // e.g. "gesture_left", "haptic_panel_left"
		if a, ok := mappings[key]; ok && a != "" && a != "none" {
			hasGestures = true
			break
		}
	}
	// Gesture button always has gestures by default
	if button == "gesture" {
		hasGestures = true
	}

	if hasGestures {
		// Gesture-enabled button: use hold+move+release detection
		if state == "down" {
			gesture.start(button)
			return // don't execute action yet — wait for release
		}
		if state == "up" {
			btn, direction := gesture.finish()
			if btn == "" || direction == "" {
				return // swipe already handled during hold, or aborted gesture
			}

			// Only "click" reaches here — swipes are handled in gesture_move
			if direction == "click" {
				actionID := mappings[button]
				if actionID == "" || actionID == "none" {
					return
				}
				mlog.Printf("[Agent] Gesture %s click → %s\n", btn, actionID)
				input.ExecuteAction(actionID)
			}
			return
		}
	}

	// Non-gesture button: execute immediately on press
	if state != "down" && state != "click" {
		return
	}

	actionID, ok := mappings[button]
	if !ok || actionID == "" || actionID == "none" {
		return
	}

	mlog.Printf("[Agent] Button %s → action %s\n", button, actionID)
	input.ExecuteAction(actionID)
}

// globalHookRef is set by main() for config updates to refresh mappings.
var globalHookRef *input.MouseHook

func handleConfigChanged(cfg *config.Config, data map[string]interface{}) {
	// Reload config from disk
	newCfg, err := config.Load()
	if err != nil {
		mlog.Printf("[Agent] Config reload failed: %v\n", err)
		return
	}
	cfg.Version = newCfg.Version
	cfg.ActiveProfile = newCfg.ActiveProfile
	cfg.Profiles = newCfg.Profiles
	cfg.Settings = newCfg.Settings
	mlog.Printf("[Agent] Config reloaded: active=%s\n", cfg.ActiveProfile)

	// Update hook mappings
	if globalHookRef != nil {
		globalHookRef.SetMappings(cfg.GetActiveMappings())
		globalHookRef.InvertVScroll = cfg.Settings.InvertVScroll
		globalHookRef.InvertHScroll = cfg.Settings.InvertHScroll
	}
}

// resolveButton maps HID++ CID names to config button keys.
func resolveButton(button string) string {
	switch strings.ToLower(button) {
	case "haptic_panel":
		return "haptic_panel"
	case "gesture":
		return "gesture"
	default:
		return button
	}
}

// ── Agent Health/Version IPC Server ──────────────────────────
// Listens on \\.\pipe\MasterMice-agent for version queries.
// Protocol: JSON-lines, same as the main service.
// Supports: {"cmd":"health"} → {"ok":true,"data":{"version":"X.Y.Z"}}
func runAgentHealthServer() {
	cfg := &winio.PipeConfig{
		SecurityDescriptor: "D:P(A;;GA;;;WD)",
		MessageMode:        false,
	}

	l, err := winio.ListenPipe(agentPipeName, cfg)
	if err != nil {
		mlog.Printf("[Agent-IPC] Failed to listen on %s: %v\n", agentPipeName, err)
		return
	}
	defer l.Close()
	mlog.Printf("[Agent-IPC] Health endpoint on %s\n", agentPipeName)

	for {
		conn, err := l.Accept()
		if err != nil {
			continue
		}
		go handleAgentHealthClient(conn)
	}
}

func handleAgentHealthClient(conn net.Conn) {
	defer conn.Close()
	scanner := bufio.NewScanner(conn)
	for scanner.Scan() {
		line := scanner.Text()
		var req map[string]interface{}
		if err := json.Unmarshal([]byte(line), &req); err != nil {
			continue
		}

		cmd, _ := req["cmd"].(string)
		id, _ := req["id"].(float64)

		var resp []byte
		switch cmd {
		case "health":
			resp, _ = json.Marshal(map[string]interface{}{
				"id": int(id),
				"ok": true,
				"data": map[string]interface{}{
					"version": version,
					"type":    "mastermice-agent",
				},
			})
		default:
			resp, _ = json.Marshal(map[string]interface{}{
				"id":    int(id),
				"ok":    false,
				"error": "unknown command",
			})
		}
		resp = append(resp, '\n')
		conn.Write(resp)
	}
}
