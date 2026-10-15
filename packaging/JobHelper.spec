# PyInstaller recipe for JobHelper.app. Build with: python scripts/build_app.py
# (that script runs PyInstaller with this file, then checks the app it made).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from jobhelper import app_info  # noqa: E402  (the app's name, version and bundle id, in one place)

import claude_agent_sdk  # noqa: E402

SDK = Path(claude_agent_sdk.__file__).resolve().parent

a = Analysis(
    [str(ROOT / "app_qt.py")],
    pathex=[str(ROOT)],
    binaries=[(str(SDK / "_bundled" / "claude"), "claude_agent_sdk/_bundled")],   # the Claude program the SDK asks with
    datas=[
        (str(ROOT / "ui_qt"), "ui_qt"),                  # the window, its icon and sound
        (str(ROOT / "CHANGELOG.md"), "."),              # Help > What changed
        *collect_data_files("docx"),                    # python-docx's own blank document
        *collect_data_files("certifi"),
    ],
    hiddenimports=["run", "status", "PySide6.QtQuick", *collect_submodules("jobhelper")],   # imported by name: the weekly run, the window picture
    excludes=["pytest", "tkinter", "PyInstaller"],
    noarchive=False,
)
# Qt parts the window never uses (a web engine, 3D, charts, maps, media, PDF viewing...): PySide6's hooks
# collect them anyway. Dropping them takes the app from about 650 MB to about 300 MB. The window check
# of scripts/build_app.py proves that nothing the window needs went with them.
UNUSED_QT = ("Qt3D", "QtCharts", "QtDataVisualization", "QtGraphs", "QtLocation", "QtMultimedia", "QtPdf",
             "QtPositioning", "QtQuick3D", "QtRemoteObjects", "QtScxml", "QtSensors", "QtSpatialAudio", "QtTest",
             "QtTextToSpeech", "QtVirtualKeyboard", "QtWebChannel", "QtWebEngine", "QtWebSockets", "QtWebView")


def _used(entry) -> bool:
    parts = Path(entry[0]).parts
    for folder in ("lib", "qml"):
        if "Qt" in parts and folder in parts:
            at = parts.index(folder) + 1
            if at < len(parts) and parts[at].startswith(UNUSED_QT):
                return False
    return True


a.binaries = [entry for entry in a.binaries if _used(entry)]
a.datas = [entry for entry in a.datas if _used(entry)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=app_info.NAME, console=False,
          argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, name=app_info.NAME)
app = BUNDLE(
    coll,
    name=f"{app_info.NAME}.app",
    icon=str(ROOT / "ui_qt" / "icon.icns"),
    bundle_identifier=app_info.BUNDLE_ID,
    version=app_info.VERSION,
    info_plist={
        "CFBundleDisplayName": app_info.NAME,
        "CFBundleShortVersionString": app_info.VERSION,
        "CFBundleVersion": app_info.VERSION,
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        # macOS asks once before the app may control another app: Chrome for the forms, Terminal for the sign-in
        "NSAppleEventsUsageDescription": app_info.APPLE_EVENTS_REASON,
    },
)
