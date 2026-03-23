"""
MasterMice logging — writes to a rotating log file in the config directory.
Captures stdout/stderr so existing print() statements are logged too.
Supports three levels: "disabled", "errors", "verbose".
Log file auto-rotates when it reaches the configured max size (default 1024 KB).
"""

import io
import logging
import logging.handlers
import os
import sys

from core.config import CONFIG_DIR

LOG_FILE = os.path.join(CONFIG_DIR, "mastermice.log")
DEFAULT_MAX_KB = 1024

_root = logging.getLogger("mastermice")
_handler = None
_original_stdout = sys.stdout
_original_stderr = sys.stderr


class _TeeStream(io.TextIOBase):
    """Writes to both the original stream and a logging.Logger."""

    def __init__(self, original, logger, level):
        self._original = original
        self._logger = logger
        self._level = level
        self._buf = ""

    def write(self, text):
        if self._original:
            self._original.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if line:
                self._logger.log(self._level, line)
        return len(text)

    def flush(self):
        if self._original:
            self._original.flush()
        if self._buf.strip():
            self._logger.log(self._level, self._buf.strip())
            self._buf = ""


def setup(level_str="errors", max_kb=DEFAULT_MAX_KB):
    """Initialize or reconfigure logging with rotating file handler."""
    global _handler

    os.makedirs(CONFIG_DIR, exist_ok=True)

    # Remove previous handler
    if _handler:
        _root.removeHandler(_handler)
        _handler.close()
        _handler = None

    if level_str == "disabled":
        _root.setLevel(logging.CRITICAL + 1)
        sys.stdout = _original_stdout
        sys.stderr = _original_stderr
        return

    level = logging.ERROR if level_str == "errors" else logging.DEBUG
    _root.setLevel(level)

    # RotatingFileHandler: rotates when file exceeds maxBytes,
    # keeps 1 backup (.log.1) so latest logs are always in .log
    _handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=max(64, max_kb) * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    _handler.setLevel(level)
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    _root.addHandler(_handler)

    # Redirect stdout/stderr so print() goes to log file too
    sys.stdout = _TeeStream(_original_stdout, logging.getLogger("mastermice.stdout"), logging.INFO)
    sys.stderr = _TeeStream(_original_stderr, logging.getLogger("mastermice.stderr"), logging.ERROR)


def get_log_content(max_lines=500):
    """Read the last N lines from the log file for the in-app viewer."""
    if not os.path.exists(LOG_FILE):
        return "(no log file yet)"
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:])
    except Exception as e:
        return f"(error reading log: {e})"


def get_log_path():
    """Return the absolute path to the log file."""
    return LOG_FILE
