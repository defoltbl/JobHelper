"""The self-check made when the app starts: one clear line when something is wrong."""
import pytest

from jobhelper import agent1_cv, config, health, integrity, store, vault


@pytest.fixture
def healthy(isolate_data, monkeypatch):
    config.ensure_dirs()
    store.save_jobs([store.new_job(id="a", title="Dev", company="Acme")])
    for path in (config.CV_INSTRUCTION, config.LETTER_INSTRUCTION, config.LETTER_TEMPLATE):
        path.write_text("x", encoding="utf-8")
    cv = config.CV_DIR / "cv.docx"
    cv.write_bytes(b"cv")
    monkeypatch.setattr(agent1_cv, "find_cv", lambda: cv)
    return isolate_data


def _named(report, name):
    return next(c for c in report["checks"] if c["name"] == name)


def test_all_well_says_nothing(healthy):
    report = health.run(True)
    assert report["ok"] is True and report["problems"] == 0 and report["message"] == ""
    assert [c["name"] for c in report["checks"]] == [name for name, _ in health.CHECKS] + ["Claude"]
    assert len(health.run()["checks"]) == len(health.CHECKS)             # Claude not known yet: not judged


def test_not_signed_in_is_one_clear_line(healthy):
    report = health.run(False)
    assert report["ok"] is False and report["problems"] == 1
    assert report["message"] == "You are not signed in to Claude. Open the Account card and press Sign in."


def test_a_damaged_job_list_and_database_are_named_with_the_way_out(healthy):
    vault.write_text(config.JOBS_JSON, "{not json")
    config.RESPONSES_DB.write_bytes(b"JHENC1\ngarbage")
    report = health.run(True)
    assert "damaged" in _named(report, "Job list")["problem"] and "data/backups" in _named(report, "Job list")["problem"]
    assert _named(report, "Replies")["ok"] is False
    assert report["problems"] == 2 and report["message"].startswith("2 things need your attention. The first: ")


def test_a_missing_key_is_reported_once_per_file_it_blocks(healthy, monkeypatch):
    def locked():
        raise vault.VaultError("no key")
    monkeypatch.setattr(vault, "state", lambda: "locked")
    monkeypatch.setattr(vault, "data_key", locked)
    report = health.run(True)
    assert "restore-key" in _named(report, "Data key")["problem"]
    assert "restore-key" in _named(report, "Job list")["problem"]
    assert report["ok"] is False


def test_missing_cv_rules_and_template(healthy, monkeypatch):
    monkeypatch.setattr(agent1_cv, "find_cv", lambda: None)
    config.LETTER_TEMPLATE.unlink()
    report = health.run(True)
    assert _named(report, "Master CV")["problem"].startswith("No master CV yet")
    assert "cover letter template" in _named(report, "Files for writing")["problem"]


def test_changed_rule_files_and_damaged_options(healthy, monkeypatch):
    monkeypatch.setattr(integrity, "problems", lambda: [{"title": "CV rules", "state": "changed"}])
    vault.write_text(config.DATA_DIR / "ui_settings.json", "[1, 2]")
    report = health.run(True)
    assert _named(report, "Rules and template unchanged")["problem"].startswith("Changed outside the app: CV rules.")
    assert "defaults are used" in _named(report, "Options")["problem"]


def test_an_incomplete_job_entry_and_a_crashing_check(healthy, monkeypatch):
    monkeypatch.setattr(store, "load_jobs", lambda: [{"id": "a", "status": "found"}, {"title": "no id"}])
    assert _named(health.run(True), "Job list")["problem"] == "1 entries in your job list are incomplete."

    def boom():
        raise RuntimeError("disk gone")
    monkeypatch.setattr(health, "CHECKS", [("Folders writable", boom)])
    report = health.run(True)
    assert "The check itself failed (RuntimeError: disk gone)." == report["checks"][0]["problem"]


def test_a_read_only_folder_is_noticed(healthy, monkeypatch):
    import os
    real = os.access
    monkeypatch.setattr(os, "access", lambda path, mode: False if str(path).endswith("cover_letters") else real(path, mode))
    assert "cover_letters cannot be written" in _named(health.run(True), "Folders writable")["problem"]
