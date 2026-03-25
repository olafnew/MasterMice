// mastermice-svc — MasterMice HID++ service.
//
// In console mode (not running as a Windows service), it connects to
// the first Logitech HID++ device and provides an interactive console.
package main

import (
	"bufio"
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/sstallion/go-hid"
	hidpp "github.com/olafnew/mastermice-svc/internal/hidpp"
	"github.com/olafnew/mastermice-svc/internal/ipc"
	msvc "github.com/olafnew/mastermice-svc/internal/service"
)

const version = "0.6.0"

func main() {
	// Handle service management commands (require admin)
	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "install", "--install":
			fmt.Printf("[mastermice-svc] v%s — installing service\n", version)
			if err := msvc.Install(); err != nil {
				fmt.Printf("[ERROR] %v\n", err)
				os.Exit(1)
			}
			fmt.Println("[OK] Service installed and started")
			os.Exit(0)

		case "uninstall", "remove", "--uninstall", "--remove":
			fmt.Printf("[mastermice-svc] v%s — uninstalling service\n", version)
			if err := msvc.Uninstall(); err != nil {
				fmt.Printf("[ERROR] %v\n", err)
				os.Exit(1)
			}
			fmt.Println("[OK] Service removed")
			os.Exit(0)

		case "start", "--start":
			if err := msvc.StartService(); err != nil {
				fmt.Printf("[ERROR] %v\n", err)
				os.Exit(1)
			}
			fmt.Println("[OK] Service started")
			os.Exit(0)

		case "stop", "--stop":
			if err := msvc.StopService(); err != nil {
				fmt.Printf("[ERROR] %v\n", err)
				os.Exit(1)
			}
			fmt.Println("[OK] Service stopped")
			os.Exit(0)

		case "status", "--status":
			if msvc.IsInstalled() {
				fmt.Println("installed")
			} else {
				fmt.Println("not-installed")
			}
			os.Exit(0)

		case "debug", "--debug":
			hidpp.Debug = true

		case "version", "--version":
			fmt.Printf("mastermice-svc v%s\n", version)
			os.Exit(0)
		}
	}

	// Kill old service + agent instances (except ourselves) BEFORE touching HID
	hidpp.KillOldMasterMiceByName("mastermice-svc.exe")
	hidpp.KillOldMasterMiceByName("mastermice-agent.exe")

	if err := hid.Init(); err != nil {
		log.Fatalf("[ERROR] hidapi init failed: %v", err)
	}
	defer hid.Exit()

	// Windows service mode (launched by SCM)
	if msvc.IsWindowsService() {
		if err := msvc.RunService(fullConnect, version); err != nil {
			log.Fatalf("[SVC] %v", err)
		}
		return
	}

	// Console mode (launched directly or by the app)
	fmt.Printf("[mastermice-svc] v%s — console mode\n", version)
	runConsole()
}

// fullConnect kills Logitech software and connects to a device.
func fullConnect() (*hidpp.Device, error) {
	running := hidpp.CheckLogitechSoftware()
	if len(running) > 0 {
		fmt.Printf("[LOGI] Detected: %s\n", strings.Join(running, ", "))
		result := hidpp.KillLogitechSoftware()
		if len(result.KilledProcesses) > 0 || len(result.StoppedServices) > 0 {
			fmt.Println("[LOGI] Waiting for handles to release...")
			time.Sleep(1 * time.Second)
		}
	} else {
		fmt.Println("[LOGI] No conflicting Logitech software detected")
	}
	return connectDevice()
}

// runConsole runs the interactive console mode with IPC server.
func runConsole() {
	device, err := fullConnect()
	if err != nil {
		log.Fatalf("[ERROR] %v", err)
	}
	defer device.Transport.Close()
	defer hidpp.RestoreLogitechServices() // restore services on exit

	printDeviceState(device)

	// Start named pipe IPC server
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	broadcaster := ipc.NewBroadcaster()
	handler := ipc.NewHandler(device, version)
	pipeServer := ipc.NewServer(handler, broadcaster)
	eventPipe := ipc.NewEventPipe()

	go func() {
		if err := pipeServer.Run(ctx); err != nil {
			fmt.Printf("[IPC] Server error: %v\n", err)
		}
	}()
	go func() {
		if err := eventPipe.Run(ctx); err != nil {
			fmt.Printf("[EventPipe] Error: %v\n", err)
		}
	}()

	// Device notification loop (reads HID++ events, pushes to event pipe)
	go deviceNotificationLoop(ctx, device, handler, broadcaster, eventPipe)

	fmt.Println("[COMMANDS] dpi <value> | smartshift <threshold> | hires on|off | smooth on|off | battery | status | quit")

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt)

	scanner := bufio.NewScanner(os.Stdin)
	inputCh := make(chan string, 1)
	go func() {
		for scanner.Scan() {
			inputCh <- scanner.Text()
		}
	}()

	for {
		fmt.Print("> ")
		select {
		case <-sig:
			fmt.Println("\n[INFO] Shutting down")
			return
		case line := <-inputCh:
			if handleCommand(device, strings.TrimSpace(line)) {
				return
			}
		}
	}
}

func handleCommand(d *hidpp.Device, line string) bool {
	parts := strings.Fields(line)
	if len(parts) == 0 {
		return false
	}

	cmd := strings.ToLower(parts[0])
	switch cmd {
	case "quit", "exit", "q":
		fmt.Println("[INFO] Shutting down")
		return true

	case "dpi":
		if len(parts) < 2 {
			fmt.Println("Usage: dpi <value>  (200-8000)")
			return false
		}
		val, err := strconv.Atoi(parts[1])
		if err != nil {
			fmt.Printf("Invalid DPI: %v\n", err)
			return false
		}
		if err := d.SetDPI(val); err != nil {
			fmt.Printf("[ERROR] %v\n", err)
		}

	case "smartshift", "ss":
		if len(parts) < 2 {
			fmt.Println("Usage: smartshift <threshold 1-50> | smartshift off")
			return false
		}
		if parts[1] == "off" {
			if err := d.SetSmartShift(10, 50, false); err != nil {
				fmt.Printf("[ERROR] %v\n", err)
			} else {
				fmt.Println("[SMARTSHIFT] Disabled (free-spin)")
			}
		} else {
			val, err := strconv.Atoi(parts[1])
			if err != nil {
				fmt.Printf("Invalid threshold: %v\n", err)
				return false
			}
			if err := d.SetSmartShift(val, 50, true); err != nil {
				fmt.Printf("[ERROR] %v\n", err)
			} else {
				fmt.Printf("[SMARTSHIFT] Set threshold to %d\n", val)
			}
		}

	case "hires", "hr":
		if len(parts) < 2 {
			fmt.Println("Usage: hires on|off")
			return false
		}
		on := parts[1] == "on" || parts[1] == "1" || parts[1] == "true"
		if err := d.SetHiResWheel(&on, nil); err != nil {
			fmt.Printf("[ERROR] %v\n", err)
		} else {
			fmt.Printf("[HIRES] Set to %v\n", on)
		}

	case "smooth", "sm":
		if len(parts) < 2 {
			fmt.Println("Usage: smooth on|off")
			return false
		}
		on := parts[1] == "on" || parts[1] == "1" || parts[1] == "true"
		if err := d.SetSmoothScroll(on); err != nil {
			fmt.Printf("[ERROR] %v\n", err)
		} else {
			fmt.Printf("[SMOOTH] Set to %v\n", on)
		}

	case "battery", "batt":
		batt, err := d.ReadBattery()
		if err != nil {
			fmt.Printf("[ERROR] %v\n", err)
		} else {
			fmt.Printf("[BATTERY] %d%%, charging=%v\n", batt.Level, batt.Charging)
		}

	case "status", "st":
		printDeviceState(d)

	default:
		fmt.Println("[COMMANDS] dpi <value> | smartshift <threshold>|off | hires on|off | smooth on|off | battery | status | quit")
	}

	return false
}

func printDeviceState(d *hidpp.Device) {
	fmt.Printf("\n── %s (%s) ──\n", d.Name, d.ModelKey)
	if d.Profile != nil {
		fmt.Printf("   Max DPI: %d | SmartShift v%d | Haptics: %v\n",
			d.Profile.DPIMax, d.Profile.SmartShiftVer, d.Profile.HasHaptics)
	}

	if batt, err := d.ReadBattery(); err == nil {
		fmt.Printf("   Battery: %d%% (charging=%v)\n", batt.Level, batt.Charging)
	}
	if dpi, err := d.ReadDPI(); err == nil {
		fmt.Printf("   DPI: %d\n", dpi)
	}
	if ss, err := d.GetSmartShift(); err == nil {
		if d.SmartShiftVer == 2 {
			fmt.Printf("   SmartShift: enabled=%v threshold=%d force=%d\n",
				ss.Enabled, ss.Threshold, ss.Force)
		} else {
			fmt.Printf("   SmartShift: enabled=%v threshold=%d\n",
				ss.Enabled, ss.Threshold)
		}
	}
	if hr, err := d.GetHiResWheel(); err == nil {
		fmt.Printf("   HiRes: %v (invert=%v)\n", hr.HiRes, hr.Invert)
	}
	if sm, err := d.GetSmoothScroll(); err == nil {
		fmt.Printf("   Smooth: %v\n", sm)
	}
	fmt.Println()
}

// ── Device discovery ─────────────────────────────────────────────

type hidInfo struct {
	Path      string
	PID       uint16
	UsagePage uint16
	Usage     uint16
}

func connectDevice() (*hidpp.Device, error) {
	var allInfos []hidInfo

	err := hid.Enumerate(hidpp.LogiVID, 0, func(info *hid.DeviceInfo) error {
		allInfos = append(allInfos, hidInfo{
			Path:      info.Path,
			PID:       info.ProductID,
			UsagePage: info.UsagePage,
			Usage:     info.Usage,
		})
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("enumerate failed: %w", err)
	}
	if len(allInfos) == 0 {
		return nil, fmt.Errorf("no Logitech HID devices found")
	}
	fmt.Printf("[ENUM] Found %d Logitech HID interfaces\n", len(allInfos))

	var candidates []hidInfo
	for _, info := range allInfos {
		if info.UsagePage == 0xFFBC {
			continue
		}
		if info.UsagePage >= 0xFF00 {
			candidates = append(candidates, info)
		}
	}
	if len(candidates) == 0 {
		return nil, fmt.Errorf("no suitable HID++ interfaces found")
	}

	sort.Slice(candidates, func(i, j int) bool {
		return candidates[i].Usage == 0x0002 && candidates[j].Usage != 0x0002
	})

	for _, info := range candidates {
		fmt.Printf("[ENUM] Trying: PID=0x%04X usage=0x%04X\n", info.PID, info.Usage)

		dev, err := hid.OpenPath(info.Path)
		if err != nil {
			fmt.Printf("[ENUM]   Could not open: %v\n", err)
			continue
		}

		transport := hidpp.NewTransport(dev, hidpp.BTDevIdx)

		// Probe all indices, collect responding ones
		indices := []byte{hidpp.BTDevIdx, 1, 2, 3, 4, 5, 6}
		var alive []byte
		for _, idx := range indices {
			transport.SetDevIdx(idx)
			fmt.Printf("[ENUM]   Probing 0x%02X...", idx)
			if transport.Probe(0x00, hidpp.FeatReprogV4, 500*time.Millisecond) {
				fmt.Printf(" FOUND\n")
				alive = append(alive, idx)
			} else {
				fmt.Printf(" -\n")
			}
		}

		// Identify each responding index
		for _, idx := range alive {
			transport.SetDevIdx(idx)

			nameIdx, err := transport.RequestIRoot(hidpp.FeatDeviceName)
			if err != nil {
				continue
			}
			name := readDeviceName(transport, nameIdx)
			if name == "" {
				continue
			}

			modelKey, profile := hidpp.MatchProfile(name)
			if profile == nil {
				lower := strings.ToLower(name)
				if !strings.Contains(lower, "mouse") && !strings.Contains(lower, "master") {
					fmt.Printf("[ENUM]   Index 0x%02X: %q — not a mouse, skip\n", idx, name)
					continue
				}
			}

			fmt.Printf("[ENUM] Connected: %q at index 0x%02X\n", name, idx)

			device := &hidpp.Device{
				Transport: transport,
				DevIdx:    idx,
				ConnPID:   info.PID,
				Name:      name,
				ModelKey:  modelKey,
				Profile:   profile,
				NameIdx:   nameIdx,
			}

			fmt.Println("[DEVICE] Discovering features...")
			device.DiscoverFeatures()

			return device, nil
		}

		transport.Close()
	}

	return nil, fmt.Errorf("no Logitech mouse found")
}

func readDeviceName(t *hidpp.Transport, nameIdx byte) string {
	report, err := t.Request(nameIdx, 0, nil, 2*time.Second)
	if err != nil || len(report.Params) < 1 {
		return ""
	}
	nameLen := int(report.Params[0])

	var name strings.Builder
	for offset := 0; offset < nameLen; offset += 16 {
		report, err := t.Request(nameIdx, 1, []byte{byte(offset)}, 2*time.Second)
		if err != nil {
			break
		}
		for _, b := range report.Params {
			if b == 0 || name.Len() >= nameLen {
				break
			}
			name.WriteByte(b)
		}
	}
	return name.String()
}

// deviceNotificationLoop reads HID++ notifications and routes them to event pipe.
// Used in console mode (in service mode, deviceLoopWithReconnect handles this).
func deviceNotificationLoop(ctx context.Context, d *hidpp.Device,
	handler *ipc.Handler, broadcaster *ipc.Broadcaster, eventPipe *ipc.EventPipe) {

	readCount := 0
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		report, err := d.Transport.Read(1 * time.Second)
		if err != nil {
			readCount++
			if readCount <= 3 || readCount%30 == 0 {
				fmt.Printf("[NOTIF-DBG] Read #%d: %v\n", readCount, err)
			}
			continue
		}

		// Log ALL reports for debugging
		pLen := len(report.Params)
		if pLen > 6 {
			pLen = 6
		}
		fmt.Printf("[NOTIF] feat=0x%02X func=%d sw=0x%X params=%02X\n",
			report.FeatIdx, report.Func, report.SW, report.Params[:pLen])

		if report.SW == hidpp.MySW {
			continue
		}

		// Battery events
		if d.BattIdx != 0 && report.FeatIdx == d.BattIdx {
			if batt, err := d.ReadBattery(); err == nil {
				evtData := map[string]interface{}{
					"level":    batt.Level,
					"charging": batt.Charging,
				}
				handler.PushEvent("battery_update", evtData)
				if eventPipe != nil {
					eventPipe.Push("battery_update", evtData)
				}
			}
		}

		// REPROG_V4 notifications (from Wireshark + live testing):
		//   func=0: diverted_buttons_event — params = LIST of currently pressed CIDs
		//           [CID1_hi, CID1_lo, CID2_hi, CID2_lo, ...] (zero-padded)
		//           CID present = button pressed, CID=0x0000 = released (empty list)
		//   func=1: divertedRawXY — params=[dx_hi, dx_lo, dy_hi, dy_lo] (raw sensor)
		if d.ReprogIdx != 0 && report.FeatIdx == d.ReprogIdx {
			switch report.Func {

			case 0:
				// Diverted button event — params contain LIST of pressed CIDs
				if len(report.Params) >= 2 {
					cid := uint16(report.Params[0])<<8 | uint16(report.Params[1])

					if cid != 0 {
						// A button IS pressed (CID is in the list)
						var buttonName string
						switch cid {
						case 0x01A0:
							buttonName = "haptic_panel"
						case 0x00C3:
							buttonName = "gesture"
						}
						if buttonName != "" {
							evtData := map[string]interface{}{
								"button": buttonName,
								"state":  "down",
								"cid":    fmt.Sprintf("0x%04X", cid),
							}
							handler.PushEvent("button_event", evtData)
							if eventPipe != nil {
								eventPipe.Push("button_event", evtData)
							}
						}
					} else {
						// CID=0x0000 → all buttons released
						// Send "up" for all known diverted buttons
						for _, btn := range []string{"gesture", "haptic_panel"} {
							evtData := map[string]interface{}{
								"button": btn,
								"state":  "up",
							}
							handler.PushEvent("button_event", evtData)
							if eventPipe != nil {
								eventPipe.Push("button_event", evtData)
							}
						}
					}
				}

			case 1:
				// divertedRawXY — mouse movement while gesture button held
				// params = [dx_hi, dx_lo, dy_hi, dy_lo] (signed 16-bit big-endian)
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
