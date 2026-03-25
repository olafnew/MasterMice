package hidpp

import (
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// Logitech Options+ processes that block HID++ access on Bolt/Unifying receivers.
// Only Options+ family is killed — G HUB, SetPoint, etc. are left alone
// because they target different product lines and don't conflict.
var logiProcesses = []string{
	// Options+ (current) — these hold HID++ handles
	"logioptionsplus_agent.exe",    // PRIMARY — device communication agent
	"logioptionsplus_updater.exe",  // auto-update checker
	"logioptionsplus_appbroker.exe", // per-app profile broker
	"LogiOptionsPlus.exe",          // main UI (Electron)
	"LogiAiPromptBuilder.exe",      // AI Prompt Builder
	"LogiAppBroker.exe",            // older naming variant
	"LogiPluginService.exe",        // plugin manager (Loupedeck)
	"LogiPluginServiceExt.exe",     // extended plugin service
	// Legacy Options (also holds HID++ handles)
	"LogiOptions.exe",
	"LogiOptionsMgr.exe",
	"LogiOverlay.exe",
	"LogiMgr.exe",
	// Bolt standalone (holds receiver handle)
	"LogiBolt.exe",
}

// Logitech Windows services that hold HID handles.
var logiServices = []string{
	"LogiPluginService",
	"LogiOptionsPlusService",
	"LogiOptionsPlus",
	"LGHUBUpdaterService",
	"logi_lamparray_service",
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

	// Targeted wildcard: only kill Options+ processes (not G HUB, SetPoint, etc.)
	// A user may legitimately run G HUB for a gaming mouse alongside MasterMice
	wildcard := findWildcardLogiProcesses()
	for _, proc := range wildcard {
		lower := strings.ToLower(proc)
		if strings.Contains(lower, "mastermice") {
			continue // never kill our own
		}
		// Only kill Options+ family — they're the ones that hold HID++ handles on Bolt/Unifying
		isOptionsPlus := strings.Contains(lower, "logioptions") || strings.Contains(lower, "logiplugin")
		if !isOptionsPlus {
			continue // leave G HUB, SetPoint, etc. alone
		}
		err := exec.Command("taskkill", "/F", "/IM", proc).Run()
		if err == nil {
			result.KilledProcesses = append(result.KilledProcesses, proc)
			fmt.Printf("[LOGI] Killed (wildcard): %s\n", proc)
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

	// Check exact process names
	for _, proc := range logiProcesses {
		if strings.Contains(outLower, strings.ToLower(proc)) {
			found = append(found, proc)
		}
	}

	// Also catch any process containing "logioptions" or "logiplugin" (covers variants)
	lines := strings.Split(string(out), "\n")
	for _, line := range lines {
		lineLower := strings.ToLower(line)
		if strings.Contains(lineLower, "logioptions") || strings.Contains(lineLower, "logiplugin") {
			// Extract process name from CSV: "processname.exe","PID",...
			parts := strings.Split(strings.TrimSpace(line), ",")
			if len(parts) >= 1 {
				name := strings.Trim(parts[0], "\" ")
				if name != "" && !containsStr(found, name) {
					found = append(found, name)
				}
			}
		}
	}

	return found
}

func containsStr(list []string, s string) bool {
	sLower := strings.ToLower(s)
	for _, item := range list {
		if strings.ToLower(item) == sLower {
			return true
		}
	}
	return false
}

// findWildcardLogiProcesses returns ALL running processes whose name contains
// "logi" or "lghub" or "setpoint" — catches any Logitech process we don't
// know about by name. The caller should skip "mastermice" processes.
func findWildcardLogiProcesses() []string {
	out, err := exec.Command("tasklist", "/FO", "CSV", "/NH").Output()
	if err != nil {
		return nil
	}

	var found []string
	lines := strings.Split(string(out), "\n")
	for _, line := range lines {
		lineLower := strings.ToLower(strings.TrimSpace(line))
		if lineLower == "" {
			continue
		}
		parts := strings.Split(lineLower, ",")
		if len(parts) < 1 {
			continue
		}
		name := strings.Trim(parts[0], "\" ")
		if name == "" {
			continue
		}

		// Match any Logitech-related process
		isLogi := strings.Contains(name, "logi") ||
			strings.Contains(name, "lghub") ||
			strings.Contains(name, "setpoint") ||
			strings.Contains(name, "khalmnpr") ||
			strings.Contains(name, "lcore") ||
			strings.Contains(name, "lcdmon")

		if isLogi && !containsStr(found, name) {
			// Get the original-case name from the raw line
			origParts := strings.Split(strings.TrimSpace(line), ",")
			origName := strings.Trim(origParts[0], "\" ")
			found = append(found, origName)
		}
	}
	return found
}

// KillOldMasterMiceByName kills old instances of a SPECIFIC exe name
// (excluding the current process). The service calls this with "mastermice-svc.exe",
// the agent calls this with "mastermice-agent.exe".
// IMPORTANT: The agent must NEVER kill the service — only its own old instances.
func KillOldMasterMiceByName(targetExe string) {
	myPID := os.Getpid()

	out, err := exec.Command("tasklist", "/FI", "IMAGENAME eq "+targetExe, "/FO", "CSV", "/NH").Output()
	if err != nil {
		return
	}
	lines := strings.Split(string(out), "\n")
	for _, line := range lines {
		parts := strings.Split(strings.TrimSpace(line), ",")
		if len(parts) < 2 {
			continue
		}
		pidStr := strings.Trim(parts[1], "\" ")
		pid, err := strconv.Atoi(pidStr)
		if err != nil || pid == myPID {
			continue // skip our own process
		}
		exec.Command("taskkill", "/F", "/PID", pidStr).Run()
		fmt.Printf("[KILL] Killed old %s (PID %d)\n", targetExe, pid)
	}

	// Brief wait for handles to release
	time.Sleep(500 * time.Millisecond)
}
