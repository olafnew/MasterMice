package ipc

import (
	"fmt"
	"runtime"
	"time"

	"github.com/olafnew/mastermice-svc/internal/hidpp"
)

// Handler dispatches IPC commands to device methods.
type Handler struct {
	Device    *hidpp.Device
	StartTime time.Time
}

// NewHandler creates a command handler for the given device.
func NewHandler(device *hidpp.Device) *Handler {
	return &Handler{
		Device:    device,
		StartTime: time.Now(),
	}
}

// Handle processes a request and returns a response.
func (h *Handler) Handle(req *Request) *Response {
	switch req.Cmd {

	case "get_status":
		d := h.Device
		data := map[string]interface{}{
			"connected": d.Transport != nil,
			"model":     d.ModelKey,
			"name":      d.Name,
		}
		if batt, err := d.ReadBattery(); err == nil {
			data["battery_level"] = batt.Level
			data["battery_charging"] = batt.Charging
		}
		if dpi, err := d.ReadDPI(); err == nil {
			data["dpi"] = dpi
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
			"has_haptics":     d.HapticIdx != 0,
			"has_hires":       d.HiResIdx != 0,
			"has_smooth":      d.ScrollCtrlIdx != 0,
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
			b := v.(bool)
			hiresPtr = &b
			data["hires"] = b
		}
		if v, ok := req.Params["invert"]; ok {
			b := v.(bool)
			invertPtr = &b
			data["invert"] = b
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

	case "health":
		var mem runtime.MemStats
		runtime.ReadMemStats(&mem)
		return okResp(req.ID, map[string]interface{}{
			"ok":        true,
			"uptime_s":  int(time.Since(h.StartTime).Seconds()),
			"mem_mb":    float64(mem.Alloc) / 1024 / 1024,
			"sys_mb":    float64(mem.Sys) / 1024 / 1024,
			"goroutines": runtime.NumGoroutine(),
		})

	default:
		return errResp(req.ID, fmt.Sprintf("unknown command: %s", req.Cmd))
	}
}

func okResp(id int, data map[string]interface{}) *Response {
	return &Response{ID: id, OK: true, Data: data}
}

func errResp(id int, msg string) *Response {
	return &Response{ID: id, OK: false, Err: msg}
}
