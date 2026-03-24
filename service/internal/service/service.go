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
	ConnectFn func() (*hidpp.Device, error)
	Version   string
}

// Execute is called by the Windows SCM.
func (s *MasterMiceSvc) Execute(args []string, r <-chan svc.ChangeRequest, changes chan<- svc.Status) (ssec bool, errno uint32) {
	changes <- svc.Status{State: svc.StartPending}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start IPC servers
	broadcaster := ipc.NewBroadcaster()
	handler := ipc.NewHandler(nil, s.Version)
	pipeServer := ipc.NewServer(handler, broadcaster)
	eventPipe := ipc.NewEventPipe()

	go func() {
		if err := pipeServer.Run(ctx); err != nil {
			fmt.Printf("[SVC] Pipe server error: %v\n", err)
		}
	}()
	go func() {
		if err := eventPipe.Run(ctx); err != nil {
			fmt.Printf("[SVC] Event pipe error: %v\n", err)
		}
	}()

	// Start device loop with auto-reconnect
	go deviceLoopWithReconnect(ctx, s.ConnectFn, handler, broadcaster, eventPipe)

	const accepted = svc.AcceptStop | svc.AcceptShutdown
	changes <- svc.Status{State: svc.Running, Accepts: accepted}
	fmt.Println("[SVC] Running")

	for {
		c := <-r
		switch c.Cmd {
		case svc.Stop, svc.Shutdown:
			fmt.Println("[SVC] Stop requested")
			changes <- svc.Status{State: svc.StopPending}
			cancel()
			time.Sleep(500 * time.Millisecond)
			if d := handler.GetDevice(); d != nil {
				d.CloseShortHandle()
				d.Transport.Close()
			}
			return
		case svc.Interrogate:
			changes <- c.CurrentStatus
		}
	}
}

// deviceLoopWithReconnect manages device lifecycle: connect, monitor, reconnect.
func deviceLoopWithReconnect(ctx context.Context, connectFn func() (*hidpp.Device, error),
	handler *ipc.Handler, broadcaster *ipc.Broadcaster, eventPipe *ipc.EventPipe) {

	var device *hidpp.Device
	var lastBattPoll time.Time
	var lastBattEvent time.Time

	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		// Connect if no device
		if device == nil {
			fmt.Println("[SVC] Connecting to device...")
			d, err := connectFn()
			if err != nil {
				fmt.Printf("[SVC] Connection failed: %v — retrying in 5s\n", err)
				select {
				case <-ctx.Done():
					return
				case <-time.After(5 * time.Second):
				}
				continue
			}
			device = d
			handler.SetDevice(device)
			fmt.Printf("[SVC] Device connected: %s\n", device.Name)

			// Broadcast connected event
			broadcaster.Broadcast(&ipc.Event{
				Event: "device_connected",
				Data: map[string]interface{}{
					"model": device.ModelKey,
					"name":  device.Name,
				},
			})

			// Initial battery read
			if batt, err := device.ReadBattery(); err == nil {
				lastBattPoll = time.Now()
				broadcaster.Broadcast(&ipc.Event{
					Event: "battery_update",
					Data: map[string]interface{}{
						"level":    batt.Level,
						"charging": batt.Charging,
					},
				})
			}
		}

		// Read notifications (non-blocking, 1s timeout)
		report, err := device.Transport.Read(1 * time.Second)
		if err != nil {
			if err.Error() != "hidpp: request timed out" {
				// Real error — device probably disconnected
				fmt.Printf("[SVC] Device read error: %v — disconnected\n", err)
				device.CloseShortHandle()
				device.Transport.Close()
				device = nil
				handler.SetDevice(nil)

				broadcaster.Broadcast(&ipc.Event{
					Event: "device_disconnected",
					Data:  map[string]interface{}{},
				})

				fmt.Println("[SVC] Will retry connection in 5s...")
				select {
				case <-ctx.Done():
					return
				case <-time.After(5 * time.Second):
				}
			}
			// Timeout — check if battery poll needed
			if device != nil && device.BattIdx != 0 {
				sinceLastPoll := time.Since(lastBattPoll)
				sinceLastEvent := time.Since(lastBattEvent)
				if sinceLastPoll > 5*time.Minute && sinceLastEvent > 60*time.Second {
					if batt, err := device.ReadBattery(); err == nil {
						lastBattPoll = time.Now()
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
			continue
		}

		// Skip our own responses
		if report.SW == hidpp.MySW {
			continue
		}

		// Handle battery push events
		if device.BattIdx != 0 && report.FeatIdx == device.BattIdx {
			lastBattEvent = time.Now()
			if batt, err := device.ReadBattery(); err == nil {
				evtData := map[string]interface{}{
					"level":    batt.Level,
					"charging": batt.Charging,
				}
				broadcaster.Broadcast(&ipc.Event{Event: "battery_update", Data: evtData})
				handler.PushEvent("battery_update", evtData)
				if eventPipe != nil {
					eventPipe.Push("battery_update", evtData)
				}
			}
		}

		// Handle REPROG_V4 notifications
		// Protocol (from Wireshark captures):
		//   func=0: button event notification — params=[CID_hi, CID_lo, flags, ...]
		//   func=1: divertedRawXY — params=[dx_hi, dx_lo, dy_hi, dy_lo] (NO CID prefix!)
		//   func=2: divertedButtons — params=[CID_hi, CID_lo, pressed(0/1), ...]
		//   func=3: divert config response
		if device.ReprogIdx != 0 && report.FeatIdx == device.ReprogIdx {
			switch report.Func {

			case 0, 2:
				// Button press/release events (both func=0 and func=2 carry CID + flags)
				if len(report.Params) >= 3 {
					cid := uint16(report.Params[0])<<8 | uint16(report.Params[1])
					flags := report.Params[2]
					pressed := (flags & 0x01) != 0

					var buttonName string
					switch cid {
					case 0x01A0:
						buttonName = "haptic_panel"
					case 0x00C3:
						buttonName = "gesture"
					}

					if buttonName != "" {
						state := "up"
						if pressed {
							state = "down"
						}
						evtData := map[string]interface{}{
							"button": buttonName,
							"state":  state,
							"cid":    fmt.Sprintf("0x%04X", cid),
						}
						handler.PushEvent("button_event", evtData)
						if eventPipe != nil {
							eventPipe.Push("button_event", evtData)
						}
					}
				}

			case 1:
				// divertedRawXY — raw mouse movement while gesture button held
				// Params: [dx_hi, dx_lo, dy_hi, dy_lo] (signed 16-bit big-endian)
				// NO CID prefix — the device sends raw sensor data directly
				if len(report.Params) >= 4 {
					dx := int16(uint16(report.Params[0])<<8 | uint16(report.Params[1]))
					dy := int16(uint16(report.Params[2])<<8 | uint16(report.Params[3]))
					if eventPipe != nil {
						eventPipe.Push("gesture_move", map[string]interface{}{
							"dx": int(dx),
							"dy": int(dy),
						})
					}
				}
			}
		}
	}
}

// RunService starts the Windows service.
func RunService(connectFn func() (*hidpp.Device, error), version string) error {
	return svc.Run(ServiceName, &MasterMiceSvc{ConnectFn: connectFn, Version: version})
}

// IsWindowsService returns true if the process is running as a Windows service.
func IsWindowsService() bool {
	is, err := svc.IsWindowsService()
	if err != nil {
		return false
	}
	return is
}
