// desktop-test — Interactive minimize/restore test tool.
// Press 1 to minimize all windows, press 2 to restore them.
// Full debug output for diagnosing SetWindowPlacement issues.
package main

import (
	"bufio"
	"fmt"
	"os"
	"sync"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

const (
	SW_MINIMIZE      = 6
	SW_SHOWMINIMIZED = 2
	SW_SHOWNORMAL    = 1
	SW_SHOWMAXIMIZED = 3
	SW_RESTORE       = 9
	GW_OWNER         = 4
	WS_EX_TOOLWINDOW = 0x00000080
	WS_EX_APPWINDOW  = 0x00040000
	WS_EX_NOACTIVATE = 0x08000000
	DWMWA_CLOAKED    = 14
)

type WINDOWPLACEMENT struct {
	Length           uint32
	Flags            uint32
	ShowCmd          uint32
	PtMinPosition    POINT
	PtMaxPosition    POINT
	RcNormalPosition RECT
}

type POINT struct{ X, Y int32 }
type RECT struct{ Left, Top, Right, Bottom int32 }

var (
	user32 = windows.NewLazySystemDLL("user32.dll")
	dwmapi = windows.NewLazySystemDLL("dwmapi.dll")

	pEnumWindows        = user32.NewProc("EnumWindows")
	pGetWindowLongW     = user32.NewProc("GetWindowLongW")
	pGetWindow          = user32.NewProc("GetWindow")
	pIsWindowVisible    = user32.NewProc("IsWindowVisible")
	pIsWindow           = user32.NewProc("IsWindow")
	pGetWindowPlacement = user32.NewProc("GetWindowPlacement")
	pSetWindowPlacement = user32.NewProc("SetWindowPlacement")
	pShowWindow         = user32.NewProc("ShowWindow")
	pGetShellWindow     = user32.NewProc("GetShellWindow")
	pGetDesktopWindow   = user32.NewProc("GetDesktopWindow")
	pGetWindowTextW     = user32.NewProc("GetWindowTextW")
	pGetWindowTextLen   = user32.NewProc("GetWindowTextLengthW")
	pDwmGetWindowAttr   = dwmapi.NewProc("DwmGetWindowAttribute")
)

func showCmdName(cmd uint32) string {
	switch cmd {
	case 1:
		return "NORMAL"
	case 2:
		return "MINIMIZED"
	case 3:
		return "MAXIMIZED"
	case 9:
		return "RESTORE"
	default:
		return fmt.Sprintf("(%d)", cmd)
	}
}

func getWindowText(hwnd uintptr) string {
	length, _, _ := pGetWindowTextLen.Call(hwnd)
	if length == 0 {
		return ""
	}
	buf := make([]uint16, length+1)
	pGetWindowTextW.Call(hwnd, uintptr(unsafe.Pointer(&buf[0])), uintptr(length+1))
	return syscall.UTF16ToString(buf)
}

func isAltTabWindow(hwnd uintptr) bool {
	ret, _, _ := pIsWindowVisible.Call(hwnd)
	if ret == 0 {
		return false
	}
	var cloaked uint32
	r, _, _ := pDwmGetWindowAttr.Call(hwnd, DWMWA_CLOAKED,
		uintptr(unsafe.Pointer(&cloaked)), unsafe.Sizeof(cloaked))
	if r == 0 && cloaked != 0 {
		return false
	}
	shell, _, _ := pGetShellWindow.Call()
	desk, _, _ := pGetDesktopWindow.Call()
	if hwnd == shell || hwnd == desk {
		return false
	}
	exStyle, _, _ := pGetWindowLongW.Call(hwnd, uintptr(uint32(0xFFFFFFEC))) // GWL_EXSTYLE=-20
	ex := uint32(exStyle)
	if ex&WS_EX_APPWINDOW != 0 {
		return true
	}
	if ex&WS_EX_TOOLWINDOW != 0 {
		return false
	}
	if ex&WS_EX_NOACTIVATE != 0 {
		return false
	}
	owner, _, _ := pGetWindow.Call(hwnd, GW_OWNER)
	if owner != 0 {
		return false
	}
	length, _, _ := pGetWindowTextLen.Call(hwnd)
	if length == 0 {
		return false
	}
	return true
}

type savedWindow struct {
	hwnd      uintptr
	placement WINDOWPLACEMENT
	title     string
}

var (
	mu    sync.Mutex
	saved []savedWindow
)

// Package-level callback to avoid callback slot leak
var enumCB = syscall.NewCallback(func(hwnd uintptr, lParam uintptr) uintptr {
	if !isAltTabWindow(hwnd) {
		return 1
	}
	var wp WINDOWPLACEMENT
	wp.Length = uint32(unsafe.Sizeof(wp))
	ret, _, _ := pGetWindowPlacement.Call(hwnd, uintptr(unsafe.Pointer(&wp)))
	if ret == 0 {
		return 1
	}
	title := getWindowText(hwnd)
	saved = append(saved, savedWindow{hwnd: hwnd, placement: wp, title: title})
	return 1
})

func minimizeAll() {
	mu.Lock()
	defer mu.Unlock()

	saved = saved[:0]
	ret, _, err := pEnumWindows.Call(enumCB, 0)
	if ret == 0 {
		fmt.Printf("EnumWindows FAILED: %v\n", err)
		return
	}

	fmt.Printf("\n=== MINIMIZE ALL (%d windows) ===\n", len(saved))
	minimized := 0
	for i, sw := range saved {
		fmt.Printf("  [%2d] hwnd=0x%08X show=%s title=%q\n",
			i, sw.hwnd, showCmdName(sw.placement.ShowCmd), sw.title)
		fmt.Printf("       pos=(%d,%d)-(%d,%d) length=%d\n",
			sw.placement.RcNormalPosition.Left, sw.placement.RcNormalPosition.Top,
			sw.placement.RcNormalPosition.Right, sw.placement.RcNormalPosition.Bottom,
			sw.placement.Length)

		if sw.placement.ShowCmd != SW_SHOWMINIMIZED {
			pShowWindow.Call(sw.hwnd, SW_MINIMIZE)
			minimized++
		}
	}
	fmt.Printf("Minimized %d windows (saved %d placements)\n", minimized, len(saved))
	fmt.Printf("WINDOWPLACEMENT sizeof = %d (expected 44)\n", unsafe.Sizeof(WINDOWPLACEMENT{}))
}

func restoreAll() {
	mu.Lock()
	defer mu.Unlock()

	if len(saved) == 0 {
		fmt.Println("Nothing to restore (no saved windows)")
		return
	}

	fmt.Printf("\n=== RESTORE ALL (%d saved) ===\n", len(saved))
	restored := 0

	for i := len(saved) - 1; i >= 0; i-- {
		sw := &saved[i] // pointer, not copy

		// Check if window still exists
		valid, _, _ := pIsWindow.Call(sw.hwnd)
		if valid == 0 {
			fmt.Printf("  [%2d] hwnd=0x%08X INVALID (window closed) — skipping\n", i, sw.hwnd)
			continue
		}

		// Determine the right ShowCmd for restoration
		restoreCmd := sw.placement.ShowCmd
		if restoreCmd == SW_SHOWMINIMIZED || restoreCmd == SW_MINIMIZE {
			restoreCmd = SW_RESTORE // was already minimized before we touched it
		}

		fmt.Printf("  [%2d] hwnd=0x%08X saved=%s → restore=%s title=%q\n",
			i, sw.hwnd, showCmdName(sw.placement.ShowCmd), showCmdName(restoreCmd), sw.title)

		// Step 1: ShowWindow to un-minimize FIRST
		ret1, _, err1 := pShowWindow.Call(sw.hwnd, uintptr(restoreCmd))
		fmt.Printf("       ShowWindow(%s) ret=%d err=%v\n", showCmdName(restoreCmd), ret1, err1)

		// Step 2: SetWindowPlacement to restore exact position
		wp := sw.placement
		wp.Length = uint32(unsafe.Sizeof(wp)) // defensive
		wp.ShowCmd = restoreCmd
		ret2, _, err2 := pSetWindowPlacement.Call(sw.hwnd, uintptr(unsafe.Pointer(&wp)))
		fmt.Printf("       SetWindowPlacement ret=%d err=%v\n", ret2, err2)

		if ret2 != 0 {
			restored++
		}
	}

	fmt.Printf("Restored %d / %d windows\n", restored, len(saved))
	saved = saved[:0]
}

func main() {
	fmt.Println("=== Desktop Minimize/Restore Test ===")
	fmt.Printf("WINDOWPLACEMENT size: %d bytes (expected 44)\n\n", unsafe.Sizeof(WINDOWPLACEMENT{}))
	fmt.Println("Commands:")
	fmt.Println("  1 — Minimize all windows (save positions)")
	fmt.Println("  2 — Restore all windows (to saved positions)")
	fmt.Println("  q — Quit")
	fmt.Println()

	scanner := bufio.NewScanner(os.Stdin)
	for {
		fmt.Print("> ")
		if !scanner.Scan() {
			break
		}
		switch scanner.Text() {
		case "1":
			minimizeAll()
		case "2":
			restoreAll()
		case "q", "quit":
			fmt.Println("Bye")
			return
		default:
			fmt.Println("Unknown command. Use 1, 2, or q.")
		}
	}
}
