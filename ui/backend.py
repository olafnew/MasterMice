"""
QML Backend Bridge — connects the QML UI to the engine and config.
Exposes properties, signals, and slots for two-way data binding.
"""

import os
import subprocess
import sys

from PySide6.QtCore import QObject, Property, Signal, Slot, Qt

from core.config import (
    APP_VERSION, BUTTON_NAMES, DEVICE_PROFILES, load_config, save_config,
    get_active_mappings, get_device_buttons, get_device_name,
    set_mapping, create_profile, delete_profile, KNOWN_APPS, get_icon_for_exe,
)
from core.key_simulator import ACTIONS


def _action_label(action_id):
    return ACTIONS.get(action_id, {}).get("label", "Do Nothing")


class Backend(QObject):
    """QML-exposed backend that bridges the engine and configuration."""

    # ── Signals ────────────────────────────────────────────────
    mappingsChanged = Signal()
    settingsChanged = Signal()
    profilesChanged = Signal()
    activeProfileChanged = Signal()
    statusMessage = Signal(str)
    dpiFromDevice = Signal(int)
    mouseConnectedChanged = Signal()

    # Internal cross-thread signals
    _profileSwitchRequest = Signal(str)
    _dpiReadRequest = Signal(int)
    _connectionChangeRequest = Signal(bool)
    _batteryUpdateRequest = Signal(int, bool)
    _deviceDetectedRequest = Signal(str, str)

    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._cfg = load_config()
        self._mouse_connected = False
        self._battery_level = -1
        self._battery_charging = False

        # Cross-thread signal connections
        self._profileSwitchRequest.connect(
            self._handleProfileSwitch, Qt.QueuedConnection)
        self._dpiReadRequest.connect(
            self._handleDpiRead, Qt.QueuedConnection)
        self._connectionChangeRequest.connect(
            self._handleConnectionChange, Qt.QueuedConnection)
        self._batteryUpdateRequest.connect(
            self._handleBatteryUpdate, Qt.QueuedConnection)
        self._deviceDetectedRequest.connect(
            self._handleDeviceDetected, Qt.QueuedConnection)

        # Wire engine callbacks
        if engine:
            engine.set_profile_change_callback(self._onEngineProfileSwitch)
            engine.set_dpi_read_callback(self._onEngineDpiRead)
            engine.set_connection_change_callback(self._onEngineConnectionChange)
            engine.set_battery_callback(self._onEngineBatteryRead)
            engine.set_device_detected_callback(self._onEngineDeviceDetected)

    @Slot(result=str)
    def checkLogiSoftware(self):
        """Check if Logitech software is running that blocks HID++ access.
        Returns warning message or empty string."""
        import subprocess
        LOGI_PROCS = [
            "logioptionsplus_agent.exe", "logioptionsplus.exe",
            "logioptions.exe", "LogiAppBroker.exe", "SetPoint.exe",
            "SetPointP.exe", "LogiMgr.exe",
        ]
        found = []
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5)
            running = result.stdout.lower()
            for proc in LOGI_PROCS:
                if proc.lower() in running:
                    found.append(proc)
        except Exception:
            pass
        if found:
            names = ", ".join(found)
            return (f"Logitech software detected: {names}\n"
                    "These may block MasterMice from accessing the mouse.\n"
                    "Close them or uninstall for full functionality.")
        return ""

    # ── Properties ─────────────────────────────────────────────

    @Property(list, notify=mappingsChanged)
    def buttons(self):
        """List of button dicts for the active profile, filtered by device."""
        mappings = get_active_mappings(self._cfg)
        device_buttons = get_device_buttons(self._cfg)
        result = []
        for i, key in enumerate(device_buttons):
            name = BUTTON_NAMES.get(key, key)
            aid = mappings.get(key, "none")
            result.append({
                "key": key,
                "name": name,
                "actionId": aid,
                "actionLabel": _action_label(aid),
                "index": i + 1,
            })
        return result

    @Property(list, constant=True)
    def actionCategories(self):
        """Actions grouped by category — for the action picker chips."""
        from collections import OrderedDict
        cats = OrderedDict()
        for aid in sorted(
            ACTIONS,
            key=lambda a: (
                "0" if ACTIONS[a]["category"] == "Other" else "1" + ACTIONS[a]["category"],
                ACTIONS[a]["label"],
            ),
        ):
            data = ACTIONS[aid]
            cat = data["category"]
            cats.setdefault(cat, []).append({"id": aid, "label": data["label"]})
        return [{"category": c, "actions": a} for c, a in cats.items()]

    @Property(list, constant=True)
    def allActions(self):
        """Flat sorted action list (Do Nothing first) — for ComboBoxes."""
        result = []
        none_data = ACTIONS.get("none")
        if none_data:
            result.append({"id": "none", "label": none_data["label"],
                           "category": "Other"})
        for aid in sorted(
            ACTIONS,
            key=lambda a: (ACTIONS[a]["category"], ACTIONS[a]["label"]),
        ):
            if aid == "none":
                continue
            data = ACTIONS[aid]
            result.append({"id": aid, "label": data["label"],
                           "category": data["category"]})
        return result

    @Property(int, notify=settingsChanged)
    def dpi(self):
        return self._cfg.get("settings", {}).get("dpi", 1000)

    @Property(int, notify=settingsChanged)
    def maxDpi(self):
        """Max DPI for the connected device (4000 for MX3, 8000 for MX4)."""
        model = self._cfg.get("settings", {}).get("mouse_model", "")
        return 8000 if model == "mx_master_4" else 4000

    @Property(int, notify=settingsChanged)
    def mouseSpeed(self):
        """Windows pointer speed (1-20, default 10)."""
        return self._get_windows_mouse_speed()

    @Slot(int)
    def setMouseSpeed(self, value):
        """Set Windows pointer speed via SPI_SETMOUSESPEED (1-20)."""
        import ctypes
        v = max(1, min(20, int(value)))
        SPI_SETMOUSESPEED = 0x0071
        ctypes.windll.user32.SystemParametersInfoW(SPI_SETMOUSESPEED, 0, v, 0)
        print(f"[Settings] Windows mouse speed → {v}")
        self.settingsChanged.emit()

    @staticmethod
    def _get_windows_mouse_speed():
        import ctypes
        speed = ctypes.c_int(0)
        SPI_GETMOUSESPEED = 0x0070
        ctypes.windll.user32.SystemParametersInfoW(SPI_GETMOUSESPEED, 0, ctypes.byref(speed), 0)
        return speed.value

    @Property(int, notify=settingsChanged)
    def scrollLines(self):
        """Windows scroll lines per notch (SPI_GETWHEELSCROLLLINES)."""
        import ctypes
        val = ctypes.c_uint(0)
        ctypes.windll.user32.SystemParametersInfoW(0x0068, 0, ctypes.byref(val), 0)
        return val.value

    @Slot(int)
    def setScrollLines(self, value):
        """Set Windows scroll lines per notch (SPI_SETWHEELSCROLLLINES)."""
        import ctypes
        v = max(1, min(20, int(value)))
        ctypes.windll.user32.SystemParametersInfoW(0x0069, v, 0, 0)
        print(f"[Settings] Windows scroll lines → {v}")
        self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def invertVScroll(self):
        return self._cfg.get("settings", {}).get("invert_vscroll", False)

    @Property(bool, notify=settingsChanged)
    def invertHScroll(self):
        return self._cfg.get("settings", {}).get("invert_hscroll", False)

    @Property(str, notify=settingsChanged)
    def mouseModel(self):
        return self._cfg.get("settings", {}).get("mouse_model", "")

    @Property(str, notify=settingsChanged)
    def mouseModelName(self):
        return get_device_name(self._cfg)

    @Property(bool, notify=settingsChanged)
    def debugMode(self):
        return self._cfg.get("settings", {}).get("debug_mode", False)

    @Property(int, notify=settingsChanged)
    def batteryLevel(self):
        return self._battery_level

    @Property(bool, notify=settingsChanged)
    def batteryCharging(self):
        return self._battery_charging

    @Property(str, notify=settingsChanged)
    def logLevel(self):
        return self._cfg.get("settings", {}).get("log_level", "errors")

    @Property(str, notify=settingsChanged)
    def logContent(self):
        from core.logger import get_log_content
        return get_log_content()

    @Property(str, constant=True)
    def logFilePath(self):
        from core.logger import get_log_path
        return get_log_path()

    @Property(str, constant=True)
    def appVersion(self):
        return APP_VERSION

    @Property(str, notify=activeProfileChanged)
    def activeProfile(self):
        return self._cfg.get("active_profile", "default")

    @Property(bool, notify=mouseConnectedChanged)
    def mouseConnected(self):
        return self._mouse_connected

    @Property(str, notify=mouseConnectedChanged)
    def connectionType(self):
        """Return 'unifying', 'bolt', 'bluetooth', or 'unknown'."""
        hg = self._engine.hook._hid_gesture if self._engine else None
        if not hg or not self._mouse_connected:
            return "unknown"
        dev_idx = getattr(hg, '_dev_idx', 0xFF)
        # Bluetooth direct uses index 0xFF
        if dev_idx == 0xFF:
            return "bluetooth"
        # Check receiver PID from the connected device info
        pid = getattr(hg, '_connected_pid', 0)
        if pid == 0xC548:
            return "bolt"
        elif pid in (0xC52B, 0xC534, 0xC539):
            return "unifying"
        return "unknown"

    @Property(list, notify=profilesChanged)
    def profiles(self):
        result = []
        active = self._cfg.get("active_profile", "default")
        for pname, pdata in self._cfg.get("profiles", {}).items():
            # Collect icons for all apps in this profile
            apps = pdata.get("apps", [])
            app_icons = [get_icon_for_exe(ex) for ex in apps]
            result.append({
                "name": pname,
                "label": pdata.get("label", pname),
                "apps": apps,
                "appIcons": app_icons,
                "isActive": pname == active,
            })
        return result

    @Property(list, constant=True)
    def knownApps(self):
        return [{"exe": ex, "label": info["label"], "icon": get_icon_for_exe(ex)}
                for ex, info in KNOWN_APPS.items()]

    # ── Slots ──────────────────────────────────────────────────

    @Slot(str, str)
    def setMapping(self, button, actionId):
        """Set a button mapping in the active profile."""
        self._cfg = set_mapping(self._cfg, button, actionId)
        if self._engine:
            self._engine.reload_mappings()
        self.mappingsChanged.emit()
        self.statusMessage.emit("Saved")

    @Slot(str, str, str)
    def setProfileMapping(self, profileName, button, actionId):
        """Set a button mapping in a specific profile."""
        self._cfg = set_mapping(self._cfg, button, actionId,
                                profile=profileName)
        if self._engine:
            self._engine.reload_mappings()
        self.profilesChanged.emit()
        self.mappingsChanged.emit()
        self.statusMessage.emit("Saved")

    @Slot(int)
    def setDpi(self, value):
        print(f"[Settings] DPI → {value}")
        self._cfg.setdefault("settings", {})["dpi"] = value
        save_config(self._cfg)
        if self._engine:
            self._engine.set_dpi(value)
        self.settingsChanged.emit()

    @Slot(bool)
    def setInvertVScroll(self, value):
        print(f"[Settings] Invert vertical scroll → {value}")
        self._cfg.setdefault("settings", {})["invert_vscroll"] = value
        save_config(self._cfg)
        if self._engine:
            self._engine.reload_mappings()
        self.settingsChanged.emit()

    @Slot(bool)
    def setInvertHScroll(self, value):
        print(f"[Settings] Invert horizontal scroll → {value}")
        self._cfg.setdefault("settings", {})["invert_hscroll"] = value
        save_config(self._cfg)
        if self._engine:
            self._engine.reload_mappings()
        self.settingsChanged.emit()

    @Slot(str)
    def setMouseModel(self, value):
        if value not in DEVICE_PROFILES:
            return
        print(f"[Settings] Mouse model → {value}")
        self._cfg.setdefault("settings", {})["mouse_model"] = value
        save_config(self._cfg)
        self.settingsChanged.emit()
        self.mappingsChanged.emit()  # button list changes per device

    @Slot(bool)
    def setDebugMode(self, value):
        print(f"[Settings] Debug mode → {value}")
        self._cfg.setdefault("settings", {})["debug_mode"] = bool(value)
        save_config(self._cfg)
        self.settingsChanged.emit()

    @Slot(result=int)
    def getSmartShiftThreshold(self):
        """Read SmartShift threshold from device. Returns 1-50 or -1."""
        if not self._engine:
            return -1
        hg = self._engine.hook._hid_gesture
        if hg and hasattr(hg, "get_smart_shift"):
            result = hg.get_smart_shift()
            if result:
                return result.get("threshold", -1)
        return -1

    @Slot(int)
    def setSmartShiftThreshold(self, value):
        if not self._engine:
            return
        hg = self._engine.hook._hid_gesture
        if hg and hasattr(hg, "set_smart_shift"):
            hg.set_smart_shift(value)
        self.settingsChanged.emit()

    @Slot(result=bool)
    def getHiResScroll(self):
        if not self._engine:
            return False
        hg = self._engine.hook._hid_gesture
        if hg and hasattr(hg, "get_hires_wheel"):
            result = hg.get_hires_wheel()
            if result:
                return result.get("hires", False)
        return False

    @Slot(result=bool)
    def hasHiResWheel(self):
        """True if the connected device supports the Hi-Res wheel feature."""
        if not self._engine:
            return False
        hg = self._engine.hook._hid_gesture
        if hg:
            return hg._hires_idx is not None
        return False

    @Slot(bool)
    def setHiResScroll(self, value):
        if not self._engine:
            return
        hg = self._engine.hook._hid_gesture
        if hg and hasattr(hg, "set_hires_wheel"):
            hg.set_hires_wheel(hires=value)
            # Update hook's scroll accumulator state
            mult = getattr(hg, '_hires_multiplier', 15)
            div = self._cfg.get("settings", {}).get("hires_scroll_divider", 15)
            self._engine.update_hires_scroll_state(value, mult, div)
        self.settingsChanged.emit()

    @Property(int, notify=settingsChanged)
    def hiResScrollDivider(self):
        return self._cfg.get("settings", {}).get("hires_scroll_divider", 15)

    @Slot(int)
    def setHiResScrollDivider(self, value):
        """Set HiRes scroll speed divider (1=fastest, 30=slowest, 15=normal)."""
        v = max(1, min(30, int(value)))
        self._cfg.setdefault("settings", {})["hires_scroll_divider"] = v
        save_config(self._cfg)
        print(f"[Settings] HiRes scroll divider → {v}")
        if self._engine:
            self._engine.hook.hires_divider = v
        self.settingsChanged.emit()

    # ── SmartShift v2 (threshold + force + on/off) ─────────────

    @Slot(result=bool)
    def hasSmartShift(self):
        """True if the connected device supports SmartShift."""
        if not self._engine:
            return False
        hg = self._engine.hook._hid_gesture
        return bool(hg and hg._smart_shift_idx is not None)

    @Slot(result=int)
    def getSmartShiftVersion(self):
        """Returns 1 (MX3) or 2 (MX4 enhanced with force control)."""
        if not self._engine:
            return 0
        hg = self._engine.hook._hid_gesture
        return hg._smart_shift_ver if hg else 0

    @Slot(result=bool)
    def getSmartShiftEnabled(self):
        if not self._engine:
            return True
        hg = self._engine.hook._hid_gesture
        if hg and hasattr(hg, "get_smart_shift"):
            result = hg.get_smart_shift()
            if result:
                return result.get("enabled", True)
        return True

    @Slot(bool)
    def setSmartShiftEnabled(self, value):
        if not self._engine:
            return
        hg = self._engine.hook._hid_gesture
        if hg and hasattr(hg, "set_smart_shift"):
            hg.set_smart_shift(threshold=None, enabled=value)
        self.settingsChanged.emit()

    @Slot(result=int)
    def getScrollForce(self):
        """Returns scroll force 1-100, or -1 if not supported."""
        if not self._engine:
            return -1
        hg = self._engine.hook._hid_gesture
        if hg and hasattr(hg, "get_smart_shift"):
            result = hg.get_smart_shift()
            if result:
                return result.get("force", -1)
        return -1

    @Slot(int)
    def setScrollForce(self, value):
        if not self._engine:
            return
        hg = self._engine.hook._hid_gesture
        if hg and hasattr(hg, "set_smart_shift"):
            hg.set_smart_shift(threshold=None, force=value)
        self.settingsChanged.emit()

    # ── Smooth Scrolling ───────────────────────────────────────

    @Slot(result=bool)
    def hasSmoothScrolling(self):
        if not self._engine:
            return False
        hg = self._engine.hook._hid_gesture
        return bool(hg and hg._scroll_ctrl_idx is not None)

    @Slot(result=bool)
    def getSmoothScrolling(self):
        if not self._engine:
            return False
        hg = self._engine.hook._hid_gesture
        if hg and hasattr(hg, "get_smooth_scroll"):
            result = hg.get_smooth_scroll()
            return result if result is not None else False
        return False

    @Slot(bool)
    def setSmoothScrolling(self, value):
        if not self._engine:
            return
        hg = self._engine.hook._hid_gesture
        if hg and hasattr(hg, "set_smooth_scroll"):
            hg.set_smooth_scroll(value)
        self.settingsChanged.emit()

    # ── Haptic Feedback (MX4) ──────────────────────────────────
    # Uses HidD_SetOutputReport on SHORT handle — not hidapi.write()

    @Slot(result=bool)
    def hasHapticFeedback(self):
        if not self._engine:
            return False
        hg = self._engine.hook._hid_gesture
        return bool(hg and hg._short_handle is not None)

    @Slot(result=bool)
    def getHapticEnabled(self):
        return self._cfg.get("settings", {}).get("haptic_enabled", True)

    @Slot(bool)
    def setHapticEnabled(self, value):
        if not self._engine:
            return
        self._cfg.setdefault("settings", {})["haptic_enabled"] = bool(value)
        save_config(self._cfg)
        hg = self._engine.hook._hid_gesture
        if hg:
            intensity = self._cfg.get("settings", {}).get("haptic_intensity", 60)
            hg.haptic_set_config(value, intensity)
        self.settingsChanged.emit()

    @Slot(result=int)
    def getHapticIntensity(self):
        return self._cfg.get("settings", {}).get("haptic_intensity", 60)

    @Slot(int)
    def setHapticIntensity(self, value):
        if not self._engine:
            return
        v = max(0, min(100, int(value)))
        self._cfg.setdefault("settings", {})["haptic_intensity"] = v
        save_config(self._cfg)
        hg = self._engine.hook._hid_gesture
        if hg:
            hg.haptic_set_config(True, v)
        self.settingsChanged.emit()

    @Slot()
    def testHaptic(self):
        """Send a strong haptic pulse for testing."""
        if not self._engine:
            return
        hg = self._engine.hook._hid_gesture
        if hg:
            hg.haptic_trigger(0x08)  # strong pulse
            print("[Settings] Haptic test pulse sent")

    @Property(int, notify=settingsChanged)
    def logMaxKb(self):
        return self._cfg.get("settings", {}).get("log_max_kb", 1024)

    @Slot(str)
    def setLogLevel(self, value):
        if value not in ("disabled", "errors", "verbose"):
            return
        print(f"[Settings] Log level → {value}")
        self._cfg.setdefault("settings", {})["log_level"] = value
        save_config(self._cfg)
        from core.logger import setup
        max_kb = self._cfg.get("settings", {}).get("log_max_kb", 1024)
        setup(value, max_kb)
        self.settingsChanged.emit()

    @Slot(int)
    def setLogMaxKb(self, value):
        value = max(64, min(10240, value))  # clamp 64 KB – 10 MB
        self._cfg.setdefault("settings", {})["log_max_kb"] = value
        save_config(self._cfg)
        from core.logger import setup
        level = self._cfg.get("settings", {}).get("log_level", "errors")
        setup(level, value)
        self.settingsChanged.emit()

    @Slot()
    def clearLog(self):
        from core.logger import LOG_FILE
        try:
            open(LOG_FILE, "w").close()
            print("[MasterMice] Log cleared")
        except Exception:
            pass

    @Slot(result=str)
    def refreshLogContent(self):
        from core.logger import get_log_content
        content = get_log_content()
        self.settingsChanged.emit()  # force UI update
        return content

    @Slot(result=str)
    def runDiagnostics(self):
        """Run HID++ device diagnostics and return results.
        Pauses the live HID++ listener first so we can open the device."""
        from core.config import APP_VERSION
        # Pause HID++ listener to release the device
        hg = self._engine.hook._hid_gesture if self._engine else None
        # Read the known device index before pausing (survives cleanup)
        known_dev_idx = getattr(hg, '_dev_idx', 0xFF) if hg else 0xFF
        if hg and hasattr(hg, "pause"):
            hg.pause()
        try:
            return self._runDiagnosticsInner(APP_VERSION, known_dev_idx)
        finally:
            if hg and hasattr(hg, "resume"):
                hg.resume()

    def _runDiagnosticsInner(self, app_version, hint_dev_idx=0xFF):
        lines = []
        lines.append(f"=== MasterMice v{app_version} Diagnostics ===")
        lines.append("")

        # Check hidapi
        try:
            import hid
            lines.append("[OK] hidapi module available")
        except ImportError:
            lines.append("[FAIL] hidapi not installed")
            return "\n".join(lines)

        # Enumerate Logitech devices — skip 0xFFBC (receiver mgmt, no device HID++)
        LOGI_VID = 0x046D
        devices = []
        for info in hid.enumerate(LOGI_VID, 0):
            up = info.get("usage_page", 0)
            if up >= 0xFF00 and up != 0xFFBC:
                devices.append(info)
                pid = info.get("product_id", 0)
                product = info.get("product_string", "")
                lines.append(f"[DEVICE] PID=0x{pid:04X}  UP=0x{up:04X}  \"{product}\"")

        if not devices:
            lines.append("[WARN] No Logitech HID++ devices found")
            return "\n".join(lines)

        import time
        from core.hid_gesture import _parse
        LONG_ID = 0x11
        LONG_LEN = 20
        MY_SW = 0x0A

        # Try each HID interface and probe device indices
        # (Bolt receivers use indices 1-6, Bluetooth uses 0xFF)
        d = None
        active_idx = hint_dev_idx

        indices_to_try = [hint_dev_idx] + [
            i for i in (0xFF, 1, 2, 3, 4, 5, 6) if i != hint_dev_idx]

        for info in devices:
            pid = info.get("product_id", 0)
            try:
                dev = hid.device()
                dev.open_path(info["path"])
                dev.set_nonblocking(False)
            except Exception as e:
                lines.append(f"[SKIP] PID=0x{pid:04X}: {e}")
                continue

            # Quick probe: try each device index with a FEATURE_SET lookup
            for idx in indices_to_try:
                buf = [0] * LONG_LEN
                buf[0] = LONG_ID
                buf[1] = idx
                buf[2] = 0x00  # IRoot
                buf[3] = (MY_SW & 0x0F)
                buf[4] = 0x00
                buf[5] = 0x01  # FEATURE_SET
                buf[6] = 0x00
                try:
                    dev.write(buf)
                except Exception:
                    continue
                deadline = time.time() + 1.5
                while time.time() < deadline:
                    raw = dev.read(64, 500)
                    if not raw:
                        continue
                    msg = _parse(list(raw))
                    if msg and msg[1] == 0x00 and msg[3] == MY_SW:
                        _, _, _, _, p = msg
                        if p and p[0] != 0:
                            d = dev
                            active_idx = idx
                            break
                    if msg and msg[1] == 0xFF:
                        break  # error — try next index
                if d is not None:
                    break

            if d is not None:
                lines.append(f"[OK] Opened PID=0x{pid:04X}  devIdx=0x{active_idx:02X}")
                break
            try:
                dev.close()
            except Exception:
                pass

        if d is None:
            lines.append("[FAIL] No responding HID++ device found")
            return "\n".join(lines)

        def tx(feat, func, params):
            buf = [0] * LONG_LEN
            buf[0] = LONG_ID
            buf[1] = active_idx
            buf[2] = feat
            buf[3] = ((func & 0x0F) << 4) | (MY_SW & 0x0F)
            for i, b in enumerate(params):
                if 4 + i < LONG_LEN:
                    buf[4 + i] = b & 0xFF
            d.write(buf)

        def rx(timeout_ms=1500):
            raw = d.read(64, timeout_ms)
            return list(raw) if raw else None

        def request(feat, func, params):
            tx(feat, func, params)
            deadline = time.time() + 2
            while time.time() < deadline:
                raw = rx(500)
                if not raw:
                    continue
                msg = _parse(raw)
                if msg and msg[1] == feat and msg[3] == MY_SW:
                    return msg
                if msg and msg[1] == 0xFF:
                    return None
            return None

        def find_feature(fid):
            hi = (fid >> 8) & 0xFF
            lo = fid & 0xFF
            resp = request(0x00, 0, [hi, lo, 0x00])
            if resp:
                _, _, _, _, p = resp
                if p and p[0] != 0:
                    return p[0]
            return None

        # Probe features
        features = {
            0x0001: "FEATURE_SET",
            0x0003: "DEVICE_FW_VERSION",
            0x0005: "DEVICE_NAME",
            0x1000: "BATTERY_LEVEL_STATUS",
            0x1001: "BATTERY_VOLTAGE",
            0x1004: "UNIFIED_BATTERY",
            0x1B04: "REPROG_CONTROLS_V4",
            0x2201: "ADJUSTABLE_DPI",
            0x2250: "HIRES_WHEEL",
            0x8060: "REPORT_RATE",
            0x8061: "EXTENDED_ADJUSTABLE_REPORT_RATE",
        }

        lines.append("")
        lines.append("--- Feature Discovery ---")
        found = {}
        for fid, fname in features.items():
            idx = find_feature(fid)
            status = f"@0x{idx:02X}" if idx else "NOT FOUND"
            lines.append(f"  0x{fid:04X} {fname}: {status}")
            if idx:
                found[fid] = idx

        # Read battery
        for batt_fid in (0x1004, 0x1000, 0x1001):
            if batt_fid in found:
                lines.append("")
                lines.append(f"--- Battery (0x{batt_fid:04X}) ---")
                fn = 1 if batt_fid == 0x1004 else 0
                resp = request(found[batt_fid], fn, [])
                if resp:
                    _, _, _, _, p = resp
                    hexdata = " ".join(f"{b:02X}" for b in p[:8])
                    lines.append(f"  Raw: [{hexdata}]")
                    if batt_fid == 0x1000:
                        lines.append(f"  Level={p[0]}%, nextLevel={p[1]}%, status={p[2]}")
                    elif batt_fid == 0x1004:
                        lines.append(f"  SoC={p[0]}%, battStatus={p[1]}, extPower={p[2]}")
                    elif batt_fid == 0x1001:
                        v = (p[0] << 8 | p[1]) if len(p) >= 2 else 0
                        lines.append(f"  Voltage={v}mV, flags=0x{p[2]:02X}")
                else:
                    lines.append("  READ FAILED")
                break

        # Read DPI
        if 0x2201 in found:
            lines.append("")
            lines.append("--- DPI ---")
            resp = request(found[0x2201], 2, [0x00])
            if resp:
                _, _, _, _, p = resp
                dpi = (p[1] << 8 | p[2]) if len(p) >= 3 else 0
                lines.append(f"  Current DPI: {dpi}")
            else:
                lines.append("  READ FAILED")

        # Read report rate
        if 0x8060 in found:
            lines.append("")
            lines.append("--- Report Rate (0x8060) ---")
            resp = request(found[0x8060], 0, [])
            if resp:
                _, _, _, _, p = resp
                hexdata = " ".join(f"{b:02X}" for b in p[:8])
                lines.append(f"  Raw: [{hexdata}]")
                rate_ms = p[0] if p else 0
                lines.append(f"  Rate: {rate_ms}ms ({1000//rate_ms}Hz)" if rate_ms else "  Rate: unknown")

        try:
            d.close()
        except Exception:
            pass

        result = "\n".join(lines)
        print(result)  # also send to log
        return result

    @Slot()
    def openLogInExplorer(self):
        from core.logger import get_log_path
        path = os.path.normpath(get_log_path())
        try:
            if sys.platform == "win32":
                # /select, must be joined with path as one argument
                subprocess.Popen(f'explorer /select,"{path}"', shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
        except Exception:
            # Fallback: just open the folder
            folder = os.path.dirname(path)
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", folder])

    @Slot(str)
    def addProfile(self, appLabel):
        """Create a new per-app profile from the known-apps label."""
        exe = None
        for ex, info in KNOWN_APPS.items():
            if info["label"] == appLabel:
                exe = ex
                break
        if not exe:
            return
        for pdata in self._cfg.get("profiles", {}).values():
            if exe.lower() in [a.lower() for a in pdata.get("apps", [])]:
                self.statusMessage.emit("Profile already exists")
                return
        safe_name = exe.replace(".exe", "").lower()
        self._cfg = create_profile(
            self._cfg, safe_name, label=appLabel, apps=[exe])
        if self._engine:
            self._engine.cfg = self._cfg
        self.profilesChanged.emit()
        self.statusMessage.emit("Profile created")

    @Slot(str)
    def deleteProfile(self, name):
        if name == "default":
            return
        self._cfg = delete_profile(self._cfg, name)
        if self._engine:
            self._engine.cfg = self._cfg
            self._engine.reload_mappings()
        self.profilesChanged.emit()
        self.statusMessage.emit("Profile deleted")

    @Slot(str, result=list)
    def getProfileMappings(self, profileName):
        """Return button mappings for a specific profile, filtered by device."""
        profiles = self._cfg.get("profiles", {})
        pdata = profiles.get(profileName, {})
        mappings = pdata.get("mappings", {})
        device_buttons = get_device_buttons(self._cfg)
        result = []
        for key in device_buttons:
            name = BUTTON_NAMES.get(key, key)
            aid = mappings.get(key, "none")
            result.append({
                "key": key,
                "name": name,
                "actionId": aid,
                "actionLabel": _action_label(aid),
            })
        return result

    @Slot(str, result=str)
    def actionLabelFor(self, actionId):
        return _action_label(actionId)

    # ── Engine thread callbacks (cross-thread safe) ────────────

    def _onEngineProfileSwitch(self, profile_name):
        """Called from engine thread — posts to Qt main thread."""
        self._profileSwitchRequest.emit(profile_name)

    def _onEngineDpiRead(self, dpi):
        """Called from engine thread — posts to Qt main thread."""
        self._dpiReadRequest.emit(dpi)

    def _onEngineConnectionChange(self, connected):
        """Called from engine/hook thread — posts to Qt main thread."""
        self._connectionChangeRequest.emit(connected)

    def _onEngineBatteryRead(self, result):
        """Called from engine thread — result is dict with level/charging."""
        level = result.get("level", -1) if result else -1
        charging = result.get("charging", False) if result else False
        self._batteryUpdateRequest.emit(level if level is not None else -1, charging)

    @Slot(str)
    def _handleProfileSwitch(self, profile_name):
        """Runs on Qt main thread."""
        self._cfg["active_profile"] = profile_name
        self.activeProfileChanged.emit()
        self.mappingsChanged.emit()
        self.profilesChanged.emit()
        self.statusMessage.emit(f"Profile: {profile_name}")

    @Slot(int)
    def _handleDpiRead(self, dpi):
        """Runs on Qt main thread."""
        self._cfg.setdefault("settings", {})["dpi"] = dpi
        self.settingsChanged.emit()
        self.dpiFromDevice.emit(dpi)

    @Slot(bool)
    def _handleConnectionChange(self, connected):
        """Runs on Qt main thread."""
        self._mouse_connected = connected
        self.mouseConnectedChanged.emit()

    @Slot(int, bool)
    def _handleBatteryUpdate(self, level, charging):
        """Runs on Qt main thread."""
        self._battery_level = level
        self._battery_charging = charging
        self.settingsChanged.emit()

    def _onEngineDeviceDetected(self, model_key, device_name):
        """Called from engine thread — posts to Qt main thread."""
        self._deviceDetectedRequest.emit(model_key, device_name)

    @Slot(str, str)
    def _handleDeviceDetected(self, model_key, device_name):
        """Runs on Qt main thread. Auto-sets mouse_model from detected device."""
        current = self._cfg.get("settings", {}).get("mouse_model", "")
        if model_key and model_key in DEVICE_PROFILES:
            self._cfg.setdefault("settings", {})["mouse_model"] = model_key
            save_config(self._cfg)
            print(f"[Backend] Device auto-detected: {model_key} "
                  f"(\"{device_name}\"), was: {current!r}")
            self.settingsChanged.emit()
            self.mappingsChanged.emit()  # button list may change per device
