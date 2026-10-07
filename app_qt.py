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
    app = QGuiApplication(sys.argv)
    app.setApplicationName("JobHelper")
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
    # Tear the QML engine down while `bridge` is still alive, so exit-time
    # property re-evaluation doesn't fire against a freed context object.
    engine.deleteLater()
    engine = None
    return rc


if __name__ == "__main__":
    sys.exit(main())
