#!/usr/bin/env python3
"""JobHelper: status tools (run any time, independent of the pipeline).

    python status.py list                     # show tracked jobs + statuses
    python status.py apply adzuna-123          # you applied: the lead becomes an application (status "waiting")
    python status.py update adzuna-123 interview --note "call on Fri 10:00"
    python status.py sync                      # read inbox replies & auto-update
    python status.py rebuild                   # regenerate the Excel table
    python status.py usage                      # show Claude usage (tokens / cost)
    python status.py usage --reset             # reset the usage counters

Statuses: found, letter_ready, not_interested, waiting, interview, offer, rejected, on_hold
(`python status.py --help` lists every command.)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from jobhelper import (agent1_cv, agent2_search, agent3_letters, agent4_tracker,
                       agent5_responses, config, letters, llm, store, usage, vault)


def cmd_list(_args) -> int:
    jobs = store.load_jobs()
    if not jobs:
        print("No jobs tracked yet. Run: python run.py")
        return 0
    ordered = sorted(jobs, key=lambda j: (-(j.get("match_score") or 0),))
    print(f"{'ID':<16} {'%':>3}  {'STATUS':<12} TITLE @ COMPANY")
    print("-" * 78)
    for j in ordered:
        print(f"{j['id']:<16} {str(j.get('match_score') or ''):>3}  "
              f"{j.get('status',''):<12} {j['title']} @ {j['company']}")
    print(f"\n{len(jobs)} jobs. Excel: {config.EXCEL_PATH}")
    return 0


def cmd_update(args) -> int:
    if args.status not in store.STATUSES:
        print(f"✗ Unknown status '{args.status}'. Valid: {', '.join(store.STATUSES)}")
        return 1
    jobs = store.load_jobs()
    job = store.find(jobs, args.job_id)
    if not job:
        print(f"✗ No job with id '{args.job_id}'. Try: python status.py list")
        return 1
    job["status"] = args.status
    job["last_update"] = date.today().isoformat()
    job["status_by_hand"] = datetime.now().isoformat(timespec="seconds")       # emails older than this do not change it back
    if args.status == "waiting" and not job.get("date_applied"):
        job["date_applied"] = date.today().isoformat()
    if args.note:
        job["notes"] = (f"[{date.today().isoformat()}] {args.note}\n" + job.get("notes", "")).strip()
    store.save_jobs(jobs)
    agent4_tracker.render_all(jobs)
    print(f"✓ {job['title']} @ {job['company']} → {args.status}")
    return 0


def cmd_apply(args) -> int:
    """Mark a lead as applied → status 'waiting' (moves it to applications.xlsx)."""
    jobs = store.load_jobs()
    job = store.find(jobs, args.job_id)
    if not job:
        print(f"✗ No job with id '{args.job_id}'. Try: python status.py list")
        return 1
    if job.get("status") not in store.LEAD_STATUSES:
        print(f"✗ {job['title']} @ {job['company']} is not a new job any more (status: {job.get('status')}). "
              f"To change the status of an application: python status.py update {job['id']} <status>")
        return 1
    job["status"] = "waiting"
    job["last_update"] = date.today().isoformat()
    job["status_by_hand"] = datetime.now().isoformat(timespec="seconds")
    if not job.get("date_applied"):
        job["date_applied"] = date.today().isoformat()
    if args.note:
        job["notes"] = (f"[{date.today().isoformat()}] {args.note}\n" + job.get("notes", "")).strip()
    store.save_jobs(jobs)
    agent4_tracker.render_all(jobs)
    print(f"✓ Applied: {job['title']} @ {job['company']} → waiting (moved to applications.xlsx)")
    return 0


def cmd_retailor(args) -> int:
    """Generate a cover letter + tailored CV on demand for a job (or all
    letter-ready leads missing a tailored CV)."""
    jobs = store.load_jobs()
    try:
        cv_path = agent1_cv.find_cv()
        cv_text = agent1_cv.read_cv_text(cv_path) if cv_path else ""
    except Exception:
        cv_path, cv_text = None, ""

    if args.job_id:
        targets = [store.find(jobs, args.job_id)]
        if targets == [None]:
            print(f"✗ No job with id '{args.job_id}'. Try: python status.py list")
            return 1
    else:
        # Any qualifying lead (score >= threshold) missing a letter or a tailored CV;
        # with --all, every qualifying lead (re-adapts CVs made by an older method).
        targets = [j for j in jobs if j.get("status") in store.LEAD_STATUSES
                   and isinstance(j.get("match_score"), int) and j["match_score"] >= config.DEFAULT_THRESHOLD
                   and (args.all or not j.get("cover_letter_file") or not j.get("tailored_cv_file"))]
        if not targets:
            print("Nothing to do — every qualifying lead already has a letter + tailored CV.")
            return 0

    stopped = ""
    for job in targets:
        try:
            done = agent3_letters.generate_for(job, cv_text=cv_text, cv_path=cv_path,
                                               rewrite_letter=args.letters)
        except (llm.LimitReached, llm.PaidApiRefused) as e:      # nothing more can be written now: what is done is saved
            stopped = str(e)
            break
        tag = ", ".join(k for k, v in done.items() if v) or "nothing new"
        print(f"  {job['title']} @ {job['company']}: {tag}")
    store.save_jobs(jobs)
    agent4_tracker.render_all(jobs)
    if stopped:
        print(f"\n⏸  {stopped}\n   What was written is saved. Run this again later: jobs that have their documents are not done twice.")
        return 3
    print(f"\nProcessed {len(targets)} job(s). CVs/letters in {config.TAILORED_CV_DIR} / {config.LETTERS_DIR}")
    print(usage.format_report())
    return 0


def mail_problem(error: Exception) -> str:
    """Why the mailbox could not be read, in a sentence (the password is never part of it)."""
    import imaplib
    if isinstance(error, imaplib.IMAP4.error):
        return "Couldn't sign in to your email. Check its password in the app's Account card."
    from jobhelper import email_client
    if email_client.untrusted(error):
        return email_client.UNTRUSTED
    if isinstance(error, OSError):
        return "The mail server could not be reached. Check your connection and run this again."
    return f"The mailbox could not be read ({type(error).__name__})."


class Stopped(Exception):
    """A command that cannot go on and has already said why. `code` is what the command returns: 1 when it failed,
    3 when Claude's limit stopped it (what was done is saved)."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def _mail_failed(error: Exception) -> Stopped:
    """Say why the mailbox could not be read, in one sentence: no mailbox connected says so itself; anything else is
    told by `mail_problem`, never as a traceback (the weekly run's log gets a sentence)."""
    print(f"✗ {error}" if isinstance(error, RuntimeError) else f"✗ {mail_problem(error)}")
    return Stopped(1)


def scan_inbox(jobs: list, days: int):
    """Read the replies (read-only) the way every command here does. Claude's limit: what was read is saved, and the
    command stops with 3; a mailbox problem: one sentence, and 1."""
    try:
        return agent5_responses.process_inbox(jobs, lookback_days=days)
    except llm.LimitReached as e:
        store.save_jobs(jobs)                    # the replies read so far have already changed these jobs
        agent4_tracker.render_all(jobs)
        print(f"⏸  {e}\n   What was read is saved. Run it again after the reset: nothing is read twice.")
        raise Stopped(3) from e
    except Exception as e:  # noqa: BLE001 - said in a sentence
        raise _mail_failed(e) from e


def fetch_mail(days):
    """The recent messages, without Claude; a mailbox problem is one sentence, and the command stops with 1."""
    from jobhelper import email_client
    try:
        return email_client.fetch_recent(days).messages
    except Exception as e:  # noqa: BLE001 - said in a sentence
        raise _mail_failed(e) from e


def cmd_sync(args) -> int:
    jobs = store.load_jobs()
    if not jobs:
        print("No jobs tracked yet. Run: python run.py")
        return 0
    days = args.days or config.scan_days()
    print(f"Reading inbox ({config.IMAP_USER}), last {days} days — read-only, nothing is sent or deleted …")
    stats = scan_inbox(jobs, days)
    pruned = agent5_responses.after_scan(jobs)         # leads now applied to are dropped
    if pruned:
        print(f"  · removed {len(pruned)} lead(s) from new_jobs you've applied to")
    store.save_jobs(jobs)
    agent4_tracker.render_all(jobs)
    agent5_responses.build_report(jobs)
    from jobhelper import notify
    text, title, _urgent = stats.notice()
    notify.send(text, title)
    print(f"\nScanned {stats.scanned} emails ({stats.skipped_unrelated} unrelated skipped) "
          f"→ {stats.new_responses} new responses ({stats.rejections} rejections), "
          f"{stats.status_updates} status updates.")
    for warning in stats.warnings:
        print(f"  ! {warning}")
    print(f"→ {config.EXCEL_PATH}")
    print(f"→ {config.RESPONSES_REPORT}\n")
    agent5_responses.print_report(jobs)
    print(f"\n{usage.format_report()}")
    if getattr(args, "summary", False):
        from jobhelper import db, followup, summary
        week = summary.week(jobs, db.all_responses(), followup.saved_days())
        print("\n── The last 7 days ──")
        for row in summary.lines(week):
            print(f"  {row['label']}: {row['value']}  {row['note']}".rstrip())
        notify.send(summary.headline(week), "Your week")
    return 0


def cmd_responses(args) -> int:
    jobs = store.load_jobs()
    if args.scan:
        print(f"Reading inbox ({config.IMAP_USER}) — read-only …")
        stats = scan_inbox(jobs, args.days or config.scan_days())
        agent5_responses.annotate_progress(jobs)
        store.save_jobs(jobs)
        agent4_tracker.render_all(jobs)
        print(f"Scanned {stats.scanned} emails → {stats.new_responses} new responses.\n")
        for warning in stats.warnings:
            print(f"  ! {warning}")
    agent5_responses.print_report(jobs)
    agent5_responses.build_report(jobs)
    print(f"\n→ {config.RESPONSES_REPORT}")
    return 0


def cmd_letters(_args) -> int:
    jobs = store.load_jobs()
    stats = letters.import_letters(jobs)
    store.save_jobs(jobs)
    agent4_tracker.render_all(jobs)
    print(f"Cover letters in {config.COVER_LETTERS_DIR}:")
    print(f"  scanned {stats['scanned']}, linked {stats['linked']} to jobs, "
          f"seeded {stats['seeded']} past applications.")
    print(f"→ {config.EXCEL_PATH}")
    return 0


repair_statuses = store.repair_statuses          # the same repair as the window's Repair button


def cmd_repair_statuses(_args) -> int:
    jobs = store.load_jobs()
    if not any(j.get("status") not in store.STATUSES for j in jobs):
        print("Every job has a status the app knows. Nothing to repair.")
        return 0
    backup = vault.make_backup("before_status_repair")
    fixed = repair_statuses(jobs)
    store.save_jobs(jobs)
    agent4_tracker.render_all(jobs)
    print(f"Repaired {len(fixed)} job(s) (backup: {backup.name}):")
    for j in fixed:
        print(f"   {j.get('company') or j['id']} – {j.get('title', '')}: now {j['status']}")
    return 0


def cmd_prune(_args) -> int:
    jobs = store.load_jobs()
    removed = agent2_search.prune_applied_leads(jobs)
    store.save_jobs(jobs)
    agent4_tracker.render_all(jobs)
    print(f"Removed {len(removed)} lead(s) from new_jobs you've already applied to:")
    for j in removed:
        print(f"   {j['company']} — {j['title']}")
    return 0


def cmd_rebuild(_args) -> int:
    jobs = store.load_jobs()
    agent5_responses.annotate_progress(jobs)
    agent4_tracker.render_all(jobs)
    print(f"✓ Rebuilt {config.EXCEL_PATH} ({len(jobs)} jobs)")
    return 0


def cmd_usage(args) -> int:
    if args.reset:
        usage.reset()
        print("✓ Usage counters reset.")
        return 0
    print(usage.format_report(show_session=False))
    return 0


def cmd_pdf(args) -> int:
    """Make PDF copies of the adapted CVs and the letters this app wrote."""
    from jobhelper import agent3_letters, pdf
    if not pdf.available():
        print("LibreOffice is not installed, so PDFs cannot be made.\n"
              "Install it from https://www.libreoffice.org/download/ and run this again.")
        return 1
    made = skipped = failed = 0
    for job in store.load_jobs():
        docs = []
        if job.get("tailored_cv_file", "").endswith(".docx"):
            docs.append(config.TAILORED_CV_DIR / job["tailored_cv_file"])
        if agent3_letters._generated_letter(job):          # never the letters you wrote yourself
            docs.append((config.LETTERS_DIR / job["cover_letter_file"]).with_suffix(".docx"))
        for doc in docs:
            if not doc.is_file():
                continue
            if pdf.pdf_for(doc) and not args.all:
                skipped += 1
                continue
            out = pdf.to_pdf(doc)
            if out:
                made += 1
                pages = pdf.page_count(out)
                print(f"  ✓ {out.name}" + (f"   ({pages} pages!)" if pages > 1 else ""))
            else:
                failed += 1
                print(f"  ✗ {doc.name}")
    print(f"PDFs made: {made}, already there: {skipped}, failed: {failed}")
    return 0 if not failed else 1


def cmd_repair_emails(args) -> int:
    """Re-read the inbox text (read-only, no Claude usage) and fix replies that an
    older version filed wrongly because it could not read HTML-only emails."""
    from jobhelper import agent5_responses, vault
    print("Reading the inbox (read-only) …")
    emails = fetch_mail(args.days)                   # no mailbox, or it cannot be read: said, nothing changed
    jobs = store.load_jobs()
    backup = vault.make_backup("before_email_repair")
    stats = agent5_responses.repair_unread_bodies(jobs, emails)
    agent5_responses.annotate_progress(jobs)
    store.save_jobs(jobs)
    agent4_tracker.render_all(jobs)
    agent5_responses.build_report(jobs)
    print(f"Backup: {backup.name}")
    print(f"Rejections found in emails that were read as empty: {stats['rejections_found']} "
          f"({stats['jobs_rejected']} applications moved to rejected)")
    print(f"Emails queued to be read again by the next Scan email: {stats['requeued']}")
    return 0


def cmd_followups(args) -> int:
    """List applications that have had no reply for a while."""
    from jobhelper import db, followup
    days = args.days if args.days is not None else followup.saved_days()
    jobs = store.load_jobs()
    replies = followup.last_reply_by_job(db.all_responses())
    due = followup.due_jobs(jobs, db.all_responses(), days)
    if not due:
        print(f"No application has been waiting {days}+ days without a reply.")
        return 0
    print(f"Waiting {days}+ days without a reply ({len(due)}):")
    for j in sorted(due, key=lambda j: -followup.info(j, days, replies.get(j["id"]))["days_waiting"]):
        state = followup.info(j, days, replies.get(j["id"]))
        print(f"  {state['days_waiting']:>3} days  {j['company']} · {j['title']}   [{j['id']}]")
    return 0


def cmd_security(args) -> int:
    """Encryption, Keychain and tamper-check tools."""
    import getpass
    from pathlib import Path
    from jobhelper import integrity, vault
    try:
        if args.action == "status":
            print(f"Encryption: {vault.state()}   (ok = on, off = no Keychain, locked = key missing)")
            for path in vault.data_files():
                if path.exists():
                    print(f"  {'encrypted' if vault.file_is_encrypted(path) else 'PLAIN    '}  {path.name}")
            print(f"Mailbox password in the Keychain: {'yes' if vault.get_secret(vault.IMAP_ACCOUNT) else 'no'}")
            for f in integrity.check():
                print(f"  {f['state']:<9}  {f['title']}" + (f"  ({f['file']})" if f["file"] else ""))
        elif args.action == "protect":
            print(vault.protect_all())
        elif args.action == "approve":
            done = integrity.approve()
            print("Approved: " + ", ".join(integrity.TITLES[n] for n in done))
        elif args.action == "recovery-key":
            print("Keep this somewhere safe (a password manager). Anyone with it can read your data:\n")
            print("  " + vault.recovery_key())
        elif args.action == "restore-key":
            vault.restore_key(getpass.getpass("Recovery key: "))
            print("Key restored to the Keychain.")
        elif args.action == "backup":
            print(f"Encrypted backup written to {vault.make_backup('manual')}")
        elif args.action == "backup-all":
            done = vault.backup_everything()
            print(f"Everything backed up: {done['files']} files, {done['bytes'] / 1_048_576:.1f} MB, encrypted, in\n  {done['folder']}")
            print("It holds the app's data, your master CV, your own letters, the letters and CVs the app wrote,\n"
                  "the rule files and the letter template. To get it back:\n"
                  f"  python status.py security restore \"{done['folder']}\" <an empty folder>")
        elif args.action == "test-restore":
            report = vault.restore_test()
            print(f"Backup made: {report['backup']}, restored into a temporary folder and compared with the live data:")
            for f in report["files"]:
                print(f"  {'ok     ' if f['ok'] else 'PROBLEM'}  {f['name']}" + (f"  ({f['problem']})" if f["problem"] else ""))
            older = report["older"]
            print(f"Older backups: {older['readable']} of {older['files']} files can be decrypted.")
            for name in older["unreadable"]:
                print(f"  cannot be read: {name}")
            print("\n✅ Your backups can be restored." if report["ok"] else "\n✗ Something is wrong with the backups. See the lines above.")
            return 0 if report["ok"] else 1
        elif args.action == "restore":
            if len(args.paths) != 2:
                print("Usage: python status.py security restore <backup file or folder> <destination folder>")
                return 1
            n = vault.restore_backup(Path(args.paths[0]), Path(args.paths[1]))
            print(f"Decrypted {n} file(s) into {args.paths[1]}")
    except vault.VaultError as e:
        print(f"✗ {e}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="JobHelper status tools.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List tracked jobs").set_defaults(func=cmd_list)

    p_up = sub.add_parser("update", help="Set a job's status")
    p_up.add_argument("job_id")
    p_up.add_argument("status")
    p_up.add_argument("--note", default="", help="Add a dated note")
    p_up.set_defaults(func=cmd_update)

    p_apply = sub.add_parser("apply", help="Mark a lead as applied (status → waiting)")
    p_apply.add_argument("job_id")
    p_apply.add_argument("--note", default="", help="Add a dated note")
    p_apply.set_defaults(func=cmd_apply)

    p_sync = sub.add_parser("sync", help="Read inbox replies: update statuses + response DB")
    p_sync.add_argument("--days", type=int, default=None, help="How many days back to scan (default: the app's Options, else .env IMAP_LOOKBACK_DAYS)")
    p_sync.add_argument("--summary", action="store_true",
                        help="Afterwards, print the last 7 days in a few lines and send them as one notification (weekly run)")
    p_sync.set_defaults(func=cmd_sync)

    sub.add_parser("rebuild", help="Regenerate the Excel table").set_defaults(func=cmd_rebuild)
    sub.add_parser("prune", help="Remove new_jobs leads you've already applied to").set_defaults(func=cmd_prune)
    sub.add_parser("repair-statuses", help="Fix jobs whose status the app does not know (they show in no list)").set_defaults(func=cmd_repair_statuses)

    p_resp = sub.add_parser("responses", help="Show rejection/response analytics (Agent 5)")
    p_resp.add_argument("--scan", action="store_true", help="Scan inbox first for new responses")
    p_resp.add_argument("--days", type=int, default=None, help="With --scan: how many days back to scan")
    p_resp.set_defaults(func=cmd_responses)

    sub.add_parser("letters", help="Import your own cover letters (data/my_letters/)").set_defaults(func=cmd_letters)

    p_re = sub.add_parser("retailor", help="Generate cover letter + tailored CV on demand")
    p_re.add_argument("job_id", nargs="?", default=None, help="A specific job id (default: all letter-ready leads missing a tailored CV)")
    p_re.add_argument("--all", action="store_true", help="Re-adapt the CV for every qualifying lead, not only missing ones")
    p_re.add_argument("--letters", action="store_true",
                      help="Also rewrite letters this app generated (your own imported letters are never touched)")
    p_re.set_defaults(func=cmd_retailor)

    p_pdf = sub.add_parser("pdf", help="Make PDF copies of adapted CVs and app-written letters (needs LibreOffice)")
    p_pdf.add_argument("--all", action="store_true", help="Remake PDFs that already exist")
    p_pdf.set_defaults(func=cmd_pdf)

    p_rep = sub.add_parser("repair-emails", help="Fix replies misread because the email was HTML only (no Claude usage)")
    p_rep.add_argument("--days", type=int, default=None, help="How many days back (default: IMAP_LOOKBACK_DAYS)")
    p_rep.set_defaults(func=cmd_repair_emails)

    p_fu = sub.add_parser("followups", help="List applications with no reply for N days")
    p_fu.add_argument("--days", type=int, default=None, help="Override the number of days (default: the app's Options)")
    p_fu.set_defaults(func=cmd_followups)

    p_sec = sub.add_parser("security", help="Encryption, Keychain and tamper-check tools")
    p_sec.add_argument("action", choices=["status", "protect", "approve", "recovery-key", "restore-key", "backup", "backup-all", "restore", "test-restore"])
    p_sec.add_argument("paths", nargs="*", help="restore: <backup> <destination>")
    p_sec.set_defaults(func=cmd_security)

    p_use = sub.add_parser("usage", help="Show Claude usage (tokens / API-equiv. cost)")
    p_use.add_argument("--reset", action="store_true", help="Reset the usage counters")
    p_use.set_defaults(func=cmd_usage)

    args = parser.parse_args()
    from jobhelper import vault
    try:
        if args.cmd != "security":
            vault.protect_all()
        return args.func(args)
    except Stopped as stop:
        return stop.code
    except vault.VaultError as e:
        print(f"✗ {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
