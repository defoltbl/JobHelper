#!/usr/bin/env python3
"""JobHelper — native desktop app (PySide6 / Qt Quick).

    python app_qt.py

Truly native (GPU-rendered, no web engine). Uses your Claude subscription via
the Claude Code CLI, exactly like the command-line tools.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from jobhelper import config, vault
from jobhelper.qt_bridge import Bridge

QML = Path(__file__).resolve().parent / "ui_qt" / "Main.qml"


def apply_text_size(environ=None) -> str:
    """The size of text and controls chosen in Options: Qt is told before the window exists, and draws everything
    that much larger. A size set from outside (QT_SCALE_FACTOR) is left as it is. Returns what was set ('' = nothing)."""
    environ = os.environ if environ is None else environ
    if environ.get("QT_SCALE_FACTOR"):
        return ""
    try:
        scale = config.text_scale()
    except Exception:  # noqa: BLE001 - the window must open whatever the settings file holds
        return ""
    if scale == 1.0:
        return ""
    environ["QT_SCALE_FACTOR"] = f"{scale:g}"
    return environ["QT_SCALE_FACTOR"]


CHECK_FLAG = "--check-window"
NOTIFY_TEST_FLAG = "--notify-test"       # the installed app sends one test notification and says what macOS did


def check_refusal(environ) -> str:
    """Why the window check may not run here ('' = it may): it only ever runs on a throwaway data
    folder and an in-memory keychain, so it can never touch a person's data or Keychain."""
    if not str(environ.get("JOBHELPER_HOME") or "").strip():
        return "The window check needs JOBHELPER_HOME: a throwaway data folder."
    if str(environ.get("JOBHELPER_VAULT_BACKEND") or "").lower() != "memory":
        return "The window check needs JOBHELPER_VAULT_BACKEND=memory."
    return ""


def main() -> int:
    from jobhelper import home, weekly
    # Finder and launchd start an app in / (the whole disk). Every program the app starts (Claude, LibreOffice)
    # works where the app works, and Claude watches that folder: so the app works in an empty folder of its own.
    os.chdir(config.work_dir())
    if weekly.FLAG in sys.argv[1:]:
        return weekly.main()                          # the weekly run: no window, everything into its log
    if NOTIFY_TEST_FLAG in sys.argv[1:]:
        from jobhelper import notify
        print("If macOS asks whether to allow JobHelper's notifications, choose Allow.")
        result = notify.send_test(patience=60)
        print(f"notification: {result['msg']} (permission: {notify.notifier().permission()})")
        return 0 if result["ok"] else 1
    checking = CHECK_FLAG in sys.argv[1:]
    if checking:
        refusal = check_refusal(os.environ)
        if refusal:
            print(refusal)
            return 2
        return check_window()
    if home.start().moved:
        # the data has just moved into the Library: start again, so every part of the app uses the new place
        os.execv(sys.executable, home.restart_command(sys.argv, sys.executable, getattr(sys, "frozen", False)))
    from jobhelper import schedule
    fixed = schedule.refresh()                        # a weekly run of an older version now starts this one
    if not fixed["ok"]:
        print("Weekly run: %s" % fixed.get("msg", ""))
    # Background work (reading the mailbox, preparing Insights) hands over to the window ten times
    # sooner than Python's default, so animations stay smooth while it runs.
    sys.setswitchinterval(0.0005)
    apply_text_size()
    app = QGuiApplication(sys.argv)
    app.setApplicationName("JobHelper")
    icon = Path(__file__).resolve().parent / "ui_qt" / "icon.png"
    if icon.is_file():
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(icon)))          # the Dock and the window show the app's own icon
    app.setOrganizationName("JobHelper")

    try:
        vault.protect_all()      # secrets to the Keychain, data and backups encrypted
    except Exception as e:  # noqa: BLE001 - the window still opens and explains
        print("Data protection: %s" % e)

    engine = QQmlApplicationEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.load(QUrl.fromLocalFile(str(QML)))
    if not engine.rootObjects():
        print("Failed to load the QML UI.")
        return 1
    rc = app.exec()
    shut_down(engine)
    return rc


def check_window(seconds: float = 4.0) -> int:
    """Load the whole window off-screen, let it start for a few seconds, then close it: 0 when Qt
    reported no problem, else 1 (the problems are printed). For a built app: `JobHelper --check-window`."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    import importlib

    from PySide6.QtCore import QTimer
    app = QGuiApplication(sys.argv[:1])
    engine = QQmlApplicationEngine()
    problems: list[str] = []
    engine.warnings.connect(lambda found: problems.extend(w.toString() for w in found))
    bridge = Bridge(quiet=True)
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.load(QUrl.fromLocalFile(str(QML)))
    if not engine.rootObjects():
        print("Failed to load the QML UI.")
        return 1
    picture = os.environ.get("JOBHELPER_CHECK_PICTURE", "")

    def finish():
        try:
            if picture:                               # a picture of the window, to look at after a build
                importlib.import_module("PySide6.QtQuick")    # so the window is a QQuickWindow, which can be pictured
                if not engine.rootObjects()[0].grabWindow().save(picture):
                    problems.append(f"The picture could not be saved to {picture}.")
        except Exception as e:  # noqa: BLE001 - a picture that fails is a problem of the check, never a hang
            problems.append(f"The picture of the window failed: {e}")
        finally:
            app.quit()
    QTimer.singleShot(int(seconds * 1000), finish)
    app.exec()
    shut_down(engine)
    for name in ("run", "status"):                    # what the weekly run starts (a built app must carry them)
        try:
            importlib.import_module(name)
        except Exception as e:  # noqa: BLE001 - reported as a problem of the check
            problems.append(f"The weekly run's {name} cannot be loaded: {e}")
    for problem in problems:
        print(problem)
    print(f"window check: {len(problems)} problems")
    return 1 if problems else 0


def shut_down(engine) -> None:
    """Take the window down now, while the bridge it talks to still exists. Left to be cleaned up
    later, the bridge would go first and every binding that calls it would complain on the way out
    ("Cannot call method … of null")."""
    from shiboken6 import delete
    for window in engine.rootObjects():
        delete(window)
    delete(engine)


if __name__ == "__main__":
    sys.exit(main())
