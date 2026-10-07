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
        text = (ROOT / "data" / name).read_text(encoding="utf-8")
        assert "{{name}}" in text or "{{first_name}}" in text
        assert "—" not in text
    config.ensure_dirs()
    config.CV_INSTRUCTION.write_text((ROOT / "data" / "cv_adaptation_instruction.example.md").read_text(encoding="utf-8"), encoding="utf-8")
    config.LETTER_INSTRUCTION.write_text((ROOT / "data" / "cover_letter_instruction.example.md").read_text(encoding="utf-8"), encoding="utf-8")
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
    template = ROOT / "data" / "cover_letter_template.docx"
    if not template.exists():
        pytest.skip("letter template not present")
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
