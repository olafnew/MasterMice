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
	"logioptionsplus_appbroker.exe",
	"LogiAppBroker.exe",
	"LogiPluginService.exe",
	"LogiPluginServiceExt.exe",
	"SetPoint.exe",
	"SetPointP.exe",
	"LogiMgr.exe",
}

// Logitech Windows services that hold HID handles.
var logiServices = []string{
	"LogiPluginService",
	"LogiOptionsPlusService",
	"LogiOptionsPlus",
}

// KillLogitechResult reports what was killed/stopped/disabled.
type KillLogitechResult struct {
	KilledProcesses  []string
	StoppedServices  []string
	DisabledServices []string
}

// Track original service start types so we can restore on exit
var originalServiceStates = map[string]string{}

// KillLogitechSoftware terminates Logitech processes, stops their services,
// and DISABLES them so Windows doesn't auto-restart them.
// Returns what was killed/stopped/disabled.
func KillLogitechSoftware() *KillLogitechResult {
	result := &KillLogitechResult{}

	// Kill running processes
	running := findRunningLogiProcesses()
	for _, proc := range running {
		err := exec.Command("taskkill", "/F", "/IM", proc).Run()
		if err == nil {
			result.KilledProcesses = append(result.KilledProcesses, proc)
			fmt.Printf("[LOGI] Killed process: %s\n", proc)
		}
	}

	// Stop AND disable services so they don't auto-restart
	for _, svc := range logiServices {
		// Save original start type before disabling
		saveOriginalStartType(svc)

		// Stop the service
		err := exec.Command("sc", "stop", svc).Run()
		if err == nil {
			result.StoppedServices = append(result.StoppedServices, svc)
			fmt.Printf("[LOGI] Stopped service: %s\n", svc)
		}

		// Disable the service (prevents auto-restart by Windows SCM)
		err = exec.Command("sc", "config", svc, "start=", "disabled").Run()
		if err == nil {
			result.DisabledServices = append(result.DisabledServices, svc)
			fmt.Printf("[LOGI] Disabled service: %s\n", svc)
		}
	}

	// Kill again after a short delay — services may have spawned child processes
	// before being disabled
	if len(result.StoppedServices) > 0 {
		running2 := findRunningLogiProcesses()
		for _, proc := range running2 {
			exec.Command("taskkill", "/F", "/IM", proc).Run()
			fmt.Printf("[LOGI] Killed (retry): %s\n", proc)
		}
	}

	return result
}

// RestoreLogitechServices restores Logitech services to their original start
// type (before we disabled them). Called on service shutdown or crash cleanup.
func RestoreLogitechServices() {
	if len(originalServiceStates) == 0 {
		return
	}
	for svc, startType := range originalServiceStates {
		err := exec.Command("sc", "config", svc, "start=", startType).Run()
		if err == nil {
			fmt.Printf("[LOGI] Restored service %s to start=%s\n", svc, startType)
		}
	}
	originalServiceStates = map[string]string{}
}

// saveOriginalStartType queries and caches a service's current start type.
func saveOriginalStartType(svcName string) {
	if _, exists := originalServiceStates[svcName]; exists {
		return // already saved
	}
	out, err := exec.Command("sc", "qc", svcName).Output()
	if err != nil {
		return
	}
	// Parse "START_TYPE" from sc qc output
	lines := strings.Split(string(out), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if strings.Contains(line, "START_TYPE") {
			// e.g. "START_TYPE         : 2  AUTO_START"
			if strings.Contains(line, "AUTO_START") {
				originalServiceStates[svcName] = "auto"
			} else if strings.Contains(line, "DEMAND_START") {
				originalServiceStates[svcName] = "demand"
			} else if strings.Contains(line, "DISABLED") {
				originalServiceStates[svcName] = "disabled"
			} else {
				originalServiceStates[svcName] = "auto" // safe default
			}
			fmt.Printf("[LOGI] Saved %s original start type: %s\n",
				svcName, originalServiceStates[svcName])
			return
		}
	}
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
