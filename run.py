#!/usr/bin/env python3
"""JobHelper — run the full 4-agent pipeline.

    python run.py                 # analyze CV → search your city (Options, or --where) → letters → Excel
    python run.py --where Brno    # search a different city
    python run.py --threshold 70  # only write letters for stronger matches
    python run.py --reuse-profile # skip Agent 1, reuse the last CV analysis

Uses your Claude subscription via the Claude Code CLI (no API key needed).
"""
from __future__ import annotations

import argparse
import sys

from jobhelper import (agent1_cv, agent2_search, agent3_letters, agent4_tracker, config, integrity, job_sources, letters, llm, notify, store, usage, vault)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the JobHelper pipeline.")
    parser.add_argument("--where", default="", help="City to search in (default: the city saved in the app's Options)")
    parser.add_argument("--source", default="czech",
                        choices=["czech", "linkedin", "remote", "adzuna", "jooble", "all"],
                        help="Job source: czech=jobs.cz+prace.cz+LinkedIn (default), or linkedin/remote/adzuna/jooble/all")
    parser.add_argument("--include-remote", action="store_true",
                        help="Also add RemoteOK + We Work Remotely remote roles to the search")
    parser.add_argument("--threshold", type=int, default=config.DEFAULT_THRESHOLD,
                        help=f"Min match score to write a cover letter + CV (default {config.DEFAULT_THRESHOLD}; 50-59 are flagged 'moderate')")
    parser.add_argument("--per-query", type=int, default=15, help="Results per search query")
    parser.add_argument("--all-languages", action="store_true",
                        help="Include Czech-language ads too (default: English-only)")
    parser.add_argument("--max-age-days", type=int, default=config.MAX_JOB_AGE_DAYS,
                        help=f"Only keep jobs posted within N days (default {config.MAX_JOB_AGE_DAYS}; 0 = no limit)")
    parser.add_argument("--no-letters-import", action="store_true",
                        help="Don't import your own cover letters (data/my_letters/)")
    parser.add_argument("--no-tailor-cv", action="store_true",
                        help="Don't generate keyword-tailored CVs for strong matches")
    parser.add_argument("--reuse-profile", action="store_true", help="Reuse last CV analysis instead of re-running Agent 1")
    parser.add_argument("--skip-search", action="store_true", help="Skip Agent 2 (re-score existing jobs only)")
    # Options saved in the desktop app are the defaults here too, so the weekly
    # scheduled run searches the same way as the Run search button.
    saved = config.ui_settings()
    known = {"where", "source", "include_remote", "threshold", "per_query",
             "all_languages", "max_age_days"}
    parser.set_defaults(**{k: v for k, v in saved.items() if k in known})
    args = parser.parse_args()

    config.ensure_dirs()
    config.apply_ui_settings(saved)
    try:
        if vault.protect_all()["state"] == "locked":
            vault.data_key()                     # raises with the reason and the fix
        changed = [f["title"] for f in integrity.problems()]
    except vault.VaultError as e:
        print(f"✗ {e}")
        return 2
    if changed:
        print("✗ Changed outside the app: " + ", ".join(changed) + ".\n"
              "  Nothing was generated. Check the files, then approve them in the app's\n"
              "  Account card or with:  python status.py security approve")
        return 2
    if not args.skip_search and not str(args.where or "").strip():
        print("✗ No city to search in. Choose one in the app's Options, or pass it: python run.py --where Brno")
        return 1
    if config.using_paid_api():
        print("✗ " + llm.PAID_API_MESSAGE)
        return 2

    # ── Agent 1: analyze CV ─────────────────────────────────────────────
    profile = agent1_cv.load_profile(current_only=True) if args.reuse_profile else None
    if profile is None:
        print("① Agent 1: analyzing your CV …")
        try:
            profile = agent1_cv.analyze()
        except (FileNotFoundError, ValueError) as e:
            print(f"   ✗ {e}")
            return 1
        print(f"   CV: {profile.get('_cv_file')} | seniority: {profile.get('seniority')} "
              f"| target roles: {', '.join(profile.get('target_roles', [])[:4])}")
    else:
        print(f"① Agent 1: reusing saved profile ({profile.get('_cv_file')})")

    jobs = store.load_jobs()

    # ── Agent 2: search ─────────────────────────────────────────────────
    if not args.skip_search:
        queries = (saved.get("queries") or profile.get("search_queries")
                   or profile.get("target_roles") or [])
        # what Options ticks (the weekly run), unless --source / --include-remote were typed on the command line
        typed = any(a.startswith(("--source", "--include-remote")) for a in sys.argv[1:])
        if typed:                       # typed by hand: --include-remote adds the remote boards to any --source
            choice = job_sources.SourceChoice.from_command_line(args.source, args.include_remote)
        else:
            choice = job_sources.SourceChoice.from_options(saved)
        print(f"\n② Agent 2: searching {args.where} ({', '.join(choice.names())}) for {len(queries)} queries …")
        # the same settings as the window's Run search (the Options with their defaults), with what was typed here
        from jobhelper import ui_api
        options = {**ui_api.Api().options(), "where": args.where, "per_query": args.per_query,
                   "all_languages": args.all_languages, "max_age_days": args.max_age_days}
        settings = agent2_search.SearchSettings.from_options(options, agent1_cv.level_of(profile))
        filtered = []
        try:
            new_jobs = settings.run(queries, choice, dropped=filtered)
        except RuntimeError as e:
            print(f"   ✗ {e}")
            return 1
        # Skip only the SAME role at a company you've already applied to /
        # been rejected by. Different roles at the same company are kept.
        took = agent2_search.take_in(jobs, new_jobs, english_only=settings.english_only, dropped=filtered)
        added = took["added"]
        msg = f"   found {took['found']} listings — {added} new, {took['skipped']} already tracked"
        if took["closed"]:
            msg += f"; {took['closed']} earlier ones no longer accept applications"
        if took["known"]:
            msg += f"; skipped {took['known']} you've already applied to (same role & company)"
        print(msg)
        store.save_jobs(jobs)
    else:
        print("\n② Agent 2: skipped")

    # ── Prune leads for roles you've already applied to ─────────────────
    pruned = agent2_search.prune_applied_leads(jobs)
    if pruned:
        print(f"   🧹 removed {len(pruned)} lead(s) you've already applied to")
        store.save_jobs(jobs)

    # ── Import your own cover letters (link + seed past applications) ────
    if not args.no_letters_import:
        lstats = letters.import_letters(jobs)
        if lstats["scanned"]:
            print(f"\n   📎 Cover letters: linked {lstats['linked']} to jobs, "
                  f"seeded {lstats['seeded']} past applications (from {config.COVER_LETTERS_DIR})")
            store.save_jobs(jobs)

    # ── Agent 3: score + cover letters + tailored CVs ───────────────────
    cv_text, cv_path = "", None
    if not args.no_tailor_cv:
        try:
            cv_path = agent1_cv.find_cv()
            cv_text = agent1_cv.read_cv_text(cv_path) if cv_path else ""
        except Exception as e:
            print(f"   (couldn't read master CV for tailoring: {e})")
    print(f"\n③ Agent 3: scoring jobs, writing cover letters & tailoring CVs (threshold {args.threshold}) …")
    try:
        stats = agent3_letters.process(jobs, profile, threshold=args.threshold, cv_text=cv_text, cv_path=cv_path)
    except llm.LimitReached as e:
        store.save_jobs(jobs)
        agent4_tracker.render_all(jobs)
        notify.send(notify.PAUSED + " Run it again after the reset.", "Search stopped early")
        print(f"\n⏸  {e}\n   What was finished is saved. Run again after the reset: the remaining jobs\n"
              "   are scored then, and nothing that is done is repeated.")
        return 3
    store.save_jobs(jobs)
    if not args.skip_search:                # the app's Last run card shows a command-line or weekly run too
        from datetime import datetime
        from jobhelper import ui_api
        ui_api.Api().note_run(when=datetime.now().strftime("%d %b %H:%M"), found="+%d new" % added, filtered=len(filtered),
                              letters=stats["letters"], cvs=stats.get("tailored_cvs", 0),
                              scored=stats.get("scored", 0), prefiltered=stats.get("prefiltered", 0),
                              cost=round(usage.session().get("cost_usd", 0.0), 2), cost_of="search")
    print(f"   scored {stats['scored']}, wrote {stats['letters']} letters, "
          f"{stats['tailored_cvs']} tailored CVs, skipped {stats['skipped']} already-scored")

    # ── Agent 4: Excel tables (new leads + applications) ────────────────
    print("\n④ Agent 4: building the tracking tables …")
    agent4_tracker.render_all(jobs)
    leads = sum(1 for j in jobs if j.get("status") in store.LEAD_STATUSES)
    apps = sum(1 for j in jobs if j.get("status") in store.APPLICATION_STATUSES)
    print(f"   → {config.NEW_JOBS_EXCEL}  ({leads} new leads)")
    print(f"   → {config.EXCEL_PATH}  ({apps} applications)")

    ready = sum(1 for j in jobs if j.get("status") == "letter_ready")
    print(f"\n✅ Done. {len(jobs)} jobs tracked, {ready} with cover letters ready to send.")
    print(f"   Letters: {config.LETTERS_DIR}")
    print("   Update statuses later with:  python status.py sync   (or)  python status.py update <id> <status>")

    print()
    print(usage.format_report())
    notify.send(notify.search_text(added if not args.skip_search else 0, stats["letters"]), "Search finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
