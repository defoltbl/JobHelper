"""What the window tests share: the real window loaded offscreen (`loaded_window`, used by the `ui` fixture in
conftest.py), a handle to poke it (`Ui`), the clean-up after each test, and the waits for a state."""
from contextlib import contextmanager
import os
from datetime import date, timedelta

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QUrl  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression, qmlContext  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from jobhelper import config, notify, qt_bridge, schedule, store, ui_api  # noqa: E402
from tests.conftest import ROOT  # noqa: E402


READY = {"claude": True, "plan": "pro", "claude_email": "me@example.com", "paid_api": False,
         "email": True, "email_addr": "jobs@example.com", "cv": "cv.docx",
         "vault": "ok", "changed_files": []}


def qml_source() -> str:
    """The text of every QML file of the window (it is split into one file per window)."""
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(list((ROOT / "ui_qt").glob("*.qml")) + list((ROOT / "ui_qt").glob("*.js"))))


def _wait(ms):
    """Let the window run for `ms`. In short steps: under test the window's loop keeps Python to
    itself for the whole of one wait (the running app does not), and a background thread, such
    as the connection check, gets its turn only between two waits."""
    import time
    end = time.monotonic() + ms / 1000
    while True:
        left = end - time.monotonic()
        if left <= 0:
            break
        QTest.qWait(max(1, min(8, round(left * 1000))))
        time.sleep(0.002)                  # a real pause: this is when background threads run


class Ui:
    """A loaded window plus helpers to poke it."""

    def __init__(self, engine, bridge, conn, warnings):
        self.engine, self.bridge, self.conn, self.warnings = engine, bridge, conn, warnings
        self.win = engine.rootObjects()[0]

    def find(self, name):
        obj = self.win.findChild(QObject, name)
        assert obj is not None, f"no QML object named {name!r}"
        return obj

    def seen(self, root="statusPanel"):
        """Every item drawn under a part of the window, rows made by a Repeater included
        (those are children on screen but not children of the object tree, so find() misses them)."""
        todo, out = [self.win.findChild(QQuickItem, root)], []
        while todo:
            item = todo.pop()
            out.append(item)
            todo.extend(item.childItems())
        return out

    def drawn(self, name, root="statusPanel"):
        for item in self.seen(root):
            if item.objectName() == name:
                return item
        raise AssertionError(f"nothing named {name!r} is drawn in {root}")

    # each window lives in its own file; names inside a window are only known in that window's context
    WINDOWS = ["tableDialog", "detailDialog", "compareDialog", "formDialog", "assistantDialog", "prepEditDialog", "helpDialog", "prepDialog", "letterDialog",
               "responseDialog", "limitDialog", "welcome", "optDialog", "remoteDialog", "schedDialog",
               "navPanel", "stagePanel", "statusPanel", "pipelineBar"]      # the parts of the main screen

    def _inside(self, obj):
        """The context of the file an object was written in. For a window made in Main.qml
        that is not the object's own context (Main's) but the one its children were created in."""
        own = qmlContext(obj)
        if obj is self.win:
            return own
        for child in obj.findChildren(QObject):
            ctx = qmlContext(child)
            if ctx is not None and ctx != own and ctx.parentContext() == own:
                return ctx
        return own

    def js(self, code, scope=None):
        """Evaluate in the main window's context; if a name is only known inside one of
        the windows (its text fields, lists …), evaluate there instead."""
        targets = [scope] if scope else [self.win] + [self.win.findChild(QObject, name) for name in self.WINDOWS]
        error = ""
        for target in targets:
            if target is None:
                continue
            expr = QQmlExpression(self._inside(target), target, code)   # that file's context, so its ids resolve
            value = expr.evaluate()
            if not expr.hasError():
                return value[0] if isinstance(value, tuple) else value
            error = error or expr.error().toString()
            if "ReferenceError" not in expr.error().toString():
                break
        raise AssertionError(error)

    def wait(self, ms=60):
        _wait(ms)


# the windows a test may leave open (stacked ones before the window under them)
DIALOGS = ["detailDialog", "compareDialog", "formDialog", "assistantDialog", "prepEditDialog", "helpDialog", "prepDialog",
           "letterDialog", "responseDialog", "limitDialog", "remoteDialog", "optDialog", "aboutDialog", "schedDialog", "tableDialog"]


def _email_answer(ui):
    """Saving a mailbox tries it in the background; wait for the card to get its answer."""
    welcome = ui.find("welcome")
    for _ in range(200):
        if not welcome.property("emailBusy"):
            return
        ui.wait(20)
    raise AssertionError("the mailbox check never answered")


def _begin_search(ui):
    ui.js('resultFade.stop(); runMode = "search"; runResult = ""; runProgress = 0; stageKey = ""; resetRobots()')
    ui.bridge._set_running(True)


def _titles(ui):
    return [ui.js(f"listView.model[{i}].primary") for i in range(ui.find("listView").property("count"))]


def _card_values(ui):
    return {t.property("text") for t in ui.seen() if isinstance(t.property("text"), str)}


def _open_job(ui, job_id="app"):
    ui.js(f'detailDialog.show("{job_id}")')
    _until_open(ui, "detailDialog")


def _open(ui, dialog, ms=450, most_ms=6000):
    """Open a window and wait until its opening animation has ended (its onOpened has run). A fixed pause was
    too short on GitHub's busier Mac runners: the Options window had not read its backup folder yet."""
    ui.js("open()", dialog)
    ui.wait(ms)
    waited = 0
    while dialog.property("opened") is False and waited < most_ms:
        ui.wait(50); waited += 50


def _until_open(ui, name, most_ms=4000):
    """Wait for a window's opening animation to end: a fixed pause is too short on a busy machine."""
    dialog, waited = ui.find(name), 0
    ui.wait(450)
    while dialog.property("opened") is not True and waited < most_ms:
        ui.wait(50); waited += 50
    assert dialog.property("opened") is True


def _until_true(ui, check, most_ms=4000):
    """Wait until `check()` is true, letting the window work meanwhile; a fixed pause is too short on a busy machine."""
    waited = 0
    while not check() and waited < most_ms:
        ui.wait(50); waited += 50
    return check()


def _until_shown(ui, name, most_ms=4000):
    """Wait until an item is really on screen: a window that fades in (the welcome card) shows nothing before."""
    item, waited = ui.find(name), 0
    while item.property("visible") is not True and waited < most_ms:
        ui.wait(50); waited += 50
    return item


def _until_closed(ui, window, most_ms=4000):
    """Wait for a window's closing animation to end. `window` is its name or the window itself."""
    dialog, waited = (ui.find(window) if isinstance(window, str) else window), 0
    while dialog.property("visible") is not False and waited < most_ms:
        ui.wait(50); waited += 50
    assert dialog.property("visible") is False


def _until(done, seconds=2.0):
    import time
    end = time.time() + seconds
    while time.time() < end and not done():
        time.sleep(0.01)
    return done()


def _border_with_focus(ui, window, field):
    """The colour of a field's border while the field has the keyboard focus, and the theme's red."""
    scope = ui.find(window)
    ui.win.requestActivate()
    ui.js(f"{field}.forceActiveFocus()", scope)
    assert _until(lambda: ui.js(f"{field}.activeFocus", scope) is True), f"{field} has the focus"
    return ui.js(f"String({field}.background.border.color)", scope), ui.js("String(theme.crit)")


def _wait_scored(ui):
    import time
    for _ in range(300):
        time.sleep(0.02)
        ui.wait(10)
        if ui.js("detailDialog.scoreBusy") is False:
            return
    raise AssertionError("the score never came back")


def _contrast(a, b):
    def lum(h):
        r, g, b_ = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4   # noqa: E731
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b_)
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _wait_idle(ui, dialog):
    for _ in range(200):                  # up to 6 s: GitHub's Mac runners are about three times slower
        if not dialog.property("busy"):
            return
        ui.wait(30)


def _listed(value):
    """A list property of a window, whichever way Qt hands it over."""
    return list(value.toVariant()) if hasattr(value, "toVariant") else list(value)


def close_left_windows(ui):
    """After each window test: no window left open, no review queue, no pretend run. A test that fails half-way
    must not leave a window open for the next one (on a slow runner one late window once failed five later tests)."""
    ui.js("detailDialog.reviewQueue = []")
    # A test that failed after starting a pretend run left the window "running" (and maybe paused), so every later
    # test that starts something was refused with "A search or scan is running" (six failures on main, 17 October).
    if ui.bridge._running or ui.win.property("paused"):
        ui.bridge.limitChanged.emit({"paused": False, "can_resume": False, "window": "", "used": 0, "resets_at": "",
                                     "resets_day": "", "message": ""})
        ui.bridge._set_running(False)
        ui.js('resultFade.stop(); runResult = ""; runMode = ""; runProgress = 0')
    left = [d for d in (ui.win.findChild(QObject, name) for name in DIALOGS) if d is not None and d.property("visible")]
    for dialog in left:
        ui.js("close()", dialog)
    for _ in range(120):
        if not any(d.property("visible") for d in left):
            break
        ui.wait(50)


@contextmanager
def loaded_window(tmp_path_factory):
    """The real window, loaded offscreen on a temporary data folder with two made-up jobs; taken down at the end
    as the app does it."""
    data = tmp_path_factory.mktemp("ui_data")
    mp = pytest.MonkeyPatch()
    for name, value in {
        "DATA_DIR": data, "CV_DIR": data / "cv", "LETTERS_DIR": data / "cover_letters",
        "TAILORED_CV_DIR": data / "tailored_cvs", "JOBS_JSON": data / "jobs.json",
        "MY_LETTERS_DIR": data / "my_letters", "COVER_LETTERS_DIR": data / "my_letters",
        "EXCEL_PATH": data / "applications.xlsx", "NEW_JOBS_EXCEL": data / "new_jobs.xlsx",
        "PROFILE_JSON": data / "profile.json", "USAGE_JSON": data / "usage.json",
        "RESPONSES_DB": data / "responses.db", "RESPONSES_REPORT": data / "responses_report.xlsx",
        "ENV_PATH": data / ".env", "MODEL": config.MODEL, "MIN_LEAD_SCORE": config.MIN_LEAD_SCORE,
        "IMAP_USER": "", "IMAP_PASSWORD": "",
    }.items():
        mp.setattr(config, name, value)
    conn = dict(READY)
    mp.setattr(ui_api.Api, "connections", lambda self: dict(conn))
    mp.setattr(qt_bridge.Bridge, "_ping_usage", lambda self: self.usageReady.emit())   # no Claude call
    sent = []
    mp.setattr(notify, "send", lambda message, subtitle="": sent.append((message, subtitle)) or True)   # no real notification
    mp.setattr(schedule, "read_schedule",
               lambda: {"enabled": False, "weekday": 1, "hour": 9, "minute": 0, "label": "Off"})
    config.ensure_dirs()
    store.save_jobs([
        store.new_job(id="lead", title="Junior Python Developer", company="Acme", match_score=80,
                      match_tier="strong", status="letter_ready"),
        store.new_job(id="app", title="QA Engineer", company="Beta", status="waiting",
                      date_applied=(date.today() - timedelta(days=20)).isoformat(),
                      description="We use Python, Docker and Kubernetes.", match_score=64, match_tier="strong",
                      match_reason="Solid Python background."),
    ])

    warnings = []
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    bridge = qt_bridge.Bridge()
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.load(QUrl.fromLocalFile(str(ROOT / "ui_qt" / "Main.qml")))
    assert engine.rootObjects(), "Main.qml failed to load: %s" % warnings
    handle = Ui(engine, bridge, conn, warnings)
    handle.sent = sent
    handle.win.show()
    _wait(2300)                            # splash → welcome card
    for _ in range(200):                   # the connection check is a thread; wait for it, not for a guessed time
        if handle.win.property("connChecked") and handle.find("welcome").property("phase") == "card":
            break
        _wait(30)
    _wait(700)                             # the card's own entrance
    try:
        yield handle
    finally:
        _take_down(handle, engine, bridge, mp)


def _take_down(handle, engine, bridge, mp):
    """Close as the app does: the window goes before the bridge, so no binding is left calling a bridge that is gone
    (the terminal used to show "TypeError: Cannot call method … of null" on every exit)."""
    import app_qt
    from PySide6.QtCore import qInstallMessageHandler
    said = []
    earlier = qInstallMessageHandler(lambda kind, context, message: said.append(message))
    try:
        handle.win.close()
        app_qt.shut_down(engine)
        del engine, bridge
        QTest.qWait(50)
    finally:
        qInstallMessageHandler(earlier)
        mp.undo()
    assert not [m for m in said if "of null" in m or "TypeError" in m], said
