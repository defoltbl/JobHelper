"""The app itself: the sign-in and connections, Claude usage, the log of small problems, backups, the start-up check and the change list.

Part of the window's back end: the facade `ui_api.Api` hands calls to this service."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import trouble
from .claude_cli import ClaudeCli
from .api_base import _guarded
from . import agent1_cv, agent4_tracker, health, config, integrity, pdf, store, usage, vault


def _claude_auth_status():
    """Ask the Claude program who is signed in: the same program the SDK asks with (tests replace this,
    so they never run the real one)."""
    return ClaudeCli.of_the_sdk().auth_status()


class SystemService:
    """The app itself: the sign-in and connections, Claude usage, the log of small problems, backups, the start-up check and the change list."""

    def __init__(self, app, editor, cv, desktop) -> None:
        """`app` is the facade (`ui_api.Api`): what this service needs from the others is asked through it."""
        self._app, self._editor, self._cv, self._desktop = app, editor, cv, desktop
        self._widget_reloader = None              # made on the first widget update: it remembers what it last asked macOS to redraw

    # ── notifications: whether macOS shows them ─────────────────
    _NOTIFICATION_SETTINGS = "x-apple.systempreferences:com.apple.Notifications-Settings.extension"

    def notification_permission(self):
        """"allowed", "off" (turned off in System Settings), "not asked" or "unknown" (outside the installed app)."""
        from . import notify
        return notify.notifier().permission()

    def test_notification(self):
        """One test notification from Options, with what macOS did in words."""
        from . import notify
        return notify.send_test()

    def open_notification_settings(self):
        """System Settings at its Notifications page, where JobHelper's notifications are turned on."""
        self._desktop.open(self._NOTIFICATION_SETTINGS)
        return {"ok": True}

    # ── read: status / data ─────────────────────────────────────
    def connections(self):
        claude, plan, claude_email = False, "", ""
        try:
            out = _claude_auth_status()
            try:
                info = json.loads(out.stdout)
                claude = info.get("loggedIn") is True
                plan = str(info.get("subscriptionType") or "")
                claude_email = str(info.get("email") or "")
            except ValueError:
                claude = '"loggedIn": true' in out.stdout
        except Exception:
            claude = False
        cv = agent1_cv.find_cv()
        changed = []
        try:
            changed = [f["title"] for f in integrity.problems()]
        except vault.VaultError:
            pass
        return {"vault": vault.state(), "changed_files": changed, "pdf": pdf.available(),
                "claude": claude, "plan": plan if claude else "",
                "claude_email": claude_email if claude else "",
                "paid_api": config.using_paid_api(),
                "email": config.has_imap(), "email_addr": config.IMAP_USER,
                "email2": bool(config.IMAP_USER_2 and config.IMAP_PASSWORD_2), "email2_addr": config.IMAP_USER_2,
                "email_host": config.IMAP_HOST, "email2_host": config.IMAP_HOST_2,       # a server typed by hand ('' = read from the address)
                "cv": cv.name if cv else ""}

    def usage_info(self):
        """The usage card: how much of each limit is used now, and when a used one frees."""
        totals = usage.totals()
        now = datetime.now()
        out = {"model": config.MODEL, "calls": totals["calls"], "cost": round(totals["cost_usd"], 2)}
        for name, w in usage.windows(now.timestamp()).items():
            out[name + "_used"] = None if w["used"] is None else min(100, max(0, round(w["used"] * 100)))
            resets = ""
            if w["resets_at"]:
                when = datetime.fromtimestamp(w["resets_at"])
                resets = when.strftime("%H:%M") if when.date() == now.date() else when.strftime("%d %b %H:%M")
            out[name + "_resets"] = resets
        # seconds until the next limit comes back, so the card can correct itself then (0 = none is counting down)
        coming = [w["resets_at"] - now.timestamp() for w in usage.windows(now.timestamp()).values() if w["resets_at"] and w["used"]]
        out["next_reset_in"] = int(min(coming)) + 1 if coming else 0
        return out

    # ── the check made when the app starts ──────────────────────
    def self_check(self, claude_signed_in=None):
        return health.run(claude_signed_in)

    # ── what the start-up check offers to put right ─────────────
    _RESTORABLE = {"jobs": ("JOBS_JSON", "job list"), "replies": ("RESPONSES_DB", "replies database")}

    def fix_problem(self, action):
        """Do what a problem of the start-up check offers (its `action`): {ok, msg}."""
        fixes = {"repair_statuses": self.repair_statuses,
                 "restore_jobs": lambda: self.restore_data("jobs"),
                 "restore_replies": lambda: self.restore_data("replies")}
        fix = fixes.get(str(action or ""))
        if fix is None:
            return {"ok": False, "msg": "The app has no fix for this problem. Select Show all to read what to do."}
        return fix()

    def repair_statuses(self):
        """Give every job whose status the app does not know a status it knows. A backup is made first."""
        try:
            jobs = store.load_jobs()
        except Exception as e:  # noqa: BLE001 - shown as the reason
            return {"ok": False, "msg": f"Your job list could not be read: {trouble._safe(e)}"}
        if not any(j.get("status") not in store.STATUSES for j in jobs):
            return {"ok": True, "fixed": 0, "msg": "Every job has a status the app knows. Nothing was changed."}
        try:
            vault.make_backup("before_status_repair")
            fixed = store.repair_statuses(jobs)
            store.save_jobs(jobs)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"The statuses were not repaired: {trouble._safe(e)}"}
        try:
            agent4_tracker.render_all(jobs)
        except Exception as e:  # noqa: BLE001 - the spreadsheets are made again on the next change
            trouble.note("repairing statuses: the spreadsheets", e)
        count = len(fixed)
        return {"ok": True, "fixed": count,
                "msg": f"Repaired {count} {'job' if count == 1 else 'jobs'}. Each one has a note that tells what was changed."}

    def restore_data(self, kind):
        """Put back the newest backup copy of the job list or the replies database that opens. The damaged
        file is moved into the backups (folder "damaged"), never deleted."""
        if kind not in self._RESTORABLE:
            return {"ok": False, "msg": "Only the job list and the replies database can be restored here."}
        attr, what = self._RESTORABLE[kind]
        path = getattr(config, attr)
        try:
            found = vault.newest_good_copy(path)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"The backups could not be read: {trouble._safe(e)}"}
        if found is None:
            return {"ok": False, "msg": f"No backup copy of your {what} opens, so nothing was changed. "
                                        "If you have a copy of your own, put it back in the app's data folder."}
        data, copy = found
        try:
            vault.set_aside(path, "damaged")
            vault.write_bytes(path, data)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"Your {what} was not restored: {trouble._safe(e)}"}
        made = datetime.fromtimestamp(copy.stat().st_mtime).strftime("%d %B %Y, %H:%M")
        return {"ok": True, "msg": f"Your {what} is back as it was on {made}. Changes made after that time are not in it. "
                                   "The damaged file is kept in the backups, in the folder damaged."}

    # ── the macOS widget ────────────────────────────────────────
    def widget_update(self):
        """Write the summary the macOS widget shows: {ok} (msg when it could not be written)."""
        from . import widget_feed
        try:
            if self._widget_reloader is None:
                self._widget_reloader = widget_feed.WidgetReloader.of_the_app()
            widget_feed.WidgetFeed(self._app, widget_feed.folder(), self._widget_reloader).write()
        except Exception as e:  # noqa: BLE001 - the widget keeps its last summary; noted for the log of small problems
            trouble.note("writing the summary for the widget", e)
            return {"ok": False, "msg": trouble._safe(e)}
        return {"ok": True}

    # ── what changed (CHANGELOG.md, shown in Help) ──────────────
    @_guarded(list)
    def limits(self):
        """How long what you type may be, from the module that checks it, so the window says it before the check refuses."""
        from . import assistant, config, cover_letter, form_answers, housekeeping, mailhosts, planner
        app = self._app                             # the Options' own limits: asked through the facade, like any other service
        return {"request": assistant.MAX_REQUEST, "question": form_answers.MAX_QUESTION, "answer": form_answers.MAX_ANSWER,
                "event_note": planner.MAX_EVENT_NOTE, "company_notes": dict(planner.NOTE_LIMITS),
                "experience_notes": config.MAX_EXPERIENCE_NOTES, "letter_hint": cover_letter.MAX_HINT,
                "list_word": app.MAX_WORD, "options": dict(app.OPTION_TEXTS),
                "company_name": app.MAX_COMPANY_NAME, "pay_role": app.MAX_PAY_ROLE,
                "salary_max": app.MAX_SALARY,
                "mail_server": mailhosts.MAX_HOST,
                # the ranges of the Options' numbers: a saved value is never cut to fit a box that allows less
                "numbers": {key: list(span) for key, span in app.OPTION_NUMBERS.items()},
                "shelf_days": [housekeeping.SHELF_MIN_DAYS, app.SHELF_MAX_DAYS], "look_back": list(config.LOOK_BACK_ONCE)}

    def changelog(self):
        """[{date, items}] from CHANGELOG.md, newest first; **words** become <b>words</b>."""
        import html
        try:
            text = (config.ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        except OSError:
            return []
        out = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("## "):
                out.append({"date": line[3:].strip(), "items": []})
            elif line.startswith("- ") and out:
                out[-1]["items"].append(re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(line[2:].strip(), quote=False)))
        return [entry for entry in out if entry["items"]]

    # ── what the app used, what went wrong, and backups: all without a terminal ──
    USAGE_NAMES = {"agent1_cv": "Reading your CV", "agent3_letters": "Scoring jobs and writing letters", "agent3_cv": "Adapting CVs",
                   "agent5_responses": "Reading replies", "form_answers": "Form answers", "assistant": "Questions to the assistant", "interview_prep": "Interview preparation",
                   "usage_ping": "Asking how much is left", "limit_check": "Asking how much is left", "general": "Other"}

    def usage_overview(self):
        """Everything the app has asked Claude so far: {calls, cost, kinds: [{name, calls, cost}]}, most used first.
        The cost is what the same work would have cost through the paid API; nothing was billed."""
        totals = usage.totals()
        kinds: dict[str, dict] = {}
        for tag, d in usage.by_tag().items():
            name = self.USAGE_NAMES.get(tag, "Trials and other work" if tag.endswith("_trial") else tag.replace("_", " ").capitalize())
            row = kinds.setdefault(name, {"name": name, "calls": 0, "cost": 0.0})
            row["calls"] += int(d["calls"])
            row["cost"] += float(d["cost_usd"])
        rows = sorted(kinds.values(), key=lambda r: -r["cost"])
        for row in rows:
            row["cost"] = round(row["cost"], 2)
        return {"calls": int(totals["calls"]), "cost": round(float(totals["cost_usd"]), 2), "kinds": rows}

    def trouble_log(self, most=25):
        """The last lines of the log of errors the app carried on after, newest first: {lines, total, file}."""
        path = config.DATA_DIR / trouble.LOG_NAME
        try:
            lines = [ln.strip() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        except OSError:
            lines = []
        return {"lines": list(reversed(lines[-int(most):])), "total": len(lines), "file": trouble.LOG_NAME}

    def show_trouble_log(self):
        path = config.DATA_DIR / trouble.LOG_NAME
        if not path.is_file():
            return {"ok": False, "msg": "There is no log yet: nothing has gone wrong."}
        self._desktop.reveal(path)
        return {"ok": True}

    def backup_all(self):
        """One encrypted backup of everything: the data, your CV, your letters, the documents, the rules."""
        try:
            done = vault.backup_everything()
        except Exception as e:  # noqa: BLE001 - shown as the reason
            return {"ok": False, "msg": f"The backup was not made: {trouble._safe(e)}"}
        return {"ok": True, "folder": done["folder"].name,
                "msg": f"Backed up {done['files']} files ({done['bytes'] / 1_048_576:.1f} MB), encrypted, in the folder {done['folder'].name} of the app's backups."}

    def backup_check(self):
        """Prove that backups can be restored: make one, restore it into a throwaway folder, compare."""
        try:
            report = vault.restore_test()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"The backups could not be checked: {trouble._safe(e)}"}
        bad = [f["name"] for f in report["files"] if not f["ok"]] + list(report["older"]["unreadable"])
        if report["ok"]:
            return {"ok": True, "msg": f"Your backups can be restored: {len(report['files'])} files compared with the live data, "
                                       f"{report['older']['readable']} of {report['older']['files']} older backup files can be opened."}
        return {"ok": False, "msg": "Something is wrong with the backups: " + ", ".join(bad[:6]) + ("…" if len(bad) > 6 else "") + "."}

    def backup_export(self, folder):
        """Save a readable (not encrypted) copy of the newest full backup into an empty folder the person chose."""
        text = str(folder or "")
        if text.startswith("file://"):
            from urllib.parse import unquote, urlparse
            text = unquote(urlparse(text).path)
        target = Path(text) if text else None
        if target is None or not target.is_dir():
            return {"ok": False, "msg": "Choose a folder that exists."}
        if any(p for p in target.iterdir() if p.name != ".DS_Store"):
            return {"ok": False, "msg": "Choose an empty folder, so that nothing in it is mixed up or replaced."}
        data = config.DATA_DIR.resolve()
        if target.resolve() == data or data in target.resolve().parents:
            return {"ok": False, "msg": "Choose a folder outside the app's own data folder."}
        fulls = sorted((p for p in vault.backups_dir().glob("everything_*") if p.is_dir()), key=lambda p: p.name)
        if not fulls:
            made = self.backup_all()
            if not made.get("ok"):
                return made
            fulls = sorted((p for p in vault.backups_dir().glob("everything_*") if p.is_dir()), key=lambda p: p.name)
        try:
            count = vault.restore_backup(fulls[-1], target)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"The copy was not made: {trouble._safe(e)}"}
        return {"ok": True, "msg": f"Saved {count} readable files from the backup {fulls[-1].name}. They are not encrypted: "
                                   "keep that folder safe, and delete it when you no longer need it."}
