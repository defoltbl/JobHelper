"""The weekly script must work wherever the project folder is, for any user."""
import shutil
import subprocess
from pathlib import Path

import pytest

import status
from jobhelper import config

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "weekly_jobhelper.sh"
ZSH = shutil.which("zsh")


def _tracked_text_files():
    skip = {".venv", ".git", "data", "__pycache__", ".pytest_cache"}
    for path in ROOT.rglob("*"):
        if path.is_file() and not (set(path.relative_to(ROOT).parts) & skip) \
                and path.suffix in {".py", ".sh", ".md", ".qml", ".json", ".txt", ".ini", ".example"}:
            yield path


def test_no_file_names_one_persons_computer():
    home = str(Path.home())
    for path in _tracked_text_files():
        if path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "/Volumes/" not in text, f"{path.name} names a disk"
        assert home not in text and "/Users/" not in text, f"{path.name} names a home folder"


def test_the_old_cron_script_is_gone_and_nothing_points_to_it():
    assert not (ROOT / "weekly_scan.sh").exists()
    for path in _tracked_text_files():
        if path != Path(__file__).resolve():
            assert "weekly_scan.sh" not in path.read_text(encoding="utf-8", errors="ignore"), path.name


def _fake_project(tmp_path, with_venv=True):
    """A copy of the script in a folder with a space in its name and a stand-in Python that records its calls."""
    project = tmp_path / "My Job Helper"
    project.mkdir()
    shutil.copy(SCRIPT, project / "weekly_jobhelper.sh")
    recorder = "#!/bin/sh\necho \"$(pwd -P)|$*\" >> \"$(dirname \"$0\")/../../calls.txt\"\n"
    if with_venv:
        py = project / ".venv" / "bin" / "python"
        py.parent.mkdir(parents=True)
        py.write_text(recorder)
        py.chmod(0o755)
    return project


@pytest.mark.skipif(ZSH is None, reason="zsh is not installed")
def test_script_finds_its_own_folder_and_uses_the_projects_python(tmp_path):
    project = _fake_project(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    done = subprocess.run([ZSH, str(project / "weekly_jobhelper.sh")], cwd=elsewhere, capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    calls = (project / "calls.txt").read_text().splitlines()
    here = str(project.resolve())
    assert calls == [f"{here}|run.py --reuse-profile", f"{here}|status.py sync --summary"]     # no fixed number of days
    log = (project / "data" / "weekly_jobhelper.log").read_text()
    assert "--- job search ---" in log and "--- email analysis ---" in log
    assert not (elsewhere / "data").exists()                                                  # nothing written where it was started


def test_script_has_no_fixed_folder_or_days():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'PROJECT="${0:A:h}"' in text and "--days" not in text
    assert ".venv/bin/python" in text and "command -v python3" in text


def test_sync_takes_its_period_from_options(monkeypatch):
    monkeypatch.setattr(config, "IMAP_LOOKBACK_DAYS", 120)
    for saved, days in (({"scan_days": 10}, 10), ({"scan_days": "14"}, 14), ({}, 120), ({"scan_days": 0}, 120),
                        ({"scan_days": "soon"}, 120), ({"scan_days": -3}, 120)):
        monkeypatch.setattr(config, "ui_settings", lambda saved=saved: saved)
        assert status.scan_days() == days
