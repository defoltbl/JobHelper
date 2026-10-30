"""The window, loaded offscreen: the welcome card, runs, the job window, Options cards and help.

Its tests share one window and follow on from each other, so they run on one worker in this order (see
tests/window_harness.py). The other window test files run beside it, each with a window of its own."""

import re

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.xdist_group("test_window_main")


from PySide6.QtCore import QObject, Qt  # noqa: E402

from jobhelper import api_core, config, qt_bridge, ui_api  # noqa: E402
from tests.conftest import ROOT  # noqa: E402
from tests.window_harness import (READY, _begin_search, _border_with_focus, _card_values, _email_answer, _open, _titles, _until_closed, _until_open, _until_shown, _until_true, qml_source)  # noqa: E402


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
    _until_true(ui, lambda: ui.find("welcome").property("visible") is False)
    assert welcome.property("visible") is False        # fully animated away
    ui.js("welcome.openCard()")
    assert welcome.property("shown") is True and welcome.property("first") is False
    assert ui.find("welcomeStart").property("text") == "Done"
    ui.js("welcome.finish()")
    _until_true(ui, lambda: ui.find("welcome").property("visible") is False)


def test_pdf_row_says_how_to_get_pdf_copies_and_is_never_required(ui):
    welcome, row = ui.find("welcome"), ui.find("pdfRow")
    ui.win.setProperty("connData", {**READY, "pdf": False})
    assert "libreoffice.org" in row.property("sub") and "Word files are made as usual" in row.property("sub")
    assert "select Recheck" in row.property("sub") and welcome.property("ready") is True              # optional
    ui.win.setProperty("connData", {**READY, "pdf": True})
    assert row.property("sub").startswith("Made with LibreOffice")
    ui.win.setProperty("connData", dict(READY))
    assert ui.warnings == []


def test_the_set_up_line_names_what_is_missing(ui):
    cases = [({"cv": ""}, "Needed before the line can run: your master CV."),
             ({"claude": False}, "Needed before the line can run: the Claude sign-in."),
             ({"claude": False, "cv": ""}, "Needed before the line can run: the Claude sign-in and your master CV."),
             ({"paid_api": True}, "A paid Claude key is set on this Mac. Remove it, then start the app again.")]
    for missing, said in cases:
        ui.win.setProperty("connData", {**READY, **missing})
        assert ui.js("welcome.neededText()") == said, missing
    ui.win.setProperty("connData", dict(READY))
    assert ui.js("welcome.neededText()") == ""


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


def test_the_recovery_key_is_shown_and_restored_in_the_account_card(ui, monkeypatch):
    """Both needed a command in the terminal before; someone who only uses the window could not do either."""
    from jobhelper import vault
    monkeypatch.setattr(vault, "state", lambda: "ok")
    monkeypatch.setattr(vault, "recovery_key", lambda: "k" * 43 + "=")
    copied = []
    monkeypatch.setattr(qt_bridge.Bridge, "copyText", qt_bridge.Slot(str, result=bool)(lambda self, text: copied.append(text) or True))
    welcome = ui.find("welcome")
    ui.js("welcome.openCard()")
    ui.win.setProperty("connData", {**READY, "vault": "ok", "changed_files": []})
    ui.wait(80)
    assert welcome.property("keyText") == "" and ui.find("keyShow").property("text") == "Recovery key"   # never shown unasked
    ui.js("welcome.toggleKey()")
    assert welcome.property("keyText") == "k" * 43 + "=" and ui.find("keyShow").property("text") == "Hide key"
    assert ui.find("keyField").property("readOnly") is True and ui.find("keyField").property("text") == "k" * 43 + "="
    ui.js("welcome.keyCopied = bridge.copyText(welcome.keyText)")
    assert copied == ["k" * 43 + "="] and ui.find("keyCopy").property("text") == "Copied"
    ui.js("welcome.toggleKey()")                                   # Hide
    assert welcome.property("keyText") == ""
    ui.js("welcome.toggleKey(); welcome.finish()")                 # closing the card puts it away too
    _until_true(ui, lambda: ui.find("welcome").property("visible") is False)
    assert welcome.property("keyText") == ""
    assert "interval: 60000; running: welcome.keyText" in qml_source(), "and it is put away by itself after a minute"
    # no key to show
    monkeypatch.setattr(vault, "state", lambda: "off")
    ui.js("welcome.openCard(); welcome.toggleKey()")
    assert welcome.property("keyText") == "" and "no key to show" in welcome.property("keyErr")

    # a new Mac: the saved key opens the data again
    used = []
    def restore(text):
        if text != "good-key":
            raise vault.VaultError("That key does not belong to this data." if text == "other-key" else "That is not a valid JobHelper key.")
        used.append(text)
    monkeypatch.setattr(vault, "restore_key", restore)
    ui.win.setProperty("connData", {**READY, "vault": "locked", "changed_files": []})
    field = ui.find("restoreField")
    for typed, part in (("", "Paste your recovery key first"), ("two words", "not a recovery key"), ("ключ", "not a recovery key"),
                        ("x" * 201, "not a recovery key"), ("bad-key", "not a recovery key for this data"), ("other-key", "does not belong")):
        field.setProperty("text", typed)
        ui.js("welcome.restoreKey()")
        assert part in welcome.property("restoreErr"), typed
        assert field.property("text") == "", "what was pasted is never left on screen"
        assert typed == "" or typed not in welcome.property("restoreErr")
    field.setProperty("text", "good-key")
    ui.js("welcome.restoreKey()")
    assert used == ["good-key"] and welcome.property("restoreErr") == ""
    ui.win.setProperty("connData", dict(READY))
    ui.js('welcome.keyErr = ""; welcome.finish()')
    _until_true(ui, lambda: ui.find("welcome").property("visible") is False)
    assert "python status.py" not in (ROOT / "ui_qt" / "WelcomeOverlay.qml").read_text(encoding="utf-8")
    assert ui.warnings == []


def test_a_refused_app_password_is_not_saved(ui, monkeypatch):
    """Before, only the form of the password was checked, and a wrong one showed up at the first scan."""
    from jobhelper import email_client
    saved, tried = [], []
    monkeypatch.setattr(config, "set_imap", lambda user, pwd, lookback=None, host=None: saved.append((user, pwd)))
    monkeypatch.setattr(email_client, "try_login", lambda user, password, timeout=8.0, host="": tried.append((user, password)) or
                        {"ok": False, "msg": "The mail server refused this address and App Password. Check both."})
    welcome = ui.find("welcome")
    ui.js("welcome.openCard(); welcome.editBox = 1")
    welcome.setProperty("editEmail", True)
    welcome.setProperty("emailDraft", "jobs@example.com")
    welcome.setProperty("hostDraft", "imap.example.com")
    welcome.setProperty("pwDraft", "abcdabcdabcdabcd")
    ui.js("welcome.saveEmail()")
    ui.js("welcome.saveEmail()")                                   # a second press while it is checking does nothing
    _email_answer(ui)
    assert tried == [("jobs@example.com", "abcdabcdabcdabcd")] and saved == []
    assert "refused" in welcome.property("emailErr") and welcome.property("editEmail") is True
    assert welcome.property("pwDraft") == "" and ui.find("emailSave").property("text") == "Save"

    # no connection: saved, and the card says the password was not tried
    monkeypatch.setattr(email_client, "try_login", lambda user, password, timeout=8.0, host="":
                        {"ok": None, "msg": "The mail server could not be reached, so the password was not tried."})
    welcome.setProperty("pwDraft", "abcdabcdabcdabcd")
    ui.js("welcome.saveEmail()")
    _email_answer(ui)
    assert saved == [("jobs@example.com", "abcdabcdabcdabcd")] and welcome.property("editEmail") is False
    note = _until_shown(ui, "emailNote")                           # the card may still be fading in on a slow machine
    assert note.property("visible") is True and "not tried" in note.property("text")
    ui.js('welcome.emailNote = ""; welcome.finish()')
    _until_true(ui, lambda: ui.find("welcome").property("visible") is False)
    assert ui.warnings == []


def test_a_welcome_field_with_an_error_is_red_even_with_the_focus(ui):
    """The email, its password and the recovery key showed the focus colour over their red error."""
    welcome = ui.find("welcome")
    ui.js("welcome.openCard(); welcome.editBox = 1")
    welcome.setProperty("editEmail", True)
    _until_shown(ui, "welcome")
    welcome.setProperty("emailDraft", "not-an-email")
    ui.js("welcome.saveEmail()")
    shown, red = _border_with_focus(ui, "welcome", "wEmail")
    assert shown == red, "the address is wrong: the address box is red"
    welcome.setProperty("emailDraft", "jobs@gmail.com")
    welcome.setProperty("pwDraft", "abcd efgh ijkl mnop 2")
    ui.js("welcome.saveEmail()")
    assert "16 letters" in welcome.property("emailErr")
    shown, red = _border_with_focus(ui, "welcome", "wPw")
    assert shown == red, "the address is right: the password box is red"
    welcome.setProperty("pwDraft", "")
    ui.js('welcome.emailErr = ""; welcome.emailDraft = ""; welcome.editEmail = false')
    ui.win.setProperty("connData", {**READY, "vault": "locked", "changed_files": []})
    welcome.setProperty("restoreErr", "That is not a recovery key.")
    shown, red = _border_with_focus(ui, "welcome", "restoreField")
    assert shown == red, "restoreField"
    welcome.setProperty("restoreErr", "")
    ui.win.setProperty("connData", dict(READY))
    ui.js("welcome.finish()")
    assert _until_true(ui, lambda: welcome.property("visible") is False)
    assert ui.warnings == []


def test_an_old_usage_reading_says_when_it_was_taken(ui):
    """While Claude refused every call, the 7-day line showed a reading from two days before as if it were now."""
    start = ui.js("usageData")
    try:
        ui.win.setProperty("usageData", {**start, "five_hour_used": 100, "five_hour_low": True, "five_hour_resets": "03:40", "five_hour_as_of": "",
                                         "seven_day_used": 0, "seven_day_resets": "22 Oct 02:00", "seven_day_as_of": "18 Oct 09:22"})
        assert _until_true(ui, lambda: ui.drawn("usageResets_seven_day").property("text") == "resets 22 Oct 02:00\nas of 18 Oct 09:22")
        assert ui.drawn("usageResets_five_hour").property("text") == "resets 03:40"     # a used-up window still says when it comes back
        assert ui.drawn("usageLeft_seven_day").property("text") == "100% left"
    finally:
        ui.win.setProperty("usageData", start)
    assert ui.warnings == []


def test_welcome_rejects_a_bad_email_and_stays_open(ui, monkeypatch):
    saved = []
    monkeypatch.setattr(config, "set_imap", lambda user, pwd, lookback=None, host=None: saved.append((user, pwd)))
    welcome = ui.find("welcome")
    ui.js("welcome.openCard()")
    welcome.setProperty("editEmail", True)
    welcome.setProperty("hostDraft", "")
    for email, password in (("not-an-email", ""), ("jobs@gmail.com", "short"), ("jobs@gmail.com", "пароль"), ("jobs@gmail.com", "abcdabcdabcd1234"),
                            ("jobs@example.com", "secret123"), ("jobs@outlook.com", "secret123"), ("jobs@seznam.cz", "пароль")):
        welcome.setProperty("emailDraft", email)
        welcome.setProperty("pwDraft", password)
        ui.js("welcome.saveEmail()")
        assert welcome.property("emailErr") != "", (email, password)
        assert welcome.property("editEmail") is True
    assert saved == []
    welcome.setProperty("emailDraft", "jobs@gmail.com")
    assert welcome.property("needsServer") is False and "Google App Password" in ui.find("mailHint").property("text")
    welcome.setProperty("emailDraft", "jobs@example.com")          # a provider the app does not know: its server is asked for
    assert welcome.property("needsServer") is True and "imap.example.com" in ui.find("mailHint").property("text")
    assert "bridge.saveEmailChecked(editBox, emailDraft, pwDraft, needsServer ? hostDraft" in qml_source()
    welcome.setProperty("hostDraft", "imap.example.com")
    welcome.setProperty("pwDraft", "abcd abcd abcd abcd")          # spaces as Google shows it
    ui.js("welcome.saveEmail()")
    assert welcome.property("emailBusy") is True and ui.find("emailSave").property("text") == "Checking…"
    _email_answer(ui)
    assert saved == [("jobs@example.com", "abcd abcd abcd abcd")]
    assert welcome.property("emailErr") == "" and welcome.property("editEmail") is False
    ui.js("welcome.finish()")
    _until_true(ui, lambda: ui.find("welcome").property("visible") is False)


# ── run progress ────────────────────────────────────────────────────────────


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
    _open(ui, dialog, 500)
    assert dialog.property("opened") is True
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
    assert dialog.property("visible") is False
    assert ui.warnings == []


@pytest.mark.parametrize("view, rows", [("new", 1), ("app", 1), ("resp", 0), ("ana", 22)])       # 2 headings + 5 lines for the last 7 days + 14 all-time rows
def test_views_list_the_data(ui, view, rows):
    ui.js(f'openView("{view}")')
    _until_open(ui, "tableDialog")
    assert ui.find("tableDialog").property("opened") is True
    assert ui.find("listView").property("count") == rows
    ui.js("close()", ui.find("tableDialog"))
    _until_closed(ui, "tableDialog")
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
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: "Python and Docker")
    dialog = ui.find("detailDialog")
    ui.js('detailDialog.show("app")')
    _until_open(ui, "detailDialog")
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
    _until_closed(ui, "detailDialog")
    assert ui.warnings == []


def test_detail_view_ignores_an_unknown_job(ui):
    ui.js('detailDialog.show("does-not-exist")')
    ui.wait(150)                                                       # nothing may open: only time can show that
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
    _open(ui, dialog, 450)
    spin = ui.find("fuSpin")
    assert spin.property("value") == 10
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
    ui.bridge.saveOptions({**ui.bridge.options(), "followup_days": 21})
    ui.js("optsData = bridge.options()")              # what Save does in the window
    _open(ui, dialog, 450)
    assert spin.property("value") == 21
    ui.js("close()", dialog)
    _until_closed(ui, dialog)



def test_the_options_lists_offer_what_the_back_end_accepts(ui):
    """The model, career-site system and text-size lists are filled from `limits().choices`: a new choice there shows
    here without a change to the window."""
    from jobhelper import scrapers_ats
    from jobhelper.api_options import OptionsService
    dialog = ui.find("optDialog")
    _open(ui, dialog, 450)
    assert ui.js("modelCombo.count") == len(OptionsService.MODELS)
    assert ui.js("coAts.count") == len(scrapers_ats.ATS_NAMES)
    assert ui.js("sizeCombo.count") == len(config.TEXT_SIZES)
    assert ui.js("sizeCombo.textAt(sizeCombo.count - 1)") == f"{config.TEXT_SIZES[-1]}%"
    assert ui.js("modelCombo.currentText") == ui.bridge.options()["model"]          # the saved model is chosen on open
    ui.js("close()", dialog)
    _until_closed(ui, dialog)


def test_scan_period_option_is_loaded_and_saved(ui):
    dialog = ui.find("optDialog")
    ui.bridge.saveOptions({**ui.bridge.options(), "scan_days": 45})
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    assert ui.find("scanSpin").property("value") == 45
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
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
    _until_open(ui, "limitDialog")
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
    _until_closed(ui, "limitDialog")

    ui.bridge.limitChanged.emit({**info, "can_resume": True})
    _until_true(ui, lambda: resume.property("color").name() != grey)
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
    _open(ui, dialog, 450)
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
    _until_closed(ui, dialog)


def test_a_saved_number_above_the_old_box_range_is_shown_and_saved_as_it_is(ui):
    """The boxes had their own ranges (max age 0-90, years 0-30, follow-up 0-90 …) while the back end takes more, so a value
    saved from the command line was cut to fit when Options opened, and Save wrote the smaller number with no word."""
    dialog = ui.find("optDialog")
    numbers = ui.bridge._api.OPTION_NUMBERS
    wide = {"max_age_days": 120, "max_years": 45, "followup_days": 200, "keep_backups": 500, "scan_days": 1000}
    for key, value in wide.items():
        low, high = numbers[key]
        assert low <= value <= high, key
    before = ui.bridge.options()                                                # put back at the end: one window for the whole file
    ui.bridge.saveOptions({**before, **wide, "where": "Prague"})
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    shown = {"max_age_days": "ageSpin", "max_years": "yearsSpin", "followup_days": "fuSpin", "keep_backups": "keepSpin", "scan_days": "scanSpin"}
    for key, spin in shown.items():
        assert ui.js(spin + ".value") == wide[key], key
        assert ui.js(spin + ".to") == numbers[key][1], f"{spin} reaches what the back end allows"
    ui.js("optSaveBtn.clicked()")                                              # the real Save button: it saves and closes
    _until_closed(ui, dialog)
    assert ui.js("optDialog.optErr") == "" and {key: ui.bridge.options()[key] for key in wide} == wide, "nothing was cut on the way back"
    ui.bridge.saveOptions(before)
    ui.js("optsData = bridge.options()")


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
    _until_open(ui, "detailDialog")
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
    _until_closed(ui, "detailDialog")
    assert ui.warnings == []


def test_second_mailbox_row_follows_the_connection(ui):
    welcome = ui.find("welcome")
    ui.js("welcome.openCard()")
    _until_shown(ui, "welcome")
    ui.win.setProperty("connData", {**READY, "email2": False, "email2_addr": ""})
    assert ui.find("secondMailAdd").property("text") == "Add"
    ui.js("welcome.editBox = 2; welcome.editEmail = true")
    welcome.setProperty("emailDraft", READY["email_addr"])
    welcome.setProperty("pwDraft", "abcdabcdabcdabcd")
    ui.js("welcome.saveEmail()")
    _email_answer(ui)
    assert "already your main job email" in welcome.property("emailErr")    # refused, card stays open
    ui.js('welcome.editEmail = false; welcome.emailErr = ""; welcome.editBox = 1')
    ui.win.setProperty("connData", {**READY, "email2": True, "email2_addr": "second@example.com"})
    assert ui.find("secondMailAdd").property("text") == "Change"
    ui.win.setProperty("connData", dict(READY))
    ui.js("welcome.finish()")
    _until_true(ui, lambda: ui.find("welcome").property("visible") is False)
    assert ui.warnings == []


# ── skip words, readable replies, analytics that add up ─────────────────────
def test_skip_words_and_exceptions_are_edited_loaded_and_saved(ui):
    dialog, skip, keep = ui.find("optDialog"), ui.find("skipTags"), ui.find("keepTags")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    assert ui.js('all().join(",")', skip) == "intern,internship"          # the default
    assert ui.js('add("Student")', skip) is True and ui.js('add("student")', skip) is False
    assert "already" in skip.property("err")
    assert ui.js('add("стажёр")', skip) is False and "Latin" in skip.property("err")
    assert ui.js('add("7")', skip) is False
    assert ui.js('add("graduate program")', keep) is True
    assert ui.js('all().join(",")', skip) == "intern,internship,student"
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
    ui.bridge.saveOptions({**ui.bridge.options(), "skip_words": ["sales"], "keep_words": ["sales engineer"]})
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    assert ui.js('all().join(",")', skip) == "sales" and ui.js('all().join(",")', keep) == "sales engineer"
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
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
    _until_open(ui, "tableDialog")
    assert ui.js("listView.model[0].rid") == "<r1@x>"
    ui.js('responseDialog.show("<r1@x>")')
    _until_open(ui, "responseDialog")
    assert ui.find("responseDialog").property("opened") is True
    assert ui.find("responseTitle").property("text") == "Beta"
    assert ui.find("responseSummary").property("text") == "Beta chose another candidate."
    assert ui.js("responseDialog.r.category") == "went with other candidate" and ui.js("responseDialog.r.date") == "2026-10-05 10:15"
    assert ui.js("responseDialog.r.job_title") == "QA Engineer"
    ui.js("responseDialog.close(); tableDialog.close()")
    _until_closed(ui, "responseDialog")
    _until_closed(ui, "tableDialog")
    ui.js('responseDialog.show("<missing>")')
    assert ui.find("responseDialog").property("visible") is False
    assert ui.warnings == []


def test_analytics_rows_add_up(ui):
    ui.js('openView("ana")')
    _until_open(ui, "tableDialog")
    rows = {r["primary"]: int(r["value"]) for r in [
        {"primary": ui.js(f"listView.model[{i}].primary"), "value": ui.js(f"listView.model[{i}].value")}
        for i in range(ui.find("listView").property("count"))] if str(r["value"]).strip() != ""}
    assert rows["Applications"] == rows["↳ waiting for an answer"] + rows["↳ in interviews now"] + rows["↳ offers"] + rows["↳ rejected"]
    assert rows["Reply emails"] == (rows["↳ confirmations"] + rows["↳ interview emails"] + rows["↳ tests and tasks"]
                                    + rows["↳ rejections"] + rows["↳ other"])
    assert rows["Why the rejection emails said no"] == rows["↳ rejections"]
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")


# ── search / filter / sort, not interested, letter editor ───────────────────


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
        _until_open(ui, "tableDialog")
        dialog, search = ui.find("tableDialog"), ui.find("searchField")
        assert len(_titles(ui)) == 4 and ui.js("titleTxt.text", dialog).endswith("– 4")
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
        _until_closed(ui, "tableDialog")
        _store.save_jobs(jobs)
    assert ui.warnings == []


def test_not_interested_hides_the_lead_and_the_filter_restores_it(ui):
    from jobhelper import store as _store
    jobs = _store.load_jobs()
    _store.save_jobs(jobs + [_store.new_job(id="bye", title="Boring Role", company="Nope Ltd", match_score=10)])
    try:
        ui.js('openView("new")')
        _until_open(ui, "tableDialog")
        assert any(t.startswith("Boring Role") for t in _titles(ui))
        ui.js('detailDialog.show("bye")')
        _until_open(ui, "detailDialog")
        assert ui.find("notInterested").property("visible") is True
        assert ui.js('bridge.dismissJob("bye").ok') is True
        ui.js("detailDialog.close(); refreshOpenView()")
        _until_closed(ui, "detailDialog")
        assert not any(t.startswith("Boring Role") for t in _titles(ui)) and ui.js("countsData.leads") is not None
        ui.js('groupFilter = "not interested"; apply()', ui.find("tableDialog"))
        assert _titles(ui) == ["Boring Role  ·  Nope Ltd"] and ui.js("listView.model[0].actions[0].kind") == "restore"
        assert ui.js('bridge.restoreJob("bye").ok') is True
        ui.js("refreshOpenView()")
        _until_true(ui, lambda: ui.js("groupFilter", ui.find("tableDialog")) == "")
        assert ui.js("groupFilter", ui.find("tableDialog")) == ""                # that group is empty again
        assert any(t.startswith("Boring Role") for t in _titles(ui))
    finally:
        ui.js("tableDialog.close()")
        _until_closed(ui, "tableDialog")
        _store.save_jobs(jobs)
    assert ui.warnings == []


def test_letter_editor_edits_rewrites_and_saves(ui, monkeypatch):
    import shutil
    from jobhelper import cover_letter, llm, store as _store
    template = ROOT / "tests" / "fixtures" / "letter_example_deutscheborse.docx"      # never your own template in data/
    monkeypatch.setattr(config, "LETTER_TEMPLATE", config.DATA_DIR / "cover_letter_template.docx")
    shutil.copy2(template, config.LETTER_TEMPLATE)
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: "Alex Novak\nPython, Docker.")
    paras = [("I am applying because the work matches what I build every day. " * 5).strip() for _ in range(5)]
    cover_letter.build_docx(config.LETTER_TEMPLATE, config.LETTERS_DIR / "L.docx", "QA Engineer", paras, date_text="7 October 2026")
    jobs = _store.load_jobs()
    lead = _store.find(jobs, "lead"); lead["cover_letter_file"] = "L.docx"
    _store.save_jobs(jobs)
    dialog = ui.find("letterDialog")
    ui.js('letterDialog.show("lead")')
    _until_open(ui, "letterDialog")
    assert dialog.property("opened") is True and ui.js("letterDialog.texts.length") == 5
    assert ui.js("letterDialog.dirty") is False and ui.find("letterSave").property("enabled") is False

    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"paragraph": "I would like to bring the same drive to this team."})
    ui.js("letterDialog.rewrite(3)")
    assert ui.js("letterDialog.busyIndex") == 3
    for _ in range(100):
        ui.wait(30)
        if ui.js("letterDialog.busyIndex") == -1:
            break
    assert ui.js("letterDialog.err") == ""
    assert ui.js("letterDialog.texts[3]") == "I would like to bring the same drive to this team."
    assert ui.js("letterDialog.dirty") is True and "rewritten" in ui.js("letterDialog.info")
    assert cover_letter.read_letter(config.LETTERS_DIR / "L.docx")["paragraphs"][3] == paras[3]     # nothing saved yet

    ui.js("letterDialog.save()")
    assert ui.js("letterDialog.err") == "" and ui.js("letterDialog.dirty") is False
    assert cover_letter.read_letter(config.LETTERS_DIR / "L.docx")["paragraphs"][3] == "I would like to bring the same drive to this team."
    ui.js('letterDialog.setText(0, ""); letterDialog.save()')
    assert "5 paragraphs" in ui.js("letterDialog.err") and dialog.property("opened") is True        # red message, stays open
    ui.js("letterDialog.close()")
    _until_closed(ui, "letterDialog")
    lead["cover_letter_file"] = ""
    _store.save_jobs(jobs)
    assert ui.warnings == []


# ── insights and interview preparation ──────────────────────────────────────
def test_insights_view_lists_roles_keywords_and_skills(ui, monkeypatch):
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: "Python and Docker")
    ui.js('openView("ins")')
    _until_open(ui, "tableDialog")
    rows = [(ui.js(f"listView.model[{i}].primary"), ui.js(f"listView.model[{i}].heading")) for i in range(ui.find("listView").property("count"))]
    heads = [text for text, heading in rows if heading is True]
    assert heads == ["What is working: kinds of role", "What is working: where the job came from", "Week by week",
                     "How long companies take to decide", "Search keywords", "Skills to learn", "Why jobs score low",
                     "What the postings pay"]
    assert any(str(text).startswith("Week of ") and str(text).endswith("(this week)") for text, _ in rows)
    assert any(text == "Kubernetes" for text, _ in rows)                           # asked for in the seeded posting, not in the CV
    assert ui.js("sorts.length", ui.find("tableDialog")) == 0                      # a plain list, no toolbar
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")
    assert ui.warnings == []


def test_interview_preparation_from_the_job_window(ui, monkeypatch):
    from jobhelper import llm
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: "Alex Novak\nPython, Docker.")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {
        "summary": "Mostly Python.", "ask_them": ["What is the team like?"], "revise": ["Docker"],
        "questions": [{"kind": "about you", "question": "Tell me about yourself.", "why": "Opening.", "answer": "I am a junior developer."},
                      {"kind": "technical", "question": "Kubernetes?", "why": "", "answer": "I have years of production experience with Kubernetes."}]})
    ui.js('detailDialog.show("app")')
    _until_open(ui, "detailDialog")
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
    _until_closed(ui, "prepDialog")
    _until_closed(ui, "detailDialog")
    ui.js('prepDialog.show("lead")')
    assert prep.property("visible") is False                                       # nothing saved for that job
    assert ui.warnings == []


# ── help, and the cost wording ──────────────────────────────────────────────
def test_help_opens_from_the_button_and_covers_the_app(ui):
    dialog = ui.find("helpDialog")
    assert ui.find("helpButton").property("text") == "Help"
    _open(ui, dialog, 500)
    assert dialog.property("opened") is True
    titles = ui.js("topics.map(function (t) { return t.title; }).join('|')", dialog)
    for expected in ("What JobHelper does", "A normal week", "Scores and labels", "The assistant", "Claude and the limit", "Privacy and safety"):
        assert expected in titles
    text = ui.js("topics.map(function (t) { return t.lines.join(' '); }).join(' ')", dialog)
    assert "empty fields only" in text and "Opera GX and Firefox do not" in text      # the assistant is explained as well
    assert "never sends" in text and "never invents experience" in text and "recovery key" in text
    assert "—" not in text                                             # en dash rule applies to the help too
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
    assert ui.warnings == []


def test_last_run_card_says_what_you_paid_and_the_api_price(ui):
    source = qml_source()
    assert '"You paid"' in source and '"Same work via API"' in source and '"subscription only"' in source
    assert "$0" not in source, "nothing was paid per run, so no price is shown next to 'You paid'"
    assert '"Total cost"' not in source and '"Cost (API-equiv.)"' not in source
    assert "usageData.cost" not in source, "the card shows the last run's cost, not the total of everything"


def test_last_run_card_shows_the_cost_of_the_last_run_only(ui):
    ui.js('lastRunData = ({ when: "07 Oct 14:20", found: "+3 new" })')
    ui.wait(60)
    assert {"Same work via API", "after next run"} <= _card_values(ui)     # a summary saved before costs were noted
    ui.js('lastRunData = ({ when: "07 Oct 14:20", found: "+3 new", cost: 0.4, cost_of: "search" })')
    ui.wait(60)
    values = _card_values(ui)
    assert {"Same search via API", "≈ $0.40", "subscription only"} <= values and "Same work via API" not in values
    ui.js('lastRunData = ({ scan: "07 Oct · 0 new", cost: 0, cost_of: "email scan" })')
    ui.wait(60)
    assert {"Same scan via API", "≈ $0.00"} <= _card_values(ui)
    ui.js("lastRunData = bridge.lastRun()")
    assert ui.warnings == []


def test_last_run_card_says_how_much_mail_the_scan_went_through(ui):
    ui.js('lastRunData = ({ scan: "09 Oct · 0 new" })')
    ui.wait(60)
    assert "Emails read" not in _card_values(ui)                # a summary saved before this was noted: no empty row
    ui.js('lastRunData = ({ scan: "09 Oct · 0 new", scan_detail: "45 · 5 asked", cost: 0.08, cost_of: "email scan" })')
    ui.wait(60)
    assert {"Emails read", "45 · 5 asked", "09 Oct · 0 new"} <= _card_values(ui)
    ui.js("lastRunData = bridge.lastRun()")
    assert ui.warnings == []


def test_about_you_takes_your_own_salary_figure_and_currency(ui):
    dialog = ui.find("aboutDialog")
    start = ui.bridge.options()
    assert ui.bridge.saveOptions({**start, "where": "Prague", "country": ""})["ok"] is True
    ui.js("aboutDialog.show()")
    _until_open(ui, "aboutDialog")
    spin, combo, note = ui.find("salarySpin"), ui.find("currencyCombo"), ui.find("salaryNote")
    assert spin.property("value") == 0 and combo.property("currentText") == "CZK" and combo.property("count") >= 10
    assert "the app's estimate" in note.property("text") or "only for software roles" in note.property("text")
    ui.js("close()", dialog)
    _until_closed(ui, "aboutDialog")
    assert ui.bridge.saveOptions({**ui.bridge.options(), "where": "Berlin"})["ok"] is True
    ui.js("aboutDialog.show()")
    _until_open(ui, "aboutDialog")
    assert "no estimate for this country" in note.property("text")
    spin.setProperty("value", 3200)
    ui.js('currencyCombo.currentIndex = currencyCombo.find("EUR")', dialog)
    assert "Form answers give this" in note.property("text")
    import json
    got = json.loads(ui.js("JSON.stringify(aboutDialog.collect())", dialog))
    assert (got["salary_target"], got["salary_currency"]) == (3200, "EUR") and "where" not in got     # only the About you facts
    ui.js("aboutDialog.save()", dialog)
    _until_closed(ui, "aboutDialog")
    assert ui.bridge.options()["where"] == "Berlin"                                       # the other Options are kept

    # the job window and the list say it in that currency
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(salary="70 000 - 80 000 CZK", desired_monthly_czk=58000), render=False)
    detail = ui.bridge.jobDetail("lead")
    assert detail["desired_text"] == "3 200 EUR/mo target" and detail["pay_text"] == "posting says 2 800–3 200 EUR/mo"
    assert [r["desired"] for r in ui.bridge.leads() if r["id"] == "lead"] == ["3 200 EUR/mo"]
    ui.js("aboutDialog.show()")
    _until_open(ui, "aboutDialog")
    assert ui.find("salarySpin").property("value") == 3200 and ui.find("currencyCombo").property("currentText") == "EUR"   # loaded again
    ui.js("close()", dialog)
    _until_closed(ui, "aboutDialog")
    # no figure of your own, in Berlin: nothing is shown, rather than a Prague figure
    assert ui.bridge.saveOptions({**ui.bridge.options(), "salary_target": 0})["ok"] is True
    assert ui.bridge.jobDetail("lead")["desired_text"] == ""
    assert ui.bridge.saveOptions({**ui.bridge.options(), "where": "Prague", "salary_currency": "CZK"})["ok"] is True
    detail = ui.bridge.jobDetail("lead")
    assert detail["desired_text"] == "58 000 CZK/mo target" and detail["pay_text"] == "posting says 70–80k CZK/mo"
    ui.bridge.saveOptions(start)
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(salary="", desired_monthly_czk=""), render=False)
    ui.js("optsData = bridge.options()")
    assert "CZK/mo" not in (ROOT / "ui_qt" / "DetailDialog.qml").read_text(encoding="utf-8") and "CZK/mo" not in (ROOT / "ui_qt" / "views.js").read_text(encoding="utf-8")
    assert ui.warnings == []


def test_options_has_a_country_for_any_city(ui):
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    field = ui.find("countryField")
    ui.js('cityCombo.editText = "Prague"', dialog)
    assert field.property("text") == "" and field.property("placeholderText") == "Czechia (from the city)"
    ui.js('cityCombo.editText = "Smallville"', dialog)
    assert field.property("placeholderText") == "not known for this city: type it"
    for wrong, part in (("Германия", "in English"), ("Germany 2", "no digits"), ("DE;", "only the country's name")):
        assert part in ui.js('optDialog.countryProblem("%s")' % wrong, dialog), wrong
    for fine in ("", "Germany", "United Kingdom", "Côte d'Ivoire", "St. Lucia", "Bosnia-Herzegovina"):
        assert ui.js('optDialog.countryProblem("%s")' % fine, dialog) == "", fine
    ui.js('cityCombo.editText = "Tbilisi"; countryField.text = "Georgia 1"', dialog)
    before = ui.bridge.options().get("country", "")
    assert "no digits" in ui.js("optDialog.countryProblem(countryField.text)", dialog)
    assert ui.js("optDialog.collect().options.country", dialog) == "Georgia 1"
    assert ui.bridge.saveOptions(ui.js("optDialog.collect().options", dialog) and {**ui.bridge.options(), "country": "Georgia 1"})["ok"] is False
    assert ui.bridge.options().get("country", "") == before             # the backend refuses the same thing
    ui.js('countryField.text = " Georgia "', dialog)
    assert ui.js("optDialog.collect().options.country", dialog) == "Georgia"
    ui.js("confirmClose = true; close()", dialog)
    _until_closed(ui, dialog)
    ui.js("optsData = bridge.options()")
    assert ui.warnings == []


def test_job_sources_are_picked_in_any_combination(ui):
    """One dropdown of fixed sets plus a remote switch could not say "LinkedIn and the Czech boards": each kind is now a chip."""
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    plain = lambda v: v.toVariant() if hasattr(v, "toVariant") else v                    # noqa: E731
    assert [k["name"] for k in plain(ui.js("optDialog.sourceKinds", dialog))] == ["Czech boards", "LinkedIn", "Career sites", "Remote boards"]
    ui.js("pickedSources = ['boards', 'linkedin', 'careers']", dialog)
    ui.js("toggleSource('careers'); toggleSource('remote'); toggleSource('linkedin'); toggleSource('linkedin')", dialog)
    assert plain(ui.js("optDialog.collect().options.sources", dialog)) == ["boards", "linkedin", "remote"]      # always in one order
    chip = lambda key: ui.drawn("source_" + key, root="sourceChips")                    # noqa: E731 - drawn by a Repeater
    assert chip("careers").property("picked") is False and chip("remote").property("picked") is True
    assert ui.find("sourcesErr").property("visible") is False
    ui.js("toggleSource('boards'); toggleSource('linkedin'); toggleSource('remote')", dialog)
    assert ui.find("sourcesErr").property("visible") is True                # none left: said at once, in red
    ui.js('cityCombo.editText = "Prague"', dialog)
    before = ui.bridge.options()["sources"]
    ui.js("optSaveBtn.clicked()", dialog)                                   # Save with nothing picked: refused, nothing stored
    assert ui.find("sourcesErr").property("visible") is True and dialog.property("opened") is True
    assert ui.js("optErr", dialog) == "", "said once, by its own red line, not again in the footer"
    assert "at least one job source" in ui.bridge.saveOptions({**ui.bridge.options(), "sources": []})["msg"]   # the back end refuses it too
    assert ui.bridge.options()["sources"] == before
    ui.js("confirmClose = true; close()", dialog)
    _until_closed(ui, "optDialog")
    ui.js("optsData = bridge.options()")


def test_remote_jobs_are_kept_in_your_country_with_added_countries_or_anywhere(ui):
    dialog, picker = ui.find("optDialog"), ui.find("remoteDialog")
    plain = lambda v: v.toVariant() if hasattr(v, "toVariant") else v                    # noqa: E731
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    ui.js('cityCombo.editText = "Prague"; countryField.text = ""; remoteWhere = "country"; pickedRemote = []', dialog)
    scope = lambda key: ui.drawn("remote_" + key, root="remoteScope")                   # noqa: E731 - drawn by a Repeater
    assert scope("country").property("picked") is True and ui.js("optDialog.homeName", dialog) == "Czechia"
    assert ui.find("remoteAdd").property("text") == "+ Add countries"
    # the picker: your own country is not a choice, the list filters by name and by part of the world
    ui.js("remoteAddBtn.clicked()", dialog)
    _until_open(ui, "remoteDialog")
    assert ui.js("remoteDialog.home") == "czechia" and ui.js("remoteDialog.shown.some(c => c.key === 'czechia')") is False
    assert "Czechia is always included" in ui.find("remoteHomeNote").property("text")
    ui.js('searchField.text = "kor"', picker)
    assert [c["key"] for c in plain(ui.js("remoteDialog.shown"))] == ["north korea", "south korea"]
    ui.js('searchField.text = "xyz"', picker)
    assert ui.find("noCountry").property("visible") is True
    ui.js('searchField.text = ""; remoteDialog.area = "oceania"', picker)
    assert all(c["area"] == "oceania" for c in plain(ui.js("remoteDialog.shown"))) and len(plain(ui.js("remoteDialog.shown"))) >= 10
    ui.js("remoteDialog.area = ''; remoteDialog.toggle('south korea'); remoteDialog.toggle('germany'); remoteDialog.toggle('poland');"
          "remoteDialog.toggle('poland')")
    assert plain(ui.js("remoteDialog.picked")) == ["germany", "south korea"]             # in the list's order
    assert ui.find("pickedCount").property("text") == "2 countries added"
    ui.js("remoteDialog.picked = remoteDialog.all.slice(0, 40).map(c => c.key); remoteDialog.toggle('vietnam')")
    assert "up to 40 countries" in ui.find("remoteErr").property("text")                # a 41st is refused in red
    ui.js("remoteDialog.picked = ['germany', 'south korea']; remoteDialog.err = ''")
    ui.js("remoteDoneBtn.clicked()", picker)
    _until_closed(ui, "remoteDialog")
    # back in Options: the countries are chips with a cross; Save stores them
    assert plain(ui.js("optDialog.pickedRemote", dialog)) == ["germany", "south korea"]
    assert ui.drawn("remoteCountry_south korea", root="remoteCountries") is not None and ui.find("remoteAdd").property("text") == "Change"
    ui.js("dropRemote('germany')", dialog)
    assert plain(ui.js("optDialog.collect().options.remote_countries", dialog)) == ["south korea"]
    ui.js("remoteWhere = 'world'", dialog)
    assert ui.find("remoteCountries").property("visible") is True                       # added countries count in both choices
    assert "any part of the world" in ui.find("remoteNote").property("text") and "except for these" in ui.find("remoteNote").property("text")
    ui.js("remoteWhere = 'country'", dialog)
    start = ui.bridge.options()
    ui.js("optSaveBtn.clicked()", dialog)
    _until_closed(ui, "optDialog")
    saved = ui.bridge.options()
    assert saved["remote_where"] == "country" and saved["remote_countries"] == ["south korea"]
    # Cancel in the picker leaves the choice as it was
    _open(ui, dialog, 450)
    ui.js("remoteAddBtn.clicked()", dialog)
    _until_open(ui, "remoteDialog")
    ui.js("remoteDialog.toggle('japan'); remoteDialog.close()")
    _until_closed(ui, "remoteDialog")
    assert plain(ui.js("optDialog.pickedRemote", dialog)) == ["south korea"]
    ui.js("confirmClose = true; close()", dialog)
    _until_closed(ui, "optDialog")
    ui.bridge.saveOptions(start)
    ui.js("optsData = bridge.options()")
    assert ui.warnings == []


def test_options_says_in_red_when_macos_hides_the_notifications(ui):
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    row = ui.find("notifyOffRow")
    assert ui.js("optDialog.notifyPermission", dialog) == "unknown" and row.property("visible") is False   # tests: not the built app
    ui.js('notifySw.checked = true; optDialog.notifyPermission = "off"', dialog)
    assert _until_true(ui, lambda: row.property("visible") is True)
    assert "System Settings → Notifications → JobHelper" in ui.find("notifyOff").property("text")
    ui.js("notifySw.checked = false", dialog)                                # switched off in the app: nothing to say
    assert _until_true(ui, lambda: row.property("visible") is False)
    ui.js('notifySw.checked = true; optDialog.notifyPermission = "allowed"', dialog)
    assert row.property("visible") is False
    ui.js("notifyTestBtn.clicked()", dialog)                                 # the plain way in tests: never a real notification
    assert ui.find("notifyNote").property("visible") is True and ui.find("notifyNote").property("text") != ""
    ui.js("confirmClose = true; close()", dialog)
    _until_closed(ui, "optDialog")
    assert ui.warnings == []


def test_the_main_screen_names_the_sources_a_search_reads(ui):
    def chips():
        return [item.property("text") for item in ui.seen("navPanel") if isinstance(item.property("text"), str)]
    ui.js('optsData = Object.assign({}, bridge.options(), { source_names: ["Czech boards", "LinkedIn"] })')
    ui.wait(60)
    assert "Czech boards" in chips() and "LinkedIn" in chips() and "+ Remote" not in chips() and "Remote boards" not in chips()
    ui.js('optsData = Object.assign({}, bridge.options(), { source_names: ["LinkedIn", "Remote boards"] })')
    ui.wait(60)
    assert "Remote boards" in chips() and "Czech boards" not in chips()
    ui.js("optsData = bridge.options()")
    assert ui.warnings == []


def test_options_can_start_one_longer_email_scan(ui, monkeypatch):
    started = []
    monkeypatch.setattr(qt_bridge.Bridge, "_scan", lambda self, days=None: started.append(days))
    monkeypatch.setattr(config, "IMAP_USER", "jobs@example.com")
    monkeypatch.setattr(config, "IMAP_PASSWORD", "abcdabcdabcdabcd")
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    saved_days = ui.find("scanSpin").property("value")
    spin, note = ui.find("backSpin"), ui.find("backNote")
    assert spin.property("value") == 90 and note.property("visible") is False
    spin.setProperty("value", 60)
    ui.js("optDialog.scanBack()", dialog)
    for _ in range(50):
        ui.wait(20)
        if started:
            break
    assert started == [60] and "last 60 days" in note.property("text") and dialog.property("backBad") is False
    assert ui.find("scanSpin").property("value") == saved_days and ui.bridge.options()["scan_days"] == saved_days   # the setting stays
    ui.js("optDialog.scanBack()", dialog)                          # the first one is still "running"
    assert dialog.property("backBad") is True and "running" in note.property("text") and started == [60]
    ui.bridge._set_running(False)
    ui.js('win.runMode = ""; win.resetRobots()')
    monkeypatch.setattr(config, "IMAP_PASSWORD", "")
    ui.js("optDialog.scanBack()", dialog)                          # no mailbox: said here, in red
    assert dialog.property("backBad") is True and "job email" in note.property("text") and started == [60]
    ui.js("confirmClose = false; close()", dialog)
    _until_closed(ui, dialog)
    assert ui.warnings == []


def test_closing_buttons_ask_once_before_they_discard_unsaved_text(ui, monkeypatch):
    """Mark applied and Not interested close the job window; with text not saved they used to discard it silently."""
    done = []
    monkeypatch.setattr(qt_bridge.Bridge, "applyJob", qt_bridge.Slot(str, result=bool)(lambda self, job_id: done.append(("apply", job_id)) or True))
    monkeypatch.setattr(ui_api.Api, "dismiss_job", lambda self, job_id: done.append(("dismiss", job_id)) or {"ok": True})
    ui.js('detailDialog.show("lead")')
    _until_open(ui, "detailDialog")
    note = ui.find("closeNote")
    ui.js('cnNotes.text = "They pay monthly."')
    ui.js("detailDialog.markApplied()")
    assert done == [] and ui.find("detailDialog").property("opened") is True
    assert note.property("text") == "Not saved yet: the notes about the company. Save it, or press Mark applied once more to discard it."
    ui.js("detailDialog.notInterested()")                       # another button: asked about again, by its own name
    assert done == [] and "press Not interested once more" in note.property("text")
    ui.js("detailDialog.notInterested()")                       # the second press of the same button goes ahead
    _until_closed(ui, "detailDialog")
    assert done == [("dismiss", "lead")] and ui.find("detailDialog").property("opened") is False
    ui.js('detailDialog.show("lead")')
    _until_open(ui, "detailDialog")
    assert ui.js("detailDialog.confirmAction") == "" and note.property("visible") is False
    ui.js("detailDialog.markApplied()")                         # nothing typed: no question
    _until_closed(ui, "detailDialog")
    assert done[-1] == ("apply", "lead") and ui.find("detailDialog").property("opened") is False
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")
    source = (ROOT / "ui_qt" / "DetailDialog.qml").read_text(encoding="utf-8")
    assert source.count("bridge.applyJob(") == 1 and source.count("bridge.dismissJob(") == 1, "both buttons go through the asking functions"
    assert ui.warnings == []


def test_usage_card_corrects_itself_when_a_reset_time_passes(ui):
    timer = ui.find("usageReset")
    keep = ui.js("JSON.stringify(usageData)")
    ui.js('usageData = ({ model: "sonnet", five_hour_used: 12, next_reset_in: 0 })')
    assert timer.property("running") is False
    ui.js('usageData = ({ model: "sonnet", five_hour_used: 100, five_hour_resets: "14:00", next_reset_in: 600 })')
    assert timer.property("running") is True and timer.property("interval") == 601500
    ui.js('usageData = ({ model: "sonnet", seven_day_used: 100, next_reset_in: 590000 })')      # days away: still a valid timer
    assert 0 < timer.property("interval") <= 2147483647
    ui.js('usageData = ({ model: "sonnet", five_hour_used: 100, five_hour_resets: "14:00", next_reset_in: 1 })')
    _until_true(ui, lambda: ui.js("usageData.five_hour_used") != 100, most_ms=8000)
    assert ui.js("usageData.five_hour_used") != 100
    ui.js("usageData = JSON.parse('%s')" % keep.replace("\\", "\\\\").replace("'", "\\'"))
    assert ui.warnings == []


def test_a_long_choice_in_a_combo_box_wraps_instead_of_being_cut(ui):
    """ThemedCombo (the assistant's job and browser boxes use it): a long choice wraps, never cut. Tried on a box made
    for the test, the size Options' old "Job source" box had."""
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    combo = ui.js('Qt.createQmlObject(\'import QtQuick; ThemedCombo { implicitWidth: 210; textRole: "text"; valueRole: "value"; '
                  'model: [{ text: "LinkedIn only", value: "a" }, { text: "Czech boards, LinkedIn & careers", value: "b" }] }\', '
                  'sourcesBox, Qt.resolvedUrl("WrapTest.qml"))', dialog)
    combo.setProperty("currentIndex", 0)                         # short
    ui.wait(80)
    short, line = combo.property("height"), combo.property("contentItem")
    assert short == 32 and line.property("lineCount") == 1
    combo.setProperty("implicitWidth", 150)                       # a box that cannot hold the longest choice on one line
    combo.setProperty("currentIndex", 1)
    ui.wait(80)
    assert line.property("lineCount") >= 2 and combo.property("height") > short
    assert line.property("truncated") is False and line.property("text") == "Czech boards, LinkedIn & careers"
    assert line.property("x") + line.property("width") <= combo.property("width")          # clear of the arrow's side
    # and it is really drawn: the box holds pixels in the text's colour (a blank box once passed every check above)
    assert line.property("visible") is True and line.property("opacity") == 1
    from PySide6.QtQuick import QQuickWindow
    corner = line.mapToScene(line.boundingRect().topLeft())
    picture = QQuickWindow.grabWindow(ui.win).copy(int(corner.x()), int(corner.y()), int(line.width()), int(line.height()))
    ink = ui.js("theme.ink")
    close = lambda c: abs(c.red() - ink.red()) + abs(c.green() - ink.green()) + abs(c.blue() - ink.blue()) < 90      # noqa: E731
    assert sum(close(picture.pixelColor(x, y)) for x in range(0, picture.width(), 2) for y in range(0, picture.height(), 2)) > 20
    assert ui.js("cityCombo.height", dialog) == 32               # an editable box keeps its one-line field
    combo.deleteLater()
    ui.js("confirmClose = false; close()", dialog)
    _until_closed(ui, "optDialog")
    assert ui.warnings == []


def test_usage_card_shows_nothing_left_and_when_it_resets(ui):
    keep = ui.js("JSON.stringify(usageData)")
    width = ui.find("statusPanel").property("width")
    ui.js('usageData = ({ model: "sonnet", five_hour_used: 100, five_hour_low: true, five_hour_resets: "12 Oct 14:00", seven_day_used: 34, seven_day_resets: "12 Oct 09:00" })')
    ui.wait(60)
    five, seven = ui.drawn("usageLeft_five_hour"), ui.drawn("usageLeft_seven_day")
    assert five.property("text") == "0% left" and five.property("font").bold()
    resets = ui.drawn("usageResets_five_hour")
    assert resets.property("visible") is True and resets.property("text") == "resets 12 Oct 14:00"
    assert seven.property("text") == "66% left"
    assert ui.drawn("usageResets_seven_day").property("text") == "resets 12 Oct 09:00"      # each window says its own reset time
    assert ui.find("statusPanel").property("width") == width, "a longer text must not widen the column past the window"
    assert resets.mapToItem(None, 0, 0).x() + resets.property("width") <= ui.win.width()
    ui.js('usageData = ({ model: "sonnet", five_hour_used: 85, five_hour_low: true, five_hour_resets: "14:00" })')
    ui.wait(60)
    five, seven = ui.drawn("usageLeft_five_hour"), ui.drawn("usageLeft_seven_day")      # the rows are made again
    assert five.property("text") == "15% left" and not five.property("font").bold()
    assert ui.drawn("usageResets_five_hour").property("text") == "resets 14:00"
    assert seven.property("text") == "—"
    ui.js("usageData = JSON.parse('%s')" % keep.replace("\\", "\\\\").replace("'", "\\'"))
    assert ui.warnings == []


def test_the_right_column_fits_inside_the_window(ui):
    panel = ui.find("statusPanel")
    assert panel.mapToItem(None, 0, 0).x() + panel.property("width") <= ui.win.width()
    for item in ui.seen():
        if item.property("visible") and isinstance(item.property("text"), str) and item.property("text"):
            assert item.mapToItem(None, 0, 0).x() + item.property("width") <= ui.win.width() + 0.5, item.property("text")


# ── about you, notifications, backups, readable help ────────────────────────
def test_new_options_are_loaded_and_saved(ui):
    dialog = ui.find("optDialog")
    ui.bridge.saveOptions({**ui.bridge.options(), "about_right_to_work": "EU citizen", "about_start": "one month",
                           "notifications": False, "keep_backups": 25})
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    assert ui.find("notifySw").property("checked") is False and ui.find("keepSpin").property("value") == 25
    ui.js("close()", dialog)
    _until_closed(ui, "optDialog")
    ui.js("aboutDialog.show()")
    _until_open(ui, "aboutDialog")
    assert ui.find("rightField").property("text") == "EU citizen" and ui.find("startField").property("text") == "one month"
    ui.js("close()", ui.find("aboutDialog"))
    _until_closed(ui, "aboutDialog")
    ui.bridge.saveOptions({**ui.bridge.options(), "about_right_to_work": "", "about_start": "", "notifications": True, "keep_backups": 10})
    assert ui.warnings == []


def test_help_marks_key_words(ui):
    text = ui.js("topics.map(function (t) { return t.lines.join(' '); }).join(' ')", ui.find("helpDialog"))
    for word in ("Run search", "Scan email", "Mark applied", "strong", "stretch", "Not interested", "recovery key"):
        assert f"<b>{word}</b>" in text, word
    assert text.count("<b>") == text.count("</b>") and "<b><b>" not in text
    source = qml_source()
    assert "textFormat: Text.StyledText" in source


def test_every_dialog_closes_with_one_shared_button(ui):
    """The ✕ of every dialog is CloseButton: Tab reaches it, it has a name for VoiceOver, and it closes its window."""
    ui_dir = ROOT / "ui_qt"
    for path in ui_dir.glob("*Dialog.qml"):
        if path.name != "LimitDialog.qml":                           # the limit notice has one big Close button and Esc
            assert path.read_text(encoding="utf-8").count("CloseButton {") == 1, path.name
    shell = (ui_dir / "CloseButton.qml").read_text(encoding="utf-8")
    assert 'Accessible.name: "Close"' in shell and "visualFocus" in shell
    dialog = ui.find("helpDialog")
    ui.js("helpDialog.open()")
    _until_open(ui, "helpDialog")
    buttons = [o for o in dialog.findChildren(QObject) if o.metaObject().className().startswith("CloseButton")]
    assert len(buttons) == 1 and buttons[0].property("focusPolicy") != Qt.NoFocus
    buttons[0].clicked.emit()
    _until_closed(ui, dialog)
    assert dialog.property("visible") is False
    from PySide6.QtTest import QTest                                  # Space on the ✕ of a window that asks first: clean, so it closes
    options = ui.find("optDialog")
    _open(ui, options)
    close = next(o for o in options.findChildren(QObject) if o.metaObject().className().startswith("CloseButton"))
    ui.win.requestActivate()
    close.forceActiveFocus()
    QTest.keyClick(ui.win, Qt.Key_Space)
    _until_closed(ui, options)
    assert options.property("visible") is False and ui.warnings == []


def test_every_dialog_has_the_same_title_header_and_footer(ui):
    """Titles were 16 or 17 pixels, footers had 12 or 14 pixels of margin: each dialog now uses the one shell."""
    ui_dir = ROOT / "ui_qt"
    for path in ui_dir.glob("*Dialog.qml"):
        if path.name == "LimitDialog.qml":                                # the limit notice is a warning card, not a dialog shell
            continue
        text = path.read_text(encoding="utf-8")
        assert text.count("DialogHeader {") == 1 and text.count("DialogTitle {") == 1, path.name
        assert "DialogFooter {" in text or path.name == "TableDialog.qml", path.name        # the list has no footer row
        assert not re.search(r"RowLayout \{[^}\n]*Layout\.margins: 1[246]\b", text), f"{path.name}: a copied header or footer row"
    title = (ui_dir / "DialogTitle.qml").read_text(encoding="utf-8")
    assert "Text.PlainText" in title and "Text.Wrap" in title                # a company's name is never markup, and it wraps
    dialog = ui.find("optDialog")
    _open(ui, dialog)
    titles = [o for o in dialog.findChildren(QObject) if o.metaObject().className().startswith("DialogTitle")]
    footers = [o for o in dialog.findChildren(QObject) if o.metaObject().className().startswith("DialogFooter")]
    assert len(titles) == 1 and titles[0].property("font").pixelSize() == 17 and titles[0].property("text") == "Options"
    assert len(footers) == 1 and footers[0].property("spacing") == 6
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
    assert ui.warnings == []


def test_the_usage_bar_shows_what_is_left_and_a_reset_asks_again(ui, monkeypatch):
    """The card is titled USAGE LEFT but the bar drew what was used: a used-up window showed a full green bar."""
    import json
    import time
    from datetime import datetime
    keep = ui.js("JSON.stringify(usageData)")
    try:
        ui.js('usageData = ({ model: "sonnet", five_hour_used: 100, five_hour_low: true, five_hour_resets: "01:20", seven_day_used: 25, next_reset_in: 0 })')
        bars = {k: next(i for i in ui.seen("statusPanel") if i.objectName() == "usageBar_" + k) for k in ("five_hour", "seven_day")}
        track = bars["seven_day"].parentItem().property("width")
        assert bars["five_hour"].property("width") == 0, "nothing left: an empty bar"
        assert abs(bars["seven_day"].property("width") - 0.75 * track) < 1, "three quarters left: three quarters of the bar"
        def line(key="five_hour"):           # the rows are made again with each new set of figures
            return next(i for i in ui.seen("statusPanel") if i.objectName() == "usageResets_" + key).property("text")
        assert line() == "resets 01:20"
        assert line("seven_day") == "", "a window whose reset is not known says nothing"
        ui.js('usageData = ({ model: "sonnet", five_hour_used: 40, five_hour_resets: "18:00", five_hour_held_until: "03 Nov 09:00", '
              'seven_day_used: 100, seven_day_low: true, seven_day_resets: "03 Nov 09:00", next_reset_in: 0 })')
        assert line() == "resets 18:00\nback with 7-day: 03 Nov 09:00", "the used-up week: both times"
        assert line("seven_day") == "resets 03 Nov 09:00"
        ui.js('usageData = ({ model: "sonnet", five_hour_used: 40, five_hour_resets: "18:00", seven_day_used: 10, seven_day_resets: "03 Nov 09:00" })')
        assert line() == "resets 18:00" and line("seven_day") == "resets 03 Nov 09:00", "each its own time, also with much left"
        ui.js('usageData = ({ model: "sonnet", five_hour_used: null, seven_day_used: 25, next_reset_in: 0 })')
        assert line() == "", "after a reset: no old date, the card asks again"
        unknown = next(i for i in ui.seen("statusPanel") if i.objectName() == "usageBar_five_hour")
        assert unknown.property("visible") is False, "not known: no fill, so it never looks used up"
        left = next(i for i in ui.seen("statusPanel") if i.objectName() == "usageLeft_five_hour")
        assert left.property("text") == "—", "not known since the reset, not a guessed 100%"
        tick = ui.find("usageTick")
        assert tick.property("running") is True and tick.property("interval") == 60000, "looks every minute while shown"
        ui.js("usageBusy = false")
        from jobhelper import config
        before = config.USAGE_JSON.read_bytes() if config.USAGE_JSON.exists() else None
        try:
            fresh = datetime.now().isoformat(timespec="seconds")
            config.USAGE_JSON.write_text(json.dumps({"last_rate_limit": {"at": fresh, "info": {"unifiedWindows": {
                "five_hour": {"utilization": 0.3, "resetsAt": time.time() + 3600}}}}}), encoding="utf-8")
            assert ui.js("usageTick.triggered(); usageBusy") is False, "fresh figures: no question to Claude"
            ui.js("appRunning = true")
            assert ui.js("refreshUsageNow(); usageBusy") is False, "never during a run: the run brings its own figures"
            ui.js("appRunning = false")
            # later the old flag is out of date: the timer reads the figures again before it decides
            old = datetime.fromtimestamp(time.time() - 2 * 3600).isoformat(timespec="seconds")
            config.USAGE_JSON.write_text(json.dumps({"last_rate_limit": {"at": old, "info": {"unifiedWindows": {
                "five_hour": {"utilization": 0.3, "resetsAt": time.time() + 3600}}}}}), encoding="utf-8")
            ui.js("usageData = ({ model: 'sonnet', five_hour_used: 30, should_refresh: false }); usageBusy = false")
            assert ui.js("usageTick.triggered(); usageBusy") is True
            assert _until_true(ui, lambda: ui.js("usageBusy") is False)
            asked = []
            monkeypatch.setattr(qt_bridge.Bridge, "_ping_usage", lambda self: asked.append(True) or self.usageReady.emit())
            ui.js("usageBusy = true; startUp.triggered()")
            assert ui.js("usageBusy") is True and asked == [], "start-up goes through refreshUsageNow: no second question"
            ui.js("usageBusy = false; startUp.triggered()")
            assert _until_true(ui, lambda: asked == [True]) and _until_true(ui, lambda: ui.js("usageBusy") is False)
            ui.win.activeChanged.emit()                                         # back to the front with old figures: it asks
            assert ui.js("usageBusy") is True
            assert _until_true(ui, lambda: ui.js("usageBusy") is False)
            ui.win.showMinimized()
            assert _until_true(ui, lambda: ui.js("usageTick.running") is False), "minimised: no looking"
            ui.win.showNormal()
            assert _until_true(ui, lambda: ui.js("usageTick.running") is True)
            assert ui.js("usageReset.triggered(); usageBusy") is True, "a reset time passed: the card asks too"
            assert _until_true(ui, lambda: ui.js("usageBusy") is False)
            ui.js("appRunning = true")                                          # a run ends: first runFinished, then running false
            ui.bridge.runFinished.emit("search", "Done: 2 new jobs.")
            assert _until_true(ui, lambda: ui.js("ticker.text") == "Done: 2 new jobs.")
            assert ui.js("usageBusy") is False, "still running when it reports: no question yet"
            ui.bridge.runningChanged.emit(False)
            assert ui.js("appRunning") is False and ui.js("usageBusy") is True, "stopped: now it asks"
            assert _until_true(ui, lambda: ui.js("usageBusy") is False)
        finally:
            if before is None:
                config.USAGE_JSON.unlink(missing_ok=True)
            else:
                config.USAGE_JSON.write_bytes(before)
    finally:
        ui.js("appRunning = false")
        ui.js('resultFade.stop(); runResult = ""; runMode = ""; runProgress = 0; ticker.text = ""')
        ui.js("usageData = JSON.parse('%s')" % keep.replace("\\", "\\\\").replace("'", "\\'"))


def test_an_estimate_becomes_your_own_figure_with_one_press(ui):
    """The estimates could not be changed where they stood: the role had to be typed again under "A different figure for"."""
    import json
    dialog = ui.find("aboutDialog")
    start = ui.bridge.options()
    assert ui.bridge.saveOptions({**start, "where": "Prague", "country": "", "wanted_roles": ["Junior Python Developer"]})["ok"] is True
    try:
        ui.js("aboutDialog.show()")
        _until_open(ui, "aboutDialog")
        def drawn(name):                                          # rows of a Repeater: drawn, not found
            return next((i for i in ui.seen("salaryEstimates") if i.objectName() == name), None)
        assert _until_true(ui, lambda: drawn("estimateChange_0") is not None and drawn("estimateChange_0").property("visible") is True)
        assert "Change makes one your own figure" in ui.find("salaryNote").property("text")
        drawn("estimateChange_0").clicked.emit()
        assert _until_true(ui, lambda: ui.js("payModel.count", dialog) == 1)
        row = json.loads(ui.js("JSON.stringify(payModel.get(0))", dialog))
        assert row["role"] == "Junior Python Developer" and row["amount"] > 0, "the role and the estimate, ready to change"
        assert drawn("estimate_0").property("text") == "your figure below" and drawn("estimateChange_0").property("visible") is False
        assert json.loads(ui.js("JSON.stringify(aboutDialog.collect())", dialog))["salary_by_role"][0]["role"] == "Junior Python Developer"
        czk = row["amount"]
        # a role edited in the list: the estimate offers Change again
        ui.js('payModel.setProperty(0, "role", "support")', dialog)
        assert _until_true(ui, lambda: drawn("estimateChange_0").property("visible") is True)
        # in euros the figure is the estimate said in euros, not 58 000 EUR
        ui.js('payModel.clear(); currencyCombo.currentIndex = currencyCombo.find("EUR")', dialog)
        drawn("estimateChange_0").clicked.emit()
        assert _until_true(ui, lambda: ui.js("payModel.count", dialog) == 1)
        euros = json.loads(ui.js("JSON.stringify(payModel.get(0))", dialog))["amount"]
        assert 0 < euros < czk / 10, (czk, euros)
        # a refused Change is said next to the estimates, in one red line
        ui.js('payModel.clear(); for (var i = 0; i < 20; i++) payModel.append({ role: "role " + i, amount: 1000 })', dialog)
        drawn("estimateChange_0").clicked.emit()
        assert _until_true(ui, lambda: "up to 20 kinds of role" in ui.js("aboutDialog.estimateErr", dialog))
        assert ui.js("aboutDialog.payErr", dialog) == ""
        ui.find("salarySpin").setProperty("value", 60000)                         # a figure of your own: no estimates, no red line about them
        assert _until_true(ui, lambda: drawn("estimateErr").property("visible") is False)
    finally:
        ui.js("payModel.clear(); aboutDialog.confirmClose = true; close()", dialog)
        _until_closed(ui, "aboutDialog")
        ui.bridge.saveOptions(start)
    assert ui.warnings == []


def test_options_ask_the_back_end_rules_and_never_lose_a_change_unseen(ui):
    """Hands-on check and window review (H1, H2, H4, F3, F4, H6, H8): a token the search refuses was accepted and then
    dropped at Save as "saved"; "Narnia" was a country; a 150-character role came back at Save under the key "queries";
    9999 in Max job age was cut to 3650 as the window closed; footer lines stayed after the fault was put right."""
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    try:
        assert ui.js('optDialog.addCompany("Acme", "greenhouse", "acme.io")', dialog) is False
        assert ui.js("coErr", dialog).startswith("Use the short name"), "the rule the search uses (H1)"
        assert "is not a country the app knows" in ui.js('optDialog.countryProblem("Narnia")', dialog), "F3"
        assert ui.js('optDialog.countryProblem("Czech Republic")', dialog) == ""
        assert ui.js('optDialog.addRole("data " + "a".repeat(150))', dialog) is False and "up to 100 characters" in ui.js("roleErr", dialog), "H2"
        ui.js('ageSpin.contentItem.text = "9999"', dialog)
        ui.js("optSaveBtn.clicked()", dialog)
        assert dialog.property("opened") is True and "“Max job age” takes 0 to 3650; you typed 9999" in ui.js("optErr", dialog), "H4"
        ui.js("ageSpin.contentItem.text = '10'; ageSpin.value = 10", dialog)
        ui.js('cityCombo.editText = ""', dialog)
        ui.js("optSaveBtn.clicked()", dialog)
        assert ui.js("optErr", dialog) == "Enter a city (e.g. Prague) before saving."
        ui.js('cityCombo.editText = "Prague"', dialog)
        assert ui.js("optErr", dialog) == "", "the fault is put right: its line goes (F4)"
        ui.js("tryClose()", dialog)
        assert ui.js("confirmClose", dialog) is True
        ui.js('cityCombo.editText = "Brno"', dialog)
        assert ui.js("confirmClose", dialog) is False, "an edit after the prompt: closing asks again (H6)"
        ui.js("optCancelBtn.clicked()", dialog)
        assert ui.js("confirmClose", dialog) is True and dialog.property("opened") is True, "Cancel asks once, as ✕ and Esc do (H8)"
    finally:
        ui.js("confirmClose = true; close()", dialog)
        _until_closed(ui, dialog)
        ui.js("optsData = bridge.options()")
    assert ui.warnings == []


def test_option_messages_name_what_the_window_shows(isolate_data):
    from jobhelper import ui_api
    api = ui_api.Api()
    result = api.save_options({**api.options(), "queries": ["data " + "a" * 150]})
    assert result["ok"] is False and "“Search roles”" in result["msg"] and "queries" not in result["msg"], "H2"
    assert api.save_options({**api.options(), "where": "x" * 90})["msg"].startswith("“City”"), "H7"


def test_options_number_and_list_faults_are_said_once_and_go_when_fixed(ui):
    """Review of the Options fixes: a fixed number kept its red line; two boxes that are no options blocked Save; a full
    list was refused only at Save."""
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    try:
        ui.js('cityCombo.editText = "Prague"', dialog)
        ui.js('shelfSpin.contentItem.text = "99999"', dialog)
        assert ui.js("optDialog.numberProblem()", dialog) == "", "the tidy and scan-back boxes are no options"
        ui.js('shelfSpin.contentItem.text = "30"', dialog)
        ui.js('ageSpin.contentItem.text = "9999"', dialog)
        ui.js("optErr = optDialog.numberProblem()", dialog)
        assert "you typed 9999" in ui.js("optErr", dialog) and ui.js("ageSpin.flagged", dialog) is True and ui.js("ageSpin.note", dialog) == ""
        ui.js("ageSpin.contentItem.text = '9998'; ageSpin.contentItem.textEdited()", dialog)       # another wrong number
        assert "you typed 9998" in ui.js("optErr", dialog) and ui.js("ageSpin.note", dialog) == "", "one message, not two"
        ui.js("ageSpin.contentItem.text = '10'; ageSpin.contentItem.textEdited()", dialog)
        assert ui.js("optErr", dialog) == "" and ui.js("ageSpin.flagged", dialog) is False, "fixed: the line goes"
        ui.js("rolesModel.clear(); for (var i = 0; i < win.limits.list_max; i++) rolesModel.append({ text: 'data analyst ' + i })", dialog)
        assert ui.js('optDialog.addRole("software tester")', dialog) is False and "holds up to 60" in ui.js("roleErr", dialog)
        ui.js("skipTags.setAll(Array.apply(null, Array(win.limits.list_max)).map(function (_, i) { return 'word' + i; }))", dialog)
        assert ui.js('skipTags.add("intern")', dialog) is False and "holds up to 60" in ui.js("skipTags.err", dialog)
    finally:
        ui.js("confirmClose = true; close()", dialog)
        _until_closed(ui, dialog)
        ui.js("optsData = bridge.options()")
    assert ui.warnings == []


def test_the_weekly_run_and_remote_countries_ask_before_a_change_is_lost(ui, monkeypatch):
    """Hands-on check F5, F6, F7 and window review H3: Esc, ✕ and Cancel threw away a change; an empty hour counted as
    00; a wrong time stopped the weekly run being switched off."""
    from PySide6.QtTest import QTest
    from jobhelper import schedule
    sent = []
    monkeypatch.setattr(schedule, "write_schedule", lambda *a: sent.append(a) or {"ok": True})
    sched = ui.find("schedDialog")
    ui.js("schedData = ({ enabled: true, weekday: 1, hour: 9, minute: 0, label: 'Mon 09:00' })")
    _open(ui, sched, 500)
    try:
        typing = "hourField.children.filter(function (c) { return c.objectName === 'timeInput'; })[0]"
        ui.js("hourField.text = '7'; " + typing + ".textEdited()", sched)     # typed, as a person does: the field is in typing mode
        assert ui.js("hourField.value", sched) == 7
        ui.win.requestActivate()
        QTest.keyClick(ui.win, Qt.Key_Escape)
        assert _until_true(ui, lambda: "did not save" in ui.js("schedErr", sched)) and sched.property("opened") is True, "F6"
        assert ui.js("schedCancelBtn.text", sched) == "Discard changes"
        QTest.keyClick(ui.win, Qt.Key_Escape)                           # asked once: the second Esc discards
        _until_closed(ui, sched)
        _open(ui, sched, 500)
        assert ui.js("hourField.text", sched) == "09" and ui.js("timeErr", sched) == "", "reopened as saved, whatever was typed"
        ui.js("minField.text = ''", sched)
        assert ui.js("timeErr", sched) == "Enter the minute, 0 to 59.", "an empty minute is no 00 (F7)"
        ui.js("minField.children[minField.children.length - 1].editingFinished()", sched)
        assert ui.js("minField.text", sched) == "" and ui.js("timeErr", sched) != "", "leaving the box keeps it empty"
        ui.js("schedSaveBtn.clicked()", sched)
        assert sent == [] and sched.property("opened") is True, "nothing is sent while a box is empty"
        ui.js("minField.reset(0); hourField.text = '25'; hourField.value = 25", sched)
        ui.js("en = false; schedDialog.changed()", sched)
        assert ui.js("timeErr", sched) == "", "switched off: the time does not matter (H3)"
        ui.js("schedSaveBtn.clicked()", sched)
        assert sent and sent[-1][0] is False and sent[-1][2] == 9, "the saved time is sent, never the wrong one"
    finally:
        ui.js("confirmClose = true; close()", sched)
        _until_closed(ui, sched)
        ui.js("schedData = bridge.weeklySchedule()")
    picker = ui.find("remoteDialog")
    ui.js('remoteDialog.show(["germany"], "czechia")')
    _until_open(ui, "remoteDialog")
    try:
        ui.js('remoteDialog.toggle("austria")')
        ui.js("remoteCancelBtn.clicked()", picker)
        assert picker.property("opened") is True and "did not press Done" in ui.js("err", picker), "a tick is not lost unasked (F5)"
        ui.js("remoteCancelBtn.clicked()", picker)
        _until_closed(ui, "remoteDialog")
    finally:
        ui.js("confirmClose = true; close()", picker)
        _until_closed(ui, "remoteDialog")
    assert ui.warnings == []


def test_the_weekly_run_save_never_reaches_the_real_launch_agent_in_a_test_copy(ui):
    """F17 from the window: the tests run with JOBHELPER_HOME, so Save is refused with the reason."""
    sched = ui.find("schedDialog")
    ui.js("schedData = ({ enabled: true, weekday: 1, hour: 9, minute: 0, label: 'Mon 09:00' })")
    _open(ui, sched, 500)
    try:
        ui.js("schedSaveBtn.clicked()", sched)
        assert sched.property("opened") is True and "JOBHELPER_HOME" in ui.js("schedErr", sched)
    finally:
        ui.js("confirmClose = true; close()", sched)
        _until_closed(ui, sched)
        ui.js("schedData = bridge.weeklySchedule()")
    assert ui.warnings == []


def test_esc_in_a_welcome_email_field_leaves_the_field(ui):
    """Window review H8: Esc did nothing inside the welcome card's email fields."""
    from PySide6.QtTest import QTest
    ui.js("welcome.openCard()")
    welcome = ui.find("welcome")
    try:
        welcome.setProperty("editEmail", True)
        ui.js("wEmail.forceActiveFocus()", welcome)
        assert ui.js("wEmail.activeFocus", welcome) is True
        ui.win.requestActivate()
        QTest.keyClick(ui.win, Qt.Key_Escape)
        assert _until_true(ui, lambda: ui.js("wEmail.activeFocus", welcome) is False), "Esc leaves the field"
    finally:
        welcome.setProperty("editEmail", False)
        ui.js("welcome.finish()")
    assert ui.warnings == []
