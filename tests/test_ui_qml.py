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
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(list((ROOT / "ui_qt").glob("*.qml")) + list((ROOT / "ui_qt").glob("*.js"))))


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
    WINDOWS = ["tableDialog", "detailDialog", "compareDialog", "formDialog", "prepEditDialog", "helpDialog", "prepDialog", "letterDialog",
               "responseDialog", "limitDialog", "welcome", "optDialog", "schedDialog",
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
        QTest.qWait(ms)


@pytest.fixture(scope="module")
def ui(qapp, tmp_path_factory):
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
    ('cityEN("")', ""),
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
    for name in ("TableDialog", "DetailDialog", "CompareDialog", "FormAnswersDialog", "HelpDialog", "PrepDialog", "LetterDialog",
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
                 "schedDialog.open()", "schedDialog.close()", 'formDialog.show("app")', "formDialog.close()"):
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
    assert ui.find("formDialog").property("opened") is True and ui.js("formDialog.jobId") == "lead"
    assert ui.js("detailDialog.stepsDone") == 3                                   # opening is not doing: no tick yet
    ui.js('formDialog.fill({ items: [{ question: "Why us?", answer: "Because of your product.", check: "" }] }); formDialog.copy(0)')
    assert ui.js("detailDialog.stepsDone") == 4                                   # an answer was copied
    ui.js("formDialog.close()")
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


def test_options_show_your_own_letters_folder(ui, monkeypatch):
    opened = []
    monkeypatch.setattr(ui_api.Api, "_open", lambda self, target: opened.append(target))
    config.COVER_LETTERS_DIR.mkdir(parents=True, exist_ok=True)
    (config.COVER_LETTERS_DIR / "Alex_Novak_CoverLetter_Acme.docx").write_bytes(b"mine")
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert ui.js("optDialog.myLetters.count") == 1 and ui.js("optDialog.myLetters.name") == config.COVER_LETTERS_DIR.name
    assert ui.find("myLettersOpen").property("text") == "Open folder"
    assert ui.js("bridge.openMyLetters().ok") is True and opened == [config.COVER_LETTERS_DIR]
    ui.js("close()", dialog)
    ui.wait(350)
    (config.COVER_LETTERS_DIR / "Alex_Novak_CoverLetter_Acme.docx").unlink()
    assert ui.warnings == []


def test_without_a_city_the_search_does_not_start_and_options_open(ui):
    start = ui.bridge.options()
    ui.bridge.saveOptions({**start, "where": ""})
    ui.js("optsData = bridge.options()")
    ui.wait(100)
    assert ui.js('cityEN(optsData.where) || "No city yet"') == "No city yet"
    ui.js("startRun()")
    ui.wait(500)
    assert ui.win.property("appRunning") is False                                 # nothing was started
    assert ui.find("optDialog").property("opened") is True                        # straight to where the city is set
    assert "city" in ui.js("ticker.text").lower()
    assert ui.js("cityCombo.editText") == ""                                      # and no city is filled in for you
    ui.js("optDialog.close()")
    ui.wait(350)
    ui.bridge.saveOptions(start)
    ui.js("optsData = bridge.options()")
    assert ui.warnings == []


# ── hover that fades out cleanly ────────────────────────────────────────────
def test_hover_fades_to_the_same_colour_not_through_black(ui):
    """A colour animated to plain "transparent" passes through black and leaves a dark shadow behind."""
    assert ui.js('var c = clearOf(Qt.rgba(0.2, 0.4, 0.6, 1)); Math.round(c.r * 10) + "," + Math.round(c.g * 10) + "," + Math.round(c.b * 10) + "," + c.a') == "2,4,6,0"
    import re
    for path in sorted((ROOT / "ui_qt").glob("*.qml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            nearby = " ".join(lines[i:i + 3])
            if '"transparent"' in line and re.search(r"Behavior on (color|border\.color)", nearby) and "containsMouse" in line:
                raise AssertionError(f"{path.name}:{i + 1} fades a hover colour to plain transparent")


def test_insights_are_warmed_up_in_the_background(ui, monkeypatch):
    import time
    calls = []
    monkeypatch.setattr(ui_api.Api, "insights", lambda self: calls.append(1) or {})
    ui.js("bridge.warmUp()")
    for _ in range(100):
        time.sleep(0.01)
        if calls:
            break
    assert calls == [1]
    monkeypatch.setattr(ui_api.Api, "insights", lambda self: (_ for _ in ()).throw(RuntimeError("no data yet")))
    ui.js("bridge.warmUp()")                                   # a failure in the head start is not shown to anyone
    time.sleep(0.05)
    assert "bridge.warmUp()" in qml_source() and ui.warnings == []


# ── answers for one job's form ──────────────────────────────────────────────
def test_form_answers_are_drafted_per_job_edited_and_kept(ui, monkeypatch):
    import time

    from jobhelper import llm
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "Alex Novak\nPython, Docker.")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"answers": [
        {"n": 1, "answer": "I like how Beta tests its products.", "needs_you": ""},
        {"n": 2, "answer": "I expect [your figure] CZK gross per month.", "needs_you": "Your salary figure"}]})
    source = qml_source()
    assert 'objectName: "answersButton"' not in source and "answersDialog" not in source      # the general Answers button is gone
    ui.js('formDialog.show("app")')
    ui.wait(450)
    dialog = ui.find("formDialog")
    assert dialog.property("opened") is True and ui.find("formFor").property("text") == "Beta  ·  QA Engineer"
    ui.js("formDialog.draft()")
    assert "Paste the questions" in ui.js("formDialog.err") and ui.js("formDialog.busy") is False     # red message, nothing asked
    ui.js('fmQuestions.text = (formDialog.info.common || []).join("\\n")')
    assert "Why do you want to work at Beta?" in ui.js("fmQuestions.text")
    ui.js('fmQuestions.text = "Why do you want to work at Beta?\\nWhat are your salary expectations?"; formDialog.draft()')
    assert ui.js("formDialog.busy") is True and ui.find("fmDraft").property("text") == "Asking Claude…"
    for _ in range(200):
        time.sleep(0.02)                                  # let the background worker run
        ui.wait(10)
        if ui.js("formDialog.busy") is False:
            break
    assert ui.js("formDialog.err") == "", ui.js("formDialog.err")
    assert ui.js("fmModel.count") == 2 and "1 need your attention" in ui.js("formDialog.note")
    assert ui.js("fmModel.get(1).check") == "Your salary figure" and ui.find("fmDraft").property("text") == "Draft again"
    ui.js('fmModel.setProperty(1, "answer", "I expect 60 000 CZK gross per month."); formDialog.dirty = true; formDialog.save()')
    assert ui.js("formDialog.note") == "Saved with this job." and ui.js("formDialog.dirty") is False
    ui.js("formDialog.close()")
    ui.wait(350)
    ui.js('formDialog.show("app")')                        # they are still there, and only for this job
    ui.wait(400)
    assert ui.js("fmModel.get(1).answer") == "I expect 60 000 CZK gross per month."
    ui.js("formDialog.close()")
    ui.wait(350)
    ui.js('formDialog.show("lead")')
    ui.wait(400)
    assert ui.js("fmModel.count") == 0 and ui.js("fmQuestions.text") == ""
    ui.js("formDialog.close()")
    ui.wait(350)
    ui.bridge.saveFormAnswers("app", [])
    assert ui.warnings == []


def test_form_answers_show_the_reason_when_claude_cannot_be_asked(ui, monkeypatch):
    import time

    from jobhelper import llm

    def limit(*a, **k):
        raise llm.LimitReached("Claude's 7-day limit is used up (99%). It resets at 18:00 on 08 Oct.")
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "Alex Novak\nPython.")
    monkeypatch.setattr(llm, "ask_json", limit)
    ui.js('formDialog.show("app"); fmQuestions.text = "Why us?"; formDialog.draft()')
    for _ in range(200):
        time.sleep(0.02)
        ui.wait(10)
        if ui.js("formDialog.busy") is False:
            break
    assert "limit is used up" in ui.js("formDialog.err") and ui.find("formDialog").property("visible") is True    # stays open
    assert ui.js("fmQuestions.text") == "Why us?"                                 # what you pasted is not lost
    ui.js("formDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_form_answers_explain_every_wrong_step(ui, monkeypatch):
    """Whatever the user does wrong in this window gets a clear message, and nothing is lost silently."""
    monkeypatch.setattr(ui_api.Api, "make_form_answers", lambda self, job_id, text: pytest.fail("nothing may be drafted here"))
    ui.bridge.saveFormAnswers("app", [{"question": "Why us?", "answer": "Because of your product.", "check": ""},
                                      {"question": "Notice period?", "answer": "My notice period is [your notice period].", "check": "Fill it in"},
                                      {"question": "Anything else?", "answer": "", "check": ""}])
    ui.js('formDialog.show("app")')
    ui.wait(450)
    note = ui.find("fmNote")
    # pasted text that cannot be used: said while typing, in red, and Draft does nothing
    ui.js('fmQuestions.text = "' + "\\n".join(f"Question number {i}?" for i in range(18)) + '"')
    assert "That is 18 questions" in ui.find("fmHint").property("text")
    ui.js("formDialog.draft()")
    assert "one draft takes up to 15" in ui.find("fmHint").property("text") and ui.js("formDialog.busy") is False
    assert ui.js("formDialog.err") == ""                                           # said once, under the box, not twice
    ui.js('fmQuestions.text = "' + "x" * 320 + '"')
    assert "characters long" in ui.find("fmHint").property("text")
    ui.js('fmQuestions.text = "Why us?\\nwhy us?\\nSalary?"')
    assert ui.find("fmHint").property("text") == "2 questions found · 1 repeated line was left out · one Claude call"
    # drafting again would replace answers: asked first, never done on one click
    ui.js("formDialog.draft()")
    assert "replaces the 3 answers below" in note.property("text") and ui.js("formDialog.busy") is False
    ui.js('fmQuestions.text = "Why us?"')                                         # changing the text takes the confirmation back
    assert ui.js("formDialog.confirmDraft") is False
    # copying something unfinished
    ui.js("formDialog.copy(2)")
    assert "still empty" in note.property("text")
    ui.js("formDialog.copy(1)")
    assert "square brackets" in note.property("text")
    ui.js("formDialog.copy(0)")
    assert note.property("text") == "Copied."
    # saving says what is still open
    ui.js("formDialog.save()")
    assert note.property("text") == "Saved with this job. 1 answer is still empty. 1 answer still has a part in [square brackets] to fill in."
    # closing with an unsaved change: one warning, then it closes
    ui.js('fmModel.setProperty(0, "answer", "Changed and not saved."); formDialog.dirty = true; formDialog.tryClose()')
    ui.wait(250)
    dialog = ui.find("formDialog")
    assert dialog.property("visible") is True and "did not save" in note.property("text")
    assert ui.js("formDialog.closePolicy === 0") is True                           # Esc cannot throw the change away either
    ui.js("formDialog.tryClose()")
    ui.wait(450)
    assert dialog.property("visible") is False
    assert ui.bridge.formAnswers("app")["items"][0]["answer"] == "Because of your product."      # the discarded change was not saved
    # closing while Claude is working
    ui.js('formDialog.show("app"); formDialog.busy = true; formDialog.tryClose()')
    ui.wait(300)
    assert dialog.property("visible") is True and "still drafting" in note.property("text")
    ui.js("formDialog.busy = false; formDialog.tryClose()")
    ui.wait(450)
    ui.bridge.saveFormAnswers("app", [])
    assert ui.warnings == []


def test_a_message_behind_an_open_window_is_shown_on_top_of_it(ui):
    """The status line is hidden by any open window, so results and errors must also appear above it."""
    toast = ui.find("toast")
    ui.js('ticker.text = "said with no window open"')
    ui.wait(250)
    assert toast.property("visible") is False                                      # the status line itself is in view
    _open_job(ui, "app")
    ui.js('ticker.text = "No link for this job."')
    ui.wait(300)
    assert toast.property("visible") is True and ui.find("toastText").property("text") == "No link for this job."
    assert ui.js("toastBad") is True
    ui.js('ticker.text = "Opened the job posting in your browser."')
    ui.wait(250)
    assert ui.js("toastBad") is False and ui.find("toastText").property("text").startswith("Opened")
    ui.bridge.logChanged.emit("Scoring 3 of 14 jobs…")                             # a run's progress does not pop up
    ui.wait(250)
    assert ui.find("toastText").property("text").startswith("Opened")
    ui.js("toastTimer.interval = 150; toastTimer.restart()")
    ui.wait(600)
    assert toast.property("visible") is False                                      # and it goes away by itself
    ui.js("toastTimer.interval = 4200; detailDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


@pytest.mark.parametrize("text, bad", [
    ("Couldn't make the single PDF.", True), ("No link for this job.", True), ("That job could not be opened.", True),
    ("These CVs cannot be compared.", True), ("The pasted reply could not be filed.", True), ("That answer is still empty.", True),
    ("Choose the city to search in first (Options).", True), ("Not prepared: the limit is used up", True),
    ("Date saved. You will be reminded the day before.", False), ("Moved to Applications (waiting).", False),
    ("Opened one PDF with the letter and the CV (2 pages).", False), ("Merged into one application.", False),
])
def test_which_messages_are_shown_as_errors(ui, text, bad):
    assert ui.js("looksBad(" + repr(text).replace("\\'", "'") + ")") is bad


def test_preparation_opens_as_a_document_from_both_windows(ui, monkeypatch):
    calls = []
    monkeypatch.setattr(ui_api.Api, "prep_document", lambda self, job_id, reveal=False: calls.append((job_id, reveal)) or {"ok": True, "file": "Alex_Beta_Prep.docx"})
    ui.bridge._api._change("app", lambda jobs, j: j.__setitem__("interview_prep", {"made": "2026-10-08", "summary": "s", "questions": [
        {"kind": "about you", "question": "Tell me about yourself.", "why": "", "answer": "I am a junior developer.", "check": ""}]}), render=False)
    _open_job(ui, "app")
    assert ui.find("prepDocument").property("visible") is True
    ui.js('prepDialog.show("app")')
    ui.wait(450)
    assert ui.find("prepDoc").property("text") == "Open as document" and ui.find("prepShow").property("text") == "Show in folder"
    assert ui.js('bridge.prepDocument("app", false).file') == "Alex_Beta_Prep.docx" and ui.js('bridge.prepDocument("app", true).ok') is True
    assert calls == [("app", False), ("app", True)]
    ui.js("prepDialog.close()")
    ui.wait(350)
    ui.js("detailDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("app", lambda jobs, j: j.update(interview_prep={}), render=False)
    _open_job(ui, "app")
    assert ui.find("prepDocument").property("visible") is False                 # nothing prepared yet: no document button
    ui.js("detailDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_show_in_folder_buttons_and_the_laid_out_description(ui, monkeypatch):
    shown = []
    monkeypatch.setattr(ui_api.Api, "show_in_folder", lambda self, kind, job_id: shown.append((kind, job_id)) or {"ok": True, "file": "CV.pdf"})
    (config.TAILORED_CV_DIR / "cv_app.docx").write_bytes(b"x")
    ui.bridge._api._change("app", lambda jobs, j: j.update(tailored_cv_file="cv_app.docx",
                           description="We build tools. Requirements Strong Python Benefits Flexible hours"), render=False)
    _open_job(ui, "app")
    assert ui.find("showCv").property("visible") is True and ui.find("showLetter").property("visible") is False
    ui.js('detailDialog.showFile("cv")')
    assert shown == [("cv", "app")]
    assert ui.find("descText").property("text") == "We build tools.\n\nREQUIREMENTS\nStrong Python\n\nBENEFITS\nFlexible hours"
    ui.js("detailDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("app", lambda jobs, j: j.update(tailored_cv_file="", description="We use Python, Docker and Kubernetes."), render=False)
    assert ui.warnings == []


def test_more_about_your_work_is_saved_and_checked(ui):
    dialog = ui.find("optDialog")
    start = ui.bridge.options()
    ui.bridge.saveOptions({**start, "where": "Prague", "about_experience": "At Acme I wrote the import service in Python."})
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    field = ui.find("expField")
    assert field.property("text") == "At Acme I wrote the import service in Python."
    assert ui.find("expCount").property("text") == "45 of 4000 characters"
    ui.js('expField.text = "' + "x" * 4010 + '"')
    assert ui.find("expCount").property("text") == "10 characters too long (the limit is 4000)"
    source = qml_source()
    assert "characters too long. Shorten it, then save." in source and "about_experience: expField.text.trim()" in source
    ui.js("close()", dialog)
    ui.wait(350)
    ui.bridge.saveOptions(start)
    assert ui.warnings == []


def test_preparation_window_groups_questions_by_who_asks(ui):
    assert ui.js('prepDialog.who({ audience: "hr", kind: "technical" })') == "hr"
    assert ui.js('prepDialog.who({ kind: "technical" })') == "technical" and ui.js('prepDialog.who({ kind: "practical" })') == "hr"   # older saved ones
    source = qml_source()
    assert "If you speak with HR or a recruiter: plain words, no jargon" in source
    assert "If you speak with an engineer or the hiring manager: precise answers" in source


def test_preparation_window_shows_what_you_can_ask_each_listener(ui):
    ui.bridge._api._change("app", lambda jobs, j: j.update(interview_prep={"made": "2026-10-08", "summary": "s", "questions": [
        {"audience": "hr", "kind": "about you", "question": "Tell me about yourself.", "why": "", "answer": "I am a junior developer.", "check": ""}],
        "ask_hr": ["What are the next steps?"], "ask_technical": ["What would I own first?"], "ask_them": []}), render=False)
    ui.js('prepDialog.show("app")')
    ui.wait(450)
    assert ui.find("askHr").property("visible") is True and ui.find("askTech").property("visible") is True
    assert ui.js("prepDialog.prep.ask_hr[0]") == "What are the next steps?"
    ui.js("prepDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("app", lambda jobs, j: j.update(interview_prep={}), render=False)
    assert ui.warnings == []


def test_wanted_and_unwanted_roles_are_edited_in_options(ui):
    dialog = ui.find("optDialog")
    start = ui.bridge.options()
    ui.bridge.saveOptions({**start, "where": "Prague", "wanted_roles": ["backend developer"], "unwanted_roles": ["economist"]})
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert ui.js("wantedTags.all().join(',')") == "backend developer" and ui.js("unwantedTags.all().join(',')") == "economist"
    assert ui.js('unwantedTags.add("x")') is False and "job title" in ui.js("unwantedTags.err")       # wrong input is explained
    source = qml_source()
    assert "is under both the roles you want and the roles you do not want" in source
    note = ui.find("fieldsNote")                                                                      # your profession follows the roles as typed
    assert note.property("text").startswith("Your profession, as the app reads it from these roles: software and IT.")
    assert ui.js('wantedTags.add("registered nurse")') is True
    assert "these roles: software and IT, care and health." in note.property("text")
    ui.js('wantedTags.setAll(["beekeeper"])')
    assert note.property("text").startswith("The app cannot tell your profession from these roles or your CV") \
        or "from your CV" in note.property("text")
    assert "a title that names one is skipped before scoring" in source

    ui.js('wantedTags.setAll(["backend developer"])')                                                 # … or you pick it yourself
    names = ui.js("fieldsBox.read.all.join('|')").split("|")
    assert "software and IT" in names and "care and health" in names and ui.find("fieldsAuto").property("visible") is False
    assert note.property("text").endswith("Pick below to set it yourself.") and ui.js("optDialog.changed()") is False
    ui.js('optDialog.toggleField("law", fieldsBox.read.all); optDialog.toggleField("finance", fieldsBox.read.all)')
    assert ui.js("optDialog.pickedFields.join('|')") == "finance|law"                                 # kept in the app's order
    assert note.property("text").startswith("Your profession, as you picked it: finance, law.") and ui.find("fieldsAuto").property("visible") is True
    assert ui.js("optDialog.changed()") is True and ui.js("optDialog.collect().options.my_fields.join('|')") == "finance|law"
    ui.js('optDialog.toggleField("law", fieldsBox.read.all)')
    assert ui.js("optDialog.pickedFields.join('|')") == "finance"
    ui.js("optDialog.pickedFields = []")                                                              # "Let the app decide"
    assert "as the app reads it from these roles: software and IT" in note.property("text") and ui.js("optDialog.changed()") is False
    ui.js("close()", dialog)
    ui.wait(350)
    ui.bridge.saveOptions({**start, "where": "Prague", "wanted_roles": ["backend developer"], "my_fields": ["law", "no such field", "finance"]})
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert ui.js("optDialog.pickedFields.join('|')") == "finance|law" and ui.js("optDialog.changed()") is False   # an unknown name is dropped on load
    assert "Let the app decide" in source and "Pick it below if you want that." in source
    ui.js("close()", dialog)
    ui.wait(350)
    ui.bridge.saveOptions(start)
    assert ui.warnings == []


def test_the_preparation_can_be_edited_and_wrong_steps_are_explained(ui, monkeypatch):
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "Alex Novak\nPython, Docker.")
    prep = {"made": "2026-10-08", "summary": "They will ask about Python.", "pitch": "I am a junior developer.", "fit": ["Python", "Docker"],
            "questions": [{"audience": "hr", "kind": "about you", "question": "Tell me about yourself.", "why": "", "answer": "I am a junior developer.", "check": ""}],
            "ask_hr": ["What are the next steps?"], "ask_technical": [], "ask_them": [], "checks": []}
    ui.bridge._api._change("app", lambda jobs, j: j.update(interview_prep=dict(prep)), render=False)
    ui.js('prepEditDialog.show("app")')
    ui.wait(450)
    dialog, note = ui.find("prepEditDialog"), ui.find("peNote")
    assert dialog.property("opened") is True and ui.js("peModel.count") == 5
    keys = [ui.js(f"peModel.get({i}).key") for i in range(5)]
    assert keys == ["summary", "fit", "pitch", "questions.0.answer", "ask_hr"]
    # an empty answer is refused, in red, and the window stays open
    ui.js('peModel.setProperty(3, "text", ""); prepEditDialog.dirty = true; prepEditDialog.save()')
    assert "is empty" in note.property("text") and dialog.property("visible") is True
    # too long is said before anything is sent
    ui.js('peModel.setProperty(3, "text", "I am a junior developer."); peModel.setProperty(2, "text", "' + "x" * 3010 + '"); prepEditDialog.save()')
    assert "longer than 3000 characters" in note.property("text")
    # closing with changes asks once
    ui.js('peModel.setProperty(2, "text", "My own pitch."); prepEditDialog.dirty = true; prepEditDialog.tryClose()')
    ui.wait(200)
    assert dialog.property("visible") is True and "did not save" in note.property("text") and ui.js("prepEditDialog.closePolicy === 0") is True
    ui.js("prepEditDialog.save()")
    assert note.property("text") == "Saved." and ui.js("prepEditDialog.dirty") is False
    assert ui.bridge.interviewPrep("app")["pitch"] == "My own pitch."
    ui.js("prepEditDialog.tryClose()")
    ui.wait(450)
    assert dialog.property("visible") is False
    # "Make again" would replace the edit: asked first
    _open_job(ui, "app")
    assert ui.js("detailDialog.job.prep_edited") is True
    source = qml_source()
    assert "Making it again replaces the changes you made in the sheet." in source and 'objectName: "prepEdit"' in source
    ui.js("detailDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("app", lambda jobs, j: j.update(interview_prep={}), render=False)
    ui.js('prepEditDialog.show("app")')                                          # nothing to edit: said, no empty window
    ui.wait(250)
    assert dialog.property("visible") is False and "Prepare the interview first" in ui.js("ticker.text")
    assert ui.warnings == []


# ── every text field says when it is full or too long ───────────────────────
def test_text_fields_in_the_job_window_explain_their_limits(ui):
    _open_job(ui, "app")
    line = ui.find("notesLine")
    ui.js('cnContact.text = "' + "c" * 200 + '"; detailDialog.notesInfo = detailDialog.full(cnContact, "“Who you spoke to”"); detailDialog.notesBad = true')
    assert line.property("text") == "“Who you spoke to” takes up to 200 characters."
    ui.js('cnContact.text = "Jana"; cnNotes.text = "' + "n" * 2010 + '"')
    assert ui.find("notesOver").property("visible") is True and ui.find("notesOver").property("text") == "10 characters too long (the limit is 2000)"
    ui.js("detailDialog.saveNotes()")
    assert "10 characters too long" in line.property("text") and ui.js("detailDialog.notesBad") is True      # refused, in red
    from jobhelper import planner
    assert planner.company_notes("Beta")["updated"] == ""                                                    # and not saved cut
    ui.js('cnNotes.text = "Short note."; detailDialog.saveNotes()')
    assert line.property("text") == "Saved for Beta." and ui.js("detailDialog.notesBad") is False
    ui.js('evNote.text = "' + "e" * 200 + '"; detailDialog.eventErr = detailDialog.full(evNote, "The note")')
    assert ui.find("eventErr").property("text") == "The note takes up to 200 characters."
    ui.js('detailDialog.eventErr = ""; detailDialog.replyOpen = true; replyText.text = "' + "r" * 8005 + '"')
    assert ui.find("replyHint").property("text").startswith("5 characters too long: paste only the message itself")
    ui.js("detailDialog.fileReply()")
    assert "Paste only the message itself" in ui.js("detailDialog.replyErr") and ui.js("detailDialog.replyBusy") is False
    ui.js('replyText.text = ""; detailDialog.replyOpen = false; cnNotes.text = ""; cnContact.text = ""; detailDialog.saveNotes(); detailDialog.close()')
    ui.wait(350)
    assert ui.warnings == []


def test_form_answers_and_preparation_lists_explain_their_limits(ui, monkeypatch):
    ui.bridge.saveFormAnswers("app", [{"question": "Why us?", "answer": "Because.", "check": ""}])
    ui.js('formDialog.show("app")')
    ui.wait(450)
    ui.js('fmModel.setProperty(0, "answer", "' + "a" * 3004 + '"); formDialog.dirty = true; formDialog.save()')
    assert "is longer than 3000 characters" in ui.find("fmNote").property("text")
    assert ui.bridge.formAnswers("app")["items"][0]["answer"] == "Because."       # the long version was not saved
    ui.js("formDialog.dirty = false; formDialog.close()")
    ui.wait(350)
    assert ui.js("prepEditDialog.listProblem('one\\ntwo')") == ""
    many = "\\n".join(f"line {i}" for i in range(13))
    assert ui.js(f"prepEditDialog.listProblem('{many}')") == "13 lines; the most is 12. Remove some."
    assert ui.js("prepEditDialog.listProblem('" + "q" * 401 + "')") == "Line 1 is 401 characters long; the most is 400."
    ui.bridge.saveFormAnswers("app", [])
    source = qml_source()
    assert "“Right to work” takes up to" in source and "“You can start” takes up to" in source
    assert ui.warnings == []


# ── the older windows: every text field explains itself too ─────────────────
def test_number_fields_say_what_they_accept_instead_of_going_silent(ui):
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    spin = ui.find("scanSpin")                                                   # 1 to 365
    start = spin.property("value")
    ui.js('scanSpin.contentItem.text = "999"; scanSpin.contentItem.textEdited()')
    assert ui.js("scanSpin.note") == "Between 1 and 365" and ui.js("scanSpin.noteBad") is True
    assert spin.property("value") == start                                        # a wrong number is not taken
    ui.js("scanSpin.contentItem.editingFinished()")
    assert spin.property("value") == 365 and ui.js("scanSpin.note") == "Changed to 365, the highest allowed"
    assert ui.js("scanSpin.contentItem.text") == "365"
    ui.js('scanSpin.contentItem.text = "0"; scanSpin.contentItem.textEdited(); scanSpin.contentItem.editingFinished()')
    assert spin.property("value") == 1 and ui.js("scanSpin.note") == "Changed to 1, the lowest allowed"
    ui.js('scanSpin.contentItem.text = "45"; scanSpin.contentItem.textEdited()')
    assert spin.property("value") == 45 and ui.js("scanSpin.note") == ""           # a good number: taken at once, nothing said
    ui.js('scanSpin.contentItem.text = ""; scanSpin.contentItem.textEdited(); scanSpin.contentItem.editingFinished()')
    assert spin.property("value") == 45 and ui.js("scanSpin.note") == "Left at 45"
    ui.js(f"scanSpin.value = {start}; scanSpin.note = ''")
    ui.js("close()", dialog)
    ui.wait(350)
    assert ui.warnings == []


def test_career_site_name_is_checked(ui):
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert ui.js('optDialog.addCompany("' + "n" * 61 + '", "greenhouse", "acme")') is False
    assert ui.js("optDialog.coErr") == "The company name is 61 characters long; the most is 60."
    assert ui.js('optDialog.addCompany("Компания", "greenhouse", "acme")') is False and "Latin letters" in ui.js("optDialog.coErr")
    assert ui.js('optDialog.addCompany("Acme", "greenhouse", "")') is False and "token" in ui.js("optDialog.coErr")
    assert ui.find("coName").property("maximumLength") == 60
    ui.js("close()", dialog)
    ui.wait(350)
    assert ui.warnings == []


def test_letter_editor_explains_wrong_steps(ui, monkeypatch):
    from jobhelper import cover_letter
    paras = ["First paragraph of the letter.", "Second one.", "Third one.", "Fourth one.", "Fifth one."]
    monkeypatch.setattr(ui_api.Api, "letter_for_edit", lambda self, job_id: {"ok": True, "id": "lead", "company": "Acme", "title": "Dev",
                        "title_line": "Dev", "date_text": "", "paragraphs": list(paras), "min_words": cover_letter.MIN_WORDS, "max_words": cover_letter.MAX_WORDS})
    saved = []
    monkeypatch.setattr(ui_api.Api, "save_letter", lambda self, job_id, texts: saved.append(list(texts)) or {"ok": True, "warnings": []})
    ui.js('letterDialog.show("lead")')
    ui.wait(450)
    dialog, err = ui.find("letterDialog"), ui.find("letterErr")
    assert dialog.property("opened") is True
    ui.js('letterDialog.setText(1, "   "); letterDialog.setText(3, "")')
    ui.js("letterDialog.save()")
    assert err.property("text") == "Paragraph 2 and 4 are empty. A letter needs all 5 paragraphs." and saved == []
    ui.js("letterDialog.rewrite(1)")
    assert "Paragraph 2 is empty" in err.property("text") and ui.js("letterDialog.busyIndex") == -1      # nothing to rewrite: Claude is not asked
    ui.js('letterDialog.setText(1, "Second one, changed."); letterDialog.setText(3, "Fourth one."); letterDialog.tryClose()')
    ui.wait(200)
    assert dialog.property("visible") is True and "did not save" in err.property("text")                 # changes are not thrown away on one click
    ui.js("letterDialog.busyIndex = 2; letterDialog.tryClose()")
    assert "still rewriting paragraph 3" in err.property("text") and dialog.property("visible") is True
    ui.js("letterDialog.busyIndex = -1; letterDialog.save()")
    assert saved and saved[0][1] == "Second one, changed."
    assert ui.find("hintField").property("maximumLength") == 300
    ui.js('hintField.text = "' + "h" * 300 + '"; hintField.textEdited()')
    assert err.property("text") == "The note for a rewrite takes up to 300 characters."
    ui.js('hintField.text = ""; letterDialog.err = ""; letterDialog.tryClose()')
    ui.wait(450)
    assert dialog.property("visible") is False                                                           # saved: closes at once
    assert ui.warnings == []


# ── score again ─────────────────────────────────────────────────────────────
def test_score_again_from_the_job_window(ui, monkeypatch):
    import time

    from jobhelper import llm
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "Alex Novak\nPython.")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 35, "match_reason": "Another field."})
    _open_job(ui, "lead")
    assert ui.find("scoreAgain").property("text") == "Score again" and ui.js("detailDialog.job.can_rescore") is True
    ui.js("detailDialog.scoreAgain()")
    assert ui.js("detailDialog.scoreBusy") is True and ui.find("scoreAgain").property("enabled") is False
    for _ in range(200):
        time.sleep(0.02)
        ui.wait(10)
        if ui.js("detailDialog.scoreBusy") is False:
            break
    assert ui.find("scoreNote").property("text") == "Scored again: 80 before, 35 now."
    assert ui.js("detailDialog.job.score") == 35 and ui.js("detailDialog.job.score_before") == 80
    ui.js("detailDialog.close()")
    ui.wait(350)
    _open_job(ui, "lead")                                                       # later it still says what it was
    assert ui.find("scoreNote").property("text") == "It was 80 before it was scored again."
    ui.js("detailDialog.close()")
    ui.wait(350)
    _open_job(ui, "app")
    assert ui.js("detailDialog.job.can_rescore") is False                         # an application is not scored again
    ui.js("detailDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("lead", lambda jobs, j: j.update(match_score=80, match_reason="", score_before=None), render=False)
    assert ui.warnings == []


def test_score_again_says_why_it_failed_and_keeps_the_score(ui, monkeypatch):
    import time

    from jobhelper import llm

    def limit(*a, **k):
        raise llm.LimitReached("Claude's 7-day limit is used up (99%). It resets at 18:00.")
    monkeypatch.setattr(llm, "ask_json", limit)
    _open_job(ui, "lead")
    ui.js("detailDialog.scoreAgain()")
    for _ in range(200):
        time.sleep(0.02)
        ui.wait(10)
        if ui.js("detailDialog.scoreBusy") is False:
            break
    assert "Not scored again: Claude's 7-day limit is used up" in ui.find("scoreNote").property("text") and ui.js("detailDialog.scoreBad") is True
    assert ui.js("detailDialog.job.score") == 80
    ui.js("detailDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


def test_score_all_again_asks_before_spending_the_limit(ui, monkeypatch):
    started = []
    monkeypatch.setattr(qt_bridge.Bridge, "rescoreAll", lambda self: started.append(1) or {"ok": False, "msg": "A run is already in progress."})
    ui.js('openView("new")')
    ui.wait(450)
    button = ui.find("rescoreAll")
    assert button.property("visible") is True and button.property("text") == "Score all again"
    source = qml_source()
    assert "Only scores change; no letter is written or removed. Press again to start." in source
    ui.js("tableDialog.confirmRescore = true; tableDialog.rescoreJobs = 1")
    assert button.property("text") == "Yes, score 1 again"
    ui.js("tableDialog.close()")
    ui.wait(350)
    assert ui.js("tableDialog.confirmRescore") is False and started == []         # closing takes the confirmation back; nothing started
    ui.js('openView("app")')
    ui.wait(400)
    assert button.property("visible") is False                                    # only in New Jobs
    ui.js("tableDialog.close()")
    ui.wait(350)
    assert ui.warnings == []


# ── Options: changes are not thrown away unasked ────────────────────────────
def test_options_ask_once_before_discarding_changes(ui):
    dialog = ui.find("optDialog")
    start = ui.bridge.options()
    ui.bridge.saveOptions({**start, "where": "Prague"})
    ui.js("optsData = bridge.options()")
    ui.js("open()", dialog)
    ui.wait(450)
    assert ui.js("optDialog.changed()") is False
    ui.js("optDialog.tryClose()")                                               # nothing changed: closes at once
    ui.wait(450)
    assert dialog.property("visible") is False
    ui.js("open()", dialog)
    ui.wait(450)
    ui.js("thrSpin.value = thrSpin.value + 5")
    assert ui.js("optDialog.changed()") is True
    ui.js("optDialog.tryClose()")
    ui.wait(250)
    assert dialog.property("visible") is True and "did not save" in ui.js("optDialog.optErr")
    assert ui.find("optCancel").property("text") == "Discard changes"
    ui.js("thrSpin.value = thrSpin.value - 5")                                  # put back by hand: nothing to lose any more
    assert ui.js("optDialog.changed()") is False
    ui.js('skipTags.add("contractor"); optDialog.confirmClose = false; optDialog.tryClose()')
    ui.wait(200)
    assert dialog.property("visible") is True                                     # a tag counts as a change too
    ui.js("optDialog.tryClose()")                                               # the second time it goes
    ui.wait(450)
    assert dialog.property("visible") is False and "contractor" not in ui.bridge.options()["skip_words"]
    assert ui.js("optDialog.closePolicy === 0") is True                           # Esc cannot bypass the question
    ui.bridge.saveOptions(start)
    ui.js("optsData = bridge.options()")
    assert ui.warnings == []


def _wait_scored(ui):
    import time
    for _ in range(300):
        time.sleep(0.02)
        ui.wait(10)
        if ui.js("detailDialog.scoreBusy") is False:
            return
    raise AssertionError("the score never came back")


# ── what a score rests on, pasted text, documents left from a higher score ──
def test_a_title_only_score_is_marked_and_the_posting_can_be_pasted(ui, monkeypatch):
    from jobhelper import llm
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "Alex Novak\nPython.")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 65, "match_reason": "Fits."})
    start = store.find(store.load_jobs(), "lead")
    ui.bridge._api._change("lead", lambda jobs, j: j.update(description="", match_score=40), render=False)
    ui.js('openView("new")')
    ui.wait(450)
    assert "scored from the title only" in ui.js("listView.model[0].secondary")
    ui.js("tableDialog.close()")
    ui.wait(350)
    _open_job(ui, "lead")
    assert ui.find("basisRow").property("visible") is True and ui.js("detailDialog.job.basis") == "title"
    ui.js('detailDialog.pasteOpen = true; pastedText.text = "too short"; detailDialog.savePasted()')
    assert ui.find("pasteHint").property("text") == "That is only 9 characters. Paste the whole posting (at least 200)."
    ui.js('pastedText.text = "' + "x" * 20010 + '"; detailDialog.pasteErr = ""')
    assert ui.find("pasteHint").property("text") == "10 characters too long (the limit is 20000)"
    ui.js("detailDialog.savePasted()")
    assert "the most is 20000" in ui.find("pasteHint").property("text") and ui.js("detailDialog.pasteOpen") is True      # refused, stays open
    ui.js('pastedText.text = "' + "We build internal tools in Python and test them well. " * 10 + '"; detailDialog.savePasted()')
    assert ui.js("detailDialog.pasteOpen") is False and ui.js("detailDialog.job.basis") == ""
    assert ui.find("basisRow").property("visible") is False
    assert ui.js("detailDialog.scoreBusy") is True                                   # the new text is scored at once, unasked
    assert ui.find("scoreNote").property("text") == "The posting's text is saved. Asking Claude…"
    _wait_scored(ui)
    assert ui.find("scoreNote").property("text") == "The posting's text is saved. Scored again: 40 before, 65 now."
    assert ui.js("detailDialog.job.score") == 65 and ui.js("detailDialog.scoreLead") == ""
    ui.js("detailDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("lead", lambda jobs, j: j.update(description=start.get("description", ""), match_score=80, description_by_hand=False), render=False)
    assert ui.warnings == []


def test_documents_from_a_higher_score_are_marked_and_moved_only_after_asking(ui, monkeypatch):
    for folder, name in ((config.TAILORED_CV_DIR, "cv_lead.docx"), (config.LETTERS_DIR, "L_lead.docx")):
        (folder / name).write_bytes(b"x")
    monkeypatch.setattr(ui_api.Api, "_threshold", lambda self: 50)
    ui.bridge._api._change("lead", lambda jobs, j: j.update(tailored_cv_file="cv_lead.docx", cover_letter_file="L_lead.docx",
                                                             status="letter_ready", match_score=30), render=False)
    ui.js('openView("new")')
    ui.wait(450)
    assert "documents from a higher score" in ui.js("listView.model[0].secondary")
    ui.js("tableDialog.close()")
    ui.wait(350)
    _open_job(ui, "lead")
    assert ui.find("staleRow").property("visible") is True and "below your limit of 50" in ui.find("staleText").property("text")
    ui.js("detailDialog.shelve()")
    assert ui.find("shelveDocs").property("text") == "Yes, move them" and (config.LETTERS_DIR / "L_lead.docx").exists()      # asked first
    ui.js("detailDialog.shelve()")
    assert ui.find("staleText").property("text").endswith("files moved to the backup.") and not (config.LETTERS_DIR / "L_lead.docx").exists()
    assert ui.js("detailDialog.job.docs_stale") is False and ui.find("shelveDocs").property("visible") is False
    ui.js("detailDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("lead", lambda jobs, j: j.update(match_score=80, status="letter_ready"), render=False)
    assert ui.warnings == []


def test_read_it_again_button_reports_both_outcomes(ui, monkeypatch):
    from jobhelper import agent2_search
    start = store.find(store.load_jobs(), "lead")
    ui.bridge._api._change("lead", lambda jobs, j: j.update(description="", match_score=40, url="https://example.com/job"), render=False)
    _open_job(ui, "lead")
    assert ui.find("rereadPosting").property("visible") is True
    got = ui.js("bridge.rereadPosting(detailDialog.job.id)")
    assert got["ok"] is False and "paste its text instead" in got["msg"]
    ui.js("detailDialog.readAgain()")                                                # the button: nothing new to read
    assert "paste its text instead" in ui.find("scoreNote").property("text") and ui.js("detailDialog.scoreBad") is True
    assert ui.js("detailDialog.scoreBusy") is False
    text = "We build internal tools in Python and test them well. " * 10
    monkeypatch.setattr(agent2_search, "refetch_description", lambda job: text)
    ui.js("win.appRunning = true; detailDialog.readAgain()")                         # read, but a search is running: no scoring now
    assert ui.find("scoreNote").property("text") == f"Read {len(text)} characters of the posting. A search or scan is running: press Score again when it has finished."
    assert ui.js("detailDialog.scoreBusy") is False and ui.js("detailDialog.job.basis") == "" and ui.find("basisRow").property("visible") is False
    ui.js("win.appRunning = false")

    from jobhelper import llm
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "Alex Novak\nPython.")
    ui.bridge._api._change("lead", lambda jobs, j: j.update(description="", match_score=40), render=False)
    ui.js("detailDialog.refresh()")

    def limit(*a, **k):
        raise llm.LimitReached("Claude's 7-day limit is used up.")
    monkeypatch.setattr(llm, "ask_json", limit)
    ui.js("detailDialog.readAgain()")
    assert ui.find("rereadPosting").property("enabled") is False
    _wait_scored(ui)
    note = ui.find("scoreNote").property("text")                                     # the text is kept, and the reason it was not scored is said
    assert note.startswith(f"Read {len(text)} characters of the posting. Not scored again:") and ui.js("detailDialog.scoreBad") is True
    assert store.find(store.load_jobs(), "lead")["description"] == text and ui.js("detailDialog.job.score") == 40

    ui.bridge._api._change("lead", lambda jobs, j: j.update(description="", match_score=None), render=False)   # a job with no score yet
    ui.js("detailDialog.refresh(); detailDialog.readAgain()")
    assert ui.js("detailDialog.scoreBusy") is False and ui.js("ticker.text") == f"Read {len(text)} characters of the posting. The next search will score it."
    ui.js("detailDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("lead", lambda jobs, j: j.update(description=start.get("description", ""), match_score=80, url=""), render=False)
    assert ui.warnings == []


# ── New Jobs: all documents below the limit at once, and the score a job had before ──
def test_documents_below_the_limit_are_moved_together_only_after_asking(ui, monkeypatch):
    for folder, name in ((config.TAILORED_CV_DIR, "cv_lead.docx"), (config.LETTERS_DIR, "L_lead.docx")):
        (folder / name).write_bytes(b"x")
    monkeypatch.setattr(ui_api.Api, "_threshold", lambda self: 50)
    ui.bridge._api._change("lead", lambda jobs, j: j.update(tailored_cv_file="cv_lead.docx", cover_letter_file="L_lead.docx",
                                                             status="letter_ready", match_score=30), render=False)
    ui.js('openView("new")')
    ui.wait(450)
    bar, button, text = ui.find("staleBar"), ui.find("shelveAll"), ui.find("staleBarText")
    assert bar.property("visible") is True and button.property("text") == "Move them to backup"
    assert text.property("text") == "1 job has documents from a score that is now below your limit."
    ui.js("tableDialog.shelveAll()")                                                # first press only asks, and names the jobs
    assert button.property("text") == "Yes, move documents of 1 job" and "A letter of your own is never moved." in text.property("text")
    title = store.find(store.load_jobs(), "lead")["title"]
    assert ui.find("staleNames").property("visible") is True and title in ui.find("staleNames").property("text")
    assert (config.LETTERS_DIR / "L_lead.docx").exists()
    ui.js('tableDialog.confirmStale = false')                                       # Cancel
    assert button.property("text") == "Move them to backup" and (config.LETTERS_DIR / "L_lead.docx").exists()
    ui.js("tableDialog.close()")
    ui.wait(350)
    ui.js('openView("new")')
    ui.wait(450)
    assert ui.js("tableDialog.confirmStale") is False                               # a closed window forgets the question

    ui.js("tableDialog.shelveAll()")
    ui.js("win.appRunning = true; tableDialog.shelveAll()")                         # a search started meanwhile
    assert "A search or scan is running" in ui.find("staleNote").property("text") and ui.js("tableDialog.staleBad") is True
    assert (config.LETTERS_DIR / "L_lead.docx").exists()
    ui.js("win.appRunning = false")

    ui.bridge._running = True                                                       # the bridge refuses too, whatever the window thinks
    try:
        assert "A search or scan is running" in ui.bridge.shelveAllDocs(1)["msg"] and (config.LETTERS_DIR / "L_lead.docx").exists()
    finally:
        ui.bridge._running = False

    ui.js("tableDialog.staleRows = [{id: 'x', title: 'T', company: 'C', score: 1}, {id: 'y', title: 'T', company: 'C', score: 1}]; tableDialog.confirmStale = true")
    ui.js("tableDialog.shelveAll()")                                                # the list is not what was asked about
    assert "The list changed: it is now 1 job" in ui.find("staleNote").property("text") and (config.LETTERS_DIR / "L_lead.docx").exists()
    assert ui.js("tableDialog.confirmStale") is True and ui.js("tableDialog.staleRows.length") == 1
    ui.js("tableDialog.shelveAll()")
    assert not (config.LETTERS_DIR / "L_lead.docx").exists() and not (config.TAILORED_CV_DIR / "cv_lead.docx").exists()
    assert "Documents of 1 job moved to the backup (2 files)." in ui.js("ticker.text")
    assert "documents from a higher score" not in ui.js("listView.model[0].secondary")
    assert ui.find("staleBarText").property("visible") is False                     # nothing left to move …

    undo = ui.find("undoRow")                                                       # … and what was moved can be put back
    assert bar.property("visible") is True and undo.property("visible") is True
    assert ui.find("undoText").property("text").startswith("Documents of 1 job were moved to the backup on 20")
    ui.js("win.appRunning = true; tableDialog.putBack()")
    assert "A search or scan is running. Put the documents back" in ui.find("staleNote").property("text") and not (config.LETTERS_DIR / "L_lead.docx").exists()
    ui.js("win.appRunning = false")
    ui.bridge._running = True
    try:
        assert "A search or scan is running" in ui.bridge.unshelveLast("")["msg"] and "A search or scan is running" in ui.bridge.unshelveDocs("lead")["msg"]
    finally:
        ui.bridge._running = False
    ui.js("tableDialog.lastShelved = {batch: 'gone', when: '2026-01-01T10:00:00', jobs: [{id: 'lead'}]}; tableDialog.putBack()")
    assert "The list changed. Look at it again" in ui.find("staleNote").property("text") and ui.js("tableDialog.staleBad") is True
    assert ui.js("tableDialog.lastShelved.batch") != "gone" and not (config.LETTERS_DIR / "L_lead.docx").exists()      # the real batch is shown again
    ui.js("tableDialog.putBack()")
    assert (config.LETTERS_DIR / "L_lead.docx").exists() and (config.TAILORED_CV_DIR / "cv_lead.docx").exists()
    assert "Documents of 1 job are back in place (2 files)." in ui.js("ticker.text")
    assert undo.property("visible") is False and ui.find("staleBarText").property("visible") is True                    # below the limit again, so offered again
    assert "documents from a higher score" in ui.js("listView.model[0].secondary")
    ui.js("tableDialog.close()")
    ui.wait(350)

    _open_job(ui, "lead")                                                           # the same for one job, in its window
    ui.js("detailDialog.shelve(); detailDialog.shelve()")
    assert not (config.LETTERS_DIR / "L_lead.docx").exists() and ui.find("unshelveDocs").property("visible") is True
    ui.js("detailDialog.close()")
    ui.wait(350)
    _open_job(ui, "lead")
    assert ui.find("staleRow").property("visible") is True and ui.find("staleText").property("text").startswith("The documents the app wrote for this job were moved to the backup on 20")
    ui.js("win.appRunning = true; detailDialog.unshelve()")
    assert "A search or scan is running" in ui.find("staleText").property("text") and ui.js("detailDialog.shelveBad") is True
    ui.js("win.appRunning = false")
    (config.LETTERS_DIR / "L_lead.docx").write_bytes(b"in the way")
    ui.js("detailDialog.unshelve()")
    assert "A file named L_lead.docx is already in its folder" in ui.find("staleText").property("text") and ui.js("detailDialog.shelveBad") is True
    (config.LETTERS_DIR / "L_lead.docx").unlink()
    ui.js("detailDialog.unshelve()")
    assert ui.find("staleText").property("text") == "2 files are back in place." and ui.js("detailDialog.shelveBad") is False
    assert (config.LETTERS_DIR / "L_lead.docx").read_bytes() == b"x" and ui.find("unshelveDocs").property("visible") is False
    assert ui.find("shelveDocs").property("visible") is True
    ui.js("detailDialog.close()")
    ui.wait(350)

    ui.js('openView("app")')
    ui.wait(400)
    assert bar.property("visible") is False                                         # only in New Jobs
    ui.js("tableDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("lead", lambda jobs, j: j.update(match_score=80, status="letter_ready"), render=False)
    assert ui.warnings == []


def test_the_list_shows_the_score_before(ui):
    ui.bridge._api._change("lead", lambda jobs, j: j.update(score_before=55, match_score=30), render=False)
    ui.js('openView("new")')
    ui.wait(450)
    row = ui.js("(function(){ var m = listView.model; for (var i = 0; i < m.length; i++) if (m[i].id === 'lead') return m[i]; return {}; })()")
    assert row["was"] == "was 55" and row["value"] == "30" and ui.js("tableDialog.anyWas") is True
    assert not row["secondary"].startswith(" ") and "·   ·" not in row["secondary"]      # no separator before the first note
    ui.js("tableDialog.close()")
    ui.wait(350)
    ui.bridge._api._change("lead", lambda jobs, j: j.update(score_before=80, match_score=80), render=False)
    ui.js('openView("new")')
    ui.wait(450)
    assert ui.js("tableDialog.anyWas") is False and ui.js("listView.model.map(function (r) { return r.was || ''; }).join('')") == ""
    ui.js("tableDialog.close()")
    ui.wait(350)
    assert "the score it had before it was scored again" in qml_source()
    assert ui.warnings == []


# ── Options: old moved documents are removed only after asking, with the count ──
def test_old_moved_documents_are_removed_from_options_after_asking(ui):
    from datetime import datetime, timedelta

    from jobhelper import housekeeping, vault
    folder = vault.backups_dir() / housekeeping.SHELF
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        old.unlink()

    def copy(name, days):
        path = folder / f"{name}.{(datetime.now() - timedelta(days=days, minutes=5)).strftime('%Y%m%d_%H%M%S')}.docx.enc"
        path.write_bytes(b"x" * 4096)
        return path
    fresh, old_one, old_two = copy("fresh", 1), copy("one", 40), copy("two", 90)
    dialog = ui.find("optDialog")
    ui.js("open()", dialog)
    ui.wait(450)
    note, button = ui.find("shelfNote"), ui.find("tidyShelf")
    assert note.property("text") == "3 moved documents are in the backup (12 KB). 2 are older than 30 days (8 KB)."
    assert button.property("text") == "Remove" and button.property("enabled") is True
    ui.js("shelfSpin.value = 200")                                                    # another age: counted again at once
    assert note.property("text").endswith("None is older than 200 days.") and button.property("enabled") is False
    ui.js("optDialog.tidyShelf()")
    assert ui.js("optDialog.confirmTidy") is False and old_two.exists()               # nothing to ask about
    ui.js("shelfSpin.value = 60; optDialog.tidyShelf()")                              # first press only asks
    assert button.property("text") == "Yes, move 1 to the Trash" and "The app can then no longer put them back" in note.property("text") and old_two.exists()
    assert ui.find("tidyCancel").property("visible") is True
    ui.js("shelfSpin.value = 30")                                                     # the age changed: the question is taken back
    assert ui.js("optDialog.confirmTidy") is False and button.property("text") == "Remove"
    ui.js("optDialog.tidyShelf(); win.appRunning = true; optDialog.tidyShelf()")      # a search started meanwhile
    assert "A search or scan is running" in note.property("text") and ui.js("optDialog.shelfBad") is True and old_one.exists()
    ui.js("win.appRunning = false")
    ui.bridge._running = True
    try:
        assert "A search or scan is running" in ui.bridge.tidyShelf(30, 2)["msg"] and old_one.exists()
    finally:
        ui.bridge._running = False
    ui.js("optDialog.tidyShelf()")
    copy("three", 50)                                                                 # the folder changed after the question
    ui.js("optDialog.tidyShelf()")
    assert "The number changed: it is now 3" in note.property("text") and button.property("text") == "Yes, move 3 to the Trash" and old_one.exists()
    ui.js("optDialog.tidyShelf()")
    assert note.property("text") == "Moved 3 old copies to the Trash (12 KB)." and ui.js("optDialog.shelfBad") is False
    assert (housekeeping.trash_dir(old_one) / old_one.name).exists()
    assert not old_one.exists() and not old_two.exists() and fresh.exists() and button.property("enabled") is False
    assert "wrapMode: Text.WordWrap" in qml_source().split('objectName: "shelfNote"')[1][:200]
    ui.js("close()", dialog)
    ui.wait(350)
    ui.js("open()", dialog)
    ui.wait(450)
    assert note.property("text") == "1 moved document is in the backup (4 KB). None is older than 30 days."
    ui.js("close()", dialog)
    ui.wait(350)
    fresh.unlink()
    assert ui.warnings == []


def test_jobs_that_could_not_be_put_back_are_listed_one_by_one(ui, monkeypatch):
    monkeypatch.setattr(ui_api.Api, "_threshold", lambda self: 50)
    jobs = store.load_jobs()
    for name in ("one", "two"):
        (config.LETTERS_DIR / f"L_{name}.docx").write_bytes(b"x")
        jobs.append(store.new_job(id=f"pb_{name}", title=f"Tester {name}", company="Acme <b>Labs</b>", match_score=20, status="letter_ready",
                                  cover_letter_file=f"L_{name}.docx", description="x" * 900))
    store.save_jobs(jobs)
    try:
        ui.js('openView("new")')
        ui.wait(450)
        ui.js("tableDialog.shelveAll(); tableDialog.shelveAll()")
        assert not (config.LETTERS_DIR / "L_one.docx").exists() and ui.js("tableDialog.staleFailed.length") == 0
        (config.LETTERS_DIR / "L_one.docx").write_bytes(b"in the way")
        ui.js("tableDialog.putBack()")
        failed = ui.find("staleFailed")
        assert ui.find("staleNote").property("text") == "Documents of 1 job are back in place (1 file). Not put back:" and ui.js("tableDialog.staleBad") is True
        assert failed.property("visible") is True
        assert failed.property("text") == "Tester one  ·  Acme <b>Labs</b>: A file named L_one.docx is already in its folder, so nothing was put back."
        assert (config.LETTERS_DIR / "L_two.docx").exists() and ui.find("undoRow").property("visible") is True          # the one left is still offered
        ui.js("tableDialog.putBack()")                                                    # nothing could be done this time: said per job too
        assert ui.find("staleNote").property("text") == "Couldn't put the documents back. The reason for each job:"
        assert "Tester one" in failed.property("text") and failed.property("text").count("\n") == 0
        (config.LETTERS_DIR / "L_one.docx").unlink()
        ui.js("tableDialog.putBack()")
        assert ui.js("tableDialog.staleFailed.length") == 0 and failed.property("visible") is False and (config.LETTERS_DIR / "L_one.docx").read_bytes() == b"x"
        source = qml_source().split('objectName: "staleFailed"')[1][:260]
        assert "textFormat: Text.PlainText" in qml_source().split('objectName: "staleFailed"')[0][-120:] + source and "wrapMode: Text.WordWrap" in source
        ui.js("tableDialog.close()")
        ui.wait(350)
        assert ui.js("tableDialog.staleFailed.length") == 0
    finally:
        store.save_jobs([j for j in store.load_jobs() if not j["id"].startswith("pb_")])
        for name in ("one", "two"):
            (config.LETTERS_DIR / f"L_{name}.docx").unlink(missing_ok=True)
    assert ui.warnings == []


# ── light theme: small text must read against the light surfaces ────────────
def _contrast(a, b):
    def lum(h):
        r, g, b_ = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4   # noqa: E731
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b_)
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_light_theme_text_colours_read_on_light_surfaces():
    import re
    main = (ROOT / "ui_qt" / "Main.qml").read_text(encoding="utf-8")
    light = {name: value for name, value in re.findall(r'property color (\w+): win\.dark \? "#[0-9a-fA-F]{6}" : "(#[0-9a-fA-F]{6})"', main)}
    assert {"winbg", "surface", "surface2", "ink", "soft", "faint", "accent", "good", "warn", "crit"} <= set(light)
    for text in ("ink", "soft", "faint", "good", "warn", "crit"):
        for ground in ("winbg", "surface", "surface2"):
            assert _contrast(light[text], light[ground]) >= 4.5, (text, ground, round(_contrast(light[text], light[ground]), 2))
    assert _contrast(light["accentInk"], light["accent"]) >= 4.5 and _contrast(light["accentInk"], light["good"]) >= 4.5   # the label on a main button, the tick
    assert _contrast(light["warn"], light["warnbg"]) >= 4.5 and _contrast(light["good"], light["goodbg"]) >= 4.5 and _contrast(light["crit"], light["critbg"]) >= 4.5


def test_dark_theme_text_colours_read_on_dark_surfaces():
    import re
    main = (ROOT / "ui_qt" / "Main.qml").read_text(encoding="utf-8")
    dark = {name: value for name, value in re.findall(r'property color (\w+): win\.dark \? "(#[0-9a-fA-F]{6})" : "#[0-9a-fA-F]{6}"', main)}
    assert {"winbg", "surface", "surface2", "ink", "soft", "faint", "accent", "accentInk", "good", "warn", "crit"} <= set(dark)
    for text in ("ink", "soft", "faint", "good", "warn", "crit", "accent"):
        for ground in ("winbg", "surface", "surface2"):
            assert _contrast(dark[text], dark[ground]) >= 4.5, (text, ground, round(_contrast(dark[text], dark[ground]), 2))
    assert _contrast(dark["accentInk"], dark["accent"]) >= 4.5 and _contrast(dark["accentInk"], dark["good"]) >= 4.5   # the label on a main button, the tick
    assert _contrast(dark["warn"], dark["warnbg"]) >= 4.5 and _contrast(dark["good"], dark["goodbg"]) >= 4.5 and _contrast(dark["crit"], dark["critbg"]) >= 4.5


def test_the_resume_button_s_white_label_reads_on_its_blue(ui):
    assert _contrast("#ffffff", ui.js('"" + win.resumeBlue')) >= 4.5 and "win.resumeBlue" in qml_source()


def test_no_label_on_the_accent_is_fixed_white():
    """A main button, a picked chip and the tick take their label colour from the theme: white suits only the light theme."""
    for name in ("SmallButton", "PillButton", "TableDialog", "HelpDialog", "OptionsDialog", "DetailDialog", "FormAnswersDialog", "PrepDialog",
                 "PrepEditDialog", "LetterDialog", "CompareDialog"):
        text = (ROOT / "ui_qt" / f"{name}.qml").read_text(encoding="utf-8")
        assert '"#ffffff"' not in text and '"white"' not in text, name
    assert "theme.accentInk" in (ROOT / "ui_qt" / "SmallButton.qml").read_text(encoding="utf-8")


def test_the_label_on_a_main_button_follows_the_theme(ui):
    """Read from the running window: a colour that exists in the file but does not reach the label would pass the other tests."""
    start = ui.js("win.dark")
    try:
        ui.js("win.dark = true")
        assert ui.js('"" + theme.accentInk') == "#1b1305" and ui.js('"" + theme.accent') == "#f0a84a"
        ui.js('openView("new")')
        ui.wait(450)
        ui.js("tableDialog.confirmRescore = true; tableDialog.rescoreJobs = 1")              # a main-style button
        button = ui.find("rescoreAll")
        assert ui.js('"" + contentItem.color', button) == "#1b1305"
        ui.js("win.dark = false")
        ui.wait(50)
        assert ui.js('"" + theme.accentInk') == "#ffffff" and ui.js('"" + contentItem.color', button) == "#ffffff"
        ui.js("tableDialog.close()")
        ui.wait(350)
    finally:
        ui.js("win.dark = %s" % ("true" if start else "false"))
    assert ui.warnings == []


# ── text wraps, it is never cut off ─────────────────────────────────────────
def test_no_text_in_the_window_is_cut_with_an_ellipsis():
    for path in sorted((ROOT / "ui_qt").glob("*.qml")):
        text = path.read_text(encoding="utf-8")
        assert "elide:" not in text and "maximumLineCount" not in text, f"{path.name} cuts a text short; let it wrap"


def test_a_long_title_makes_its_row_taller_instead_of_being_cut(ui):
    long_title = "Senior Principal Associate Vice Coordinator of Cross-Functional Platform Reliability and Developer Experience Enablement (Remote, EMEA)"
    start = store.find(store.load_jobs(), "lead")["title"]
    ui.bridge._api._change("lead", lambda jobs, j: j.update(title=long_title), render=False)
    try:
        ui.js('openView("new")')
        ui.wait(450)
        heights = ui.js("(function(){ var out = []; for (var i = 0; i < listView.count; i++) { var it = listView.itemAtIndex(i); if (it) out.push(Math.round(it.height)); } return out.join(','); })()")
        heights = [int(h) for h in heights.split(",") if h]
        assert max(heights) > 54 and min(heights) >= 54                                 # the long one grew, the others kept their size
        ui.js("tableDialog.close()")
        ui.wait(350)
        _open_job(ui, "lead")
        title = ui.find("detailTitle")
        assert title.property("truncated") is False and title.property("lineCount") >= 2 and title.property("text") == long_title
        ui.js("detailDialog.close()")
        ui.wait(350)
        ui.js('ticker.text = "' + "A long message in the status line that has to be read to its last word. " * 4 + '"')
        ui.wait(100)
        assert ui.js("statusBar.height") > 46 and ui.js("ticker.truncated") is False     # the bar grows with its message
        ui.js('ticker.text = ""')
    finally:
        ui.bridge._api._change("lead", lambda jobs, j: j.update(title=start), render=False)
    assert ui.warnings == []


def test_help_describes_what_was_added_since_it_was_written():
    text = (ROOT / "ui_qt" / "HelpDialog.qml").read_text(encoding="utf-8")
    for words in ("Move documents to backup", "Put them back", "Trash", "Kinds of role you want", "Read it again", "was 55",
                  "no longer accepts applications", "app_trouble.log", "docs/GUIDE.md"):
        assert words in text, words


# ── the illustrated guide ───────────────────────────────────────────────────
def test_the_guide_s_pictures_exist_and_come_from_the_picture_script():
    import re
    guide = (ROOT / "docs" / "GUIDE.md").read_text(encoding="utf-8")
    used = re.findall(r"\]\(img/([^)]+)\)", guide)
    assert len(used) >= 20 and len(set(used)) == len(used)
    script = (ROOT / "tests" / "guide_shots.py").read_text(encoding="utf-8")
    for name in used:
        assert (ROOT / "docs" / "img" / name).is_file(), name
        assert f'shot("{name[:-4]}")' in script, f"{name} is not taken by tests/guide_shots.py"
    assert "tests/guide_shots.py" in guide and "invented" in guide           # says where the pictures come from
    for link in re.findall(r"\]\((\.\./[^)#]+)\)", guide):
        assert (ROOT / "docs" / link).resolve().is_file(), link
    for section in re.findall(r"\]\(#([^)]+)\)", guide):                      # every entry of the contents leads somewhere
        heading = next((h for h in re.findall(r"^## (.+)$", guide, re.M)
                        if re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") == section), None)
        assert heading, section


def test_a_search_role_outside_software_can_be_added(ui):
    """The words the app knew for roles were all from software jobs: "registered nurse" was refused as not a role."""
    dialog = ui.find("optDialog")
    ui.js("open()", dialog)
    ui.wait(450)
    before = ui.js("rolesModel.count")
    assert ui.js('optDialog.addRole("registered nurse")') is True and ui.js("optDialog.roleErr") == ""       # a profession the app knows
    assert ui.js('optDialog.addRole("junior accountant")') is True
    assert ui.js('optDialog.addRole("beekeeper")') is False                                                   # unknown: asked once …
    assert "is not a role the app knows" in ui.js("optDialog.roleErr") and "press Add again" in ui.js("optDialog.roleErr")
    assert ui.js("rolesModel.count") == before + 2
    assert ui.js('optDialog.addRole("beekeeper")') is True and ui.js("optDialog.roleErr") == ""               # … then added
    assert ui.js('optDialog.addRole("asdfgh")') is False and ui.js('optDialog.addRole("zzzzqq")') is False     # a different word is asked about afresh
    assert ui.js("rolesModel.count") == before + 3
    assert ui.js('optDialog.addRole("план")') is False and "Latin letters" in ui.js("optDialog.roleErr")       # the other checks still hold
    assert ui.js('optDialog.addRole("beekeeper")') is False and "already in the list" in ui.js("optDialog.roleErr")
    assert ui.bridge.knownRole("staff nurse") is True and ui.bridge.knownRole("beekeeper") is False and ui.bridge.knownRole("") is False
    ui.js("optDialog.pendingRole = ''; optDialog.roleErr = ''; optDialog.load()")
    ui.js("close()", dialog)
    ui.wait(350)
    assert ui.warnings == []


def test_the_job_window_asks_before_closing_with_unsaved_text(ui):
    _open_job(ui, "app")
    dialog = ui.find("detailDialog")
    assert ui.js("detailDialog.pending.length") == 0 and ui.js("detailDialog.closePolicy") != 0           # nothing typed: Esc closes
    ui.js('cnNotes.text = "They asked about pytest."')
    assert ui.js("detailDialog.pending.join('|')") == "the notes about the company" and ui.js("detailDialog.closePolicy") == 0   # Esc alone no longer closes
    ui.js("detailDialog.tryClose()")                                                                    # the ✕ (and Esc, through the shortcut)
    note = ui.find("closeNote")
    assert dialog.property("opened") is True and note.property("visible") is True
    assert note.property("text") == "Not saved yet: the notes about the company. Save it, or close once more to discard it."
    ui.js("detailDialog.saveNotes()")                                                                   # saved: nothing pending any more
    assert ui.js("detailDialog.pending.length") == 0
    ui.js('evNote.text = "bring the laptop"; replyText.text = "Dear Alex, thank you for your time today."')
    assert ui.js("detailDialog.pending.join('|')") == "the pasted reply|the date to remember"
    ui.js("detailDialog.confirmClose = false; detailDialog.tryClose()")
    assert "the pasted reply, the date to remember" in note.property("text") and dialog.property("opened") is True
    ui.js("detailDialog.tryClose()")                                                                    # the second time closes and discards
    ui.wait(350)
    assert dialog.property("opened") is False
    _open_job(ui, "app")                                                                                # opened again: clean
    assert ui.js("detailDialog.pending.length") == 0 and ui.js("detailDialog.closeNote") == "" and ui.js("replyText.text") == ""
    ui.js("detailDialog.tryClose()")
    ui.wait(350)
    assert dialog.property("opened") is False
    ui.bridge._api.save_company_notes("Beta", {"contact": "", "salary": "", "asked": "", "notes": ""})
    _open_job(ui, "lead")                                                                               # a new job has none of those fields filled
    assert ui.js("detailDialog.pending.length") == 0
    ui.js("detailDialog.close()")
    ui.wait(350)
    assert ui.warnings == []
