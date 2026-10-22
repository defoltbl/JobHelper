"""config: the app manages .env and its saved Options itself — never the real files here."""
import json

import pytest

from jobhelper import config, vault


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_PATH", path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    for name in ("IMAP_USER", "IMAP_PASSWORD", "IMAP_LOOKBACK_DAYS"):
        monkeypatch.setattr(config, name, getattr(config, name))   # restored after the test
    for key in ("IMAP_USER", "IMAP_PASSWORD", "IMAP_LOOKBACK_DAYS", "JOBHELPER_TEST_KEY"):
        monkeypatch.delenv(key, raising=False)
    return path


def test_update_env_creates_file(env_file):
    config.update_env({"JOBHELPER_TEST_KEY": "one"})
    assert env_file.read_text(encoding="utf-8") == "JOBHELPER_TEST_KEY=one\n"


def test_update_env_replaces_key_and_keeps_other_lines(env_file):
    env_file.write_text("# my notes\nOTHER=keep\nJOBHELPER_TEST_KEY=old\n", encoding="utf-8")
    config.update_env({"JOBHELPER_TEST_KEY": "new"})
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert lines == ["# my notes", "OTHER=keep", "JOBHELPER_TEST_KEY=new"]


def test_set_imap_keeps_the_password_out_of_env(env_file):
    env_file.write_text("IMAP_USER=old@example.com\nIMAP_PASSWORD=oldoldoldoldoldo\nOTHER=keep\n", encoding="utf-8")
    config.set_imap("  me@example.com ", " abcdabcdabcdabcd ")
    text = env_file.read_text(encoding="utf-8")
    assert "IMAP_USER=me@example.com" in text and "OTHER=keep" in text
    assert "IMAP_PASSWORD" not in text and "abcdabcdabcdabcd" not in text
    assert vault.get_secret(vault.IMAP_ACCOUNT) == "abcdabcdabcdabcd"
    assert config.IMAP_USER == "me@example.com" and config.has_imap()


def test_set_imap_blank_password_keeps_the_stored_one(env_file):
    config.set_imap("me@example.com", "abcdabcdabcdabcd")
    config.set_imap("other@example.com", "")
    assert vault.get_secret(vault.IMAP_ACCOUNT) == "abcdabcdabcdabcd"
    # and the running app still has it: before, the next scan acted as if no mailbox was set up
    assert config.IMAP_USER == "other@example.com" and config.IMAP_PASSWORD == "abcdabcdabcdabcd" and config.has_imap()


def test_without_a_keychain_a_blank_password_does_not_wipe_the_saved_one(env_file):
    vault.use_keychain(vault.NoKeychain())
    config.set_imap("me@example.com", "abcdabcdabcdabcd")
    config.set_imap("other@example.com", "")
    text = env_file.read_text(encoding="utf-8")
    assert "IMAP_PASSWORD=abcdabcdabcdabcd" in text and "IMAP_USER=other@example.com" in text
    assert config.IMAP_PASSWORD == "abcdabcdabcdabcd"


def test_both_mailboxes_are_saved_by_the_same_rule(env_file, monkeypatch):
    for name in ("IMAP_USER_2", "IMAP_PASSWORD_2", "IMAP_HOST", "IMAP_HOST_2"):
        monkeypatch.setattr(config, name, getattr(config, name))
    config.set_imap2("two@example.com", "efghefghefghefgh", host="imap.example.net")
    config.set_imap2("two-new@example.com", "")
    assert config.IMAP_USER_2 == "two-new@example.com" and config.IMAP_PASSWORD_2 == "efghefghefghefgh"
    assert vault.get_secret(vault.IMAP_ACCOUNT_2) == "efghefghefghefgh"
    assert "IMAP_HOST_2=imap.example.net" in env_file.read_text(encoding="utf-8")


def test_set_imap_without_a_keychain_falls_back_to_env(env_file):
    vault.use_keychain(vault.NoKeychain())
    config.set_imap("me@example.com", "abcdabcdabcdabcd")
    assert "IMAP_PASSWORD=abcdabcdabcdabcd" in env_file.read_text(encoding="utf-8")


def test_old_password_is_moved_from_env_to_keychain(env_file):
    env_file.write_text("# notes\nIMAP_USER=me@example.com\nIMAP_PASSWORD=abcdabcdabcdabcd\n", encoding="utf-8")
    assert config.move_password_to_keychain() is True
    assert env_file.read_text(encoding="utf-8") == "# notes\nIMAP_USER=me@example.com\n"
    assert vault.get_secret(vault.IMAP_ACCOUNT) == "abcdabcdabcdabcd"
    assert config.IMAP_PASSWORD == "abcdabcdabcdabcd"
    assert config.move_password_to_keychain() is False          # nothing left to move


def test_password_stays_in_env_if_the_keychain_refuses_it(env_file, monkeypatch):
    env_file.write_text("IMAP_PASSWORD=abcdabcdabcdabcd\n", encoding="utf-8")
    monkeypatch.setattr(vault, "get_secret", lambda account: "")      # read-back fails
    assert config.move_password_to_keychain() is False
    assert "IMAP_PASSWORD=abcdabcdabcdabcd" in env_file.read_text(encoding="utf-8")


def test_remove_env_only_drops_the_named_keys(env_file):
    env_file.write_text("A=1\nB=2\nC=3\n", encoding="utf-8")
    config.remove_env(["B"])
    assert env_file.read_text(encoding="utf-8") == "A=1\nC=3\n"


def test_ui_settings_missing_or_broken_is_empty(env_file):
    assert config.ui_settings() == {}
    (env_file.parent / "ui_settings.json").write_text("{not json", encoding="utf-8")
    assert config.ui_settings() == {}
    (env_file.parent / "ui_settings.json").write_text("[1, 2]", encoding="utf-8")
    assert config.ui_settings() == {}


def test_apply_ui_settings_sets_model_and_lead_floor(env_file, monkeypatch):
    monkeypatch.setattr(config, "MODEL", "sonnet")
    monkeypatch.setattr(config, "MIN_LEAD_SCORE", 0)
    (env_file.parent / "ui_settings.json").write_text(
        json.dumps({"model": "opus", "min_lead_score": 55}), encoding="utf-8")
    config.apply_ui_settings()
    assert config.MODEL == "opus"
    assert config.MIN_LEAD_SCORE == 55


def test_apply_ui_settings_ignores_bad_values(env_file, monkeypatch):
    monkeypatch.setattr(config, "MODEL", "sonnet")
    monkeypatch.setattr(config, "MIN_LEAD_SCORE", 10)
    config.apply_ui_settings({"model": "  ", "min_lead_score": "abc"})
    assert (config.MODEL, config.MIN_LEAD_SCORE) == ("sonnet", 10)
    config.apply_ui_settings({"min_lead_score": 250})
    assert config.MIN_LEAD_SCORE == 100          # clamped


# ── nothing about one particular person is built into the app ───────────────
def test_candidate_facts_come_from_the_cv_and_options(env_file):
    cv = "Jane Doe\nJunior Data Analyst\njane@example.com"
    assert config.candidate_facts(cv) == {"name": "Jane Doe", "first_name": "Jane", "location": "", "right_to_work": "", "start": ""}
    block = config.facts_block(cv)
    assert "do not mention the right to work" in block and "do not mention a start date" in block
    (env_file.parent / "ui_settings.json").write_text(json.dumps({
        "where": "Berlin", "about_right_to_work": "EU citizen", "about_start": "one month"}), encoding="utf-8")
    facts = config.candidate_facts(cv)
    assert (facts["location"], facts["right_to_work"], facts["start"]) == ("Berlin", "EU citizen", "one month")
    assert "Right to work: EU citizen" in config.facts_block(cv) and "Can start: one month" in config.facts_block(cv)


def test_placeholders_in_rule_files_are_filled_for_whoever_uses_the_app(env_file):
    (env_file.parent / "ui_settings.json").write_text(json.dumps({"where": "Brno", "about_start": "two weeks"}), encoding="utf-8")
    text = "Write as {{first_name}} ({{ NAME }}), based in {{location}}. Start: {{start}}. Work: {{right_to_work}}. Keep {{unknown_word}}."
    out = config.fill_placeholders(text, "Jane Doe\nAnalyst")
    assert out == "Write as Jane (Jane Doe), based in Brno. Start: two weeks. Work: (not stated). Keep {{unknown_word}}."


def test_no_personal_name_in_code_or_docs():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    owner = re.compile("(?i)" + "andr" + "ii|maksy" + "menko")           # built in pieces so this file passes too
    files = [*root.glob("*.py"), *root.glob("*.md"), *root.glob("*.sh"), *(root / "jobhelper").glob("*.py"),
             *(root / "ui_qt").glob("*.qml"), *(root / "tests").glob("*.py"), *(root / "scripts").glob("*.py"),
             root / ".env.example", root / "requirements.txt"]
    readme = (root / "README.md").read_text(encoding="utf-8").splitlines()
    signed = readme.index("## Author") + 1 if "## Author" in readme else len(readme) + 1     # the one place that names the author, at their wish
    assert "## Author" not in readme or not any(line.startswith("## ") for line in readme[signed:]), "the Author section is the last one"
    found = [f"{f.relative_to(root)}:{n}" for f in files if f.is_file()
             for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1)
             if owner.search(line) and not (f.name == "README.md" and f.parent == root and n > signed)
             and not (f.name == "LICENSE.md" and f.parent == root and n == 1)]          # its Required Notice line, checked below
    assert found == [], "a personal name is written into: " + ", ".join(found[:8])
    assert not any("@" in line or "+420" in line for line in readme[signed:]), "a name and public profiles, never an email address or a phone number"
    assert not (root / "LICENSE").exists(), "the licence is LICENSE.md, so GitHub shows its headings and links"
    raw = (root / "LICENSE.md").read_bytes()
    licence = raw.decode("utf-8").splitlines()
    named = [n for n, line in enumerate(licence, 1) if owner.search(line)]
    assert licence[0].startswith("Required Notice: Copyright 2026 ") and named == [1], \
        "the licence names its copyright holder once, on its Required Notice line, and nowhere else"
    assert not any("@" in line or "+420" in line for line in licence)
    import hashlib                                      # below the notice: the official text, word for word
    body = raw.split(b"\n", 2)[2]
    assert hashlib.sha256(body).hexdigest() == "c0ea4a896d2c8c394b29f9427589996db826cd501c512279ff0ed3ef48fabbe5", "the PolyForm Noncommercial 1.0.0 text was changed"
    assert licence[2] == "# PolyForm Noncommercial License 1.0.0"


def test_the_env_file_is_private_from_its_first_byte(isolate_data, monkeypatch):
    """A chmod after writing left a moment when any user of the Mac could read the file. Now it is private before it
    holds anything, and an old readable file is replaced by a private one."""
    import os
    import stat
    config.ENV_PATH.write_text("OLD=1\n", encoding="utf-8")
    os.chmod(config.ENV_PATH, 0o644)
    seen, real = [], os.replace

    def replace(src, dst):
        seen.append(stat.S_IMODE(os.stat(src).st_mode))            # the new file's rights, before it is put in place
        return real(src, dst)
    monkeypatch.setattr(config.os, "replace", replace)
    old_mask = os.umask(0o000)                                       # even with no mask, nothing wider than 0600
    try:
        config.update_env({"IMAP_USER": "jordan@example.com"})
        config.remove_env(["OLD"])
    finally:
        os.umask(old_mask)
    assert seen == [0o600, 0o600] and stat.S_IMODE(os.stat(config.ENV_PATH).st_mode) == 0o600
    assert config.ENV_PATH.read_text(encoding="utf-8") == "IMAP_USER=jordan@example.com\n"
    assert not config.ENV_PATH.with_name(".env.part").exists()
