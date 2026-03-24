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
	"net"
	"os"
	"os/signal"
	"strings"
	"time"

	winio "github.com/Microsoft/go-winio"

	"github.com/olafnew/mastermice-svc/internal/appdetect"
	"github.com/olafnew/mastermice-svc/internal/config"
	"github.com/olafnew/mastermice-svc/internal/input"
)

const (
	version        = "0.1.0"
	mainPipeName   = `\\.\pipe\MasterMice`
	eventPipeName  = `\\.\pipe\MasterMice-events`
)

func main() {
	fmt.Printf("[mastermice-agent] v%s — user session agent\n", version)

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

	// Handle Ctrl+C
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt)

	// Event reader goroutine — receives button events and executes actions
	go func() {
		scanner := bufio.NewScanner(eventConn)
		for scanner.Scan() {
			line := scanner.Text()
			handleEvent(cfg, line)
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
		return
	}

	eventName, _ := msg["event"].(string)
	data, _ := msg["data"].(map[string]interface{})

	switch eventName {
	case "button_event":
		handleButtonEvent(cfg, data)
	case "gesture_move":
		// TODO Phase 4: accumulate gesture deltas
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

	if state != "down" && state != "click" {
		return // only act on press, not release
	}

	// Look up action in current profile mappings
	mappings := cfg.GetActiveMappings()
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
