package ipc

import (
	"fmt"
	"runtime"
	"sync"
	"time"

	"github.com/olafnew/mastermice-svc/internal/hidpp"
)

// Handler dispatches IPC commands to device methods.
// All device access is serialized via mu to prevent concurrent HID++ commands.
type Handler struct {
	Device    *hidpp.Device
	StartTime time.Time
	Version   string

	mu     sync.Mutex
	evtMu  sync.Mutex
	events []map[string]interface{} // buffered events for poll-based clients
}

// PushEvent adds an event to the buffer (called from deviceLoop goroutine).
// Python polls these via "get_events" command since sync pipe can't receive pushes.
func (h *Handler) PushEvent(name string, data map[string]interface{}) {
	h.evtMu.Lock()
	defer h.evtMu.Unlock()
	evt := map[string]interface{}{
		"event": name,
		"data":  data,
		"ts":    time.Now().UnixMilli(),
	}
	h.events = append(h.events, evt)
	// Keep max 50 events
	if len(h.events) > 50 {
		h.events = h.events[len(h.events)-50:]
	}
}

// DrainEvents returns and clears all buffered events.
func (h *Handler) DrainEvents() []map[string]interface{} {
	h.evtMu.Lock()
	defer h.evtMu.Unlock()
	evts := h.events
	h.events = nil
	return evts
}

// NewHandler creates a command handler for the given device.
func NewHandler(device *hidpp.Device, version string) *Handler {
	return &Handler{
		Device:    device,
		StartTime: time.Now(),
		Version:   version,
	}
}

// SetDevice updates the device pointer (used by reconnect logic).
func (h *Handler) SetDevice(d *hidpp.Device) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.Device = d
}

// GetDevice returns the current device pointer.
func (h *Handler) GetDevice() *hidpp.Device {
	h.mu.Lock()
	defer h.mu.Unlock()
	return h.Device
}

// Handle processes a request and returns a response.
// Serializes device access across concurrent IPC clients.
func (h *Handler) Handle(req *Request) *Response {
	// These commands don't need device lock
	switch req.Cmd {
	case "health":
		return h.handleHealth(req)
	case "get_events":
		// Drain buffered events (battery changes, button presses)
		// This is the mechanism for sync pipe clients to receive push-style events
		evts := h.DrainEvents()
		return &Response{
			ID: req.ID, OK: true,
			Data: map[string]interface{}{"events": evts},
		}
	}

	h.mu.Lock()
	defer h.mu.Unlock()

	if h.Device == nil {
		return errResp(req.ID, "no device connected")
	}

	switch req.Cmd {

	case "get_status":
		d := h.Device
		data := map[string]interface{}{
			"connected":        d.Transport != nil,
			"model":            d.ModelKey,
			"name":             d.Name,
			"battery_level":    d.CachedBattLevel,
			"battery_charging": d.CachedBattCharging,
			"dpi":              d.CachedDPI,
		}
		// Connection type from PID
		switch d.ConnPID {
		case hidpp.PIDBolt:
			data["connection_type"] = "bolt"
		case hidpp.PIDUnifyingOld, hidpp.PIDUnifyingNew, hidpp.PIDUnifyingAlt:
			data["connection_type"] = "unifying"
		default:
			if d.DevIdx == hidpp.BTDevIdx {
				data["connection_type"] = "bluetooth"
			} else {
				data["connection_type"] = "unknown"
			}
		}
		return okResp(req.ID, data)

	case "get_capabilities":
		d := h.Device
		data := map[string]interface{}{
			"model":           d.ModelKey,
			"name":            d.Name,
			"has_smartshift":  d.SmartShiftIdx != 0,
			"smartshift_ver":  d.SmartShiftVer,
			"has_haptics":         d.HapticIdx != 0,
			"has_button_sens":     d.ButtonSensIdx != 0,
			"has_hires":           d.HiResIdx != 0,
			"has_smooth":          d.ScrollCtrlIdx != 0,
		}
		if d.Profile != nil {
			data["max_dpi"] = d.Profile.DPIMax
			data["buttons"] = d.Profile.Buttons
		}
		return okResp(req.ID, data)

	case "set_dpi":
		val := ParamInt(req.Params, "value", 0)
		if val == 0 {
			return errResp(req.ID, "missing 'value' param")
		}
		if err := h.Device.SetDPI(val); err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, nil)

	case "read_dpi":
		dpi, err := h.Device.ReadDPI()
		if err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, map[string]interface{}{"dpi": dpi})

	case "set_smartshift":
		threshold := ParamInt(req.Params, "threshold", -1)
		force := ParamInt(req.Params, "force", 50)
		enabled := ParamBool(req.Params, "enabled", true)
		if threshold == -1 {
			return errResp(req.ID, "missing 'threshold' param")
		}
		if err := h.Device.SetSmartShift(threshold, force, enabled); err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, nil)

	case "get_smartshift":
		ss, err := h.Device.GetSmartShift()
		if err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, map[string]interface{}{
			"enabled":   ss.Enabled,
			"threshold": ss.Threshold,
			"force":     ss.Force,
			"mode":      ss.Mode,
		})

	case "set_hires_wheel":
		data := map[string]interface{}{}
		var hiresPtr, invertPtr *bool
		if v, ok := req.Params["hires"]; ok {
			if b, ok := v.(bool); ok {
				hiresPtr = &b
				data["hires"] = b
			}
		}
		if v, ok := req.Params["invert"]; ok {
			if b, ok := v.(bool); ok {
				invertPtr = &b
				data["invert"] = b
			}
		}
		if err := h.Device.SetHiResWheel(hiresPtr, invertPtr); err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, data)

	case "get_hires_wheel":
		hr, err := h.Device.GetHiResWheel()
		if err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, map[string]interface{}{
			"target": hr.Target,
			"hires":  hr.HiRes,
			"invert": hr.Invert,
		})

	case "set_smooth_scroll":
		enabled := ParamBool(req.Params, "enabled", true)
		if err := h.Device.SetSmoothScroll(enabled); err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, nil)

	case "get_smooth_scroll":
		on, err := h.Device.GetSmoothScroll()
		if err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, map[string]interface{}{"enabled": on})

	case "read_battery":
		batt, err := h.Device.ReadBattery()
		if err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, map[string]interface{}{
			"level":    batt.Level,
			"charging": batt.Charging,
		})

	case "set_haptic":
		enabled := ParamBool(req.Params, "enabled", true)
		intensity := ParamInt(req.Params, "intensity", 60)
		if err := h.Device.HapticSetConfig(enabled, intensity); err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, nil)

	case "get_button_sensitivity":
		val, err := h.Device.GetButtonSensitivity()
		if err != nil {
			return errResp(req.ID, err.Error())
		}
		// Map raw value to named preset
		name := "unknown"
		switch val {
		case hidpp.ButtonSensLight:
			name = "light"
		case hidpp.ButtonSensMedium:
			name = "medium"
		case hidpp.ButtonSensHard:
			name = "hard"
		case hidpp.ButtonSensFirm:
			name = "firm"
		}
		return okResp(req.ID, map[string]interface{}{
			"preset": name,
			"raw":    val,
		})

	case "set_button_sensitivity":
		presetName := ParamString(req.Params, "preset", "")
		var preset uint16
		switch presetName {
		case "light":
			preset = hidpp.ButtonSensLight
		case "medium":
			preset = hidpp.ButtonSensMedium
		case "hard":
			preset = hidpp.ButtonSensHard
		case "firm":
			preset = hidpp.ButtonSensFirm
		default:
			// Allow raw value too
			raw := ParamInt(req.Params, "raw", 0)
			if raw == 0 {
				return errResp(req.ID, "unknown preset; use light/medium/hard/firm or raw value")
			}
			preset = uint16(raw)
		}
		if err := h.Device.SetButtonSensitivity(preset); err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, nil)

	case "haptic_trigger":
		pulseType := ParamInt(req.Params, "pulse_type", 0x04)
		if err := h.Device.HapticTrigger(byte(pulseType)); err != nil {
			return errResp(req.ID, err.Error())
		}
		return okResp(req.ID, nil)

	case "haptic_sequence":
		// params: {"steps": [{"pulse": 4, "delay": 30}, ...], "repeat": 1}
		stepsRaw, ok := req.Params["steps"]
		if !ok {
			return errResp(req.ID, "missing 'steps' param")
		}
		stepsArr, ok := stepsRaw.([]interface{})
		if !ok {
			return errResp(req.ID, "'steps' must be an array")
		}
		var steps []hidpp.HapticSequenceStep
		for _, s := range stepsArr {
			sm, ok := s.(map[string]interface{})
			if !ok {
				continue
			}
			pulse := 0
			delay := 0
			if v, ok := sm["pulse"].(float64); ok {
				pulse = int(v)
			}
			if v, ok := sm["delay"].(float64); ok {
				delay = int(v)
			}
			steps = append(steps, hidpp.HapticSequenceStep{
				Pulse: byte(pulse),
				Delay: delay,
			})
		}
		repeat := ParamInt(req.Params, "repeat", 1)
		// Run in background so IPC doesn't block during playback
		go func() {
			if err := h.Device.HapticPlaySequence(steps, repeat); err != nil {
				fmt.Printf("[HAPTIC] Sequence error: %v\n", err)
			}
		}()
		return okResp(req.ID, nil)

	case "health":
		return h.handleHealth(req)

	default:
		return errResp(req.ID, fmt.Sprintf("unknown command: %s", req.Cmd))
	}
}

func (h *Handler) handleHealth(req *Request) *Response {
	var mem runtime.MemStats
	runtime.ReadMemStats(&mem)
	return okResp(req.ID, map[string]interface{}{
		"ok":         true,
		"version":    h.Version,
		"uptime_s":   int(time.Since(h.StartTime).Seconds()),
		"mem_mb":     float64(mem.Alloc) / 1024 / 1024,
		"sys_mb":     float64(mem.Sys) / 1024 / 1024,
		"goroutines": runtime.NumGoroutine(),
	})
}

func okResp(id int, data map[string]interface{}) *Response {
	return &Response{ID: id, OK: true, Data: data}
}

func errResp(id int, msg string) *Response {
	return &Response{ID: id, OK: false, Err: msg}
}
