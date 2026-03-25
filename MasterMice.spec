# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for MasterMice
Produces a single-directory portable build in  dist/MasterMice {version}/
Run:  pyinstaller MasterMice.spec
"""

import os
import sys
import shutil
import PySide6

block_cipher = None
ROOT = os.path.abspath(".")
PYSIDE6_DIR = os.path.dirname(PySide6.__file__)

a = Analysis(
    ["main_qml.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # QML UI files
        (os.path.join(ROOT, "ui", "qml"), os.path.join("ui", "qml")),
        # Image assets
        (os.path.join(ROOT, "images"), "images"),
    ],
    hiddenimports=[
        # conditional / lazy imports PyInstaller may miss
        "hid",
        "ctypes.wintypes",
        # PySide6 QML runtime
        "PySide6.QtQuick",
        "PySide6.QtQuickControls2",
        "PySide6.QtQml",
        "PySide6.QtNetwork",
        "PySide6.QtOpenGL",
        "PySide6.QtSvg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ── Aggressively trim unneeded PySide6 modules ──
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DExtras",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtLocation",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtSerialBus",
        "PySide6.QtTest",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtSql",
        "PySide6.QtSvgWidgets",
        "PySide6.QtTextToSpeech",
        "PySide6.QtQuick3D",
        "PySide6.QtVirtualKeyboard",
        "PySide6.QtGraphs",
        "PySide6.Qt5Compat",
        # ── PySide6 designer / tools (not needed at runtime) ──
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
        "PySide6.QtUiTools",
        "PySide6.QtXml",
        "PySide6.QtConcurrent",
        "PySide6.QtDBus",
        "PySide6.QtStateMachine",
        "PySide6.QtHttpServer",
        "PySide6.QtSpatialAudio",
        # ── Other unused stdlib modules ──
        "unittest",
        "xmlrpc",
        "pydoc",
        "doctest",
        "tkinter",
        "test",
        "distutils",
        "setuptools",
        "ensurepip",
        "lib2to3",
        "idlelib",
        "turtledemo",
        "turtle",
        "sqlite3",
        "multiprocessing",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Filter out massive Qt DLLs and data we don't need ──────────────────
_qt_keep = {
    # Core Qt
    "Qt6Core", "Qt6Gui", "Qt6Widgets", "Qt6Network", "Qt6OpenGL", "Qt6Svg",
    # QML / Quick
    "Qt6Qml", "Qt6QmlCore", "Qt6QmlMeta", "Qt6QmlModels",
    "Qt6QmlNetwork", "Qt6QmlWorkerScript",
    "Qt6Quick", "Qt6QuickControls2", "Qt6QuickControls2Impl",
    "Qt6QuickControls2Basic", "Qt6QuickControls2BasicStyleImpl",
    "Qt6QuickControls2Material", "Qt6QuickControls2MaterialStyleImpl",
    "Qt6QuickTemplates2", "Qt6QuickLayouts", "Qt6QuickEffects",
    "Qt6QuickShapes",
    # Rendering
    "Qt6ShaderTools",
    # PySide6 runtime
    "pyside6.abi3", "pyside6qml.abi3", "shiboken6.abi3",
    # VC runtime
    "MSVCP140", "MSVCP140_1", "MSVCP140_2",
    "VCRUNTIME140", "VCRUNTIME140_1",
}

def _should_keep(name):
    if "PySide6" not in name and "pyside6" not in name.lower():
        return True
    base = os.path.basename(name)
    stem = os.path.splitext(base)[0]
    if stem in _qt_keep:
        return True
    if base.endswith(".pyd"):
        return True
    for keep in ("platforms", "imageformats", "styles", "iconengines",
                 "platforminputcontexts"):
        if keep in name:
            return True
    for keep_qml in ("QtCore", "QtQml", "QtQuick", "QtNetwork"):
        pat = os.path.join("qml", keep_qml)
        if pat in name.replace("/", os.sep):
            return True
    return False

a.binaries = [b for b in a.binaries if _should_keep(b[0])]
a.datas    = [d for d in a.datas    if _should_keep(d[0])]

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MasterMice",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # production: no console window
    icon=os.path.join(ROOT, "images", "mastermice.ico"),
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MasterMice 0.551",
)

# ── Post-build cleanup ──────────────────────────────────────────────────
_dist = os.path.join("dist", "MasterMice 0.32", "_internal", "PySide6")

_keep_qml = {"QtCore", "QtQml", "QtQuick", "QtNetwork"}
_keep_qtquick = {"Controls", "Layouts", "Templates", "Window"}
_keep_plugins = {"iconengines", "imageformats", "platforms",
                 "platforminputcontexts", "styles"}

def _cleanup():
    qml_root = os.path.join(_dist, "qml")
    if os.path.isdir(qml_root):
        for d in os.listdir(qml_root):
            if d not in _keep_qml:
                p = os.path.join(qml_root, d)
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                    print(f"  [cleanup] removed qml/{d}")
        qtquick = os.path.join(qml_root, "QtQuick")
        if os.path.isdir(qtquick):
            for d in os.listdir(qtquick):
                if d not in _keep_qtquick:
                    p = os.path.join(qtquick, d)
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                        print(f"  [cleanup] removed qml/QtQuick/{d}")
    plugins_root = os.path.join(_dist, "plugins")
    if os.path.isdir(plugins_root):
        for d in os.listdir(plugins_root):
            if d not in _keep_plugins:
                p = os.path.join(plugins_root, d)
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                    print(f"  [cleanup] removed plugins/{d}")
    trans = os.path.join(_dist, "translations")
    if os.path.isdir(trans):
        shutil.rmtree(trans, ignore_errors=True)
        print("  [cleanup] removed translations/")

print("[MasterMice] Post-build cleanup...")
_cleanup()

# ── Copy Go binaries into _internal/ (hidden from user view) ─────────
_dist_ver = "MasterMice 0.551"
_dst_dir = os.path.join("dist", _dist_ver, "_internal")
for _exe_name in ["mastermice-svc.exe", "mastermice-agent.exe"]:
    _src = os.path.join(ROOT, "service", _exe_name)
    if os.path.isfile(_src) and os.path.isdir(_dst_dir):
        shutil.copy2(_src, os.path.join(_dst_dir, _exe_name))
        print(f"  [bundle] Copied {_exe_name} to _internal/")
    else:
        print(f"  [bundle] WARNING: {_src} not found — {_exe_name} not bundled!")

print("[MasterMice] Cleanup done.")
