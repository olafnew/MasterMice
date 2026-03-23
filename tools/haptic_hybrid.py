"""
Haptic Hybrid Test v1.0
Uses hidapi for device FINDING (works in PyInstaller).
Uses ctypes CreateFileW + HidD_SetOutputReport for SENDING (correct USB pipe).
"""
import sys, os, time, ctypes
import ctypes.wintypes as wt

try:
    import hid as _hid
except ImportError:
    print("ERROR: pip install hidapi"); sys.exit(1)

VERSION = "1.0"
LOGI_VID = 0x046D

kernel32 = ctypes.windll.kernel32
hid_dll = ctypes.windll.hid

GENERIC_RW = 0x80000000 | 0x40000000
SHARE_RW = 0x01 | 0x02
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wt.HANDLE(-1).value


def find_paths():
    """Use hidapi enumerate to find SHORT and LONG HID++ paths."""
    short_path = None
    long_path = None

    for info in _hid.enumerate(LOGI_VID, 0):
        up = info.get("usage_page", 0)
        usage = info.get("usage", 0)
        path = info.get("path", b"")
        pid = info.get("product_id", 0)

        if up != 0xFF00:
            continue

        # Decode path for display
        path_str = path.decode("utf-8", "replace") if isinstance(path, bytes) else str(path)

        if usage == 0x0001:
            short_path = path_str
            print(f"  SHORT: PID=0x{pid:04X} Usage=0x{usage:04X} path={path_str[:80]}")
        elif usage == 0x0002:
            long_path = path_str
            print(f"  LONG:  PID=0x{pid:04X} Usage=0x{usage:04X} path={path_str[:80]}")

    return short_path, long_path


def open_handle(path_str):
    """Open a Windows file handle for HidD_SetOutputReport."""
    h = kernel32.CreateFileW(
        path_str, GENERIC_RW, SHARE_RW, None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE:
        print(f"  CreateFileW FAILED: err={ctypes.GetLastError()}")
        return None
    return h


def send_short(handle, report_7bytes):
    """Send 7-byte short report via HidD_SetOutputReport."""
    buf = (ctypes.c_ubyte * 7)(*report_7bytes)
    raw = " ".join(f"{b:02X}" for b in report_7bytes)
    ok = hid_dll.HidD_SetOutputReport(handle, buf, 7)
    print(f"  [{raw}] {'OK' if ok else f'FAIL err={ctypes.GetLastError()}'}")
    return bool(ok)


def send_long(handle, report_20bytes):
    """Send 20-byte long report via HidD_SetOutputReport."""
    while len(report_20bytes) < 20:
        report_20bytes.append(0)
    buf = (ctypes.c_ubyte * 20)(*report_20bytes[:20])
    raw = " ".join(f"{b:02X}" for b in report_20bytes[:10]) + " ..."
    ok = hid_dll.HidD_SetOutputReport(handle, buf, 20)
    print(f"  [{raw}] {'OK' if ok else f'FAIL err={ctypes.GetLastError()}'}")
    return bool(ok)


def main():
    print(f"{'='*60}")
    print(f"  Haptic Hybrid Test v{VERSION}")
    print(f"  hidapi for finding + ctypes for sending")
    print(f"{'='*60}\n")

    print("Finding HID++ interfaces via hidapi...")
    short_path, long_path = find_paths()

    if not short_path:
        print("\nERROR: SHORT interface (Usage=0x0001) not found.")
        print("Is the Bolt receiver plugged in?")
        input("Press Enter to exit...")
        return

    print(f"\nOpening SHORT handle via CreateFileW...")
    short_h = open_handle(short_path)
    if not short_h:
        print("ERROR: Cannot open SHORT handle.")
        input("Press Enter to exit...")
        return
    print("SHORT handle: OK")

    long_h = None
    if long_path:
        print(f"Opening LONG handle via CreateFileW...")
        long_h = open_handle(long_path)
        print(f"LONG handle: {'OK' if long_h else 'FAILED (non-critical)'}")

    DEV = 0x02
    HAP = 0x0B

    print(f"\n{'='*60}")
    print(f"  AUTO TEST — hold mouse lightly!")
    print(f"{'='*60}")
    time.sleep(2)

    # 1. Enable
    print(f"\n[1/10] Enable haptics at 100%")
    send_short(short_h, [0x10, DEV, HAP, 0x2A, 0x01, 0x64, 0x00])
    time.sleep(1)

    # 2. Tick
    print(f"\n[2/10] TICK pulse")
    send_short(short_h, [0x10, DEV, HAP, 0x4A, 0x04, 0x00, 0x00])
    time.sleep(1.5)

    # 3. Strong
    print(f"\n[3/10] STRONG pulse")
    send_short(short_h, [0x10, DEV, HAP, 0x4A, 0x08, 0x00, 0x00])
    time.sleep(1.5)

    # 4. Light
    print(f"\n[4/10] LIGHT pulse")
    send_short(short_h, [0x10, DEV, HAP, 0x4A, 0x02, 0x00, 0x00])
    time.sleep(1.5)

    # 5. Triple tick
    print(f"\n[5/10] Triple tick")
    for i in range(3):
        send_short(short_h, [0x10, DEV, HAP, 0x4A, 0x04, 0x00, 0x00])
        time.sleep(0.3)
    time.sleep(1)

    # 6. Burst
    print(f"\n[6/10] Rapid burst (10 ticks)")
    for i in range(10):
        send_short(short_h, [0x10, DEV, HAP, 0x4A, 0x04, 0x00, 0x00])
        time.sleep(0.05)
    time.sleep(1.5)

    # 7-9. Intensity
    for val, name, n in [(0x19,"25% Subtle",7), (0x3C,"60% Medium",8), (0x64,"100% High",9)]:
        print(f"\n[{n}/10] Intensity: {name} + strong pulse")
        send_short(short_h, [0x10, DEV, HAP, 0x2A, 0x01, val, 0x00])
        time.sleep(0.3)
        send_short(short_h, [0x10, DEV, HAP, 0x4A, 0x08, 0x00, 0x00])
        time.sleep(1.5)

    # 10. Sensitivity
    if long_h:
        print(f"\n[10/10] Button sensitivity: Light -> Firm -> Medium")
        send_long(long_h, [0x11, DEV, 0x0C, 0x3A, 0x00, 0x0F, 0x3E, 0x26, 0x1B, 0x00])
        time.sleep(1)
        send_long(long_h, [0x11, DEV, 0x0C, 0x3A, 0x00, 0x19, 0x58, 0x3F, 0x5C, 0x00])
        time.sleep(1)
        send_long(long_h, [0x11, DEV, 0x0C, 0x3A, 0x00, 0x13, 0x0E, 0x2F, 0xA3, 0x00])
        time.sleep(1)
    else:
        print(f"\n[10/10] Skipped (no LONG handle)")

    # Cleanup
    print(f"\nDisabling haptics...")
    send_short(short_h, [0x10, DEV, HAP, 0x2A, 0x00, 0x64, 0x00])

    print(f"\n{'='*60}")
    print(f"  TEST COMPLETE")
    print(f"  Did you feel vibrations during steps 2-9?")
    print(f"{'='*60}")

    kernel32.CloseHandle(short_h)
    if long_h:
        kernel32.CloseHandle(long_h)
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
