# MasterMice

<p align="center">
  <img src="images/icons/icon_teal.png" width="128" alt="MasterMice logo" />
</p>

A lightweight, open-source alternative to **Logitech Options+** for the
**Logitech MX Master** series. Remap every button, tune scroll and DPI,
control haptics — all without telemetry, cloud accounts, or Logitech bloatware.

> MasterMice originated as a fork of [Mouser](https://github.com/TomBadash/Mouser)
> by [TomBadash](https://github.com/TomBadash), expanded with full MX Master 4
> support, haptic motor control, dual-device profiles, and a redesigned UI.

---

## Supported Devices

| Device | Connection | DPI | SmartShift | Haptics | Status |
|--------|-----------|-----|-----------|---------|--------|
| **MX Master 4** | Bolt / Bluetooth | up to 8000 | v2 (threshold + force) | Yes | Fully supported |
| **MX Master 3 / 3S** | Unifying / Bluetooth | up to 4000 | v1 (threshold) | No | Fully supported |

The device is auto-detected by name on connection — no manual selection needed.

---

## Download

> **No install required.** Download, extract, run.

<p align="center">
  <a href="https://github.com/olafnew/MasterMice/releases/latest">
    <img src="https://img.shields.io/badge/Download-Latest_Release-00d4aa?style=for-the-badge&logo=windows" alt="Download" />
  </a>
</p>

1. Go to [**Releases**](https://github.com/olafnew/MasterMice/releases/latest)
2. Download the `.zip` for your version
3. Extract anywhere and run **MasterMice.exe**

### First launch

- **Windows SmartScreen** may warn on first run — click **More info → Run anyway**
- MasterMice will **automatically kill Logitech Options+** if it's running (it conflicts with HID++ access) and show a popup explaining how to permanently disable it
- A **system tray icon** appears — the app keeps running when you close the window
- Config is saved to `%APPDATA%\MasterMice\` (migrated automatically from Mouser if upgrading)

---

## Features

### Button Remapping
- Remap **all programmable buttons** — middle click, gesture button, back, forward, scroll mode, thumb wheel, haptic panel (MX4)
- **Gesture swipe actions** — assign different actions to gesture up/down/left/right
- **Per-application profiles** — automatic profile switching based on the foreground app
- **22+ built-in actions**: navigation, browser, editing, media, and more

### Pointing & Scrolling
- **DPI control** — slider with presets, capped per device (4000 for MX3, 8000 for MX4)
- **SmartShift** — threshold and force sliders (MX4 adds force control)
- **Hi-Res scrolling** toggle with speed divider
- **Smooth scrolling** toggle
- **Scroll direction inversion** — independent vertical and horizontal

### MX Master 4 Extras
- **Haptic motor** — enable/disable, intensity slider, test pulse
- **Button sensitivity** — Light / Medium / Hard / Firm presets
- **Dual HID++ handle architecture** — haptic commands via USB control transfer, everything else via HID++ 2.0 interrupt

### Device Management
- **Auto-detection** — identifies MX3/3S/4 by device name on connect
- **Auto-reconnection** — detects power off/on and restores settings
- **Connection type indicator** — shows Unifying, Bolt, or Bluetooth icon
- **Battery level** — polled + event-driven with charging indicator

### UI
- **Dark / Light mode** — follows system or manual override
- **Interactive mouse diagram** — click hotspot dots to remap buttons
- **Action picker overlay** — floating card on mouse image
- **System tray** — hide to tray, toggle remapping, debug mode
- **Saved toast** on every setting change

---

## Screenshots

_Coming soon — the app is in active development._

---

## Running from Source

### Prerequisites

- **Windows 10/11** (macOS support inherited from upstream but untested with MX4 features)
- **Python 3.10+**
- **Logitech MX Master 3/3S/4** paired via Bluetooth or USB receiver
- **Logitech Options+ must NOT be running**

### Setup

```bash
git clone https://github.com/olafnew/MasterMice.git
cd MasterMice
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main_qml.py
```

### Building a Portable Executable

```bash
pip install pyinstaller
.venv\Scripts\pyinstaller MasterMice.spec --noconfirm
```

Output goes to `dist\MasterMice {version}\`. Zip and distribute.

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│  Mouse HW   │────▶│  MouseHook   │────▶│    Engine       │
│  (HID++)    │     │  (WH_MOUSE_LL│     │  (orchestrator) │
└─────────────┘     │  + raw input)│     └───────┬────────┘
                    └──────────────┘             │
                          ▲               ┌──────▼────────┐
                     block/pass           │ KeySimulator   │
                                          │ (SendInput)    │
┌─────────────┐     ┌──────────────┐      └───────────────┘
│   QML UI    │◀───▶│   Backend    │
│  (PySide6)  │     │  (QObject)   │      ┌───────────────┐
└─────────────┘     └──────┬───────┘      │  AppDetector   │
                           │              │  (foreground)   │
                    ┌──────▼───────┐      └───────────────┘
                    │ HidGesture   │
                    │ Listener     │
                    │ (HID++ 2.0)  │
                    └──────────────┘
```

- **MouseHook** — low-level Windows mouse hook on a dedicated thread with its own message pump
- **HidGestureListener** — HID++ 2.0 protocol: feature discovery, battery, SmartShift, DPI, haptics, button divert
- **Engine** — wires hook callbacks to actions, handles per-app profile switching
- **Backend** — QML-Python bridge exposing properties and slots
- **AppDetector** — polls foreground window, resolves UWP apps

---

## Diagnostic Tools

The `tools/` directory contains standalone debug utilities:

| Tool | Purpose |
|------|---------|
| `battery_test.py` | Battery protocol debugger |
| `smartshift_test.py` | SmartShift protocol debugger |
| `hid_debug.py` | HID interface enumerator |
| `haptic_hybrid.py` | Haptic motor test (MX4) |
| `mx4_haptic_probe.py` | Haptic SET_REPORT probe (MX4) |
| `fix_receiver.ps1` | Logitech receiver driver reset |

---

## Credits

- Original project: [TomBadash/Mouser](https://github.com/TomBadash/Mouser)
- macOS support: [andrew-sz](https://github.com/andrew-sz)

## License

[MIT License](LICENSE)

---

**MasterMice** is not affiliated with or endorsed by Logitech. "Logitech", "MX Master", and "Options+" are trademarks of Logitech International S.A.
