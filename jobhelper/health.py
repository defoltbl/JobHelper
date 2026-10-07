"""A short self-check when the app starts.

Reads only. Each check answers one question a person can act on; the window
shows one line when something is wrong and nothing when all is well.
"""
from __future__ import annotations

from typing import Any

from . import agent1_cv, config, db, integrity, store, vault


def _check(name: str, fn) -> dict[str, Any]:
    """Run one check: fn returns '' (fine) or what is wrong and what to do."""
    try:
        problem = fn() or ""
    except Exception as e:  # noqa: BLE001 - a crashing check is itself a finding
        problem = f"The check itself failed ({type(e).__name__}: {e})."
    return {"name": name, "ok": not problem, "problem": problem}


def _data_key() -> str:
    state = vault.state()
    if state == "locked":
        return ("The key for your data is not in the Keychain, so nothing can be opened. "
                "Put it back with: python status.py security restore-key")
    return ""            # 'off' is a choice (or no Keychain on this system), not a fault


def _jobs() -> str:
    try:
        jobs = store.load_jobs()
    except vault.VaultError:
        return "Your job list cannot be decrypted. Restore the key (python status.py security restore-key)."
    except ValueError:
        return "Your job list (data/jobs.json) is damaged. Restore it from data/backups (python status.py security restore)."
    broken = [j for j in jobs if not isinstance(j, dict) or not j.get("id") or "status" not in j]
    return f"{len(broken)} entries in your job list are incomplete." if broken else ""


def _responses() -> str:
    try:
        db.all_responses()
    except vault.VaultError:
        return "The replies database cannot be decrypted. Restore the key (python status.py security restore-key)."
    except Exception:  # noqa: BLE001
        return "The replies database (data/responses.db) is damaged. Restore it from data/backups."
    return ""


def _settings() -> str:
    path = config.DATA_DIR / "ui_settings.json"
    if not path.is_file():
        return ""
    try:
        import json
        if not isinstance(json.loads(vault.read_text(path)), dict):
            raise ValueError
    except vault.VaultError:
        return "Your Options cannot be decrypted, so the defaults are used. Restore the key."
    except ValueError:
        return "Your saved Options are damaged, so the defaults are used. Open Options and press Save to write them again."
    return ""


def _rules() -> str:
    changed = [f["title"] for f in integrity.problems()]
    return ("Changed outside the app: " + ", ".join(changed) + ". Approve them in the Account card if you made the change."
            ) if changed else ""


def _cv() -> str:
    try:
        cv = agent1_cv.find_cv()
    except Exception:  # noqa: BLE001
        cv = None
    return "" if cv else "No master CV yet. Add yours in the Account card."


def _writing_files() -> str:
    missing = [name for name, path in (("CV rules", config.CV_INSTRUCTION), ("cover letter rules", config.LETTER_INSTRUCTION),
                                       ("cover letter template", config.LETTER_TEMPLATE)) if not path.is_file()]
    return ("Missing in the data folder: " + ", ".join(missing) + ". Letters and CVs cannot be written without them "
            "(see \"Using it with your own CV\" in README.md).") if missing else ""


def _folders() -> str:
    import os
    for folder in (config.DATA_DIR, config.LETTERS_DIR, config.TAILORED_CV_DIR):
        if folder.is_dir() and not os.access(folder, os.W_OK):
            return f"The folder {folder.name} cannot be written to. Check the disk and its permissions."
    return ""


CHECKS = [("Data key", _data_key), ("Job list", _jobs), ("Replies", _responses), ("Options", _settings),
          ("Rules and template unchanged", _rules), ("Master CV", _cv), ("Files for writing", _writing_files),
          ("Folders writable", _folders)]


def run(claude_signed_in: bool | None = None) -> dict[str, Any]:
    """{ok, checks: [{name, ok, problem}], problems, message}. `claude_signed_in` comes
    from the connection check the window already made (None = not known yet)."""
    checks = [_check(name, fn) for name, fn in CHECKS]
    if claude_signed_in is not None:
        checks.append({"name": "Claude", "ok": bool(claude_signed_in),
                       "problem": "" if claude_signed_in else "You are not signed in to Claude. Open the Account card and press Sign in."})
    bad = [c for c in checks if not c["ok"]]
    message = "" if not bad else (bad[0]["problem"] if len(bad) == 1 else f"{len(bad)} things need your attention. The first: {bad[0]['problem']}")
    return {"ok": not bad, "checks": checks, "problems": len(bad), "message": message}
