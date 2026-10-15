"""What the app learns from the data: insights, the last week, what a search filtered out, and a CV compared with the master.

Part of the window's back end: the facade `ui_api.Api` hands calls to this service."""
from __future__ import annotations

import os

from .api_base import _guarded
from . import (agent1_cv, agent2_search, agent4_tracker, summary, compare, config, db, insights, keywords, salary, store)


def list_position(index, size: int) -> int:
    """A place in a list as the window names it (a whole number, sometimes as 2.0 or "2"), or -1 when there is none."""
    try:
        place = int(index)
    except (TypeError, ValueError):
        return -1
    return place if not isinstance(index, bool) and 0 <= place < size and place == float(index) else -1


class InsightsService:
    """What the app learns from the data: insights, the last week, what a search filtered out, and a CV compared with the master."""

    def __init__(self, app, editor, cv, desktop) -> None:
        """`app` is the facade (`ui_api.Api`): what this service needs from the others is asked through it."""
        self._app, self._editor, self._cv, self._desktop = app, editor, cv, desktop

    # ── the last seven days ─────────────────────────────────────
    @_guarded(dict)
    def week_summary(self):
        w = summary.week(store.load_jobs(), db.all_responses(), int(self._app.options().get("followup_days") or 0))
        return {"from": w["from"], "to": w["to"], "lines": summary.lines(w), "headline": summary.headline(w)}

    # ── what the last search filtered out ───────────────────────
    @_guarded(dict)
    def filtered_out(self):
        """Postings the last search removed before scoring, each with its reason.
        The stored posting itself is left out: the window only needs to know whether it can come back."""
        data = agent2_search.load_dropped()
        rows = [{**{k: v for k, v in r.items() if k != "job"},
                 "can_return": isinstance(r.get("job"), dict) and bool(r["job"].get("id"))
                               and r.get("group") not in agent2_search.NO_BRING_BACK}
                for r in data["rows"]]
        return {"when": data["when"], "total": data["total"], "rows": rows}

    def bring_back(self, index):
        """Put a filtered-out posting into New Jobs; the next search run scores it like any other."""
        data = agent2_search.load_dropped()
        rows = data["rows"]
        index = list_position(index, len(rows))
        if index < 0:
            return {"ok": False, "msg": "That posting is not in the list any more."}
        row = rows[index]
        posting = row.get("job")
        if not isinstance(posting, dict) or not posting.get("id"):
            return {"ok": False, "msg": "This posting was saved without its details. Run a search, then bring it back."}
        if row.get("group") in agent2_search.NO_BRING_BACK:
            return {"ok": False, "msg": "The next search would remove it again for the same reason."}
        jobs = store.load_jobs()
        if store.find(jobs, posting["id"]):
            return {"ok": False, "msg": "This posting is already in your lists."}
        job = store.normalise(dict(posting))
        job["status"] = "found"
        job["brought_back"] = row.get("reason", "")       # why it was filtered, for the record
        job["prefilter_override"] = True                  # you chose it: the free pre-filter must not skip it
        if not job.get("desired_monthly_czk"):
            level = (agent1_cv.load_profile() or {}).get("seniority", "junior")
            monthly, annual = salary.estimate(job.get("title", ""), level)
            job["desired_monthly_czk"], job["desired_annual_czk"] = monthly or "", annual or ""
        store.upsert(jobs, [job])
        store.save_jobs(jobs)
        agent4_tracker.render_all(jobs)
        live = self._editor.live
        if live is not None and not store.find(live, job["id"]):
            live.append(dict(job))                        # a run in progress must not lose it
        del rows[index]
        agent2_search.save_dropped(rows, when=data["when"])
        return {"ok": True, "title": job.get("title", "")}

    def open_filtered(self, index):
        rows = agent2_search.load_dropped()["rows"]
        index = list_position(index, len(rows))
        url = str(rows[index].get("url") or "") if index >= 0 else ""
        if not url.startswith(("http://", "https://")):
            return {"ok": False}
        self._desktop.open(url)
        return {"ok": True}

    # ── master CV next to an adapted one ────────────────────────
    def comparable(self, j) -> bool:
        name = j.get("tailored_cv_file", "")
        master = agent1_cv.find_cv()
        return bool(name) and name.endswith(".docx") and (config.TAILORED_CV_DIR / name).is_file() \
            and master is not None and str(master).lower().endswith(".docx")

    @_guarded(dict)
    def cv_compare(self, job_id):
        j = store.find(store.load_jobs(), job_id)
        if not j or not self.comparable(j):
            return {"ok": False, "msg": "There is no adapted Word CV for this job to compare."}
        try:
            result = compare.compare(agent1_cv.find_cv(), config.TAILORED_CV_DIR / j["tailored_cv_file"])
        except Exception:  # noqa: BLE001
            return {"ok": False, "msg": "The two CV files could not be read."}
        # adapted before the master CV was last changed: differences outside the adapted parts come from the older master
        adapted = config.TAILORED_CV_DIR / j["tailored_cv_file"]
        older = os.path.getmtime(adapted) < os.path.getmtime(agent1_cv.find_cv())
        return {"ok": True, "company": j["company"], "title": j["title"], "file": j["tailored_cv_file"],
                "older_master": older, **result}

    # ── insights (worked out locally, no model call) ────────────
    @_guarded(dict)
    def insights(self):
        jobs, opts = store.load_jobs(), self._app.options()
        threshold = int(opts.get("threshold") or 30)
        return {"works": insights.what_works(jobs, db.all_responses()),
                "keywords": insights.keyword_stats(jobs, list(opts.get("queries") or []), threshold),
                "gaps": insights.skill_gaps(jobs, self._cv.text()),
                "salaries": insights.salaries(jobs),
                "trends": insights.trends(jobs, db.all_responses()),
                "reply_times": insights.reply_times(jobs, db.all_responses()),
                "low_scores": insights.low_score_reasons(jobs, self._cv.text(), threshold),
                "threshold": threshold, "min_group": insights.MIN_GROUP}

    def read_ahead(self):
        """Prepare what the Insights view needs (the keywords of every posting and of the CV), gently:
        for a background thread, so the first Insights view opens at once. Returns how many texts were read."""
        return keywords.read_ahead([j.get("description") or "" for j in store.load_jobs()] + [self._cv.text()])
