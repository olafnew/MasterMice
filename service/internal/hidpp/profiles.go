package hidpp

import "strings"

// DeviceProfile defines the capabilities of a specific mouse model.
type DeviceProfile struct {
	Name             string
	NameMatches      []string // substrings to match against DEVICE_NAME (lowercase)
	Buttons          []string
	BatteryFeatureID uint16
	BattSOCCharging  bool   // reports correct SOC while charging
	SmartShiftFeatID uint16
	SmartShiftVer    int    // 1 or 2
	SmartShiftForce  bool   // has force parameter
	HasHaptics       bool
	HapticFeatureID  uint16
	HasButtonSens    bool   // MX4 button press sensitivity
	ButtonSensFeatID uint16
	DPIMax           int
	DPIFlag          byte
	SmoothScrollOn   byte // value to write for "smooth scroll ON"
}

// Profiles maps model keys to their device profiles.
var Profiles = map[string]*DeviceProfile{
	ModelMX3: {
		Name:        "MX Master 3/3S",
		NameMatches: []string{"master 3"},
		Buttons: []string{
			"left_click", "right_click",
			"scroll_up", "scroll_down", "middle", "mode_shift",
			"xbutton2", "xbutton1", "gesture", "thumb_wheel",
		},
		BatteryFeatureID: FeatBattLevel,
		BattSOCCharging:  false,
		SmartShiftFeatID: FeatSmartShift,
		SmartShiftVer:    1,
		SmartShiftForce:  false,
		HasHaptics:       false,
		HapticFeatureID:  0,
		HasButtonSens:    false,
		ButtonSensFeatID: 0,
		DPIMax:           4000,
		DPIFlag:          0x00,
		SmoothScrollOn:   0x03,
	},
	ModelMX4: {
		Name:        "MX Master 4",
		NameMatches: []string{"master 4"},
		Buttons: []string{
			"left_click", "right_click",
			"scroll_up", "scroll_down", "middle", "mode_shift",
			"xbutton2", "xbutton1", "gesture", "thumb_wheel",
			"haptic_panel",
		},
		BatteryFeatureID: FeatBattUnified,
		BattSOCCharging:  true,
		SmartShiftFeatID: FeatSmartShift2,
		SmartShiftVer:    2,
		SmartShiftForce:  true,
		HasHaptics:       true,
		HapticFeatureID:  FeatHaptic,
		HasButtonSens:    true,
		ButtonSensFeatID: FeatButtonSens,
		DPIMax:           8000,
		DPIFlag:          0x01,
		SmoothScrollOn:   0x01,
	},
}

// MatchProfile returns the model key and profile for a given device name,
// or empty string and nil if no match.
func MatchProfile(deviceName string) (string, *DeviceProfile) {
	lower := strings.ToLower(deviceName)
	for key, p := range Profiles {
		for _, substr := range p.NameMatches {
			if strings.Contains(lower, substr) {
				return key, p
			}
		}
	}
	return "", nil
}
