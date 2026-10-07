"""The QML window, loaded offscreen with a stubbed bridge: it must load without
warnings, and the welcome screen, progress bar and validators must behave."""
import os
from datetime import date, timedelta

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QUrl  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression, qmlContext  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from jobhelper import config, notify, qt_bridge, schedule, store, ui_api  # noqa: E402
from tests.conftest import ROOT  # noqa: E402

READY = {"claude": True, "plan": "pro", "claude_email": "me@example.com", "paid_api": False,
         "email": True, "email_addr": "jobs@example.com", "cv": "cv.docx",
         "vault": "ok", "changed_files": []}


def qml_source() -> str:
    """The text of every QML file of the window (it is split into one file per window)."""
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "ui_qt").glob("*.qml")))


class Ui:
    """A loaded window plus helpers to poke it."""

    def __init__(self, engine, bridge, conn, warnings):
        self.engine, self.bridge, self.conn, self.warnings = engine, bridge, conn, warnings
        self.win = engine.rootObjects()[0]

    def find(self, name):
        obj = self.win.findChild(QObject, name)
        assert obj is not None, f"no QML object named {name!r}"
        return obj

    # each window lives in its own file; names inside a window are only known in that window's context
    WINDOWS = ["tableDialog", "detailDialog", "compareDialog", "answersDialog", "helpDialog", "prepDialog", "letterDialog",
               "responseDialog", "limitDialog", "welcome", "optDialog", "schedDialog"]

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
        QTest.qWait(ms)


@pytest.fixture(scope="module")
def ui(qapp, tmp_path_factory):
    data = tmp_path_factory.mktemp("ui_data")
    mp = pytest.MonkeyPatch()
    for name, value in {
        "DATA_DIR": data, "CV_DIR": data / "cv", "LETTERS_DIR": data / "cover_letters",
        "TAILORED_CV_DIR": data / "tailored_cvs", "JOBS_JSON": data / "jobs.json",
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
    QTest.qWait(2300)                      # splash → welcome card
    yield handle
    handle.win.close()
    del engine
    mp.undo()


def test_window_loads_without_qml_warnings(ui):
    assert ui.warnings == []
    assert ui.win.property("connChecked") is True


def test_counts_come_from_the_data(ui):
    assert ui.js("countsData.leads") == 1
    assert ui.js("countsData.applications") == 1


# ── welcome screen ──────────────────────────────────────────────────────────
def test_welcome_card_is_shown_ready_at_launch(ui):
    welcome = ui.find("welcome")
    assert welcome.property("phase") == "card"
    assert welcome.property("shown") is True and welcome.property("first") is True
    assert welcome.property("ready") is True
    assert ui.find("welcomeStart").property("enabled") is True


def test_start_enters_the_app_and_the_chip_reopens_the_card(ui):
    welcome = ui.find("welcome")
    ui.js("welcome.finish()")
    assert welcome.property("shown") is False
    ui.wait(700)
    assert welcome.property("visible") is False        # fully animated away
    ui.js("welcome.openCard()")
    assert welcome.property("shown") is True and welcome.property("first") is False
    assert ui.find("welcomeStart").property("text") == "Done"
    ui.js("welcome.finish()")
    ui.wait(700)


def test_welcome_is_not_ready_without_claude_or_cv(ui):
    welcome = ui.find("welcome")
    for missing in ({"claude": False}, {"cv": ""}, {"paid_api": True},
                    {"vault": "locked"}, {"changed_files": ["CV rules"]}):
        ui.win.setProperty("connData", {**READY, **missing})
        assert welcome.property("ready") is False, missing
    ui.win.setProperty("connData", dict(READY))
    assert welcome.property("ready") is True


def test_changed_files_block_start_until_approved(ui, monkeypatch):
    approved = []
    monkeypatch.setattr(qt_bridge.integrity, "approve", lambda names=None: approved.append(names) or ["cv_rules"])
    welcome = ui.find("welcome")
    ui.win.setProperty("connData", {**READY, "changed_files": ["CV rules", "Master CV"]})
    assert welcome.property("protectedOk") is False
    assert ui.find("welcomeStart").property("enabled") is (not welcome.property("first"))
    ui.js("bridge.approveChanges()")
    assert approved == [None]
    ui.win.setProperty("connData", dict(READY))
    assert welcome.property("protectedOk") is True and ui.warnings == []


def test_plain_storage_without_keychain_does_not_block(ui):
    welcome = ui.find("welcome")
    ui.win.setProperty("connData", {**READY, "vault": "off"})
    assert welcome.property("ready") is True
    ui.win.setProperty("connData", dict(READY))


def test_welcome_rejects_a_bad_email_and_stays_open(ui, monkeypatch):
    saved = []
    monkeypatch.setattr(config, "set_imap", lambda user, pwd, lookback=None: saved.append((user, pwd)))
    welcome = ui.find("welcome")
    ui.js("welcome.openCard()")
    welcome.setProperty("editEmail", True)
    for email, password in (("not-an-email", ""), ("jobs@example.com", "short"), ("jobs@example.com", "пароль")):
        welcome.setProperty("emailDraft", email)
        welcome.setProperty("pwDraft", password)
        ui.js("welcome.saveEmail()")
        assert welcome.property("emailErr") != "", (email, password)
        assert welcome.property("editEmail") is True
    assert saved == []
    welcome.setProperty("emailDraft", "jobs@example.com")
    welcome.setProperty("pwDraft", "abcd abcd abcd abcd")          # spaces as Google shows it
    ui.js("welcome.saveEmail()")
    assert saved == [("jobs@example.com", "abcd abcd abcd abcd")]
    assert welcome.property("emailErr") == "" and welcome.property("editEmail") is False
    ui.js("welcome.finish()")
    ui.wait(700)


# ── run progress ────────────────────────────────────────────────────────────
def _begin_search(ui):
    ui.js('resultFade.stop(); runMode = "search"; runResult = ""; runProgress = 0; stageKey = ""; resetRobots()')
    ui.bridge._set_running(True)


def test_progress_follows_stages_and_job_counts(ui):
    b = ui.bridge
    _begin_search(ui)
    b.agentChanged.emit("a1", "running", "")
    assert ui.win.property("stageKey") == "a1" and ui.find("a1").property("active") is True
    b.agentChanged.emit("a1", "done", "junior")
    b.agentChanged.emit("a2", "running", "")
    b.progressChanged.emit("a2", 50, 100)
    assert ui.win.property("runProgress") == pytest.approx(0.04 + 0.24 * 0.5)
    b.agentChanged.emit("a2", "done", "+14 new")
    b.agentChanged.emit("a3", "running", "")
    b.progressChanged.emit("a3", 7, 14)
    assert ui.win.property("runProgress") == pytest.approx(0.28 + 0.68 * 0.5)
    assert ui.find("a2").property("done") is True and ui.find("a3").property("active") is True
    b.progressChanged.emit("a2", 0, 100)                 # a late signal from a finished stage
    assert ui.win.property("runProgress") == pytest.approx(0.28 + 0.68 * 0.5)
    b.runFinished.emit("search", "Done · +14 new jobs, 6 letters + CVs ready.")
    b._set_running(False)
    assert ui.win.property("runProgress") == pytest.approx(1.0)
    assert ui.win.property("runResult") == "ok" and ui.win.property("stageKey") == ""
    assert ui.warnings == []


def test_failed_run_is_marked_as_error_not_complete(ui):
    b = ui.bridge
    _begin_search(ui)
    b.agentChanged.emit("a2", "running", "")
    b.runFinished.emit("search", "Error: No usable job source")
    b._set_running(False)
    assert ui.win.property("runResult") == "error"
    assert ui.win.property("runProgress") < 1
    ui.js('resultFade.stop(); runResult = ""; runMode = ""; runProgress = 0')


def test_elapsed_time_format(ui):
    assert ui.js("fmtElapsed(0)") == "00:00"
    assert ui.js("fmtElapsed(75)") == "01:15"
    assert ui.js("fmtElapsed(3605)") == "60:05"


# ── dialogs and views ───────────────────────────────────────────────────────
@pytest.mark.parametrize("name", ["optDialog", "schedDialog"])
def test_dialogs_open_and_close(ui, name):
    dialog = ui.find(name)
    ui.js("open()", dialog)
    ui.wait(500)
    assert dialog.property("opened") is True
    ui.js("close()", dialog)
    ui.wait(400)
    assert dialog.property("visible") is False
    assert ui.warnings == []


@pytest.mark.parametrize("view, rows", [("new", 1), ("app", 1), ("resp", 0), ("ana", 21)])       # 2 headings + 5 lines for the last 7 days + 14 all-time rows
def test_views_list_the_data(ui, view, rows):
    ui.js(f'openView("{view}")')
    ui.wait(450)
    assert ui.find("tableDialog").property("opened") is True
    assert ui.find("listView").property("count") == rows
    ui.js("close()", ui.find("tableDialog"))
    ui.wait(350)
    assert ui.warnings == []


def test_both_themes_render_without_warnings(ui):
    for dark in (False, True):
        ui.win.setProperty("dark", dark)
        ui.wait(120)
    assert ui.warnings == []


# ── input validation helpers ────────────────────────────────────────────────
@pytest.mark.parametrize("code, expected", [
    ('isEmail("you@gmail.com")', True),
    ('isEmail("you@gmail")', False),
    ('isEmail("you gmail.com")', False),
    ('isAppPassword("abcd efgh ijkl mnop")', True),
    ('isAppPassword("abcdefgh1jklmnop")', False),
    ('isAppPassword("short")', False),
    ('hasNonLatin("привет")', True),
    ('hasNonLatin("エンジニア")', True),
    ('hasNonLatin("Plzeň developer")', False),
    ('looksLikeRole("junior python developer")', True),
    ('looksLikeRole("asdfgh qwerty")', False),
    ('isSlug("proton-ag")', True),
    ('isSlug("no spaces")', False),
    ('cityEN("Praha")', "Prague"),
    ('cityEN("")', "Prague"),
    ('cityEN("Berlin")', "Berlin"),
])
def test_validators(ui, code, expected):
    assert ui.js(code) == expected


# ── job detail, follow-up, stop ─────────────────────────────────────────────
def test_follow_up_count_is_shown_in_the_sidebar(ui):
    assert ui.js("countsData.followups") == 1


def test_detail_view_shows_score_keywords_and_follow_up(ui, monkeypatch):
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "Python and Docker")
    dialog = ui.find("detailDialog")
    ui.js('detailDialog.show("app")')
    ui.wait(500)
    assert dialog.property("opened") is True
    assert ui.find("detailTitle").property("text") == "QA Engineer"
    assert ui.js("detailDialog.job.reason") == "Solid Python background."
    assert ui.js("detailDialog.job.matched.join(',')") == "Python,Docker"
    assert ui.js("detailDialog.job.missing.join(',')") == "Kubernetes"
    assert ui.js("detailDialog.fu.due") is True
    ui.js("detailDialog.draft = bridge.followupDraft(detailDialog.job.id)")
    ui.wait(100)
    assert "QA Engineer" in ui.find("draftBody").property("text")
    assert ui.js("bridge.markFollowedUp(detailDialog.job.id)") is True
    ui.js("detailDialog.refresh(); countsData = bridge.counts()")
    assert ui.js("detailDialog.fu.due") is False and ui.js("countsData.followups") == 0
    ui.js("detailDialog.close()")
    ui.wait(400)
    assert ui.warnings == []


def test_detail_view_ignores_an_unknown_job(ui):
    ui.js('detailDialog.show("does-not-exist")')
    ui.wait(150)
    assert ui.find("detailDialog").property("visible") is False


def test_run_button_becomes_stop_while_running(ui, monkeypatch):
    button = ui.find("runButton")
    assert button.property("text") == "▶ Run search"
    _begin_search(ui)
    assert button.property("text") == "■ Stop" and button.property("enabled") is True
    ui.js("stopRun()")
    assert ui.win.property("stopping") is True and ui.bridge._stop.is_set()
    assert button.property("text") == "Stopping…" and button.property("enabled") is False
    ui.bridge.agentChanged.emit("a3", "running", "")
    ui.bridge.runFinished.emit("search", "Stopped. Everything finished before that is saved.")
    ui.bridge._set_running(False)
    assert ui.win.property("stopping") is False and ui.win.property("runResult") == "error"
    assert ui.find("a3").property("active") is False          # no robot keeps working after a stop
    assert button.property("text") == "▶ Run search"
    ui.bridge._stop.clear()
    ui.js('resultFade.stop(); runResult = ""; runMode = ""; runProgress = 0')


def test_email_scan_shows_real_progress(ui):
    ui.js('resultFade.stop(); runMode = "scan"; runResult = ""; runProgress = 0; stageKey = ""')
    ui.bridge._set_running(True)
    ui.bridge.agentChanged.emit("a5", "running", "")
    ui.bridge.progressChanged.emit("a5", 3, 12)
    assert ui.win.property("runProgress") == pytest.approx(0.25)
    ui.bridge.runFinished.emit("scan", "Scanned 12 emails · 1 new (0 rejections).")
    ui.bridge._set_running(False)
    assert ui.win.property("runProgress") == pytest.approx(1.0)
    ui.js('resultFade.stop(); runResult = ""; runMode = ""; runProgress = 0')


def test_follow_up_days_option_is_loaded_and_saved(ui):
    dialog = ui.find("optDialog")
    ui.js("open()", dialog)
    ui.wait(450)
    spin = ui.find("fuSpin")
    assert spin.property("value") == 10
    ui.js("close()", dialog)
    ui.wait(350)
    ui.bridge.saveOptions({**ui.bridge.options(), "followup_days": 21})
    ui.js("optsData = bridge.options()")              # what Save does in the window
    ui.js("open()", dialog)
    ui.wait(450)
    assert spin.property("value") == 21
    ui.js("close()", dialog)
    ui.wait(350)


def test_scan_period_option_is_loaded_and_saved(ui):
    dialog = ui.find("optDialog")
    ui.bridge.saveOptions({**ui.bridge.options(), "scan_days": 45})
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert ui.find("scanSpin").property("value") == 45
    ui.js("close()", dialog)
    ui.wait(350)
    assert ui.warnings == []


# ── paused on Claude's limit ────────────────────────────────────────────────
def test_pause_shows_resume_warning_and_sound_then_resume_turns_blue(ui, monkeypatch):
    played = []
    monkeypatch.setattr(qt_bridge.subprocess, "Popen", lambda cmd, **k: played.append(cmd[0]))
    run, resume, dialog = ui.find("runButton"), ui.find("resumeButton"), ui.find("limitDialog")
    _begin_search(ui)
    ui.bridge.agentChanged.emit("a3", "running", "")
    info = {"paused": True, "can_resume": False, "window": "5-hour", "used": 99, "resets_at": "13:20",
            "resets_day": "07 Oct", "message": "limit"}
    ui.bridge.limitChanged.emit(info)
    ui.wait(450)
    assert ui.win.property("paused") is True and ui.win.property("working") is False
    assert run.property("visible") is False and resume.property("visible") is True
    assert ui.find("stopWhilePaused").property("visible") is True
    assert dialog.property("opened") is True and played == ["afplay"]
    assert "5-hour limit is used up (99%)" in ui.find("limitText").property("text")
    assert "13:20" in ui.find("limitText").property("text")
    assert ui.find("a3").property("active") is False                      # the robot rests while paused
    why = ui.win.property("limitWhy")
    assert "Can't resume yet" in why and "13:20" in why and "turns blue" in why
    grey = resume.property("color").name()
    ui.js("close()", dialog)
    ui.wait(350)

    ui.bridge.limitChanged.emit({**info, "can_resume": True})
    ui.wait(350)
    assert ui.win.property("canResume") is True and "limit is back" in ui.win.property("limitWhy")
    assert resume.property("color").name() != grey                       # grey -> blue
    assert dialog.property("visible") is False and played == ["afplay"]  # no second warning for the same pause

    ui.bridge.limitChanged.emit({**info, "paused": False, "can_resume": False})
    assert ui.win.property("paused") is False and run.property("visible") is True
    assert ui.find("a3").property("active") is True                       # the same agent continues
    ui.bridge.runFinished.emit("search", "Done · +0 new jobs, 0 letters + CVs ready.")
    ui.bridge._set_running(False)
    ui.js('resultFade.stop(); runResult = ""; runMode = ""; runProgress = 0')
    assert ui.warnings == []


# ── number fields and the Last run card ─────────────────────────────────────
def test_typed_number_is_saved_without_pressing_enter(ui):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest as _QTest
    dialog, spin = ui.find("optDialog"), ui.find("scanSpin")
    ui.bridge.saveOptions({**ui.bridge.options(), "scan_days": 120})
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert spin.property("value") == 120
    assert spin.property("activeFocus") is False                 # nothing is pre-selected on open
    ui.js("contentItem.forceActiveFocus(); contentItem.selectAll()", spin)
    ui.win.requestActivate()
    for key in (Qt.Key_1, Qt.Key_0):                             # type over it, no Enter, no click elsewhere
        _QTest.keyClick(ui.win, key)
    ui.wait(80)
    assert spin.property("value") == 10
    assert spin.property("wheelEnabled") is False
    ui.js("close()", dialog)
    ui.wait(350)


def test_last_run_card_survives_a_restart(ui):
    ui.bridge._api.note_run(when="07 Oct 14:20", found="+12 new", letters=20, cvs=19)
    ui.bridge._api.note_run(scan="07 Oct · 2 new")
    assert ui.bridge.lastRun() == {"when": "07 Oct 14:20", "found": "+12 new", "letters": 20, "cvs": 19,
                                   "scan": "07 Oct · 2 new"}
    ui.js("reloadAll()")                                         # what the window does when it starts
    assert ui.js("lastRunData.letters") == 20 and ui.js("lastRunData.found") == "+12 new"
    # a long value must not break the layout (it is shortened inside the card)
    ui.js('lastRunData = ({ when: "07 Oct 14:20", found: "a very long value that would never fit in this narrow card at all" })')
    ui.wait(80)
    ui.js("lastRunData = bridge.lastRun()")
    assert ui.warnings == []


# ── status, apply date, merge and the second mailbox in the window ──────────
def test_status_buttons_and_apply_date_in_the_job_view(ui):
    ui.js('detailDialog.show("app")')
    ui.wait(450)
    assert ui.js("detailDialog.job.is_application") is True
    ui.js('detailDialog.setStatus("rejected")')
    assert ui.js("detailDialog.job.status") == "rejected"
    ui.js('detailDialog.setStatus("waiting")')
    field = ui.find("dateField")
    field.setProperty("text", "07.10.2026")
    ui.js("detailDialog.saveDate()")
    assert "YYYY-MM-DD" in ui.js("detailDialog.dateErr")                    # red message, window stays open
    assert ui.find("detailDialog").property("opened") is True
    field.setProperty("text", "2026-09-30")
    ui.js("detailDialog.saveDate()")
    assert ui.js("detailDialog.dateErr") == "" and ui.js("detailDialog.job.applied") == "2026-09-30"
    assert ui.js("detailDialog.job.applied_from_email") is False
    ui.js("detailDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_second_mailbox_row_follows_the_connection(ui):
    welcome = ui.find("welcome")
    ui.js("welcome.openCard()")
    ui.wait(300)
    ui.win.setProperty("connData", {**READY, "email2": False, "email2_addr": ""})
    assert ui.find("secondMailAdd").property("text") == "Add"
    ui.js("welcome.editBox = 2; welcome.editEmail = true")
    welcome.setProperty("emailDraft", READY["email_addr"])
    welcome.setProperty("pwDraft", "abcdabcdabcdabcd")
    ui.js("welcome.saveEmail()")
    assert "already your main job email" in welcome.property("emailErr")    # refused, card stays open
    ui.js('welcome.editEmail = false; welcome.emailErr = ""; welcome.editBox = 1')
    ui.win.setProperty("connData", {**READY, "email2": True, "email2_addr": "second@example.com"})
    assert ui.find("secondMailAdd").property("text") == "Change"
    ui.win.setProperty("connData", dict(READY))
    ui.js("welcome.finish()")
    ui.wait(600)
    assert ui.warnings == []


# ── skip words, readable replies, analytics that add up ─────────────────────
def test_skip_words_and_exceptions_are_edited_loaded_and_saved(ui):
    dialog, skip, keep = ui.find("optDialog"), ui.find("skipTags"), ui.find("keepTags")
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert ui.js('all().join(",")', skip) == "intern,internship"          # the default
    assert ui.js('add("Student")', skip) is True and ui.js('add("student")', skip) is False
    assert "already" in skip.property("err")
    assert ui.js('add("стажёр")', skip) is False and "Latin" in skip.property("err")
    assert ui.js('add("7")', skip) is False
    assert ui.js('add("graduate program")', keep) is True
    assert ui.js('all().join(",")', skip) == "intern,internship,student"
    ui.js("close()", dialog)
    ui.wait(350)
    ui.bridge.saveOptions({**ui.bridge.options(), "skip_words": ["sales"], "keep_words": ["sales engineer"]})
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert ui.js('all().join(",")', skip) == "sales" and ui.js('all().join(",")', keep) == "sales engineer"
    ui.js("close()", dialog)
    ui.wait(350)
    ui.bridge.saveOptions({**ui.bridge.options(), "skip_words": ["intern", "internship"], "keep_words": []})
    assert ui.warnings == []


@pytest.mark.parametrize("roles, skips, keeps, clash", [
    (["software engineering intern"], ["intern"], [], True),
    (["Machine Learning Interns"], ["intern"], [], True),
    (["internal tools engineer"], ["intern"], [], False),
    (["junior python developer"], ["intern", "internship"], [], False),
    (["software engineering intern"], ["intern"], ["software engineering"], False),
    (["c++ developer"], ["c++"], [], True),
])
def test_a_search_role_may_not_contain_a_skipped_word(ui, roles, skips, keeps, clash):
    import json
    message = ui.js(f"roleClash({json.dumps(roles)}, {json.dumps(skips)}, {json.dumps(keeps)})", ui.find("optDialog"))
    assert (message != "") is clash
    if clash:
        assert roles[0] in message and "skip" in message


def test_click_a_reply_to_read_it_and_open_its_application(ui):
    from jobhelper import db
    db.upsert_response({"msg_id": "<r1@x>", "job_id": "app", "company": "Beta", "role": "QA Engineer", "stage": "rejection",
                        "received_date": "Mon, 5 Oct 2026 10:15:00 +0200", "subject": "Your application", "from_addr": "hr@beta.com",
                        "summary": "Beta chose another candidate.", "rejection_category": "went_with_other_candidate"})
    ui.js('openView("resp")')
    ui.wait(450)
    assert ui.js("listView.model[0].rid") == "<r1@x>"
    ui.js('responseDialog.show("<r1@x>")')
    ui.wait(450)
    assert ui.find("responseDialog").property("opened") is True
    assert ui.find("responseTitle").property("text") == "Beta"
    assert ui.find("responseSummary").property("text") == "Beta chose another candidate."
    assert ui.js("responseDialog.r.category") == "went with other candidate" and ui.js("responseDialog.r.date") == "2026-10-05 10:15"
    assert ui.js("responseDialog.r.job_title") == "QA Engineer"
    ui.js("responseDialog.close(); tableDialog.close()")
    ui.wait(400)
    ui.js('responseDialog.show("<missing>")')
    assert ui.find("responseDialog").property("visible") is False
    assert ui.warnings == []


def test_analytics_rows_add_up(ui):
    ui.js('openView("ana")')
    ui.wait(450)
    rows = {r["primary"]: int(r["value"]) for r in [
        {"primary": ui.js(f"listView.model[{i}].primary"), "value": ui.js(f"listView.model[{i}].value")}
        for i in range(ui.find("listView").property("count"))] if str(r["value"]).strip() != ""}
    assert rows["Applications"] == rows["↳ waiting for an answer"] + rows["↳ in interviews now"] + rows["↳ offers"] + rows["↳ rejected"]
    assert rows["Reply emails"] == (rows["↳ confirmations"] + rows["↳ interview emails"] + rows["↳ tests and tasks"]
                                    + rows["↳ rejections"] + rows["↳ other"])
    assert rows["Why the rejection emails said no"] == rows["↳ rejections"]
    ui.js("tableDialog.close()")
    ui.wait(350)


# ── search / filter / sort, not interested, letter editor ───────────────────
def _titles(ui):
    return [ui.js(f"listView.model[{i}].primary") for i in range(ui.find("listView").property("count"))]


def test_tables_can_be_searched_filtered_and_sorted(ui):
    from jobhelper import store as _store
    jobs = _store.load_jobs()
    extra = [_store.new_job(id="t1", title="Data Engineer", company="Zeta Corp", match_score=40, match_tier="stretch",
                            status="letter_ready", date_posted="2026-10-06", location="Brno"),
             _store.new_job(id="t2", title="Python Developer", company="Alpha", match_score=20, date_posted="2026-10-01"),
             _store.new_job(id="t3", title="QA Tester", company="Midway", date_posted="2026-10-07")]
    _store.save_jobs(jobs + extra)
    try:
        ui.js('openView("new")')
        ui.wait(450)
        dialog, search = ui.find("tableDialog"), ui.find("searchField")
        assert len(_titles(ui)) == 4 and ui.js("titleTxt.text", dialog).endswith("— 4")
        assert _titles(ui)[0].startswith("Junior Python Developer")              # best score first
        search.setProperty("text", "python")
        assert len(_titles(ui)) == 2 and ui.js("titleTxt.text", dialog).endswith("2 of 4")
        search.setProperty("text", "brno zeta")                                  # all words must match, place included
        assert _titles(ui) == ["Data Engineer  ·  Zeta Corp"]
        search.setProperty("text", "no such thing")
        assert _titles(ui) == []
        search.setProperty("text", "")
        ui.js('groupFilter = "stretch"; apply()', dialog)
        assert _titles(ui) == ["Data Engineer  ·  Zeta Corp"]
        ui.js('groupFilter = "not scored"; apply()', dialog)
        assert _titles(ui) == ["QA Tester  ·  Midway"]
        ui.js('groupFilter = ""; sortKey = "company"; apply()', dialog)
        assert [t.split("  ·  ")[1] for t in _titles(ui)] == ["Acme", "Alpha", "Midway", "Zeta Corp"]
        ui.js('sortKey = "date"; apply()', dialog)
        assert _titles(ui)[0].startswith("QA Tester") and _titles(ui)[1].startswith("Data Engineer")
        groups = ui.js("groups.map(function (g) { return g.key + ':' + g.n; }).join(',')", dialog)
        assert groups == "strong:1,stretch:1,no documents:1,not scored:1"
    finally:
        ui.js("tableDialog.close()")
        ui.wait(350)
        _store.save_jobs(jobs)
    assert ui.warnings == []


def test_not_interested_hides_the_lead_and_the_filter_restores_it(ui):
    from jobhelper import store as _store
    jobs = _store.load_jobs()
    _store.save_jobs(jobs + [_store.new_job(id="bye", title="Boring Role", company="Nope Ltd", match_score=10)])
    try:
        ui.js('openView("new")')
        ui.wait(450)
        assert any(t.startswith("Boring Role") for t in _titles(ui))
        ui.js('detailDialog.show("bye")')
        ui.wait(400)
        assert ui.find("notInterested").property("visible") is True
        assert ui.js('bridge.dismissJob("bye").ok') is True
        ui.js("detailDialog.close(); refreshOpenView()")
        ui.wait(400)
        assert not any(t.startswith("Boring Role") for t in _titles(ui)) and ui.js("countsData.leads") is not None
        ui.js('groupFilter = "not interested"; apply()', ui.find("tableDialog"))
        assert _titles(ui) == ["Boring Role  ·  Nope Ltd"] and ui.js("listView.model[0].actions[0].kind") == "restore"
        assert ui.js('bridge.restoreJob("bye").ok') is True
        ui.js("refreshOpenView()")
        ui.wait(300)
        assert ui.js("groupFilter", ui.find("tableDialog")) == ""                # that group is empty again
        assert any(t.startswith("Boring Role") for t in _titles(ui))
    finally:
        ui.js("tableDialog.close()")
        ui.wait(350)
        _store.save_jobs(jobs)
    assert ui.warnings == []


def test_letter_editor_edits_rewrites_and_saves(ui, monkeypatch):
    import shutil
    from jobhelper import cover_letter, llm, store as _store
    template = ROOT / "data" / "cover_letter_template.docx"
    if not template.exists():
        pytest.skip("letter template not present")
    monkeypatch.setattr(config, "LETTER_TEMPLATE", config.DATA_DIR / "cover_letter_template.docx")
    shutil.copy2(template, config.LETTER_TEMPLATE)
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "Alex Novak\nPython, Docker.")
    paras = [("I am applying because the work matches what I build every day. " * 5).strip() for _ in range(5)]
    cover_letter.build_docx(config.LETTER_TEMPLATE, config.LETTERS_DIR / "L.docx", "QA Engineer", paras, date_text="7 October 2026")
    jobs = _store.load_jobs()
    lead = _store.find(jobs, "lead"); lead["cover_letter_file"] = "L.docx"
    _store.save_jobs(jobs)
    dialog = ui.find("letterDialog")
    ui.js('letterDialog.show("lead")')
    ui.wait(450)
    assert dialog.property("opened") is True and ui.js("letterDialog.texts.length") == 5
    assert ui.js("letterDialog.dirty") is False and ui.find("letterSave").property("enabled") is False

    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"paragraph": "I would like to bring the same drive to this team."})
    ui.js("letterDialog.rewrite(3)")
    assert ui.js("letterDialog.busyIndex") == 3
    for _ in range(100):
        ui.wait(30)
        if ui.js("letterDialog.busyIndex") == -1:
            break
    assert ui.js("letterDialog.texts[3]") == "I would like to bring the same drive to this team."
    assert ui.js("letterDialog.dirty") is True and "rewritten" in ui.js("letterDialog.info")
    assert cover_letter.read_letter(config.LETTERS_DIR / "L.docx")["paragraphs"][3] == paras[3]     # nothing saved yet

    ui.js("letterDialog.save()")
    assert ui.js("letterDialog.err") == "" and ui.js("letterDialog.dirty") is False
    assert cover_letter.read_letter(config.LETTERS_DIR / "L.docx")["paragraphs"][3] == "I would like to bring the same drive to this team."
    ui.js('letterDialog.setText(0, ""); letterDialog.save()')
    assert "5 paragraphs" in ui.js("letterDialog.err") and dialog.property("opened") is True        # red message, stays open
    ui.js("letterDialog.close()")
    ui.wait(350)
    lead["cover_letter_file"] = ""
    _store.save_jobs(jobs)
    assert ui.warnings == []


# ── insights and interview preparation ──────────────────────────────────────
def test_insights_view_lists_roles_keywords_and_skills(ui, monkeypatch):
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "Python and Docker")
    ui.js('openView("ins")')
    ui.wait(450)
    rows = [(ui.js(f"listView.model[{i}].primary"), ui.js(f"listView.model[{i}].heading")) for i in range(ui.find("listView").property("count"))]
    heads = [text for text, heading in rows if heading is True]
    assert heads == ["What is working: kinds of role", "What is working: where the job came from", "Week by week",
                     "How long companies take to decide", "Search keywords", "Skills to learn", "Why jobs score low",
                     "What the postings pay"]
    assert any(str(text).startswith("Week of ") and str(text).endswith("(this week)") for text, _ in rows)
    assert any(text == "Kubernetes" for text, _ in rows)                           # asked for in the seeded posting, not in the CV
    assert ui.js("sorts.length", ui.find("tableDialog")) == 0                      # a plain list, no toolbar
    ui.js("tableDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_interview_preparation_from_the_job_window(ui, monkeypatch):
    from jobhelper import llm
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "Alex Novak\nPython, Docker.")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {
        "summary": "Mostly Python.", "ask_them": ["What is the team like?"], "revise": ["Docker"],
        "questions": [{"kind": "about you", "question": "Tell me about yourself.", "why": "Opening.", "answer": "I am a junior developer."},
                      {"kind": "technical", "question": "Kubernetes?", "why": "", "answer": "I have years of production experience with Kubernetes."}]})
    ui.js('detailDialog.show("app")')
    ui.wait(450)
    assert ui.js("detailDialog.job.has_prep") is False and ui.find("prepMake").property("text") == "Prepare"
    ui.js('detailDialog.prepErr = ""; detailDialog.prepBusy = true; detailDialog.prepJob = "app"; bridge.prepareInterview("app")')
    assert ui.find("prepMake").property("enabled") is False
    import time
    for _ in range(200):
        time.sleep(0.02)                                  # let the background worker run
        ui.wait(10)
        if ui.js("detailDialog.prepBusy") is False:
            break
    prep = ui.find("prepDialog")
    for _ in range(60):                                   # the window opens with an animation
        ui.wait(30)
        if prep.property("opened") is True:
            break
    assert ui.js("detailDialog.prepErr") == "", ui.js("detailDialog.prepErr")
    assert prep.property("opened") is True and ui.find("prepFor").property("text") == "Beta  ·  QA Engineer"
    assert ui.js("prepDialog.prep.questions.length") == 2
    assert ui.js("prepDialog.prep.questions[1].check") == "Kubernetes"             # an unbacked claim is flagged for you
    assert ui.js("detailDialog.job.has_prep") is True
    ui.js('prepDialog.note = "x"; prepDialog.close(); detailDialog.close()')
    ui.wait(400)
    ui.js('prepDialog.show("lead")')
    assert prep.property("visible") is False                                       # nothing saved for that job
    assert ui.warnings == []


# ── help, and the cost wording ──────────────────────────────────────────────
def test_help_opens_from_the_button_and_covers_the_app(ui):
    dialog = ui.find("helpDialog")
    assert ui.find("helpButton").property("text") == "Help"
    ui.js("open()", dialog)
    ui.wait(500)
    assert dialog.property("opened") is True
    titles = ui.js("topics.map(function (t) { return t.title; }).join('|')", dialog)
    for expected in ("What JobHelper does", "A normal week", "Scores and labels", "Claude and the limit", "Privacy and safety"):
        assert expected in titles
    text = ui.js("topics.map(function (t) { return t.lines.join(' '); }).join(' ')", dialog)
    assert "never sends" in text and "never invents experience" in text and "recovery key" in text
    assert "—" not in text                                             # en dash rule applies to the help too
    ui.js("close()", dialog)
    ui.wait(350)
    assert ui.warnings == []


def test_last_run_card_says_what_you_paid_and_the_api_price(ui):
    source = qml_source()
    assert '"You paid"' in source and '"Same work via API"' in source and "$0 · subscription" in source
    assert '"Total cost"' not in source and '"Cost (API-equiv.)"' not in source
    assert ui.js("usageData.cost !== undefined") in (True, False) and ui.warnings == []


# ── about you, notifications, backups, readable help ────────────────────────
def test_new_options_are_loaded_and_saved(ui):
    dialog = ui.find("optDialog")
    ui.bridge.saveOptions({**ui.bridge.options(), "about_right_to_work": "EU citizen", "about_start": "one month",
                           "notifications": False, "keep_backups": 25})
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert ui.find("rightField").property("text") == "EU citizen" and ui.find("startField").property("text") == "one month"
    assert ui.find("notifySw").property("checked") is False and ui.find("keepSpin").property("value") == 25
    ui.js("close()", dialog)
    ui.wait(350)
    ui.bridge.saveOptions({**ui.bridge.options(), "about_right_to_work": "", "about_start": "", "notifications": True, "keep_backups": 10})
    assert ui.warnings == []


def test_help_marks_key_words(ui):
    text = ui.js("topics.map(function (t) { return t.lines.join(' '); }).join(' ')", ui.find("helpDialog"))
    for word in ("Run search", "Scan email", "Mark applied", "strong", "stretch", "Not interested", "recovery key"):
        assert f"<b>{word}</b>" in text, word
    assert text.count("<b>") == text.count("</b>") and "<b><b>" not in text
    source = qml_source()
    assert "textFormat: Text.StyledText" in source


# ── dates, company notes, pasted replies, CV comparison, pay ────────────────
def _open_job(ui, job_id="app"):
    ui.js(f'detailDialog.show("{job_id}")')
    ui.wait(450)
    assert ui.find("detailDialog").property("opened") is True


def test_a_date_on_a_job_shows_on_the_main_screen_and_is_announced(ui):
    card = ui.find("upcomingCard")
    assert card.property("visible") is False                                       # nothing planned: no empty card
    _open_job(ui)
    ui.js('evDate.text = "next week"; detailDialog.saveEvent()')
    assert "YYYY-MM-DD" in ui.find("eventErr").property("text") and ui.find("eventErr").property("visible") is True
    assert ui.find("detailDialog").property("opened") is True and ui.js("upcomingData.length") == 0
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    ui.js(f'evDate.text = "{tomorrow}"; evTime.text = "14:30"; evNote.text = "Teams call"; detailDialog.eventKind = "call"; detailDialog.saveEvent()')
    assert ui.js("detailDialog.eventErr") == "" and ui.js("detailDialog.job.event.kind") == "call"
    assert ui.js("upcomingData.length") == 1 and ui.js("upcomingData[0].label") == "tomorrow"
    assert card.property("visible") is True
    ui.sent.clear()
    assert ui.js("bridge.remind()") == 1 and ui.js("bridge.remind()") == 0         # once a day
    assert ui.sent == [("Tomorrow at 14:30: call · Beta", "Reminder")]
    ui.js('detailDialog.show("app")')                                              # reopening shows what was saved
    ui.wait(200)
    assert ui.find("evDate").property("text") == tomorrow and ui.find("evNote").property("text") == "Teams call"
    ui.js("bridge.clearEvent(detailDialog.job.id); detailDialog.refresh(); upcomingData = bridge.upcoming()")
    assert card.property("visible") is False and ui.find("evDate").property("text") == ""
    ui.js("detailDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_company_notes_are_kept_for_the_company(ui):
    from jobhelper import planner
    _open_job(ui)
    ui.js('cnContact.text = "Jana, HR"; cnSalary.text = "55k"; cnAsked.text = "SQL joins"; cnNotes.text = "Nice team"; detailDialog.saveNotes()')
    assert ui.js("detailDialog.notesInfo") == "Saved for Beta."
    assert planner.company_notes("beta")["asked"] == "SQL joins"
    ui.js("detailDialog.close()")
    ui.wait(350)
    _open_job(ui)
    assert ui.find("cnContact").property("text") == "Jana, HR" and ui.find("cnNotes").property("text") == "Nice team"
    ui.js('cnContact.text = ""; cnSalary.text = ""; cnAsked.text = ""; cnNotes.text = ""; detailDialog.saveNotes()')
    assert planner.company_notes("Beta")["updated"] == ""
    ui.js("detailDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_a_pasted_reply_is_filed_from_the_job_window(ui, monkeypatch):
    import time

    from jobhelper import db, llm
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"stage": "acknowledged", "summary": "They got it."})
    _open_job(ui)
    assert ui.js("detailDialog.replyOpen") is False
    ui.js('detailDialog.replyOpen = true; replyText.text = "ok"; detailDialog.fileReply()')
    assert "too short" in ui.js("detailDialog.replyErr") and ui.js("detailDialog.replyBusy") is False
    ui.js('replyText.text = "Hello, thank you for applying. We received your application and will be in touch."; detailDialog.fileReply()')
    assert ui.js("detailDialog.replyBusy") is True
    for _ in range(200):
        time.sleep(0.02)                                  # let the background worker run
        ui.wait(10)
        if ui.js("detailDialog.replyBusy") is False:
            break
    assert ui.js("detailDialog.replyErr") == "", ui.js("detailDialog.replyErr")
    assert ui.js("detailDialog.replyInfo") == "Filed as: acknowledged." and ui.js("detailDialog.replyOpen") is False
    assert ui.find("replyText").property("text") == ""
    rows = [r for r in db.all_responses() if r["msg_id"].startswith("pasted-")]
    assert len(rows) == 1 and rows[0]["job_id"] == "app"
    ui.js("detailDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_cv_comparison_window(ui, monkeypatch):
    import docx

    from jobhelper import agent1_cv

    def make(path, lines):
        d = docx.Document()
        for line in lines:
            d.add_paragraph(line)
        d.save(str(path))
        return path

    master = make(config.DATA_DIR / "master.docx", ["Alex Novak", "PROFILE", "I know Python."])
    make(config.TAILORED_CV_DIR / "cv_lead.docx", ["Alex Novak", "PROFILE", "I know Python and SQL."])
    monkeypatch.setattr(agent1_cv, "find_cv", lambda: master)
    _open_job(ui, "lead")
    assert ui.find("compareCv").property("visible") is False                       # no adapted CV yet
    ui.js("compareDialog.show(detailDialog.job.id)")
    ui.wait(150)
    assert ui.find("compareDialog").property("visible") is False                   # and nothing opens
    ui.bridge._api._change("lead", lambda jobs, j: j.update(tailored_cv_file="cv_lead.docx", salary="50 000 - 60 000 CZK"), render=False)
    ui.js("detailDialog.refresh()")
    assert ui.find("compareCv").property("visible") is True
    assert ui.js("detailDialog.job.pay.low") == 50000
    ui.js("compareDialog.show(detailDialog.job.id)")
    ui.wait(500)
    dialog = ui.find("compareDialog")
    assert dialog.property("opened") is True
    assert "1 paragraph changed" in ui.find("compareSummary").property("text")
    assert ui.js("compareDialog.data.rows[0].adapted") == "I know Python<b> and SQL</b>."
    assert ui.js("compareDialog.data.rows[0].master") == "I know Python."
    ui.js("compareDialog.close()")
    ui.wait(300)
    ui.js("detailDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_insights_list_what_postings_pay(ui, monkeypatch):
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "Python and Docker")
    ui.bridge._api._change("lead", lambda jobs, j: j.update(salary="50 000 - 60 000 CZK", desired_monthly_czk=55000), render=False)
    ui.js('openView("ins")')
    ui.wait(450)
    count = ui.find("listView").property("count")
    rows = [(ui.js(f"listView.model[{i}].primary"), ui.js(f"listView.model[{i}].secondary"), ui.js(f"listView.model[{i}].value")) for i in range(count)]
    pay = [r for r in rows if r[0] == "Junior Python Developer  ·  Acme"]
    assert pay and pay[0][2] == "60k" and "50–60k CZK" in pay[0][1] and "your target 55k: around your target" in pay[0][1]
    assert any("1 of 2 postings state it" in str(r[1]) for r in rows)
    ui.js("tableDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_scan_all_folders_switch_is_saved(ui):
    dialog = ui.find("optDialog")
    assert ui.bridge.options()["scan_all_folders"] is False
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    switch = ui.find("foldersSw")
    assert switch.property("checked") is False
    ui.bridge.saveOptions({**ui.bridge.options(), "scan_all_folders": True})
    ui.js("close()", dialog)
    ui.wait(350)
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert switch.property("checked") is True
    ui.js("close()", dialog)
    ui.wait(350)
    ui.bridge.saveOptions({**ui.bridge.options(), "scan_all_folders": False})
    assert ui.warnings == []


def test_application_only_cards_are_hidden_for_a_new_job_and_nothing_overflows(ui, monkeypatch):
    from jobhelper import planner
    for name in ("cv_lead.docx", "cv_lead.pdf"):
        (config.TAILORED_CV_DIR / name).write_bytes(b"x")
    for name in ("L_lead.docx", "L_lead.pdf"):
        (config.LETTERS_DIR / name).write_bytes(b"x")
    ui.bridge._api._change("lead", lambda jobs, j: j.update(tailored_cv_file="cv_lead.docx", cover_letter_file="L_lead.docx",
                                                             url="https://example.com/job"), render=False)
    monkeypatch.setattr(ui_api.Api, "_comparable", lambda self, j: True)
    monkeypatch.setattr(ui_api.Api, "_editable_letter", lambda self, j: True)
    _open_job(ui, "lead")
    for card in ("eventCard", "replyCard", "notesCard"):
        assert ui.find(card).property("visible") is False, card
    dialog_width = ui.js("detailDialog.width")
    footer = ui.find("detailFooter")
    assert footer.property("width") <= dialog_width                              # every button on, still inside the window
    assert ui.find("detailDocs").property("height") > 40                         # the document buttons wrapped to a second line
    assert ui.js("detailFlick.width") <= dialog_width
    planner.save_company_notes("Acme", {"contact": "Jana"})                      # notes kept from an earlier application
    ui.js("detailDialog.refresh()")
    assert ui.find("notesCard").property("visible") is True and ui.find("eventCard").property("visible") is False
    planner.save_company_notes("Acme", {})
    ui.js("detailDialog.close()")
    ui.wait(350)
    _open_job(ui, "app")
    for card in ("eventCard", "replyCard", "notesCard"):
        assert ui.find(card).property("visible") is True, card
    ui.js("detailDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("lead", lambda jobs, j: j.update(tailored_cv_file="", cover_letter_file="", url=""), render=False)
    assert ui.warnings == []


def test_sidebar_counts_and_icons_share_one_column(ui):
    source = qml_source()
    assert 'objectName: "navTail_" + modelData.k; implicitWidth: 46' in source
    tail = source[source.index('objectName: "navTail_"'):][:1400]
    assert tail.count("anchors.centerIn: parent") >= 3                             # the pill, its number and the icon


def test_filtered_out_list_opens_from_the_last_run_card(ui):
    from jobhelper import agent2_search
    agent2_search.save_dropped([
        {"title": "Software Engineering Intern", "company": "Acme", "source": "linkedin", "url": "https://example.com/1",
         "group": "skip word", "reason": 'The title has a word you skip ("intern").'},
        {"title": "Backend Developer", "company": "Beta", "source": "jobs.cz", "url": "",
         "group": "too many years", "reason": "Asks for 6+ years of experience."}])
    ui.bridge._api.note_run(filtered=2)
    ui.js("lastRunData = bridge.lastRun()")
    ui.wait(100)
    source = qml_source()
    assert 'lastRunData.filtered + " · see why ›"' in source and "win.openView(modelData.view)" in source
    ui.js('openView("skip")')
    ui.wait(450)
    assert ui.find("listView").property("count") == 2
    assert ui.js("listView.model[0].primary") == "Software Engineering Intern  ·  Acme"
    assert ui.js("listView.model[1].secondary") == "Asks for 6+ years of experience.   ·  jobs.cz"
    assert ui.js("listView.model[0].actions.length") == 1 and ui.js("listView.model[1].actions.length") == 0
    assert ui.js("tableDialog.groups.length") == 2                                # a filter chip per reason
    ui.js("tableDialog.close()")
    ui.wait(350)
    agent2_search.save_dropped([])
    assert ui.warnings == []


def test_polish_empty_filtered_row_older_master_note_and_old_letter_chip(ui, monkeypatch):
    source = qml_source()
    assert '" · see why ›" : "after next search"' in source                      # not a bare dash that looks broken
    assert 'letter_old_format === true ? "letter: older format, open in Word"' in source
    note = ui.find("olderMaster")
    monkeypatch.setattr(ui_api.Api, "cv_compare", lambda self, job_id: {
        "ok": True, "company": "Acme", "title": "Dev", "file": "x.docx", "older_master": True,
        "rows": [], "same": 3, "changed": 0, "added": 0, "removed": 0})
    ui.js('compareDialog.show("lead")')
    ui.wait(450)
    assert note.property("visible") is True
    ui.js("compareDialog.close()")
    ui.wait(300)
    monkeypatch.setattr(ui_api.Api, "cv_compare", lambda self, job_id: {
        "ok": True, "company": "Acme", "title": "Dev", "file": "x.docx", "older_master": False,
        "rows": [], "same": 3, "changed": 0, "added": 0, "removed": 0})
    ui.js('compareDialog.show("lead")')
    ui.wait(450)
    assert note.property("visible") is False
    ui.js("compareDialog.close()")
    ui.wait(300)
    assert ui.warnings == []


def test_level_words_and_years_are_edited_in_options(ui):
    dialog = ui.find("optDialog")
    start = ui.bridge.options()
    ui.bridge.saveOptions({**start, "level_words": ["senior", "lead"], "max_years": 6})
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert ui.js("levelTags.all().join(',')") == "senior,lead" and ui.find("yearsSpin").property("value") == 6
    ui.js('levelTags.add("Principal")')
    assert ui.js("levelTags.all().join(',')") == "senior,lead,principal"
    ui.js("close()", dialog)
    ui.wait(350)
    ui.bridge.saveOptions(start)
    assert ui.warnings == []


def test_help_has_a_what_changed_tab(ui):
    dialog = ui.find("helpDialog")
    ui.js("open()", dialog)
    ui.wait(450)
    assert ui.js("helpDialog.tab") == "how" and ui.js("helpDialog.changes.length") >= 2
    ui.js('helpDialog.tab = "new"')
    ui.wait(150)
    assert "2026" in ui.js("helpDialog.changes[0].date") and "<b>" in ui.js("helpDialog.changes[0].items[0]")
    ui.js('helpDialog.tab = "how"; helpDialog.close()')
    ui.wait(350)
    assert ui.warnings == []


def test_bring_back_button_in_the_filtered_out_list(ui):
    from jobhelper import agent2_search
    posting = store.new_job(id="back1", title="Senior Tester", company="Gamma", url="https://example.com/b")
    agent2_search.save_dropped([
        {"title": "Senior Tester", "company": "Gamma", "source": "linkedin", "url": "https://example.com/b",
         "group": "level", "reason": 'The title has a level you skip ("senior").', "job": posting},
        {"title": "Twin", "company": "Gamma", "source": "jobs.cz", "url": "", "group": "duplicate", "reason": "R.",
         "job": store.new_job(id="twin", title="Twin", company="Gamma")}])
    before = ui.js("bridge.counts().leads")
    ui.js('openView("skip")')
    ui.wait(450)
    assert [ui.js(f"listView.model[0].actions[{i}].label") for i in range(2)] == ["open ↗", "bring back"]
    assert ui.js("listView.model[1].actions.length") == 0                        # a duplicate would be removed again
    assert ui.js("bridge.bringBack(0).ok") is True
    ui.js("countsData = bridge.counts(); refreshOpenView()")
    ui.wait(300)
    assert ui.find("listView").property("count") == 1 and ui.js("countsData.leads") == before + 1
    ui.js("tableDialog.close()")
    ui.wait(350)
    jobs = [j for j in store.load_jobs() if j["id"] != "back1"]
    store.save_jobs(jobs)
    agent2_search.save_dropped([])
    ui.js("countsData = bridge.counts()")
    assert ui.warnings == []


# ── calendar file, thank-you note, answers, the last 7 days ─────────────────
def test_thank_you_card_appears_after_the_interview_day(ui, monkeypatch):
    opened = []
    monkeypatch.setattr(ui_api.Api, "_open", lambda self, target: opened.append(str(target)))
    today = date.today().isoformat()
    _open_job(ui)
    assert ui.find("thanksCard").property("visible") is False and ui.find("evCalendar").property("visible") is False
    ui.js(f'evDate.text = "{today}"; evTime.text = "00:00"; detailDialog.eventKind = "interview"; detailDialog.saveEvent()')
    assert ui.find("thanksCard").property("visible") is True and ui.find("evCalendar").property("visible") is True
    assert ui.js("bridge.exportEvent(detailDialog.job.id).ok") is True and opened[-1].endswith(".ics")
    ui.js("detailDialog.thanks = bridge.thanksDraft(detailDialog.job.id)")
    ui.wait(100)
    body = ui.find("thanksBody").property("text")
    assert "Thank you for the interview about the QA Engineer position" in body and "Beta" in body
    assert ui.js("bridge.markThanked(detailDialog.job.id)") is True
    ui.js("detailDialog.refresh()")
    assert ui.find("thanksCard").property("visible") is False                      # not offered twice for the same day
    ui.js("bridge.clearEvent(detailDialog.job.id); detailDialog.refresh(); upcomingData = bridge.upcoming(); detailDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_answers_window_saves_and_copies_with_the_job_filled_in(ui, monkeypatch):
    from jobhelper import answers
    copied = []
    monkeypatch.setattr(qt_bridge.Bridge, "copyText", lambda self, text: copied.append(text) or True)
    dialog = ui.find("answersDialog")
    ui.js('answersDialog.show("app")')
    ui.wait(450)
    assert dialog.property("opened") is True
    assert ui.js("answersDialog.all().length") == len(answers.STARTERS) and ui.js("answersDialog.all()[0].answer") == ""
    ui.js("answersDialog.copy(0)")
    assert "still empty" in ui.js("answersDialog.info") and copied == []
    ui.js('answersModel.setProperty(2, "answer", "I like what {company} builds, and the {role} role fits my skills."); answersDialog.dirty = true')
    ui.js('answersModel.append({ question: "", answer: "dropped: it has no question" }); answersDialog.save()')
    assert ui.js("answersDialog.info") == "Saved." and ui.js("answersDialog.dirty") is False
    saved = answers.load()
    assert len(saved) == len(answers.STARTERS) and saved[2]["answer"].startswith("I like what {company}")
    ui.js("answersDialog.copy(2)")
    assert copied == ["I like what Beta builds, and the QA Engineer role fits my skills."]
    assert "company and role filled in" in ui.js("answersDialog.info")
    ui.js("answersDialog.close()")
    ui.wait(350)
    answers.save([])
    (config.DATA_DIR / "answers.json").unlink()
    assert ui.warnings == []


def test_analytics_start_with_the_last_seven_days(ui):
    ui.js('openView("ana")')
    ui.wait(450)
    assert ui.js("listView.model[0].primary") == "The last 7 days" and ui.js("listView.model[0].heading") is True
    labels = [ui.js(f"listView.model[{i}].primary") for i in range(1, 6)]
    assert labels == ["New jobs found", "Ready to send", "Applications sent", "Replies received", "Follow-ups due"]
    assert ui.js("listView.model[6].primary") == "All time"
    ui.js("tableDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_start_up_check_shows_one_line_only_when_something_is_wrong(ui):
    banner = ui.find("healthBanner")
    assert ui.js("healthData.checks.length") > 5                                  # the check ran when the window started
    start = ui.js("healthData.problems")
    ui.js('healthData = { ok: true, checks: [], problems: 0, message: "" }')
    assert banner.property("visible") is False
    ui.js('healthData = { ok: false, problems: 2, message: "2 things need your attention. The first: No master CV yet.", '
          'checks: [{ name: "Master CV", ok: false, problem: "No master CV yet." }, { name: "Claude", ok: false, problem: "Not signed in." }, '
          '{ name: "Job list", ok: true, problem: "" }] }')
    assert banner.property("visible") is True and "No master CV yet" in ui.find("healthText").property("text")
    ui.js("showHealth()")
    ui.wait(450)
    assert ui.find("listView").property("count") == 3
    assert ui.js("listView.model[0].secondary") == "No master CV yet." and ui.js("listView.model[2].secondary") == "fine"
    ui.js("tableDialog.close()")
    ui.wait(350)
    ui.js("healthHidden = true")
    assert banner.property("visible") is False
    ui.js("healthHidden = false; healthData = bridge.selfCheck(true)")
    assert ui.js("healthData.problems") <= max(start, 3)
    ui.js('healthData = { ok: true, checks: [], problems: 0, message: "" }')
    assert ui.warnings == []


# ── the window is split into one file per window ────────────────────────────
def test_every_window_has_its_own_file_and_main_stays_small():
    folder = ROOT / "ui_qt"
    for name in ("TableDialog", "DetailDialog", "CompareDialog", "AnswersDialog", "HelpDialog", "PrepDialog", "LetterDialog",
                 "ResponseDialog", "LimitDialog", "WelcomeOverlay", "OptionsDialog", "ScheduleDialog", "SmallButton", "DetailCard"):
        assert (folder / f"{name}.qml").is_file(), name
    main = (folder / "Main.qml").read_text(encoding="utf-8")
    assert len(main.splitlines()) < 1400                                   # new windows go into their own file
    assert "\n    Dialog {" not in main and "\n    component " not in main


def test_a_split_file_never_hands_a_robot_its_own_empty_theme(ui):
    """Inside another file `theme: theme` means the robot's own (empty) property, not the app's colours."""
    for path in (ROOT / "ui_qt").glob("*.qml"):
        if path.name != "Main.qml":
            assert "theme: theme" not in path.read_text(encoding="utf-8"), path.name
    assert ui.js("logoBot.theme === win.appTheme && logoBot.theme.accent !== undefined") is True


def test_every_window_opens_from_the_main_file_without_warnings(ui):
    for name in Ui.WINDOWS:
        assert ui.win.findChild(QObject, name) is not None, name
    for code in ('openView("new")', "tableDialog.close()", "helpDialog.open()", "helpDialog.close()", "limitDialog.open()", "limitDialog.close()",
                 "schedDialog.open()", "schedDialog.close()", 'answersDialog.show("")', "answersDialog.close()"):
        ui.js(code)
        ui.wait(380)
    assert ui.warnings == []


def test_start_up_check_still_runs_when_the_sign_in_check_is_slow(ui):
    """The splash gives up waiting after 6 seconds and marks the connection check as done;
    the self-check must still run when the answer arrives later."""
    ui.js('healthRan = false; healthData = { ok: true, checks: [], problems: 0, message: "" }; connChecked = true')
    ui.bridge.connectionsReady.emit(dict(ui.conn))
    ui.wait(150)
    assert ui.js("healthRan") is True and ui.js("healthData.checks.length") > 5
    ui.js('healthData = { ok: true, checks: [], problems: 0, message: "" }')
    ui.bridge.connectionsReady.emit(dict(ui.conn))                       # clean and already run: not repeated on every recheck
    ui.wait(150)
    assert ui.js("healthData.checks.length") == 0
    assert ui.warnings == []


# ── apply checklist, one PDF, search in Answers ─────────────────────────────
def test_apply_checklist_ticks_steps_and_marks_applied(ui, monkeypatch):
    opened = []
    monkeypatch.setattr(ui_api.Api, "_open", lambda self, target: opened.append(str(target)))
    monkeypatch.setattr(ui_api.Api, "combined_pdf", lambda self, job_id: {"ok": True, "file": "both.pdf", "pages": 3})
    monkeypatch.setattr(ui_api.Api, "_can_combine", lambda self, j: bool(j.get("tailored_cv_file")))
    for folder, name in ((config.TAILORED_CV_DIR, "cv_lead.docx"), (config.LETTERS_DIR, "L_lead.docx")):
        (folder / name).write_bytes(b"x")
    ui.bridge._api._change("lead", lambda jobs, j: j.update(tailored_cv_file="cv_lead.docx", cover_letter_file="L_lead.docx",
                                                             url="https://example.com/job", apply_steps=[]), render=False)
    _open_job(ui, "lead")
    assert ui.find("applyCard").property("visible") is True and ui.find("onePdf").property("visible") is True
    assert ui.js("detailDialog.applySteps.map(function (s) { return s.key; }).join(',')") == "posting,cv,letter,combined,answers"
    assert ui.find("applyCount").property("text").startswith("0 of 5 done")
    ui.js('detailDialog.doStep("posting"); detailDialog.doStep("cv"); detailDialog.doStep("combined")')
    assert opened[0] == "https://example.com/job" and "cv_lead." in opened[1]
    assert ui.js("detailDialog.stepsDone") == 3 and ui.js("detailDialog.job.apply_steps.join(',')") == "posting,cv,combined"
    ui.js('detailDialog.doStep("answers")')
    ui.wait(450)
    assert ui.find("answersDialog").property("opened") is True and ui.js("answersDialog.jobId") == "lead"
    ui.js("answersDialog.close()")
    ui.wait(350)
    ui.js("detailDialog.close()")
    ui.wait(350)
    _open_job(ui, "lead")                                                         # the ticks are still there
    assert ui.find("applyCount").property("text").startswith("4 of 5 done")
    ui.js("detailDialog.close()")
    ui.wait(350)
    _open_job(ui, "app")
    assert ui.find("applyCard").property("visible") is False                      # already applied: no checklist
    ui.js("detailDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("lead", lambda jobs, j: j.update(tailored_cv_file="", cover_letter_file="", url="", apply_steps=[]), render=False)
    assert ui.warnings == []


def test_a_failed_step_is_not_ticked(ui, monkeypatch):
    monkeypatch.setattr(ui_api.Api, "combined_pdf", lambda self, job_id: {"ok": False, "msg": "The two PDF files could not be joined."})
    (config.TAILORED_CV_DIR / "cv_lead.docx").write_bytes(b"x")
    ui.bridge._api._change("lead", lambda jobs, j: j.update(tailored_cv_file="cv_lead.docx", url="", apply_steps=[]), render=False)
    _open_job(ui, "lead")
    ui.js('detailDialog.doStep("combined"); detailDialog.doStep("posting")')      # no single PDF, and this job has no link
    assert ui.js("detailDialog.stepsDone") == 0 and ui.js("(detailDialog.job.apply_steps || []).length") == 0
    ui.js("detailDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("lead", lambda jobs, j: j.update(tailored_cv_file="", apply_steps=[]), render=False)
    assert ui.warnings == []


def test_search_in_the_answers_window(ui):
    from jobhelper import answers
    answers.save([{"question": "Salary expectation", "answer": "60 000 CZK gross"}, {"question": "Notice period", "answer": "Two weeks"},
                  {"question": "Why {company}?", "answer": "I like the product."}, {"question": "Strengths", "answer": "Python and testing"},
                  {"question": "Work permit", "answer": "Not needed"}])
    ui.js('answersDialog.show("")')
    ui.wait(450)
    assert ui.find("ansSearch").property("visible") is True and ui.js("answersDialog.shown") == 5
    ui.js('answersDialog.query = "PYTHON"')
    assert ui.js("answersDialog.shown") == 1                                      # found in an answer, any letter case
    ui.js('answersDialog.query = "salary"')
    assert ui.js("answersDialog.shown") == 1 and ui.find("ansNone").property("visible") is False
    ui.js('answersDialog.query = "zzz"')
    assert ui.js("answersDialog.shown") == 0 and "Nothing matches" in ui.find("ansNone").property("text")
    ui.js("answersDialog.save()")                                                 # saving while a search hides rows keeps them all
    assert len(answers.load()) == 5 and ui.js("answersDialog.query") == ""
    ui.js("answersDialog.close()")
    ui.wait(350)
    (config.DATA_DIR / "answers.json").unlink()
    ui.js('answersDialog.show("")')
    ui.wait(400)
    assert ui.find("ansSearch").property("visible") is True                       # six starter questions
    ui.js("answersDialog.close()")
    ui.wait(350)
    assert ui.warnings == []
