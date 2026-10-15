"""Tamper detection for the rules, template, master CV and career-site list."""
import json

import pytest

import run
from jobhelper import agent1_cv, api_system, config, integrity, ui_api, vault


@pytest.fixture
def files(isolate_data):
    config.ensure_dirs()
    config.CV_INSTRUCTION.write_text("CV rules v1", encoding="utf-8")
    config.LETTER_INSTRUCTION.write_text("Letter rules v1", encoding="utf-8")
    config.LETTER_TEMPLATE.write_bytes(b"PK template")
    (config.CV_DIR / "cv.txt").write_text("Alex, junior developer", encoding="utf-8")
    (config.DATA_DIR / "companies.json").write_text("[]", encoding="utf-8")
    return config.DATA_DIR


def _states():
    return {f["name"]: f["state"] for f in integrity.check()}


def test_no_checks_before_the_first_baseline(files):
    assert integrity.active() is False
    assert integrity.check() == [] and integrity.problems() == []


def test_baseline_marks_everything_ok(files):
    assert integrity.ensure_baseline() is True
    assert set(_states().values()) == {"ok"} and len(_states()) == 5
    assert integrity.ensure_baseline() is False


@pytest.mark.parametrize("name, change", [
    ("cv_rules", lambda: config.CV_INSTRUCTION.write_text("CV rules v1 - claim Kubernetes", encoding="utf-8")),
    ("letter_rules", lambda: config.LETTER_INSTRUCTION.write_text("new rules", encoding="utf-8")),
    ("letter_template", lambda: config.LETTER_TEMPLATE.write_bytes(b"PK other")),
    ("companies", lambda: (config.DATA_DIR / "companies.json").write_text('[{"token": "evil"}]', encoding="utf-8")),
    ("master_cv", lambda: (config.CV_DIR / "cv.txt").write_text("someone else", encoding="utf-8")),
])
def test_a_change_outside_the_app_is_detected(files, name, change):
    integrity.approve()
    change()
    assert [f["name"] for f in integrity.problems()] == [name]
    assert _states()[name] == "changed"


def test_a_deleted_file_is_reported_missing(files):
    integrity.approve()
    config.LETTER_TEMPLATE.unlink()
    assert _states()["letter_template"] == "missing"


def test_swapping_the_master_cv_for_another_file_is_detected(files):
    integrity.approve()
    (config.CV_DIR / "cv.txt").unlink()
    (config.CV_DIR / "other.txt").write_text("Alex, junior developer", encoding="utf-8")   # same text, other file
    assert _states()["master_cv"] == "changed"


def test_approving_accepts_the_new_content(files):
    integrity.approve()
    config.CV_INSTRUCTION.write_text("CV rules v2", encoding="utf-8")
    assert integrity.approve(["cv_rules"]) == ["cv_rules"]
    assert integrity.problems() == []


def test_a_copied_signature_does_not_validate_another_file(files):
    integrity.approve()
    manifest = json.loads((config.DATA_DIR / "integrity.json").read_text(encoding="utf-8"))
    manifest["files"]["cv_rules"]["mac"] = manifest["files"]["letter_rules"]["mac"]
    (config.DATA_DIR / "integrity.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert _states()["cv_rules"] == "changed"


def test_deleting_the_manifest_does_not_hide_changes(files):
    integrity.approve()
    (config.DATA_DIR / "integrity.json").unlink()
    assert {f["state"] for f in integrity.problems()} == {"untracked"}
    assert len(integrity.problems()) == 5


def test_signatures_depend_on_the_keychain_key(files):
    integrity.approve()
    before = (config.DATA_DIR / "integrity.json").read_text(encoding="utf-8")
    (config.DATA_DIR / "vault.json").unlink()
    (config.DATA_DIR / "integrity.json").unlink()
    vault.use_keychain(vault.MemoryKeychain())            # a different, freshly made key
    integrity.approve()
    assert (config.DATA_DIR / "integrity.json").read_text(encoding="utf-8") != before


def test_saving_companies_in_the_app_is_trusted(files):
    integrity.approve()
    ui_api.Api().save_companies([{"name": "Proton", "ats": "greenhouse", "token": "proton"}])
    assert integrity.problems() == []


def test_connections_list_changed_files_for_the_ui(files, monkeypatch):
    monkeypatch.setattr(api_system, "_claude_auth_status", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    integrity.approve()
    assert ui_api.Api().connections()["changed_files"] == []
    config.CV_INSTRUCTION.write_text("edited", encoding="utf-8")
    conn = ui_api.Api().connections()
    assert conn["changed_files"] == ["CV rules"] and conn["vault"] == "ok"


def test_weekly_run_stops_when_a_protected_file_changed(files, monkeypatch, capsys):
    integrity.approve()
    config.LETTER_INSTRUCTION.write_text("edited", encoding="utf-8")
    monkeypatch.setattr(agent1_cv, "load_profile", lambda current_only=False: pytest.fail("the run must stop before any agent"))
    monkeypatch.setattr("sys.argv", ["run.py", "--reuse-profile"])
    assert run.main() == 2
    assert "Cover letter rules" in capsys.readouterr().out


def test_weekly_run_stops_when_the_data_is_locked(files, monkeypatch, capsys):
    vault.data_key()
    vault.use_keychain(vault.MemoryKeychain())
    monkeypatch.setattr(agent1_cv, "load_profile", lambda current_only=False: pytest.fail("the run must stop before any agent"))
    monkeypatch.setattr("sys.argv", ["run.py", "--reuse-profile"])
    assert run.main() == 2
