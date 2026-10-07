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
