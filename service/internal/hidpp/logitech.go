package hidpp

import (
	"fmt"
	"os/exec"
	"strings"
)

// Logitech process names that block HID++ access.
var logiProcesses = []string{
	"logioptionsplus_agent.exe",
	"logioptionsplus_updater.exe",
	"LogiAppBroker.exe",
	"SetPoint.exe",
	"SetPointP.exe",
	"LogiMgr.exe",
}

// Logitech Windows services that hold HID handles.
var logiServices = []string{
	"LogiPluginService",
	"LogiOptionsPlusService",
}

// KillLogitechResult reports what was killed/stopped.
type KillLogitechResult struct {
	KilledProcesses []string
	StoppedServices []string
}

// KillLogitechSoftware terminates Logitech processes and stops their services
// to free HID++ device access. Returns what was killed.
func KillLogitechSoftware() *KillLogitechResult {
	result := &KillLogitechResult{}

	// Check running processes via tasklist
	running := findRunningLogiProcesses()

	// Kill each found process
	for _, proc := range running {
		err := exec.Command("taskkill", "/F", "/IM", proc).Run()
		if err == nil {
			result.KilledProcesses = append(result.KilledProcesses, proc)
			fmt.Printf("[LOGI] Killed process: %s\n", proc)
		}
	}

	// Stop services
	for _, svc := range logiServices {
		err := exec.Command("sc", "stop", svc).Run()
		if err == nil {
			result.StoppedServices = append(result.StoppedServices, svc)
			fmt.Printf("[LOGI] Stopped service: %s\n", svc)
		}
	}

	return result
}

// CheckLogitechSoftware returns a list of running Logitech process names
// without killing them.
func CheckLogitechSoftware() []string {
	return findRunningLogiProcesses()
}

func findRunningLogiProcesses() []string {
	out, err := exec.Command("tasklist", "/FO", "CSV", "/NH").Output()
	if err != nil {
		return nil
	}

	outLower := strings.ToLower(string(out))
	var found []string
	for _, proc := range logiProcesses {
		if strings.Contains(outLower, strings.ToLower(proc)) {
			found = append(found, proc)
		}
	}
	return found
}
