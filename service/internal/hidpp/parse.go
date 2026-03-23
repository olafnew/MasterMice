package hidpp

// Report represents a parsed HID++ report.
type Report struct {
	DevIdx  byte
	FeatIdx byte
	Func    byte
	SW      byte
	Params  []byte
}

// IsError returns true if this report signals an HID++ error (feat_idx == 0xFF).
func (r *Report) IsError() bool {
	return r.FeatIdx == 0xFF
}

// Parse interprets a raw HID read buffer into a Report.
//
// On Windows the hidapi C backend strips the report-ID byte, so byte 0 is
// the device index. On other platforms the report-ID may be present.
// We detect which layout by checking if byte 0 is a valid report-ID.
func Parse(raw []byte) *Report {
	if len(raw) < 4 {
		return nil
	}

	off := 0
	if raw[0] == ShortID || raw[0] == LongID {
		off = 1
	}

	if off+3 > len(raw) {
		return nil
	}

	fsw := raw[off+2]
	return &Report{
		DevIdx:  raw[off],
		FeatIdx: raw[off+1],
		Func:    (fsw >> 4) & 0x0F,
		SW:      fsw & 0x0F,
		Params:  raw[off+3:],
	}
}
