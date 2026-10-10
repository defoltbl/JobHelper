#!/usr/bin/env python3
"""Draw the diagrams of docs/CODE.md: the five agents (docs/img/code_pipeline.png) and one for each
process the document explains (docs/img/code_*.png, described in DIAGRAMS below).

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


# ── the diagrams of how things work ──────────────────────────────────────────
# Each is drawn on a grid: a node is (column, row, kind, words). Kinds: "step" (something done), "ask" (a decision),
# "store" (a file or a place), "who" (the person, Claude, a site), "stop" (an end). An arrow is (from, to, words).
BLUE, GREEN, VIOLET, AMBER, RED, GREY = "#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#f43f5e", "#6b7a90"
LOOK = {"step": ("#f6f8fb", BLUE), "ask": ("#fff7e6", AMBER), "store": ("#eef1f5", "#9aa7b7"), "who": ("#f3ecfe", VIOLET), "stop": ("#e9f7ee", GREEN), "no": ("#fdecec", RED)}

DIAGRAMS = {
    "code_layers": {
        "title": "A press of a button, from the window to the data and back",
        "cell": (270, 150), "nodes": {
            "qml": (0, 0, "who", "Window\nui_qt/*.qml\nshows, never reads a file"),
            "slot": (1, 0, "step", "Bridge slot\nqt_bridge, bridge_*\nstarts a thread for long work"),
            "api": (2, 0, "step", "Api method\nui_api, api_*\nchecks the input"),
            "mod": (3, 0, "step", "Modules\nagents, rules,\nwriting, mail"),
            "sig": (1, 1, "step", "Signal\n_post(name, plain values)"),
            "data": (3, 1, "store", "data/ (encrypted)\nstore, db, vault"),
            "key": (2, 1, "store", "macOS Keychain\nthe data key, passwords"),
            "out": (4, 0, "who", "Claude · job boards\nmailbox · browser")},
        "arrows": [("qml", "slot", "calls"), ("slot", "api", "calls"), ("api", "mod", "uses"), ("mod", "out", "asks"),
                   ("mod", "data", "reads, writes"), ("data", "key", "key"), ("api", "sig", "a dictionary"), ("sig", "qml", "answers")]},
    "code_search": {
        "title": "What a search does with a posting",
        "cell": (250, 132), "nodes": {
            "cv": (0, 0, "step", "1 · Profiler\nreads the CV once"),
            "ask": (1, 0, "step", "2 · Scout\nasks the boards"),
            "rules": (2, 0, "ask", "Fits the rules?\nlanguage, level, years,\nage, place, applied"),
            "kind": (3, 0, "ask", "Plainly another\nprofession?"),
            "score": (4, 0, "step", "3 · Scribe\nscores, 5 per call"),
            "out": (2, 1, "store", "Filtered out\nkept with the reason"),
            "skip": (3, 1, "store", "Marked skipped\nno Claude call"),
            "limit": (4, 1, "ask", "At or above\nyour limit?"),
            "lead": (4, 2, "store", "A lead without\ndocuments"),
            "docs": (3, 2, "step", "Adapts the CV,\nthen writes the letter"),
            "check": (2, 2, "ask", "Says only what\nthe CV shows?"),
            "save": (1, 2, "step", "4 · Tracker\nsaves, rebuilds Excel"),
            "back": (0, 2, "step", "Sent back once,\nthen shown to you")},
        "arrows": [("cv", "ask", ""), ("ask", "rules", ""), ("rules", "kind", "yes"), ("kind", "score", "no"), ("score", "limit", ""),
                   ("rules", "out", "no"), ("kind", "skip", "yes"), ("limit", "lead", "no"), ("limit", "docs", "yes"), ("docs", "check", ""),
                   ("check", "save", "yes"), ("save", "back", "if not")]},
    "code_honesty": {
        "title": "How a text is kept inside what the CV shows",
        "cell": (270, 140), "nodes": {
            "draft": (0, 0, "who", "Claude drafts\nfrom the CV, your notes\nand the posting"),
            "tech": (1, 0, "ask", "A technology\nnot in the CV?"),
            "claim": (2, 0, "ask", "A term of the posting\nstated as experience?"),
            "first": (3, 0, "ask", "Third person,\nem dash, emoji?"),
            "ok": (4, 0, "stop", "Saved"),
            "again": (1, 1, "step", "Sent back once,\nwith what was wrong"),
            "show": (3, 1, "step", "Kept, and shown in\nthe job's window\n(cv_check, letter_check)"),
            "you": (4, 1, "who", "You read it\nbefore you send")},
        "arrows": [("draft", "tech", ""), ("tech", "claim", "no"), ("claim", "first", "no"), ("first", "ok", "no"), ("tech", "again", "yes"),
                   ("claim", "again", "yes"), ("again", "draft", "once"), ("first", "show", "still there"), ("show", "you", "")]},
    "code_scan": {
        "title": "What an email scan does with a message",
        "cell": (250, 140), "nodes": {
            "box": (0, 0, "who", "Mailbox\nopened read-only"),
            "seen": (1, 0, "ask", "Read before?"),
            "like": (2, 0, "ask", "About an application?\nrules, no Claude call"),
            "claude": (3, 0, "who", "5 · Postman\nClaude reads it"),
            "match": (4, 0, "ask", "Names a company\nby its own words?"),
            "skip": (1, 1, "store", "Left alone"),
            "ad": (2, 1, "store", "Adverts, newsletters,\nalerts: left alone"),
            "file": (4, 1, "step", "Filed to the application;\nits status follows"),
            "loose": (3, 1, "store", "Kept unfiled:\nFile under…")},
        "arrows": [("box", "seen", ""), ("seen", "like", "no"), ("like", "claude", "yes"), ("claude", "match", ""), ("seen", "skip", "yes"),
                   ("like", "ad", "no"), ("match", "file", "yes"), ("match", "loose", "no")]},
    "code_limit": {
        "title": "The limit is a state, not an error",
        "cell": (270, 150), "nodes": {
            "run": (0, 0, "step", "Running\nevery call goes\nthrough llm.ask"),
            "hit": (1, 0, "ask", "Limit used up?\n99% of a window, or\nClaude says so"),
            "pause": (2, 0, "step", "Paused\nwork saved, the reset\ntime is shown"),
            "wait": (3, 0, "ask", "Reset time\npassed?"),
            "resume": (3, 1, "who", "You press Resume"),
            "same": (1, 1, "step", "Goes on from\nthe same job"),
            "done": (0, 1, "stop", "Finished")},
        "arrows": [("run", "hit", "before a call"), ("hit", "pause", "yes"), ("pause", "wait", ""), ("wait", "resume", "yes"), ("resume", "same", ""),
                   ("same", "run", ""), ("hit", "done", "no, and nothing left")]},
    "code_safety": {
        "title": "How the data is kept safe",
        "cell": (270, 150), "nodes": {
            "app": (0, 0, "step", "store · db\nevery read and write"),
            "vault": (1, 0, "step", "vault\nAES-256-GCM"),
            "files": (2, 0, "store", "data/*.json, *.db\nencrypted on disk"),
            "key": (1, 1, "store", "macOS Keychain\nthe data key"),
            "backup": (2, 1, "store", "data/backups/\nbefore every bulk change"),
            "rules": (3, 0, "store", "Rule files, template,\nmaster CV: signed"),
            "changed": (3, 1, "ask", "Changed outside\nthe app?"),
            "approve": (4, 1, "who", "Shown line by line;\nyou approve"),
            "recover": (0, 1, "who", "Recovery key\nshown on request,\nfor a new Mac")},
        "arrows": [("app", "vault", ""), ("vault", "files", ""), ("vault", "key", "key"), ("files", "backup", "copy"), ("rules", "changed", "at start"),
                   ("changed", "approve", "yes"), ("key", "recover", "")]},
    "code_fill": {
        "title": "How the assistant fills in a form",
        "cell": (250, 140), "nodes": {
            "read": (0, 0, "step", "READ\nlists the fields,\nnot what they hold"),
            "plan": (1, 0, "ask", "plan()\nwhat is each field?"),
            "values": (2, 0, "store", "What goes in\nMy details · answers and\nchoices (one call each)"),
            "fill": (3, 0, "step", "FILL\nwrites empty fields only"),
            "empty": (4, 0, "ask", "EMPTY\nthrown away?"),
            "never": (0, 1, "no", "Never: Submit, Next,\na box that agrees"),
            "left": (1, 1, "store", "Left to you, with\nthe reason: passwords,\nprivate, unknown files"),
            "press": (2, 1, "step", "CHOOSE · ATTACH\na menu, an entry, a radio,\na row · the CV and letter"),
            "say": (3, 1, "stop", "Report: filled,\nleft, to check"),
            "typed": (4, 1, "step", "Written again,\nas typing arrives")},
        "arrows": [("read", "plan", ""), ("plan", "values", "mine"), ("values", "fill", "text"), ("fill", "empty", ""), ("plan", "left", "not mine"),
                   ("values", "press", "a choice"), ("press", "say", ""), ("empty", "typed", "yes"), ("typed", "say", ""), ("fill", "say", "")]},
    "code_talk": {
        "title": "How the assistant decides what to do with a request",
        "cell": (250, 132), "nodes": {
            "req": (0, 0, "who", "You ask"),
            "fixed": (1, 0, "ask", "A fixed request?\nfill, details, help"),
            "free": (1, 1, "stop", "Done at once,\nno Claude call"),
            "jobs": (2, 0, "step", "The jobs it is\nlikely about, your notes,\nthe last turns"),
            "claude": (3, 0, "who", "Claude: an answer,\nor up to 3 actions"),
            "check": (4, 0, "ask", "check()\nknown action,\nreal job?"),
            "drop": (4, 1, "no", "Dropped, and said"),
            "change": (3, 1, "ask", "Changes your data?"),
            "yes": (2, 1, "who", "Asked in the app's\nwords: Yes, do it"),
            "do": (2, 2, "step", "Done by the app's\nown functions"),
            "undo": (1, 2, "store", "Undo: the job\nas it was"),
            "show": (3, 2, "stop", "Shown at once:\nopen, brief, draft")},
        "arrows": [("req", "fixed", ""), ("fixed", "free", "yes"), ("fixed", "jobs", "no"), ("jobs", "claude", ""), ("claude", "check", ""),
                   ("check", "drop", "no"), ("check", "change", "yes"), ("change", "yes", "yes"), ("yes", "do", ""), ("do", "undo", "kept"), ("change", "show", "no")]},
    "code_docs": {
        "title": "How a PDF of the documentation is made",
        "cell": (250, 140), "nodes": {
            "md": (0, 0, "store", "docs/GUIDE.md\ndocs/CODE.md"),
            "num": (1, 0, "step", "guide_number\nFigure 4.2, Table 9.1"),
            "html": (2, 0, "step", "Markdown to pages:\ncaptions, notes,\nlong tables cut"),
            "gap": (3, 0, "ask", "A figure left\nits page half empty?"),
            "move": (3, 1, "step", "Text of the same\nsection comes forward"),
            "rules": (4, 0, "step", "Page rules: nothing\nsplit, no lonely heading"),
            "pdf": (4, 1, "store", "PDF with contents,\nlinks and outline"),
            "test": (4, 2, "ask", "Tests: numbers,\npages, fingerprint"),
            "shots": (0, 1, "step", "guide_shots\npictures from\ninvented data")},
        "arrows": [("md", "num", ""), ("num", "html", ""), ("html", "gap", ""), ("gap", "move", "yes"), ("move", "rules", ""), ("gap", "rules", "no"),
                   ("rules", "pdf", ""), ("pdf", "test", ""), ("shots", "md", "pictures")]},
}


def draw_flow(name: str, out_dir: Path = OUT.parent) -> Path:
    """One of the DIAGRAMS as a picture, at twice the size it is shown at."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPolygonF

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    spec = DIAGRAMS[name]
    cw, ch = spec["cell"]
    bw, bh, left, top = cw - 62, ch - 54, 30, 70
    cols = max(n[0] for n in spec["nodes"].values()) + 1
    rows = max(n[1] for n in spec["nodes"].values()) + 1
    image = QImage(left * 2 + cols * cw - 62, top + rows * ch - 30, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor("#182230"))
    p.setFont(QFont("Helvetica Neue", 17, QFont.Bold))
    p.drawText(QRectF(0, 14, image.width(), 34), Qt.AlignCenter, spec["title"])
    box = {key: QRectF(left + c * cw, top + r * ch, bw, bh) for key, (c, r, _kind, _words) in spec["nodes"].items()}

    def edge(rect: QRectF, toward: QPointF) -> QPointF:
        """Where the line from the middle of a box to a point leaves the box."""
        mid = rect.center()
        dx, dy = toward.x() - mid.x(), toward.y() - mid.y()
        if abs(dx) * rect.height() > abs(dy) * rect.width():
            scale = (rect.width() / 2) / abs(dx)
        else:
            scale = (rect.height() / 2) / abs(dy) if dy else 0
        return QPointF(mid.x() + dx * scale, mid.y() + dy * scale)

    for start, end, words in spec["arrows"]:
        a, b = edge(box[start], box[end].center()), edge(box[end], box[start].center())
        p.setPen(QPen(QColor(GREY), 2.4))
        p.drawLine(a, b)
        line = QLineF(b, a)
        line.setLength(13)
        left_wing, right_wing = QLineF(line), QLineF(line)
        left_wing.setAngle(line.angle() + 24)
        right_wing.setAngle(line.angle() - 24)
        p.setBrush(QColor(GREY))
        p.drawPolygon(QPolygonF([b, left_wing.p2(), right_wing.p2()]))
        if words:
            p.setFont(QFont("Helvetica Neue", 11))
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            wide = p.fontMetrics().horizontalAdvance(words) + 10
            label = QRectF(mid.x() - wide / 2, mid.y() - 10, wide, 20)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ffffff"))
            p.drawRect(label)
            p.setPen(QColor("#45556b"))
            p.drawText(label, Qt.AlignCenter, words)
    for key, (_c, _r, kind, words) in spec["nodes"].items():
        fill, line_colour = LOOK[kind]
        rect = box[key]
        p.setPen(QPen(QColor(line_colour), 2.6))
        p.setBrush(QColor(fill))
        if kind == "ask":                               # a decision: cut corners
            cut = 16
            p.drawPolygon(QPolygonF([QPointF(rect.left() + cut, rect.top()), QPointF(rect.right() - cut, rect.top()), QPointF(rect.right(), rect.center().y()),
                                     QPointF(rect.right() - cut, rect.bottom()), QPointF(rect.left() + cut, rect.bottom()), QPointF(rect.left(), rect.center().y())]))
        else:
            p.drawRoundedRect(rect, 8 if kind == "store" else 14, 8 if kind == "store" else 14)
        lines = words.split("\n")
        p.setPen(QColor("#182230"))
        p.setFont(QFont("Helvetica Neue", 13, QFont.Bold))
        height = 20 + 17 * (len(lines) - 1)
        y = rect.center().y() - height / 2
        p.drawText(QRectF(rect.left() + 4, y, rect.width() - 8, 20), Qt.AlignCenter, lines[0])
        p.setPen(QColor("#45556b"))
        p.setFont(QFont("Helvetica Neue", 11))
        for n, text in enumerate(lines[1:]):
            p.drawText(QRectF(rect.left() + 4, y + 20 + 17 * n, rect.width() - 8, 17), Qt.AlignCenter, text)
    p.end()
    out = out_dir / f"{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(out))
    _ = app
    return out


if __name__ == "__main__":
    print(draw().name)
    for diagram in DIAGRAMS:
        print(draw_flow(diagram).name)
