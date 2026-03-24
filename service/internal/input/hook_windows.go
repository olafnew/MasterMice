package input

import (
	"fmt"
	"runtime"
	"sync"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	pSetWindowsHookExW  = user32.NewProc("SetWindowsHookExW")
	pUnhookWindowsHookEx = user32.NewProc("UnhookWindowsHookEx")
	pCallNextHookEx      = user32.NewProc("CallNextHookEx")
	pGetMessageW         = user32.NewProc("GetMessageW")
	pTranslateMessage    = user32.NewProc("TranslateMessage")
	pDispatchMessageW    = user32.NewProc("DispatchMessageW")

	kernel32          = windows.NewLazySystemDLL("kernel32.dll")
	pGetModuleHandleW = kernel32.NewProc("GetModuleHandleW")
)

const (
	WH_MOUSE_LL    = 14
	WM_XBUTTONDOWN = 0x020B
	WM_XBUTTONUP   = 0x020C
	WM_MBUTTONDOWN = 0x0207
	WM_MBUTTONUP   = 0x0208
	WM_MOUSEWHEEL  = 0x020A
	WM_MOUSEHWHEEL = 0x020E

	XBUTTON1 = 1
	XBUTTON2 = 2
)

// MSLLHOOKSTRUCT matches the Windows MSLLHOOKSTRUCT.
type MSLLHOOKSTRUCT struct {
	X         int32
	Y         int32
	MouseData uint32
	Flags     uint32
	Time      uint32
	ExtraInfo uintptr
}

// MSG matches the Windows MSG struct.
type MSG struct {
	Hwnd    uintptr
	Message uint32
	WParam  uintptr
	LParam  uintptr
	Time    uint32
	Pt      struct{ X, Y int32 }
}

// MouseHook implements a WH_MOUSE_LL hook in Go.
type MouseHook struct {
	hhook      uintptr
	mappings   map[string]string // button_key → action_id
	mu         sync.RWMutex
	stopCh     chan struct{}

	// Scroll settings
	InvertVScroll bool
	InvertHScroll bool
}

// NewMouseHook creates a new mouse hook (not yet installed).
func NewMouseHook() *MouseHook {
	return &MouseHook{
		mappings: make(map[string]string),
		stopCh:   make(chan struct{}),
	}
}

// SetMappings updates the button→action mappings (thread-safe).
func (h *MouseHook) SetMappings(m map[string]string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.mappings = m
}

// Global hook instance (Windows callback can't receive Go closures)
var globalHook *MouseHook

// Start installs the hook and runs the message pump. BLOCKS until Stop is called.
// Must be called from a dedicated goroutine.
func (h *MouseHook) Start() error {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()

	globalHook = h

	modHandle, _, _ := pGetModuleHandleW.Call(0)

	hhook, _, err := pSetWindowsHookExW.Call(
		WH_MOUSE_LL,
		windows.NewCallback(mouseHookProc),
		modHandle,
		0,
	)
	if hhook == 0 {
		return fmt.Errorf("SetWindowsHookExW failed: %v", err)
	}
	h.hhook = hhook
	fmt.Println("[MouseHook] Hook installed")

	// Message pump — required for WH_MOUSE_LL to receive events
	var msg MSG
	for {
		select {
		case <-h.stopCh:
			pUnhookWindowsHookEx.Call(h.hhook)
			fmt.Println("[MouseHook] Hook removed")
			return nil
		default:
		}

		ret, _, _ := pGetMessageW.Call(
			uintptr(unsafe.Pointer(&msg)),
			0, 0, 0,
		)
		if ret == 0 || ret == uintptr(^uint(0)) { // WM_QUIT or error
			break
		}
		pTranslateMessage.Call(uintptr(unsafe.Pointer(&msg)))
		pDispatchMessageW.Call(uintptr(unsafe.Pointer(&msg)))
	}

	pUnhookWindowsHookEx.Call(h.hhook)
	return nil
}

// Stop signals the hook to uninstall and the message pump to exit.
func (h *MouseHook) Stop() {
	close(h.stopCh)
}

// mouseHookProc is the WH_MOUSE_LL callback.
// CRITICAL: Must return quickly (<200ms) or Windows will unhook it.
func mouseHookProc(nCode, wParam, lParam uintptr) uintptr {
	if nCode < 0 || globalHook == nil {
		ret, _, _ := pCallNextHookEx.Call(0, nCode, wParam, lParam)
		return ret
	}

	info := (*MSLLHOOKSTRUCT)(unsafe.Pointer(lParam))
	blocked := false

	globalHook.mu.RLock()
	mappings := globalHook.mappings
	globalHook.mu.RUnlock()

	switch uint32(wParam) {
	case WM_XBUTTONDOWN:
		hiWord := (info.MouseData >> 16) & 0xFFFF
		var buttonKey string
		if hiWord == XBUTTON1 {
			buttonKey = "xbutton1"
		} else if hiWord == XBUTTON2 {
			buttonKey = "xbutton2"
		}
		if buttonKey != "" {
			if actionID, ok := mappings[buttonKey]; ok && actionID != "" && actionID != "none" {
				go ExecuteAction(actionID) // execute on separate goroutine
				blocked = true
			}
		}

	case WM_XBUTTONUP:
		hiWord := (info.MouseData >> 16) & 0xFFFF
		var buttonKey string
		if hiWord == XBUTTON1 {
			buttonKey = "xbutton1"
		} else if hiWord == XBUTTON2 {
			buttonKey = "xbutton2"
		}
		if buttonKey != "" {
			if actionID, ok := mappings[buttonKey]; ok && actionID != "" && actionID != "none" {
				blocked = true // also block the UP event
			}
		}

	case WM_MBUTTONDOWN:
		if actionID, ok := mappings["middle"]; ok && actionID != "" && actionID != "none" {
			go ExecuteAction(actionID)
			blocked = true
		}

	case WM_MBUTTONUP:
		if actionID, ok := mappings["middle"]; ok && actionID != "" && actionID != "none" {
			blocked = true
		}

	case WM_MOUSEWHEEL:
		delta := int16(info.MouseData >> 16)
		if globalHook.InvertVScroll {
			delta = -delta
		}
		if delta > 0 {
			if actionID, ok := mappings["scroll_up"]; ok && actionID != "" && actionID != "none" {
				go ExecuteAction(actionID)
				blocked = true
			}
		} else if delta < 0 {
			if actionID, ok := mappings["scroll_down"]; ok && actionID != "" && actionID != "none" {
				go ExecuteAction(actionID)
				blocked = true
			}
		}

	case WM_MOUSEHWHEEL:
		delta := int16(info.MouseData >> 16)
		if globalHook.InvertHScroll {
			delta = -delta
		}
		// Horizontal scroll → thumb_wheel action
		if actionID, ok := mappings["thumb_wheel"]; ok && actionID != "" && actionID != "none" {
			go ExecuteAction(actionID)
			blocked = true
		}
	}

	if blocked {
		return 1
	}
	ret, _, _ := pCallNextHookEx.Call(0, nCode, wParam, lParam)
	return ret
}
