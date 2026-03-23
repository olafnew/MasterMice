"""
SmartShift & Scroll Wheel Interactive Debug Tool v1.1
=====================================================
Standalone tool — no threads, exclusive HID access.
Tests SmartShift SET/GET protocol and HiRes wheel control
with raw hex output for every HID++ exchange.

Run:  python tools/smartshift_test.py
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
LONG_ID  = 0x11
LONG_LEN = 20
MY_SW    = 0x0A

FEAT_SMART_SHIFT  = 0x2110
FEAT_SMART_SHIFT2 = 0x2111
FEAT_HIRES_WHEEL  = 0x2121
FEAT_HIRES_WHEEL2 = 0x2250

# ── Log file ─────────────────────────────────────────────────
LOG_FILE = None

def log(msg):
    print(msg)
    if LOG_FILE:
        LOG_FILE.write(msg + "\n")
        LOG_FILE.flush()

def hexdump(data, max_bytes=20):
    if not data:
        return "(empty)"
    return " ".join(f"{b:02X}" for b in data[:max_bytes])


# ── HID++ I/O ────────────────────────────────────────────────

def parse(raw):
    if not raw or len(raw) < 4:
        return None
    off = 1 if raw[0] in (0x10, 0x11) else 0
    if off + 3 > len(raw):
        return None
    dev  = raw[off]
    feat = raw[off + 1]
    fsw  = raw[off + 2]
    func = (fsw >> 4) & 0x0F
    sw   = fsw & 0x0F
    params = raw[off + 3:]
    return dev, feat, func, sw, params


def tx(dev, dev_idx, feat, func, params):
    buf = [0] * LONG_LEN
    buf[0] = LONG_ID
    buf[1] = dev_idx
    buf[2] = feat
    buf[3] = ((func & 0x0F) << 4) | (MY_SW & 0x0F)
    for i, b in enumerate(params):
        if 4 + i < LONG_LEN:
            buf[4 + i] = b & 0xFF
    log(f"  TX: [{hexdump(buf)}]")
    dev.write(buf)


def rx(dev, timeout_ms=2000):
    raw = dev.read(64, timeout_ms)
    if raw:
        data = list(raw)
        log(f"  RX: [{hexdump(data)}]")
        return data
    return None


def request(dev, dev_idx, feat, func, params, timeout_ms=2000):
    tx(dev, dev_idx, feat, func, params)
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        raw = rx(dev, min(500, timeout_ms))
        if raw is None:
            continue
        msg = parse(raw)
        if msg is None:
            continue
        _, r_feat, r_func, r_sw, r_params = msg
        # HID++ error
        if r_feat == 0xFF:
            code = r_params[1] if len(r_params) > 1 else 0
            log(f"  ERROR: HID++ error 0x{code:02X}")
            return None
        if r_feat == feat and r_sw == MY_SW:
            return msg
        # Log unexpected messages
        log(f"  (unexpected: feat=0x{r_feat:02X} func={r_func} sw=0x{r_sw:X})")
    log("  TIMEOUT: no matching response")
    return None


def find_feature(dev, dev_idx, feature_id):
    hi = (feature_id >> 8) & 0xFF
    lo = feature_id & 0xFF
    resp = request(dev, dev_idx, 0x00, 0, [hi, lo, 0x00])
    if resp:
        _, _, _, _, p = resp
        if p and p[0] != 0:
            return p[0]
    return None


# ── Connect ──────────────────────────────────────────────────

def connect():
    log("Scanning for Logitech HID++ devices...")
    infos = []
    for info in _hid.enumerate(LOGI_VID, 0):
        if info.get("usage_page", 0) >= 0xFF00:
            infos.append(info)
            pid = info.get("product_id", 0)
            up  = info.get("usage_page", 0)
            product = info.get("product_string", "")
            log(f"  PID=0x{pid:04X}  UP=0x{up:04X}  \"{product}\"")

    if not infos:
        log("No Logitech HID++ devices found!")
        return None, None

    for info in infos:
        pid = info.get("product_id", 0)
        try:
            d = _hid.device()
            d.open_path(info["path"])
            d.set_nonblocking(False)
        except Exception as e:
            log(f"  Can't open PID=0x{pid:04X}: {e}")
            continue

        for idx in (0xFF, 1, 2, 3, 4, 5, 6):
            log(f"  Probing devIdx=0x{idx:02X}...")
            resp = request(d, idx, 0x00, 0, [0x00, 0x01, 0x00], timeout_ms=1500)
            if resp:
                _, _, _, _, p = resp
                if p and p[0] != 0:
                    log(f"  Connected! PID=0x{pid:04X} devIdx=0x{idx:02X}")
                    return d, idx

        try:
            d.close()
        except Exception:
            pass

    log("No responding device found!")
    return None, None


# ── SmartShift tests ─────────────────────────────────────────

def test_smartshift(dev, dev_idx):
    log("\n" + "=" * 60)
    log("  SMARTSHIFT DEBUG")
    log("=" * 60)

    # Discover
    log("\n[1] Discovering SmartShift feature...")
    ss_idx = find_feature(dev, dev_idx, FEAT_SMART_SHIFT)
    ss_ver = 1
    if ss_idx:
        log(f"    Found SMART_SHIFT (0x2110) at index 0x{ss_idx:02X}")
    else:
        ss_idx = find_feature(dev, dev_idx, FEAT_SMART_SHIFT2)
        if ss_idx:
            ss_ver = 2
            log(f"    Found SMART_SHIFT_ENHANCED (0x2111) at index 0x{ss_idx:02X}")
        else:
            log("    SmartShift NOT FOUND on this device!")
            return

    # Read current state
    log(f"\n[2] Reading current state (func=0)...")
    resp = request(dev, dev_idx, ss_idx, 0, [])
    if resp:
        _, _, _, _, p = resp
        log(f"    Raw params: [{hexdump(p)}]")
        log(f"    mode={p[0]}  threshold={p[1]}  byte2={p[2]}")
        if p[1] == 0xFF:
            log("    → SmartShift is DISABLED (threshold=0xFF)")
        else:
            log(f"    → SmartShift ENABLED, threshold={p[1]}")
    else:
        log("    READ FAILED!")

    if ss_ver == 2:
        log(f"\n[2b] Reading via func=1 (MX4 enhanced)...")
        resp = request(dev, dev_idx, ss_idx, 1, [])
        if resp:
            _, _, _, _, p = resp
            log(f"    Raw params: [{hexdump(p)}]")
            log(f"    mode={p[0]}  threshold={p[1]}  force={p[2]}")

    # Interactive SET tests
    log("\n" + "-" * 60)
    log("  INTERACTIVE SET TESTS")
    log("  After each SET, scroll the wheel to check if behavior changed.")
    log("  Press Enter to proceed, 'q' to skip to next section.")
    log("-" * 60)

    # Test all candidate SET approaches
    tests = []
    if ss_ver == 1:
        tests = [
            ("func=1, params=[threshold=50]",           1, [50]),
            ("func=1, params=[threshold=4]",            1, [4]),
            ("func=1, params=[threshold=0xFF] (disable)", 1, [0xFF]),
            ("func=1, params=[threshold=10] (re-enable)", 1, [10]),
            ("func=0, params=[mode=1, threshold=50, auto=10]", 0, [1, 50, 10]),
            ("func=0, params=[mode=2, threshold=4, auto=10]",  0, [2, 4, 10]),
            ("func=0, params=[mode=1, threshold=0xFF, auto=10] (disable)", 0, [1, 0xFF, 10]),
            ("func=0, params=[mode=1, threshold=10, auto=10] (re-enable)", 0, [1, 10, 10]),
        ]
    else:
        tests = [
            ("func=2, params=[0x02, threshold=50, force=75]",  2, [0x02, 50, 75]),
            ("func=2, params=[0x02, threshold=4, force=75]",   2, [0x02, 4, 75]),
            ("func=2, params=[0x02, threshold=0xFF, force=75] (disable)", 2, [0x02, 0xFF, 75]),
            ("func=2, params=[0x02, threshold=13, force=75] (re-enable)", 2, [0x02, 13, 75]),
        ]

    for desc, func, params in tests:
        log(f"\n  TEST: {desc}")
        choice = input("  Press Enter to send, 's' to skip, 'q' to quit tests: ").strip().lower()
        if choice == 'q':
            break
        if choice == 's':
            continue

        log(f"  Sending SET: feat=0x{ss_idx:02X} func={func} params={params}")
        resp = request(dev, dev_idx, ss_idx, func, params)
        if resp:
            _, _, r_func, _, p = resp
            log(f"    Response func={r_func} params: [{hexdump(p)}]")
        else:
            log("    SET FAILED (timeout or error)")

        # Read back
        log("  Reading back state (func=0)...")
        resp = request(dev, dev_idx, ss_idx, 0, [])
        if resp:
            _, _, _, _, p = resp
            log(f"    State: mode={p[0]}  threshold={p[1]}  byte2={p[2]}")
        else:
            log("    Read-back FAILED")

        input("  >>> Scroll the wheel now. Did behavior change? Press Enter to continue...")


# ── HiRes Wheel tests ────────────────────────────────────────

def test_hires(dev, dev_idx):
    log("\n" + "=" * 60)
    log("  HIRES WHEEL DEBUG")
    log("=" * 60)

    # Try 0x2250 first
    log("\n[1] Discovering HiRes Wheel features...")
    hr2_idx = find_feature(dev, dev_idx, FEAT_HIRES_WHEEL2)
    if hr2_idx:
        log(f"    Found HIRES_WHEEL V2 (0x2250) at index 0x{hr2_idx:02X}")
        log("    Reading capabilities (func=0)...")
        resp = request(dev, dev_idx, hr2_idx, 0, [])
        if resp:
            _, _, _, _, p = resp
            log(f"    Raw: [{hexdump(p)}]")
            log(f"    multiplier={p[0]}  capabilities=0x{p[1]:02X}")

    hr_idx = find_feature(dev, dev_idx, FEAT_HIRES_WHEEL)
    if hr_idx:
        log(f"    Found HIRES_WHEEL (0x2121) at index 0x{hr_idx:02X}")
        log("    Reading capabilities (func=0)...")
        resp = request(dev, dev_idx, hr_idx, 0, [])
        if resp:
            _, _, _, _, p = resp
            log(f"    Raw: [{hexdump(p)}]")
            log(f"    multiplier={p[0]}  capabilities=0x{p[1]:02X}")
    else:
        log("    HIRES_WHEEL (0x2121) NOT FOUND")
        if not hr2_idx:
            log("    No HiRes wheel features found!")
            return
        hr_idx = hr2_idx  # use V2 for tests

    # Read current mode
    log(f"\n[2] Reading current HiRes mode (func=1) on 0x{hr_idx:02X}...")
    resp = request(dev, dev_idx, hr_idx, 1, [])
    if resp:
        _, _, _, _, p = resp
        log(f"    Raw: [{hexdump(p)}]")
        flags = p[0] if p else 0
        log(f"    target={bool(flags & 0x01)}  hires={bool(flags & 0x02)}  invert={bool(flags & 0x04)}")

    # Interactive SET
    log("\n" + "-" * 60)
    log("  INTERACTIVE HIRES TESTS")
    log("-" * 60)

    tests = [
        ("func=2, flags=0x02 (HiRes ON)",  2, [0x02]),
        ("func=2, flags=0x00 (HiRes OFF)", 2, [0x00]),
        ("func=2, flags=0x02 (HiRes ON again)", 2, [0x02]),
        ("func=2, flags=0x04 (Invert ON)", 2, [0x04]),
        ("func=2, flags=0x00 (all OFF)",   2, [0x00]),
    ]

    for desc, func, params in tests:
        log(f"\n  TEST: {desc}")
        choice = input("  Press Enter to send, 's' to skip, 'q' to quit tests: ").strip().lower()
        if choice == 'q':
            break
        if choice == 's':
            continue

        log(f"  Sending SET: feat=0x{hr_idx:02X} func={func} params={params}")
        resp = request(dev, dev_idx, hr_idx, func, params)
        if resp:
            _, _, r_func, _, p = resp
            log(f"    Response func={r_func} params: [{hexdump(p)}]")
        else:
            log("    SET FAILED (timeout or error)")

        # Read back
        log("  Reading back mode (func=1)...")
        resp = request(dev, dev_idx, hr_idx, 1, [])
        if resp:
            _, _, _, _, p = resp
            flags = p[0] if p else 0
            log(f"    target={bool(flags & 0x01)}  hires={bool(flags & 0x02)}  invert={bool(flags & 0x04)}")

        input("  >>> Scroll the wheel now. Did behavior change? Press Enter to continue...")


# ── Event listener ───────────────────────────────────────────

def listen_events(dev, dev_idx, ss_idx, hr_idx, duration=15):
    log(f"\n{'=' * 60}")
    log(f"  LISTENING FOR WHEEL EVENTS ({duration}s)")
    log(f"  Scroll wheel, press ratchet button, toggle modes...")
    log(f"{'=' * 60}")

    start = time.time()
    count = 0
    while time.time() - start < duration:
        raw = rx(dev, 500)
        if raw is None:
            continue
        msg = parse(raw)
        if msg is None:
            continue
        _, feat, func, sw, params = msg
        elapsed = time.time() - start

        label = ""
        if feat == ss_idx:
            label = f"SMARTSHIFT func={func}"
        elif feat == hr_idx:
            label = f"HIRES func={func}"
        elif feat == 0xFF:
            label = "ERROR"
        else:
            label = f"feat=0x{feat:02X} func={func}"

        log(f"  [{elapsed:5.1f}s] {label} sw=0x{sw:X} data=[{hexdump(params)}]")
        count += 1

    log(f"  Captured {count} events in {duration}s")


# ── Main ─────────────────────────────────────────────────────

def main():
    global LOG_FILE

    print("=" * 60)
    print("  SmartShift & Scroll Wheel Debug Tool")
    print("  MasterMice Project — standalone, no threads")
    print("=" * 60)
    print()

    # Open log file
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "smartshift_debug.log")
    log_path = os.path.normpath(log_path)
    try:
        LOG_FILE = open(log_path, "w", encoding="utf-8")
        print(f"Logging to: {log_path}")
    except Exception as e:
        print(f"Warning: can't open log file: {e}")

    log(f"Session start: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    dev, dev_idx = connect()
    if dev is None:
        input("Press Enter to exit...")
        return

    # Discover feature indices for event listener
    ss_idx = find_feature(dev, dev_idx, FEAT_SMART_SHIFT)
    if not ss_idx:
        ss_idx = find_feature(dev, dev_idx, FEAT_SMART_SHIFT2)
    hr_idx = find_feature(dev, dev_idx, FEAT_HIRES_WHEEL)
    if not hr_idx:
        hr_idx = find_feature(dev, dev_idx, FEAT_HIRES_WHEEL2)

    while True:
        log("\n" + "=" * 60)
        log("  MAIN MENU")
        log("=" * 60)
        log("  1. SmartShift tests")
        log("  2. HiRes Wheel tests")
        log("  3. Listen for wheel events (15s)")
        log("  4. Raw HID++ command (manual)")
        log("  5. Quit")
        choice = input("\n  Choice: ").strip()

        if choice == '1':
            test_smartshift(dev, dev_idx)
        elif choice == '2':
            test_hires(dev, dev_idx)
        elif choice == '3':
            listen_events(dev, dev_idx, ss_idx or 0, hr_idx or 0)
        elif choice == '4':
            raw_command(dev, dev_idx)
        elif choice == '5':
            break
        else:
            log("Invalid choice")

    try:
        dev.close()
    except Exception:
        pass
    if LOG_FILE:
        LOG_FILE.close()
    log("Done.")


def raw_command(dev, dev_idx):
    log("\n  RAW HID++ COMMAND")
    log("  Enter: feat_index func param0 param1 ... (hex, space-separated)")
    log("  Example: 0D 1 0A   (feat=0x0D func=1 param=0x0A)")
    cmd = input("  > ").strip()
    if not cmd:
        return
    try:
        parts = cmd.split()
        feat = int(parts[0], 16)
        func = int(parts[1], 16) if len(parts) > 1 else 0
        params = [int(p, 16) for p in parts[2:]]
        log(f"  Sending: feat=0x{feat:02X} func={func} params={params}")
        resp = request(dev, dev_idx, feat, func, params)
        if resp:
            _, _, r_func, _, p = resp
            log(f"  Response: func={r_func} params=[{hexdump(p)}]")
        else:
            log("  No response (timeout or error)")
    except Exception as e:
        log(f"  Parse error: {e}")


if __name__ == "__main__":
    main()
