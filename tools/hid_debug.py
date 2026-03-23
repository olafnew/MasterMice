"""
Logitech HID++ Deep Diagnostic Tool
Enumerates ALL HID devices, shows raw details, attempts every possible
connection method. Designed to troubleshoot "no compatible device" issues.

Run:  python tools/hid_debug.py
"""

VERSION = "1.1"

import sys
import os
import time
import json

try:
    import hid as _hid
except ImportError:
    print("ERROR: 'hidapi' not installed. Run: pip install hidapi")
    sys.exit(1)

LOGI_VID = 0x046D
SHORT_ID = 0x10
LONG_ID  = 0x11
SHORT_LEN = 7
LONG_LEN  = 20
MY_SW = 0x0A

LOG_PATH = os.path.join(os.environ.get("TEMP", "."), "hid_debug.log")
LOG_FILE = None

def log(msg=""):
    print(msg)
    if LOG_FILE:
        try:
            LOG_FILE.write(msg + "\n")
            LOG_FILE.flush()
        except Exception:
            pass

def fmt_hex(data):
    return " ".join(f"{b:02X}" for b in data)

def main():
    global LOG_FILE
    LOG_FILE = open(LOG_PATH, "w", encoding="utf-8")
    log("=" * 70)
    log("  Logitech HID++ Deep Diagnostic Tool")
    log("=" * 70)
    log(f"Logging to: {LOG_PATH}")
    log(f"Session: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Python: {sys.version}")
    log(f"hidapi: {_hid.version() if hasattr(_hid, 'version') else 'unknown'}")
    log()

    # ── Phase 1: Enumerate ALL HID devices ──────────────────────
    log("=" * 70)
    log("  PHASE 1: Full HID Device Enumeration")
    log("=" * 70)
    log()

    all_devs = _hid.enumerate()
    log(f"Total HID devices on system: {len(all_devs)}")
    log()

    # Show ALL Logitech devices
    logi_devs = [d for d in all_devs if d.get("vendor_id") == LOGI_VID]
    log(f"Logitech devices (VID=0x{LOGI_VID:04X}): {len(logi_devs)}")
    log("-" * 70)

    for i, d in enumerate(logi_devs):
        pid = d.get("product_id", 0)
        up = d.get("usage_page", 0)
        usage = d.get("usage", 0)
        iface = d.get("interface_number", -1)
        prod = d.get("product_string", "?")
        mfr = d.get("manufacturer_string", "?")
        sn = d.get("serial_number", "")
        path = d.get("path", b"").decode("utf-8", errors="replace") if isinstance(d.get("path"), bytes) else str(d.get("path", ""))
        out_len = d.get("output_report_length", 0)
        in_len = d.get("input_report_length", 0)

        log(f"  [{i:2d}] PID=0x{pid:04X}  UP=0x{up:04X}  Usage=0x{usage:04X}  "
            f"iface={iface}")
        log(f"       product=\"{prod}\"  manufacturer=\"{mfr}\"  serial=\"{sn}\"")
        log(f"       output_report_length={out_len}  input_report_length={in_len}")
        log(f"       path={path[:100]}")
        log()

    if not logi_devs:
        log("  NO Logitech HID devices found!")
        log("  Check: is the receiver plugged in? Is the mouse paired?")
        log()

    # ── Phase 2: Categorize interfaces ──────────────────────────
    log("=" * 70)
    log("  PHASE 2: Interface Analysis")
    log("=" * 70)
    log()

    candidates = []
    for d in logi_devs:
        pid = d.get("product_id", 0)
        up = d.get("usage_page", 0)
        out_len = d.get("output_report_length", 0)
        in_len = d.get("input_report_length", 0)
        prod = d.get("product_string", "?")

        category = "unknown"
        suitable = False

        if up == 0xFFBC:
            category = "RECEIVER_MGMT (0xFFBC) — pairing/firmware, NOT for device HID++"
        elif up == 0xFF43:
            category = "BLUETOOTH_DIRECT (0xFF43) — Bluetooth HID++"
            suitable = True
        elif up == 0xFF00:
            # Always try 0xFF00 — some Windows builds report length=0
            suitable = True
            if out_len >= 20:
                category = f"VENDOR_HID++ (0xFF00) — LONG reports ({out_len}B) ← BEST CANDIDATE"
            elif out_len >= 7:
                category = f"VENDOR_HID++ (0xFF00) — SHORT reports ({out_len}B)"
            else:
                category = f"VENDOR_HID++ (0xFF00) — report size unknown (trying anyway)"
        elif up == 0x0001 and d.get("usage", 0) == 0x0002:
            category = "STANDARD_MOUSE (UP=0x0001 U=0x0002) — normal mouse HID"
        elif up == 0x0001 and d.get("usage", 0) == 0x0006:
            category = "STANDARD_KEYBOARD (UP=0x0001 U=0x0006)"
        elif up == 0x000C:
            category = "CONSUMER_CONTROL (UP=0x000C) — media keys"
        elif up >= 0xFF00:
            category = f"VENDOR_SPECIFIC (0x{up:04X}) — may be HID++"
            suitable = True  # always try vendor-specific pages

        log(f"  PID=0x{pid:04X} UP=0x{up:04X} out={out_len:3d}B in={in_len:3d}B "
            f"→ {category}")

        if suitable:
            candidates.append(d)

    log()
    log(f"  HID++ candidates: {len(candidates)}")

    if not candidates:
        log()
        log("  *** NO SUITABLE HID++ INTERFACES FOUND ***")
        log("  Possible causes:")
        log("    1. Logi Options+ agent is still running (logioptionsplus_agent.exe)")
        log("       → Check Task Manager, kill it, and retry")
        log("    2. Logitech driver still has exclusive access after uninstall")
        log("       → Unplug receiver, wait 5s, plug back in")
        log("    3. LogiMgr or SetPoint still installed")
        log("       → Check installed programs")
        log("    4. Windows HID driver issue")
        log("       → Try a different USB port")
        log()

        # Check for Logi processes
        log("  Checking for Logitech processes...")
        try:
            import subprocess
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq logi*", "/FO", "CSV"],
                capture_output=True, text=True, timeout=5
            )
            lines = [l for l in result.stdout.strip().split("\n") if l and "INFO:" not in l]
            if len(lines) > 1:
                for line in lines[1:]:
                    log(f"    FOUND: {line}")
                log("    ^^^ These may be blocking HID access!")
            else:
                log("    No Logitech processes found running.")
        except Exception as e:
            log(f"    Could not check processes: {e}")

        # Also check for any process with "logi" in name
        log()
        log("  Checking for ALL logi* processes...")
        try:
            result = subprocess.run(
                ["wmic", "process", "where",
                 "name like '%logi%'",
                 "get", "name,processid,executablepath", "/format:csv"],
                capture_output=True, text=True, timeout=5
            )
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip() and "Node" not in l]
            if lines:
                for line in lines:
                    log(f"    {line}")
            else:
                log("    None found.")
        except Exception:
            pass

        log()

    # ── Phase 3: Try to open and probe each candidate ───────────
    log("=" * 70)
    log("  PHASE 3: Connection Attempts")
    log("=" * 70)
    log()

    for ci, d in enumerate(candidates):
        pid = d.get("product_id", 0)
        up = d.get("usage_page", 0)
        out_len = d.get("output_report_length", 0)
        path = d.get("path", b"")
        prod = d.get("product_string", "?")

        log(f"--- Candidate {ci + 1}: PID=0x{pid:04X} UP=0x{up:04X} "
            f"out={out_len}B \"{prod}\" ---")

        # Try to open
        dev = _hid.device()
        try:
            dev.open_path(path)
            log(f"  [OK] Opened successfully")
        except Exception as e:
            log(f"  [FAIL] Cannot open: {e}")
            log(f"  → This usually means another process has exclusive access")
            continue

        # Try all device indices
        found_idx = None
        for idx in [0xFF, 1, 2, 3, 4, 5, 6]:
            # Build IRoot query for FEATURE_SET (0x0001)
            pkt = [0] * LONG_LEN
            pkt[0] = LONG_ID
            pkt[1] = idx
            pkt[2] = 0x00  # IRoot
            pkt[3] = MY_SW << 4  # func=0, sw=MY_SW
            pkt[4] = 0x00  # feature ID high
            pkt[5] = 0x01  # feature ID low (FEATURE_SET)

            try:
                dev.write(bytes(pkt))
                log(f"  TX idx=0x{idx:02X}: {fmt_hex(pkt)}")
            except Exception as e:
                log(f"  TX idx=0x{idx:02X}: WRITE FAILED — {e}")
                continue

            # Read response (500ms timeout)
            deadline = time.time() + 0.5
            while time.time() < deadline:
                try:
                    raw = dev.read(64, timeout=100)
                except Exception:
                    raw = None
                if not raw or len(raw) < 4:
                    continue

                log(f"  RX:          {fmt_hex(raw[:20])}")

                # Check for HID++ error
                if raw[0] == SHORT_ID and len(raw) >= 7 and raw[2] == 0xFF:
                    err = raw[5] if len(raw) > 5 else 0
                    log(f"       → HID++ error 0x{err:02X} for idx=0x{idx:02X}")
                    break

                # Check for matching response
                if (raw[0] in (SHORT_ID, LONG_ID)
                        and raw[1] == idx
                        and raw[2] == 0x00
                        and (raw[3] >> 4) == (MY_SW & 0x0F)):
                    feat_idx = raw[4]
                    log(f"       → FEATURE_SET found at index 0x{feat_idx:02X}!")
                    found_idx = idx
                    break

                # Unrelated packet — keep reading
                log(f"       → (unrelated, keep reading...)")

            if found_idx is not None:
                break

        if found_idx is not None:
            log(f"  [SUCCESS] Device responds at index 0x{found_idx:02X}")
            log()

            # Try to read device name
            log(f"  Querying DEVICE_NAME (0x0005)...")
            name_idx = _probe_feature(dev, found_idx, 0x0005)
            if name_idx:
                name = _read_device_name(dev, found_idx, name_idx)
                log(f"  Device name: \"{name}\"")
            else:
                log(f"  DEVICE_NAME not found")

            # Try battery features
            for fid, fname in [(0x1004, "UNIFIED_BATTERY"),
                               (0x1000, "BATTERY_LEVEL_STATUS")]:
                bi = _probe_feature(dev, found_idx, fid)
                if bi:
                    log(f"  {fname} (0x{fid:04X}) at index 0x{bi:02X}")
                else:
                    log(f"  {fname} (0x{fid:04X}): not found")

            # Try SmartShift
            for fid, fname in [(0x2111, "SMART_SHIFT_ENHANCED"),
                               (0x2110, "SMART_SHIFT")]:
                si = _probe_feature(dev, found_idx, fid)
                if si:
                    log(f"  {fname} (0x{fid:04X}) at index 0x{si:02X}")
                    break
            else:
                log(f"  SMART_SHIFT: not found")

        else:
            log(f"  [FAIL] No responding device index (tried 0xFF, 1-6)")
            log(f"  → Device may be in deep sleep, or paired to different receiver")

        try:
            dev.close()
        except Exception:
            pass
        log()

    # ── Phase 4: Raw USB device tree ────────────────────────────
    log("=" * 70)
    log("  PHASE 4: USB Device Check")
    log("=" * 70)
    log()
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "path", "Win32_PnPEntity", "where",
             "DeviceID like '%VID_046D%'",
             "get", "Name,DeviceID,Status", "/format:csv"],
            capture_output=True, text=True, timeout=10
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n")
                 if l.strip() and "Node" not in l]
        if lines:
            for line in lines:
                log(f"  {line}")
        else:
            log("  No Logitech USB devices in PnP tree")
    except Exception as e:
        log(f"  USB check failed: {e}")

    log()
    log("=" * 70)
    log("  DIAGNOSTIC COMPLETE")
    log("=" * 70)
    log(f"Full log saved to: {LOG_PATH}")

    LOG_FILE.close()
    input("\nPress Enter to exit...")


def _probe_feature(dev, dev_idx, feature_id):
    """Send IRoot query for a feature ID, return feature index or None."""
    pkt = [0] * LONG_LEN
    pkt[0] = LONG_ID
    pkt[1] = dev_idx
    pkt[2] = 0x00  # IRoot
    pkt[3] = MY_SW << 4
    pkt[4] = (feature_id >> 8) & 0xFF
    pkt[5] = feature_id & 0xFF
    try:
        dev.write(bytes(pkt))
    except Exception:
        return None
    deadline = time.time() + 1.0
    while time.time() < deadline:
        try:
            raw = dev.read(64, timeout=100)
        except Exception:
            continue
        if not raw or len(raw) < 5:
            continue
        if (raw[0] in (SHORT_ID, LONG_ID)
                and raw[1] == dev_idx
                and raw[2] == 0x00
                and (raw[3] >> 4) == (MY_SW & 0x0F)):
            fi = raw[4]
            return fi if fi != 0 else None
    return None


def _read_device_name(dev, dev_idx, name_idx):
    """Read device name using DEVICE_NAME feature."""
    # func=0: getNameLength
    pkt = [0] * LONG_LEN
    pkt[0] = LONG_ID
    pkt[1] = dev_idx
    pkt[2] = name_idx
    pkt[3] = MY_SW << 4  # func=0
    try:
        dev.write(bytes(pkt))
    except Exception:
        return "(write failed)"
    name_len = 0
    deadline = time.time() + 1.0
    while time.time() < deadline:
        try:
            raw = dev.read(64, timeout=100)
        except Exception:
            continue
        if (raw and len(raw) >= 5
                and raw[1] == dev_idx
                and raw[2] == name_idx):
            name_len = raw[4]
            break
    if not name_len:
        return "(unknown)"

    # func=1: getName (may need multiple calls for long names)
    name = ""
    offset = 0
    while offset < name_len:
        pkt2 = [0] * LONG_LEN
        pkt2[0] = LONG_ID
        pkt2[1] = dev_idx
        pkt2[2] = name_idx
        pkt2[3] = (MY_SW << 4) | 0x01  # func=1
        pkt2[4] = offset
        try:
            dev.write(bytes(pkt2))
        except Exception:
            break
        deadline = time.time() + 1.0
        while time.time() < deadline:
            try:
                raw = dev.read(64, timeout=100)
            except Exception:
                continue
            if (raw and len(raw) >= 5
                    and raw[1] == dev_idx
                    and raw[2] == name_idx):
                chunk = bytes(raw[4:20]).split(b"\x00")[0].decode("ascii", errors="replace")
                name += chunk
                offset += len(chunk)
                break
        else:
            break
    return name


if __name__ == "__main__":
    main()
