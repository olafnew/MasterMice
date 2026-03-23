"""
Logitech HID++ Mouse Diagnostic Tool v2.1
Tests ALL discoverable features: battery, DPI, report rate, buttons,
firmware, device name, and listens for live events.

Run:  python tools/battery_test.py
"""

import sys
import os
import time
import struct

try:
    import hid as _hid
except ImportError:
    print("ERROR: 'hidapi' not installed. Run: pip install hidapi")
    sys.exit(1)

LOGI_VID = 0x046D
SHORT_ID = 0x10
LONG_ID = 0x11
SHORT_LEN = 7
LONG_LEN = 20
MY_SW = 0x0A

# ── All known HID++ 2.0 features worth probing ──────────────────
FEATURES = {
    # Root / device info
    0x0001: "FEATURE_SET",
    0x0003: "DEVICE_FW_VERSION",
    0x0005: "DEVICE_NAME",
    0x0007: "DEVICE_FRIENDLY_NAME",
    # Battery
    0x1000: "BATTERY_LEVEL_STATUS",
    0x1001: "BATTERY_VOLTAGE",
    0x1004: "UNIFIED_BATTERY",
    # Input
    0x1B04: "REPROG_CONTROLS_V4",
    0x1D4B: "WIRELESS_DEVICE_STATUS",
    # Pointer
    0x2201: "ADJUSTABLE_DPI",
    0x2250: "HIRES_WHEEL",
    # Performance
    0x8060: "REPORT_RATE",
    0x8061: "EXTENDED_ADJUSTABLE_REPORT_RATE",
    # Lighting / cosmetic
    0x8070: "COLOR_LED_EFFECTS",
    0x8071: "RGB_EFFECTS",
    # Profiles
    0x8100: "ONBOARD_PROFILES",
    # Misc
    0x00C2: "DFU_CONTROL_SIGNED",
    0x1814: "CHANGE_HOST",
    0x1815: "HOSTS_INFO",
    0x1982: "BACKLIGHT2",
    0x1A20: "SENSOR_RESOLUTION",
    0x40A3: "FN_INVERSION",
}

# Battery status names
BATT_STATUS_1000 = {
    0: "discharging", 1: "recharging", 2: "charge_in_final",
    3: "charge_complete", 4: "recharging_below_optimal",
    5: "invalid_battery", 6: "thermal_error", 7: "other_error",
}
BATT_STATUS_1004 = {
    0: "discharging", 1: "recharging", 2: "almost_full", 3: "charged",
    4: "slow_recharging", 5: "invalid_battery", 6: "thermal_error",
}

REPORT_RATE_8061 = ["8ms (125Hz)", "4ms (250Hz)", "2ms (500Hz)",
                     "1ms (1000Hz)", "500us (2000Hz)", "250us (4000Hz)",
                     "125us (8000Hz)"]


def parse(raw):
    if not raw or len(raw) < 4:
        return None
    off = 1 if raw[0] in (SHORT_ID, LONG_ID) else 0
    if off + 3 > len(raw):
        return None
    dev = raw[off]
    feat = raw[off + 1]
    fsw = raw[off + 2]
    func = (fsw >> 4) & 0x0F
    sw = fsw & 0x0F
    params = raw[off + 3:]
    return dev, feat, func, sw, params


def hexdump(data, n=16):
    return " ".join(f"{b:02X}" for b in data[:n])


class HidppDevice:
    def __init__(self, hid_device, dev_idx=0xFF):
        self.dev = hid_device
        self.dev_idx = dev_idx
        self.features = {}  # fid -> index

    def tx(self, feat, func, params):
        buf = [0] * LONG_LEN
        buf[0] = LONG_ID
        buf[1] = self.dev_idx
        buf[2] = feat
        buf[3] = ((func & 0x0F) << 4) | (MY_SW & 0x0F)
        for i, b in enumerate(params):
            if 4 + i < LONG_LEN:
                buf[4 + i] = b & 0xFF
        self.dev.write(buf)

    def rx(self, timeout_ms=2000):
        raw = self.dev.read(64, timeout_ms)
        return list(raw) if raw else None

    def request(self, feat, func, params, timeout_ms=2000):
        self.tx(feat, func, params)
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            raw = self.rx(min(500, timeout_ms))
            if raw is None:
                continue
            msg = parse(raw)
            if msg is None:
                continue
            _, r_feat, r_func, r_sw, r_params = msg
            if r_feat == 0xFF:
                code = r_params[1] if len(r_params) > 1 else 0
                return None  # HID++ error
            if r_feat == feat and r_sw == MY_SW:
                return msg
        return None

    def find_feature(self, fid):
        hi = (fid >> 8) & 0xFF
        lo = fid & 0xFF
        resp = self.request(0x00, 0, [hi, lo, 0x00])
        if resp:
            _, _, _, _, p = resp
            if p and p[0] != 0:
                self.features[fid] = p[0]
                return p[0]
        return None

    def probe_all(self):
        print("\n╔══════════════════════════════════════════╗")
        print("║       HID++ Feature Discovery            ║")
        print("╠══════════════════════════════════════════╣")
        found = 0
        for fid, name in sorted(FEATURES.items()):
            idx = self.find_feature(fid)
            if idx is not None:
                print(f"║  0x{fid:04X} {name:<32s} @0x{idx:02X} ║")
                found += 1
            else:
                print(f"║  0x{fid:04X} {name:<32s}  ---  ║")
        print(f"╠══════════════════════════════════════════╣")
        print(f"║  {found} / {len(FEATURES)} features found{' ' * 20}║")
        print(f"╚══════════════════════════════════════════╝")


def test_device_name(d):
    if 0x0005 not in d.features:
        return
    idx = d.features[0x0005]
    print(f"\n── Device Name (0x0005 @0x{idx:02X}) ──")
    # Get name length
    resp = d.request(idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        name_len = p[0] if p else 0
        print(f"  Name length: {name_len}")
        # Read name in chunks
        name = ""
        for offset in range(0, name_len, 16):
            resp = d.request(idx, 1, [offset])
            if resp:
                _, _, _, _, p = resp
                chunk = bytes(p[:min(16, name_len - offset)])
                name += chunk.decode("utf-8", errors="replace")
        print(f"  Device name: \"{name}\"")


def test_firmware(d):
    if 0x0003 not in d.features:
        return
    idx = d.features[0x0003]
    print(f"\n── Firmware Version (0x0003 @0x{idx:02X}) ──")
    # Get entity count
    resp = d.request(idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        count = p[0] if p else 0
        print(f"  Firmware entities: {count}")
        for entity in range(count):
            resp = d.request(idx, 1, [entity])
            if resp:
                _, _, _, _, p = resp
                fw_type = p[0] if p else 0
                types = {0: "Main App", 1: "Bootloader", 2: "Hardware"}
                name = bytes(p[1:4]).decode("ascii", errors="replace")
                ver = f"{p[4]}.{p[5]}" if len(p) > 5 else "?"
                build = (p[6] << 8 | p[7]) if len(p) > 7 else 0
                print(f"  [{types.get(fw_type, f'type{fw_type}')}] "
                      f"{name} v{ver} build {build}")


def test_battery_1000(d):
    idx = d.features[0x1000]
    print(f"\n── Battery Level Status (0x1000 @0x{idx:02X}) ──")

    resp = d.request(idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        print(f"  Raw: [{hexdump(p)}]")
        level = p[0]
        next_lvl = p[1]
        status = p[2] if len(p) > 2 else 0
        status_name = BATT_STATUS_1000.get(status, f"unknown({status})")
        print(f"  Discharge level : {level}%")
        print(f"  Next level      : {next_lvl}%")
        print(f"  Status          : {status} ({status_name})")
        if status in (1, 2, 3, 4):
            print(f"  ** CHARGING **")
    else:
        print("  READ FAILED")

    # Capabilities
    resp = d.request(idx, 1, [])
    if resp:
        _, _, _, _, p = resp
        print(f"  Capabilities raw: [{hexdump(p)}]")


def test_battery_1001(d):
    idx = d.features[0x1001]
    print(f"\n── Battery Voltage (0x1001 @0x{idx:02X}) ──")

    resp = d.request(idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        print(f"  Raw: [{hexdump(p)}]")
        voltage = (p[0] << 8 | p[1]) if len(p) >= 2 else 0
        flags = p[2] if len(p) > 2 else 0
        print(f"  Voltage : {voltage} mV")
        print(f"  Flags   : 0x{flags:02X}")
        charging = (flags & 0x80) != 0
        print(f"  Charging: {charging}")
    else:
        print("  READ FAILED")


def test_battery_1004(d):
    idx = d.features[0x1004]
    print(f"\n── Unified Battery (0x1004 @0x{idx:02X}) ──")

    # Capabilities
    resp = d.request(idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        print(f"  Capabilities raw: [{hexdump(p)}]")
        print(f"  Supported levels: 0x{p[0]:02X}, flags: 0x{p[1]:02X}" if len(p) > 1 else "")

    # Status
    resp = d.request(idx, 1, [])
    if resp:
        _, _, _, _, p = resp
        print(f"  Status raw: [{hexdump(p)}]")
        soc = p[0]
        batt_status = p[1] if len(p) > 1 else 0
        ext_power = p[2] if len(p) > 2 else 0
        status_name = BATT_STATUS_1004.get(batt_status, f"unknown({batt_status})")
        print(f"  State of charge : {soc}%")
        print(f"  Battery status  : {batt_status} ({status_name})")
        print(f"  External power  : {ext_power} ({'plugged' if ext_power else 'unplugged'})")
        if batt_status in (1, 2):
            print(f"  ** CHARGING **")
    else:
        print("  READ FAILED")


def test_dpi(d):
    if 0x2201 not in d.features:
        return
    idx = d.features[0x2201]
    print(f"\n── Adjustable DPI (0x2201 @0x{idx:02X}) ──")

    # Get sensor count
    resp = d.request(idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        count = p[0] if p else 0
        print(f"  Sensor count: {count}")

    # Get DPI list (function 1)
    resp = d.request(idx, 1, [0x00])
    if resp:
        _, _, _, _, p = resp
        print(f"  DPI list raw: [{hexdump(p)}]")
        # Parse DPI steps
        i = 0
        dpis = []
        while i + 1 < len(p):
            val = (p[i] << 8) | p[i + 1]
            if val == 0:
                break
            if val & 0xE000:
                # Step format: bits[15:13]=step, bits[12:0]=start
                step = (val >> 13) * 50
                start = val & 0x1FFF
                dpis.append(f"{start}-step{step}")
            else:
                dpis.append(str(val))
            i += 2
        print(f"  Supported DPIs: {', '.join(dpis)}")

    # Current DPI (function 2)
    resp = d.request(idx, 2, [0x00])
    if resp:
        _, _, _, _, p = resp
        current = (p[1] << 8 | p[2]) if len(p) >= 3 else 0
        default_idx = p[3] if len(p) > 3 else 0
        print(f"  Current DPI: {current}")


def test_hires_wheel(d):
    if 0x2250 not in d.features:
        return
    idx = d.features[0x2250]
    print(f"\n── Hi-Res Wheel (0x2250 @0x{idx:02X}) ──")

    resp = d.request(idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        print(f"  Capabilities raw: [{hexdump(p)}]")
        multiplier = p[0] if p else 0
        flags = p[1] if len(p) > 1 else 0
        print(f"  Multiplier: {multiplier}")
        print(f"  Has invert: {bool(flags & 0x08)}")
        print(f"  Has ratchet switch: {bool(flags & 0x04)}")

    # Get mode
    resp = d.request(idx, 1, [])
    if resp:
        _, _, _, _, p = resp
        print(f"  Mode raw: [{hexdump(p)}]")
        invert = bool(p[0] & 0x04) if p else False
        hires = bool(p[0] & 0x02) if p else False
        target = bool(p[0] & 0x01) if p else False
        print(f"  HiRes mode: {hires}, Inverted: {invert}, Target: {target}")


def test_report_rate(d):
    if 0x8060 not in d.features:
        return
    idx = d.features[0x8060]
    print(f"\n── Report Rate (0x8060 @0x{idx:02X}) ──")

    # Get report rate list (function 0)
    resp = d.request(idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        print(f"  Rate list raw: [{hexdump(p)}]")
        # Bitmap of supported rates
        # bit 0 = 1ms, bit 1 = 2ms, bit 2 = 3ms, bit 3 = 4ms, bit 4 = 5ms, bit 5 = 6ms, bit 6 = 7ms, bit 7 = 8ms
        bitmap = p[0] if p else 0
        rates = []
        for bit in range(8):
            if bitmap & (1 << bit):
                ms = bit + 1
                rates.append(f"{ms}ms ({1000 // ms}Hz)")
        if rates:
            print(f"  Supported rates: {', '.join(rates)}")
        else:
            print(f"  Bitmap: 0x{bitmap:02X}")

    # Get current rate (function 1)
    resp = d.request(idx, 1, [])
    if resp:
        _, _, _, _, p = resp
        print(f"  Current rate raw: [{hexdump(p)}]")
        rate_ms = p[0] if p else 0
        if rate_ms:
            print(f"  Current rate: {rate_ms}ms ({1000 // rate_ms}Hz)")


def test_extended_report_rate(d):
    if 0x8061 not in d.features:
        return
    idx = d.features[0x8061]
    print(f"\n── Extended Adjustable Report Rate (0x8061 @0x{idx:02X}) ──")

    # Get supported rates (function 0)
    resp = d.request(idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        print(f"  Supported raw: [{hexdump(p)}]")

    # Get current rate (function 2)
    resp = d.request(idx, 2, [])
    if resp:
        _, _, _, _, p = resp
        print(f"  Current raw: [{hexdump(p)}]")
        rate_idx = p[0] if p else 0
        if rate_idx < len(REPORT_RATE_8061):
            print(f"  Current rate: {REPORT_RATE_8061[rate_idx]}")
        else:
            print(f"  Rate index: {rate_idx}")


def test_reprog_controls(d):
    if 0x1B04 not in d.features:
        return
    idx = d.features[0x1B04]
    print(f"\n── Reprogrammable Controls V4 (0x1B04 @0x{idx:02X}) ──")

    # Get control count (function 0)
    resp = d.request(idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        count = p[0] if p else 0
        print(f"  Control count: {count}")

        # List all controls (function 1)
        for i in range(count):
            resp = d.request(idx, 1, [i])
            if resp:
                _, _, _, _, p = resp
                cid = (p[0] << 8 | p[1]) if len(p) >= 2 else 0
                tid = (p[2] << 8 | p[3]) if len(p) >= 4 else 0
                flags = p[4] if len(p) > 4 else 0
                pos = p[5] if len(p) > 5 else 0
                group = p[6] if len(p) > 6 else 0
                gmask = p[7] if len(p) > 7 else 0
                divertable = bool(flags & 0x01)
                persist = bool(flags & 0x04)
                virtual = bool(flags & 0x10)
                print(f"  [{i:2d}] CID=0x{cid:04X} TID=0x{tid:04X} "
                      f"{'divert' if divertable else '      '} "
                      f"{'persist' if persist else '       '} "
                      f"{'virtual' if virtual else '       '} "
                      f"pos={pos} grp={group}")


def test_change_host(d):
    if 0x1814 not in d.features:
        return
    idx = d.features[0x1814]
    print(f"\n── Change Host (0x1814 @0x{idx:02X}) ──")
    resp = d.request(idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        count = p[0] if p else 0
        current = p[1] if len(p) > 1 else 0
        print(f"  Host count: {count}, current host: {current}")


def listen_events(d, duration=10):
    print(f"\n── Listening for live events ({duration}s) ──")
    print("  (Move mouse, click buttons, plug/unplug charger...)")
    start = time.time()
    count = 0
    while time.time() - start < duration:
        raw = d.rx(500)
        if raw is None:
            continue
        msg = parse(raw)
        if msg is None:
            continue
        _, feat, func, sw, params = msg
        elapsed = time.time() - start

        # Identify the feature
        feat_name = "?"
        for fid, fidx in d.features.items():
            if fidx == feat:
                feat_name = FEATURES.get(fid, f"0x{fid:04X}")
                break

        print(f"  [{elapsed:5.1f}s] feat=0x{feat:02X}({feat_name}) "
              f"func={func} sw=0x{sw:X} data=[{hexdump(params, 8)}]")
        count += 1

    print(f"  Captured {count} events in {duration}s")


def main():
    print("=" * 60)
    print("  Logitech HID++ Mouse Diagnostic Tool v2")
    print("=" * 60)

    print("\nScanning for Logitech HID++ devices...")
    infos = []
    for info in _hid.enumerate(LOGI_VID, 0):
        up = info.get("usage_page", 0)
        if up >= 0xFF00:
            infos.append(info)
            pid = info.get("product_id", 0)
            usage = info.get("usage", 0)
            product = info.get("product_string", "")
            mfr = info.get("manufacturer_string", "")
            serial = info.get("serial_number", "")
            print(f"  PID=0x{pid:04X}  UP=0x{up:04X}  "
                  f"\"{product}\"  mfr=\"{mfr}\"  sn=\"{serial}\"")

    if not infos:
        print("\nNo Logitech HID++ devices found!")
        print("Ensure mouse is on and connected via Bluetooth or Bolt.")
        input("Press Enter to exit...")
        sys.exit(1)

    for info in infos:
        pid = info.get("product_id", 0)
        product = info.get("product_string", "")
        print(f"\n{'=' * 60}")
        print(f"  Testing: {product} (PID=0x{pid:04X})")
        print(f"{'=' * 60}")

        try:
            dev = _hid.device()
            dev.open_path(info["path"])
            dev.set_nonblocking(False)
        except Exception as e:
            print(f"  Cannot open: {e}")
            continue

        # Try device indices
        d = None
        for idx in (0xFF, 1, 2, 3, 4, 5, 6):
            resp = HidppDevice(dev, idx).request(0x00, 0, [0x00, 0x01, 0x00], timeout_ms=1000)
            if resp:
                d = HidppDevice(dev, idx)
                print(f"  Connected at device index 0x{idx:02X}")
                break

        if d is None:
            print("  No responding device index found")
            dev.close()
            continue

        # Discover all features
        d.probe_all()

        # Run all tests
        test_device_name(d)
        test_firmware(d)

        if 0x1000 in d.features:
            test_battery_1000(d)
        if 0x1001 in d.features:
            test_battery_1001(d)
        if 0x1004 in d.features:
            test_battery_1004(d)

        test_dpi(d)
        test_hires_wheel(d)
        test_report_rate(d)
        test_extended_report_rate(d)
        test_reprog_controls(d)
        test_change_host(d)

        # Live event capture
        listen_events(d, duration=15)

        try:
            dev.close()
        except Exception:
            pass

    print(f"\n{'=' * 60}")
    print("  Diagnostic complete.")
    print(f"{'=' * 60}")
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
