# MasterMice — Claude Code Instructions

## CRITICAL: Do NOT Build Unless Explicitly Asked

- **NEVER** build, compile, or run PyInstaller unless the user explicitly says "build", "compile", or "create a build"
- Discussion, planning, code changes, and analysis do NOT trigger a build
- The user will clearly command when to build — do not assume

## Versioning Rules (MANDATORY)

- **Every build MUST have a unique version number.** No two builds share a version.
- **Bug/glitch fixes:** increment the sub-version: 0.39 → 0.391 → 0.392
- **New features** (buttons, icons, UI changes, new settings): increment the minor version: 0.39 → 0.40 → 0.41
- Version is stored in TWO places: `APP_VERSION` in `core/config.py` AND `distpath` in `MasterMice.spec`
- **ALL diagnostic tools** must also have a VERSION string displayed on startup

## Build Rules (MANDATORY — when user asks to build)

- **ALWAYS** bump version (see Versioning Rules above) before building
- **ALWAYS** update `CHANGELOG.txt` with what changed (new features, fixes, etc.)
- **ALWAYS** build with PyInstaller after code changes: `.venv/Scripts/pyinstaller MasterMice.spec --noconfirm`
- Build output goes to `dist/MasterMice {version}/`
- **NEVER** forget any of these three steps when the user asks to build
- Console is currently TRUE (debug mode) — do NOT switch to False until explicitly told

## QML Rules (CRITICAL)

- **NEVER** use `ScrollView` wrapping content — use standalone `Flickable` instead. Qt 6 `ScrollView` causes blank pages on some Windows builds.
- **NEVER** use inline semicolons in QML property declarations (e.g., `Text { text: "x"; color: "y" }`). Some Qt builds reject them. Always use multi-line format.
- **ALWAYS** check brace balance after editing QML files
- **ALWAYS** use `Flickable` with explicit `contentHeight` for scrollable pages

## HID++ Protocol Rules

### Dual Handle Architecture (MX4 via Bolt)
- **SHORT handle** (Usage=0x0001, 7 bytes): for haptic motor commands via `HidD_SetOutputReport`
- **LONG handle** (Usage=0x0002, 20 bytes): for all HID++ 2.0 feature commands via `hidapi.write()`
- `hidapi.write()` sends interrupt OUT — Bolt receivers IGNORE this for some features
- `HidD_SetOutputReport()` sends USB SET_REPORT control transfer — required for haptics
- Use `hidapi.enumerate()` to find device paths (PyInstaller compatible), then `ctypes.CreateFileW` to open SHORT handle

### SmartShift
- MX3 (v1): func=0 is GET (read-only), func=1 is SET with params `[auto_disengage=10, threshold]`
- MX4 (v2): func=2 is SET with params `[0x02, threshold, force]`
- threshold range: 1-50, or 0xFF to disable
- MX3 auto_disengage is always 10

### Haptic Motor (MX4 ONLY — Feature 0x19B0, index 0x0B)
- Feature ID is **0x19B0** (NOT 0xB019 — that was a wrong assumption)
- Commands go via SHORT handle using `HidD_SetOutputReport`
- func=2 (byte3=0x2A): enable/disable + set intensity (0-100%)
- func=4 (byte3=0x4A): trigger pulse — 0x02=light, 0x04=tick, 0x08=strong, 0x00=reset
- MX3 does NOT have this feature

### Button Sensitivity (MX4 ONLY — Feature 0x19C0, index 0x0C)
- Commands go via LONG handle
- func=3 (byte3=0x3A): set sensitivity preset
- Presets: Light(0x0F3E), Medium(0x130E), Hard(0x16DE), Firm(0x1958)

### Battery
- MX3 uses 0x1000 (BATTERY_LEVEL_STATUS) — reports 0% while charging, cache last known level
- MX4 uses 0x1004 (UNIFIED_BATTERY) — check `ext_power == 1` for charging, NOT `batt_status` (stays at 8)
- Status code 8 = "normal/OK" on MX4, not an error

### Smooth Scrolling
- ON value differs: `0x03` for MX3, `0x01` for MX4

### DPI
- Flag byte: `0x00` for MX3, `0x01` for MX4
- Max DPI: 4000 (MX3), 8000 (MX4)
- Step: 50 DPI for both
- Cap UI slider and filter preset buttons based on detected device max

### Feature Discovery
- Profile-driven: detect device by DEVICE_NAME first, look up DEVICE_PROFILES
- Discover only features the profile says exist — no speculative probing
- **NEVER** hardcode feature indices — always discover via ROOT (index 0x00)

## Thread Safety

- ALL public HID++ getters/setters (SmartShift, HiRes, SmoothScroll) MUST use `_queued_request()` which executes on the listener thread
- **NEVER** call `_request()` directly from the UI thread — it causes response collisions with the listener thread's `_rx()` loop
- Haptic motor uses `HidD_SetOutputReport` which is thread-safe (different pipe)

## Auto-Detection

- Primary: DEVICE_NAME string match against `DEVICE_PROFILES[].name_matches`
- Backup: "master 4" in name → MX4 (covers haptic probe failures)
- Auto-set `mouse_model` in config on detection

## Startup Sequence

1. Kill competing Logitech processes (Options+, SetPoint, LogiPluginService)
2. Show popup warning if anything was killed (advise uninstall)
3. Single-instance check (kill existing MasterMice)
4. Load config, start engine
5. On device connect: apply saved haptic config

## UI Architecture

- Mouse images use PNG alpha transparency; dark mode inverts line colors to white
- Callout dot order computed algorithmically for non-crossing lines
- Action picker: floating overlay card on mouse image, close button, dimmed callouts
- Connection type: PNG icons (unifying.png, bolt.png, bluetooth.png)
- All pages use `Flickable` (NOT `ScrollView`) for scrolling
- "Saved" toast on every setting change

## Connection Optimization

- Skip usage_page 0xFFBC (receiver management)
- Prefer Usage=0x0002 (long reports) when enumerating interfaces
- Sequential probing with 500ms timeout per index (reduced from 2000ms)
- Remember last working `devIdx` in config for fast reconnect

## Logging

- Every HID++ setting change MUST be logged at INFO level
- Every error MUST be logged at ERROR level
- AppDetect: deduplicate with 5-second throttle

## Project Structure

```
MasterMice/
├── main_qml.py              # Entry point
├── MasterMice.spec           # PyInstaller build spec
├── MasterMice.bat            # Windows launcher
├── CLAUDE.md                 # This file
├── CHANGELOG.txt             # Version history
├── requirements.txt          # Python dependencies
├── core/
│   ├── config.py             # Configuration + device profiles
│   ├── engine.py             # Orchestration (battery, connect/disconnect)
│   ├── hid_gesture.py        # HID++ listener + feature control
│   ├── mouse_hook.py         # Windows raw input hook
│   ├── app_detector.py       # Foreground app detection
│   ├── key_simulator.py      # Key/mouse event injection
│   └── logger.py             # Log file management
├── ui/
│   ├── backend.py            # QML-Python bridge (properties, slots)
│   └── qml/
│       ├── Main.qml          # Root window + navigation
│       ├── MousePage.qml     # Mouse image + button mapping
│       ├── ScrollPage.qml    # Point & Scroll settings
│       ├── SettingsPage.qml  # App settings + diagnostics
│       ├── HotspotDot.qml    # Clickable callout dot component
│       ├── ActionChip.qml    # Action selector chip component
│       ├── AppIcon.qml       # SVG icon component
│       ├── Theme.js          # Dark/light color palettes
│       └── DeviceModels.js   # Mouse hotspot coordinates
├── images/
│   ├── MX Master 3-3S.png   # Mouse line art (3/3S)
│   ├── MX Master 4.png      # Mouse line art (4)
│   ├── mastermice.ico        # App icon (teal, multi-res)
│   ├── mastermice_white.ico  # Tray icon (white, multi-res)
│   └── icons/                # UI icons (SVG + PNG)
└── tools/
    ├── battery_test.py       # Diagnostic tool v2.1
    ├── hid_debug.py          # HID interface debugger v1.1
    ├── smartshift_test.py    # SmartShift protocol debugger v1.1
    ├── haptic_hybrid.py      # Haptic motor test (compiled) v1.0
    ├── mx4_haptic_probe.py   # Haptic SET_REPORT probe v1.0
    └── fix_receiver.ps1      # Driver reset PowerShell script
```

## Build Plan

### Current: v0.392 (console=True, debug build)

### Next: v0.40 — Release Candidate
- [ ] Test haptics on MX4 in MasterMice
- [ ] Button sensitivity UI (Light/Medium/Hard/Firm) for MX4
- [ ] Full test pass on MX3 + MX4 + both receivers
- [ ] Fix any remaining bugs from testing

### Then: v1.0 — First Public Release
- [ ] `console=False`
- [ ] Windows service architecture (core separated from UI)
- [ ] Installer (NSIS or WiX)
- [ ] Code signing certificate
- [ ] README + documentation
- [ ] GitHub repo setup
