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
        self.service_version = ""          # cached from health check
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
        """Battery update from service. Only logs on actual change."""
        import time
        self._last_battery_event_time = time.time()
        result = {
            "level": data.get("level", 0),
            "charging": data.get("charging", False),
        }
        # Only log if battery state actually changed
        prev = getattr(self, '_last_battery_state', None)
        if prev != (result["level"], result["charging"]):
            print(f"[Engine] Battery: {result['level']}% {'(charging)' if result['charging'] else ''}")
            self._last_battery_state = (result["level"], result["charging"])

        # Haptic feedback on charge state change
        new_charging = result.get("charging", False)
        old_charging = getattr(self, '_last_charging_state', None)
        if old_charging is not None and new_charging != old_charging:
            if self.svc.connected and self.cfg.get("settings", {}).get("haptic_enabled", True):
                import threading
                def _haptic_notify():
                    try:
                        if new_charging:
                            # Plugged in → Buzz 0.5s × 3
                            for _ in range(3):
                                self.svc.haptic_sequence([
                                    {"pulse": 0x02, "delay": 25}
                                ] * 20, repeat=1)
                                time.sleep(0.7)
                            print("[Engine] Haptic: charge connected (buzz x3)")
                        else:
                            # Unplugged → Triple
                            self.svc.haptic_trigger(0x0C)
                            print("[Engine] Haptic: charge disconnected (triple)")
                    except Exception as e:
                        print(f"[Engine] Haptic charge notify failed: {e}")
                threading.Thread(target=_haptic_notify, daemon=True).start()
        self._last_charging_state = new_charging
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
        self._svc_watchdog_stop = threading.Event()

        EXPECTED_SVC_VERSION = "0.6.5"

        # Connect to the Go service (auto-launch if needed)
        def _connect_service():
            import time
            time.sleep(0.5)

            # Try connecting first (service may already be running)
            if self.svc.connect():
                # Check version — kill outdated service and relaunch
                health = self.svc.health()
                svc_ver = health.get("version", "") if health else ""
                if svc_ver != EXPECTED_SVC_VERSION:
                    print(f"[Engine] Service version mismatch: "
                          f"got '{svc_ver}', need '{EXPECTED_SVC_VERSION}' — restarting")
                    self.svc.disconnect()
                    self._kill_old_service()
                    # Update SCM binPath if service is installed (points to old exe)
                    self._update_scm_path()
                else:
                    from core.config import APP_VERSION
                    print(f"[Engine] App v{APP_VERSION}, Service v{svc_ver}")
                    self.service_version = svc_ver
                    # Always ensure agent is running (may have died since last session)
                    self._ensure_agent_running()
                    self._read_initial_state()
                    self._start_watchdog()
                    return

            # Service not running or was killed — launch it
            print("[Engine] Starting service...")
            svc_path = self._find_and_launch_service()
            if svc_path:
                for attempt in range(30):
                    time.sleep(0.5)
                    if self.svc.connect():
                        print(f"[Engine] Connected to service (attempt {attempt + 1})")
                        # Cache version from fresh service
                        h = self.svc.health()
                        if h:
                            self.service_version = h.get("version", "")
                        self._read_initial_state()
                        self._start_watchdog()
                        return
                print("[Engine] Service launched but failed to connect after 15s")
            else:
                print("[Engine] Service not available — HID++ features disabled")

        threading.Thread(target=_connect_service, daemon=True,
                         name="SvcConnect").start()

    def _start_watchdog(self):
        """Start a background thread that monitors service health and polls battery.
        If service dies, updates UI to disconnected and attempts restart."""
        def _watchdog():
            import time
            poll_count = 0
            while not self._svc_watchdog_stop.is_set():
                self._svc_watchdog_stop.wait(5)  # check every 5 seconds
                if self._svc_watchdog_stop.is_set():
                    break
                if not self.svc.connected:
                    continue

                poll_count += 1

                # Poll buffered events from service (battery changes, button presses)
                # This is lightweight — just drains a buffer, no HID++ calls
                try:
                    events = self.svc.get_events()
                    for evt in events:
                        evt_name = evt.get("event", "")
                        evt_data = evt.get("data", {})
                        if evt_name == "battery_update" and self._battery_read_cb:
                            self._on_battery_event(evt_data)
                        elif evt_name == "haptic_panel_down":
                            self._on_svc_gesture_down(evt_data)
                        elif evt_name == "device_connected":
                            self._on_svc_connected(evt_data)
                        elif evt_name == "device_disconnected":
                            self._on_svc_disconnected(evt_data)
                except Exception:
                    pass

                # Fallback battery poll every 5 minutes (in case push events missed)
                if poll_count % 60 == 0 and self._battery_read_cb:
                    try:
                        batt = self.svc.read_battery()
                        if batt:
                            self._on_battery_event(batt)
                    except Exception:
                        pass

                # Ping service
                try:
                    result = self.svc.health()
                except Exception:
                    result = None
                if result is None:
                    # Service died
                    print("[Engine] Service health check FAILED — service may have crashed")
                    self.svc.disconnect()
                    if self._connection_change_cb:
                        try:
                            self._connection_change_cb(False)
                        except Exception:
                            pass
                    # Attempt auto-restart
                    print("[Engine] Attempting service restart...")
                    time.sleep(2)
                    svc_path = self._find_and_launch_service()
                    if svc_path:
                        for attempt in range(15):
                            time.sleep(1)
                            if self.svc.connect():
                                h = self.svc.health()
                                svc_v = h.get("version", "?") if h else "?"
                                self.service_version = svc_v if h else ""
                                from core.config import APP_VERSION
                                print(f"[Engine] Service restarted — App v{APP_VERSION}, Service v{svc_v}")
                                self._read_initial_state()
                                break
                        else:
                            print("[Engine] Service restart failed after 15s")
                    else:
                        print("[Engine] Cannot find service exe for restart")

        threading.Thread(target=_watchdog, daemon=True, name="SvcWatchdog").start()

    def _update_scm_path(self):
        """If the service is registered in SCM, update binPath to the current exe.
        This handles the case where the user moved or updated the app folder."""
        import subprocess, sys, os
        CREATE_NO_WINDOW = 0x08000000
        try:
            # Check if service exists in SCM
            result = subprocess.run(
                ["sc", "query", "MasterMice"],
                capture_output=True, timeout=3, creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                return  # not installed as SCM service, nothing to update

            # Find current service exe
            if getattr(sys, "frozen", False):
                app_dir = os.path.dirname(sys.executable)
                svc_path = os.path.join(app_dir, "_internal", "mastermice-svc.exe")
            else:
                root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                svc_path = os.path.join(root, "service", "mastermice-svc.exe")

            svc_path = os.path.abspath(svc_path)
            if not os.path.isfile(svc_path):
                return

            # Update binPath (sc config doesn't need admin if we're just updating path
            # and service is stopped — but it usually does need admin)
            subprocess.run(
                ["sc", "config", "MasterMice", f'binPath= "{svc_path}"'],
                capture_output=True, timeout=5, creationflags=CREATE_NO_WINDOW,
            )
            print(f"[Engine] Updated SCM binPath: {svc_path}")
        except Exception as e:
            print(f"[Engine] SCM path update failed (non-critical): {e}")

    def _kill_old_service(self):
        """Reliably stop any running mastermice-svc.exe — handles both SCM and console.
        Non-interactive, no UAC prompts. Waits for pipe to disappear."""
        import subprocess, time, os
        CREATE_NO_WINDOW = 0x08000000
        stopped = False

        # Strategy 1: sc stop (works if installed as SCM service)
        try:
            result = subprocess.run(
                ["sc", "stop", "MasterMice"],
                timeout=5, capture_output=True, creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                print("[Engine] Stopped SCM service")
                stopped = True
        except Exception:
            pass

        # Strategy 2: taskkill (works for console processes or if sc stop failed)
        if not stopped:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "mastermice-svc.exe"],
                    timeout=5, capture_output=True, creationflags=CREATE_NO_WINDOW,
                )
                print("[Engine] Killed service process via taskkill")
                stopped = True
            except Exception:
                pass

        # Strategy 3: If both failed, try WMI via PowerShell (catches edge cases)
        if not stopped:
            try:
                subprocess.run(
                    ["powershell", "-Command",
                     "Get-Process mastermice-svc -ErrorAction SilentlyContinue | Stop-Process -Force"],
                    timeout=5, capture_output=True, creationflags=CREATE_NO_WINDOW,
                )
                print("[Engine] Killed service via PowerShell")
            except Exception:
                pass

        # Wait for the named pipe to disappear (confirms the old process released resources)
        pipe_path = r'\\.\pipe\MasterMice'
        for i in range(40):  # up to 8 seconds
            try:
                # Try to check if pipe exists by attempting to open it
                import ctypes
                import ctypes.wintypes as wt
                h = ctypes.windll.kernel32.CreateFileW(
                    pipe_path, 0x80000000, 0, None, 3, 0, None)
                if h == ctypes.c_void_p(-1).value or h == 0:
                    # Pipe gone — old service is fully dead
                    print(f"[Engine] Old service pipe released ({i * 0.2:.1f}s)")
                    return
                ctypes.windll.kernel32.CloseHandle(h)
            except Exception:
                return
            time.sleep(0.2)

        print("[Engine] Warning: old service pipe still active after 8s")

    def _ensure_agent_running(self):
        """Ensure an agent process is running. Only launches if not already present.
        Does NOT kill existing agents — they self-manage via KillOldMasterMiceByName.
        If a full restart was needed (service version mismatch), _find_and_launch_service
        handles killing everything."""
        import sys, os, subprocess
        CREATE_NO_WINDOW = 0x08000000

        # Check if agent is already running
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq mastermice-agent.exe", "/NH", "/FO", "CSV"],
                capture_output=True, timeout=3, creationflags=CREATE_NO_WINDOW,
            )
            if b"mastermice-agent.exe" in result.stdout:
                print("[Engine] Agent already running — not relaunching")
                return
        except Exception:
            pass

        # Agent not running — launch it
        if getattr(sys, "frozen", False):
            app_dir = os.path.dirname(sys.executable)
            candidates = [
                os.path.join(app_dir, "_internal", "mastermice-agent.exe"),
                os.path.join(app_dir, "mastermice-agent.exe"),
            ]
        else:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            candidates = [os.path.join(root, "service", "mastermice-agent.exe")]

        for path in candidates:
            path = os.path.abspath(path)
            if os.path.isfile(path):
                try:
                    subprocess.Popen([path], creationflags=CREATE_NO_WINDOW)
                    print(f"[Engine] Agent launched: {path}")
                except Exception as e:
                    print(f"[Engine] Failed to launch agent: {e}")
                break

    def _find_service_exe(self):
        """Return path to mastermice-svc.exe, or None."""
        import sys, os
        if getattr(sys, "frozen", False):
            app_dir = os.path.dirname(sys.executable)
            for p in [os.path.join(app_dir, "_internal", "mastermice-svc.exe"),
                       os.path.join(app_dir, "mastermice-svc.exe")]:
                if os.path.isfile(p):
                    return os.path.abspath(p)
        else:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            p = os.path.join(root, "service", "mastermice-svc.exe")
            if os.path.isfile(p):
                return os.path.abspath(p)
        return None

    def _find_and_launch_service(self):
        """Find and launch mastermice-svc.exe + mastermice-agent.exe.
        Kills any existing agent first to prevent duplicate instances."""
        import sys, os, subprocess
        CREATE_NO_WINDOW = 0x08000000

        # Kill any existing agent to prevent duplicates
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "mastermice-agent.exe"],
                timeout=3, capture_output=True, creationflags=CREATE_NO_WINDOW,
            )
        except Exception:
            pass

        if getattr(sys, "frozen", False):
            app_dir = os.path.dirname(sys.executable)
            svc_candidates = [
                os.path.join(app_dir, "_internal", "mastermice-svc.exe"),
                os.path.join(app_dir, "mastermice-svc.exe"),
            ]
            agent_candidates = [
                os.path.join(app_dir, "_internal", "mastermice-agent.exe"),
                os.path.join(app_dir, "mastermice-agent.exe"),
            ]
        else:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            svc_candidates = [os.path.join(root, "service", "mastermice-svc.exe")]
            agent_candidates = [os.path.join(root, "service", "mastermice-agent.exe")]

        # Go binaries write to the shared log file THEMSELVES
        # (via internal/logging package). No stdout redirect needed.
        svc_path = None
        for path in svc_candidates:
            path = os.path.abspath(path)
            if os.path.isfile(path):
                try:
                    subprocess.Popen([path],
                                     creationflags=CREATE_NO_WINDOW)
                    print(f"[Engine] Launched service: {path}")
                    svc_path = path
                except Exception as e:
                    print(f"[Engine] Failed to launch service: {e}")
                break

        # Launch agent — writes to shared log file itself
        for path in agent_candidates:
            path = os.path.abspath(path)
            if os.path.isfile(path):
                try:
                    subprocess.Popen([path],
                                     creationflags=CREATE_NO_WINDOW)
                    print(f"[Engine] Launched agent: {path}")
                except Exception as e:
                    print(f"[Engine] Failed to launch agent: {e}")
                break

        return svc_path

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

            # Apply saved haptic config on connect
            if connected:
                self._apply_haptic_on_connect()

    def _apply_haptic_on_connect(self):
        """Apply saved haptic config when device connects via service."""
        try:
            settings = self.cfg.get("settings", {})
            enabled = settings.get("haptic_enabled", True)
            intensity = settings.get("haptic_intensity", 60)
            if self.svc.connected:
                self.svc.set_haptic(enabled, intensity)
                print(f"[Engine] Applied haptic config: "
                      f"{'ON' if enabled else 'OFF'} intensity={intensity}%")
        except Exception as e:
            print(f"[Engine] Haptic config apply failed: {e}")

    def stop(self):
        if hasattr(self, '_svc_watchdog_stop'):
            self._svc_watchdog_stop.set()
        self._app_detector.stop()
        self.hook.stop()
        self.svc.disconnect()
