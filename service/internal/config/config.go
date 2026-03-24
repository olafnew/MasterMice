// Package config handles MasterMice configuration loading, saving, and watching.
// The JSON schema matches Python's config.py exactly for compatibility.
package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
)

// Config represents the full MasterMice configuration.
type Config struct {
	Version       int                `json:"version"`
	ActiveProfile string             `json:"active_profile"`
	Profiles      map[string]Profile `json:"profiles"`
	Settings      Settings           `json:"settings"`

	mu       sync.RWMutex
	filePath string
}

// Profile represents a button mapping profile (default or per-app).
type Profile struct {
	Label    string            `json:"label"`
	Apps     []string          `json:"apps"`
	Mappings map[string]string `json:"mappings"`
}

// Settings holds global application settings.
type Settings struct {
	StartMinimized    bool    `json:"start_minimized"`
	StartWithWindows  bool    `json:"start_with_windows"`
	HScrollThreshold  int     `json:"hscroll_threshold"`
	InvertHScroll     bool    `json:"invert_hscroll"`
	InvertVScroll     bool    `json:"invert_vscroll"`
	DPI               int     `json:"dpi"`
	GestureThreshold  float64 `json:"gesture_threshold"`
	GestureDeadzone   float64 `json:"gesture_deadzone"`
	GestureTimeoutMs  int     `json:"gesture_timeout_ms"`
	GestureCooldownMs int     `json:"gesture_cooldown_ms"`
	DebugMode         bool    `json:"debug_mode"`
	MouseModel        string  `json:"mouse_model"`
	LogLevel          string  `json:"log_level"`
	LogMaxKB          int     `json:"log_max_kb"`
	HapticEnabled     bool    `json:"haptic_enabled"`
	HapticIntensity   int     `json:"haptic_intensity"`
	HiResScrollDiv    int     `json:"hires_scroll_divider"`
	ScrollForce       int     `json:"scroll_force"`
}

// DefaultConfig returns a fresh config with default values.
func DefaultConfig() *Config {
	return &Config{
		Version:       5,
		ActiveProfile: "default",
		Profiles: map[string]Profile{
			"default": {
				Label: "Default (All Apps)",
				Apps:  []string{},
				Mappings: map[string]string{
					"left_click":    "none",
					"right_click":   "none",
					"scroll_up":     "none",
					"scroll_down":   "none",
					"middle":        "none",
					"mode_shift":    "none",
					"gesture":       "task_view",
					"gesture_left":  "none",
					"gesture_right": "none",
					"gesture_up":    "none",
					"gesture_down":  "none",
					"xbutton1":      "none",
					"xbutton2":      "none",
					"thumb_wheel":   "none",
					"haptic_panel":  "task_view",
				},
			},
		},
		Settings: Settings{
			StartMinimized:    true,
			HScrollThreshold:  1,
			DPI:               1000,
			GestureThreshold:  50,
			GestureDeadzone:   40,
			GestureTimeoutMs:  3000,
			GestureCooldownMs: 500,
			LogLevel:          "errors",
			LogMaxKB:          1024,
			HapticEnabled:     true,
			HapticIntensity:   60,
			HiResScrollDiv:    15,
		},
	}
}

// ConfigDir returns the config directory path.
// Uses %APPDATA%\MasterMice on Windows.
func ConfigDir() string {
	appdata := os.Getenv("APPDATA")
	if appdata == "" {
		appdata = filepath.Join(os.Getenv("USERPROFILE"), "AppData", "Roaming")
	}
	return filepath.Join(appdata, "MasterMice")
}

// ConfigPath returns the full path to config.json.
func ConfigPath() string {
	return filepath.Join(ConfigDir(), "config.json")
}

// Load reads config from disk, or returns defaults if not found.
func Load() (*Config, error) {
	path := ConfigPath()
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			cfg := DefaultConfig()
			cfg.filePath = path
			return cfg, nil
		}
		return nil, fmt.Errorf("read config: %w", err)
	}

	cfg := DefaultConfig() // start with defaults, overlay file values
	if err := json.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}
	cfg.filePath = path
	cfg.migrate()
	cfg.mergeDefaults()
	return cfg, nil
}

// Save writes config to disk.
func (c *Config) Save() error {
	c.mu.RLock()
	defer c.mu.RUnlock()

	dir := filepath.Dir(c.filePath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("create config dir: %w", err)
	}

	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal config: %w", err)
	}

	return os.WriteFile(c.filePath, data, 0644)
}

// GetActiveProfile returns the currently active profile.
func (c *Config) GetActiveProfile() Profile {
	c.mu.RLock()
	defer c.mu.RUnlock()

	p, ok := c.Profiles[c.ActiveProfile]
	if !ok {
		p = c.Profiles["default"]
	}
	return p
}

// GetActiveMappings returns the button→action mappings for the active profile.
func (c *Config) GetActiveMappings() map[string]string {
	return c.GetActiveProfile().Mappings
}

// GetProfileForApp returns the profile name matching the given exe, or "default".
func (c *Config) GetProfileForApp(exeName string) string {
	c.mu.RLock()
	defer c.mu.RUnlock()

	exeLower := strings.ToLower(exeName)
	for name, p := range c.Profiles {
		for _, app := range p.Apps {
			if strings.ToLower(app) == exeLower {
				return name
			}
		}
	}
	return "default"
}

// SetMapping updates a button mapping in a profile and saves.
func (c *Config) SetMapping(profile, button, actionID string) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	p, ok := c.Profiles[profile]
	if !ok {
		return fmt.Errorf("profile %q not found", profile)
	}
	if p.Mappings == nil {
		p.Mappings = make(map[string]string)
	}
	p.Mappings[button] = actionID
	c.Profiles[profile] = p

	return c.saveUnlocked()
}

// SetSetting updates a single setting by key and saves.
func (c *Config) SetSetting(key string, value interface{}) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	// Marshal settings to map, update key, unmarshal back
	data, _ := json.Marshal(c.Settings)
	m := map[string]interface{}{}
	json.Unmarshal(data, &m)
	m[key] = value
	data, _ = json.Marshal(m)
	json.Unmarshal(data, &c.Settings)

	return c.saveUnlocked()
}

// ToJSON returns the config as a JSON-serializable map (for IPC responses).
func (c *Config) ToJSON() map[string]interface{} {
	c.mu.RLock()
	defer c.mu.RUnlock()

	data, _ := json.Marshal(c)
	var m map[string]interface{}
	json.Unmarshal(data, &m)
	return m
}

func (c *Config) saveUnlocked() error {
	dir := filepath.Dir(c.filePath)
	os.MkdirAll(dir, 0755)
	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(c.filePath, data, 0644)
}

// migrate upgrades old config versions to current.
func (c *Config) migrate() {
	if c.Version < 5 {
		// Set default actions for gesture and haptic_panel
		for _, p := range c.Profiles {
			if p.Mappings != nil {
				if p.Mappings["haptic_panel"] == "none" || p.Mappings["haptic_panel"] == "" {
					p.Mappings["haptic_panel"] = "task_view"
				}
				if p.Mappings["gesture"] == "none" || p.Mappings["gesture"] == "" {
					p.Mappings["gesture"] = "task_view"
				}
			}
		}
		c.Version = 5
	}
}

// mergeDefaults fills in any missing keys from defaults.
func (c *Config) mergeDefaults() {
	def := DefaultConfig()
	if c.Profiles == nil {
		c.Profiles = def.Profiles
	}
	for _, p := range c.Profiles {
		if p.Mappings == nil {
			p.Mappings = def.Profiles["default"].Mappings
		}
		for k, v := range def.Profiles["default"].Mappings {
			if _, ok := p.Mappings[k]; !ok {
				p.Mappings[k] = v
			}
		}
	}
	if c.Settings.LogLevel == "" {
		c.Settings.LogLevel = "errors"
	}
	if c.Settings.LogMaxKB == 0 {
		c.Settings.LogMaxKB = 1024
	}
	if c.Settings.GestureThreshold == 0 {
		c.Settings.GestureThreshold = 50
	}
	if c.Settings.GestureDeadzone == 0 {
		c.Settings.GestureDeadzone = 40
	}
	if c.Settings.GestureTimeoutMs == 0 {
		c.Settings.GestureTimeoutMs = 3000
	}
	if c.Settings.GestureCooldownMs == 0 {
		c.Settings.GestureCooldownMs = 500
	}
	if c.Settings.HiResScrollDiv == 0 {
		c.Settings.HiResScrollDiv = 15
	}
}
