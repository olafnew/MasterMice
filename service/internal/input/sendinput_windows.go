package input

import (
	"fmt"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	user32       = windows.NewLazySystemDLL("user32.dll")
	pSendInput   = user32.NewProc("SendInput")
)

const (
	INPUT_KEYBOARD       = 1
	KEYEVENTF_EXTENDEDKEY = 0x0001
	KEYEVENTF_KEYUP       = 0x0002
)

// KEYBDINPUT matches the Windows KEYBDINPUT struct.
type KEYBDINPUT struct {
	Vk        uint16
	Scan      uint16
	Flags     uint32
	Time      uint32
	ExtraInfo uintptr
}

// INPUT matches the Windows INPUT struct (keyboard variant).
type INPUT struct {
	Type uint32
	Ki   KEYBDINPUT
	_    [8]byte // padding to match union size
}

// ExecuteAction looks up an action by ID and injects the key combo via SendInput.
// Returns true if the action was found and executed, false for "none" or unknown.
func ExecuteAction(actionID string) bool {
	if actionID == "" || actionID == "none" {
		return false
	}

	action, ok := AllActions[actionID]
	if !ok || action.Keys == nil {
		return false
	}

	sendKeyCombo(action.Keys)
	return true
}

// sendKeyCombo presses all keys simultaneously, holds briefly, then releases in reverse.
// Matches Python's send_key_combo behavior.
func sendKeyCombo(keys []uint16) {
	n := len(keys)
	if n == 0 {
		return
	}

	// Build input array: N key-down + N key-up
	inputs := make([]INPUT, n*2)

	// Key-down events (in order)
	for i, vk := range keys {
		var flags uint32
		if IsExtendedKey(vk) {
			flags |= KEYEVENTF_EXTENDEDKEY
		}
		inputs[i] = INPUT{
			Type: INPUT_KEYBOARD,
			Ki: KEYBDINPUT{
				Vk:    vk,
				Flags: flags,
			},
		}
	}

	// Key-up events (reverse order)
	for i := 0; i < n; i++ {
		vk := keys[n-1-i]
		var flags uint32 = KEYEVENTF_KEYUP
		if IsExtendedKey(vk) {
			flags |= KEYEVENTF_EXTENDEDKEY
		}
		inputs[n+i] = INPUT{
			Type: INPUT_KEYBOARD,
			Ki: KEYBDINPUT{
				Vk:    vk,
				Flags: flags,
			},
		}
	}

	// Send key-down events
	sendInputs(inputs[:n])

	// Brief hold (matches Python's 50ms sleep)
	time.Sleep(50 * time.Millisecond)

	// Send key-up events
	sendInputs(inputs[n:])
}

func sendInputs(inputs []INPUT) {
	if len(inputs) == 0 {
		return
	}
	ret, _, err := pSendInput.Call(
		uintptr(len(inputs)),
		uintptr(unsafe.Pointer(&inputs[0])),
		uintptr(unsafe.Sizeof(inputs[0])),
	)
	if ret == 0 {
		fmt.Printf("[Input] SendInput failed: %v\n", err)
	}
}
