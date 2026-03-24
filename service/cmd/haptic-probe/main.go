// haptic-probe — Deep protocol exploration for MX Master 4 haptic motor.
// Probes all functions and pulse types to discover hidden capabilities.
package main

import (
	"bufio"
	"fmt"
	"os"
	"time"
	"unsafe"

	"github.com/sstallion/go-hid"
	"golang.org/x/sys/windows"
)

const (
	logiVID = 0x046D
	devIdx  = 0x02
	hapIdx  = 0x0B
)

var (
	hidDLL               = windows.MustLoadDLL("hid.dll")
	hidD_SetOutputReport = hidDLL.MustFindProc("HidD_SetOutputReport")
)

func sendShort(handle windows.Handle, report [7]byte) bool {
	ret, _, _ := hidD_SetOutputReport.Call(
		uintptr(handle), uintptr(unsafe.Pointer(&report[0])), 7,
	)
	return ret != 0
}

func sendShortVerbose(handle windows.Handle, report [7]byte, desc string) bool {
	hex := fmt.Sprintf("%02X %02X %02X %02X %02X %02X %02X",
		report[0], report[1], report[2], report[3], report[4], report[5], report[6])
	ok := sendShort(handle, report)
	status := "OK"
	if !ok {
		status = "FAIL"
	}
	fmt.Printf("  [%s] %s  — %s\n", hex, status, desc)
	return ok
}

func waitAndAsk(prompt string) string {
	fmt.Printf("\n  >>> %s (enter to continue, or describe what you felt): ", prompt)
	scanner := bufio.NewScanner(os.Stdin)
	scanner.Scan()
	return scanner.Text()
}

func main() {
	fmt.Println("================================================================")
	fmt.Println("  MasterMice Haptic Protocol Deep Probe")
	fmt.Println("  Exploring ALL functions and pulse types on feature 0x19B0")
	fmt.Println("================================================================\n")

	// Find SHORT handle
	var shortPath string
	hid.Enumerate(logiVID, 0, func(info *hid.DeviceInfo) error {
		if info.UsagePage == 0xFF00 && info.Usage == 0x0001 && shortPath == "" {
			shortPath = info.Path
			fmt.Printf("[ENUM] SHORT: PID=0x%04X path=%s\n", info.ProductID, info.Path[:min(80, len(info.Path))])
		}
		return nil
	})
	if shortPath == "" {
		fmt.Println("[ERROR] SHORT interface not found")
		os.Exit(1)
	}

	pathW, _ := windows.UTF16PtrFromString(shortPath)
	handle, err := windows.CreateFile(pathW,
		windows.GENERIC_READ|windows.GENERIC_WRITE,
		windows.FILE_SHARE_READ|windows.FILE_SHARE_WRITE,
		nil, windows.OPEN_EXISTING, 0, 0)
	if err != nil {
		fmt.Printf("[ERROR] CreateFile: %v\n", err)
		os.Exit(1)
	}
	defer windows.CloseHandle(handle)
	fmt.Println("[OK] SHORT handle opened\n")

	// ═══════════════════════════════════════════════════════════════
	// PHASE 1: Probe all functions (func 0-7)
	// ═══════════════════════════════════════════════════════════════
	fmt.Println("════════════════════════════════════════════════════════════")
	fmt.Println("  PHASE 1: Probe all functions (0-7)")
	fmt.Println("  Sending [0x10, dev, 0x0B, funcSW, 0x00, 0x00, 0x00]")
	fmt.Println("  funcSW = (func << 4) | 0x0A (sw=0x0A)")
	fmt.Println("════════════════════════════════════════════════════════════\n")

	for fn := 0; fn <= 7; fn++ {
		funcSW := byte((fn << 4) | 0x0A)
		desc := fmt.Sprintf("func=%d (byte3=0x%02X)", fn, funcSW)
		sendShortVerbose(handle, [7]byte{0x10, devIdx, hapIdx, funcSW, 0x00, 0x00, 0x00}, desc)
		time.Sleep(200 * time.Millisecond)
	}

	// ═══════════════════════════════════════════════════════════════
	// PHASE 2: Read capabilities (func=0)
	// ═══════════════════════════════════════════════════════════════
	fmt.Println("\n════════════════════════════════════════════════════════════")
	fmt.Println("  PHASE 2: Probe func=0 (getCapabilities?) with params")
	fmt.Println("════════════════════════════════════════════════════════════\n")

	for p := byte(0); p <= 5; p++ {
		desc := fmt.Sprintf("func=0 param[0]=0x%02X", p)
		sendShortVerbose(handle, [7]byte{0x10, devIdx, hapIdx, 0x0A, p, 0x00, 0x00}, desc)
		time.Sleep(200 * time.Millisecond)
	}

	// ═══════════════════════════════════════════════════════════════
	// PHASE 3: Read config (func=1)
	// ═══════════════════════════════════════════════════════════════
	fmt.Println("\n════════════════════════════════════════════════════════════")
	fmt.Println("  PHASE 3: Probe func=1 (getConfig?) with params")
	fmt.Println("════════════════════════════════════════════════════════════\n")

	for p := byte(0); p <= 3; p++ {
		desc := fmt.Sprintf("func=1 param[0]=0x%02X", p)
		sendShortVerbose(handle, [7]byte{0x10, devIdx, hapIdx, 0x1A, p, 0x00, 0x00}, desc)
		time.Sleep(200 * time.Millisecond)
	}

	// ═══════════════════════════════════════════════════════════════
	// PHASE 4: Enable haptics for pulse testing
	// ═══════════════════════════════════════════════════════════════
	fmt.Println("\n════════════════════════════════════════════════════════════")
	fmt.Println("  PHASE 4: Enable at 100% + probe ALL single-bit pulse types")
	fmt.Println("  Hold mouse lightly!")
	fmt.Println("════════════════════════════════════════════════════════════\n")

	time.Sleep(2 * time.Second)
	sendShortVerbose(handle, [7]byte{0x10, devIdx, hapIdx, 0x2A, 0x01, 0x64, 0x00}, "Enable 100%")
	time.Sleep(500 * time.Millisecond)

	// Test all single-bit pulse values
	pulseNames := map[byte]string{
		0x01: "bit0 (0x01) — unknown",
		0x02: "bit1 (0x02) — known: LIGHT",
		0x04: "bit2 (0x04) — known: TICK",
		0x08: "bit3 (0x08) — known: STRONG",
		0x10: "bit4 (0x10) — unknown",
		0x20: "bit5 (0x20) — unknown",
		0x40: "bit6 (0x40) — unknown",
		0x80: "bit7 (0x80) — unknown",
	}

	for _, bit := range []byte{0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80} {
		desc := pulseNames[bit]
		sendShortVerbose(handle, [7]byte{0x10, devIdx, hapIdx, 0x4A, bit, 0x00, 0x00}, desc)
		waitAndAsk(fmt.Sprintf("Pulse 0x%02X — feel anything?", bit))
	}

	// ═══════════════════════════════════════════════════════════════
	// PHASE 5: Combo pulse types
	// ═══════════════════════════════════════════════════════════════
	fmt.Println("\n════════════════════════════════════════════════════════════")
	fmt.Println("  PHASE 5: Combo pulse types (bit combinations)")
	fmt.Println("════════════════════════════════════════════════════════════\n")

	combos := []struct {
		val  byte
		desc string
	}{
		{0x06, "light+tick (0x02|0x04)"},
		{0x0A, "light+strong (0x02|0x08)"},
		{0x0C, "tick+strong (0x04|0x08)"},
		{0x0E, "light+tick+strong (0x02|0x04|0x08)"},
		{0x00, "reset/arm (0x00)"},
	}

	for _, c := range combos {
		sendShortVerbose(handle, [7]byte{0x10, devIdx, hapIdx, 0x4A, c.val, 0x00, 0x00}, c.desc)
		waitAndAsk(fmt.Sprintf("Pulse 0x%02X — feel anything?", c.val))
	}

	// ═══════════════════════════════════════════════════════════════
	// PHASE 6: Explore the "unused" bytes in pulse command
	// ═══════════════════════════════════════════════════════════════
	fmt.Println("\n════════════════════════════════════════════════════════════")
	fmt.Println("  PHASE 6: Explore bytes 5-6 in pulse command (maybe duration/repeat?)")
	fmt.Println("  Using TICK (0x04) as base pulse")
	fmt.Println("════════════════════════════════════════════════════════════\n")

	// Byte 5 variations
	for _, b5 := range []byte{0x01, 0x02, 0x05, 0x0A, 0x10, 0x20, 0x50, 0xFF} {
		desc := fmt.Sprintf("tick + byte5=0x%02X", b5)
		sendShortVerbose(handle, [7]byte{0x10, devIdx, hapIdx, 0x4A, 0x04, b5, 0x00}, desc)
		waitAndAsk(fmt.Sprintf("Byte5=0x%02X — different from normal tick?", b5))
	}

	// Byte 6 variations
	fmt.Println()
	for _, b6 := range []byte{0x01, 0x02, 0x05, 0x0A, 0x10, 0x50, 0xFF} {
		desc := fmt.Sprintf("tick + byte6=0x%02X", b6)
		sendShortVerbose(handle, [7]byte{0x10, devIdx, hapIdx, 0x4A, 0x04, 0x00, b6}, desc)
		waitAndAsk(fmt.Sprintf("Byte6=0x%02X — different from normal tick?", b6))
	}

	// ═══════════════════════════════════════════════════════════════
	// PHASE 7: Func=3 exploration (unknown function)
	// ═══════════════════════════════════════════════════════════════
	fmt.Println("\n════════════════════════════════════════════════════════════")
	fmt.Println("  PHASE 7: Probe func=3 (0x3A) — unknown function")
	fmt.Println("════════════════════════════════════════════════════════════\n")

	for p := byte(0); p <= 5; p++ {
		desc := fmt.Sprintf("func=3 param=0x%02X", p)
		sendShortVerbose(handle, [7]byte{0x10, devIdx, hapIdx, 0x3A, p, 0x00, 0x00}, desc)
		time.Sleep(300 * time.Millisecond)
		waitAndAsk(fmt.Sprintf("func=3 param=0x%02X — anything?", p))
	}

	// Cleanup
	fmt.Println("\n[CLEANUP] Disabling haptics")
	sendShort(handle, [7]byte{0x10, devIdx, hapIdx, 0x2A, 0x00, 0x64, 0x00})

	fmt.Println("\n================================================================")
	fmt.Println("  PROBE COMPLETE")
	fmt.Println("  Please paste the full terminal output back to the developer!")
	fmt.Println("================================================================")
	fmt.Print("\nPress Enter to exit...")
	fmt.Scanln()
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
