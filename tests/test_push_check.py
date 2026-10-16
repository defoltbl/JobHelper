"""The push check: what a git push would publish, on throwaway repositories with an invented owner."""
import io
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import push_check  # noqa: E402

NOREPLY = "12345+jordan-example@users.noreply.github.com"
OWNER = push_check.PrivateWords(["Jordan", "Weber", "jordan.weber@private-mail.example", "777888999", "linkedin.com/in/jordan-w-1234",
                                 "github.com/jordan-w"])


def _git(repo, *args, email=NOREPLY):
    env = {"GIT_AUTHOR_NAME": "Jordan Weber", "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": "Jordan Weber",
           "GIT_COMMITTER_EMAIL": email, "HOME": str(repo), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=env).stdout.strip()


def _commit(repo, files: dict, message="Add a feature", email=NOREPLY):
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    _git(repo, "add", "-A", email=email)
    _git(repo, "commit", "-q", "-m", message, email=email)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "project"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _commit(r, {"app.py": "print('hello')\n",
                "README.md": "# App\n\nSome text.\n\n## Author\n\n**Jordan Weber** – [LinkedIn](https://linkedin.com/in/jordan-w-1234)\n",
                "LICENSE": "MIT License\n\nCopyright (c) 2026 Jordan Weber\n\nPermission is hereby granted.\n"}, "First version")
    return r


def _check(repo, ranges=None):
    return [str(f) for f in push_check.PushCheck(repo, OWNER).run(ranges)]


def test_a_clean_history_may_be_pushed(repo):
    assert _check(repo) == []                                   # named only in README's Author section and the copyright line


def test_a_personal_detail_anywhere_else_stops_the_push(repo):
    _commit(repo, {"tests/test_x.py": "CV = 'Jordan Weber, call 777 888 999'\n", "notes.md": "mail: jordan.weber@private-mail.example\n"})
    found = _check(repo)
    assert "a personal detail: tests/test_x.py:1" in found and "a personal detail: notes.md:1" in found
    assert not any("jordan.weber@" in f or "777" in f for f in found), "the report never repeats the private word"


def test_the_readme_allows_the_name_only_in_its_author_section(repo):
    _commit(repo, {"README.md": "# App by Jordan Weber\n\n## Author\n\nJordan Weber\n"})
    assert _check(repo) == ["a personal detail: README.md:1"]


def test_the_licence_allows_the_name_only_on_its_copyright_line(repo):
    _commit(repo, {"LICENSE": "MIT License\n\nCopyright (c) 2026 Jordan Weber\n\nThanks to Jordan.\n"})
    assert _check(repo) == ["a personal detail: LICENSE:5"]


def test_a_detail_removed_later_still_stops_the_push(repo):
    """The whole history goes to the remote: a detail in an old commit is published although it is gone now."""
    _commit(repo, {"old.txt": "phone 777888999\n"})
    _commit(repo, {"old.txt": "nothing\n"})
    assert "a personal detail: old.txt:1" in _check(repo)


def test_word_files_and_their_hidden_author_are_read(repo):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:t>Invented text</w:t></w:document>")
        z.writestr("docProps/core.xml", "<cp:lastModifiedBy>Weber</cp:lastModifiedBy>")
    _commit(repo, {"tests/fixtures/cv.docx": buf.getvalue()})
    assert "a personal detail: tests/fixtures/cv.docx" in _check(repo)


@pytest.mark.parametrize("content, kind", [
    ("KEY = 'sk-" + "ant-api03-abcdefghijklmnop'\n", "an Anthropic API key"),          # built in pieces: this file is pushed too
    ("token = gh" + "p_abcdefghijklmnopqrstuvwxyz123456\n", "a GitHub token"),
    ("-----BEGIN RSA " + "PRIVATE KEY-----\n", "a private key"),
    ("JOOBLE_API_" + "KEY=abcdef0123456789abcdef\n", "a password or key in a setting"),
    ("pass" + "word: Tr9vLm2QzK8pW4nB\n", "a password or key in a setting"),
])
def test_secrets_stop_the_push(repo, content, kind):
    _commit(repo, {"config.py": content})
    assert f"{kind}: config.py" in _check(repo)


def test_a_personal_email_on_a_commit_stops_the_push(repo):
    _commit(repo, {"b.py": "x = 1\n"}, email="jordan.weber@private-mail.example")
    found = _check(repo)
    assert any(f.startswith("the author email is not a GitHub noreply address") for f in found)
    assert any(f.startswith("the committer email is not a GitHub noreply address") for f in found)


def test_an_assistant_credit_line_stops_the_push(repo):
    _commit(repo, {"c.py": "y = 2\n"}, message="Add y\n\nCo-Authored-By: Someone <x@example.com>")
    assert any(f.startswith("an assistant credit line") for f in _check(repo))


@pytest.mark.parametrize("name", ["data/jobs.json", ".env", "sub/.env"])
def test_private_files_stop_the_push(repo, name):
    _commit(repo, {name: "anything\n"})
    assert f"a private file (the data folder or .env): {name}" in _check(repo)


def test_the_hook_checks_only_what_the_remote_does_not_have(repo):
    first = _git(repo, "rev-parse", "HEAD")
    _commit(repo, {"old.txt": "phone 777888999\n"})                 # already on the remote
    pushed = _git(repo, "rev-parse", "HEAD")
    new = _commit(repo, {"new.py": "z = 3\n"})
    assert _check(repo, [(new, pushed)]) == []                       # only the new commit goes out
    assert "a personal detail: old.txt:1" in _check(repo, [(new, first)])
    assert "a personal detail: old.txt:1" in _check(repo, [(new, push_check.ZERO)])   # a first push sends everything
    assert _check(repo, [(push_check.ZERO, pushed)]) == []          # deleting a branch sends nothing


def test_the_hook_is_installed_and_blocks_a_bad_push(repo, tmp_path):
    hook = push_check.install_hook(repo)
    assert hook.name == "pre-push" and hook.stat().st_mode & 0o111
    text = hook.read_text()
    assert "push_check.py" in text and "--hook" in text and sys.executable in text


def test_the_command_line_says_what_it_found_and_fails(repo, monkeypatch, capsys):
    _commit(repo, {"x.py": "owner = 'Jordan Weber'\n"})
    monkeypatch.setattr(push_check.PrivateWords, "from_data_home", classmethod(lambda cls: OWNER))
    assert push_check.main(["--repo", str(repo)]) == 1
    out = capsys.readouterr().out
    assert "Nothing was pushed" in out and "a personal detail (1): x.py:1" in out
    clean = repo.parent / "clean"
    clean.mkdir()
    _git(clean, "init", "-q", "-b", "main")
    _commit(clean, {"a.py": "a = 1\n"})
    assert push_check.main(["--repo", str(clean)]) == 0 and "may go ahead" in capsys.readouterr().out


def test_the_owner_words_come_from_their_own_data_and_never_from_the_repository():
    source = (ROOT / "scripts" / "push_check.py").read_text(encoding="utf-8")
    assert "CvSource" in source and "push_check_words.txt" in source and "config.IMAP_USER" in source
    assert "jordan" not in source.lower()


def test_a_made_up_test_value_is_not_a_secret(repo):
    _commit(repo, {"tests/test_env.py": "ENV = 'IMAP_PASSWORD=abcdabcdabcdabcd\\nAPP_KEY=oldoldoldoldoldold'\n"})
    assert _check(repo) == []
    _commit(repo, {"settings.py": "ADZUNA_APP_" + "KEY = 'f3a9Kq72LmZ0xW5bT8'\n"})
    assert "a password or key in a setting: settings.py" in _check(repo)


def test_the_repositorys_own_address_may_name_its_owner(repo):
    """A badge needs github.com/<owner>/JobHelper; that address is public with the repository. Other addresses of the owner are not."""
    _commit(repo, {"README.md": "# App\n![Tests](https://github.com/jordan-w/JobHelper/actions/workflows/tests.yml/badge.svg)\n"})
    assert _check(repo) == []
    _commit(repo, {"notes.md": "see https://github.com/jordan-w/other-project\n"})
    assert "a personal detail: notes.md:1" in _check(repo)
