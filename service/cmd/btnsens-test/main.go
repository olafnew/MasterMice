// btnsens_test — Targeted probe for button sensitivity SET command format.
package main

import (
	"fmt"
	"os"
	"time"

	"github.com/olafnew/mastermice-svc/internal/hidpp"
	"github.com/sstallion/go-hid"
)

func main() {
	fmt.Println("=== Button Sensitivity SET Probe ===")
	fmt.Println("Testing parameter formats for func=3 on feature 0x19C0\n")

	hidpp.Debug = true

	var devPath string
	hid.Enumerate(hidpp.LogiVID, 0, func(info *hid.DeviceInfo) error {
		if info.UsagePage >= 0xFF00 && info.UsagePage != 0xFFBC && info.Usage == 0x0002 && devPath == "" {
			devPath = info.Path
			fmt.Printf("[ENUM] PID=0x%04X\n", info.ProductID)
		}
		return nil
	})
	if devPath == "" {
		fmt.Println("No device found")
		os.Exit(1)
	}

	dev, err := hid.OpenPath(devPath)
	if err != nil {
		fmt.Printf("Open failed: %v\n", err)
		os.Exit(1)
	}
	defer dev.Close()

	t := hidpp.NewTransport(dev, 0x02)
	idx, _ := t.RequestIRoot(0x19C0)
	fmt.Printf("[OK] Feature 0x19C0 at index 0x%02X\n\n", idx)

	// Read current value first
	report, err := t.Request(idx, 2, nil, 2*time.Second)
	if err == nil {
		fmt.Printf("Current value (func=2): %02X\n\n", report.Params)
	}

	light := uint16(0x0F3E)
	medium := uint16(0x130E)

	// Test func=3 with different parameter formats
	fmt.Println("=== func=3 parameter format tests ===\n")

	tests := []struct {
		desc   string
		params []byte
	}{
		// Format: [index, hi, lo]
		{"[0x00, 0x0F, 0x3E] (index=0, Light)", []byte{0x00, 0x0F, 0x3E}},
		{"[0x01, 0x0F, 0x3E] (index=1, Light)", []byte{0x01, 0x0F, 0x3E}},
		// Format: [hi, lo] (what we had)
		{"[0x0F, 0x3E] (Light, no index)", []byte{0x0F, 0x3E}},
		// Format: [0x00, 0x01, hi, lo] (index + subindex?)
		{"[0x00, 0x01, 0x0F, 0x3E] (idx=0, sub=1, Light)", []byte{0x00, 0x01, 0x0F, 0x3E}},
		{"[0x00, 0x00, 0x0F, 0x3E] (idx=0, sub=0, Light)", []byte{0x00, 0x00, 0x0F, 0x3E}},
		// Format: single byte preset index
		{"[0x00] (preset index 0)", []byte{0x00}},
		{"[0x01] (preset index 1)", []byte{0x01}},
		{"[0x02] (preset index 2)", []byte{0x02}},
		{"[0x03] (preset index 3)", []byte{0x03}},
	}

	for _, test := range tests {
		report, err := t.Request(idx, 3, test.params, 2*time.Second)
		if err != nil {
			fmt.Printf("  func=3 %s → ERROR: %v\n", test.desc, err)
		} else {
			fmt.Printf("  func=3 %s → OK: %02X\n", test.desc, report.Params)
		}
		time.Sleep(300 * time.Millisecond)
	}

	// Also try func=2 as SET with different formats
	fmt.Println("\n=== func=2 as SET (with index prefix) ===\n")
	tests2 := []struct {
		desc   string
		params []byte
	}{
		{"[0x00, 0x13, 0x0E] (idx=0, Medium)", []byte{0x00, byte(medium >> 8), byte(medium & 0xFF)}},
		{"[0x00, 0x0F, 0x3E] (idx=0, Light)", []byte{0x00, byte(light >> 8), byte(light & 0xFF)}},
	}
	for _, test := range tests2 {
		report, err := t.Request(idx, 2, test.params, 2*time.Second)
		if err != nil {
			fmt.Printf("  func=2 %s → ERROR: %v\n", test.desc, err)
		} else {
			fmt.Printf("  func=2 %s → OK: %02X\n", test.desc, report.Params)
		}
		time.Sleep(300 * time.Millisecond)
	}

	// Verify current value changed
	fmt.Println("\n=== Verify current value ===")
	report, err = t.Request(idx, 2, nil, 2*time.Second)
	if err == nil {
		fmt.Printf("Current value now: %02X\n", report.Params)
	}

	fmt.Println("\n=== Done ===")
	fmt.Print("Press Enter to exit...")
	fmt.Scanln()
}
