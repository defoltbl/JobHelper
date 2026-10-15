"""The weekly run must work wherever the app is, for any user."""
from pathlib import Path

import pytest

import status
from jobhelper import config, weekly

ROOT = Path(__file__).resolve().parent.parent


def _tracked_text_files():
    skip = {".venv", ".git", "data", "__pycache__", ".pytest_cache"}
    for path in ROOT.rglob("*"):
        parts = path.relative_to(ROOT).parts
        if any(part.startswith("data_moved_to_Library") for part in parts):
            continue                                           # your old data folder, kept after the move
        if path.is_file() and not (set(parts) & skip) \
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


def test_the_weekly_shell_script_is_gone_and_nothing_points_to_it():
    """The weekly run is the app itself with --weekly: a packaged app has no .venv or run.py to start."""
    assert not (ROOT / "weekly_jobhelper.sh").exists()
    for path in _tracked_text_files():
        if path != Path(__file__).resolve() and path.name != "CHANGELOG.md":
            assert "weekly_jobhelper.sh" not in path.read_text(encoding="utf-8", errors="ignore"), path.name


def test_weekly_run_writes_each_step_into_its_log_and_goes_on_after_a_failure(tmp_path):
    from datetime import datetime
    done = []

    def search():
        print("found 3 jobs")
        done.append("search")
        return 0

    def broken():
        raise RuntimeError("the mail server said no")

    def scan():
        done.append("scan")
        return 2

    log = tmp_path / "logs" / "weekly.log"
    code = weekly.WeeklyRun(log, [("job search", search), ("broken", broken), ("email analysis", scan)],
                            now=lambda: datetime(2026, 10, 19, 9, 0)).run()
    text = log.read_text(encoding="utf-8")
    assert done == ["search", "scan"] and code == 2
    assert text.startswith("===== weekly JobHelper 2026-10-19 09:00 =====")
    assert "--- job search ---\nfound 3 jobs" in text and "RuntimeError: the mail server said no" in text
    assert "(broken ended with code 1)" in text and "(email analysis ended with code 2)" in text
    weekly.WeeklyRun(log, [("again", lambda: 0)]).run()
    assert log.read_text(encoding="utf-8").startswith(text)                    # added to, never written over


def test_the_default_steps_are_the_search_then_the_mail(monkeypatch):
    seen = []
    for name in ("run", "status"):
        module = __import__(name)
        monkeypatch.setattr(module, "main", lambda name=name: seen.append((name, list(__import__("sys").argv))) or 0)
    log = config.DATA_DIR / "weekly-test.log"
    assert weekly.WeeklyRun(log).run() == 0
    assert seen == [("run", ["run.py", "--reuse-profile"]), ("status", ["status.py", "sync", "--summary"])]   # no fixed days


@pytest.mark.parametrize("ending, code", [(SystemExit(0), 0), (SystemExit(None), 0), (SystemExit(3), 3), (SystemExit("bad"), 1)])
def test_a_command_that_ends_with_sys_exit_gives_its_code(monkeypatch, ending, code):
    import sys

    def stop():
        raise ending
    monkeypatch.setattr(__import__("run"), "main", stop)
    before = list(sys.argv)
    assert weekly.command_step("run", ["--reuse-profile"])() == code and sys.argv == before


def test_the_app_with_weekly_runs_the_steps_and_opens_no_window(monkeypatch):
    import sys

    import app_qt
    from jobhelper import home
    monkeypatch.setattr(sys, "argv", ["app_qt.py", "--weekly"])
    monkeypatch.setattr(weekly, "main", lambda: 7)
    monkeypatch.setattr(home, "start", lambda: pytest.fail("the weekly run never moves the data"))
    monkeypatch.setattr(app_qt, "QGuiApplication", lambda *a: pytest.fail("the weekly run opens no window"))
    assert app_qt.main() == 7


def test_sync_takes_its_period_from_options(monkeypatch):
    monkeypatch.setattr(config, "IMAP_LOOKBACK_DAYS", 120)
    for saved, days in (({"scan_days": 10}, 10), ({"scan_days": "14"}, 14), ({}, 120), ({"scan_days": 0}, 120),
                        ({"scan_days": "soon"}, 120), ({"scan_days": -3}, 120)):
        monkeypatch.setattr(config, "ui_settings", lambda saved=saved: saved)
        assert status.scan_days() == days
