"""Encryption at rest and Keychain storage (always against the in-memory Keychain)."""
import base64
import json

import pytest

from jobhelper import agent1_cv, config, db, store, ui_api, vault

SECRET_TEXT = "Junior Python Developer at Acme"


def _raw(path) -> bytes:
    return path.read_bytes()


# ── bytes ───────────────────────────────────────────────────────────────────
def test_encrypt_roundtrip_and_fresh_nonce(isolate_data):
    one, two = vault.encrypt(b"hello"), vault.encrypt(b"hello")
    assert one.startswith(vault.MAGIC) and b"hello" not in one
    assert one != two                                   # a new nonce every time
    assert vault.decrypt(one) == vault.decrypt(two) == b"hello"


def test_plain_data_passes_through_decrypt(isolate_data):
    assert vault.decrypt(b'{"old": "plain file"}') == b'{"old": "plain file"}'


def test_tampered_ciphertext_is_rejected(isolate_data):
    blob = bytearray(vault.encrypt(b"important"))
    blob[-1] ^= 1
    with pytest.raises(vault.VaultError):
        vault.decrypt(bytes(blob))


def test_wrong_key_cannot_decrypt(isolate_data):
    blob = vault.encrypt(b"important")
    other = base64.urlsafe_b64encode(b"\x07" * 32).decode()
    (config.DATA_DIR / "vault.json").unlink()
    vault.use_keychain(vault.MemoryKeychain({vault.KEY_ACCOUNT: other}))
    with pytest.raises(vault.VaultError):
        vault.decrypt(blob)


# ── the key ─────────────────────────────────────────────────────────────────
def test_key_is_created_once_for_a_new_folder(isolate_data):
    vault.use_keychain(vault.MemoryKeychain())
    first = vault.data_key()
    assert len(first) == 32 and vault.keychain().get(vault.KEY_ACCOUNT)
    assert json.loads((config.DATA_DIR / "vault.json").read_text())["key_id"]
    vault.use_keychain(vault.keychain())                # forget the cache, keep the Keychain
    assert vault.data_key() == first


def test_missing_key_locks_instead_of_starting_over(isolate_data):
    vault.data_key()                                    # folder is now tied to the test key
    vault.use_keychain(vault.MemoryKeychain())          # Keychain lost the key
    assert vault.state() == "locked"
    with pytest.raises(vault.VaultError, match="restore-key"):
        vault.data_key()
    assert vault.keychain().get(vault.KEY_ACCOUNT) is None      # and no new key was made up


def test_recovery_key_restores_access(isolate_data):
    store.save_jobs([store.new_job(id="1", title=SECRET_TEXT)])
    saved = vault.recovery_key()
    vault.use_keychain(vault.MemoryKeychain())
    assert vault.state() == "locked"
    vault.restore_key(saved)
    assert vault.state() == "ok" and store.load_jobs()[0]["title"] == SECRET_TEXT


@pytest.mark.parametrize("bad", ["", "not-a-key", base64.urlsafe_b64encode(b"short").decode()])
def test_restore_rejects_invalid_keys(isolate_data, bad):
    with pytest.raises(vault.VaultError):
        vault.restore_key(bad)


def test_restore_rejects_a_key_for_other_data(isolate_data):
    vault.data_key()
    with pytest.raises(vault.VaultError, match="does not belong"):
        vault.restore_key(base64.urlsafe_b64encode(b"\x09" * 32).decode())


def test_without_a_keychain_files_stay_plain(isolate_data):
    vault.use_keychain(vault.NoKeychain())
    assert vault.state() == "off"
    store.save_jobs([store.new_job(id="1", title=SECRET_TEXT)])
    assert SECRET_TEXT.encode() in _raw(config.JOBS_JSON)
    assert store.load_jobs()[0]["title"] == SECRET_TEXT


def test_encryption_can_be_switched_off(isolate_data, monkeypatch):
    monkeypatch.setenv("JOBHELPER_ENCRYPT", "0")
    store.save_jobs([store.new_job(id="1", title=SECRET_TEXT)])
    assert SECRET_TEXT.encode() in _raw(config.JOBS_JSON)


# ── the data files ──────────────────────────────────────────────────────────
def test_jobs_file_is_encrypted_on_disk(isolate_data):
    store.save_jobs([store.new_job(id="1", title=SECRET_TEXT, company="Acme")])
    raw = _raw(config.JOBS_JSON)
    assert raw.startswith(vault.MAGIC) and b"Acme" not in raw and SECRET_TEXT.encode() not in raw
    assert store.load_jobs()[0]["title"] == SECRET_TEXT
    assert oct(config.JOBS_JSON.stat().st_mode & 0o777) == "0o600"


def test_old_plain_jobs_file_still_loads_and_is_encrypted_on_save(isolate_data):
    config.ensure_dirs()
    config.JOBS_JSON.write_text(json.dumps([store.new_job(id="1", title=SECRET_TEXT)]), encoding="utf-8")
    jobs = store.load_jobs()
    assert jobs[0]["title"] == SECRET_TEXT
    store.save_jobs(jobs)
    assert vault.file_is_encrypted(config.JOBS_JSON)


def test_profile_and_options_are_encrypted(isolate_data, monkeypatch):
    monkeypatch.setattr(agent1_cv, "find_cv", lambda: None)
    config.ensure_dirs()
    vault.write_text(config.PROFILE_JSON, json.dumps({"summary": SECRET_TEXT, "search_queries": ["qa engineer"]}))
    ui_api.Api().save_options({"where": "Brno", "queries": ["secret keyword"]})
    assert SECRET_TEXT.encode() not in _raw(config.PROFILE_JSON)
    assert b"secret keyword" not in _raw(config.DATA_DIR / "ui_settings.json")
    assert agent1_cv.load_profile()["summary"] == SECRET_TEXT
    assert config.ui_settings()["where"] == "Brno"
    assert ui_api.Api().options()["queries"] == ["secret keyword"]


def test_responses_database_is_encrypted_and_keeps_working(isolate_data):
    db.upsert_response({"msg_id": "<1@x>", "company": "Acme", "stage": "rejection",
                        "summary": "We regret to inform you", "rejection_category": "position_filled"})
    db.mark_seen("<1@x>")
    raw = _raw(config.RESPONSES_DB)
    assert raw.startswith(vault.MAGIC)
    assert b"SQLite format" not in raw and b"Acme" not in raw and b"regret" not in raw
    assert db.total() == 1 and db.is_seen("<1@x>") and db.has_response("<1@x>")
    db.set_response_job("<1@x>", "job-9")
    db.upsert_response({"msg_id": "<2@x>", "company": "Beta", "stage": "interview"})
    assert [r["company"] for r in db.all_responses()] == ["Acme", "Beta"] or db.total() == 2
    assert db.all_responses()[0]["job_id"] in ("job-9", "")
    assert db.rejection_reason_counts() == {"position_filled": 1}


def test_old_plain_database_is_read_and_encrypted_on_next_write(isolate_data):
    import sqlite3
    config.ensure_dirs()
    conn = sqlite3.connect(str(config.RESPONSES_DB))
    conn.executescript(db._SCHEMA)
    conn.execute("INSERT INTO responses (msg_id, company, stage) VALUES ('<old@x>', 'Legacy', 'other')")
    conn.commit()
    conn.close()
    assert db.total() == 1 and not vault.file_is_encrypted(config.RESPONSES_DB)
    db.mark_seen("<new@x>")
    assert vault.file_is_encrypted(config.RESPONSES_DB)
    assert db.total() == 1 and db.all_responses()[0]["company"] == "Legacy"


def test_reads_do_not_rewrite_the_database(isolate_data):
    db.mark_seen("<1@x>")
    before = _raw(config.RESPONSES_DB)
    db.total(); db.is_seen("<1@x>"); db.all_responses()          # noqa: E702
    assert _raw(config.RESPONSES_DB) == before


def test_locked_data_shows_empty_lists_not_a_crash(isolate_data):
    store.save_jobs([store.new_job(id="1", title=SECRET_TEXT)])
    db.mark_seen("<1@x>")
    vault.use_keychain(vault.MemoryKeychain())                      # key gone
    api = ui_api.Api()
    assert api.counts() == {"leads": 0, "applications": 0, "responses": 0, "followups": 0, "duplicates": 0}
    assert api.leads() == [] and api.applications() == [] and api.responses() == []
    with pytest.raises(vault.VaultError):
        store.load_jobs()


# ── backups ─────────────────────────────────────────────────────────────────
def test_existing_backups_are_encrypted_in_place(isolate_data):
    root = vault.backups_dir()
    (root / "old" / "cover_letters").mkdir(parents=True)
    (root / "jobs.20261006.json").write_text('[{"company": "Acme"}]', encoding="utf-8")
    (root / "old" / "cover_letters" / "letter.docx").write_bytes(b"PK\x03\x04 Dear Acme")
    assert vault.encrypt_tree(root) == 2
    names = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert names == ["jobs.20261006.json.enc", "old/cover_letters/letter.docx.enc"]
    assert all(b"Acme" not in p.read_bytes() for p in root.rglob("*") if p.is_file())
    assert vault.encrypt_tree(root) == 0                # nothing left to do


def test_backup_and_restore_roundtrip(isolate_data, tmp_path):
    store.save_jobs([store.new_job(id="1", title=SECRET_TEXT)])
    db.mark_seen("<1@x>")
    folder = vault.make_backup("test")
    assert sorted(p.name for p in folder.iterdir()) == ["jobs.json.enc", "responses.db.enc"]
    assert all(vault.file_is_encrypted(p) for p in folder.iterdir())
    out = tmp_path / "restored"
    assert vault.restore_backup(folder, out) == 2
    assert json.loads((out / "jobs.json").read_text(encoding="utf-8"))[0]["title"] == SECRET_TEXT
    assert (out / "responses.db").read_bytes().startswith(b"SQLite format 3")


# ── protect_all (runs at every start) ───────────────────────────────────────
def test_protect_all_upgrades_an_old_folder_and_is_idempotent(isolate_data):
    config.ensure_dirs()
    config.JOBS_JSON.write_text(json.dumps([store.new_job(id="1", title=SECRET_TEXT)]), encoding="utf-8")
    config.PROFILE_JSON.write_text('{"summary": "x"}', encoding="utf-8")
    config.ENV_PATH.write_text("IMAP_USER=me@example.com\nIMAP_PASSWORD=abcdabcdabcdabcd\n", encoding="utf-8")
    (vault.backups_dir()).mkdir()
    (vault.backups_dir() / "jobs.old.json").write_text("[]", encoding="utf-8")

    report = vault.protect_all()
    assert report["state"] == "ok" and report["password_moved"] is True
    assert sorted(report["files"]) == ["jobs.json", "profile.json"]
    assert report["backups"] == 1 and report["baseline"] is True
    assert "IMAP_PASSWORD" not in config.ENV_PATH.read_text(encoding="utf-8")
    assert vault.get_secret(vault.IMAP_ACCOUNT) == "abcdabcdabcdabcd"
    assert store.load_jobs()[0]["title"] == SECRET_TEXT

    again = vault.protect_all()
    assert (again["password_moved"], again["files"], again["backups"], again["baseline"]) == (False, [], 0, False)


def test_protect_all_does_nothing_when_locked(isolate_data):
    vault.data_key()
    config.JOBS_JSON.write_text("[]", encoding="utf-8")
    vault.use_keychain(vault.MemoryKeychain())
    report = vault.protect_all()
    assert report["state"] == "locked" and report["files"] == []
    assert config.JOBS_JSON.read_text(encoding="utf-8") == "[]"


# ── the real Keychain is never used here ────────────────────────────────────
def test_tests_use_the_memory_keychain():
    assert isinstance(vault.keychain(), vault.MemoryKeychain)
    assert not isinstance(vault.keychain(), vault.MacKeychain)


def test_mac_keychain_sends_the_secret_on_stdin_not_in_arguments(monkeypatch):
    calls = []

    class Result:
        returncode, stdout, stderr = 0, 'pa"ss\\word\n', ""

    def run(cmd, input=None, **kwargs):
        calls.append((cmd, input))
        return Result()

    monkeypatch.setattr(vault.subprocess, "run", run)
    vault.MacKeychain().set("imap_password", 'pa"ss\\word')
    cmd, sent = calls[0]
    assert cmd == ["security", "-i"] and 'pa"ss' not in " ".join(cmd)
    assert '-w "pa\\"ss\\\\word"' in sent and '-a "imap_password"' in sent


def test_mac_keychain_rejects_control_characters():
    with pytest.raises(vault.VaultError):
        vault.MacKeychain().set("imap_password", "line1\nline2")
