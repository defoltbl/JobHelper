"""The weekly run must work wherever the app is, for any user."""
from pathlib import Path

import pytest

from jobhelper import config, weekly

ROOT = Path(__file__).resolve().parent.parent


def _tracked_text_files(root=ROOT):
    skip = {".venv", ".git", "data", "__pycache__", ".pytest_cache", "build", "dist"}     # build/, dist/: the built app
    for path in root.rglob("*"):
        parts = path.relative_to(root).parts
        if any(part.startswith("data_moved_to_Library") for part in parts):
            continue                                           # your old data folder, kept after the move
        if parts[:2] == (".claude", "worktrees"):
            continue                                           # other checkouts of this repository, with their own copies
        if path.is_file() and not (set(parts) & skip) \
                and path.suffix in {".py", ".sh", ".md", ".qml", ".json", ".txt", ".ini", ".example"}:
            yield path


def test_the_scan_reads_this_checkout_and_not_the_worktrees_inside_it(tmp_path):
    """A session in its own worktree keeps it in .claude/worktrees: its copy of this file is not a file of this folder."""
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "helper.md").write_text("an agent")
    copy = tmp_path / ".claude" / "worktrees" / "other" / "tests"
    copy.mkdir(parents=True)
    (copy / "test_weekly_script.py").write_text("a copy")
    assert [p.relative_to(tmp_path).as_posix() for p in _tracked_text_files(tmp_path)] == [".claude/agents/helper.md"]


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


def test_the_weekly_run_waits_for_the_window_and_never_writes_over_its_jobs(tmp_path, jobs_held_elsewhere):
    """#72: the weekly run and the open window each loaded the job list, worked for minutes and wrote it all back."""
    from jobhelper import api_core, store
    ran = []
    log = tmp_path / "weekly.log"
    assert weekly.WeeklyRun(log, [("job search", lambda: ran.append(1) or 0)], wait=0.3).run() == weekly.WeeklyRun.BUSY_CODE
    assert ran == [] and "did not start" in log.read_text(encoding="utf-8")
    with pytest.raises(store.JobsBusy):
        store.save_jobs([])                                                     # nothing written over the other's changes
    assert api_core.JobEditor().change("any", lambda jobs, j: None) == {"ok": False, "msg": store.RunLock.BUSY}
    jobs_held_elsewhere.kill()
    jobs_held_elsewhere.wait()
    assert weekly.WeeklyRun(tmp_path / "w2.log", [("job search", lambda: 0)], wait=0).run() == 0
    store.save_jobs([])                                                         # free again: written


def test_the_lock_is_one_per_process_so_the_window_s_own_edits_go_on(isolate_data):
    from jobhelper import store
    assert store.RunLock.path().parent == isolate_data
    with store.RunLock.holding():                                               # a run
        store.save_jobs([])                                                     # and an edit inside it
        assert store.RunLock._held == 1
    assert store.RunLock._held == 0 and store.RunLock._file is None


def test_a_disk_without_file_locks_still_saves_and_leaks_no_file(isolate_data, monkeypatch):
    """A volume that answers flock with ENOLCK cannot be shared by two processes: the lock counts as free there."""
    import errno
    from jobhelper import store
    opened = []
    real_fdopen = store.os.fdopen
    monkeypatch.setattr(store.os, "fdopen", lambda *a, **k: opened.append(real_fdopen(*a, **k)) or opened[-1])
    monkeypatch.setattr(store.fcntl, "flock", lambda f, how: (_ for _ in ()).throw(OSError(errno.ENOLCK, "no locks")))
    store.save_jobs([])
    assert opened and all(f.closed for f in opened) and store.RunLock._held == 0


def test_a_long_wait_never_blocks_the_window_s_threads(jobs_held_elsewhere):
    """The weekly run's wait sleeps outside the guard, so another thread of the same process can still ask the lock."""
    import threading
    import time
    from jobhelper import store
    waiting = threading.Thread(target=store.RunLock.take, args=(1.5,), daemon=True)
    waiting.start()
    start = time.monotonic()
    assert store.RunLock.take() is False
    assert time.monotonic() - start < 1.0, "answered at once, not after the other thread's wait"
    waiting.join()


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
        assert config.scan_days() == days


def test_a_command_that_changes_jobs_waits_for_no_other_run_and_a_read_still_works(jobs_held_elsewhere, monkeypatch, capsys):
    """#72: python run.py or status.py while the window searched wrote the list over the window's, or stopped half-way."""
    import run
    import status
    from jobhelper import store
    monkeypatch.setattr("sys.argv", ["status.py", "update", "nw1", "waiting"])
    assert status.main() == 1 and store.RunLock.COMMAND_BUSY in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["run.py", "--skip-search"])
    assert run.main() == 1 and store.RunLock.COMMAND_BUSY in capsys.readouterr().out
    assert not config.JOBS_JSON.exists(), "nothing written"
    for argv in (["list"], ["usage"], ["security", "status"]):
        monkeypatch.setattr("sys.argv", ["status.py", *argv])
        assert status.main() == 0, f"{argv}: a command that changes no job still runs"
        assert store.RunLock.COMMAND_BUSY not in capsys.readouterr().out


def test_a_command_inside_the_weekly_run_holds_the_same_lock(isolate_data):
    from jobhelper import store
    with store.RunLock.holding():                                               # the weekly run
        assert store.RunLock.command(lambda: 7) == 7                            # its step, run.py's main
