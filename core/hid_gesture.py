"""
hid_gesture.py — Detect MX Master 3S gesture button via Logitech HID++.

The gesture button on a Bluetooth-connected MX Master 3S (without Logi Options+)
often produces NO standard OS-level mouse event.  This module uses the HID++
protocol (over hidapi) to:

  1. Open the Logitech vendor-specific HID collection (UP 0xFF43).
  2. Discover the REPROG_CONTROLS_V4 (0x1B04) feature via IRoot.
  3. Divert the gesture button (CID 0x00C3) so we receive notifications.
  4. Fire callbacks on gesture press / release.

Requires:  pip install hidapi
Falls back gracefully if the package or device are unavailable.
"""

import sys
import threading
import time

try:
    import hid as _hid
    HIDAPI_OK = True
    # On macOS, allow non-exclusive HID access so the mouse keeps working
    if sys.platform == "darwin" and hasattr(_hid, "hid_darwin_set_open_exclusive"):
        _hid.hid_darwin_set_open_exclusive(0)
except ImportError:
    HIDAPI_OK = False

# ── Constants ─────────────────────────────────────────────────────
LOGI_VID       = 0x046D

SHORT_ID       = 0x10        # HID++ short report (7 bytes total)
LONG_ID        = 0x11        # HID++ long  report (20 bytes total)
SHORT_LEN      = 7
LONG_LEN       = 20

BT_DEV_IDX     = 0xFF        # device-index for direct Bluetooth
FEAT_IROOT        = 0x0000
FEAT_DEVICE_NAME  = 0x0005      # Device Name (marketing name string)
FEAT_REPROG_V4    = 0x1B04      # Reprogrammable Controls V4
FEAT_ADJ_DPI      = 0x2201      # Adjustable DPI
FEAT_BATT_UNIFIED = 0x1004      # Unified Battery (MX Master 4, newer devices)
FEAT_BATT_LEVEL   = 0x1000      # Battery Level Status (MX Master 3/3S, older devices)
FEAT_SMART_SHIFT  = 0x2110      # SmartShift (ratchet/freespin threshold)
FEAT_SMART_SHIFT2 = 0x2111      # SmartShift Enhanced (MX Master 4 — threshold + force)
FEAT_HIRES_WHEEL  = 0x2121      # Hi-Res Scrolling (MX Master 3/3S)
FEAT_HIRES_WHEEL2 = 0x2250      # Hi-Res Wheel V2 (MX Master 4, newer devices)
FEAT_HAPTIC       = 0xB019      # Haptic Feedback (MX Master 4)
CID_GESTURE       = 0x00C3      # "Mouse Gesture Button"
CID_ACTIONS_RING  = 0x01A0      # "Actions Ring / Haptic Sense Panel" (MX Master 4)

# Model keys (must match DEVICE_PROFILES keys in config.py)
MODEL_MX3   = "mx_master_3s"    # MX Master 3 (uses same profile as 3S)
MODEL_MX3S  = "mx_master_3s"    # MX Master 3S
MODEL_MX4   = "mx_master_4"     # MX Master 4

MY_SW          = 0x0A        # arbitrary software-id used in our requests


# ── Helpers ───────────────────────────────────────────────────────

def _parse(raw):
    """Parse a read buffer → (dev_idx, feat_idx, func, sw, params) or None.

    On Windows the hidapi C backend strips the report-ID byte, so the
    first byte is device-index.  On other platforms / future versions
    the report-ID may be included.  We detect which layout we have by
    checking whether byte 0 looks like a valid HID++ report-ID.
    """
    if not raw or len(raw) < 4:
        return None
    off = 1 if raw[0] in (SHORT_ID, LONG_ID) else 0
    if off + 3 > len(raw):
        return None
    dev    = raw[off]
    feat   = raw[off + 1]
    fsw    = raw[off + 2]
    func   = (fsw >> 4) & 0x0F
    sw     = fsw & 0x0F
    params = raw[off + 3:]
    return dev, feat, func, sw, params


# ── Listener class ────────────────────────────────────────────────

class HidGestureListener:
    """Background thread: diverts the gesture button and listens via HID++."""

    def __init__(self, on_down=None, on_up=None,
                 on_connect=None, on_disconnect=None,
                 on_battery=None,
                 on_actions_ring_down=None, on_actions_ring_up=None,
                 on_device_detected=None):
        self._on_down       = on_down
        self._on_up         = on_up
        self._on_connect    = on_connect
        self._on_disconnect = on_disconnect
        self._on_battery    = on_battery
        self._on_actions_ring_down = on_actions_ring_down
        self._on_actions_ring_up   = on_actions_ring_up
        self._on_device_detected   = on_device_detected
        self._dev       = None          # hid.device()
        self._thread    = None
        self._running   = False
        self._feat_idx  = None          # feature index of REPROG_V4
        self._dpi_idx   = None          # feature index of ADJUSTABLE_DPI
        self._batt_idx  = None          # feature index of battery feature
        self._batt_type = None          # "unified" (0x1004) or "level" (0x1000)
        self._smart_shift_idx = None    # feature index of SMART_SHIFT
        self._smart_shift_ver = 1       # 1=original(0x2110), 2=enhanced(0x2111)
        self._hires_idx = None          # feature index of HIRES_WHEEL
        self._haptic_idx = None         # feature index of HAPTIC_FEEDBACK
        self._scroll_ctrl_idx = None    # feature index of scroll control (smooth scrolling)
        self._dev_idx   = BT_DEV_IDX
        self._held      = False
        self._ar_held   = False         # Actions Ring held state
        self._connected = False         # True while HID++ device is open
        self._pending_dpi = None        # set by set_dpi(), applied in loop
        self._dpi_result  = None        # True/False after apply
        self._pending_battery = False   # set by read_battery()
        self._battery_result  = None    # integer percentage or None
        self._pending_cmd = None        # generic HID++ command: (feat, func, params)
        self._cmd_result  = None        # response from pending command
        self._paused = False
        self._pause_event = threading.Event()  # set when device is released
        self._device_name = ""          # marketing name from DEVICE_NAME feature
        self._detected_model = ""       # auto-detected model key
        self._cached_batt_level = None  # last known battery % (for MX3 charging quirk)
        self._connected_pid = 0         # PID of the receiver/device we connected to
        self._hires_active = False      # True when HiRes mode is enabled on device
        self._hires_multiplier = 1      # HiRes multiplier (e.g. 15 for MX3)
        self._short_handle = None       # Windows file handle for SHORT collection
                                        # (haptic commands via HidD_SetOutputReport)

    # ── public API ────────────────────────────────────────────────

    def pause(self):
        """Temporarily close the HID device so diagnostics can open it.
        Blocks until the listener thread has released the device."""
        if not self._running or self._paused:
            return
        self._pause_event.clear()
        self._paused = True
        # Wait up to 3s for the listener thread to close the device
        self._pause_event.wait(timeout=3)
        print("[HidGesture] Paused (device released)")

    def resume(self):
        """Resume the listener after a pause — will reconnect automatically."""
        if not self._paused:
            return
        self._paused = False
        print("[HidGesture] Resuming…")

    def start(self):
        if not HIDAPI_OK:
            print("[HidGesture] 'hidapi' not installed — pip install hidapi")
            return False
        self._running = True
        self._thread = threading.Thread(
            target=self._main_loop, daemon=True, name="HidGesture")
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        d = self._dev
        if d:
            try:
                d.close()
            except Exception:
                pass
            self._dev = None
        if self._thread:
            self._thread.join(timeout=3)

    # ── device discovery ──────────────────────────────────────────

    @staticmethod
    def _vendor_hid_infos():
        """Return list of device-info dicts for Logitech vendor-page TLCs.
        Skips 0xFFBC (receiver management — never has device HID++).
        Sorted: Usage=0x0002 (long reports) first, to avoid sending
        long reports to short-report interfaces which confuses Bolt receivers."""
        out = []
        try:
            for info in _hid.enumerate(LOGI_VID, 0):
                up = info.get("usage_page", 0)
                if up >= 0xFF00 and up != 0xFFBC:
                    out.append(info)
        except Exception as exc:
            print(f"[HidGesture] enumerate error: {exc}")
        # Prefer Usage=0x0002 (long reports) — Bolt receivers have both
        # Col01 (Usage=0x0001, short) and Col02 (Usage=0x0002, long).
        # Sending to Col01 first corrupts the receiver's HID++ state.
        out.sort(key=lambda d: 0 if d.get("usage", 0) == 0x0002 else 1)
        return out

    # ── low-level HID++ I/O ───────────────────────────────────────

    def _tx(self, report_id, feat, func, params):
        """Transmit an HID++ message.  Always uses 20-byte long format
        because BLE HID collections typically only support long output reports."""
        buf = [0] * LONG_LEN
        buf[0] = LONG_ID                 # always long for BLE compat
        buf[1] = self._dev_idx
        buf[2] = feat
        buf[3] = ((func & 0x0F) << 4) | (MY_SW & 0x0F)
        for i, b in enumerate(params):
            if 4 + i < LONG_LEN:
                buf[4 + i] = b & 0xFF
        self._dev.write(buf)

    def _rx(self, timeout_ms=2000):
        """Read one HID input report (blocking with timeout).
        Raises on device error (e.g., disconnection) so callers
        can trigger reconnection."""
        dev = self._dev
        if dev is None:
            return None
        d = dev.read(64, timeout_ms)
        return list(d) if d else None

    def _request(self, feat, func, params, timeout_ms=2000):
        """Send a long HID++ request, wait for matching response."""
        try:
            self._tx(LONG_ID, feat, func, params)
        except Exception:
            return None
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            try:
                raw = self._rx(min(500, timeout_ms))
            except Exception:
                return None
            if raw is None:
                continue
            msg = _parse(raw)
            if msg is None:
                continue
            _, r_feat, r_func, r_sw, r_params = msg

            # HID++ error (feature-index 0xFF)
            if r_feat == 0xFF:
                code = r_params[1] if len(r_params) > 1 else 0
                print(f"[HidGesture] HID++ error 0x{code:02X} "
                      f"for feat=0x{feat:02X} func={func}")
                return None

            if r_feat == feat and r_sw == MY_SW:
                return msg
        return None

    # ── feature helpers ───────────────────────────────────────────

    def _find_feature(self, feature_id, timeout_ms=2000):
        """Use IRoot (feature 0x0000) to discover a feature index."""
        hi = (feature_id >> 8) & 0xFF
        lo = feature_id & 0xFF
        resp = self._request(0x00, 0, [hi, lo, 0x00], timeout_ms=timeout_ms)
        if resp:
            _, _, _, _, p = resp
            if p and p[0] != 0:
                return p[0]
        return None

    def _query_device_name(self):
        """Query DEVICE_NAME (0x0005) to get the marketing name string."""
        name_fi = self._find_feature(FEAT_DEVICE_NAME)
        if not name_fi:
            return
        # func=0: getNameLength → p[0] = length
        resp = self._request(name_fi, 0, [])
        if not resp:
            return
        _, _, _, _, p = resp
        name_len = p[0] if p else 0
        if name_len == 0:
            return
        # func=1: getName(offset) → up to 16 ASCII bytes per chunk
        name = ""
        offset = 0
        while offset < name_len:
            chunk = self._request(name_fi, 1, [offset])
            if not chunk:
                break
            _, _, _, _, cp = chunk
            for b in cp:
                if 32 <= b < 127:
                    name += chr(b)
                offset += 1
                if offset >= name_len:
                    break
        self._device_name = name.strip().replace("_", " ")
        print(f"[HidGesture] Device name: \"{self._device_name}\"")

    def _auto_detect_model(self):
        """Fingerprint the device model from discovered features + name.
        Decision tree:
          1. Has 0xB019 (haptics)?      → MX Master 4
          2. Name contains "Master 4"?  → MX Master 4 (backup if haptic probe failed)
          3. Has 0x1004 (unified)?      → MX Master 3S
          4. Else (has 0x1000)          → MX Master 3 (same profile as 3S)
        """
        name_lower = self._device_name.lower()
        if self._haptic_idx is not None or "master 4" in name_lower:
            self._detected_model = MODEL_MX4
            label = "MX Master 4"
        elif self._batt_type == "unified":
            self._detected_model = MODEL_MX3S
            label = "MX Master 3S"
        else:
            self._detected_model = MODEL_MX3
            label = "MX Master 3"

        # Build feature summary for log
        feats = []
        if self._feat_idx:    feats.append("REPROG_V4")
        if self._dpi_idx:     feats.append("DPI")
        if self._batt_idx:    feats.append(f"BATT({self._batt_type})")
        if self._smart_shift_idx:
            feats.append(f"SMARTSHIFT_v{self._smart_shift_ver}")
        if self._hires_idx:   feats.append("HIRES")
        if self._haptic_idx or self._short_handle:
            feats.append("HAPTIC")
        if self._scroll_ctrl_idx: feats.append("SCROLL_CTRL")

        name_str = f" \"{self._device_name}\"" if self._device_name else ""
        print(f"[HidGesture] Auto-detected: {label}{name_str} "
              f"→ profile={self._detected_model}")
        print(f"[HidGesture] Features: {', '.join(feats)}")

        if self._on_device_detected:
            try:
                self._on_device_detected(self._detected_model, self._device_name)
            except Exception as e:
                print(f"[HidGesture] device detected callback error: {e}",
                      file=sys.stderr)

    def _divert(self):
        """Divert gesture button CID 0x00C3 (and actions ring CID 0x01A0
        if present) so we get press/release notifications."""
        if self._feat_idx is None:
            return False
        hi = (CID_GESTURE >> 8) & 0xFF
        lo = CID_GESTURE & 0xFF
        # flags: divert=1 (bit 0), dvalid=1 (bit 1) → 0x03
        resp = self._request(self._feat_idx, 3, [hi, lo, 0x03])
        ok = resp is not None
        print(f"[HidGesture] Divert CID 0x{CID_GESTURE:04X}: "
              f"{'OK' if ok else 'FAILED'}")
        # Also divert Actions Ring if callbacks are registered
        if self._on_actions_ring_down or self._on_actions_ring_up:
            ar_hi = (CID_ACTIONS_RING >> 8) & 0xFF
            ar_lo = CID_ACTIONS_RING & 0xFF
            ar_resp = self._request(self._feat_idx, 3, [ar_hi, ar_lo, 0x03])
            ar_ok = ar_resp is not None
            print(f"[HidGesture] Divert CID 0x{CID_ACTIONS_RING:04X} (Actions Ring): "
                  f"{'OK' if ar_ok else 'NOT FOUND (expected on MX3)'}")
        return ok

    def _undivert(self):
        """Restore default button behaviour (best-effort)."""
        if self._feat_idx is None or self._dev is None:
            return
        hi = (CID_GESTURE >> 8) & 0xFF
        lo = CID_GESTURE & 0xFF
        try:
            self._tx(LONG_ID, self._feat_idx, 3,
                     [hi, lo, 0x02])          # dvalid=1, divert=0
        except Exception:
            pass
        # Also un-divert Actions Ring
        ar_hi = (CID_ACTIONS_RING >> 8) & 0xFF
        ar_lo = CID_ACTIONS_RING & 0xFF
        try:
            self._tx(LONG_ID, self._feat_idx, 3,
                     [ar_hi, ar_lo, 0x02])
        except Exception:
            pass

    # ── Thread-safe HID++ command queue ────────────────────────────

    def _queued_request(self, feat, func, params, timeout=3.0):
        """Queue a HID++ request to run on the listener thread.
        Blocks until the listener thread executes it and returns the result.
        Must be called from any thread EXCEPT the listener thread."""
        self._cmd_result = None
        self._pending_cmd = (feat, func, params)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._pending_cmd is None:
                return self._cmd_result
            time.sleep(0.05)
        print("[HidGesture] Queued command timed out")
        self._pending_cmd = None
        return None

    def _apply_pending_cmd(self):
        """Called from the listener thread to execute a queued command."""
        cmd = self._pending_cmd
        if cmd is None:
            return
        feat, func, params = cmd
        self._cmd_result = self._request(feat, func, params)
        self._pending_cmd = None

    # ── DPI control ───────────────────────────────────────────────

    def set_dpi(self, dpi_value):
        """Queue a DPI change — will be applied on the listener thread.
        Can be called from any thread.  Returns True on success."""
        dpi = max(200, min(8200, int(dpi_value)))  # MX Master 3S max is 8000
        print(f"[HidGesture] DPI change requested: {dpi}")
        self._dpi_result = None
        self._pending_dpi = dpi
        # Wait up to 3s for the listener thread to apply it
        for _ in range(30):
            if self._pending_dpi is None:
                return self._dpi_result is True
            time.sleep(0.1)
        print("[HidGesture] DPI set timed out")
        return False

    def _apply_pending_dpi(self):
        """Called from the listener thread to actually send DPI."""
        dpi = self._pending_dpi
        if dpi is None:
            return
        if self._dpi_idx is None or self._dev is None:
            print("[HidGesture] Cannot set DPI — not connected")
            self._dpi_result = False
            self._pending_dpi = None
            return
        hi = (dpi >> 8) & 0xFF
        lo = dpi & 0xFF
        # setSensorDpi: function 3, params [sensorIdx=0, dpi_hi, dpi_lo]
        # (function 2 = getSensorDpi, function 3 = setSensorDpi)
        resp = self._request(self._dpi_idx, 3, [0x00, hi, lo])
        if resp:
            _, _, _, _, p = resp
            actual = (p[1] << 8 | p[2]) if len(p) >= 3 else dpi
            print(f"[HidGesture] DPI set to {actual}")
            self._dpi_result = True
        else:
            print("[HidGesture] DPI set FAILED")
            self._dpi_result = False
        self._pending_dpi = None

    def read_dpi(self):
        """Queue a DPI read — will be applied on the listener thread.
        Can be called from any thread.  Returns the DPI value or None."""
        self._dpi_result = None
        self._pending_dpi = "read"  # special sentinel
        for _ in range(30):
            if self._pending_dpi is None:
                return self._dpi_result
            time.sleep(0.1)
        print("[HidGesture] DPI read timed out")
        return None

    def _apply_pending_read_dpi(self):
        """Called from the listener thread to read current DPI."""
        if self._dpi_idx is None or self._dev is None:
            self._dpi_result = None
            self._pending_dpi = None
            return
        # getSensorDpi: function 2, params [sensorIdx=0]
        resp = self._request(self._dpi_idx, 2, [0x00])
        if resp:
            _, _, _, _, p = resp
            current = (p[1] << 8 | p[2]) if len(p) >= 3 else None
            print(f"[HidGesture] Current DPI = {current}")
            self._dpi_result = current
        else:
            print("[HidGesture] DPI read FAILED")
            self._dpi_result = None
        self._pending_dpi = None

    # ── Battery ───────────────────────────────────────────────────

    def read_battery(self):
        """Queue a battery read — applied on the listener thread.
        Returns dict {"level": 0-100, "charging": bool} or None."""
        print("[HidGesture] Battery read requested")
        self._battery_result = None
        self._pending_battery = True
        for _ in range(30):
            if not self._pending_battery:
                return self._battery_result
            time.sleep(0.1)
        print("[HidGesture] Battery read timed out")
        return None

    def _apply_pending_read_battery(self):
        """Called from the listener thread to read battery."""
        if self._paused or self._batt_idx is None or self._dev is None:
            print(f"[HidGesture] Battery read skipped — batt_idx={self._batt_idx}, "
                  f"dev={'OK' if self._dev else 'None'}")
            self._battery_result = None
            self._pending_battery = False
            return

        if self._batt_type == "unified":
            # UNIFIED_BATTERY (0x1004) — function 1: get_status
            # p[0]=stateOfCharge(0-100%), p[1]=batteryStatus, p[2]=externalPowerStatus
            # batteryStatus: 0=discharging, 1=recharging, 2=almost_full, 3=charged
            resp = self._request(self._batt_idx, 1, [])
            if resp:
                _, _, _, _, p = resp
                level = p[0] if p else None
                batt_status = p[1] if len(p) > 1 else 0
                ext_power = p[2] if len(p) > 2 else 0
                # Unified battery statuses: 0=discharging, 1=recharging, 2=almost_full,
                # 3=charge_complete, 4=recharging_below_optimal, 5=recharging_above_optimal,
                # 6=charging_error, 7=battery_error, 8=unknown(MX4 "OK")
                charging = batt_status in (1, 2, 3, 4, 5) or ext_power >= 1
                print(f"[HidGesture] Battery (unified) = {level}%, charging={charging} "
                      f"(status={batt_status}, extPower={ext_power})")
                self._battery_result = {"level": level, "charging": charging}
            else:
                print("[HidGesture] Battery (unified) read FAILED",
                      file=sys.stderr)
                self._battery_result = None

        elif self._batt_type == "level":
            # BATTERY_LEVEL_STATUS (0x1000) — function 0: GetBatteryLevelStatus
            resp = self._request(self._batt_idx, 0, [])
            if resp:
                _, _, _, _, p = resp
                level = p[0] if p else None
                batt_status = p[2] if len(p) > 2 else 0
                charging = batt_status in (1, 2, 3, 4)
                # MX3 reports 0% while charging — use cached value
                if charging and (level is None or level == 0):
                    level = self._cached_batt_level
                elif not charging and level and level > 0:
                    self._cached_batt_level = level
                print(f"[HidGesture] Battery (level) = {level}%, charging={charging} "
                      f"(status={batt_status})")
                self._battery_result = {"level": level, "charging": charging}
            else:
                print("[HidGesture] Battery (level) read FAILED",
                      file=sys.stderr)
                self._battery_result = None
        else:
            print(f"[HidGesture] Unknown battery type: {self._batt_type}")
            self._battery_result = None

        # Also fire the real-time callback (for event-triggered re-reads)
        if self._battery_result and self._on_battery:
            try:
                self._on_battery(self._battery_result)
            except Exception as e:
                print(f"[HidGesture] battery callback error: {e}")

        self._pending_battery = False

    # ── SmartShift (0x2110) ──────────────────────────────────────

    def get_smart_shift(self):
        """Read SmartShift status (thread-safe). Returns dict or None."""
        if self._smart_shift_idx is None or self._dev is None:
            return None
        if self._smart_shift_ver == 2:
            resp = self._queued_request(self._smart_shift_idx, 1, [])
            if resp:
                _, _, _, _, p = resp
                mode = p[0] if p else 0
                threshold = p[1] if len(p) > 1 else 10
                force = p[2] if len(p) > 2 else 50
                enabled = threshold != 0xFF
                print(f"[HidGesture] SmartShift v2: mode={mode} "
                      f"threshold={threshold} force={force} enabled={enabled}")
                return {"mode": mode,
                        "threshold": threshold if enabled else 10,
                        "force": force, "enabled": enabled}
            print("[HidGesture] SmartShift v2 read FAILED")
            return None
        else:
            resp = self._queued_request(self._smart_shift_idx, 0, [])
            if resp:
                _, _, _, _, p = resp
                mode = p[0] if p else 0
                threshold = p[1] if len(p) > 1 else 10
                auto_dis = p[2] if len(p) > 2 else 10
                enabled = threshold != 0xFF
                print(f"[HidGesture] SmartShift v1: mode={mode} "
                      f"threshold={threshold} auto_dis={auto_dis} "
                      f"enabled={enabled}")
                return {"mode": mode,
                        "threshold": threshold if enabled else 10,
                        "force": -1, "enabled": enabled}
            print("[HidGesture] SmartShift read FAILED")
            return None

    def set_smart_shift(self, threshold, force=None, enabled=None):
        """Set SmartShift configuration (thread-safe).
        v1 (MX3): func=1 [auto_disengage, threshold].
        v2 (MX4): func=2 [0x02, threshold, force]."""
        if self._smart_shift_idx is None or self._dev is None:
            print("[HidGesture] Cannot set SmartShift — not connected")
            return False
        if self._smart_shift_ver == 2:
            current = self.get_smart_shift()
            t = max(1, min(50, int(threshold))) if threshold is not None else (
                current["threshold"] if current else 10)
            f = max(1, min(100, int(force))) if force is not None else (
                current["force"] if current else 50)
            if enabled is not None and not enabled:
                t = 0xFF
            resp = self._queued_request(self._smart_shift_idx, 2,
                                        [0x02, t & 0xFF, f & 0xFF])
            ok = resp is not None
            print(f"[HidGesture] SmartShift v2 set threshold={t} force={f}: "
                  f"{'OK' if ok else 'FAILED'}")
            return ok
        else:
            # v1 (MX3): func=1 SET, params=[auto_disengage, threshold]
            current = self.get_smart_shift()
            t = max(1, min(50, int(threshold))) if threshold is not None else (
                current["threshold"] if current else 10)
            if enabled is not None and not enabled:
                t = 0xFF
            resp = self._queued_request(self._smart_shift_idx, 1,
                                        [10, t & 0xFF])
            ok = resp is not None
            print(f"[HidGesture] SmartShift v1 set threshold={t}: "
                  f"{'OK' if ok else 'FAILED'}")
            return ok

    # ── Hi-Res Wheel (0x2121) ─────────────────────────────────────

    def get_hires_wheel(self):
        """Read Hi-Res wheel mode (thread-safe). Returns dict or None."""
        if self._hires_idx is None or self._dev is None:
            return None
        resp = self._queued_request(self._hires_idx, 1, [])
        if resp:
            _, _, _, _, p = resp
            flags = p[0] if p else 0
            result = {
                "target": bool(flags & 0x01),
                "hires": bool(flags & 0x02),
                "invert": bool(flags & 0x04),
            }
            print(f"[HidGesture] HiRes wheel: {result}")
            return result
        print("[HidGesture] HiRes wheel read FAILED")
        return None

    def set_hires_wheel(self, hires=None, invert=None):
        """Set Hi-Res wheel mode (thread-safe). Tracks active state."""
        if self._hires_idx is None or self._dev is None:
            print("[HidGesture] Cannot set HiRes wheel — not connected")
            return False
        current = self.get_hires_wheel()
        if current is None:
            return False
        flags = 0
        new_hires = hires if hires is not None else current["hires"]
        if new_hires:
            flags |= 0x02
        if (invert if invert is not None else current["invert"]):
            flags |= 0x04
        if current["target"]:
            flags |= 0x01
        resp = self._queued_request(self._hires_idx, 2, [flags])
        ok = resp is not None
        if ok:
            self._hires_active = bool(new_hires)
        print(f"[HidGesture] HiRes wheel set flags=0x{flags:02X}: {'OK' if ok else 'FAILED'}"
              f" (hires_active={self._hires_active})")
        return ok

    # ── Haptic Motor (Feature 0x19B0, index 0x0B) ──────────────────
    # Uses HidD_SetOutputReport on the SHORT collection handle.
    # hidapi.write() sends interrupt OUT which Bolt receivers ignore.

    def _open_short_handle(self):
        """Open the SHORT HID collection (Usage=0x0001) for haptic commands.
        Uses hidapi for path finding + ctypes CreateFileW for handle."""
        if sys.platform != "win32":
            return
        import ctypes
        for info in _hid.enumerate(LOGI_VID, 0):
            if (info.get("usage_page", 0) == 0xFF00
                    and info.get("usage", 0) == 0x0001
                    and info.get("product_id", 0) == self._connected_pid):
                path = info.get("path", b"")
                if isinstance(path, bytes):
                    path = path.decode("utf-8", "replace")
                h = ctypes.windll.kernel32.CreateFileW(
                    path,
                    0x80000000 | 0x40000000,  # GENERIC_READ | GENERIC_WRITE
                    0x01 | 0x02,               # FILE_SHARE_READ | WRITE
                    None, 3, 0, None)          # OPEN_EXISTING
                if h != ctypes.c_void_p(-1).value and h != 0 and h != -1:
                    self._short_handle = h
                    print(f"[HidGesture] Opened SHORT handle for haptic motor")
                    return
                print(f"[HidGesture] SHORT handle open failed: "
                      f"err={ctypes.GetLastError()}")

    def _close_short_handle(self):
        """Close the SHORT collection handle."""
        if self._short_handle and sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.CloseHandle(self._short_handle)
            self._short_handle = None

    def _haptic_send_short(self, func_sw, p0=0, p1=0, p2=0):
        """Send a 7-byte short report via HidD_SetOutputReport."""
        if not self._short_handle:
            return False
        import ctypes
        buf = (ctypes.c_ubyte * 7)(0x10, self._dev_idx, 0x0B, func_sw, p0, p1, p2)
        ok = ctypes.windll.hid.HidD_SetOutputReport(self._short_handle, buf, 7)
        return bool(ok)

    def haptic_set_config(self, enabled, intensity):
        """Enable/disable haptic motor + set intensity (0-100).
        Uses SET_REPORT on SHORT handle — works on Bolt receivers."""
        mode = 0x01 if enabled else 0x00
        i = max(0, min(100, int(intensity)))
        ok = self._haptic_send_short(0x2A, mode, i, 0x00)
        print(f"[HidGesture] Haptic config: {'ON' if enabled else 'OFF'} "
              f"intensity={i}%: {'OK' if ok else 'FAILED'}")
        return ok

    def haptic_trigger(self, pulse_type=0x04):
        """Trigger a haptic pulse.
        pulse_type: 0x02=light, 0x04=tick, 0x08=strong, 0x00=reset/arm."""
        ok = self._haptic_send_short(0x4A, pulse_type, 0x00, 0x00)
        names = {0x00: "reset", 0x02: "light", 0x04: "tick", 0x08: "strong"}
        name = names.get(pulse_type, f"0x{pulse_type:02X}")
        print(f"[HidGesture] Haptic trigger {name}: {'OK' if ok else 'FAILED'}")
        return ok

    # Legacy wrappers for backward compatibility with backend.py
    def get_haptic(self):
        """Read haptic state. Returns dict or None."""
        if not self._short_handle:
            return None
        # We don't read state from the device — just return last known
        return {"enabled": True, "intensity": 60}

    def set_haptic(self, enabled=None, intensity=None):
        """Set haptic config (legacy wrapper)."""
        e = enabled if enabled is not None else True
        i = intensity if intensity is not None else 60
        return self.haptic_set_config(e, i)

    # ── Smooth Scrolling (via scroll control feature) ─────────────

    def get_smooth_scroll(self):
        """Read smooth scrolling state (thread-safe). Returns bool or None."""
        if self._scroll_ctrl_idx is None or self._dev is None:
            return None
        resp = self._queued_request(self._scroll_ctrl_idx, 1, [])
        if resp:
            _, _, _, _, p = resp
            flags = p[0] if p else 0
            smooth = bool(flags & 0x01)
            print(f"[HidGesture] Smooth scroll: {smooth}")
            return smooth
        print("[HidGesture] Smooth scroll read FAILED")
        return None

    def set_smooth_scroll(self, enabled):
        """Set smooth scrolling on/off (thread-safe)."""
        if self._scroll_ctrl_idx is None or self._dev is None:
            print("[HidGesture] Cannot set smooth scroll — not connected")
            return False
        resp = self._queued_request(self._scroll_ctrl_idx, 2,
                                    [0x01 if enabled else 0x00])
        ok = resp is not None
        print(f"[HidGesture] Smooth scroll set to {enabled}: "
              f"{'OK' if ok else 'FAILED'}")
        return ok

    # ── notification handling ─────────────────────────────────────

    def _handle_battery_event(self, params):
        """Handle a battery broadcast event pushed by the device.
        MX3 quirk: reports level=0% while charging — use cached level.
        If the event has level=0 and is NOT charging, do a fresh read."""
        if self._batt_type == "level":
            level = params[0] if params else None
            batt_status = params[2] if len(params) > 2 else 0
            charging = batt_status in (1, 2, 3, 4)
            # MX3 reports 0% while charging — use cached value
            if charging and (level is None or level == 0):
                level = self._cached_batt_level  # may be None on first run
            elif not charging and level and level > 0:
                self._cached_batt_level = level
        elif self._batt_type == "unified":
            level = params[0] if params else None
            batt_status = params[1] if len(params) > 1 else 0
            ext_power = params[2] if len(params) > 2 else 0
            charging = batt_status in (1, 2, 3, 4, 5) or ext_power >= 1
        else:
            return

        print(f"[HidGesture] Battery EVENT: level={level}%, charging={charging} "
              f"(status={batt_status})"
              + (f", extPower={ext_power}" if self._batt_type == "unified" else ""))

        # If level is still 0/None after caching, do a fresh read
        if not level or level == 0:
            print("[HidGesture] Event has no level — doing fresh battery read")
            self._pending_battery = True
            return

        if self._on_battery and level is not None:
            try:
                self._on_battery({"level": level, "charging": charging})
            except Exception as e:
                print(f"[HidGesture] battery callback error: {e}")

    def _on_report(self, raw):
        """Inspect incoming HID++ reports for button events and battery broadcasts."""
        msg = _parse(raw)
        if msg is None:
            return
        _, feat, func, _sw, params = msg

        # Battery broadcast event (device pushes this on charger connect/disconnect)
        if self._batt_idx is not None and feat == self._batt_idx and func == 0:
            self._handle_battery_event(params)
            return

        # Only care about notifications from REPROG_CONTROLS_V4, event 0
        if feat != self._feat_idx or func != 0:
            return

        # Params: sequential CID pairs terminated by 0x0000
        cids = set()
        i = 0
        while i + 1 < len(params):
            c = (params[i] << 8) | params[i + 1]
            if c == 0:
                break
            cids.add(c)
            i += 2

        gesture_now = CID_GESTURE in cids
        ar_now = CID_ACTIONS_RING in cids

        if gesture_now and not self._held:
            self._held = True
            print("[HidGesture] Gesture DOWN")
            if self._on_down:
                try:
                    self._on_down()
                except Exception as e:
                    print(f"[HidGesture] down callback error: {e}")

        elif not gesture_now and self._held:
            self._held = False
            print("[HidGesture] Gesture UP")
            if self._on_up:
                try:
                    self._on_up()
                except Exception as e:
                    print(f"[HidGesture] up callback error: {e}")

        if ar_now and not self._ar_held:
            self._ar_held = True
            print("[HidGesture] Actions Ring DOWN")
            if self._on_actions_ring_down:
                try:
                    self._on_actions_ring_down()
                except Exception as e:
                    print(f"[HidGesture] actions ring down error: {e}")

        elif not ar_now and self._ar_held:
            self._ar_held = False
            print("[HidGesture] Actions Ring UP")
            if self._on_actions_ring_up:
                try:
                    self._on_actions_ring_up()
                except Exception as e:
                    print(f"[HidGesture] actions ring up error: {e}")

    # ── connect / main loop ───────────────────────────────────────

    def _try_connect(self):
        """Open the vendor HID collection, identify device via name,
        then use its profile to discover only the features it has.
        Uses parallel index probing for fast connection."""
        from core.config import DEVICE_PROFILES, load_config, save_config

        infos = self._vendor_hid_infos()
        if not infos:
            return False

        cfg = load_config()
        # Try last working devIdx first (from config), then all others
        cfg_idx = cfg.get("settings", {}).get("last_dev_idx", None)
        idx_order = []
        if cfg_idx is not None:
            idx_order.append(cfg_idx)
        for i in (0xFF, 1, 2, 3, 4, 5, 6):
            if i not in idx_order:
                idx_order.append(i)

        for info in infos:
            pid = info.get("product_id", 0)
            up  = info.get("usage_page", 0)
            try:
                d = _hid.device()
                d.open_path(info["path"])
                d.set_nonblocking(False)
                self._dev = d
            except Exception as exc:
                print(f"[HidGesture] Can't open PID=0x{pid:04X} "
                      f"UP=0x{up:04X}: {exc}")
                continue

            # ── Fast connect: sequential probing with short timeout ──
            # Try last working devIdx first, then all others.
            # 500ms timeout per probe (vs 2000ms before).
            found_idx = None
            found_fi = None
            for idx in idx_order:
                self._dev_idx = idx
                fi = self._find_feature(FEAT_REPROG_V4, timeout_ms=500)
                if fi is not None:
                    found_idx = idx
                    found_fi = fi
                    break

            if found_idx is None:
                try:
                    d.close()
                except Exception:
                    pass
                self._dev = None
                continue

            # ── Device found ──────────────────────────────────────
            self._dev_idx = found_idx
            self._feat_idx = found_fi
            self._connected_pid = pid
            print(f"[HidGesture] Found REPROG_V4 @0x{found_fi:02X}  "
                  f"PID=0x{pid:04X} devIdx=0x{found_idx:02X}")

            # Save working devIdx for fast reconnect
            cfg.setdefault("settings", {})["last_dev_idx"] = found_idx
            save_config(cfg)

            # ── Step 1: Identify device by name ───────────────────
            self._query_device_name()
            name_lower = self._device_name.lower()

            # Match name to profile
            profile = None
            profile_key = ""
            for key, prof in DEVICE_PROFILES.items():
                for match_str in prof.get("name_matches", []):
                    if match_str in name_lower:
                        profile = prof
                        profile_key = key
                        break
                if profile:
                    break

            if not profile:
                # Fallback: use mx_master_3s as default
                profile_key = MODEL_MX3S
                profile = DEVICE_PROFILES.get(MODEL_MX3S, {})
                print(f"[HidGesture] Unknown device \"{self._device_name}\" "
                      f"— using fallback profile {profile_key}")

            self._detected_model = profile_key
            print(f"[HidGesture] Identified: \"{self._device_name}\" "
                  f"→ profile={profile_key}")

            # ── Step 2: Profile-driven feature discovery ──────────
            # Only discover features the profile says exist.

            # DPI (all devices)
            dpi_fi = self._find_feature(FEAT_ADJ_DPI)
            if dpi_fi:
                self._dpi_idx = dpi_fi
                print(f"[HidGesture] Found ADJUSTABLE_DPI @0x{dpi_fi:02X}")

            # Battery — use the profile's feature ID directly
            batt_fid = profile.get("battery_feature_id")
            if batt_fid:
                batt_fi = self._find_feature(batt_fid)
                if batt_fi:
                    self._batt_idx = batt_fi
                    self._batt_type = "unified" if batt_fid == 0x1004 else "level"
                    print(f"[HidGesture] Found BATTERY (0x{batt_fid:04X}) "
                          f"@0x{batt_fi:02X} type={self._batt_type}")

            # SmartShift — use profile's feature ID and version
            ss_fid = profile.get("smartshift_feature_id")
            if ss_fid:
                ss_fi = self._find_feature(ss_fid)
                if ss_fi:
                    self._smart_shift_idx = ss_fi
                    self._smart_shift_ver = profile.get("smartshift_version", 1)
                    print(f"[HidGesture] Found SMARTSHIFT (0x{ss_fid:04X}) "
                          f"@0x{ss_fi:02X} v{self._smart_shift_ver}")

            # Haptic Feedback — only if profile says it exists
            if profile.get("has_haptics"):
                hap_fid = profile.get("haptic_feature_id", FEAT_HAPTIC)
                if hap_fid:
                    # Try IRoot first (fast)
                    hap_fi = self._find_feature(hap_fid)
                    if hap_fi:
                        self._haptic_idx = hap_fi
                        print(f"[HidGesture] Found HAPTIC (0x{hap_fid:04X}) "
                              f"@0x{hap_fi:02X}")
                    else:
                        # IRoot failed for 0xB019. This happens on MX4 via Bolt.
                        # Fallback 1: FEATURE_SET enumeration (scan all indices)
                        print(f"[HidGesture] HAPTIC IRoot failed — "
                              f"scanning via FEATURE_SET...")
                        # FEATURE_SET is always at index 0x01
                        cnt_resp = self._request(0x01, 0, [])
                        count = 0
                        if cnt_resp:
                            _, _, _, _, cp = cnt_resp
                            count = cp[0] if cp else 0
                            print(f"[HidGesture] FEATURE_SET reports "
                                  f"{count} features")
                        for scan_i in range(1, min(count + 1, 30)):
                            r = self._request(0x01, 1, [scan_i])
                            if r:
                                _, _, _, _, sp = r
                                fid = (sp[0] << 8 | sp[1]) if len(sp) >= 2 else 0
                                if fid == hap_fid:
                                    self._haptic_idx = scan_i
                                    print(f"[HidGesture] Found HAPTIC via "
                                          f"FEATURE_SET @0x{scan_i:02X}")
                                    break
                                elif fid != 0:
                                    print(f"[HidGesture]   idx {scan_i:2d} "
                                          f"→ 0x{fid:04X}")
                        if self._haptic_idx is None:
                            # Fallback 2: try the known index directly (0x0B)
                            # Send a func=2 read to see if the feature responds
                            print(f"[HidGesture] Trying known haptic "
                                  f"index 0x0B directly...")
                            test = self._request(0x0B, 2, [])
                            if test:
                                _, _, _, _, tp = test
                                print(f"[HidGesture] Index 0x0B responded: "
                                      f"{[f'0x{b:02X}' for b in tp[:4]]}")
                                self._haptic_idx = 0x0B
                                print(f"[HidGesture] Using HAPTIC @0x0B "
                                      f"(direct probe)")
                            else:
                                print(f"[HidGesture] HAPTIC not found "
                                      f"by any method")

            # HiRes Wheel — try 0x2250 first, check capability,
            # fall back to 0x2121
            hr_fi = self._find_feature(FEAT_HIRES_WHEEL2)
            if hr_fi:
                self._hires_idx = hr_fi
                # Check multiplier
                cap = self._request(self._hires_idx, 0, [])
                if cap:
                    _, _, _, _, cp = cap
                    mult = cp[0] if cp else 0
                    if mult == 0:
                        print(f"[HidGesture] HIRES_WHEEL V2 @0x{hr_fi:02X} "
                              f"multiplier=0 — trying 0x2121")
                        self._hires_idx = None
                    else:
                        self._hires_multiplier = mult
                        print(f"[HidGesture] Found HIRES_WHEEL V2 "
                              f"@0x{hr_fi:02X} multiplier={mult}")

            if self._hires_idx is None:
                sc_fi = self._find_feature(FEAT_HIRES_WHEEL)
                if sc_fi:
                    cap2 = self._request(sc_fi, 0, [])
                    if cap2:
                        _, _, _, _, cp2 = cap2
                        mult2 = cp2[0] if cp2 else 0
                        if mult2 > 0:
                            self._hires_idx = sc_fi
                            self._hires_multiplier = mult2
                            print(f"[HidGesture] Found HIRES_WHEEL (0x2121) "
                                  f"@0x{sc_fi:02X} multiplier={mult2}")
                    if self._hires_idx != sc_fi:
                        self._scroll_ctrl_idx = sc_fi
                    else:
                        print(f"[HidGesture] 0x2121 @0x{sc_fi:02X} is HiRes "
                              f"— skipping smooth scroll")

            # ── Build feature summary ─────────────────────────────
            self._auto_detect_model()

            # ── Open SHORT handle for haptic motor (MX4) ──────────
            if profile.get("has_haptics"):
                self._open_short_handle()

            if self._divert():
                return True

            # Divert failed — close and try next interface
            print("[HidGesture] Divert failed, trying next interface...")
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

        return False

    def _main_loop(self):
        """Outer loop: connect → listen → reconnect on error/disconnect."""
        while self._running:
            if not self._try_connect():
                print("[HidGesture] No compatible device; retrying in 5 s…",
                      file=sys.stderr)
                for _ in range(50):
                    if not self._running:
                        return
                    time.sleep(0.1)
                continue

            self._connected = True
            if self._on_connect:
                try:
                    self._on_connect()
                except Exception:
                    pass
            print("[HidGesture] Listening for gesture events…")
            try:
                while self._running:
                    # Handle pause request (diagnostics)
                    if self._paused:
                        self._undivert()
                        try:
                            if self._dev:
                                self._dev.close()
                        except Exception:
                            pass
                        self._dev = None
                        self._pause_event.set()  # signal that device is released
                        while self._paused and self._running:
                            time.sleep(0.1)
                        break  # will reconnect in outer loop

                    # Apply any queued DPI command
                    if self._pending_dpi is not None:
                        if self._pending_dpi == "read":
                            self._apply_pending_read_dpi()
                        else:
                            self._apply_pending_dpi()
                    # Apply any queued battery read
                    if self._pending_battery:
                        self._apply_pending_read_battery()
                    # Apply any queued generic HID++ command
                    if self._pending_cmd is not None:
                        self._apply_pending_cmd()
                    raw = self._rx(1000)
                    if raw:
                        self._on_report(raw)
            except Exception as e:
                print(f"[HidGesture] read error: {e}", file=sys.stderr)

            # Cleanup before potential reconnect
            self._undivert()
            try:
                if self._dev:
                    self._dev.close()
            except Exception:
                pass
            self._dev = None
            self._feat_idx = None
            self._dpi_idx = None
            self._batt_idx = None
            self._batt_type = None
            self._smart_shift_idx = None
            self._smart_shift_ver = 1
            self._hires_idx = None
            self._haptic_idx = None
            self._close_short_handle()
            self._scroll_ctrl_idx = None
            self._device_name = ""
            self._detected_model = ""
            self._cached_batt_level = None
            self._held = False
            self._ar_held = False
            if self._connected:
                self._connected = False
                if self._on_disconnect:
                    try:
                        self._on_disconnect()
                    except Exception:
                        pass

            if self._running:
                time.sleep(2)
