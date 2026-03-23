"""
Configuration manager — loads/saves button mappings to a JSON file.
Supports per-application profiles (for future use).
"""

APP_VERSION = "0.392"
APP_NAME = "MasterMice"

import json
import os
import sys
import shutil

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MasterMice")
if sys.platform == "darwin":
    CONFIG_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "MasterMice")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# ── Migrate from old "Mouser" config path if it exists ──────────────
_OLD_CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Mouser")
if sys.platform == "darwin":
    _OLD_CONFIG_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Mouser")
_OLD_CONFIG_FILE = os.path.join(_OLD_CONFIG_DIR, "config.json")

if os.path.exists(_OLD_CONFIG_FILE) and not os.path.exists(CONFIG_FILE):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    shutil.copy2(_OLD_CONFIG_FILE, CONFIG_FILE)
    # Also copy log file if it exists
    _old_log = os.path.join(_OLD_CONFIG_DIR, "mouser.log")
    _new_log = os.path.join(CONFIG_DIR, "mastermice.log")
    if os.path.exists(_old_log) and not os.path.exists(_new_log):
        shutil.copy2(_old_log, _new_log)
    print(f"[MasterMice] Migrated config from {_OLD_CONFIG_DIR}")

# Which mouse events map to which friendly button names
# Order matches the physical layout (top → side → thumb)
BUTTON_NAMES = {
    "left_click":    "Left Click",
    "right_click":   "Right Click",
    "scroll_up":     "Scroll Up",
    "scroll_down":   "Scroll Down",
    "middle":        "Middle Button",
    "mode_shift":    "Spin Mode",
    "xbutton2":      "Forward Button",
    "xbutton1":      "Back Button",
    "gesture":       "Gesture Button",
    "thumb_wheel":   "Thumb Wheel",
    "haptic_panel":  "Haptic Sense Panel",
}

# Per-device profiles — each device lists its display name and which
# buttons from BUTTON_NAMES are physically present on that mouse.
DEVICE_PROFILES = {
    "mx_master_3s": {
        "name": "MX Master 3/3S",
        "name_matches": ["master 3"],   # substring match on DEVICE_NAME (lowercase)
        "buttons": [
            "left_click", "right_click",
            "scroll_up", "scroll_down", "middle", "mode_shift",
            "xbutton2", "xbutton1", "gesture", "thumb_wheel",
        ],
        # HID++ feature IDs for profile-driven discovery
        "battery_feature_id": 0x1000,
        "battery_soc_while_charging": False,   # reports 0% while charging
        "smartshift_feature_id": 0x2110,
        "smartshift_version": 1,
        "smartshift_has_force": False,
        "has_haptics": False,
        "haptic_feature_id": None,
        "dpi_max": 4000,
        "dpi_flag": 0x00,
        "smooth_scroll_on_value": 0x03,
    },
    "mx_master_4": {
        "name": "MX Master 4",
        "name_matches": ["master 4"],
        "buttons": [
            "left_click", "right_click",
            "scroll_up", "scroll_down", "middle", "mode_shift",
            "xbutton2", "xbutton1", "gesture", "thumb_wheel",
            "haptic_panel",
        ],
        "battery_feature_id": 0x1004,
        "battery_soc_while_charging": True,
        "smartshift_feature_id": 0x2111,
        "smartshift_version": 2,
        "smartshift_has_force": True,
        "has_haptics": True,
        "haptic_feature_id": 0xB019,
        "dpi_max": 8000,
        "dpi_flag": 0x01,
        "smooth_scroll_on_value": 0x01,
    },
}


def get_device_buttons(cfg):
    """Return the button keys list for the currently selected device model."""
    model = cfg.get("settings", {}).get("mouse_model", "")
    profile = DEVICE_PROFILES.get(model)
    if profile:
        return profile["buttons"]
    # Fallback: 3/3S button set
    return ["left_click", "right_click", "scroll_up", "scroll_down",
            "middle", "mode_shift", "xbutton2", "xbutton1",
            "gesture", "thumb_wheel"]


def get_device_name(cfg):
    """Return the display name for the currently selected device model."""
    model = cfg.get("settings", {}).get("mouse_model", "")
    profile = DEVICE_PROFILES.get(model)
    return profile["name"] if profile else ""

GESTURE_DIRECTION_BUTTONS = (
    "gesture_left",
    "gesture_right",
    "gesture_up",
    "gesture_down",
)

PROFILE_BUTTON_NAMES = {
    **BUTTON_NAMES,
    "gesture_left":  "Gesture swipe left",
    "gesture_right": "Gesture swipe right",
    "gesture_up":    "Gesture swipe up",
    "gesture_down":  "Gesture swipe down",
}

# Maps config button keys to the MouseEvent types they correspond to
BUTTON_TO_EVENTS = {
    "left_click":    ("left_down", "left_up"),
    "right_click":   ("right_down", "right_up"),
    "scroll_up":     ("scroll_up",),
    "scroll_down":   ("scroll_down",),
    "middle":        ("middle_down", "middle_up"),
    "mode_shift":    ("mode_shift_click",),
    "gesture":       ("gesture_click",),
    "gesture_left":  ("gesture_swipe_left",),
    "gesture_right": ("gesture_swipe_right",),
    "gesture_up":    ("gesture_swipe_up",),
    "gesture_down":  ("gesture_swipe_down",),
    "xbutton1":      ("xbutton1_down", "xbutton1_up"),
    "xbutton2":      ("xbutton2_down", "xbutton2_up"),
    "thumb_wheel":   ("hscroll_left", "hscroll_right"),
    "haptic_panel":  ("haptic_panel_click",),
}

DEFAULT_CONFIG = {
    "version": 4,
    "active_profile": "default",
    "profiles": {
        "default": {
            "label": "Default (All Apps)",
            "apps": [],          # empty = all apps (fallback profile)
            "mappings": {
                "left_click": "none",
                "right_click": "none",
                "scroll_up": "none",
                "scroll_down": "none",
                "middle": "none",
                "mode_shift": "none",
                "gesture": "none",
                "gesture_left": "none",
                "gesture_right": "none",
                "gesture_up": "none",
                "gesture_down": "none",
                "xbutton1": "none",
                "xbutton2": "none",
                "thumb_wheel": "none",
                "haptic_panel": "none",
            },
        }
    },
    "settings": {
        "start_minimized": True,
        "start_with_windows": False,
        "hscroll_threshold": 1,
        "invert_hscroll": False,  # swap horizontal scroll directions
        "invert_vscroll": False,  # swap vertical scroll directions
        "dpi": 1000,              # pointer speed / DPI setting
        "gesture_threshold": 50,
        "gesture_deadzone": 40,
        "gesture_timeout_ms": 3000,
        "gesture_cooldown_ms": 500,
        "debug_mode": False,
        "mouse_model": "",
        "log_level": "errors",
        "log_max_kb": 1024,
    },
}

# Known applications for per-app profiles
# Note: Modern UWP apps appear as their package exe (e.g. Microsoft.Media.Player.exe)
# thanks to ApplicationFrameHost child-window resolution in app_detector.py.
# icon values must match filenames in images/ (without extension for png,
# or with extension for non-png like .webp)
KNOWN_APPS = {
    # Windows apps
    "msedge.exe":                {"label": "Microsoft Edge",       "icon": ""},
    "chrome.exe":                {"label": "Google Chrome",        "icon": "chrom"},
    "Microsoft.Media.Player.exe":{"label": "Windows Media Player", "icon": "media.webp"},
    "wmplayer.exe":              {"label": "Windows Media Player (Classic)", "icon": "media.webp"},
    "vlc.exe":                   {"label": "VLC Media Player",     "icon": "VLC"},
    "Code.exe":                  {"label": "Visual Studio Code",   "icon": "VSCODE"},
    # macOS apps (executable names from NSWorkspace)
    "Safari":                    {"label": "Safari",               "icon": ""},
    "Google Chrome":             {"label": "Google Chrome",        "icon": "chrom"},
    "VLC":                       {"label": "VLC Media Player",     "icon": "VLC"},
    "Code":                      {"label": "Visual Studio Code",   "icon": "VSCODE"},
    "Finder":                    {"label": "Finder",               "icon": ""},
}


def get_icon_for_exe(exe_name: str) -> str:
    """Return the icon image filename (relative to images/) for an exe, or ''."""
    info = KNOWN_APPS.get(exe_name, {})
    icon = info.get("icon", "")
    if not icon:
        return ""
    # If icon already has extension, use as-is; otherwise assume .png
    if "." in icon:
        return icon
    return icon + ".png"


def ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config():
    """Load config from disk, or return defaults if none exists."""
    ensure_config_dir()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # Merge any missing keys from default
            cfg = _migrate(cfg)
            cfg = _merge_defaults(cfg, DEFAULT_CONFIG)
            return cfg
        except Exception as e:
            print(f"[Config] Error loading config: {e}")
    return json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy


def save_config(cfg):
    """Persist config to disk."""
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_active_mappings(cfg):
    """Return the mappings dict for the currently active profile."""
    profile_name = cfg.get("active_profile", "default")
    profiles = cfg.get("profiles", {})
    profile = profiles.get(profile_name, profiles.get("default", {}))
    return profile.get("mappings", DEFAULT_CONFIG["profiles"]["default"]["mappings"])


def set_mapping(cfg, button, action_id, profile=None):
    """Set a mapping for a button in the given profile (or active profile)."""
    if profile is None:
        profile = cfg.get("active_profile", "default")
    cfg["profiles"].setdefault(profile, {
        "label": profile,
        "mappings": dict(DEFAULT_CONFIG["profiles"]["default"]["mappings"]),
    })
    cfg["profiles"][profile]["mappings"][button] = action_id
    save_config(cfg)
    return cfg


def create_profile(cfg, name, label=None, copy_from="default", apps=None):
    """Create a new profile, optionally copying from an existing one."""
    if label is None:
        label = name
    source = cfg["profiles"].get(copy_from, cfg["profiles"].get("default", {}))
    cfg["profiles"][name] = {
        "label": label,
        "apps": apps if apps is not None else [],
        "mappings": dict(source.get("mappings", {})),
    }
    save_config(cfg)
    return cfg


def delete_profile(cfg, name):
    """Delete a profile (cannot delete 'default')."""
    if name == "default":
        return cfg
    cfg["profiles"].pop(name, None)
    if cfg["active_profile"] == name:
        cfg["active_profile"] = "default"
    save_config(cfg)
    return cfg


def get_profile_for_app(cfg, exe_name):
    """Return the profile name that matches the given executable, or 'default'."""
    for pname, pdata in cfg.get("profiles", {}).items():
        if exe_name and exe_name.lower() in [a.lower() for a in pdata.get("apps", [])]:
            return pname
    return "default"


def _migrate(cfg):
    """Migrate config from older versions to current."""
    version = cfg.get("version", 1)
    if version < 2:
        # v1 → v2:  add 'apps' list to each profile, new settings keys
        for pdata in cfg.get("profiles", {}).values():
            pdata.setdefault("apps", [])
        cfg.setdefault("settings", {})
        cfg["settings"].setdefault("invert_hscroll", False)
        cfg["settings"].setdefault("invert_vscroll", False)
        cfg["settings"].setdefault("dpi", 1000)
        cfg["version"] = 2

    if version < 3:
        settings = cfg.setdefault("settings", {})
        settings.setdefault("gesture_threshold", 50)
        settings.setdefault("gesture_deadzone", 40)
        settings.setdefault("gesture_timeout_ms", 3000)
        settings.setdefault("gesture_cooldown_ms", 500)
        for pdata in cfg.get("profiles", {}).values():
            mappings = pdata.setdefault("mappings", {})
            mappings.setdefault("gesture", "none")
            for key in GESTURE_DIRECTION_BUTTONS:
                mappings.setdefault(key, "none")
        cfg["version"] = 3

    if version < 4:
        # v3 → v4: fix xbutton1/xbutton2 defaults from alt_tab to none
        for pdata in cfg.get("profiles", {}).values():
            mappings = pdata.get("mappings", {})
            if mappings.get("xbutton1") == "alt_tab":
                mappings["xbutton1"] = "none"
            if mappings.get("xbutton2") == "alt_tab":
                mappings["xbutton2"] = "none"
        cfg["version"] = 4

    cfg.setdefault("settings", {})
    cfg["settings"].setdefault("debug_mode", False)

    # Always migrate old wmplayer.exe → Microsoft.Media.Player.exe in profile apps
    for pdata in cfg.get("profiles", {}).values():
        apps = pdata.get("apps", [])
        for i, a in enumerate(apps):
            if a.lower() == "wmplayer.exe":
                apps[i] = "Microsoft.Media.Player.exe"

    return cfg


def _merge_defaults(cfg, defaults):
    """Recursively merge missing keys from defaults into cfg."""
    for key, val in defaults.items():
        if key not in cfg:
            cfg[key] = val
        elif isinstance(val, dict) and isinstance(cfg.get(key), dict):
            _merge_defaults(cfg[key], val)
    return cfg
