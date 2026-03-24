// Package appdetect detects the foreground application on Windows.
// Used by the agent to report app changes to the service for profile switching.
package appdetect

import (
	"fmt"
	"path/filepath"
	"strings"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	user32   = windows.NewLazySystemDLL("user32.dll")
	kernel32 = windows.NewLazySystemDLL("kernel32.dll")

	pGetForegroundWindow       = user32.NewProc("GetForegroundWindow")
	pGetWindowThreadProcessId  = user32.NewProc("GetWindowThreadProcessId")
	pGetClassNameW             = user32.NewProc("GetClassNameW")
	pGetWindowTextW            = user32.NewProc("GetWindowTextW")
	pFindWindowExW             = user32.NewProc("FindWindowExW")

	pOpenProcess                  = kernel32.NewProc("OpenProcess")
	pCloseHandle                  = kernel32.NewProc("CloseHandle")
	pQueryFullProcessImageNameW   = kernel32.NewProc("QueryFullProcessImageNameW")
)

const (
	PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
)

// Detector polls the foreground window and calls OnChange when the exe changes.
type Detector struct {
	OnChange func(exe string)
	Interval time.Duration

	lastExe string
	stopCh  chan struct{}
}

// NewDetector creates a foreground app detector.
func NewDetector(onChange func(exe string)) *Detector {
	return &Detector{
		OnChange: onChange,
		Interval: 300 * time.Millisecond,
		stopCh:   make(chan struct{}),
	}
}

// Start begins polling. Non-blocking.
func (d *Detector) Start() {
	go d.poll()
}

// Stop stops polling.
func (d *Detector) Stop() {
	close(d.stopCh)
}

func (d *Detector) poll() {
	ticker := time.NewTicker(d.Interval)
	defer ticker.Stop()

	for {
		select {
		case <-d.stopCh:
			return
		case <-ticker.C:
			exe := GetForegroundExe()
			if exe == "" || exe == d.lastExe {
				continue
			}
			d.lastExe = exe
			if d.OnChange != nil {
				d.OnChange(exe)
			}
		}
	}
}

// GetForegroundExe returns the exe filename of the foreground window's process.
func GetForegroundExe() string {
	hwnd, _, _ := pGetForegroundWindow.Call()
	if hwnd == 0 {
		return ""
	}

	var pid uint32
	pGetWindowThreadProcessId.Call(hwnd, uintptr(unsafe.Pointer(&pid)))
	if pid == 0 {
		return ""
	}

	exe := exeFromPID(pid)
	if exe == "" {
		return ""
	}

	exeLower := strings.ToLower(exe)

	// UWP resolution: ApplicationFrameHost.exe → find real child app
	if exeLower == "applicationframehost.exe" {
		child := resolveUWPChild(hwnd)
		if child != "" {
			return child
		}
		return "" // keep last profile
	}

	// Explorer noise filter
	if exeLower == "explorer.exe" {
		cls := getWindowClass(hwnd)
		if isNoisyExplorerClass(cls) {
			return "" // keep last profile
		}
	}

	return exe
}

func exeFromPID(pid uint32) string {
	h, _, _ := pOpenProcess.Call(PROCESS_QUERY_LIMITED_INFORMATION, 0, uintptr(pid))
	if h == 0 {
		return ""
	}
	defer pCloseHandle.Call(h)

	buf := make([]uint16, 260)
	size := uint32(260)
	ret, _, _ := pQueryFullProcessImageNameW.Call(h, 0, uintptr(unsafe.Pointer(&buf[0])), uintptr(unsafe.Pointer(&size)))
	if ret == 0 {
		return ""
	}
	fullPath := windows.UTF16ToString(buf[:size])
	return filepath.Base(fullPath)
}

func getWindowClass(hwnd uintptr) string {
	buf := make([]uint16, 256)
	n, _, _ := pGetClassNameW.Call(hwnd, uintptr(unsafe.Pointer(&buf[0])), 256)
	if n == 0 {
		return ""
	}
	return windows.UTF16ToString(buf[:n])
}

func resolveUWPChild(parentHwnd uintptr) string {
	// Find first child window with a different PID
	var parentPID uint32
	pGetWindowThreadProcessId.Call(parentHwnd, uintptr(unsafe.Pointer(&parentPID)))

	child, _, _ := pFindWindowExW.Call(parentHwnd, 0, 0, 0)
	for child != 0 {
		var childPID uint32
		pGetWindowThreadProcessId.Call(child, uintptr(unsafe.Pointer(&childPID)))
		if childPID != 0 && childPID != parentPID {
			exe := exeFromPID(childPID)
			if exe != "" {
				return exe
			}
		}
		child, _, _ = pFindWindowExW.Call(parentHwnd, child, 0, 0)
	}
	return ""
}

// Noisy explorer window classes that should be ignored (not real app switches).
var noisyClasses = map[string]bool{
	"OperationStatusWindow":                    true,
	"TopLevelWindowForOverflowXamlIsland":      true,
	"ForegroundStaging":                        true,
	"ProxyModalWindow":                         true,
	"ApplicationManager_DesktopShellWindow":     true,
}

// Real explorer classes (file explorer, taskbar, etc.)
var explorerClasses = map[string]bool{
	"CabinetWClass":     true,
	"Shell_TrayWnd":     true,
	"Shell_SecondaryTrayWnd": true,
	"Progman":           true,
	"WorkerW":           true,
}

func isNoisyExplorerClass(cls string) bool {
	if noisyClasses[cls] {
		return true
	}
	if explorerClasses[cls] {
		return false
	}
	// Unknown explorer class — suppress to avoid noise
	_ = fmt.Sprintf("[AppDetect] Unknown explorer class: %s", cls)
	return true
}
