// Package service implements the Windows SCM service wrapper for MasterMice.
package service

import (
	"context"
	"fmt"
	"time"

	"golang.org/x/sys/windows/svc"

	"github.com/olafnew/mastermice-svc/internal/hidpp"
	"github.com/olafnew/mastermice-svc/internal/ipc"
)

const ServiceName = "MasterMice"

// MasterMiceSvc implements svc.Handler for the Windows service control manager.
type MasterMiceSvc struct {
	ConnectFn func() (*hidpp.Device, error) // device connection function
}

// Execute is called by the Windows SCM. It runs the service until stop is requested.
func (s *MasterMiceSvc) Execute(args []string, r <-chan svc.ChangeRequest, changes chan<- svc.Status) (ssec bool, errno uint32) {
	changes <- svc.Status{State: svc.StartPending}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Connect to device
	fmt.Println("[SVC] Connecting to device...")
	device, err := s.ConnectFn()
	if err != nil {
		fmt.Printf("[SVC] Device connection failed: %v\n", err)
		// Service still starts — will retry via reconnect loop
	}

	// Start IPC server
	broadcaster := ipc.NewBroadcaster()
	var handler *ipc.Handler
	if device != nil {
		handler = ipc.NewHandler(device)
	}
	pipeServer := ipc.NewServer(handler, broadcaster)

	go func() {
		if err := pipeServer.Run(ctx); err != nil {
			fmt.Printf("[SVC] Pipe server error: %v\n", err)
		}
	}()

	// Start device reconnect/listener loop
	if device != nil {
		go deviceLoop(ctx, device, broadcaster)
	}

	// Report running
	const accepted = svc.AcceptStop | svc.AcceptShutdown
	changes <- svc.Status{State: svc.Running, Accepts: accepted}
	fmt.Println("[SVC] Running")

	// Wait for stop signal
	for {
		c := <-r
		switch c.Cmd {
		case svc.Stop, svc.Shutdown:
			fmt.Println("[SVC] Stop requested")
			changes <- svc.Status{State: svc.StopPending}
			cancel()
			// Give goroutines time to clean up
			time.Sleep(500 * time.Millisecond)
			if device != nil {
				device.Transport.Close()
			}
			return
		case svc.Interrogate:
			changes <- c.CurrentStatus
		}
	}
}

// deviceLoop reads notifications from the device and broadcasts events.
func deviceLoop(ctx context.Context, device *hidpp.Device, broadcaster *ipc.Broadcaster) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		report, err := device.Transport.Read(1 * time.Second)
		if err != nil {
			continue
		}

		// Skip our own responses
		if report.SW == hidpp.MySW {
			continue
		}

		// Broadcast button events
		switch report.FeatIdx {
		case device.ReprogIdx:
			// TODO: parse button events and broadcast
		case device.BattIdx:
			// Battery event — broadcast
			if batt, err := device.ReadBattery(); err == nil {
				broadcaster.Broadcast(&ipc.Event{
					Event: "battery_update",
					Data: map[string]interface{}{
						"level":    batt.Level,
						"charging": batt.Charging,
					},
				})
			}
		}
	}
}

// RunService starts the Windows service. Called from main when running as a service.
func RunService(connectFn func() (*hidpp.Device, error)) error {
	return svc.Run(ServiceName, &MasterMiceSvc{ConnectFn: connectFn})
}

// IsWindowsService returns true if the process is running as a Windows service.
func IsWindowsService() bool {
	is, err := svc.IsWindowsService()
	if err != nil {
		return false
	}
	return is
}
