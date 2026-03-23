"""
service_client.py — Named pipe client for the MasterMice Go service.

Uses pure ctypes (CreateFileW / ReadFile / WriteFile) for Windows named
pipe I/O. Synchronous request/response — no background reader thread.

IMPORTANT: Windows synchronous pipe handles serialize all I/O.
ReadFile and WriteFile CANNOT run concurrently from different threads.
All pipe I/O must be sequential: write request, read response.
"""

import ctypes
import ctypes.wintypes as wt
import json
import threading

PIPE_NAME = r'\\.\pipe\MasterMice'

# ── Windows API ───────────────────────────────────────────────────
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_MORE_DATA = 234

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

kernel32.CreateFileW.restype = wt.HANDLE
kernel32.CreateFileW.argtypes = [
    wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
    wt.DWORD, wt.DWORD, wt.HANDLE,
]
kernel32.ReadFile.restype = wt.BOOL
kernel32.ReadFile.argtypes = [
    wt.HANDLE, ctypes.c_char_p, wt.DWORD,
    ctypes.POINTER(wt.DWORD), ctypes.c_void_p,
]
kernel32.WriteFile.restype = wt.BOOL
kernel32.WriteFile.argtypes = [
    wt.HANDLE, ctypes.c_char_p, wt.DWORD,
    ctypes.POINTER(wt.DWORD), ctypes.c_void_p,
]
kernel32.CloseHandle.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]


def _pipe_write(handle, data: bytes):
    """Write bytes to pipe. Raises OSError on failure."""
    written = wt.DWORD(0)
    ok = kernel32.WriteFile(handle, data, len(data), ctypes.byref(written), None)
    if not ok:
        raise OSError(f"WriteFile error {ctypes.get_last_error()}")


def _pipe_read_line(handle) -> bytes:
    """Read bytes from pipe until a newline is found. Returns the line (without newline)."""
    buf = b""
    one = ctypes.create_string_buffer(1)
    read_n = wt.DWORD(0)
    while True:
        ok = kernel32.ReadFile(handle, one, 1, ctypes.byref(read_n), None)
        if not ok or read_n.value == 0:
            if buf:
                return buf
            raise OSError(f"ReadFile error {ctypes.get_last_error()}")
        ch = one.raw[0:1]
        if ch == b'\n':
            return buf
        buf += ch


class ServiceClient:
    """Named pipe client for MasterMice Go service.

    All pipe I/O is synchronous and serialized via a lock.
    No background reader thread — Windows synchronous pipes
    don't support concurrent ReadFile + WriteFile.
    """

    def __init__(self):
        self._handle = None
        self._pipe_lock = threading.Lock()  # serializes ALL pipe I/O
        self._next_id = 1
        self._connected = False
        self._event_callbacks = {}

    @property
    def connected(self):
        return self._connected

    def connect(self, timeout=5.0):
        """Connect to the MasterMice service pipe."""
        if self._connected:
            return True
        try:
            h = kernel32.CreateFileW(
                PIPE_NAME,
                GENERIC_READ | GENERIC_WRITE,
                0, None, OPEN_EXISTING, 0, None,
            )
            if h == INVALID_HANDLE_VALUE or h is None or h == 0:
                err = ctypes.get_last_error()
                if err == 2:
                    print(f"[ServiceClient] Service not running ({PIPE_NAME})")
                else:
                    print(f"[ServiceClient] CreateFileW failed: error {err}")
                return False

            self._handle = h
            self._connected = True

            # Verify the pipe works
            try:
                result = self._raw_request({"id": 0, "cmd": "health"})
                if result and result.get("ok"):
                    print(f"[ServiceClient] Connected to {PIPE_NAME} (health OK)")
                else:
                    print(f"[ServiceClient] Connected to {PIPE_NAME} (health: {result})")
            except Exception as e:
                print(f"[ServiceClient] Connected but health failed: {e}")

            return True
        except Exception as e:
            print(f"[ServiceClient] Connect failed: {e}")
            return False

    def disconnect(self):
        """Close the pipe connection."""
        self._connected = False
        h = self._handle
        self._handle = None
        if h is not None:
            try:
                kernel32.CloseHandle(h)
            except Exception:
                pass

    def on_event(self, event_name, callback):
        """Register a callback for service events (for future use with async reader)."""
        self._event_callbacks[event_name] = callback

    def _raw_request(self, req_dict) -> dict:
        """Send a JSON request and read the JSON response. Must hold no locks.
        Returns the parsed response dict."""
        raw = (json.dumps(req_dict) + "\n").encode("utf-8")
        _pipe_write(self._handle, raw)
        resp_line = _pipe_read_line(self._handle)
        return json.loads(resp_line.decode("utf-8"))

    def request(self, cmd, timeout=5.0, **params):
        """Send a command and wait for the response.
        Returns the response data dict, or None on error.
        Thread-safe — serialized via pipe lock."""
        if not self._connected or self._handle is None:
            return None

        msg_id = self._next_id
        self._next_id += 1

        req = {"id": msg_id, "cmd": cmd}
        if params:
            req["params"] = params

        try:
            with self._pipe_lock:
                resp = self._raw_request(req)
        except Exception as e:
            print(f"[ServiceClient] {cmd} failed: {e}")
            self._connected = False
            return None

        if not resp.get("ok", False):
            err = resp.get("error", "unknown")
            print(f"[ServiceClient] {cmd}: {err}")
            return None

        return resp.get("data", {})

    # ── Convenience methods ───────────────────────────────────────

    def read_battery(self):
        return self.request("read_battery")

    def read_dpi(self):
        return self.request("read_dpi")

    def set_dpi(self, value):
        return self.request("set_dpi", value=value) is not None

    def get_smart_shift(self):
        return self.request("get_smartshift")

    def set_smart_shift(self, threshold, force=50, enabled=True):
        return self.request("set_smartshift",
                            threshold=threshold, force=force, enabled=enabled) is not None

    def get_hires_wheel(self):
        return self.request("get_hires_wheel")

    def set_hires_wheel(self, hires=None, invert=None):
        p = {}
        if hires is not None:
            p["hires"] = bool(hires)
        if invert is not None:
            p["invert"] = bool(invert)
        return self.request("set_hires_wheel", **p) is not None

    def get_smooth_scroll(self):
        return self.request("get_smooth_scroll")

    def set_smooth_scroll(self, enabled):
        return self.request("set_smooth_scroll", enabled=bool(enabled)) is not None

    def set_haptic(self, enabled, intensity):
        return self.request("set_haptic",
                            enabled=bool(enabled), intensity=int(intensity)) is not None

    def haptic_trigger(self, pulse_type=0x04):
        return self.request("haptic_trigger", pulse_type=pulse_type) is not None

    def get_status(self):
        return self.request("get_status")

    def get_capabilities(self):
        return self.request("get_capabilities")

    def health(self):
        return self.request("health")
