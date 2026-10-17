"""Notifications, clean-up of old backups and logs, hand edits during a run, rule examples."""
from pathlib import Path

import pytest

from jobhelper import config, cover_letter, cv_tailor, housekeeping, notify, store, ui_api, vault

ROOT = Path(__file__).resolve().parent.parent


# ── notifications ───────────────────────────────────────────────────────────
@pytest.fixture
def sent(isolate_data, monkeypatch):
    calls = []
    monkeypatch.setattr(notify.sys, "platform", "darwin")
    monkeypatch.setattr(notify, "_run", calls.append)
    return calls


def test_notification_is_sent_with_safe_quoting(sent):
    assert notify.send('3 new replies from "Acme"\nand others', "Email scan finished") is True
    cmd = sent[0]
    assert cmd[0] == "osascript" and cmd[1] == "-e"
    assert cmd[2] == 'display notification "3 new replies from \\"Acme\\" and others" with title "JobHelper" subtitle "Email scan finished"'


def test_notifications_can_be_switched_off(sent):
    ui_api.Api().save_options({"notifications": False})
    assert notify.send("anything") is False and sent == []
    ui_api.Api().save_options({"notifications": True})
    assert notify.send("anything") is True


def test_nothing_is_sent_off_macos_or_without_text(sent, monkeypatch):
    assert notify.send("") is False
    monkeypatch.setattr(notify.sys, "platform", "linux")
    assert notify.send("hello") is False and sent == []


@pytest.mark.parametrize("companies, text", [
    ([], ""), (["SAP"], "Interview invitation from SAP"), (["SAP", "SAP"], "Interview invitation from SAP"),
    (["SAP", "EY"], "Interview invitations from SAP and 1 other"), (["SAP", "EY", "PwC"], "Interview invitations from SAP and 2 others"),
])
def test_invitation_wording(companies, text):
    assert notify.invites_text(companies) == text


def test_inbox_scan_reports_who_invited_you(isolate_data, monkeypatch):
    from jobhelper import agent5_responses, email_client, llm
    mails = [{"msg_id": f"<{n}@x>", "date": "Mon, 5 Oct 2026 10:00:00 +0200", "sender": "hr@x.com", "subject": "s", "body": "b",
              "was_html_only": False} for n in range(3)]
    replies = iter([{"is_response": True, "stage": "interview", "company": "SAP"},
                    {"is_response": True, "stage": "rejection", "company": "EY"},
                    {"is_response": True, "stage": "assessment", "company": "PwC"}])
    monkeypatch.setattr(email_client, "fetch_recent", lambda days=None: mails)
    monkeypatch.setattr(email_client, "looks_like_application", lambda *a, **k: True)
    monkeypatch.setattr(email_client, "match_job", lambda *a, **k: None)
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: next(replies))
    stats = agent5_responses.process_inbox([])
    assert stats["invites"] == ["SAP", "PwC"] and stats["rejections"] == 1


# ── clean-up ────────────────────────────────────────────────────────────────
def _backups(n):
    root = vault.backups_dir()
    root.mkdir(parents=True, exist_ok=True)
    names = []
    for i in range(n):
        name = f"backup_202610{i + 1:02d}_120000"
        if i % 2:
            (root / (name + ".json.enc")).write_bytes(b"x"); names.append(name + ".json.enc")
        else:
            (root / name).mkdir(); (root / name / "jobs.json.enc").write_bytes(b"x"); names.append(name)
    return names


def test_only_the_newest_backups_are_kept(isolate_data):
    names = _backups(7)
    removed = housekeeping.prune_backups(keep=3)
    assert sorted(removed) == sorted(names[:4])                                   # the four oldest
    assert sorted(p.name for p in vault.backups_dir().iterdir()) == sorted(names[4:])


def test_dry_run_and_keep_all_delete_nothing(isolate_data):
    names = _backups(5)
    assert len(housekeeping.prune_backups(keep=2, dry_run=True)) == 3
    assert housekeeping.prune_backups(keep=0) == [] and housekeeping.prune_backups(keep=50) == []
    assert len(list(vault.backups_dir().iterdir())) == len(names)


def test_side_folders_are_not_counted_as_backups_and_keep_their_newest_files(isolate_data, monkeypatch):
    _backups(2)
    monkeypatch.setattr(housekeeping, "SIDE_FOLDERS", {"letter_versions": 2})
    side = vault.backups_dir() / "letter_versions"
    side.mkdir()
    for i in range(5):
        (side / f"Letter.2026100{i + 1}_120000.docx.enc").write_bytes(b"x")
    assert housekeeping.prune_backups(keep=1) == ["backup_20261001_120000"]
    assert side.is_dir()                                                           # never removed as a whole
    assert housekeeping.prune_side_folders() == 3
    assert sorted(p.name for p in side.iterdir()) == ["Letter.20261004_120000.docx.enc", "Letter.20261005_120000.docx.enc"]


def test_logs_keep_their_last_lines(isolate_data):
    config.ensure_dirs()
    (config.DATA_DIR / "weekly_jobhelper.log").write_text("\n".join(f"line {i}" for i in range(1000)) + "\n", encoding="utf-8")
    (config.DATA_DIR / "short.log").write_text("one\ntwo\n", encoding="utf-8")
    assert housekeeping.trim_logs(lines=100) == 1
    kept = (config.DATA_DIR / "weekly_jobhelper.log").read_text(encoding="utf-8").splitlines()
    assert len(kept) == 100 and kept[0] == "line 900" and kept[-1] == "line 999"
    assert (config.DATA_DIR / "short.log").read_text(encoding="utf-8") == "one\ntwo\n"


def test_live_data_is_never_touched_and_the_limit_comes_from_options(isolate_data):
    config.ensure_dirs()
    store.save_jobs([store.new_job(id="1", title="Dev", company="A")])
    _backups(6)
    ui_api.Api().save_options({"keep_backups": 4})
    report = housekeeping.run()
    assert len(report["backups_removed"]) == 2 and store.load_jobs()[0]["id"] == "1"
    assert vault.protect_all()["housekeeping"]["backups_removed"] == []           # also runs at every start


# ── a hand edit while a search or scan is running ───────────────────────────
def test_edit_during_a_run_is_not_overwritten_when_the_run_saves(isolate_data):
    config.ensure_dirs()
    store.save_jobs([store.new_job(id="a", title="Dev", company="Acme", status="waiting"),
                     store.new_job(id="b", title="QA", company="Beta", status="letter_ready")])
    api = ui_api.Api()
    running = store.load_jobs()                 # what the run loaded when it started
    api.live = running
    assert api.set_status("a", "rejected")["ok"] and api.dismiss_job("b")["ok"] and api.set_apply_date("a", "2026-10-01")["ok"]
    running[0]["match_reason"] = "the run keeps working on its copy"
    store.save_jobs(running)                    # ... and saves at the end
    saved = {j["id"]: j for j in store.load_jobs()}
    assert saved["a"]["status"] == "rejected" and saved["a"]["date_applied"] == "2026-10-01"
    assert saved["b"]["status"] == store.NOT_INTERESTED
    assert saved["a"]["match_reason"] == "the run keeps working on its copy"       # the run's own work is kept too


def test_without_a_run_edits_only_go_to_disk(isolate_data):
    config.ensure_dirs()
    store.save_jobs([store.new_job(id="a", title="Dev", company="Acme", status="waiting")])
    api = ui_api.Api()
    assert api.live is None and api.set_status("a", "interview")["ok"]
    assert store.load_jobs()[0]["status"] == "interview"


# ── the app works for somebody else's CV ────────────────────────────────────
def test_example_rule_files_are_generic_and_usable(isolate_data):
    for name in ("cv_adaptation_instruction.example.md", "cover_letter_instruction.example.md"):
        text = (ROOT / "examples" / name).read_text(encoding="utf-8")
        assert "{{name}}" in text or "{{first_name}}" in text
        assert "—" not in text
    config.ensure_dirs()
    config.CV_INSTRUCTION.write_text((ROOT / "examples" / "cv_adaptation_instruction.example.md").read_text(encoding="utf-8"), encoding="utf-8")
    config.LETTER_INSTRUCTION.write_text((ROOT / "examples" / "cover_letter_instruction.example.md").read_text(encoding="utf-8"), encoding="utf-8")
    ui_api.Api().save_options({"where": "Berlin", "about_right_to_work": "EU citizen", "about_start": ""})
    cv = "Jane Doe\nJunior Data Analyst\nSQL, Python"
    cv_rules, letter_rules = cv_tailor.load_rules(cv), cover_letter.load_rules(cv)
    assert "Jane Doe's master CV" in cv_rules and "## 4. How to adapt" in cv_rules and "{{" not in cv_rules
    assert "written by Jane" in letter_rules and "based in Berlin" in letter_rules and "EU citizen" in letter_rules
    assert "can start: (not stated)" in letter_rules and "{{" not in letter_rules
    assert "Kubernetes" in cv_tailor.unverified_terms(cv)                          # the never-claim list is read from the file


def test_letter_prompt_carries_the_persons_own_facts_not_built_in_ones(isolate_data, monkeypatch):
    import shutil
    from jobhelper import llm
    template = ROOT / "tests" / "fixtures" / "letter_example_deutscheborse.docx"      # never your own template in data/
    config.ensure_dirs()
    shutil.copy2(template, config.LETTER_TEMPLATE)
    ui_api.Api().save_options({"where": "Berlin", "about_right_to_work": "EU citizen", "about_start": "one month"})
    prompts = []
    para = ("I am applying because the work matches what I build every day in my own projects. " * 5).strip()
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: prompts.append(prompt) or {
        "title_line": "Data Analyst", "paragraphs": [para] * 5, "role_short": "Analyst"})
    cover_letter.write(store.new_job(id="x", title="Data Analyst", company="Acme", description="SQL"),
                       "Jane Doe\nJunior Data Analyst\nSQL, Python", "JaneDoe_CV.docx")
    assert "Right to work: EU citizen" in prompts[0] and "Can start: one month" in prompts[0] and "Based in: Berlin" in prompts[0]
    assert "Czech Republic" not in prompts[0]
    assert sorted(p.name for p in config.LETTERS_DIR.glob("*.docx")) == ["JaneDoe_CoverLetter_Acme_Analyst.docx"]


def test_tests_cannot_show_a_real_notification(monkeypatch):
    """The suite runs searches and scans with made-up data; none of that may reach the desktop."""
    import subprocess
    monkeypatch.setattr(notify.sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("a test reached osascript"))
    assert notify.send("made-up result", "Search finished") is True


# ── the installed app shows its own notifications (macos/Notify.swift) ─────
class FakeLibrary:
    """What macos/Notify.swift answers: 1 shown, 2 waiting for the first answer, 0 turned off, -1 refused."""

    def __init__(self, answer=1, permission=1):
        self.answer, self.allowed, self.shown = answer, permission, []

    def show(self, title: bytes, body: bytes) -> int:
        self.shown.append((title.decode(), body.decode()))
        return self.answer

    def permission(self) -> int:
        return self.allowed


@pytest.fixture
def app_library(isolate_data, monkeypatch):
    library = FakeLibrary()
    monkeypatch.setattr(notify.sys, "platform", "darwin")
    monkeypatch.setattr(notify.AppNotifier, "of_the_app", classmethod(lambda cls: cls(library.show, library.permission)))
    monkeypatch.setattr(notify, "_run", lambda cmd: pytest.fail("the app's own way is used: no osascript"))
    return library


def test_the_installed_app_shows_its_notifications_itself(app_library):
    assert notify.send('Tomorrow at 11:30:\ninterview · "BRIGHTLINE"', "Reminder") is True
    assert app_library.shown == [("Reminder", 'Tomorrow at 11:30: interview · "BRIGHTLINE"')]
    notify.send("No headline given")
    assert app_library.shown[-1] == ("JobHelper", "No headline given")         # the app's name stands in for a headline


@pytest.mark.parametrize("answer, handed", [(1, True), (2, True), (0, False), (-1, False)])
def test_what_macos_answered_is_reported(app_library, answer, handed):
    app_library.answer = answer                                       # 2: macOS still waits for the person's first answer
    assert notify.send("3 new jobs", "Search finished") is handed


@pytest.mark.parametrize("code, said", [(1, "allowed"), (0, "off"), (2, "not asked"), (-1, "unknown"), (7, "unknown")])
def test_the_permission_in_system_settings_is_read_in_words(app_library, code, said):
    app_library.allowed = code
    assert notify.notifier().permission() == said


def test_outside_the_installed_app_the_plain_way_is_used(isolate_data, monkeypatch):
    monkeypatch.undo()                                                # the real of_the_app: not frozen, so no library
    monkeypatch.setattr(config, "DATA_DIR", isolate_data)
    assert notify.AppNotifier.of_the_app() is None
    assert isinstance(notify.notifier(), notify.ScriptNotifier) and notify.ScriptNotifier().permission() == "unknown"
    monkeypatch.setattr(notify.sys, "frozen", True, raising=False)     # a built app without the library: the plain way too
    monkeypatch.setattr(notify.sys, "executable", str(isolate_data / "JobHelper.app" / "Contents" / "MacOS" / "JobHelper"))
    assert notify.AppNotifier.of_the_app() is None


def test_the_hidden_helper_app_is_gone():
    """A script app could not ask macOS for permission, so every notification was kept without being shown."""
    assert not hasattr(notify, "ensure_app") and not hasattr(notify, "_APPLET")
    swift = (ROOT / "macos" / "Notify.swift").read_text(encoding="utf-8")
    assert '@_cdecl("jobhelper_notify")' in swift and '@_cdecl("jobhelper_notify_permission")' in swift
    assert "requestAuthorization" in swift and "willPresent" in swift


@pytest.mark.parametrize("new, ready, text", [
    (0, 0, "Nothing new this time. Your list is up to date."),
    (1, 0, "1 new job found. None scored high enough for a CV and letter."),
    (1, 1, "1 new job found. 1 is ready to send, with a CV and letter."),
    (40, 20, "40 new jobs found. 20 are ready to send, with a CV and letter."),
])
def test_search_notification_wording(new, ready, text):
    assert notify.search_text(new, ready) == text


def test_icon_files_exist_and_the_app_uses_them():
    assert (ROOT / "ui_qt" / "icon.png").stat().st_size > 10_000 and (ROOT / "ui_qt" / "icon.icns").read_bytes()[:4] == b"icns"
    assert "setWindowIcon" in (ROOT / "app_qt.py").read_text(encoding="utf-8")


# ── documents moved to the backup: never cleaned up unasked, removed by age on request ──
def _shelf_copy(name, days_old):
    from datetime import datetime, timedelta
    folder = vault.backups_dir() / housekeeping.SHELF
    folder.mkdir(parents=True, exist_ok=True)
    stamp = (datetime.now() - timedelta(days=days_old, minutes=5)).strftime("%Y%m%d_%H%M%S")
    path = folder / f"{name}.{stamp}.docx.enc"
    path.write_bytes(b"x" * 2048)
    return path


def test_moved_documents_survive_the_automatic_clean_up(isolate_data):
    config.ensure_dirs()
    old = _shelf_copy("L_old", 400)
    for i in range(4):
        (vault.backups_dir() / f"before_x_2026010{i}_120000").mkdir(parents=True)
    assert housekeeping.SHELF not in [p.name for p in housekeeping.backup_entries()]
    removed = housekeeping.prune_backups(keep=1)
    assert len(removed) == 3 and housekeeping.SHELF not in removed and old.exists()          # the folder is not "an old backup"
    ui_api.Api().save_options({"keep_backups": 1})
    housekeeping.run()
    assert old.exists()


def test_old_moved_documents_are_counted_and_removed_only_by_age(isolate_data):
    config.ensure_dirs()
    api = ui_api.Api()
    assert api.shelf_status() == {"ok": True, "files": 0, "bytes": 0, "old": 0, "old_bytes": 0, "days": 30}
    assert "No moved documents are older than 30 days" in api.tidy_shelf()["msg"]
    fresh, month, year = _shelf_copy("L_fresh", 2), _shelf_copy("L_month", 45), _shelf_copy("L_year", 400)
    (vault.backups_dir() / housekeeping.SHELF / ".DS_Store").write_bytes(b"")
    assert api.shelf_status(30) == {"ok": True, "files": 3, "bytes": 6144, "old": 2, "old_bytes": 4096, "days": 30}
    assert api.shelf_status(100)["old"] == 1 and api.shelf_status(7)["old"] == 2
    refused = api.tidy_shelf(30, 5)                                                         # the question named another number
    assert refused["ok"] is False and refused["changed"] is True and "it is now 2" in refused["msg"] and month.exists()
    assert api.tidy_shelf(100, 1) == {"ok": True, "removed": 1, "bytes": 2048} and not year.exists() and month.exists() and fresh.exists()
    trash = housekeeping.trash_dir(year)
    assert (trash / year.name).read_bytes() == b"x" * 2048                                  # moved to the Trash, not deleted
    (trash / month.name).write_bytes(b"an older file of the same name")                     # a name already in the Trash is not overwritten
    assert api.tidy_shelf(30) == {"ok": True, "removed": 1, "bytes": 2048} and not month.exists() and fresh.exists()
    assert (trash / month.name).read_bytes() == b"an older file of the same name" and len(list(trash.iterdir())) == 3
    assert api.tidy_shelf(7)["ok"] is False and fresh.exists()                               # nothing that young is ever removed


@pytest.mark.parametrize("days, words", [(6, "younger than 7 days are kept"), (0, "younger than 7 days"), (-3, "younger than 7 days"),
                                         (4000, "The most is 3650 days"), (30.5, "whole number of days"), ("30", "whole number of days"),
                                         (True, "whole number of days")])
def test_a_wrong_age_is_refused_with_the_reason(isolate_data, days, words):
    config.ensure_dirs()
    path = _shelf_copy("L", 400)
    api = ui_api.Api()
    assert words in api.shelf_status(days)["msg"] and words in api.tidy_shelf(days)["msg"] and path.exists()


def test_the_module_never_removes_copies_younger_than_the_minimum(isolate_data):
    config.ensure_dirs()
    young, old = _shelf_copy("L_young", 3), _shelf_copy("L_old", 20)
    assert housekeeping.tidy_shelf(0)["removed"] == [old.name] and young.exists()


def test_a_job_whose_copies_were_removed_no_longer_offers_to_put_them_back(isolate_data):
    from datetime import datetime, timedelta
    config.ensure_dirs()
    api = ui_api.Api()
    api.save_options({"threshold": 50})
    for name in ("old", "new"):
        (config.LETTERS_DIR / f"L_{name}.docx").write_bytes(b"letter")
        (config.TAILORED_CV_DIR / f"CV_{name}.docx").write_bytes(b"cv")
    store.save_jobs([store.new_job(id=n, title="Dev", company=n, match_score=20, status="letter_ready", cover_letter_file=f"L_{n}.docx",
                                   tailored_cv_file=f"CV_{n}.docx", description="x" * 900) for n in ("old", "new")])
    assert api.shelve_all_docs()["ok"] is True
    folder = vault.backups_dir() / housekeeping.SHELF
    record = store.find(store.load_jobs(), "old")["shelved"]
    stamp = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d_%H%M%S")
    jobs = store.load_jobs()
    for item in store.find(jobs, "old")["shelved"]["files"]:                                # make the copies of one job two months old
        aged = item["backup"].replace(item["backup"].split(".")[-3], stamp) if item["backup"].endswith(".enc") else item["backup"].replace(item["backup"].split(".")[-2], stamp)
        (folder / item["backup"]).rename(folder / aged)
        item["backup"] = aged
    store.save_jobs(jobs)
    assert record and api.shelf_status(30)["old"] == 2 and api.job_detail("old")["can_unshelve"] is True
    assert api.tidy_shelf(30, 2)["removed"] == 2
    assert "shelved" not in store.find(store.load_jobs(), "old") and api.job_detail("old")["can_unshelve"] is False
    assert api.job_detail("new")["can_unshelve"] is True and api.unshelve_docs("new")["ok"] is True      # the recent one is untouched


def test_without_a_trash_nothing_is_removed(isolate_data, monkeypatch):
    config.ensure_dirs()
    old = _shelf_copy("L_old", 90)
    monkeypatch.setattr(housekeeping, "trash_dir", lambda path: None)
    assert housekeeping.move_to_trash(old) is False
    got = ui_api.Api().tidy_shelf(30, 1)
    assert got == {"ok": False, "msg": "The Trash of this disk cannot be used, so nothing was removed."} and old.exists()

    def refuses(src, dst):
        raise PermissionError("not allowed")
    monkeypatch.setattr(housekeeping, "trash_dir", lambda path: old.parent.parent)
    monkeypatch.setattr(housekeeping.os, "rename", refuses)
    assert ui_api.Api().tidy_shelf(30, 1)["msg"] == "The old copies could not be moved to the Trash." and old.exists()


def test_the_trash_is_the_one_of_the_file_s_own_disk(tmp_path, monkeypatch):
    monkeypatch.undo()                                                # the real function; every path below is inside tmp_path
    home, other = tmp_path / "home", tmp_path / "disk"
    (home / ".Trash").mkdir(parents=True); (home / "data").mkdir(); (other / "project" / "data").mkdir(parents=True); (other / ".Trashes").mkdir()
    a, b = home / "data" / "a.enc", other / "project" / "data" / "b.enc"
    a.write_bytes(b"a"); b.write_bytes(b"b")
    monkeypatch.setattr(housekeeping.Path, "home", classmethod(lambda cls: home))
    inside = str(other.resolve())
    monkeypatch.setattr(housekeeping, "_disk", lambda p: 2 if str(p).startswith(inside) else 1)      # "disk" is another disk
    monkeypatch.setattr(housekeeping.os, "getuid", lambda: 501)
    assert housekeeping.trash_dir(a) == home / ".Trash"
    assert housekeeping.trash_dir(b) == other.resolve() / ".Trashes" / "501" and (other / ".Trashes" / "501").is_dir()     # made on first use
    (other / ".Trashes" / "501").rmdir(); (other / ".Trashes").rmdir()
    assert housekeeping.trash_dir(b) is None                                                                    # a disk without a Trash


# ── errors the app carries on after are written down ────────────────────────
def test_trouble_is_noted_without_secrets_and_never_fails(isolate_data, monkeypatch):
    from jobhelper import trouble
    trouble.note("reading a page", ValueError("bad answer from https://api.example.com/v1/jobs?app_id=ID&app_key=SECRET\nsecond line"))
    trouble.note("a plain message", "x" * 2000)
    lines = (config.DATA_DIR / trouble.LOG_NAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and "reading a page: ValueError: bad answer from https://api.example.com/v1/jobs second line" in lines[0]
    assert "SECRET" not in lines[0] and "app_key" not in lines[0] and lines[0][:4].isdigit() and len(lines[1]) < 500
    monkeypatch.setattr(config, "DATA_DIR", config.DATA_DIR / "a_file_not_a_folder")
    (config.DATA_DIR).parent.mkdir(parents=True, exist_ok=True)
    config.DATA_DIR.write_text("in the way")
    trouble.note("nowhere to write", OSError("disk"))                  # must not raise


def test_damaged_options_fall_back_to_defaults_and_leave_a_note(isolate_data):
    from jobhelper import trouble
    config.ensure_dirs()
    (config.DATA_DIR / "ui_settings.json").write_text("{not json", encoding="utf-8")
    assert ui_api.Api().options()["keep_backups"] == housekeeping.DEFAULT_KEEP
    assert "reading the saved Options" in (config.DATA_DIR / trouble.LOG_NAME).read_text(encoding="utf-8")
    for _ in range(housekeeping.LOG_LINES + 50):
        trouble.note("filling the log", "x")
    housekeeping.trim_logs()
    assert len((config.DATA_DIR / trouble.LOG_NAME).read_text(encoding="utf-8").splitlines()) == housekeeping.LOG_LINES


def test_options_says_when_macos_has_the_notifications_turned_off(app_library, monkeypatch):
    opened = []
    api = ui_api.Api()
    monkeypatch.setattr(api._system._desktop, "open", lambda target: opened.append(target))
    app_library.allowed = 0
    assert api.notification_permission() == "off"
    assert api.open_notification_settings() == {"ok": True} and opened == ["x-apple.systempreferences:com.apple.Notifications-Settings.extension"]
    app_library.allowed = 1
    assert api.notification_permission() == "allowed"


@pytest.mark.parametrize("allowed, answer, ok, says", [
    (1, 1, True, "Sent."), (2, 2, True, "Choose Allow"), (0, 0, False, "turned off in System Settings"),
])
def test_the_test_button_says_what_macos_did(app_library, allowed, answer, ok, says):
    app_library.allowed, app_library.answer = allowed, answer
    ui_api.Api().save_options({"notifications": False})                  # a test is sent even with the switch off
    result = ui_api.Api().test_notification()
    assert result["ok"] is ok and says in result["msg"]
    assert app_library.shown == [(notify.TEST_HEADLINE, notify.TEST_MESSAGE)]


def test_the_command_line_test_waits_for_the_persons_first_answer(app_library):
    answers = iter([2, 2, 1])                                          # not asked, still not asked, then allowed
    app_library.answer = 2
    app_library.permission = lambda: next(answers, 1)
    slept = []
    result = notify.send_test(patience=60, sleep=slept.append)
    assert result["ok"] is True and result["msg"].startswith("Sent.") and len(slept) == 2
    app_library.permission = lambda: 2                                 # never answered: it gives up after `patience`
    slept.clear()
    assert "Choose Allow" in notify.send_test(patience=3, sleep=slept.append)["msg"] and len(slept) == 3
