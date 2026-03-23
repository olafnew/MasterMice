// Package hidpp implements the Logitech HID++ 2.0 protocol for MX Master mice.
package hidpp

// Logitech vendor ID
const LogiVID = 0x046D

// HID++ report IDs and sizes
const (
	ShortID  = 0x10
	LongID   = 0x11
	ShortLen = 7
	LongLen  = 20
)

// Device index for direct Bluetooth connection
const BTDevIdx = 0xFF

// Software ID used in our requests (arbitrary, for matching responses)
const MySW = 0x0A

// HID++ 2.0 feature IDs
const (
	FeatIRoot       = 0x0000
	FeatDeviceName  = 0x0005
	FeatReprogV4    = 0x1B04
	FeatAdjDPI      = 0x2201
	FeatBattUnified = 0x1004
	FeatBattLevel   = 0x1000
	FeatSmartShift  = 0x2110
	FeatSmartShift2 = 0x2111
	FeatHiResWheel  = 0x2121
	FeatHiResWheel2 = 0x2250
	FeatHaptic      = 0xB019
)

// Control IDs for button divert
const (
	CIDGesture    = 0x00C3 // Mouse Gesture Button
	CIDActionsRing = 0x01A0 // Actions Ring / Haptic Sense Panel (MX4)
)

// Model keys (must match DEVICE_PROFILES in Python config.py)
const (
	ModelMX3 = "mx_master_3s"
	ModelMX4 = "mx_master_4"
)

// Receiver PIDs for connection type detection
const (
	PIDUnifyingOld = 0xC52B
	PIDUnifyingNew = 0xC534
	PIDUnifyingAlt = 0xC539
	PIDBolt        = 0xC548
)
