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
)

// ── Gesture state machine ─────────────────────────────────────
// Tracks hold+move+release for gesture buttons (gesture, haptic_panel).
// When a gesture-enabled button is pressed:
//   1. Start accumulating dx/dy from gesture_move events
//   2. On release: if movement > threshold → fire swipe action, else fire click action
type gestureState struct {
	mu        sync.Mutex
	active    bool       // currently tracking a gesture
	button    string     // which button started it ("gesture" or "haptic_panel")
	startTime time.Time
	totalDX   int
	totalDY   int
}

var gesture = &gestureState{}

const (
	gestureThreshold = 300   // minimum total movement to count as swipe (in raw units)
	gestureDeadzone  = 0.35  // max cross-axis ratio before rejecting as diagonal
)

func (g *gestureState) start(button string) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.active = true
	g.button = button
	g.startTime = time.Now()
	g.totalDX = 0
	g.totalDY = 0
}

func (g *gestureState) accumulate(dx, dy int) {
	g.mu.Lock()
	defer g.mu.Unlock()
	if !g.active {
		return
	}
	g.totalDX += dx
	g.totalDY += dy
}

// finish returns the detected swipe direction or "click" if no significant movement.
// Returns: "left", "right", "up", "down", or "click"
func (g *gestureState) finish() (button string, direction string) {
	g.mu.Lock()
	defer g.mu.Unlock()
	if !g.active {
		return "", "click"
	}
	g.active = false
	btn := g.button

	absDX := math.Abs(float64(g.totalDX))
	absDY := math.Abs(float64(g.totalDY))
	dominant := math.Max(absDX, absDY)
	cross := math.Min(absDX, absDY)

	// Not enough movement → click
	if dominant < gestureThreshold {
		return btn, "click"
	}

	// Too diagonal → click (cross-axis must be < 35% of dominant)
	if dominant > 0 && cross/dominant > gestureDeadzone {
		return btn, "click"
	}

	// Determine direction
	if absDX > absDY {
		if g.totalDX > 0 {
			return btn, "right"
		}
		return btn, "left"
	}
	if g.totalDY > 0 {
		return btn, "down"
	}
	return btn, "up"
}

func (g *gestureState) isActive() bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.active
}

const (
	version        = "0.4.0"
	mainPipeName   = `\\.\pipe\MasterMice`
	eventPipeName  = `\\.\pipe\MasterMice-events`
)

func main() {
	fmt.Printf("[mastermice-agent] v%s — user session agent\n", version)

	// Kill ONLY old agent instances (never kill the service!)
	hidpp.KillOldMasterMiceByName("mastermice-agent.exe")

	// Load config for button mappings
	cfg, err := config.Load()
	if err != nil {
		fmt.Printf("[WARN] Config load failed: %v — using defaults\n", err)
		cfg = config.DefaultConfig()
	}
	fmt.Printf("[Agent] Config loaded: %d profiles, active=%s\n",
		len(cfg.Profiles), cfg.ActiveProfile)

	// Connect to event pipe (push stream from service)
	var eventConn net.Conn
	for attempt := 0; attempt < 30; attempt++ {
		timeout := 2 * time.Second
		conn, err := winio.DialPipe(eventPipeName, &timeout)
		if err == nil {
			eventConn = conn
			fmt.Printf("[Agent] Connected to event pipe\n")
			break
		}
		if attempt == 0 {
			fmt.Printf("[Agent] Waiting for service event pipe...\n")
		}
		time.Sleep(1 * time.Second)
	}
	if eventConn == nil {
		fmt.Println("[ERROR] Could not connect to service event pipe after 30s")
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
			fmt.Println("[Agent] Connected to command pipe (for haptic triggers)")
		} else {
			fmt.Printf("[WARN] Command pipe unavailable: %v — haptic feedback on actions disabled\n", err)
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
		fmt.Println("[Agent-DBG] Event reader goroutine started")
		scanner := bufio.NewScanner(eventConn)
		for scanner.Scan() {
			line := scanner.Text()
			fmt.Printf("[Agent-DBG] Raw line: %s\n", line[:min(80, len(line))])
			handleEvent(cfg, line)
		}
		if err := scanner.Err(); err != nil {
			fmt.Printf("[Agent] Event pipe error: %v\n", err)
		}
		fmt.Println("[Agent] Event pipe disconnected")
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
			fmt.Printf("[Agent] Mouse hook failed: %v\n", err)
		}
	}()
	fmt.Println("[Agent] Mouse hook started")

	// Start foreground app detection for profile switching
	detector := appdetect.NewDetector(func(exe string) {
		// Resolve profile for this app
		profileName := cfg.GetProfileForApp(exe)
		if profileName != cfg.ActiveProfile {
			cfg.ActiveProfile = profileName
			newMappings := cfg.GetActiveMappings()
			hook.SetMappings(newMappings)
			fmt.Printf("[Agent] App: %s → profile: %s\n", exe, profileName)
		}
	})
	detector.Start()
	defer detector.Stop()
	fmt.Println("[Agent] App detection started")

	fmt.Println("[Agent] Listening for events... (Ctrl+C to quit)")

	// Wait for shutdown
	<-sig
	hook.Stop()
	fmt.Println("[Agent] Shutting down")
}

func handleEvent(cfg *config.Config, line string) {
	var msg map[string]interface{}
	if err := json.Unmarshal([]byte(line), &msg); err != nil {
		fmt.Printf("[Agent-DBG] JSON parse error: %v (line=%q)\n", err, line[:min(80, len(line))])
		return
	}
	eventName, _ := msg["event"].(string)
	data, _ := msg["data"].(map[string]interface{})
	// DEBUG: log all received events
	fmt.Printf("[Agent-DBG] Event received: %s\n", eventName)

	switch eventName {
	case "button_event":
		handleButtonEvent(cfg, data)
	case "gesture_move":
		dx, _ := data["dx"].(float64)
		dy, _ := data["dy"].(float64)
		gesture.accumulate(int(dx), int(dy))
	case "config_changed":
		handleConfigChanged(cfg, data)
	case "battery_update":
		level, _ := data["level"].(float64)
		charging, _ := data["charging"].(bool)
		fmt.Printf("[Agent] Battery: %.0f%% charging=%v\n", level, charging)
	case "device_connected":
		name, _ := data["name"].(string)
		fmt.Printf("[Agent] Device connected: %s\n", name)
	case "device_disconnected":
		fmt.Println("[Agent] Device disconnected")
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
			if btn == "" {
				return
			}

			var actionID string
			if direction == "click" {
				// No significant movement → fire click action
				actionID = mappings[button]
			} else {
				// Swipe detected → fire directional action
				swipeKey := button + "_" + direction // e.g. "gesture_right"
				actionID = mappings[swipeKey]
				if actionID == "" || actionID == "none" {
					// No directional mapping → fall back to click
					actionID = mappings[button]
				}
			}

			if actionID == "" || actionID == "none" {
				return
			}

			if direction == "click" {
				fmt.Printf("[Agent] Gesture %s click → %s\n", btn, actionID)
			} else {
				fmt.Printf("[Agent] Gesture %s swipe %s → %s\n", btn, direction, actionID)
			}
			input.ExecuteAction(actionID)
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

	fmt.Printf("[Agent] Button %s → action %s\n", button, actionID)
	input.ExecuteAction(actionID)
}

// globalHookRef is set by main() for config updates to refresh mappings.
var globalHookRef *input.MouseHook

func handleConfigChanged(cfg *config.Config, data map[string]interface{}) {
	// Reload config from disk
	newCfg, err := config.Load()
	if err != nil {
		fmt.Printf("[Agent] Config reload failed: %v\n", err)
		return
	}
	cfg.Version = newCfg.Version
	cfg.ActiveProfile = newCfg.ActiveProfile
	cfg.Profiles = newCfg.Profiles
	cfg.Settings = newCfg.Settings
	fmt.Printf("[Agent] Config reloaded: active=%s\n", cfg.ActiveProfile)

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
