"""Tamper detection for the rules, template, master CV and career-site list."""
import json
from pathlib import Path

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


def test_a_lost_keychain_mark_never_signs_a_changed_file_as_good(files):
    """#75: with the Keychain's mark gone, the next start signed every file again, a changed one too."""
    integrity.ensure_baseline()
    config.CV_INSTRUCTION.write_text("CV rules v1 - claim Kubernetes", encoding="utf-8")
    vault.delete_secret(integrity.BASELINE_FLAG)
    assert integrity.active() is True, "the signed list still counts"
    assert integrity.ensure_baseline() is False and vault.get_secret(integrity.BASELINE_FLAG) == "1"
    assert _states()["cv_rules"] == "changed"


@pytest.mark.parametrize("damaged", ["{not json", '{"files": ["cv_rules"]}', '{"files": {"cv_rules": "abc"}}', "[]"])
def test_a_damaged_signed_list_never_passes_for_none(files, damaged):
    """#75: with the Keychain's mark gone and the signed list damaged, the next start signed every file as it was."""
    integrity.ensure_baseline()
    config.CV_INSTRUCTION.write_text("CV rules v1 - claim Kubernetes", encoding="utf-8")
    vault.delete_secret(integrity.BASELINE_FLAG)
    integrity._manifest_path().write_text(damaged, encoding="utf-8")
    assert integrity.active() is True and integrity.ensure_baseline() is False
    assert _states()["cv_rules"] == "untracked", "shown for you to approve, never signed by itself"
    assert integrity.problems()


def test_a_signature_that_is_not_hex_counts_as_none(files):
    integrity.ensure_baseline()
    integrity._manifest_path().write_text(json.dumps({"files": {"cv_rules": {"file": "x", "mac": "é" * 64}}}), encoding="utf-8")
    assert _states()["cv_rules"] == "untracked"


def test_a_run_says_the_files_were_not_checked_and_asks_for_no_approval(files, monkeypatch, qapp):
    from jobhelper import qt_bridge
    conn = {"claude": True, "cv": "cv.docx", "paid_api": False, "changed_files": [integrity.NOT_CHECKED]}
    monkeypatch.setattr(ui_api.Api, "connections", lambda self, sign_in=None: dict(conn))
    refused = qt_bridge.Bridge().runSearch({"where": "Brno"})
    assert refused == {"ok": False, "fix": "integrity", "msg": integrity.NOT_CHECKED_SAY}


def test_the_start_up_check_says_the_files_were_not_checked_without_asking_to_approve(files, monkeypatch):
    from jobhelper import health
    monkeypatch.setattr(integrity, "changed_titles", lambda: [integrity.NOT_CHECKED])
    line = health._rules()
    assert line == integrity.NOT_CHECKED_SAY and "Approve" not in line


def test_a_keychain_that_does_not_answer_stops_a_run_instead_of_switching_the_check_off(files, monkeypatch):
    """#75: a Keychain error during the check read as "nothing changed"."""
    integrity.ensure_baseline()
    monkeypatch.setattr(integrity, "problems", lambda: (_ for _ in ()).throw(vault.VaultError("The Keychain did not answer.")))
    assert integrity.changed_titles() == [integrity.NOT_CHECKED]
    assert ui_api.Api().connections()["changed_files"] == [integrity.NOT_CHECKED]


def test_the_window_is_told_when_the_files_were_not_checked_and_only_then(files, monkeypatch):
    """#96: the Account card offered Approve for a check that never ran; the back end now says which case it is."""
    monkeypatch.setattr(api_system, "_claude_auth_status", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(integrity, "changed_titles", lambda: [integrity.NOT_CHECKED])
    conn = ui_api.Api().connections()
    assert conn["changes_unchecked"] is True and conn["changes_msg"] == integrity.NOT_CHECKED_CARD
    assert "Account card" not in conn["changes_msg"], "the card itself is open: its words point to its own Check again"
    for titles in ([], ["CV rules"], [integrity.NOT_CHECKED, "CV rules"]):
        monkeypatch.setattr(integrity, "changed_titles", lambda titles=titles: list(titles))
        conn = ui_api.Api().connections()
        assert conn["changes_unchecked"] is False and conn["changes_msg"] == "", titles


def test_the_signed_list_is_written_whole_or_not_at_all(files, monkeypatch):
    """#75: integrity._save wrote the file in place; a stop half-way left half a list."""
    integrity.ensure_baseline()
    written = []
    monkeypatch.setattr(vault, "write_plain", lambda path, data: written.append((Path(path).name, data)))
    integrity.approve()
    assert written and written[0][1].startswith(b"{")


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
    assert integrity.state_of("letter_template") == "ok"
    config.LETTER_TEMPLATE.unlink()
    assert _states()["letter_template"] == "missing" and integrity.state_of("letter_template") == "missing"
    assert integrity.state_of("no such file") == ""


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
