"""
Mouser — QML Entry Point
==============================
Launches the Qt Quick / QML UI with PySide6.
Replaces the old tkinter-based main.py.
Run with:   python main_qml.py
"""

import time as _time
_t0 = _time.perf_counter()          # ◄ startup clock

import sys
import os

# Ensure project root on path — works for both normal Python and PyInstaller
if getattr(sys, "frozen", False):
    # PyInstaller 6.x: data files are in _internal/ next to the exe
    ROOT = os.path.join(os.path.dirname(sys.executable), "_internal")
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# Set Material theme before any Qt imports
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Material"
os.environ["QT_QUICK_CONTROLS_MATERIAL_THEME"] = "Dark"
os.environ["QT_QUICK_CONTROLS_MATERIAL_ACCENT"] = "#00d4aa"

_t1 = _time.perf_counter()
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Qt, QUrl, QCoreApplication
from PySide6.QtQml import QQmlApplicationEngine
_t2 = _time.perf_counter()

# Ensure PySide6 QML plugins are found
import PySide6
_pyside_dir = os.path.dirname(PySide6.__file__)
os.environ.setdefault("QML2_IMPORT_PATH", os.path.join(_pyside_dir, "qml"))
os.environ.setdefault("QT_PLUGIN_PATH", os.path.join(_pyside_dir, "plugins"))

_t3 = _time.perf_counter()
from core.engine import Engine
from ui.backend import Backend
_t4 = _time.perf_counter()

def _print_startup_times():
    print(f"[Startup] Env setup:        {(_t1-_t0)*1000:7.1f} ms")
    print(f"[Startup] PySide6 imports:  {(_t2-_t1)*1000:7.1f} ms")
    print(f"[Startup] Core imports:     {(_t4-_t3)*1000:7.1f} ms")
    print(f"[Startup] Total imports:    {(_t4-_t0)*1000:7.1f} ms")


def _app_icon() -> QIcon:
    """Load the app icon from the pre-cropped .ico file."""
    ico = os.path.join(ROOT, "images", "logo.ico")
    return QIcon(ico)


def main():
    _print_startup_times()
    _t5 = _time.perf_counter()

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("Mouser")
    app.setOrganizationName("Mouser")
    app.setWindowIcon(_app_icon())

    _t6 = _time.perf_counter()
    # ── Engine (created but started AFTER UI is visible) ───────
    engine = Engine()

    _t7 = _time.perf_counter()
    # ── QML Backend ────────────────────────────────────────────
    backend = Backend(engine)

    # ── QML Engine ─────────────────────────────────────────────
    qml_engine = QQmlApplicationEngine()
    qml_engine.rootContext().setContextProperty("backend", backend)
    qml_engine.rootContext().setContextProperty(
        "applicationDirPath", ROOT.replace("\\", "/"))

    qml_path = os.path.join(ROOT, "ui", "qml", "Main.qml")
    qml_engine.load(QUrl.fromLocalFile(qml_path))
    _t8 = _time.perf_counter()

    if not qml_engine.rootObjects():
        print("[Mouser] FATAL: Failed to load QML")
        sys.exit(1)

    root_window = qml_engine.rootObjects()[0]

    print(f"[Startup] QApp create:      {(_t6-_t5)*1000:7.1f} ms")
    print(f"[Startup] Engine create:    {(_t7-_t6)*1000:7.1f} ms")
    print(f"[Startup] QML load:         {(_t8-_t7)*1000:7.1f} ms")
    print(f"[Startup] TOTAL to window:  {(_t8-_t0)*1000:7.1f} ms")

    # ── Start engine AFTER window is ready (deferred) ──────────
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, lambda: (
        engine.start(),
        print("[Mouser] Engine started — remapping is active"),
    ))

    # ── System Tray ────────────────────────────────────────────
    tray = QSystemTrayIcon(_app_icon(), app)
    tray.setToolTip("Mouser — MX Master 3S")

    tray_menu = QMenu()

    open_action = QAction("Open Settings", tray_menu)
    open_action.triggered.connect(lambda: (
        root_window.show(),
        root_window.raise_(),
        root_window.requestActivate(),
    ))
    tray_menu.addAction(open_action)

    toggle_action = QAction("Disable Remapping", tray_menu)

    def toggle_remapping():
        enabled = not engine._enabled
        engine.set_enabled(enabled)
        toggle_action.setText(
            "Disable Remapping" if enabled else "Enable Remapping")

    toggle_action.triggered.connect(toggle_remapping)
    tray_menu.addAction(toggle_action)

    tray_menu.addSeparator()

    quit_action = QAction("Quit Mouser", tray_menu)

    def quit_app():
        engine.hook.stop()
        engine._app_detector.stop()
        tray.hide()
        app.quit()

    quit_action.triggered.connect(quit_app)
    tray_menu.addAction(quit_action)

    tray.setContextMenu(tray_menu)
    tray.activated.connect(lambda reason: (
        root_window.show(),
        root_window.raise_(),
        root_window.requestActivate(),
    ) if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
    tray.show()

    # ── Run ────────────────────────────────────────────────────
    try:
        sys.exit(app.exec())
    finally:
        engine.hook.stop()
        engine._app_detector.stop()
        print("[Mouser] Shut down cleanly")


if __name__ == "__main__":
    main()
