"""
pipe_test.py — Test client for MasterMice service named pipe IPC.
Connects to \\.\pipe\MasterMice and sends JSON-line commands.

Usage:
    python pipe_test.py                  # interactive mode
    python pipe_test.py read_battery     # single command
    python pipe_test.py set_dpi 2000     # command with param
"""

VERSION = "1.0"

import json
import sys
import threading
import time


def connect_pipe():
    """Open the MasterMice named pipe."""
    pipe_path = r'\\.\pipe\MasterMice'
    try:
        # On Windows, named pipes are opened as regular files
        pipe = open(pipe_path, 'r+b', buffering=0)
        return pipe
    except FileNotFoundError:
        print(f"[ERROR] Pipe not found: {pipe_path}")
        print("        Is mastermice-svc.exe running?")
        sys.exit(1)
    except PermissionError:
        print(f"[ERROR] Permission denied: {pipe_path}")
        sys.exit(1)


def send_request(pipe, cmd, params=None):
    """Send a JSON-line request and return the response."""
    msg_id = int(time.time() * 1000) % 100000
    req = {"id": msg_id, "cmd": cmd}
    if params:
        req["params"] = params

    line = json.dumps(req) + "\n"
    pipe.write(line.encode('utf-8'))
    pipe.flush()

    # Read response line
    resp_line = b""
    while True:
        ch = pipe.read(1)
        if not ch or ch == b'\n':
            break
        resp_line += ch

    if not resp_line:
        return None

    resp = json.loads(resp_line.decode('utf-8'))
    return resp


def event_listener(pipe):
    """Background thread that reads events from the pipe."""
    buf = b""
    while True:
        try:
            ch = pipe.read(1)
            if not ch:
                break
            if ch == b'\n':
                if buf:
                    msg = json.loads(buf.decode('utf-8'))
                    if 'event' in msg:
                        print(f"\n[EVENT] {msg['event']}: {msg.get('data', {})}")
                        print("> ", end="", flush=True)
                buf = b""
            else:
                buf += ch
        except Exception:
            break


def interactive(pipe):
    """Interactive command loop."""
    print(f"[pipe_test] v{VERSION} — Connected to MasterMice service")
    print("[COMMANDS] health | battery | dpi | set_dpi <val> | smartshift |"
          " set_ss <thresh> | hires | smooth | status | quit\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ("quit", "exit", "q"):
            break

        params = None
        if cmd == "set_dpi" and len(parts) > 1:
            params = {"value": int(parts[1])}
            cmd = "set_dpi"
        elif cmd == "set_ss" and len(parts) > 1:
            params = {"threshold": int(parts[1]), "enabled": True}
            cmd = "set_smartshift"
        elif cmd == "ss_off":
            params = {"threshold": 10, "enabled": False}
            cmd = "set_smartshift"
        elif cmd == "hires_on":
            params = {"hires": True}
            cmd = "set_hires_wheel"
        elif cmd == "hires_off":
            params = {"hires": False}
            cmd = "set_hires_wheel"
        elif cmd == "smooth_on":
            params = {"enabled": True}
            cmd = "set_smooth_scroll"
        elif cmd == "smooth_off":
            params = {"enabled": False}
            cmd = "set_smooth_scroll"
        elif cmd in ("battery", "batt"):
            cmd = "read_battery"
        elif cmd == "dpi":
            cmd = "read_dpi"
        elif cmd == "smartshift":
            cmd = "get_smartshift"
        elif cmd == "hires":
            cmd = "get_hires_wheel"
        elif cmd == "smooth":
            cmd = "get_smooth_scroll"
        elif cmd == "status":
            cmd = "get_status"

        resp = send_request(pipe, cmd, params)
        if resp:
            if resp.get("ok"):
                data = resp.get("data", {})
                if data:
                    for k, v in data.items():
                        print(f"  {k}: {v}")
                else:
                    print("  OK")
            else:
                print(f"  ERROR: {resp.get('error', 'unknown')}")
        else:
            print("  [no response]")


def single_command(pipe, args):
    """Execute a single command and exit."""
    cmd = args[0]
    params = None

    if cmd == "set_dpi" and len(args) > 1:
        params = {"value": int(args[1])}
    elif cmd == "set_smartshift" and len(args) > 1:
        params = {"threshold": int(args[1]), "enabled": True}

    resp = send_request(pipe, cmd, params)
    if resp:
        print(json.dumps(resp, indent=2))
    else:
        print("[no response]")


def main():
    pipe = connect_pipe()

    if len(sys.argv) > 1:
        single_command(pipe, sys.argv[1:])
    else:
        interactive(pipe)

    pipe.close()


if __name__ == "__main__":
    main()
