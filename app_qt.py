#!/usr/bin/env python3
"""JobHelper — native desktop app (PySide6 / Qt Quick).

    python app_qt.py

Truly native (GPU-rendered, no web engine). Uses your Claude subscription via
the Claude Code CLI, exactly like the command-line tools.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from jobhelper import vault
from jobhelper.qt_bridge import Bridge

QML = Path(__file__).resolve().parent / "ui_qt" / "Main.qml"


def main() -> int:
    # Background work (reading the mailbox, preparing Insights) hands over to the window ten times
    # sooner than Python's default, so animations stay smooth while it runs.
    sys.setswitchinterval(0.0005)
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
