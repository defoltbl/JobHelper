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
        return ("The key for your data is not in the Keychain, so nothing can be opened. Open the Account card and paste your "
                "recovery key there (or run: python status.py security restore-key).")
    return ""            # 'off' is a choice (or no Keychain on this system), not a fault


def _jobs() -> str:
    try:
        jobs = store.load_jobs()
    except vault.VaultError:
        return "Your job list cannot be decrypted. Paste your recovery key in the Account card (or run: python status.py security restore-key)."
    except ValueError:
        return "Your job list (data/jobs.json) is damaged. Restore it from data/backups (python status.py security restore)."
    broken = [j for j in jobs if not isinstance(j, dict) or not j.get("id") or "status" not in j]
    if broken:
        return f"{len(broken)} entries in your job list are incomplete."
    lost = [j for j in jobs if j["status"] not in store.STATUSES]
    return (f"{len(lost)} {'job has' if len(lost) == 1 else 'jobs have'} a status the app does not know, so "
            f"{'it is' if len(lost) == 1 else 'they are'} in none of the lists (the first: {lost[0].get('company') or lost[0]['id']}). "
            "Run: python status.py repair-statuses") if lost else ""


def _responses() -> str:
    try:
        db.all_responses()
    except vault.VaultError:
        return "The replies database cannot be decrypted. Paste your recovery key in the Account card (or run: python status.py security restore-key)."
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
        return "Your Options cannot be decrypted, so the defaults are used. Paste your recovery key in the Account card."
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


def _folders() -> str:
    import os
    for folder in (config.DATA_DIR, config.LETTERS_DIR, config.TAILORED_CV_DIR):
        if folder.is_dir() and not os.access(folder, os.W_OK):
            return f"The folder {folder.name} cannot be written to. Check the disk and its permissions."
    return ""


CHECKS = [("Data key", _data_key), ("Job list", _jobs), ("Replies", _responses), ("Options", _settings),
          ("Rules and template unchanged", _rules), ("Master CV", _cv), ("Folders writable", _folders)]


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
