package hidpp

import (
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/sstallion/go-hid"
)

var (
	ErrTimeout    = errors.New("hidpp: request timed out")
	ErrDevice     = errors.New("hidpp: device error")
	ErrNotOpen    = errors.New("hidpp: device not open")
	ErrReadFailed = errors.New("hidpp: read failed")
)

// Transport handles low-level HID++ I/O on a single HID device.
// Uses sstallion/go-hid which supports ReadWithTimeout natively.
type Transport struct {
	dev    *hid.Device
	devIdx byte
	mu     sync.Mutex
}

// NewTransport wraps an already-opened hid.Device.
func NewTransport(dev *hid.Device, devIdx byte) *Transport {
	return &Transport{
		dev:    dev,
		devIdx: devIdx,
	}
}

// Close closes the underlying HID device.
func (t *Transport) Close() {
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.dev != nil {
		t.dev.Close()
		t.dev = nil
	}
}

// SetDevIdx changes the device index for subsequent commands.
func (t *Transport) SetDevIdx(idx byte) {
	t.mu.Lock()
	t.devIdx = idx
	t.mu.Unlock()
}

// tx sends a 20-byte LONG HID++ report.
// Caller must hold t.mu.
func (t *Transport) tx(featIdx, funcID byte, params []byte) error {
	if t.dev == nil {
		return ErrNotOpen
	}

	buf := make([]byte, LongLen)
	buf[0] = LongID
	buf[1] = t.devIdx
	buf[2] = featIdx
	buf[3] = (funcID << 4) | MySW

	copy(buf[4:], params)

	_, err := t.dev.Write(buf)
	return err
}

// rx reads a report with timeout using hidapi's native timeout support.
// Caller must hold t.mu.
func (t *Transport) rx(timeout time.Duration) (*Report, error) {
	if t.dev == nil {
		return nil, ErrNotOpen
	}

	buf := make([]byte, LongLen+1)
	n, err := t.dev.ReadWithTimeout(buf, timeout)
	if err != nil {
		if errors.Is(err, hid.ErrTimeout) {
			return nil, ErrTimeout
		}
		return nil, fmt.Errorf("%w: %v", ErrReadFailed, err)
	}
	if n == 0 {
		return nil, ErrTimeout
	}

	report := Parse(buf[:n])
	if report == nil {
		return nil, fmt.Errorf("hidpp: failed to parse %d-byte report", n)
	}
	return report, nil
}

// Debug controls whether raw HID++ I/O is logged.
var Debug = false

// Request sends a command and waits for the matching response.
func (t *Transport) Request(featIdx, funcID byte, params []byte, timeout time.Duration) (*Report, error) {
	t.mu.Lock()
	defer t.mu.Unlock()

	if err := t.tx(featIdx, funcID, params); err != nil {
		return nil, fmt.Errorf("hidpp: tx failed: %w", err)
	}

	deadline := time.Now().Add(timeout)
	discarded := 0
	for time.Now().Before(deadline) {
		remaining := time.Until(deadline)
		if remaining < 10*time.Millisecond {
			remaining = 10 * time.Millisecond
		}

		report, err := t.rx(remaining)
		if err != nil {
			if errors.Is(err, ErrTimeout) {
				if Debug {
					fmt.Printf("[HID++ DBG] Request(feat=0x%02X func=%d) TIMEOUT after discarding %d reports\n",
						featIdx, funcID, discarded)
				}
				return nil, ErrTimeout
			}
			return nil, err
		}

		if Debug {
			fmt.Printf("[HID++ DBG] RX: devIdx=0x%02X feat=0x%02X func=%d sw=0x%X params=%02X\n",
				report.DevIdx, report.FeatIdx, report.Func, report.SW, report.Params)
		}

		// Match response: same feature index and our software ID
		if report.FeatIdx == featIdx && report.SW == MySW {
			return report, nil
		}

		// Error response for our feature
		if report.IsError() {
			if Debug {
				fmt.Printf("[HID++ DBG] Error report: feat=0xFF params=%02X\n", report.Params)
			}
			if len(report.Params) >= 2 {
				return nil, fmt.Errorf("%w: error code 0x%02X (params=%02X)",
					ErrDevice, report.Params[1], report.Params)
			}
		}

		discarded++
	}

	if Debug {
		fmt.Printf("[HID++ DBG] Request(feat=0x%02X func=%d) TIMEOUT after discarding %d reports\n",
			featIdx, funcID, discarded)
	}
	return nil, ErrTimeout
}

// Probe sends an IRoot query and returns true if the device responds
// at this index (even with an error). Used for device index discovery.
func (t *Transport) Probe(featIdx byte, featureID uint16, timeout time.Duration) bool {
	t.mu.Lock()
	defer t.mu.Unlock()

	params := make([]byte, LongLen-4)
	params[0] = byte(featureID >> 8)
	params[1] = byte(featureID & 0xFF)

	if err := t.tx(featIdx, 0, params); err != nil {
		return false
	}

	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		remaining := time.Until(deadline)
		if remaining < 10*time.Millisecond {
			remaining = 10 * time.Millisecond
		}

		report, err := t.rx(remaining)
		if err != nil {
			if errors.Is(err, ErrTimeout) {
				return false
			}
			return false
		}

		// ANY response from the device (success or error) means this index is alive
		if report.FeatIdx == featIdx && report.SW == MySW {
			return true
		}
		if report.IsError() && len(report.Params) >= 1 && report.Params[0] == featIdx {
			return true
		}

		// Notification from another source — keep waiting
	}

	return false
}

// RequestIRoot queries feature 0x0000 (IRoot) to find the index of a feature by ID.
// Returns the feature index, or 0 if not found.
// Uses 2s timeout to handle notification-heavy devices.
func (t *Transport) RequestIRoot(featureID uint16) (byte, error) {
	params := []byte{byte(featureID >> 8), byte(featureID & 0xFF)}
	report, err := t.Request(0x00, 0, params, 2*time.Second)
	if err != nil {
		return 0, err
	}
	if len(report.Params) < 1 {
		return 0, fmt.Errorf("hidpp: IRoot response too short")
	}
	return report.Params[0], nil
}

// Read reads a single report with timeout, returning any report (including notifications).
func (t *Transport) Read(timeout time.Duration) (*Report, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.rx(timeout)
}

// Send sends a command without waiting for a response.
func (t *Transport) Send(featIdx, funcID byte, params []byte) error {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.tx(featIdx, funcID, params)
}
