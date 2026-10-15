"""Where the app keeps your data.

A Mac app keeps its data in ~/Library/Application Support/<app>, not next to its program:
the program can then be replaced (a new version, a copy in Applications) and the data stays.
Older versions of JobHelper kept the data in the project folder (data/ and .env). `DataHome`
says which folder is in use, and moves an old folder into the Library once, when the app starts:

1. Everything is copied into the Library, into a folder that is not used yet.
2. Each copied file is compared with its original, byte for byte.
3. Only then the copy gets its real name, and a note (home.json) says that the move is done.
4. The old folder is not deleted: it gets the name data_moved_to_Library, and .env gets the
   name .env.moved_to_Library. They are your backup of the move.

If a step fails, the old folder stays in use and nothing in it changes.

This module imports nothing of the app: `config` asks it where the data is.
"""
from __future__ import annotations

import filecmp
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = Path.home() / "Library" / "Application Support" / "JobHelper"
OVERRIDE = "JOBHELPER_HOME"         # a folder to use instead of the Library one (tests, a second set of data)
MOVED_SUFFIX = "_moved_to_Library"


class HomeError(Exception):
    """The data could not be moved; the message says why. The old folder is still in use."""


@dataclass(frozen=True)
class Move:
    """What `DataHome.settle` did: moved now (the app must start again to use the new place), how many files, from where."""
    moved: bool
    files: int = 0
    source: Path | None = None
    kept: Path | None = None


class DataHome:
    """The folder of your data: the Library one, or an old one in the project folder that is not moved yet."""

    NOTE = "home.json"
    # what makes an old folder hold data (and not only a log line or an empty folder)
    SIGNS = ("jobs.json", "vault.json", "profile.json", "responses.db", "cv")

    def __init__(self, library: Path, legacy: Path | None = None, legacy_env: Path | None = None) -> None:
        self._library = Path(library)
        self._legacy = Path(legacy) if legacy else None
        self._legacy_env = Path(legacy_env) if legacy_env else None

    @classmethod
    def for_this_mac(cls, environ=None) -> "DataHome":
        """The real one: JOBHELPER_HOME if it is set (then only that folder), else the Library and the old project folder."""
        environ = os.environ if environ is None else environ
        override = str(environ.get(OVERRIDE) or "").strip()
        if override:
            return cls(Path(override).expanduser())
        return cls(LIBRARY, ROOT / "data", ROOT / ".env")

    # ── where things are ─────────────────────────────────────────────────────
    @property
    def library(self) -> Path:
        return self._library

    @property
    def moved(self) -> bool:
        """Whether the Library folder is the one in use (the note of a move, or of a new start, is there)."""
        return (self._library / self.NOTE).is_file()

    def _legacy_in_use(self) -> bool:
        return not self.moved and self._legacy is not None and self.holds_data(self._legacy)

    def data_dir(self) -> Path:
        """The folder with the job list, the database, the documents and the backups."""
        return self._legacy if self._legacy_in_use() else self._library / "data"

    def env_path(self) -> Path:
        """The file of the settings that are not secret (.env)."""
        return self._legacy_env if self._legacy_in_use() and self._legacy_env else self._library / ".env"

    @classmethod
    def holds_data(cls, folder: Path) -> bool:
        return Path(folder).is_dir() and any((Path(folder) / name).exists() for name in cls.SIGNS)

    # ── the move, once ───────────────────────────────────────────────────────
    def settle(self) -> Move:
        """Make the Library folder the one in use. An old folder with data is moved (see the module text);
        without one, the Library folder is simply started. Raises HomeError when a move fails."""
        if self.moved:
            return Move(False)
        if not self._legacy_in_use():
            (self._library / "data").mkdir(parents=True, exist_ok=True)
            self._write_note({"started": _now()})
            return Move(False)
        return self._move()

    def _move(self) -> Move:
        source, target = self._legacy, self._library / "data"
        if target.exists() and any(p for p in target.iterdir() if p.name != ".DS_Store"):
            raise HomeError(f"The folder {target} already holds files, so your data was not moved there. "
                            "Nothing was changed.")
        incoming = self._library / "data.incoming"
        shutil.rmtree(incoming, ignore_errors=True)            # an earlier move that stopped halfway: only a copy
        try:
            self._library.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, incoming, symlinks=True)
            different = _differences(source, incoming)
            if different:
                raise HomeError(f"{len(different)} files were not copied correctly (the first: {different[0]}). "
                                "Your data stays where it is.")
            if self._legacy_env and self._legacy_env.is_file():
                shutil.copy2(self._legacy_env, self._library / ".env")
                if not filecmp.cmp(self._legacy_env, self._library / ".env", shallow=False):
                    raise HomeError("The settings file .env was not copied correctly. Your data stays where it is.")
            if target.exists():
                target.rmdir()                                 # empty (checked above)
            incoming.rename(target)
        except HomeError:
            shutil.rmtree(incoming, ignore_errors=True)
            raise
        except OSError as e:
            shutil.rmtree(incoming, ignore_errors=True)
            raise HomeError(f"Your data could not be copied into the Library ({e.strerror or e}). It stays where it is.") from e
        files = sum(1 for p in target.rglob("*") if p.is_file())
        kept = _free_name(source.with_name(source.name + MOVED_SUFFIX))
        self._write_note({"moved_from": str(source), "kept_as": str(kept), "files": files, "moved": _now()})
        source.rename(kept)                                    # the old folder stays whole: the backup of the move
        if self._legacy_env and self._legacy_env.is_file():
            self._legacy_env.rename(_free_name(self._legacy_env.with_name(self._legacy_env.name + MOVED_SUFFIX)))
        return Move(True, files, source, kept)

    def _write_note(self, note: dict) -> None:
        self._library.mkdir(parents=True, exist_ok=True)
        (self._library / self.NOTE).write_text(json.dumps(note, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _differences(source: Path, copy: Path) -> list[str]:
    """The files of `source` that are missing in `copy` or differ from it (by their bytes)."""
    out = []
    for path in source.rglob("*"):
        if path.is_file() and not path.is_symlink():
            twin = copy / path.relative_to(source)
            if not twin.is_file() or not filecmp.cmp(path, twin, shallow=False):
                out.append(str(path.relative_to(source)))
    return out


def _free_name(path: Path) -> Path:
    """`path`, or the same name with a number when that name is taken."""
    if not path.exists():
        return path
    n = 2
    while path.with_name(f"{path.name}_{n}").exists():
        n += 1
    return path.with_name(f"{path.name}_{n}")


def here() -> DataHome:
    """The data home of this Mac (or of JOBHELPER_HOME)."""
    return DataHome.for_this_mac()


_problem: list[str] = []          # why the move at this start failed ('' when it did not)


def start() -> Move:
    """At the app's start, before the data is used: settle the data home of this Mac. A move that fails
    leaves the old folder in use; the start-up check then shows why (`problem()`)."""
    _problem.clear()
    try:
        return here().settle()
    except HomeError as e:
        _problem.append(str(e))
        return Move(False)


def problem() -> str:
    return _problem[0] if _problem else ""


def restart_command(argv: list[str], executable: str, frozen: bool) -> list[str]:
    """The command that starts this program again with the same arguments: a packaged app is its own
    program; from the source, Python runs the script again."""
    return [executable, *argv[1:]] if frozen else [executable, *argv]
