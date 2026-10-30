"""Manage the weekly macOS LaunchAgent (job search + email scan).

Lets the app turn the weekly run on/off and change its day/time without the
user touching launchctl or the plist by hand.
"""
from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

from . import config, home

LABEL = "com.jobhelper.weeklyscan"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = config.DATA_DIR / "weekly_jobhelper.launchd.log"
# launchd starts a program with a short PATH: add the usual places of the Claude CLI and Homebrew
PATH = "{home}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# launchd Weekday: 0 or 7 = Sunday, 1 = Monday … 6 = Saturday.
DAY_NAMES = {0: "Sun", 7: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}


def problem() -> str:
    """Why this app cannot set the weekly run ('' = it can). The LaunchAgent is one for the whole Mac and starts the
    app on its usual data folder, so a data folder chosen with JOBHELPER_HOME (tests, a check on invented data) never
    reads, changes or removes it."""
    if sys.platform != "darwin":
        return "Weekly scheduling is macOS-only."
    if home.overridden():
        return "The weekly run can be set only for the usual data folder, not for one chosen with JOBHELPER_HOME."
    return ""


def available() -> bool:
    return not problem()


def read_schedule() -> dict:
    """Current schedule: {enabled, weekday, hour, minute, label}."""
    if not available() or not PLIST.exists():
        return {"enabled": False, "weekday": 1, "hour": 9, "minute": 0, "label": "Off"}
    try:
        data = plistlib.loads(PLIST.read_bytes())
        ci = data.get("StartCalendarInterval", {}) or {}
        wd = int(ci.get("Weekday", 1))
        hour = int(ci.get("Hour", 9))
        minute = int(ci.get("Minute", 0))
    except Exception:
        wd, hour, minute = 1, 9, 0
    return {"enabled": True, "weekday": wd, "hour": hour, "minute": minute,
            "label": f"{DAY_NAMES.get(wd, 'Mon')} {hour:02d}:{minute:02d}"}


def command(executable: str | None = None, frozen: bool | None = None) -> list[str]:
    """What the LaunchAgent starts: this program with --weekly. A packaged app is its own program;
    from the source, the Python that runs the app starts app_qt.py."""
    from . import weekly
    executable = executable or sys.executable
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    return [executable, weekly.FLAG] if frozen else [executable, str(config.ROOT / "app_qt.py"), weekly.FLAG]


def _plist_dict(weekday: int, hour: int, minute: int) -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": command(),
        "EnvironmentVariables": {"PATH": PATH.format(home=Path.home())},
        "StartCalendarInterval": {"Weekday": int(weekday), "Hour": int(hour), "Minute": int(minute)},
        "RunAtLoad": False,
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }


def _plist_bytes(weekday: int, hour: int, minute: int) -> bytes:
    return plistlib.dumps(_plist_dict(weekday, hour, minute))


def refresh() -> dict:
    """At the app's start: a weekly run set up by an older version, or for the app in another place
    (the source, a copy in Applications), is pointed at this program and this data folder again,
    on the same day and time. {ok, changed} (and msg when it could not be changed). With JOBHELPER_HOME set it does
    nothing (problem())."""
    if not available() or not PLIST.exists():
        return {"ok": True, "changed": False}
    try:
        current = plistlib.loads(PLIST.read_bytes())
    except Exception:  # noqa: BLE001 - a damaged file is written again
        current = {}
    when = read_schedule()
    wanted = _plist_dict(when["weekday"], when["hour"], when["minute"])
    if all(current.get(key) == wanted[key] for key in ("ProgramArguments", "EnvironmentVariables", "StandardOutPath")):
        return {"ok": True, "changed": False}
    result = write_schedule(True, when["weekday"], when["hour"], when["minute"])
    return {"ok": bool(result.get("ok")), "changed": bool(result.get("ok")), **({"msg": result["msg"]} if "msg" in result else {})}


def write_schedule(enabled: bool, weekday: int, hour: int, minute: int) -> dict:
    if not available():
        return {"ok": False, "msg": problem()}
    try:
        weekday, hour, minute = int(weekday), int(hour), int(minute)
    except (TypeError, ValueError):
        return {"ok": False, "msg": "Choose a day and a time."}
    if not (0 <= weekday <= 7 and 0 <= hour <= 23 and 0 <= minute <= 59):
        return {"ok": False, "msg": "That is not a day and time of the week (hours 0 to 23, minutes 0 to 59)."}
    try:
        if PLIST.exists():
            subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True, text=True, timeout=20)
        if enabled:
            PLIST.parent.mkdir(parents=True, exist_ok=True)
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            PLIST.write_bytes(_plist_bytes(int(weekday), int(hour), int(minute)))
            r = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True, timeout=20)
            if r.returncode != 0 and (r.stderr or "").strip():
                return {"ok": False, "msg": r.stderr.strip()}
        elif PLIST.exists():
            PLIST.unlink()
        return {"ok": True, **read_schedule()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": str(e)}
