"""
MasterMice — QML Entry Point
==============================
Launches the Qt Quick / QML UI with PySide6.
Replaces the old tkinter-based main.py.
Run with:   python main_qml.py
"""

import time as _time
_t0 = _time.perf_counter()          # ◄ startup clock

import sys
import os
import signal
from urllib.parse import parse_qs, unquote

# Ensure project root on path — works for both normal Python and PyInstaller
if getattr(sys, "frozen", False):
    # PyInstaller 6.x: data files are in _internal/ next to the exe
    ROOT = os.path.join(os.path.dirname(sys.executable), "_internal")
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# Set Material theme before any Qt imports
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Material"
os.environ["QT_QUICK_CONTROLS_MATERIAL_ACCENT"] = "#00d4aa"
# Disable Windows 11 Mica/acrylic transparency on the title bar
# Only supported on newer PySide6 builds — skip if Qt version is too old
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "windows:darkmode=0,nodarkframe")

_t1 = _time.perf_counter()
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QAction, QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtCore import QObject, Property, QCoreApplication, QRectF, Qt, QUrl, Signal
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer
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
    """Load the app icon — uses mastermice.ico (multi-resolution)."""
    ico = os.path.join(ROOT, "images", "mastermice.ico")
    if not os.path.exists(ico):
        # Fallback to legacy icon
        ico = os.path.join(ROOT, "images", "logo.ico")
    return QIcon(ico)


def _render_svg_pixmap(path: str, color: QColor, size: int) -> QPixmap:
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return QPixmap()

    screen = QApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0
    pixel_size = max(size, int(round(size * dpr)))

    pixmap = QPixmap(pixel_size, pixel_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return pixmap


def _tray_icon() -> QIcon:
    """Tray icon — use white variant for dark tray backgrounds on Windows,
    mask icon on macOS, teal for everything else."""
    if sys.platform == "darwin":
        tray_svg = os.path.join(ROOT, "images", "icons", "mouse-simple.svg")
        if os.path.exists(tray_svg):
            icon = QIcon(_render_svg_pixmap(tray_svg, QColor("#000000"), 18))
            icon.setIsMask(True)
            return icon
    # Windows/Linux: use the white ICO (visible on dark tray backgrounds)
    white_ico = os.path.join(ROOT, "images", "mastermice_white.ico")
    if os.path.exists(white_ico):
        return QIcon(white_ico)
    return _app_icon()


class UiState(QObject):
    appearanceModeChanged = Signal()
    systemAppearanceChanged = Signal()
    darkModeChanged = Signal()

    def __init__(self, app: QApplication, parent=None):
        super().__init__(parent)
        self._app = app
        self._appearance_mode = "system"
        self._font_family = app.font().family()
        if self._font_family in {"", "Sans Serif"}:
            if sys.platform == "darwin":
                self._font_family = ".AppleSystemUIFont"
            elif sys.platform == "win32":
                self._font_family = "Segoe UI"
            else:
                self._font_family = "Noto Sans"
        self._system_dark_mode = False
        self._sync_system_appearance()

        style_hints = app.styleHints()
        if hasattr(style_hints, "colorSchemeChanged"):
            style_hints.colorSchemeChanged.connect(
                lambda *_: self._sync_system_appearance()
            )

    def _sync_system_appearance(self):
        is_dark = self._app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        if is_dark == self._system_dark_mode:
            return
        self._system_dark_mode = is_dark
        self.systemAppearanceChanged.emit()
        self.darkModeChanged.emit()

    @Property(str, notify=appearanceModeChanged)
    def appearanceMode(self):
        return self._appearance_mode

    @appearanceMode.setter
    def appearanceMode(self, mode):
        normalized = mode if mode in {"system", "light", "dark"} else "system"
        if normalized == self._appearance_mode:
            return
        self._appearance_mode = normalized
        self.appearanceModeChanged.emit()
        self.darkModeChanged.emit()

    @Property(bool, notify=systemAppearanceChanged)
    def systemDarkMode(self):
        return self._system_dark_mode

    @Property(bool, notify=darkModeChanged)
    def darkMode(self):
        if self._appearance_mode == "dark":
            return True
        if self._appearance_mode == "light":
            return False
        return self._system_dark_mode

    @Property(str, constant=True)
    def fontFamily(self):
        return self._font_family


class MouseImageProvider(QQuickImageProvider):
    """Serves mouse PNG images with enforced alpha transparency.
    Light pixels (checkerboard / white background) are made transparent.
    In dark mode (?dark=true), dark line pixels are inverted to white.
    Results are cached so pixel processing only happens once per variant."""

    def __init__(self, root_dir: str):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._img_dir = os.path.join(root_dir, "images")
        self._cache = {}

    def requestImage(self, image_id, size, requested_size):
        if image_id in self._cache:
            img = self._cache[image_id]
            if size is not None:
                size.setWidth(img.width())
                size.setHeight(img.height())
            return img

        name, _, query_string = image_id.partition("?")
        name = unquote(name)  # decode %20 → space
        params = parse_qs(query_string)
        dark = params.get("dark", ["false"])[0] == "true"

        img_path = os.path.join(self._img_dir, name)
        img = QImage(img_path)
        if img.isNull():
            return QImage()

        img = img.convertToFormat(QImage.Format.Format_ARGB32)

        # Process every pixel:
        #  - light pixels (avg brightness > 200) → fully transparent
        #  - dark pixels in dark mode → invert RGB, keep alpha
        w, h = img.width(), img.height()
        for y in range(h):
            for x in range(w):
                px = img.pixel(x, y)
                a = (px >> 24) & 0xFF
                if a < 10:
                    continue
                r = (px >> 16) & 0xFF
                g = (px >> 8) & 0xFF
                b = px & 0xFF
                if (r + g + b) // 3 > 200:
                    img.setPixel(x, y, 0)
                elif dark:
                    img.setPixel(x, y,
                                 (a << 24) | ((255 - r) << 16)
                                 | ((255 - g) << 8) | (255 - b))

        self._cache[image_id] = img

        if size is not None:
            size.setWidth(img.width())
            size.setHeight(img.height())
        return img


class AppIconProvider(QQuickImageProvider):
    def __init__(self, root_dir: str):
        super().__init__(QQuickImageProvider.ImageType.Pixmap)
        self._icon_dir = os.path.join(root_dir, "images", "icons")

    def requestPixmap(self, icon_id, size, requested_size):
        name, _, query_string = icon_id.partition("?")
        params = parse_qs(query_string)
        color = QColor(params.get("color", ["#000000"])[0])
        logical_size = requested_size.width() if requested_size.width() > 0 else 24
        if "size" in params:
            try:
                logical_size = max(12, int(params["size"][0]))
            except ValueError:
                logical_size = max(12, logical_size)

        icon_name = name if name.endswith(".svg") else f"{name}.svg"
        icon_path = os.path.join(self._icon_dir, icon_name)
        pixmap = _render_svg_pixmap(icon_path, color, logical_size)
        if size is not None:
            size.setWidth(logical_size)
            size.setHeight(logical_size)
        return pixmap


def main():
    # Initialize logging before anything else prints
    from core.config import load_config as _load_cfg, APP_VERSION
    from core.logger import setup as _setup_logging
    _cfg = _load_cfg()
    _setup_logging(
        _cfg.get("settings", {}).get("log_level", "errors"),
        _cfg.get("settings", {}).get("log_max_kb", 1024),
    )

    print(f"[MasterMice] Version {APP_VERSION}")
    _print_startup_times()

    # ── Hide console unless debug mode is on ──────────────────────
    if sys.platform == "win32" and not _cfg.get("settings", {}).get("debug_mode", False):
        try:
            import ctypes
            _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if _hwnd:
                ctypes.windll.user32.ShowWindow(_hwnd, 0)  # SW_HIDE
        except Exception:
            pass

    # ── Single-instance check: kill any existing MasterMice ──────
    from core.app_detector import AppDetector
    _existing = AppDetector.is_running("MasterMice.exe")
    if _existing:
        print(f"[MasterMice] Killing existing instance (PID {_existing})...")
        AppDetector.kill_process(_existing)
        _time.sleep(1)

    # ── Logitech software kill is now handled by the Go service ──
    # The service kills Logitech processes before opening HID++ handles.
    # Check if anything was running so we can warn the user.
    _logi_procs = AppDetector.check_logitech_software()
    _logi_killed = _logi_procs  # service handles the actual kill

    _t5 = _time.perf_counter()

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("MasterMice")
    app.setOrganizationName("MasterMice")
    app.setWindowIcon(_app_icon())
    ui_state = UiState(app)

    # macOS: allow Ctrl+C in terminal to quit the app
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    if sys.platform == "darwin":
        # SIGUSR1 thread dump (useful for debugging on macOS)
        import traceback
        def _dump_threads(sig, frame):
            import threading
            for t in threading.enumerate():
                print(f"\n--- {t.name} ---")
                if t.ident:
                    traceback.print_stack(sys._current_frames().get(t.ident))
        signal.signal(signal.SIGUSR1, _dump_threads)

    _t6 = _time.perf_counter()
    # ── Engine (created but started AFTER UI is visible) ───────
    engine = Engine()

    _t7 = _time.perf_counter()
    # ── QML Backend ────────────────────────────────────────────
    backend = Backend(engine)

    # ── QML Engine ─────────────────────────────────────────────
    qml_engine = QQmlApplicationEngine()
    qml_engine.addImageProvider("appicons", AppIconProvider(ROOT))
    qml_engine.addImageProvider("mouseimage", MouseImageProvider(ROOT))
    qml_engine.rootContext().setContextProperty("backend", backend)
    qml_engine.rootContext().setContextProperty("uiState", ui_state)
    _dir_fwd = ROOT.replace("\\", "/")
    qml_engine.rootContext().setContextProperty("applicationDirPath", _dir_fwd)
    # Build a file:// URL that works for both local (file:///C:/) and UNC
    # (file:////server/share) paths.  QUrl.fromLocalFile puts the server
    # in the authority component (file://server/…) which Qt Image can't open,
    # so we construct the URL manually.
    if _dir_fwd.startswith("//"):
        _app_dir_url = "file://" + _dir_fwd        # file:////server/share
    else:
        _app_dir_url = "file:///" + _dir_fwd       # file:///C:/path
    qml_engine.rootContext().setContextProperty("applicationDirUrl", _app_dir_url)

    qml_path = os.path.join(ROOT, "ui", "qml", "Main.qml")
    qml_engine.load(QUrl.fromLocalFile(qml_path))
    _t8 = _time.perf_counter()

    if not qml_engine.rootObjects():
        print("[MasterMice] FATAL: Failed to load QML")
        sys.exit(1)

    root_window = qml_engine.rootObjects()[0]

    print(f"[Startup] QApp create:      {(_t6-_t5)*1000:7.1f} ms")
    print(f"[Startup] Engine create:    {(_t7-_t6)*1000:7.1f} ms")
    print(f"[Startup] QML load:         {(_t8-_t7)*1000:7.1f} ms")
    print(f"[Startup] TOTAL to window:  {(_t8-_t0)*1000:7.1f} ms")

    # ── Show Logitech software warning if we detected anything ──
    # (Go service handles the actual kill; we just warn the user)
    if _logi_killed:
        from PySide6.QtWidgets import QMessageBox
        _warn = QMessageBox()  # no parent — QQuickWindow is not a QWidget
        _warn.setWindowTitle("MasterMice")
        _warn.setIcon(QMessageBox.Icon.Warning)
        _warn.setText("Logitech software was detected and stopped")
        _warn.setInformativeText(
            f"Stopped: {', '.join(_logi_killed)}\n\n"
            "MasterMice needs exclusive access to your mouse's HID++ interface. "
            "Logitech Options+ and SetPoint block this access.\n\n"
            "To prevent this message:\n"
            "  1. Uninstall Logi Options+ from Windows Settings\n"
            "  2. Or disable its startup service:\n"
            "     Win+R → services.msc → LogiPluginService → Disabled\n\n"
            "MasterMice will now connect to your mouse."
        )
        _warn.setStandardButtons(QMessageBox.StandardButton.Ok)
        _warn.exec()

    # ── Start engine AFTER window is ready (deferred) ──────────
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, lambda: (
        engine.start(),
        print("[MasterMice] Engine started — remapping is active"),
    ))

    # ── System Tray ────────────────────────────────────────────
    tray = QSystemTrayIcon(_tray_icon(), app)
    _name = backend.mouseModelName
    tray.setToolTip("MasterMice — " + _name if _name else "MasterMice")

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

    debug_action = QAction("Enable Debug Mode", tray_menu)

    def sync_debug_action():
        debug_enabled = bool(backend.debugMode)
        debug_action.setText(
            "Disable Debug Mode" if debug_enabled else "Enable Debug Mode"
        )

    def toggle_debug_mode():
        backend.setDebugMode(not backend.debugMode)
        sync_debug_action()
        if backend.debugMode:
            root_window.show()
            root_window.raise_()
            root_window.requestActivate()

    debug_action.triggered.connect(toggle_debug_mode)
    tray_menu.addAction(debug_action)
    backend.settingsChanged.connect(sync_debug_action)
    sync_debug_action()

    tray_menu.addSeparator()

    quit_action = QAction("Quit MasterMice", tray_menu)

    def quit_app():
        # Disconnect from Go service + close any legacy HID++ handles
        try:
            engine.svc.disconnect()
        except Exception:
            pass
        try:
            hg = getattr(engine.hook, '_hid_gesture', None)
            if hg:
                hg._close_short_handle()
                if getattr(hg, '_dev', None):
                    hg._dev.close()
                    hg._dev = None
                hg._running = False
        except Exception:
            pass
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
    ) if reason in (
        QSystemTrayIcon.ActivationReason.Trigger,
        QSystemTrayIcon.ActivationReason.DoubleClick,
    ) else None)
    tray.show()

    # ── Minimize to tray on close ─────────────────────────────
    # Don't quit when window is closed — keep running in tray.
    # User must use "Quit MasterMice" from tray menu to fully exit.
    app.setQuitOnLastWindowClosed(False)

    # ── Run ────────────────────────────────────────────────────
    try:
        sys.exit(app.exec())
    finally:
        try:
            engine.svc.disconnect()
        except Exception:
            pass
        try:
            hg = getattr(engine.hook, '_hid_gesture', None)
            if hg:
                hg._close_short_handle()
                hg._running = False
        except Exception:
            pass
        engine.hook.stop()
        engine._app_detector.stop()
        print("[MasterMice] Shut down cleanly")


if __name__ == "__main__":
    main()
