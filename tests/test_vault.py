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
    with pytest.raises(vault.VaultError, match="Account card"):
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


# ── a restore that is really run, not assumed ───────────────────────────────
def _seed(tmp_path):
    import sqlite3

    from jobhelper import config, db, store
    config.ensure_dirs()
    store.save_jobs([store.new_job(id="a", title="Dev", company="Acme")])
    db.upsert_response({"msg_id": "m1", "job_id": "a", "stage": "rejection", "company": "Acme", "subject": "s",
                        "from_addr": "hr@example.com", "received_date": "2026-10-01"})
    assert sqlite3 is not None


def test_restore_test_proves_a_backup_matches_the_live_data(isolate_data):
    import tempfile
    from pathlib import Path

    from jobhelper import config, vault
    _seed(isolate_data)
    before = set(Path(tempfile.gettempdir()).glob("jobhelper-restore-*"))
    report = vault.restore_test()
    assert report["ok"] is True and report["backup"].startswith("restore_test_")
    names = {f["name"]: f for f in report["files"]}
    assert set(names) == {"jobs.json", "responses.db"} and all(f["ok"] and f["problem"] == "" for f in names.values())
    assert set(Path(tempfile.gettempdir()).glob("jobhelper-restore-*")) == before      # no plain copy left behind
    assert vault.file_is_encrypted(config.JOBS_JSON)                                  # the live data was only read
    assert (vault.backups_dir() / report["backup"] / "jobs.json.enc").is_file()


def test_restore_test_reports_an_old_backup_that_cannot_be_read(isolate_data):
    from jobhelper import vault
    _seed(isolate_data)
    good = vault.make_backup("earlier")
    bad = vault.backups_dir() / "broken" / "jobs.json.enc"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"JHENC1\nnot really encrypted data")
    report = vault.restore_test()
    assert report["ok"] is False and report["older"]["unreadable"] == ["broken/jobs.json.enc"]
    assert report["older"]["files"] == report["older"]["readable"] + 1 and good.is_dir()
    assert all(f["ok"] for f in report["files"])                                      # today's data itself is fine


def test_restored_content_must_also_be_usable():
    from jobhelper import vault
    assert vault._usable("jobs.json", b'[{"id": 1}]') == ""
    assert "cannot be opened" in vault._usable("jobs.json", b"{broken")
    assert "cannot be opened" in vault._usable("responses.db", b"this is not a database") \
        or "damaged" in vault._usable("responses.db", b"this is not a database")
    assert vault._usable("notes.txt", b"anything") == ""


def test_restore_test_needs_protection_to_be_on(isolate_data, monkeypatch):
    import pytest as _pytest

    from jobhelper import vault
    monkeypatch.setattr(vault, "state", lambda: "off")
    with _pytest.raises(vault.VaultError, match="Protection is off") as raised:
        vault.restore_test()
    assert "status.py" not in str(raised.value)


# ── one backup of everything ────────────────────────────────────────────────
def _everything(isolate_data):
    from jobhelper import config
    _seed(isolate_data)
    docs = {config.CV_DIR / "Alex_Novak_CV.docx": b"master cv", config.COVER_LETTERS_DIR / "Alex_Novak_CoverLetter_Acme.docx": b"my own letter",
            config.LETTERS_DIR / "Letter_a.docx": b"app letter", config.LETTERS_DIR / "Letter_a.pdf": b"%PDF app letter",
            config.TAILORED_CV_DIR / "CV_a.docx": b"adapted cv", config.CV_INSTRUCTION: b"cv rules",
            config.LETTER_INSTRUCTION: b"letter rules", config.LETTER_TEMPLATE: b"template",
            config.DATA_DIR / "companies.json": b"[]"}
    for path, data in docs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (config.LETTERS_DIR / "Letter_a.editing.docx").write_bytes(b"half-finished edit")
    (config.CV_DIR / ".DS_Store").write_bytes(b"junk")
    return docs


def test_backup_everything_holds_documents_and_data_encrypted(isolate_data):
    from jobhelper import vault
    docs = _everything(isolate_data)
    done = vault.backup_everything()
    names = sorted(p.relative_to(done["folder"]).as_posix() for p in done["folder"].rglob("*") if p.is_file())
    assert names == ["companies.json.enc", "cover_letter_instruction.md.enc", "cover_letter_template.docx.enc",
                     "cover_letters/Letter_a.docx.enc", "cover_letters/Letter_a.pdf.enc", "cv/Alex_Novak_CV.docx.enc",
                     "cv_adaptation_instruction.md.enc", "jobs.json.enc", "my_letters/Alex_Novak_CoverLetter_Acme.docx.enc",
                     "responses.db.enc", "tailored_cvs/CV_a.docx.enc"]
    assert done["files"] == len(names) and done["bytes"] > 0
    for path in done["folder"].rglob("*.enc"):
        assert path.read_bytes().startswith(b"JHENC1\n") and b"master cv" not in path.read_bytes()
    assert all(path.read_bytes() == data for path, data in docs.items())            # the originals were only read


def test_backup_everything_restores_to_the_same_content(isolate_data, tmp_path):
    import json

    from jobhelper import vault
    docs = _everything(isolate_data)
    done = vault.backup_everything()
    out = tmp_path / "restored"
    assert vault.restore_backup(done["folder"], out) == done["files"]
    assert (out / "cv" / "Alex_Novak_CV.docx").read_bytes() == b"master cv"
    assert (out / "my_letters" / "Alex_Novak_CoverLetter_Acme.docx").read_bytes() == b"my own letter"
    assert (out / "cover_letter_template.docx").read_bytes() == b"template"
    assert json.loads((out / "jobs.json").read_text())[0]["company"] == "Acme"       # plain and readable again
    assert not list(out.rglob("*.editing.*")) and not list(out.rglob(".DS_Store"))
    assert len(docs) + 2 == done["files"]


def test_own_letters_kept_outside_the_app_are_backed_up_too(isolate_data, tmp_path, monkeypatch):
    from jobhelper import config, vault
    _seed(isolate_data)
    elsewhere = tmp_path / "Documents" / "Letters"
    elsewhere.mkdir(parents=True)
    (elsewhere / "Mine_CoverLetter_Beta.docx").write_bytes(b"kept elsewhere")
    monkeypatch.setattr(config, "COVER_LETTERS_DIR", elsewhere)
    done = vault.backup_everything()
    assert vault.read_bytes(done["folder"] / "my_letters" / "Mine_CoverLetter_Beta.docx.enc") == b"kept elsewhere"


def test_backup_everything_refuses_when_the_key_is_missing(isolate_data, monkeypatch):
    import pytest as _pytest

    from jobhelper import vault

    def no_key():
        raise vault.VaultError("the key is missing")
    monkeypatch.setattr(vault, "state", lambda: "locked")
    monkeypatch.setattr(vault, "data_key", no_key)
    with _pytest.raises(vault.VaultError, match="key is missing"):
        vault.backup_everything()
    assert not list(vault.backups_dir().glob("everything_*")) if vault.backups_dir().is_dir() else True


# ── found by reading vault.py line by line (10 October 2026) ────────────────
def test_a_keychain_that_cannot_be_read_is_not_taken_for_an_empty_one(monkeypatch):
    """Any failure of the system tool used to mean "no such secret". For the data key that is dangerous: "no key yet" is
    the one case in which a new key is made."""
    import subprocess
    from types import SimpleNamespace
    answers = []
    monkeypatch.setattr(vault.subprocess, "run", lambda cmd, **kw: answers.pop(0))
    mac = vault.MacKeychain()
    answers.append(SimpleNamespace(returncode=0, stdout="s3cret\n", stderr=""))
    assert mac.get("data_key") == "s3cret"
    answers.append(SimpleNamespace(returncode=44, stdout="", stderr="security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain."))
    assert mac.get("data_key") is None, "truly not there"
    answers.append(SimpleNamespace(returncode=36, stdout="", stderr="security: SecKeychainSearchCopyNext: User interaction is not allowed."))
    with pytest.raises(vault.VaultError, match="could not be read"):
        mac.get("data_key")

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 20)
    monkeypatch.setattr(vault.subprocess, "run", slow)
    with pytest.raises(vault.VaultError, match="did not answer"):
        mac.get("data_key")
    vault.use_keychain(mac)
    try:
        assert vault.get_secret("imap_password") == "", "a mailbox password that cannot be read is simply not there for now"
        assert vault.state() == "locked", "and the data is locked, not given a new key"
    finally:
        vault.use_keychain(vault.MemoryKeychain())


def test_no_new_key_is_made_for_data_that_is_already_encrypted(isolate_data):
    """The note of which key a folder uses (vault.json) can be lost. With it gone and the key not in the Keychain, the app
    used to start a new key, and the encrypted data could never be opened again."""
    config.ensure_dirs()
    vault.write_text(config.JOBS_JSON, "[]")
    assert vault.file_is_encrypted(config.JOBS_JSON) and vault.state() == "ok"
    first = vault.recovery_key()
    (config.DATA_DIR / "vault.json").unlink()
    vault.use_keychain(vault.MemoryKeychain())               # a new Mac: the Keychain is empty
    with pytest.raises(vault.VaultError, match="Account card"):
        vault.data_key()
    assert vault.state() == "locked" and vault.keychain().get(vault.KEY_ACCOUNT) is None, "nothing was written over"
    vault.restore_key(first)
    assert vault.read_text(config.JOBS_JSON) == "[]" and vault.state() == "ok"
    assert "Gmail" not in " ".join(vault.LABELS.values()), "any provider's mailbox, not one company's"


# ── the newest backup copy that opens, for the start-up check's Restore button ──
def _backup_copy(folder, name, data, age):
    import os
    import time
    path = vault.backups_dir() / folder / (name + vault.BACKUP_SUFFIX)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(vault.encrypt(data))
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


def test_newest_good_copy_skips_copies_that_do_not_open(isolate_data):
    config.ensure_dirs()
    _backup_copy("old_20260101_100000", "jobs.json", b'[{"id": "old"}]', age=300)
    good = _backup_copy("mid_20260102_100000", "jobs.json", b'[{"id": "mid"}]', age=200)
    _backup_copy("new_20260103_100000", "jobs.json", b"{not json", age=100)             # the newest is damaged too
    _backup_copy("new_20260103_100000", "profile.json", b"{}", age=50)                  # another file is not a copy of it
    data, copy = vault.newest_good_copy(config.JOBS_JSON)
    assert copy == good and data == b'[{"id": "mid"}]'


def test_newest_good_copy_is_none_without_a_usable_copy(isolate_data):
    config.ensure_dirs()
    assert vault.newest_good_copy(config.JOBS_JSON) is None                            # no backups folder at all
    _backup_copy("a_20260101_100000", "responses.db", b"not a database", age=10)
    assert vault.newest_good_copy(config.RESPONSES_DB) is None


def test_set_aside_moves_the_file_and_never_deletes_it(isolate_data):
    config.ensure_dirs()
    config.JOBS_JSON.write_bytes(b"damaged bytes")
    kept = vault.set_aside(config.JOBS_JSON, "damaged")
    assert not config.JOBS_JSON.exists() and kept.parent == vault.backups_dir() / "damaged"
    assert kept.read_bytes() == b"damaged bytes" and kept.name.startswith("jobs.") and kept.suffix == ".json"
    assert vault.set_aside(config.JOBS_JSON, "damaged") is None                         # nothing there any more
