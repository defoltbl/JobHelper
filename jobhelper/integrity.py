"""Tamper detection for the files that steer what the app writes.

The CV rules, the cover-letter rules, the letter template, the master CV and
the career-site list decide what goes into every CV and letter. Each one is
signed with HMAC-SHA256 using a key derived from the data key in the Keychain,
so a changed file cannot be given a matching signature by whoever changed it.
A change made outside the app is reported until the user approves it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from . import vault

BASELINE_FLAG = "integrity_baseline"     # kept in the Keychain: "a manifest must exist"

TITLES = {
    "cv_rules": "CV rules",
    "letter_rules": "Cover letter rules",
    "letter_template": "Cover letter template",
    "companies": "Career-site list",
    "master_cv": "Master CV",
}


def _manifest_path() -> Path:
    from . import config
    return config.DATA_DIR / "integrity.json"


def protected_files() -> dict[str, Path | None]:
    from . import agent1_cv, config
    try:
        cv = agent1_cv.find_cv()
    except Exception:  # noqa: BLE001
        cv = None
    return {
        "cv_rules": config.CV_INSTRUCTION,
        "letter_rules": config.LETTER_INSTRUCTION,
        "letter_template": config.LETTER_TEMPLATE,
        "companies": config.DATA_DIR / "companies.json",
        "master_cv": cv,
    }


def _signature(name: str, path: Path) -> str:
    key = hmac.new(vault.data_key(), b"jobhelper-integrity", hashlib.sha256).digest()
    mac = hmac.new(key, name.encode() + b"\0" + path.name.encode() + b"\0", hashlib.sha256)
    mac.update(path.read_bytes())
    return mac.hexdigest()


def _load() -> dict:
    try:
        data = json.loads(_manifest_path().read_text(encoding="utf-8"))
        return data.get("files", {}) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(files: dict) -> None:
    from . import config
    config.ensure_dirs()
    _manifest_path().write_text(json.dumps({"files": files}, indent=2, sort_keys=True), encoding="utf-8")


def active() -> bool:
    """Checks run only once a baseline exists (and the vault is usable)."""
    return vault.state() == "ok" and vault.get_secret(BASELINE_FLAG) == "1"


def check() -> list[dict]:
    """State of every protected file: ok | changed | missing | untracked | absent."""
    if not active():
        return []
    manifest, out = _load(), []
    for name, path in protected_files().items():
        exists = bool(path) and Path(path).is_file()
        entry = manifest.get(name)
        if not entry:
            state = "untracked" if exists else "absent"      # absent: never existed, nothing to protect
        elif not exists:
            state = "missing"
        else:
            good = hmac.compare_digest(entry.get("mac", ""), _signature(name, Path(path)))
            state = "ok" if good else "changed"
        out.append({"name": name, "title": TITLES[name], "state": state,
                    "file": Path(path).name if path else ""})
    return out


def problems() -> list[dict]:
    return [f for f in check() if f["state"] in ("changed", "missing", "untracked")]


KEPT = "approved"        # backups/approved/: the text of each file as it was when approved, to show what changed later
MAX_KEPT, MAX_SHOWN = 400_000, 40


def _text_of(path: Path) -> str:
    """What a watched file says, as lines of text (a Word or PDF file by its text)."""
    from . import agent1_cv
    try:
        return agent1_cv.read_cv_text(Path(path))[:MAX_KEPT]
    except Exception:  # noqa: BLE001 - a file that cannot be read has no text to compare
        return ""


def _kept_path(name: str) -> Path:
    return vault.backups_dir() / KEPT / f"{name}.txt"


def _keep(name: str, path: Path) -> None:
    try:
        target = _kept_path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        vault.write_text(target, _text_of(path))
    except Exception as e:  # noqa: BLE001 - approving must not fail because the copy could not be kept
        from . import trouble
        trouble.note("keeping a copy of an approved file", e)


def what_changed(name: str) -> dict:
    """What is different in a watched file since it was last approved:
    {title, file, known, added: [lines], removed: [lines], more}. `known` is False when no
    earlier text was kept (approved before copies were kept): then only the file can be read."""
    import difflib
    path = protected_files().get(name)
    out = {"title": TITLES.get(name, name), "file": Path(path).name if path else "", "known": False, "added": [], "removed": [], "more": 0}
    if name not in TITLES or not path or not Path(path).is_file():
        return out
    try:
        before = vault.read_text(_kept_path(name))
    except Exception:  # noqa: BLE001 - no copy, or one that cannot be opened
        return out
    old = [line.strip() for line in before.splitlines() if line.strip()]
    new = [line.strip() for line in _text_of(Path(path)).splitlines() if line.strip()]
    added, removed = [], []
    for line in difflib.ndiff(old, new):
        if line.startswith("+ "):
            added.append(line[2:][:300])
        elif line.startswith("- "):
            removed.append(line[2:][:300])
    out.update(known=True, added=added[:MAX_SHOWN], removed=removed[:MAX_SHOWN],
               more=max(0, len(added) - MAX_SHOWN) + max(0, len(removed) - MAX_SHOWN))
    return out


def approve(names: list[str] | None = None) -> list[str]:
    """Accept the current content of the given files (default: all) as trusted."""
    if vault.state() != "ok":
        return []
    manifest, done = _load(), []
    for name, path in protected_files().items():
        if names is not None and name not in names:
            continue
        if path and Path(path).is_file():
            manifest[name] = {"file": Path(path).name, "mac": _signature(name, Path(path))}
            _keep(name, Path(path))
        else:
            manifest.pop(name, None)
        done.append(name)
    _save(manifest)
    vault.set_secret(BASELINE_FLAG, "1")
    return done


def ensure_baseline() -> bool:
    """Sign everything once, the first time protection is set up. True if it did."""
    if vault.state() != "ok" or vault.get_secret(BASELINE_FLAG) == "1":
        return False
    approve()
    return True
