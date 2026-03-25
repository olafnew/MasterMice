package hidpp

import (
	"fmt"
	mlog "github.com/olafnew/mastermice-svc/internal/logging"
	"time"

	"golang.org/x/sys/windows"
)

// Device represents a connected Logitech HID++ device with discovered features.
type Device struct {
	Transport *Transport
	DevIdx    byte
	ConnPID   uint16

	// Identification
	Name     string
	ModelKey string
	Profile  *DeviceProfile

	// Discovered feature indices (0 = not found)
	NameIdx      byte
	BattIdx      byte
	BattType     string // "unified" or "level"
	DPIIdx       byte
	SmartShiftIdx byte
	SmartShiftVer int // 1 or 2
	HiResIdx     byte
	ScrollCtrlIdx byte
	HapticIdx     byte
	ButtonSensIdx byte
	ReprogIdx     byte

	// SHORT handle for haptic motor (HidD_SetOutputReport)
	ShortHandle windows.Handle

	// Cached state (updated on read, used by get_status to avoid slow HID++)
	CachedBattLevel       int  // last known battery level (0-100)
	CachedBattCharging    bool // last known charging state
	CachedDPI             int  // last known DPI value
	CachedHapticEnabled   bool
	CachedHapticIntensity int
}

// DiscoverFeatures uses IRoot to find all features declared in the device profile.
func (d *Device) DiscoverFeatures() error {
	if d.Profile == nil {
		return fmt.Errorf("no device profile set")
	}
	p := d.Profile
	t := d.Transport

	// Battery
	d.BattIdx, _ = t.RequestIRoot(p.BatteryFeatureID)
	if d.BattIdx != 0 {
		if p.BatteryFeatureID == FeatBattUnified {
			d.BattType = "unified"
		} else {
			d.BattType = "level"
		}
		mlog.Printf("[DEVICE] Battery (0x%04X) at index 0x%02X\n", p.BatteryFeatureID, d.BattIdx)
	}

	// DPI
	d.DPIIdx, _ = t.RequestIRoot(FeatAdjDPI)
	if d.DPIIdx != 0 {
		mlog.Printf("[DEVICE] DPI at index 0x%02X\n", d.DPIIdx)
	}

	// SmartShift
	d.SmartShiftIdx, _ = t.RequestIRoot(p.SmartShiftFeatID)
	if d.SmartShiftIdx != 0 {
		d.SmartShiftVer = p.SmartShiftVer
		mlog.Printf("[DEVICE] SmartShift v%d at index 0x%02X\n", d.SmartShiftVer, d.SmartShiftIdx)
	}

	// Hi-Res Wheel (try v2 first, then v1)
	d.HiResIdx, _ = t.RequestIRoot(FeatHiResWheel2)
	if d.HiResIdx == 0 {
		d.HiResIdx, _ = t.RequestIRoot(FeatHiResWheel)
	}
	if d.HiResIdx != 0 {
		mlog.Printf("[DEVICE] HiRes Wheel at index 0x%02X\n", d.HiResIdx)
	}

	// Smooth Scroll — often on the same feature index as HiRes wheel
	d.ScrollCtrlIdx = d.HiResIdx
	if d.ScrollCtrlIdx == 0 {
		// Fallback: try dedicated scroll control features
		d.ScrollCtrlIdx, _ = t.RequestIRoot(0x2121)
		if d.ScrollCtrlIdx == 0 {
			d.ScrollCtrlIdx, _ = t.RequestIRoot(0x2101)
		}
	}
	if d.ScrollCtrlIdx != 0 {
		mlog.Printf("[DEVICE] Scroll Control at index 0x%02X\n", d.ScrollCtrlIdx)
	}

	// Haptic motor (MX4 only)
	if p.HasHaptics && p.HapticFeatureID != 0 {
		d.HapticIdx, _ = t.RequestIRoot(p.HapticFeatureID)
		if d.HapticIdx != 0 {
			mlog.Printf("[DEVICE] Haptic (0x%04X) at index 0x%02X\n", p.HapticFeatureID, d.HapticIdx)
			// Open SHORT handle for haptic commands
			if err := d.OpenShortHandle(); err != nil {
				mlog.Printf("[DEVICE] WARNING: Haptic SHORT handle failed: %v\n", err)
			}
		}
	}

	// Button Sensitivity (MX4 only)
	if p.HasButtonSens && p.ButtonSensFeatID != 0 {
		d.ButtonSensIdx, _ = t.RequestIRoot(p.ButtonSensFeatID)
		if d.ButtonSensIdx != 0 {
			mlog.Printf("[DEVICE] Button Sensitivity (0x%04X) at index 0x%02X\n",
				p.ButtonSensFeatID, d.ButtonSensIdx)
		}
	}

	// REPROG_V4
	d.ReprogIdx, _ = t.RequestIRoot(FeatReprogV4)
	if d.ReprogIdx != 0 {
		mlog.Printf("[DEVICE] REPROG_V4 at index 0x%02X\n", d.ReprogIdx)
		d.DivertButtons()
	}

	return nil
}

// DivertButtons configures REPROG_V4 to divert gesture and actions ring buttons.
// This makes the device send button press/release events AND raw XY movement
// data through the HID++ channel instead of standard mouse reports.
//
// Divert flags (from Wireshark captures of Logitech Options+):
//   Bit 0: divert (redirect button events to HID++)
//   Bit 1: dvalid (divert flag is valid)
//   Bit 4: rawXY (divert raw mouse XY movement while button held)
//   Bit 5: rawXY dvalid (rawXY flag is valid)
//
// 0x03 = divert button only (events but NO movement)
// 0x33 = divert button + raw XY (events AND movement — needed for gesture swipes)
func (d *Device) DivertButtons() {
	if d.ReprogIdx == 0 {
		return
	}
	t := d.Transport

	// Divert gesture button (CID 0x00C3) with rawXY
	// func=3 (setCIDReporting), params=[CID_hi, CID_lo, flags]
	_, err := t.Request(d.ReprogIdx, 3,
		[]byte{byte(CIDGesture >> 8), byte(CIDGesture & 0xFF), 0x33},
		2*time.Second)
	if err != nil {
		mlog.Printf("[DEVICE] Divert gesture (0x00C3) failed: %v\n", err)
	} else {
		mlog.Println("[DEVICE] Divert gesture (0x00C3): OK (button + rawXY)")
	}

	// Divert actions ring / haptic panel (CID 0x01A0) — button only, no rawXY needed
	_, err = t.Request(d.ReprogIdx, 3,
		[]byte{byte(CIDActionsRing >> 8), byte(CIDActionsRing & 0xFF), 0x03},
		2*time.Second)
	if err != nil {
		mlog.Printf("[DEVICE] Divert actions ring (0x01A0): not available (MX3)\n")
	} else {
		mlog.Println("[DEVICE] Divert actions ring (0x01A0): OK")
	}
}

// ── Button Sensitivity ──────────────────────────────────────────

// Button sensitivity presets (MX4)
const (
	ButtonSensLight  uint16 = 0x0F3E
	ButtonSensMedium uint16 = 0x130E
	ButtonSensHard   uint16 = 0x16DE
	ButtonSensFirm   uint16 = 0x1958
)

// GetButtonSensitivity reads the current button sensitivity value.
// Returns the raw 2-byte preset value (e.g. 0x0F3E=Light, 0x130E=Medium).
func (d *Device) GetButtonSensitivity() (uint16, error) {
	if d.ButtonSensIdx == 0 {
		return 0, fmt.Errorf("button sensitivity not available")
	}
	// func=2: getCurrentValue → [value_hi, value_lo]
	report, err := d.Transport.Request(d.ButtonSensIdx, 2, nil, 2*time.Second)
	if err != nil {
		return 0, err
	}
	if len(report.Params) >= 2 {
		return uint16(report.Params[0])<<8 | uint16(report.Params[1]), nil
	}
	return 0, fmt.Errorf("button sensitivity response too short")
}

// SetButtonSensitivity sets the button sensitivity preset.
// Use ButtonSensLight, ButtonSensMedium, ButtonSensHard, ButtonSensFirm.
func (d *Device) SetButtonSensitivity(preset uint16) error {
	if d.ButtonSensIdx == 0 {
		return fmt.Errorf("button sensitivity not available")
	}
	hi := byte(preset >> 8)
	lo := byte(preset & 0xFF)
	// Protocol from Wireshark: func=3, params=[0x00, preset_hi, preset_lo, extra_hi, extra_lo]
	// Each preset has a companion 2-byte value (from Logitech Options+ captures):
	//   Light  (0x0F3E) → extra 0x261B
	//   Medium (0x130E) → extra 0x2FA3
	//   Hard   (0x16DE) → extra 0x392B
	//   Firm   (0x1958) → extra 0x3F5C
	var extra uint16
	switch preset {
	case ButtonSensLight:
		extra = 0x261B
	case ButtonSensMedium:
		extra = 0x2FA3
	case ButtonSensHard:
		extra = 0x392B
	case ButtonSensFirm:
		extra = 0x3F5C
	}
	ehi := byte(extra >> 8)
	elo := byte(extra & 0xFF)
	_, err := d.Transport.Request(d.ButtonSensIdx, 3, []byte{0x00, hi, lo, ehi, elo}, 2*time.Second)
	if err != nil {
		return err
	}
	mlog.Printf("[BTNSENS] Set to 0x%04X\n", preset)
	return nil
}

// ── DPI ──────────────────────────────────────────────────────────

func (d *Device) ReadDPI() (int, error) {
	if d.DPIIdx == 0 {
		return 0, fmt.Errorf("DPI feature not available")
	}
	report, err := d.Transport.Request(d.DPIIdx, 2, []byte{0x00}, 2*time.Second)
	if err != nil {
		return 0, err
	}
	if len(report.Params) >= 3 {
		dpi := int(report.Params[1])<<8 | int(report.Params[2])
		d.CachedDPI = dpi
		return dpi, nil
	}
	return 0, fmt.Errorf("DPI response too short")
}

func (d *Device) SetDPI(dpi int) error {
	if d.DPIIdx == 0 {
		return fmt.Errorf("DPI feature not available")
	}
	if dpi < 200 {
		dpi = 200
	}
	if d.Profile != nil && dpi > d.Profile.DPIMax {
		dpi = d.Profile.DPIMax
	}
	hi := byte((dpi >> 8) & 0xFF)
	lo := byte(dpi & 0xFF)
	report, err := d.Transport.Request(d.DPIIdx, 3, []byte{0x00, hi, lo}, 2*time.Second)
	if err != nil {
		return err
	}
	if len(report.Params) >= 3 {
		actual := int(report.Params[1])<<8 | int(report.Params[2])
		d.CachedDPI = actual
		mlog.Printf("[DPI] Set to %d (requested %d)\n", actual, dpi)
	}
	return nil
}

// ── Battery ──────────────────────────────────────────────────────

type BatteryStatus struct {
	Level    int
	Charging bool
}

func (d *Device) ReadBattery() (*BatteryStatus, error) {
	if d.BattIdx == 0 {
		return nil, fmt.Errorf("battery feature not available")
	}

	if d.BattType == "unified" {
		// 0x1004: func 1 = get_status → [soc, battStatus, extPower]
		// Wireshark confirms: via Bolt, extPower is ALWAYS 0.
		// Charging is indicated by battStatus: 1=recharging, 2=almost_full,
		// 3=charge_complete, 4=recharging_below_optimal, 5=recharging_above_optimal
		// Status 8 = normal/OK (not charging)
		report, err := d.Transport.Request(d.BattIdx, 1, nil, 2*time.Second)
		if err != nil {
			return nil, err
		}
		if len(report.Params) >= 3 {
			battStatus := report.Params[1]
			extPower := report.Params[2]
			// Check BOTH: extPower (works on Bluetooth) OR battStatus (works on Bolt)
			charging := (extPower >= 1 && extPower <= 5) || (battStatus >= 1 && battStatus <= 5)
			bs := &BatteryStatus{
				Level:    int(report.Params[0]),
				Charging: charging,
			}
			d.CachedBattLevel = bs.Level
			d.CachedBattCharging = bs.Charging
			return bs, nil
		}
	} else {
		// 0x1000: func 0 = get_battery_level → [level, nextLevel, battStatus]
		report, err := d.Transport.Request(d.BattIdx, 0, nil, 2*time.Second)
		if err != nil {
			return nil, err
		}
		if len(report.Params) >= 3 {
			level := int(report.Params[0])
			battStatus := report.Params[2]
			charging := battStatus >= 1 && battStatus <= 4

			// MX3 quirk: reports 0% while charging — use cache
			if charging && level == 0 && d.CachedBattLevel > 0 {
				level = d.CachedBattLevel
			} else if !charging && level > 0 {
				d.CachedBattLevel = level
			}

			bs := &BatteryStatus{Level: level, Charging: charging}
			d.CachedBattCharging = bs.Charging
			return bs, nil
		}
	}
	return nil, fmt.Errorf("battery response too short")
}

// ── SmartShift ───────────────────────────────────────────────────

type SmartShiftStatus struct {
	Enabled   bool
	Threshold int
	Force     int // -1 if v1 (no force)
	Mode      int
}

func (d *Device) GetSmartShift() (*SmartShiftStatus, error) {
	if d.SmartShiftIdx == 0 {
		return nil, fmt.Errorf("SmartShift not available")
	}

	if d.SmartShiftVer == 2 {
		report, err := d.Transport.Request(d.SmartShiftIdx, 1, nil, 2*time.Second)
		if err != nil {
			return nil, err
		}
		if len(report.Params) >= 3 {
			mode := int(report.Params[0])
			threshold := int(report.Params[1])
			force := int(report.Params[2])
			return &SmartShiftStatus{
				Enabled:   threshold != 0xFF,
				Threshold: threshold,
				Force:     force,
				Mode:      mode,
			}, nil
		}
	} else {
		report, err := d.Transport.Request(d.SmartShiftIdx, 0, nil, 2*time.Second)
		if err != nil {
			return nil, err
		}
		if len(report.Params) >= 3 {
			mode := int(report.Params[0])
			threshold := int(report.Params[1])
			return &SmartShiftStatus{
				Enabled:   threshold != 0xFF,
				Threshold: threshold,
				Force:     -1,
				Mode:      mode,
			}, nil
		}
	}
	return nil, fmt.Errorf("SmartShift response too short")
}

func (d *Device) SetSmartShift(threshold int, force int, enabled bool) error {
	if d.SmartShiftIdx == 0 {
		return fmt.Errorf("SmartShift not available")
	}

	t := threshold
	if !enabled {
		t = 0xFF
	} else {
		if t < 1 {
			t = 1
		}
		if t > 50 {
			t = 50
		}
	}

	if d.SmartShiftVer == 2 {
		f := force
		if f < 1 {
			f = 1
		}
		if f > 100 {
			f = 100
		}
		_, err := d.Transport.Request(d.SmartShiftIdx, 2,
			[]byte{0x02, byte(t), byte(f)}, 2*time.Second)
		return err
	}

	// v1: func 1 SET [autoDisengage=10, threshold]
	_, err := d.Transport.Request(d.SmartShiftIdx, 1,
		[]byte{10, byte(t)}, 2*time.Second)
	return err
}

// ── Hi-Res Wheel ─────────────────────────────────────────────────

type HiResStatus struct {
	Target bool
	HiRes  bool
	Invert bool
}

func (d *Device) GetHiResWheel() (*HiResStatus, error) {
	if d.HiResIdx == 0 {
		return nil, fmt.Errorf("HiRes wheel not available")
	}
	report, err := d.Transport.Request(d.HiResIdx, 1, nil, 2*time.Second)
	if err != nil {
		return nil, err
	}
	if len(report.Params) >= 1 {
		flags := report.Params[0]
		return &HiResStatus{
			Target: flags&0x01 != 0,
			HiRes:  flags&0x02 != 0,
			Invert: flags&0x04 != 0,
		}, nil
	}
	return nil, fmt.Errorf("HiRes response too short")
}

func (d *Device) SetHiResWheel(hires, invert *bool) error {
	if d.HiResIdx == 0 {
		return fmt.Errorf("HiRes wheel not available")
	}
	current, err := d.GetHiResWheel()
	if err != nil {
		return err
	}

	var flags byte
	h := current.HiRes
	if hires != nil {
		h = *hires
	}
	inv := current.Invert
	if invert != nil {
		inv = *invert
	}
	if current.Target {
		flags |= 0x01
	}
	if h {
		flags |= 0x02
	}
	if inv {
		flags |= 0x04
	}

	_, err = d.Transport.Request(d.HiResIdx, 2, []byte{flags}, 2*time.Second)
	return err
}

// ── Smooth Scroll ────────────────────────────────────────────────

func (d *Device) GetSmoothScroll() (bool, error) {
	if d.ScrollCtrlIdx == 0 {
		return false, fmt.Errorf("smooth scroll not available")
	}
	report, err := d.Transport.Request(d.ScrollCtrlIdx, 1, nil, 2*time.Second)
	if err != nil {
		return false, err
	}
	if len(report.Params) >= 1 {
		return report.Params[0]&0x01 != 0, nil
	}
	return false, fmt.Errorf("smooth scroll response too short")
}

func (d *Device) SetSmoothScroll(enabled bool) error {
	if d.ScrollCtrlIdx == 0 {
		return fmt.Errorf("smooth scroll not available")
	}
	var val byte
	if enabled {
		if d.Profile != nil {
			val = d.Profile.SmoothScrollOn
		} else {
			val = 0x01
		}
	}
	_, err := d.Transport.Request(d.ScrollCtrlIdx, 2, []byte{val}, 2*time.Second)
	return err
}
