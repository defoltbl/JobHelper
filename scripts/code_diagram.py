#!/usr/bin/env python3
"""Draw the diagram of the five agents for docs/CODE.md (docs/img/code_pipeline.png).

    python scripts/code_diagram.py

Drawn with Qt, at twice the size it is shown at, like the pictures of the user guide.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "img" / "code_pipeline.png"
AGENTS = [("1 · Profiler", "agent1_cv", "reads the CV,\nbuilds the profile", "#3b82f6"),
          ("2 · Scout", "agent2_search", "searches the boards,\nfilters, notes why", "#10b981"),
          ("3 · Scribe", "agent3_letters", "scores, writes the\nCV and the letter", "#8b5cf6"),
          ("4 · Tracker", "agent4_tracker", "writes the\nExcel tables", "#f59e0b"),
          ("5 · Postman", "agent5_responses", "reads replies,\nupdates statuses", "#f43f5e")]
STORES = [("data/profile.json", 0), ("data/jobs.json", 1), ("letters, CVs", 2), ("Excel tables", 3), ("data/responses.db", 4)]


def draw(out: Path = OUT) -> Path:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPolygonF

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    width, height, box, gap, top = 1240, 420, 208, 40, 60
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    left = (width - (5 * box + 4 * gap)) / 2
    for i, (name, module, does, colour) in enumerate(AGENTS):
        x = left + i * (box + gap)
        rect = QRectF(x, top, box, 150)
        p.setPen(QPen(QColor(colour), 3))
        p.setBrush(QColor("#f6f8fb"))
        p.drawRoundedRect(rect, 14, 14)
        p.setPen(QColor("#182230"))
        p.setFont(QFont("Helvetica Neue", 19, QFont.Bold))
        p.drawText(QRectF(x, top + 14, box, 34), Qt.AlignCenter, name)
        p.setPen(QColor(colour).darker(130))
        p.setFont(QFont("Menlo", 14))
        p.drawText(QRectF(x, top + 50, box, 26), Qt.AlignCenter, module)
        p.setPen(QColor("#45556b"))
        p.setFont(QFont("Helvetica Neue", 14))
        p.drawText(QRectF(x + 6, top + 82, box - 12, 60), Qt.AlignCenter, does)
        if i < 3:                                               # the search runs agents 1 to 4 in a row
            ax = x + box + 4
            p.setPen(QPen(QColor("#6b7a90"), 3))
            p.drawLine(QPointF(ax, top + 75), QPointF(ax + gap - 14, top + 75))
            p.setBrush(QColor("#6b7a90"))
            p.drawPolygon(QPolygonF([QPointF(ax + gap - 6, top + 75), QPointF(ax + gap - 18, top + 68), QPointF(ax + gap - 18, top + 82)]))
        store, _ = STORES[i]
        srect = QRectF(x + 14, top + 220, box - 28, 46)
        p.setPen(QPen(QColor("#c9d2dc"), 2))
        p.setBrush(QColor("#eef1f5"))
        p.drawRoundedRect(srect, 8, 8)
        p.setPen(QColor("#182230"))
        p.setFont(QFont("Menlo", 13))
        p.drawText(srect, Qt.AlignCenter, store)
        p.setPen(QPen(QColor("#c9d2dc"), 2, Qt.DashLine))
        p.drawLine(QPointF(x + box / 2, top + 152), QPointF(x + box / 2, top + 218))
    p.setPen(QColor("#45556b"))
    p.setFont(QFont("Helvetica Neue", 14))
    p.drawText(QRectF(left, 14, 4 * box + 3 * gap, 30), Qt.AlignCenter, "Run search: agents 1 to 4, in this order")
    p.drawText(QRectF(left + 4 * (box + gap), 14, box, 30), Qt.AlignCenter, "Scan email")
    p.drawText(QRectF(0, height - 72, width, 28), Qt.AlignCenter, "Each agent keeps what it made in the file under it. The window and the command line start the same agents.")
    p.end()
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(out))
    _ = app
    return out


if __name__ == "__main__":
    print(draw().name)
