// Package input handles Windows input injection (SendInput) and mouse hooks.
package input

// VK codes used by MasterMice actions.
const (
	VK_TAB             = 0x09
	VK_SHIFT           = 0x10
	VK_CONTROL         = 0x11
	VK_MENU            = 0x12 // Alt
	VK_LWIN            = 0x5B
	VK_BROWSER_BACK    = 0xA6
	VK_BROWSER_FORWARD = 0xA7
	VK_VOLUME_MUTE     = 0xAD
	VK_VOLUME_DOWN     = 0xAE
	VK_VOLUME_UP       = 0xAF
	VK_MEDIA_NEXT      = 0xB0
	VK_MEDIA_PREV      = 0xB1
	VK_MEDIA_STOP      = 0xB2
	VK_MEDIA_PLAY      = 0xB3
	VK_A               = 0x41
	VK_C               = 0x43
	VK_D               = 0x44
	VK_F               = 0x46
	VK_S               = 0x53
	VK_T               = 0x54
	VK_V               = 0x56
	VK_W               = 0x57
	VK_X               = 0x58
	VK_Z               = 0x5A
	VK_LEFT            = 0x25
	VK_RIGHT           = 0x27
)

// Action defines a keyboard shortcut to inject via SendInput.
type Action struct {
	ID       string
	Label    string
	Category string
	Keys     []uint16 // VK codes to press simultaneously
}

// AllActions is the complete action table — 22 actions matching Python's key_simulator.py.
var AllActions = map[string]Action{
	// Navigation
	"alt_tab":       {ID: "alt_tab", Label: "Alt + Tab (Switch Windows)", Category: "Navigation", Keys: []uint16{VK_MENU, VK_TAB}},
	"alt_shift_tab": {ID: "alt_shift_tab", Label: "Alt + Shift + Tab (Switch Windows Reverse)", Category: "Navigation", Keys: []uint16{VK_MENU, VK_SHIFT, VK_TAB}},
	"win_d":         {ID: "win_d", Label: "Show Desktop (Win+D)", Category: "Navigation", Keys: []uint16{VK_LWIN, VK_D}},
	"task_view":              {ID: "task_view", Label: "Task View (Win+Tab)", Category: "Navigation", Keys: []uint16{VK_LWIN, VK_TAB}},
	"virtual_desktop_left":  {ID: "virtual_desktop_left", Label: "Virtual Desktop Left (Win+Ctrl+←)", Category: "Navigation", Keys: []uint16{VK_LWIN, VK_CONTROL, VK_LEFT}},
	"virtual_desktop_right": {ID: "virtual_desktop_right", Label: "Virtual Desktop Right (Win+Ctrl+→)", Category: "Navigation", Keys: []uint16{VK_LWIN, VK_CONTROL, VK_RIGHT}},

	// Browser
	"browser_back":    {ID: "browser_back", Label: "Browser Back", Category: "Browser", Keys: []uint16{VK_BROWSER_BACK}},
	"browser_forward": {ID: "browser_forward", Label: "Browser Forward", Category: "Browser", Keys: []uint16{VK_BROWSER_FORWARD}},
	"close_tab":       {ID: "close_tab", Label: "Close Tab (Ctrl+W)", Category: "Browser", Keys: []uint16{VK_CONTROL, VK_W}},
	"new_tab":         {ID: "new_tab", Label: "New Tab (Ctrl+T)", Category: "Browser", Keys: []uint16{VK_CONTROL, VK_T}},

	// Editing
	"copy":       {ID: "copy", Label: "Copy (Ctrl+C)", Category: "Editing", Keys: []uint16{VK_CONTROL, VK_C}},
	"paste":      {ID: "paste", Label: "Paste (Ctrl+V)", Category: "Editing", Keys: []uint16{VK_CONTROL, VK_V}},
	"cut":        {ID: "cut", Label: "Cut (Ctrl+X)", Category: "Editing", Keys: []uint16{VK_CONTROL, VK_X}},
	"undo":       {ID: "undo", Label: "Undo (Ctrl+Z)", Category: "Editing", Keys: []uint16{VK_CONTROL, VK_Z}},
	"select_all": {ID: "select_all", Label: "Select All (Ctrl+A)", Category: "Editing", Keys: []uint16{VK_CONTROL, VK_A}},
	"save":       {ID: "save", Label: "Save (Ctrl+S)", Category: "Editing", Keys: []uint16{VK_CONTROL, VK_S}},
	"find":       {ID: "find", Label: "Find (Ctrl+F)", Category: "Editing", Keys: []uint16{VK_CONTROL, VK_F}},

	// Media
	"volume_up":   {ID: "volume_up", Label: "Volume Up", Category: "Media", Keys: []uint16{VK_VOLUME_UP}},
	"volume_down": {ID: "volume_down", Label: "Volume Down", Category: "Media", Keys: []uint16{VK_VOLUME_DOWN}},
	"volume_mute": {ID: "volume_mute", Label: "Volume Mute", Category: "Media", Keys: []uint16{VK_VOLUME_MUTE}},
	"play_pause":  {ID: "play_pause", Label: "Play / Pause", Category: "Media", Keys: []uint16{VK_MEDIA_PLAY}},
	"next_track":  {ID: "next_track", Label: "Next Track", Category: "Media", Keys: []uint16{VK_MEDIA_NEXT}},
	"prev_track":  {ID: "prev_track", Label: "Previous Track", Category: "Media", Keys: []uint16{VK_MEDIA_PREV}},

	// Gestures (default swipe actions)
	"minimize_all": {ID: "minimize_all", Label: "Minimize All (Win+D)", Category: "Navigation", Keys: []uint16{VK_LWIN, VK_D}},
	"restore_all":  {ID: "restore_all", Label: "Restore All (Win+D)", Category: "Navigation", Keys: []uint16{VK_LWIN, VK_D}},

	// Other
	"none": {ID: "none", Label: "Do Nothing (Pass-through)", Category: "Other", Keys: nil},
}

// IsExtendedKey returns true if the VK code requires the KEYEVENTF_EXTENDEDKEY flag.
func IsExtendedKey(vk uint16) bool {
	switch vk {
	case VK_BROWSER_BACK, VK_BROWSER_FORWARD,
		VK_VOLUME_MUTE, VK_VOLUME_DOWN, VK_VOLUME_UP,
		VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_STOP, VK_MEDIA_PLAY,
		VK_LWIN, VK_LEFT, VK_RIGHT:
		return true
	}
	return false
}
