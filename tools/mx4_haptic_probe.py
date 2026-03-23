"""
MX4 Haptic Probe Tool — SET_REPORT Edition v1.0
=================================================
Sends HID++ commands to MX Master 4 via USB SET_REPORT control transfers
(not interrupt OUT, which the Bolt receiver ignores for HID++ commands).

Uses Windows HidD_SetOutputReport() API via ctypes.

Usage: python mx4_haptic_probe.py
"""

import sys
import ctypes
import ctypes.wintypes as wt
import time

# ── Windows API Constants ──
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x01
FILE_SHARE_WRITE = 0x02
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wt.HANDLE(-1).value

# HID GUID
GUID_DEVINTERFACE_HID = ctypes.c_byte * 16
HID_GUID = (ctypes.c_ubyte * 16)()

# ── Load DLLs ──
hid_dll = ctypes.windll.hid
setupapi = ctypes.windll.setupapi
kernel32 = ctypes.windll.kernel32


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", ctypes.c_ulong),
        ("VendorID", ctypes.c_ushort),
        ("ProductID", ctypes.c_ushort),
        ("VersionNumber", ctypes.c_ushort),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("InterfaceClassGuid", GUID),
        ("Flags", ctypes.c_ulong),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", ctypes.c_ushort),
        ("UsagePage", ctypes.c_ushort),
        ("InputReportByteLength", ctypes.c_ushort),
        ("OutputReportByteLength", ctypes.c_ushort),
        ("FeatureReportByteLength", ctypes.c_ushort),
        ("Reserved", ctypes.c_ushort * 17),
        ("NumberLinkCollectionNodes", ctypes.c_ushort),
        ("NumberInputButtonCaps", ctypes.c_ushort),
        ("NumberInputValueCaps", ctypes.c_ushort),
        ("NumberInputDataIndices", ctypes.c_ushort),
        ("NumberOutputButtonCaps", ctypes.c_ushort),
        ("NumberOutputValueCaps", ctypes.c_ushort),
        ("NumberOutputDataIndices", ctypes.c_ushort),
        ("NumberFeatureButtonCaps", ctypes.c_ushort),
        ("NumberFeatureValueCaps", ctypes.c_ushort),
        ("NumberFeatureDataIndices", ctypes.c_ushort),
    ]


def get_hid_guid():
    guid = GUID()
    hid_dll.HidD_GetHidGuid(ctypes.byref(guid))
    return guid


def find_bolt_hidpp_path():
    """Find the Bolt receiver's HID++ interface (MI_02, usage_page=0xFF00)."""
    guid = get_hid_guid()

    DIGCF_PRESENT = 0x02
    DIGCF_DEVICEINTERFACE = 0x10
    dev_info = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if dev_info == INVALID_HANDLE_VALUE:
        print("[ERROR] SetupDiGetClassDevs failed")
        return None

    candidates = []
    index = 0
    while True:
        iface_data = SP_DEVICE_INTERFACE_DATA()
        iface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
        if not setupapi.SetupDiEnumDeviceInterfaces(
            dev_info, None, ctypes.byref(guid), index, ctypes.byref(iface_data)
        ):
            break
        index += 1

        # Get required size
        required_size = ctypes.c_ulong(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(
            dev_info, ctypes.byref(iface_data), None, 0, ctypes.byref(required_size), None
        )

        # Allocate and get detail
        class SP_DEVICE_INTERFACE_DETAIL_DATA(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("DevicePath", ctypes.c_wchar * (required_size.value // 2)),
            ]

        detail = SP_DEVICE_INTERFACE_DETAIL_DATA()
        detail.cbSize = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
        if not setupapi.SetupDiGetDeviceInterfaceDetailW(
            dev_info,
            ctypes.byref(iface_data),
            ctypes.byref(detail),
            required_size,
            None,
            None,
        ):
            continue

        path = detail.DevicePath
        # Filter for Bolt receiver VID/PID
        if "vid_046d" in path.lower() and "pid_c548" in path.lower():
            # Open to check usage page
            handle = kernel32.CreateFileW(
                path,
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
            if handle == INVALID_HANDLE_VALUE:
                continue

            # Check VID/PID
            attrs = HIDD_ATTRIBUTES()
            attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
            hid_dll.HidD_GetAttributes(handle, ctypes.byref(attrs))

            # Get usage page (wrapped in try/except for robustness)
            caps = HIDP_CAPS()
            try:
                preparsed = ctypes.c_void_p(0)
                ret = hid_dll.HidD_GetPreparsedData(handle, ctypes.byref(preparsed))
                if ret and preparsed.value and preparsed.value != 0:
                    hid_dll.HidP_GetCaps(preparsed, ctypes.byref(caps))
                    hid_dll.HidD_FreePreparsedData(preparsed)
            except OSError:
                pass  # skip this interface
            kernel32.CloseHandle(handle)

            info = {
                "path": path,
                "vid": attrs.VendorID,
                "pid": attrs.ProductID,
                "usage_page": caps.UsagePage,
                "usage": caps.Usage,
                "output_len": caps.OutputReportByteLength,
            }
            candidates.append(info)
            tag = ""
            if caps.UsagePage == 0xFF00 and caps.Usage == 0x0002:
                tag = " ◀◀◀ HID++ TARGET"
            print(
                f"  Found: VID={attrs.VendorID:04X} PID={attrs.ProductID:04X} "
                f"usage_page=0x{caps.UsagePage:04X} usage=0x{caps.Usage:04X} "
                f"output_len={caps.OutputReportByteLength}{tag}"
            )

    setupapi.SetupDiDestroyDeviceInfoList(dev_info)

    # Find BOTH HID++ interfaces (short=usage 0x0001, long=usage 0x0002)
    short_iface = None  # report_id 0x10, 7 bytes
    long_iface = None   # report_id 0x11, 20 bytes
    for c in candidates:
        if c["usage_page"] == 0xFF00 and c["usage"] == 0x0001 and c["output_len"] == 7:
            short_iface = c
        elif c["usage_page"] == 0xFF00 and c["usage"] == 0x0002 and c["output_len"] == 20:
            long_iface = c

    if short_iface:
        print(f"\n  SHORT report handle (0x10): output_len={short_iface['output_len']}")
    if long_iface:
        print(f"  LONG  report handle (0x11): output_len={long_iface['output_len']}")

    if not short_iface and not long_iface:
        print("[ERROR] Could not find Bolt HID++ interface")
        return None

    return {"short": short_iface, "long": long_iface}


class BoltHIDPP:
    """Send HID++ commands via SET_REPORT OUTPUT to Bolt receiver."""

    def __init__(self, interfaces):
        self.short_info = interfaces.get("short")
        self.long_info = interfaces.get("long")
        self.short_handle = None
        self.long_handle = None

    def open(self):
        if self.short_info:
            self.short_handle = kernel32.CreateFileW(
                self.short_info["path"],
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, 0, None,
            )
            if self.short_handle == INVALID_HANDLE_VALUE:
                print(f"[ERROR] Failed to open SHORT handle (error {ctypes.get_last_error()})")
                self.short_handle = None
            else:
                print(f"[OK] Opened SHORT report handle (0x10, 7 bytes)")

        if self.long_info:
            self.long_handle = kernel32.CreateFileW(
                self.long_info["path"],
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, 0, None,
            )
            if self.long_handle == INVALID_HANDLE_VALUE:
                print(f"[ERROR] Failed to open LONG handle (error {ctypes.get_last_error()})")
                self.long_handle = None
            else:
                print(f"[OK] Opened LONG report handle (0x11, 20 bytes)")

        return self.short_handle is not None or self.long_handle is not None

    def close(self):
        if self.short_handle:
            kernel32.CloseHandle(self.short_handle)
        if self.long_handle:
            kernel32.CloseHandle(self.long_handle)

    def send_short(self, device_idx, feature_idx, func_sw, *params):
        """Send a short HID++ report (report_id=0x10, 7 bytes)."""
        if not self.short_handle:
            print("  [ERROR] No SHORT handle available")
            return False
        p = list(params) + [0, 0, 0]
        buf = (ctypes.c_ubyte * 7)()
        buf[0] = 0x10
        buf[1] = device_idx
        buf[2] = feature_idx
        buf[3] = func_sw
        buf[4] = p[0]
        buf[5] = p[1]
        buf[6] = p[2]

        raw = " ".join(f"{buf[i]:02X}" for i in range(7))
        result = hid_dll.HidD_SetOutputReport(self.short_handle, buf, 7)
        if result:
            print(f"  [TX OK ] [{raw}]")
        else:
            err = ctypes.GetLastError()
            print(f"  [TX FAIL] [{raw}] error={err}")
        return bool(result)

    def send_long(self, device_idx, feature_idx, func_sw, *params):
        """Send a long HID++ report (report_id=0x11, 20 bytes)."""
        if not self.long_handle:
            print("  [ERROR] No LONG handle available")
            return False
        p = list(params) + [0] * 16
        buf = (ctypes.c_ubyte * 20)()
        buf[0] = 0x11
        buf[1] = device_idx
        buf[2] = feature_idx
        buf[3] = func_sw
        for i in range(min(16, len(p))):
            buf[4 + i] = p[i]

        raw = " ".join(f"{buf[i]:02X}" for i in range(20))
        result = hid_dll.HidD_SetOutputReport(self.long_handle, buf, 20)
        if result:
            print(f"  [TX OK ] [{raw}]")
        else:
            err = ctypes.GetLastError()
            print(f"  [TX FAIL] [{raw}] error={err}")
        return bool(result)

    # ── Haptic commands (feature 0x0B, device 0x02) ──

    def haptic_set_config(self, enabled, intensity):
        """Set haptic config: enabled=True/False, intensity=0-100."""
        mode = 0x01 if enabled else 0x00
        # func=2, sw=10 → byte3 = 0x2A
        print(f"  Haptic config: {'ON' if enabled else 'OFF'}, intensity={intensity}%")
        return self.send_short(0x02, 0x0B, 0x2A, mode, intensity, 0x00)

    def haptic_trigger(self, pulse_type):
        """Trigger haptic pulse: 0x00=silent, 0x02=light, 0x04=tick, 0x08=strong."""
        names = {0x00: "silent/reset", 0x02: "light", 0x04: "tick", 0x08: "strong"}
        name = names.get(pulse_type, f"0x{pulse_type:02X}")
        print(f"  Haptic trigger: {name}")
        # func=4, sw=10 → byte3 = 0x4A
        return self.send_short(0x02, 0x0B, 0x4A, pulse_type, 0x00, 0x00)

    # ── Sensitivity commands (feature 0x0C, device 0x02) ──

    def set_sensitivity(self, setting):
        """Set button press sensitivity: 'light', 'medium', 'hard', 'firm'."""
        presets = {
            "light":  (0x0F, 0x3E, 0x26, 0x1B),
            "medium": (0x13, 0x0E, 0x2F, 0xA3),
            "hard":   (0x16, 0xDE, 0x39, 0x2B),
            "firm":   (0x19, 0x58, 0x3F, 0x5C),
        }
        if setting not in presets:
            print(f"  [ERROR] Unknown setting: {setting}")
            return False
        hi, lo, ex_hi, ex_lo = presets[setting]
        print(f"  Sensitivity: {setting} (val={hi << 8 | lo})")
        # func=3, sw=10 → byte3 = 0x3A, long report
        return self.send_long(0x02, 0x0C, 0x3A, 0x00, hi, lo, ex_hi, ex_lo, 0x00)


def main():
    print("=" * 60)
    print("  MX4 Haptic Probe — SET_REPORT Edition")
    print("=" * 60)
    print()

    # Step 1: Find the device
    print("[1] Searching for Bolt receiver HID++ interface...")
    info = find_bolt_hidpp_path()
    if not info:
        print("\nFailed to find device. Is the Bolt receiver plugged in?")
        input("Press Enter to exit...")
        sys.exit(1)

    print(f"\n[2] Found interfaces")

    # Step 2: Open
    dev = BoltHIDPP(info)
    print("\n[3] Opening device handles...")
    if not dev.open():
        print("Failed to open any handle. Is Options+ still running?")
        input("Press Enter to exit...")
        sys.exit(1)

    # Step 3: Interactive menu
    print("\n" + "=" * 60)
    print("  READY — Interactive Haptic Probe")
    print("=" * 60)

    menu = """
Commands:
  1  Enable haptics at 100% (High)
  2  Enable haptics at 60% (Medium)
  3  Enable haptics at 45% (Low)
  4  Enable haptics at 25% (Subtle)
  5  Disable haptics

  t  Trigger TICK pulse (0x04)
  l  Trigger LIGHT pulse (0x02)
  s  Trigger STRONG pulse (0x08)
  r  Trigger RESET pulse (0x00)
  b  Burst: 5 rapid ticks

  p1 Sensitivity: Light
  p2 Sensitivity: Medium
  p3 Sensitivity: Hard
  p4 Sensitivity: Firm

  raw XX XX XX XX XX XX XX  (send raw short report bytes)

  q  Quit
"""

    print(menu)
    while True:
        try:
            cmd = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if not cmd:
            continue
        elif cmd == "q":
            break
        elif cmd == "1":
            dev.haptic_set_config(True, 100)
        elif cmd == "2":
            dev.haptic_set_config(True, 60)
        elif cmd == "3":
            dev.haptic_set_config(True, 45)
        elif cmd == "4":
            dev.haptic_set_config(True, 25)
        elif cmd == "5":
            dev.haptic_set_config(False, 100)
        elif cmd == "t":
            dev.haptic_trigger(0x04)
        elif cmd == "l":
            dev.haptic_trigger(0x02)
        elif cmd == "s":
            dev.haptic_trigger(0x08)
        elif cmd == "r":
            dev.haptic_trigger(0x00)
        elif cmd == "b":
            print("  Burst: 5 ticks...")
            for i in range(5):
                dev.haptic_trigger(0x04)
                time.sleep(0.05)
        elif cmd == "p1":
            dev.set_sensitivity("light")
        elif cmd == "p2":
            dev.set_sensitivity("medium")
        elif cmd == "p3":
            dev.set_sensitivity("hard")
        elif cmd == "p4":
            dev.set_sensitivity("firm")
        elif cmd.startswith("raw "):
            try:
                hexbytes = [int(x, 16) for x in cmd[4:].split()]
                while len(hexbytes) < 7:
                    hexbytes.append(0)
                dev.send_short(hexbytes[1], hexbytes[2], hexbytes[3],
                              hexbytes[4], hexbytes[5], hexbytes[6])
            except (ValueError, IndexError) as e:
                print(f"  [ERROR] Bad hex: {e}")
        else:
            print("  Unknown command. Type 'q' to quit.")
            print(menu)

    dev.close()
    print("Done.")


if __name__ == "__main__":
    main()
