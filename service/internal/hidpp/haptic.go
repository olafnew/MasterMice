package hidpp

import (
	"fmt"
	"time"
	"unsafe"

	"github.com/sstallion/go-hid"
	"golang.org/x/sys/windows"
)

// Windows HID API for SetOutputReport (control transfer on SHORT handle)
var (
	hidDLL               = windows.MustLoadDLL("hid.dll")
	procSetOutputReport  = hidDLL.MustFindProc("HidD_SetOutputReport")
)

// OpenShortHandle finds and opens the SHORT HID++ collection (usage 0x0001)
// for the same receiver PID. This handle is used for haptic motor commands
// via HidD_SetOutputReport (USB control transfer).
func (d *Device) OpenShortHandle() error {
	if d.ConnPID == 0 {
		return fmt.Errorf("no PID — cannot find SHORT handle")
	}
	if d.ShortHandle != 0 {
		return nil // already open
	}

	var shortPath string
	hid.Enumerate(LogiVID, d.ConnPID, func(info *hid.DeviceInfo) error {
		if info.UsagePage == 0xFF00 && info.Usage == 0x0001 && shortPath == "" {
			shortPath = info.Path
		}
		return nil
	})

	if shortPath == "" {
		return fmt.Errorf("SHORT interface (usage 0x0001) not found for PID 0x%04X", d.ConnPID)
	}

	pathW, err := windows.UTF16PtrFromString(shortPath)
	if err != nil {
		return err
	}

	h, err := windows.CreateFile(pathW,
		windows.GENERIC_READ|windows.GENERIC_WRITE,
		windows.FILE_SHARE_READ|windows.FILE_SHARE_WRITE,
		nil, windows.OPEN_EXISTING, 0, 0)
	if err != nil {
		return fmt.Errorf("CreateFile for SHORT handle: %w", err)
	}

	d.ShortHandle = h
	fmt.Printf("[HAPTIC] SHORT handle opened (PID=0x%04X)\n", d.ConnPID)
	return nil
}

// CloseShortHandle closes the SHORT handle.
func (d *Device) CloseShortHandle() {
	if d.ShortHandle != 0 {
		windows.CloseHandle(d.ShortHandle)
		d.ShortHandle = 0
	}
}

// sendShort sends a 7-byte report via HidD_SetOutputReport on the SHORT handle.
func (d *Device) sendShort(report [7]byte) error {
	if d.ShortHandle == 0 {
		return fmt.Errorf("SHORT handle not open")
	}
	ret, _, _ := procSetOutputReport.Call(
		uintptr(d.ShortHandle),
		uintptr(unsafe.Pointer(&report[0])),
		7,
	)
	if ret == 0 {
		return fmt.Errorf("HidD_SetOutputReport failed")
	}
	return nil
}

// HapticSetConfig enables/disables the haptic motor and sets intensity.
// enabled: true=on, false=off
// intensity: 0-100 (percentage)
func (d *Device) HapticSetConfig(enabled bool, intensity int) error {
	if d.HapticIdx == 0 {
		return fmt.Errorf("haptic feature not available")
	}
	if err := d.OpenShortHandle(); err != nil {
		return err
	}

	mode := byte(0x00)
	if enabled {
		mode = 0x01
	}
	if intensity < 0 {
		intensity = 0
	}
	if intensity > 100 {
		intensity = 100
	}

	// func=2, SW=0x0A → byte3 = (2 << 4) | 0x0A = 0x2A
	report := [7]byte{
		0x10, d.DevIdx, d.HapticIdx, 0x2A,
		mode, byte(intensity), 0x00,
	}
	if err := d.sendShort(report); err != nil {
		return err
	}
	d.CachedHapticEnabled = enabled
	d.CachedHapticIntensity = intensity
	fmt.Printf("[HAPTIC] Config: %s intensity=%d%%\n",
		map[bool]string{true: "ON", false: "OFF"}[enabled], intensity)
	return nil
}

// HapticTrigger sends a haptic pulse.
// pulseType: 0x01=nudge, 0x02=light, 0x04=tick, 0x08=strong
// Can be OR'd for combos: 0x06=buzz, 0x0A=burst, 0x0C=triple, 0x0E=double-buzz
func (d *Device) HapticTrigger(pulseType byte) error {
	if d.HapticIdx == 0 {
		return fmt.Errorf("haptic feature not available")
	}
	if err := d.OpenShortHandle(); err != nil {
		return err
	}

	// func=4, SW=0x0A → byte3 = (4 << 4) | 0x0A = 0x4A
	report := [7]byte{
		0x10, d.DevIdx, d.HapticIdx, 0x4A,
		pulseType, 0x00, 0x00,
	}
	return d.sendShort(report)
}

// HapticSequenceStep defines one step in a haptic sequence.
type HapticSequenceStep struct {
	Pulse byte // pulse type (OR'd bits)
	Delay int  // delay in ms AFTER this pulse (before next step)
}

// HapticPlaySequence plays a sequence of haptic pulses with delays.
// repeat: number of times to play the sequence (1 = once).
func (d *Device) HapticPlaySequence(steps []HapticSequenceStep, repeat int) error {
	if d.HapticIdx == 0 {
		return fmt.Errorf("haptic feature not available")
	}
	if err := d.OpenShortHandle(); err != nil {
		return err
	}
	if repeat < 1 {
		repeat = 1
	}
	if repeat > 20 {
		repeat = 20 // safety cap
	}

	for r := 0; r < repeat; r++ {
		for _, step := range steps {
			if step.Pulse > 0 {
				report := [7]byte{
					0x10, d.DevIdx, d.HapticIdx, 0x4A,
					step.Pulse, 0x00, 0x00,
				}
				if err := d.sendShort(report); err != nil {
					return err
				}
			}
			if step.Delay > 0 {
				time.Sleep(time.Duration(step.Delay) * time.Millisecond)
			}
		}
	}
	return nil
}
