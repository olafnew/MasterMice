package input

import (
	"sync"
	"syscall"
	"unsafe"

	mlog "github.com/olafnew/mastermice-svc/internal/logging"
	"golang.org/x/sys/windows"
)

// DesktopManager handles minimize-all / restore-all using EnumWindows + GetWindowPlacement.
// Saves exact window positions and restores them independently — survives opening
// new windows between minimize and restore.
//
type DesktopManager struct {
	mu     sync.Mutex
	saved  []savedWindow
	active bool
}

type savedWindow struct {
	hwnd      uintptr
	placement WINDOWPLACEMENT
}

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

const (
	swMINIMIZE      = 6
	swSHOWMINIMIZED = 2
	swSHOWNORMAL    = 1
	swSHOWMAXIMIZED = 3
	swRESTORE       = 9
	gwOWNER         = 4
	wsEX_TOOLWINDOW = 0x00000080
	wsEX_APPWINDOW  = 0x00040000
	wsEX_NOACTIVATE = 0x08000000
	dwmwaCLOAKED    = 14
)

var (
	user32DLL = windows.NewLazySystemDLL("user32.dll")
	dwmapiDLL = windows.NewLazySystemDLL("dwmapi.dll")

	pEnumWindows        = user32DLL.NewProc("EnumWindows")
	pGetWindowLongW     = user32DLL.NewProc("GetWindowLongW")
	pGetWindow          = user32DLL.NewProc("GetWindow")
	pIsWindowVisible    = user32DLL.NewProc("IsWindowVisible")
	pIsWindow           = user32DLL.NewProc("IsWindow")
	pGetWindowPlacement = user32DLL.NewProc("GetWindowPlacement")
	pSetWindowPlacement = user32DLL.NewProc("SetWindowPlacement")
	pShowWindow         = user32DLL.NewProc("ShowWindow")
	pGetShellWindow     = user32DLL.NewProc("GetShellWindow")
	pGetDesktopWindow   = user32DLL.NewProc("GetDesktopWindow")
	pGetWindowTextLenW  = user32DLL.NewProc("GetWindowTextLengthW")
	pDwmGetWindowAttr   = dwmapiDLL.NewProc("DwmGetWindowAttribute")
)

var Desktop = &DesktopManager{}

// Package-level callback — avoids callback slot leak from syscall.NewCallback
var enumCB uintptr
var enumTarget *[]savedWindow

func init() {
	enumCB = syscall.NewCallback(func(hwnd uintptr, lParam uintptr) uintptr {
		if !isAltTabWindow(hwnd) {
			return 1
		}
		var wp WINDOWPLACEMENT
		wp.Length = uint32(unsafe.Sizeof(wp))
		ret, _, _ := pGetWindowPlacement.Call(hwnd, uintptr(unsafe.Pointer(&wp)))
		if ret != 0 && enumTarget != nil {
			*enumTarget = append(*enumTarget, savedWindow{hwnd: hwnd, placement: wp})
		}
		return 1
	})
}

func isAltTabWindow(hwnd uintptr) bool {
	ret, _, _ := pIsWindowVisible.Call(hwnd)
	if ret == 0 {
		return false
	}
	var cloaked uint32
	r, _, _ := pDwmGetWindowAttr.Call(hwnd, dwmwaCLOAKED,
		uintptr(unsafe.Pointer(&cloaked)), unsafe.Sizeof(cloaked))
	if r == 0 && cloaked != 0 {
		return false
	}
	shell, _, _ := pGetShellWindow.Call()
	desk, _, _ := pGetDesktopWindow.Call()
	if hwnd == shell || hwnd == desk {
		return false
	}
	exStyle, _, _ := pGetWindowLongW.Call(hwnd, uintptr(uint32(0xFFFFFFEC)))
	ex := uint32(exStyle)
	if ex&wsEX_APPWINDOW != 0 {
		return true
	}
	if ex&wsEX_TOOLWINDOW != 0 {
		return false
	}
	if ex&wsEX_NOACTIVATE != 0 {
		return false
	}
	owner, _, _ := pGetWindow.Call(hwnd, gwOWNER)
	if owner != 0 {
		return false
	}
	length, _, _ := pGetWindowTextLenW.Call(hwnd)
	return length > 0
}

// MinimizeAll saves all visible window positions and minimizes them.
// If already active (windows already minimized), does nothing to preserve the saved state.
func (dm *DesktopManager) MinimizeAll() {
	dm.mu.Lock()
	defer dm.mu.Unlock()

	if dm.active {
		return // already minimized — don't overwrite the saved good state
	}

	dm.saved = dm.saved[:0]
	enumTarget = &dm.saved
	pEnumWindows.Call(enumCB, 0)
	enumTarget = nil

	count := 0
	for _, sw := range dm.saved {
		if sw.placement.ShowCmd != swSHOWMINIMIZED {
			pShowWindow.Call(sw.hwnd, swMINIMIZE)
			count++
		}
	}

	dm.active = true
	mlog.Printf("[Desktop] Minimized %d windows (saved %d)\n", count, len(dm.saved))
}

// RestoreAll restores all windows from the saved snapshot to their exact positions.
// Key insight from testing: ShowWindow FIRST, then SetWindowPlacement.
func (dm *DesktopManager) RestoreAll() {
	dm.mu.Lock()
	defer dm.mu.Unlock()

	if len(dm.saved) == 0 {
		return
	}

	count := 0
	for i := len(dm.saved) - 1; i >= 0; i-- {
		sw := &dm.saved[i]

		// Check window still exists
		if valid, _, _ := pIsWindow.Call(sw.hwnd); valid == 0 {
			continue
		}

		// Determine correct restore command (preserve maximized state)
		restoreCmd := sw.placement.ShowCmd
		if restoreCmd == swSHOWMINIMIZED || restoreCmd == swMINIMIZE {
			restoreCmd = swRESTORE
		}

		// Step 1: ShowWindow FIRST to un-minimize
		pShowWindow.Call(sw.hwnd, uintptr(restoreCmd))

		// Step 2: SetWindowPlacement to restore exact position
		wp := sw.placement
		wp.Length = uint32(unsafe.Sizeof(wp))
		wp.ShowCmd = restoreCmd
		pSetWindowPlacement.Call(sw.hwnd, uintptr(unsafe.Pointer(&wp)))
		count++
	}

	// DON'T clear saved — keep the snapshot so repeated restore_all (from continuous
	// gesture) re-applies the same placements harmlessly. The saved list is only
	// cleared when a NEW minimize_all creates a fresh snapshot.
	dm.active = false
	mlog.Printf("[Desktop] Restored %d windows\n", count)
}

// IsActive returns true if there's a pending minimized snapshot.
func (dm *DesktopManager) IsActive() bool {
	dm.mu.Lock()
	defer dm.mu.Unlock()
	return dm.active
}
