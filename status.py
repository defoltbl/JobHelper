#!/usr/bin/env python3
"""JobHelper — Agent 4 status tools (run any time, independent of the pipeline).

    python status.py list                     # show tracked jobs + statuses
    python status.py update adzuna-123 applied # set a status by hand
    python status.py update adzuna-123 interview --note "call on Fri 10:00"
    python status.py sync                      # read inbox replies & auto-update
    python status.py rebuild                   # regenerate the Excel table
    python status.py usage                      # show Claude usage (tokens / cost)
    python status.py usage --reset             # reset the usage counters

Statuses: found, letter_ready, applied, interview, offer, rejected, on_hold
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from jobhelper import (agent1_cv, agent2_search, agent3_letters, agent4_tracker,
                       agent5_responses, config, letters, store, usage)


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
    if args.status == "waiting" and not job.get("date_applied"):
        job["date_applied"] = date.today().isoformat()
    if args.note:
        job["notes"] = (f"[{date.today().isoformat()}] {args.note}\n" + job.get("notes", "")).strip()
    store.save_jobs(jobs)
    agent4_tracker.render_excel(jobs)
    print(f"✓ {job['title']} @ {job['company']} → {args.status}")
    return 0


def cmd_apply(args) -> int:
    """Mark a lead as applied → status 'waiting' (moves it to applications.xlsx)."""
    jobs = store.load_jobs()
    job = store.find(jobs, args.job_id)
    if not job:
        print(f"✗ No job with id '{args.job_id}'. Try: python status.py list")
        return 1
    job["status"] = "waiting"
    job["last_update"] = date.today().isoformat()
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

    made = 0
    for job in targets:
        done = agent3_letters.generate_for(job, cv_text=cv_text, cv_path=cv_path,
                                           rewrite_letter=args.letters)
        tag = ", ".join(k for k, v in done.items() if v) or "nothing new"
        print(f"  {job['title']} @ {job['company']}: {tag}")
        made += 1 if any(done.values()) else 0
    store.save_jobs(jobs)
    agent4_tracker.render_all(jobs)
    print(f"\nProcessed {len(targets)} job(s). CVs/letters in {config.TAILORED_CV_DIR} / {config.LETTERS_DIR}")
    print(usage.format_report())
    return 0


def scan_days() -> int:
    """How far back the email scan looks: "Scan emails from the last … days" in the app's
    Options, or IMAP_LOOKBACK_DAYS when that was never saved."""
    try:
        saved = int(config.ui_settings().get("scan_days") or 0)
    except (TypeError, ValueError):
        saved = 0
    return saved if saved > 0 else config.IMAP_LOOKBACK_DAYS


def cmd_sync(args) -> int:
    jobs = store.load_jobs()
    if not jobs:
        print("No jobs tracked yet. Run: python run.py")
        return 0
    days = args.days or scan_days()
    print(f"Reading inbox ({config.IMAP_USER}), last {days} days — read-only, nothing is sent or deleted …")
    try:
        stats = agent5_responses.process_inbox(jobs, lookback_days=days)
    except RuntimeError as e:
        print(f"✗ {e}")
        return 1
    agent5_responses.backfill_roles(jobs)
    agent5_responses.annotate_progress(jobs)
    pruned = agent2_search.prune_applied_leads(jobs)   # drop leads now applied to
    if pruned:
        print(f"  · removed {len(pruned)} lead(s) from new_jobs you've applied to")
    store.save_jobs(jobs)
    agent4_tracker.render_excel(jobs)
    agent5_responses.build_report(jobs)
    from jobhelper import notify
    invited = notify.invites_text(stats.get("invites") or [])
    if invited:
        notify.send(invited + ". Open JobHelper to prepare for it.", "Interview invitation")
    else:
        notify.send(agent5_responses.replies_text(stats), "Email scan finished")
    print(f"\nScanned {stats['scanned']} emails ({stats.get('skipped_unrelated', 0)} unrelated skipped) "
          f"→ {stats['new_responses']} new responses ({stats['rejections']} rejections), "
          f"{stats['status_updates']} status updates.")
    print(f"→ {config.EXCEL_PATH}")
    print(f"→ {config.RESPONSES_REPORT}\n")
    agent5_responses.print_report(jobs)
    print(f"\n{usage.format_report()}")
    if getattr(args, "summary", False):
        from jobhelper import db, summary
        week = summary.week(jobs, db.all_responses(), int(config.ui_settings().get("followup_days", 10) or 0))
        print("\n── The last 7 days ──")
        for row in summary.lines(week):
            print(f"  {row['label']}: {row['value']}  {row['note']}".rstrip())
        notify.send(summary.headline(week), "Your week")
    return 0


def cmd_responses(args) -> int:
    jobs = store.load_jobs()
    if args.scan:
        print(f"Reading inbox ({config.IMAP_USER}) — read-only …")
        try:
            stats = agent5_responses.process_inbox(jobs, lookback_days=args.days)
        except RuntimeError as e:
            print(f"✗ {e}")
            return 1
        agent5_responses.annotate_progress(jobs)
        store.save_jobs(jobs)
        agent4_tracker.render_excel(jobs)
        print(f"Scanned {stats['scanned']} emails → {stats['new_responses']} new responses.\n")
    agent5_responses.print_report(jobs)
    agent5_responses.build_report(jobs)
    print(f"\n→ {config.RESPONSES_REPORT}")
    return 0


def cmd_letters(_args) -> int:
    jobs = store.load_jobs()
    stats = letters.import_letters(jobs)
    store.save_jobs(jobs)
    agent4_tracker.render_excel(jobs)
    print(f"Cover letters in {config.COVER_LETTERS_DIR}:")
    print(f"  scanned {stats['scanned']}, linked {stats['linked']} to jobs, "
          f"seeded {stats['seeded']} past applications.")
    print(f"→ {config.EXCEL_PATH}")
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
    agent4_tracker.render_excel(jobs)
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
    from jobhelper import agent5_responses, email_client, vault
    print("Reading the inbox (read-only) …")
    emails = email_client.fetch_recent(args.days)
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
    days = args.days if args.days is not None else int(config.ui_settings().get("followup_days", followup.DEFAULT_DAYS))
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
            print(f"Gmail app password in Keychain: {'yes' if vault.get_secret(vault.IMAP_ACCOUNT) else 'no'}")
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
    parser = argparse.ArgumentParser(description="JobHelper status tools (Agent 4).")
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
    except vault.VaultError as e:
        print(f"✗ {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
