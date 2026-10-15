"""Weekly LaunchAgent management — against a temp plist with launchctl stubbed out."""
import plistlib
from types import SimpleNamespace

import pytest

from jobhelper import schedule


@pytest.fixture
def sched(tmp_path, monkeypatch):
    calls = []
    state = {"returncode": 0, "stderr": ""}

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=state["returncode"], stderr=state["stderr"], stdout="")

    monkeypatch.setattr(schedule, "PLIST", tmp_path / "LaunchAgents" / "com.jobhelper.weeklyscan.plist")
    monkeypatch.setattr(schedule, "LOG", tmp_path / "weekly.log")
    monkeypatch.setattr(schedule.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(schedule, "available", lambda: True)
    monkeypatch.setattr(schedule.subprocess, "run", fake_run)
    return SimpleNamespace(calls=calls, state=state)


def test_read_schedule_off_by_default(sched):
    assert schedule.read_schedule() == {"enabled": False, "weekday": 1, "hour": 9, "minute": 0, "label": "Off"}


def test_enable_writes_plist_and_loads_it(sched):
    result = schedule.write_schedule(True, 3, 18, 30)
    assert result["ok"] and result["enabled"] and result["label"] == "Wed 18:30"
    data = plistlib.loads(schedule.PLIST.read_bytes())
    assert data["StartCalendarInterval"] == {"Weekday": 3, "Hour": 18, "Minute": 30}
    assert data["ProgramArguments"] == schedule.command() and data["ProgramArguments"][-1] == "--weekly"
    assert "/.local/bin" in data["EnvironmentVariables"]["PATH"]                # where the Claude CLI usually is
    assert sched.calls[-1][:2] == ["launchctl", "load"]


def test_change_unloads_the_old_schedule_first(sched):
    schedule.write_schedule(True, 1, 9, 0)
    sched.calls.clear()
    schedule.write_schedule(True, 5, 7, 5)
    assert [c[1] for c in sched.calls] == ["unload", "load"]
    assert schedule.read_schedule()["label"] == "Fri 07:05"


def test_disable_removes_plist(sched):
    schedule.write_schedule(True, 1, 9, 0)
    result = schedule.write_schedule(False, 1, 9, 0)
    assert result["ok"] and not result["enabled"]
    assert not schedule.PLIST.exists()


def test_launchctl_failure_is_reported(sched):
    sched.state.update(returncode=1, stderr="Load failed: 5: Input/output error")
    result = schedule.write_schedule(True, 1, 9, 0)
    assert result == {"ok": False, "msg": "Load failed: 5: Input/output error"}


def test_corrupt_plist_falls_back_to_defaults(sched):
    schedule.PLIST.parent.mkdir(parents=True)
    schedule.PLIST.write_bytes(b"not a plist")
    assert schedule.read_schedule()["label"] == "Mon 09:00"


def test_not_available_off_macos(sched, monkeypatch):
    monkeypatch.setattr(schedule, "available", lambda: False)
    assert schedule.write_schedule(True, 1, 9, 0)["ok"] is False
    assert sched.calls == []


def test_the_command_is_the_app_itself():
    import sys
    from pathlib import Path
    source = schedule.command("/venv/bin/python", frozen=False)
    assert source[0] == "/venv/bin/python" and Path(source[1]).name == "app_qt.py" and source[2] == "--weekly"
    assert Path(source[1]).is_file()
    assert schedule.command("/Applications/JobHelper.app/Contents/MacOS/JobHelper", frozen=True) == \
        ["/Applications/JobHelper.app/Contents/MacOS/JobHelper", "--weekly"]
    assert schedule.command() == [sys.executable, source[1], "--weekly"]


def test_refresh_points_an_old_weekly_run_at_this_program_on_the_same_day(sched):
    schedule.PLIST.parent.mkdir(parents=True)
    schedule.PLIST.write_bytes(plistlib.dumps({"Label": schedule.LABEL, "ProgramArguments": ["/bin/zsh", "/old/place/weekly.sh"],
                                               "StartCalendarInterval": {"Weekday": 4, "Hour": 7, "Minute": 45},
                                               "StandardOutPath": "/old/place/data/weekly.log"}))
    assert schedule.refresh() == {"ok": True, "changed": True}
    data = plistlib.loads(schedule.PLIST.read_bytes())
    assert data["ProgramArguments"] == schedule.command() and data["StandardOutPath"] == str(schedule.LOG)
    assert data["StartCalendarInterval"] == {"Weekday": 4, "Hour": 7, "Minute": 45}
    sched.calls.clear()
    assert schedule.refresh() == {"ok": True, "changed": False} and sched.calls == []     # up to date: not touched


def test_refresh_does_nothing_when_the_weekly_run_is_off(sched):
    assert schedule.refresh() == {"ok": True, "changed": False} and not schedule.PLIST.exists() and sched.calls == []


def test_refresh_says_why_it_could_not_change_it(sched):
    schedule.PLIST.parent.mkdir(parents=True)
    schedule.PLIST.write_bytes(b"not a plist")
    sched.state.update(returncode=1, stderr="Load failed: 5")
    assert schedule.refresh() == {"ok": False, "changed": False, "msg": "Load failed: 5"}
