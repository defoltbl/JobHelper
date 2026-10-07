"""Manage the weekly macOS LaunchAgent (job search + email scan).

Lets the app turn the weekly run on/off and change its day/time without the
user touching launchctl or the plist by hand.
"""
from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

from . import config

LABEL = "com.jobhelper.weeklyscan"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
SCRIPT = config.ROOT / "weekly_jobhelper.sh"
LOG = config.DATA_DIR / "weekly_jobhelper.launchd.log"

# launchd Weekday: 0 or 7 = Sunday, 1 = Monday … 6 = Saturday.
DAY_NAMES = {0: "Sun", 7: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}


def available() -> bool:
    return sys.platform == "darwin"


def read_schedule() -> dict:
    """Current schedule: {enabled, weekday, hour, minute, label}."""
    if not PLIST.exists():
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


def _plist_bytes(weekday: int, hour: int, minute: int) -> bytes:
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": ["/bin/zsh", str(SCRIPT)],
        "StartCalendarInterval": {"Weekday": int(weekday), "Hour": int(hour), "Minute": int(minute)},
        "RunAtLoad": False,
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    })


def write_schedule(enabled: bool, weekday: int, hour: int, minute: int) -> dict:
    if not available():
        return {"ok": False, "msg": "Weekly scheduling is macOS-only."}
    try:
        if PLIST.exists():
            subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True, text=True)
        if enabled:
            PLIST.parent.mkdir(parents=True, exist_ok=True)
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            PLIST.write_bytes(_plist_bytes(int(weekday), int(hour), int(minute)))
            r = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True)
            if r.returncode != 0 and (r.stderr or "").strip():
                return {"ok": False, "msg": r.stderr.strip()}
        elif PLIST.exists():
            PLIST.unlink()
        return {"ok": True, **read_schedule()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": str(e)}
