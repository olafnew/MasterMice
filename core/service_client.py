"""
service_client.py — Named pipe client for the MasterMice Go service.

Replaces direct HidGestureListener calls with IPC over \\.\pipe\MasterMice.
Thread-safe: all public methods can be called from any thread.
"""

import json
import os
import sys
import threading
import time


PIPE_NAME = r'\\.\pipe\MasterMice'


class ServiceClient:
    """Named pipe client for MasterMice Go service.

    Usage:
        svc = ServiceClient()
        svc.connect()
        svc.on_event("battery_update", lambda data: print(data))
        result = svc.request("read_battery")
        # result = {"level": 85, "charging": False}
    """

    def __init__(self):
        self._pipe = None
        self._lock = threading.Lock()
        self._next_id = 1
        self._connected = False
        self._event_callbacks = {}
        self._reader_thread = None
        self._running = False
        # Pending responses keyed by request ID
        self._pending = {}
        self._pending_lock = threading.Lock()

    @property
    def connected(self):
        return self._connected

    def connect(self, timeout=5.0):
        """Connect to the MasterMice service pipe.
        Returns True on success, False on failure."""
        if self._connected:
            return True

        try:
            # On Windows, named pipes are opened as files
            self._pipe = open(PIPE_NAME, 'r+b', buffering=0)
            self._connected = True
            self._running = True

            # Start background reader for events
            self._reader_thread = threading.Thread(
                target=self._reader_loop, daemon=True, name="SvcPipeReader")
            self._reader_thread.start()

            print(f"[ServiceClient] Connected to {PIPE_NAME}")
            return True
        except FileNotFoundError:
            print(f"[ServiceClient] Service not running ({PIPE_NAME} not found)")
            return False
        except PermissionError:
            print(f"[ServiceClient] Permission denied on {PIPE_NAME}")
            return False
        except Exception as e:
            print(f"[ServiceClient] Connect failed: {e}")
            return False

    def disconnect(self):
        """Close the pipe connection."""
        self._running = False
        self._connected = False
        if self._pipe:
            try:
                self._pipe.close()
            except Exception:
                pass
            self._pipe = None

    def on_event(self, event_name, callback):
        """Register a callback for service events.
        callback receives a dict with the event data."""
        self._event_callbacks[event_name] = callback

    def request(self, cmd, timeout=5.0, **params):
        """Send a command to the service and wait for the response.
        Returns the response data dict, or None on error.

        Usage:
            result = svc.request("read_battery")
            result = svc.request("set_dpi", value=2000)
        """
        if not self._connected:
            print(f"[ServiceClient] Not connected — cannot send {cmd}")
            return None

        with self._lock:
            msg_id = self._next_id
            self._next_id += 1

        req = {"id": msg_id, "cmd": cmd}
        if params:
            req["params"] = params

        # Set up pending response slot
        event = threading.Event()
        with self._pending_lock:
            self._pending[msg_id] = {"event": event, "response": None}

        # Send request
        try:
            line = json.dumps(req) + "\n"
            with self._lock:
                self._pipe.write(line.encode("utf-8"))
                self._pipe.flush()
        except Exception as e:
            print(f"[ServiceClient] Write failed: {e}")
            with self._pending_lock:
                self._pending.pop(msg_id, None)
            self._handle_disconnect()
            return None

        # Wait for response
        if not event.wait(timeout):
            print(f"[ServiceClient] Request {cmd} (id={msg_id}) timed out")
            with self._pending_lock:
                self._pending.pop(msg_id, None)
            return None

        with self._pending_lock:
            entry = self._pending.pop(msg_id, None)

        if entry is None:
            return None

        resp = entry["response"]
        if resp is None:
            return None

        if not resp.get("ok", False):
            err = resp.get("error", "unknown error")
            print(f"[ServiceClient] {cmd} failed: {err}")
            return None

        return resp.get("data", {})

    # ── Convenience methods ───────────────────────────────────────

    def read_battery(self):
        """Read battery. Returns {"level": int, "charging": bool} or None."""
        return self.request("read_battery")

    def read_dpi(self):
        """Read DPI. Returns {"dpi": int} or None."""
        return self.request("read_dpi")

    def set_dpi(self, value):
        """Set DPI. Returns True on success."""
        return self.request("set_dpi", value=value) is not None

    def get_smart_shift(self):
        """Get SmartShift. Returns {"threshold", "force", "enabled", "mode"} or None."""
        return self.request("get_smartshift")

    def set_smart_shift(self, threshold, force=50, enabled=True):
        """Set SmartShift. Returns True on success."""
        return self.request("set_smartshift",
                            threshold=threshold, force=force, enabled=enabled) is not None

    def get_hires_wheel(self):
        """Get HiRes wheel. Returns {"hires", "invert", "target"} or None."""
        return self.request("get_hires_wheel")

    def set_hires_wheel(self, hires=None, invert=None):
        """Set HiRes wheel. Returns True on success."""
        params = {}
        if hires is not None:
            params["hires"] = bool(hires)
        if invert is not None:
            params["invert"] = bool(invert)
        return self.request("set_hires_wheel", **params) is not None

    def get_smooth_scroll(self):
        """Get smooth scroll. Returns {"enabled": bool} or None."""
        return self.request("get_smooth_scroll")

    def set_smooth_scroll(self, enabled):
        """Set smooth scroll. Returns True on success."""
        return self.request("set_smooth_scroll", enabled=bool(enabled)) is not None

    def set_haptic(self, enabled, intensity):
        """Set haptic config. Returns True on success."""
        return self.request("set_haptic",
                            enabled=bool(enabled), intensity=int(intensity)) is not None

    def haptic_trigger(self, pulse_type=0x04):
        """Trigger haptic pulse. Returns True on success."""
        return self.request("haptic_trigger", pulse_type=pulse_type) is not None

    def get_status(self):
        """Get full device status. Returns dict or None."""
        return self.request("get_status")

    def get_capabilities(self):
        """Get device capabilities. Returns dict or None."""
        return self.request("get_capabilities")

    def health(self):
        """Get service health. Returns dict or None."""
        return self.request("health")

    # ── Background reader ─────────────────────────────────────────

    def _reader_loop(self):
        """Background thread: reads JSON lines from the pipe.
        Dispatches responses to pending requests and events to callbacks."""
        buf = b""
        while self._running:
            try:
                ch = self._pipe.read(1)
                if not ch:
                    break
                if ch == b'\n':
                    if buf:
                        self._dispatch(buf)
                    buf = b""
                else:
                    buf += ch
            except Exception:
                break

        self._handle_disconnect()

    def _dispatch(self, raw):
        """Parse a JSON line and route it to the right handler."""
        try:
            msg = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        # Event (no "id" field)
        if "event" in msg:
            event_name = msg["event"]
            data = msg.get("data", {})
            cb = self._event_callbacks.get(event_name)
            if cb:
                try:
                    cb(data)
                except Exception as e:
                    print(f"[ServiceClient] Event callback error: {e}")
            return

        # Response (has "id" field)
        msg_id = msg.get("id")
        if msg_id is not None:
            with self._pending_lock:
                entry = self._pending.get(msg_id)
                if entry:
                    entry["response"] = msg
                    entry["event"].set()

    def _handle_disconnect(self):
        """Handle pipe disconnection."""
        if not self._connected:
            return
        self._connected = False
        print("[ServiceClient] Disconnected from service")

        # Wake up all pending requests
        with self._pending_lock:
            for entry in self._pending.values():
                entry["event"].set()
            self._pending.clear()
