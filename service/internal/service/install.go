package service

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// Install registers the service with Windows SCM.
// Must be run with admin privileges.
func Install() error {
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("cannot determine executable path: %w", err)
	}
	exePath, _ = filepath.Abs(exePath)

	// sc create requires: binPath= "C:\path\to\exe.exe"
	// The space after = is mandatory in sc syntax.
	cmd := exec.Command("sc", "create", ServiceName,
		fmt.Sprintf("binPath= \"%s\"", exePath),
		"start= auto",
		fmt.Sprintf("DisplayName= %s HID++ Service", ServiceName),
	)
	out, err := cmd.CombinedOutput()
	if err != nil {
		outStr := strings.TrimSpace(string(out))
		if strings.Contains(outStr, "1073") {
			// ERROR_SERVICE_EXISTS — already installed, just update the path
			fmt.Println("[INSTALL] Service already exists — updating path")
			exec.Command("sc", "config", ServiceName,
				fmt.Sprintf("binPath= \"%s\"", exePath)).Run()
		} else {
			return fmt.Errorf("sc create failed: %w\n%s", err, outStr)
		}
	} else {
		fmt.Printf("[INSTALL] Service created: %s\n", exePath)
	}

	// Set description
	exec.Command("sc", "description", ServiceName,
		"Manages Logitech MX Master mouse HID++ communication for MasterMice").Run()

	// Set recovery policy: restart after 5s, 10s, 30s; reset counter after 24h
	exec.Command("sc", "failure", ServiceName,
		"reset= 86400",
		"actions= restart/5000/restart/10000/restart/30000").Run()
	fmt.Println("[INSTALL] Recovery policy set (restart on failure)")

	// Start the service immediately
	startCmd := exec.Command("sc", "start", ServiceName)
	startOut, startErr := startCmd.CombinedOutput()
	if startErr != nil {
		fmt.Printf("[INSTALL] Service start: %s\n", strings.TrimSpace(string(startOut)))
	} else {
		fmt.Println("[INSTALL] Service started")
	}

	return nil
}

// Uninstall stops and removes the service from Windows SCM.
// Must be run with admin privileges.
func Uninstall() error {
	// Stop first (ignore errors — may not be running)
	stopCmd := exec.Command("sc", "stop", ServiceName)
	stopCmd.Run()

	cmd := exec.Command("sc", "delete", ServiceName)
	out, err := cmd.CombinedOutput()
	if err != nil {
		outStr := strings.TrimSpace(string(out))
		if strings.Contains(outStr, "1060") {
			// ERROR_SERVICE_DOES_NOT_EXIST — already gone
			fmt.Println("[UNINSTALL] Service was not installed")
			return nil
		}
		return fmt.Errorf("sc delete failed: %w\n%s", err, outStr)
	}
	fmt.Println("[UNINSTALL] Service stopped and removed")
	return nil
}

// IsInstalled checks if the service is registered with SCM.
func IsInstalled() bool {
	cmd := exec.Command("sc", "query", ServiceName)
	err := cmd.Run()
	return err == nil
}

// StartService starts the SCM service.
func StartService() error {
	cmd := exec.Command("sc", "start", ServiceName)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("sc start: %s", strings.TrimSpace(string(out)))
	}
	return nil
}

// StopService stops the SCM service.
func StopService() error {
	cmd := exec.Command("sc", "stop", ServiceName)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("sc stop: %s", strings.TrimSpace(string(out)))
	}
	return nil
}
