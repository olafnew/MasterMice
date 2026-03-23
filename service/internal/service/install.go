package service

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

// Install registers the service with Windows SCM.
func Install() error {
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("cannot determine executable path: %w", err)
	}
	exePath, _ = filepath.Abs(exePath)

	cmd := exec.Command("sc", "create", ServiceName,
		"binPath=", exePath,
		"start=", "auto",
		"DisplayName=", "MasterMice HID++ Service",
	)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("sc create failed: %w\n%s", err, out)
	}
	fmt.Printf("[INSTALL] Service created: %s\n", exePath)

	// Set description
	exec.Command("sc", "description", ServiceName,
		"Manages Logitech MX Master mouse HID++ communication for MasterMice").Run()

	// Set recovery policy: restart after 5s, 10s, 30s
	exec.Command("sc", "failure", ServiceName,
		"reset=", "86400",
		"actions=", "restart/5000/restart/10000/restart/30000").Run()

	fmt.Println("[INSTALL] Recovery policy set (restart on failure)")
	return nil
}

// Uninstall removes the service from Windows SCM.
func Uninstall() error {
	// Stop first (ignore errors — may not be running)
	exec.Command("sc", "stop", ServiceName).Run()

	cmd := exec.Command("sc", "delete", ServiceName)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("sc delete failed: %w\n%s", err, out)
	}
	fmt.Println("[UNINSTALL] Service removed")
	return nil
}
