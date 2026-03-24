// haptic-test — Standalone haptic motor test for MX Master 4.
// Finds the SHORT HID handle (Usage=0x0001), sends haptic commands
// via HidD_SetOutputReport, and reports results.
package main

import (
	"fmt"
	"os"
	"time"
	"unsafe"

	"github.com/sstallion/go-hid"
	"golang.org/x/sys/windows"
)

const (
	logiVID = 0x046D
	devIdx  = 0x02 // MX4 on Bolt at index 2
	hapIdx  = 0x0B // Haptic feature index
)

var (
	hidDLL              = windows.MustLoadDLL("hid.dll")
	hidD_SetOutputReport = hidDLL.MustFindProc("HidD_SetOutputReport")
)

func sendShort(handle windows.Handle, report [7]byte) bool {
	hex := fmt.Sprintf("%02X %02X %02X %02X %02X %02X %02X",
		report[0], report[1], report[2], report[3], report[4], report[5], report[6])
	ret, _, _ := hidD_SetOutputReport.Call(
		uintptr(handle),
		uintptr(unsafe.Pointer(&report[0])),
		7,
	)
	ok := ret != 0
	if ok {
		fmt.Printf("  [%s] OK\n", hex)
	} else {
		fmt.Printf("  [%s] FAILED\n", hex)
	}
	return ok
}

func main() {
	fmt.Println("============================================================")
	fmt.Println("  MasterMice Haptic Motor Test")
	fmt.Println("  Finds SHORT handle + sends HidD_SetOutputReport commands")
	fmt.Println("============================================================")
	fmt.Println()

	// Find SHORT interface (Usage=0x0001)
	fmt.Println("[ENUM] Scanning for Logitech HID interfaces...")
	var shortPath string
	var shortPID uint16

	hid.Enumerate(logiVID, 0, func(info *hid.DeviceInfo) error {
		if info.UsagePage == 0xFF00 {
			fmt.Printf("  PID=0x%04X usage=0x%04X path=%s\n",
				info.ProductID, info.Usage, info.Path[:min(80, len(info.Path))])
			if info.Usage == 0x0001 && shortPath == "" {
				shortPath = info.Path
				shortPID = info.ProductID
			}
		}
		return nil
	})

	if shortPath == "" {
		fmt.Println("\n[ERROR] SHORT interface (Usage=0x0001) not found.")
		fmt.Println("Is the Bolt receiver plugged in?")
		fmt.Print("Press Enter to exit...")
		fmt.Scanln()
		os.Exit(1)
	}

	fmt.Printf("\n[OK] SHORT interface: PID=0x%04X\n", shortPID)

	// Open via CreateFileW
	pathW, _ := windows.UTF16PtrFromString(shortPath)
	handle, err := windows.CreateFile(
		pathW,
		windows.GENERIC_READ|windows.GENERIC_WRITE,
		windows.FILE_SHARE_READ|windows.FILE_SHARE_WRITE,
		nil,
		windows.OPEN_EXISTING,
		0,
		0,
	)
	if err != nil {
		fmt.Printf("[ERROR] CreateFile failed: %v\n", err)
		fmt.Print("Press Enter to exit...")
		fmt.Scanln()
		os.Exit(1)
	}
	defer windows.CloseHandle(handle)
	fmt.Println("[OK] SHORT handle opened")

	fmt.Println()
	fmt.Println("============================================================")
	fmt.Println("  HAPTIC TEST — Hold mouse lightly, you should feel pulses!")
	fmt.Println("============================================================")
	fmt.Println()
	fmt.Println("Starting in 2 seconds...")
	time.Sleep(2 * time.Second)

	// Test 1: Enable haptics at 100%
	fmt.Println("\n[1/8] Enable haptics at 100% intensity")
	fmt.Println("  Format: [0x10, devIdx, hapIdx, func=0x2A, mode, intensity, 0x00]")
	sendShort(handle, [7]byte{0x10, devIdx, hapIdx, 0x2A, 0x01, 0x64, 0x00})
	time.Sleep(1 * time.Second)

	// Test 2: TICK pulse
	fmt.Println("\n[2/8] TICK pulse (0x04)")
	fmt.Println("  Format: [0x10, devIdx, hapIdx, func=0x4A, pulseType, 0x00, 0x00]")
	sendShort(handle, [7]byte{0x10, devIdx, hapIdx, 0x4A, 0x04, 0x00, 0x00})
	time.Sleep(1500 * time.Millisecond)

	// Test 3: STRONG pulse
	fmt.Println("\n[3/8] STRONG pulse (0x08)")
	sendShort(handle, [7]byte{0x10, devIdx, hapIdx, 0x4A, 0x08, 0x00, 0x00})
	time.Sleep(1500 * time.Millisecond)

	// Test 4: LIGHT pulse
	fmt.Println("\n[4/8] LIGHT pulse (0x02)")
	sendShort(handle, [7]byte{0x10, devIdx, hapIdx, 0x4A, 0x02, 0x00, 0x00})
	time.Sleep(1500 * time.Millisecond)

	// Test 5: Triple tick
	fmt.Println("\n[5/8] Triple tick")
	for i := 0; i < 3; i++ {
		sendShort(handle, [7]byte{0x10, devIdx, hapIdx, 0x4A, 0x04, 0x00, 0x00})
		time.Sleep(300 * time.Millisecond)
	}
	time.Sleep(1 * time.Second)

	// Test 6-8: Intensity sweep
	intensities := []struct {
		val  byte
		name string
		step int
	}{
		{0x19, "25% Subtle", 6},
		{0x3C, "60% Medium", 7},
		{0x64, "100% Full", 8},
	}
	for _, t := range intensities {
		fmt.Printf("\n[%d/8] Intensity: %s + STRONG pulse\n", t.step, t.name)
		sendShort(handle, [7]byte{0x10, devIdx, hapIdx, 0x2A, 0x01, t.val, 0x00})
		time.Sleep(300 * time.Millisecond)
		sendShort(handle, [7]byte{0x10, devIdx, hapIdx, 0x4A, 0x08, 0x00, 0x00})
		time.Sleep(1500 * time.Millisecond)
	}

	// Disable
	fmt.Println("\n[CLEANUP] Disabling haptics")
	sendShort(handle, [7]byte{0x10, devIdx, hapIdx, 0x2A, 0x00, 0x64, 0x00})

	fmt.Println()
	fmt.Println("============================================================")
	fmt.Println("  TEST COMPLETE")
	fmt.Println("  Did you feel vibrations during steps 2-8?")
	fmt.Println()
	fmt.Println("  Protocol summary:")
	fmt.Println("    Enable:  [0x10, 0x02, 0x0B, 0x2A, 0x01, intensity, 0x00]")
	fmt.Println("    Disable: [0x10, 0x02, 0x0B, 0x2A, 0x00, intensity, 0x00]")
	fmt.Println("    Pulse:   [0x10, 0x02, 0x0B, 0x4A, type, 0x00, 0x00]")
	fmt.Println("      type: 0x02=light, 0x04=tick, 0x08=strong")
	fmt.Println("============================================================")

	fmt.Print("\nPress Enter to exit...")
	fmt.Scanln()
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
