"""
Engine — wires the mouse hook to the key simulator using the
current configuration.  Sits between the hook layer and the UI.
Supports per-application auto-switching of profiles.

HID++ device communication is delegated to the Go service via
ServiceClient (named pipe IPC).  The mouse hook (WH_MOUSE_LL)
stays in-process for button remapping.
"""

import threading
from core.mouse_hook import MouseHook, MouseEvent
from core.key_simulator import execute_action
from core.config import (
    load_config, get_active_mappings, get_profile_for_app,
    BUTTON_TO_EVENTS, save_config,
)
from core.app_detector import AppDetector
from core.service_client import ServiceClient


class Engine:
    """
    Core logic: reads config, installs the mouse hook,
    dispatches actions when mapped buttons are pressed,
    and auto-switches profiles when the foreground app changes.

    HID++ commands (DPI, SmartShift, battery, etc.) go through the
    Go service via self.svc (ServiceClient).
    """

    def __init__(self):
        self.hook = MouseHook()
        self.svc = ServiceClient()
        self.cfg = load_config()
        self._enabled = True
        self._hscroll_accum = 0
        self._current_profile: str = self.cfg.get("active_profile", "default")
        self._app_detector = AppDetector(self._on_app_change)
        self._profile_change_cb = None       # UI callback
        self._connection_change_cb = None   # UI callback for device status
        self._battery_read_cb = None        # UI callback for battery level
        self._device_detected_cb = None     # UI callback for auto-detected model
        self._dpi_read_cb = None            # UI callback for initial DPI
        self._last_battery_event_time = 0.0
        self._lock = threading.Lock()
        self._setup_hooks()

        # Wire service events
        self.svc.on_event("battery_update", self._on_battery_event)
        self.svc.on_event("device_connected", self._on_svc_connected)
        self.svc.on_event("device_disconnected", self._on_svc_disconnected)
        self.svc.on_event("gesture_button_down", self._on_svc_gesture_down)
        self.svc.on_event("gesture_button_up", self._on_svc_gesture_up)

    # ------------------------------------------------------------------
    # Hook wiring
    # ------------------------------------------------------------------
    def _setup_hooks(self):
        """Register callbacks and block events for all mapped buttons."""
        mappings = get_active_mappings(self.cfg)

        # Apply scroll inversion settings to the hook
        settings = self.cfg.get("settings", {})
        self.hook.invert_vscroll = settings.get("invert_vscroll", False)
        self.hook.invert_hscroll = settings.get("invert_hscroll", False)

        for btn_key, action_id in mappings.items():
            events = list(BUTTON_TO_EVENTS.get(btn_key, ()))

            for evt_type in events:
                if evt_type.endswith("_up"):
                    if action_id != "none":
                        self.hook.block(evt_type)
                    continue

                if action_id != "none":
                    self.hook.block(evt_type)

                    if "hscroll" in evt_type:
                        self.hook.register(evt_type, self._make_hscroll_handler(action_id))
                    else:
                        self.hook.register(evt_type, self._make_handler(action_id))

    def _make_handler(self, action_id):
        def handler(event):
            if self._enabled:
                execute_action(action_id)
        return handler

    def _make_hscroll_handler(self, action_id):
        def handler(event):
            if not self._enabled:
                return
            execute_action(action_id)
        return handler

    # ------------------------------------------------------------------
    # Per-app auto-switching
    # ------------------------------------------------------------------
    def _on_app_change(self, exe_name: str):
        """Called by AppDetector when foreground window changes."""
        target = get_profile_for_app(self.cfg, exe_name)
        if target == self._current_profile:
            return
        print(f"[Engine] App changed to {exe_name} -> profile '{target}'")
        self._switch_profile(target)

    def _switch_profile(self, profile_name: str):
        with self._lock:
            self.cfg["active_profile"] = profile_name
            self._current_profile = profile_name
            self.hook.reset_bindings()
            self._setup_hooks()
        if self._profile_change_cb:
            try:
                self._profile_change_cb(profile_name)
            except Exception:
                pass

    def set_profile_change_callback(self, cb):
        """Register a callback ``cb(profile_name)`` invoked on auto-switch."""
        self._profile_change_cb = cb

    # ------------------------------------------------------------------
    # Service event handlers
    # ------------------------------------------------------------------
    def _on_svc_connected(self, data):
        """Service reports device connected."""
        model = data.get("model", "")
        name = data.get("name", "")
        print(f"[Engine] Device connected via service: {name} ({model})")
        if self._connection_change_cb:
            try:
                self._connection_change_cb(True)
            except Exception:
                pass
        if model and self._device_detected_cb:
            try:
                self._device_detected_cb(model, name)
            except Exception:
                pass

    def _on_svc_disconnected(self, data):
        """Service reports device disconnected."""
        print("[Engine] Device disconnected (service)")
        if self._connection_change_cb:
            try:
                self._connection_change_cb(False)
            except Exception:
                pass

    def _on_svc_gesture_down(self, data):
        """Gesture button pressed — dispatch via hook callbacks."""
        evt = MouseEvent("gesture_click")
        self.hook._dispatch(evt)

    def _on_svc_gesture_up(self, data):
        """Gesture button released."""
        pass  # gesture_click is single-event, no separate up needed

    def _on_battery_event(self, data):
        """Battery update from service."""
        import time
        self._last_battery_event_time = time.time()
        result = {
            "level": data.get("level", 0),
            "charging": data.get("charging", False),
        }
        print(f"[Engine] Battery event: {result}")
        if self._battery_read_cb and result:
            try:
                self._battery_read_cb(result)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Callback setters (used by Backend)
    # ------------------------------------------------------------------
    def set_connection_change_callback(self, cb):
        """Register ``cb(connected: bool)`` invoked on device connect/disconnect."""
        self._connection_change_cb = cb

    def set_battery_callback(self, cb):
        """Register ``cb(result: dict)`` invoked when battery is read or event fires."""
        self._battery_read_cb = cb

    def set_device_detected_callback(self, cb):
        """Register ``cb(model_key, device_name)`` invoked on auto-detection."""
        self._device_detected_cb = cb

    def set_dpi_read_callback(self, cb):
        """Register a callback ``cb(dpi_value)`` invoked when DPI is read from device."""
        self._dpi_read_cb = cb

    @property
    def device_connected(self):
        """Check if device is connected via the service."""
        if self.svc.connected:
            status = self.svc.get_status()
            if status:
                return status.get("connected", False)
        return False

    # ------------------------------------------------------------------
    # Public API — delegates to Go service
    # ------------------------------------------------------------------
    def set_dpi(self, dpi_value):
        """Send DPI change via the service."""
        self.cfg.setdefault("settings", {})["dpi"] = dpi_value
        save_config(self.cfg)
        if self.svc.connected:
            return self.svc.set_dpi(dpi_value)
        print("[Engine] Service not connected — DPI not applied")
        return False

    def reload_mappings(self):
        """Re-wire callbacks without tearing down the hook."""
        with self._lock:
            self.cfg = load_config()
            self._current_profile = self.cfg.get("active_profile", "default")
            self.hook.reset_bindings()
            self._setup_hooks()

    def set_enabled(self, enabled):
        self._enabled = enabled

    def update_hires_scroll_state(self, active, multiplier=None, divider=None):
        """Update the mouse hook's HiRes scroll scaling parameters."""
        self.hook.hires_active = bool(active)
        if multiplier is not None:
            self.hook.hires_multiplier = int(multiplier)
        if divider is not None:
            self.hook.hires_divider = max(1, int(divider))
        print(f"[Engine] HiRes scroll: active={active} "
              f"mult={self.hook.hires_multiplier} div={self.hook.hires_divider}")

    def start(self):
        self.hook.start()
        self._app_detector.start()

        # Connect to the Go service
        def _connect_service():
            import time
            time.sleep(1)  # brief settle
            if self.svc.connect():
                # Read initial state from service
                self._read_initial_state()
            else:
                print("[Engine] Service not available — HID++ features disabled")
        threading.Thread(target=_connect_service, daemon=True,
                         name="SvcConnect").start()

    def _read_initial_state(self):
        """Read device state from service after connecting."""
        # FIRST: get connection status + device info (fast — uses cached values)
        status = self.svc.get_status()
        if status:
            model = status.get("model", "")
            name = status.get("name", "")
            connected = status.get("connected", False)
            print(f"[Engine] Service status: connected={connected} model={model}")
            if connected:
                if self._connection_change_cb:
                    try:
                        self._connection_change_cb(True)
                    except Exception:
                        pass
                if model and self._device_detected_cb:
                    try:
                        self._device_detected_cb(model, name)
                    except Exception:
                        pass

            # Use cached battery/DPI from status (no extra HID++ calls)
            batt_level = status.get("battery_level", -1)
            batt_charging = status.get("battery_charging", False)
            if batt_level >= 0 and self._battery_read_cb:
                try:
                    self._battery_read_cb({
                        "level": batt_level,
                        "charging": batt_charging,
                    })
                except Exception:
                    pass

            dpi = status.get("dpi", 0)
            if dpi > 0:
                self.cfg.setdefault("settings", {})["dpi"] = dpi
                save_config(self.cfg)
                if self._dpi_read_cb:
                    try:
                        self._dpi_read_cb(dpi)
                    except Exception:
                        pass

    def stop(self):
        self._app_detector.stop()
        self.hook.stop()
        self.svc.disconnect()
