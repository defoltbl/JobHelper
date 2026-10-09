"""Keeping the data folder from growing without end.

* Backups: the newest N are kept, older ones are deleted for good.
* Side folders (earlier letter versions, documents of dismissed jobs): the
  newest files are kept.
* Documents moved to the backup because their job fell below your limit: never
  removed here. They can be put back, so only you remove them (Options), by age.
* Log files of the weekly run: only their last lines are kept.

Run at every start. Nothing here touches live data, only backups and logs.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from . import config, vault

DEFAULT_KEEP = 10
SIDE_FOLDERS = {"letter_versions": 40, "not_interested": 60}      # newest files kept in each
SHELF = "below_your_limit"            # documents that can be put back: never cleaned up automatically
SHELF_MIN_DAYS = 7                    # copies younger than this are never removed (New Jobs still offers to put them back)
LOG_LINES = 400
_STAMP = re.compile(r"(\d{8})_(\d{6})")


def _age_key(path: Path) -> tuple:
    """Newest first when sorted descending: the time in the name, else the file time."""
    m = _STAMP.search(path.name)
    return (m.group(1) + m.group(2)) if m else "", path.stat().st_mtime


def backup_entries() -> list[Path]:
    """Time-stamped backups (folders and single files), newest first."""
    root = vault.backups_dir()
    if not root.is_dir():
        return []
    entries = [p for p in root.iterdir() if p.name not in SIDE_FOLDERS and p.name != SHELF and not p.name.startswith(".")]
    return sorted(entries, key=_age_key, reverse=True)


def prune_backups(keep: int = DEFAULT_KEEP, dry_run: bool = False) -> list[str]:
    """Delete all but the newest `keep` backups (0 = keep everything). Returns the names removed."""
    if keep <= 0:
        return []
    gone = backup_entries()[keep:]
    if not dry_run:
        for path in gone:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
    return [p.name for p in gone]


def prune_side_folders(dry_run: bool = False) -> int:
    removed = 0
    for name, keep in SIDE_FOLDERS.items():
        folder = vault.backups_dir() / name
        if not folder.is_dir():
            continue
        files = sorted((p for p in folder.iterdir() if p.is_file()), key=_age_key, reverse=True)
        for path in files[keep:]:
            if not dry_run:
                path.unlink(missing_ok=True)
            removed += 1
    return removed


def _when(path: Path) -> datetime:
    """When a backup copy was made: the time in its name, else the file's own time."""
    m = _STAMP.search(path.name)
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime)


def shelf_files(older_than_days: int | None = None) -> list[Path]:
    """The documents moved to the backup (all of them, or only those older than the given days)."""
    folder = vault.backups_dir() / SHELF
    if not folder.is_dir():
        return []
    files = [p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")]
    if older_than_days is not None:
        limit = datetime.now() - timedelta(days=older_than_days)
        files = [p for p in files if _when(p) < limit]
    return sorted(files)


def tidy_shelf(days: int) -> dict:
    """Delete, for good, the moved documents older than `days` (never fewer than SHELF_MIN_DAYS).
    {removed: [names], bytes}"""
    days = max(int(days), SHELF_MIN_DAYS)
    removed, size = [], 0
    for path in shelf_files(days):
        try:
            n = path.stat().st_size
            path.unlink()
        except OSError:
            continue
        removed.append(path.name)
        size += n
    return {"removed": removed, "bytes": size}


def trim_logs(lines: int = LOG_LINES) -> int:
    """Keep only the last lines of each log in the data folder. Returns how many files were shortened."""
    done = 0
    for log in config.DATA_DIR.glob("*.log"):
        try:
            text = log.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        if len(text) > lines:
            log.write_text("\n".join(text[-lines:]) + "\n", encoding="utf-8")
            done += 1
    return done


def run() -> dict:
    """Everything above, with the user's own limit from Options."""
    try:
        keep = int(config.ui_settings().get("keep_backups", DEFAULT_KEEP))
    except (TypeError, ValueError):
        keep = DEFAULT_KEEP
    return {"backups_removed": prune_backups(keep), "side_files_removed": prune_side_folders(), "logs_trimmed": trim_logs()}
