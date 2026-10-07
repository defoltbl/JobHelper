"""What the search history says, worked out locally (no model call).

* what_works  - which kinds of role and which sources got confirmations and
                interviews, and which only rejections;
* keyword_stats - how each search keyword performs, so the ones that only
                  produce low scores can be dropped;
* skill_gaps  - technologies the postings ask for most that the CV does not
                show: a learning list. It is only ever displayed; nothing from
                it is added to a CV or a letter.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from . import keywords, store

MIN_GROUP = 3            # fewer applications than this say nothing reliable

# First match wins, so the more specific kinds come first.
_ROLE_TYPES = [
    ("AI / machine learning", r"\b(ai|a\.i\.|ml|machine learning|llm|genai|gen ai|nlp|deep learning|computer vision|data scien\w+|rag)\b"),
    ("Data", r"\b(data (engineer|analyst|analytics)|analytics|analyst|bi\b|business intelligence|etl|database|sql)\b"),
    ("QA / testing", r"\b(qa|quality assurance|tester|testing|test (engineer|automation)|sdet)\b"),
    ("IT support", r"\b(support|help ?desk|service desk|desktop|it (administrator|admin|operations|specialist|service)|sysadmin|system administrator|l1|l2)\b"),
    ("Mobile", r"\b(android|ios|mobile|kotlin)\b"),
    ("Software development", r"\b(software|developer|engineer|programmer|backend|back-end|frontend|front-end|full[- ]?stack|python|java|devops|cloud)\b"),
]
_ROLE_RE = [(name, re.compile(pattern, re.IGNORECASE)) for name, pattern in _ROLE_TYPES]


ROLE_UNKNOWN = "Role not recorded"


def role_type(title: str) -> str:
    if not (title or "").strip() or (title or "").strip().lower() in ("(existing application)", "(from email response)", "(unknown role)"):
        return ROLE_UNKNOWN                # an application the app knows only by its company
    for name, pattern in _ROLE_RE:
        if pattern.search(title or ""):
            return name
    return "Other"


def _source(job: dict[str, Any]) -> str:
    src = (job.get("source") or "").split("/")[0]
    return {"manual": "your own applications", "email": "found through emails", "": "unknown"}.get(src, src)


def _verdict(n: int, interviews: int, rejected: int, waiting: int) -> str:
    if n < MIN_GROUP:
        return "too few to say"
    if interviews:
        return "working: %d of %d reached an interview" % (interviews, n)
    if rejected == n:
        return "not working: all %d rejected" % n
    if rejected and rejected >= n - waiting and waiting:
        return "no interview yet: %d rejected, %d still waiting" % (rejected, waiting)
    return "no interview yet"


def what_works(jobs: list[dict[str, Any]], responses: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Outcomes of your applications grouped by kind of role and by source."""
    stages: dict[str, set[str]] = defaultdict(set)
    for r in responses:
        if r.get("job_id"):
            stages[r["job_id"]].add(r.get("stage", ""))
    apps = [j for j in jobs if j.get("status") in store.APPLICATION_STATUSES]

    def table(key_of):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for j in apps:
            groups[key_of(j)].append(j)
        rows = []
        for name, items in groups.items():
            interviews = sum(1 for j in items if j["status"] in ("interview", "offer")
                             or stages[j["id"]] & {"interview", "assessment", "offer"})
            rejected = sum(1 for j in items if j["status"] == "rejected")
            waiting = sum(1 for j in items if j["status"] in ("waiting", "on_hold"))
            replied = sum(1 for j in items if stages[j["id"]])
            rows.append({"name": name, "applications": len(items), "replied": replied, "interviews": interviews,
                         "rejected": rejected, "waiting": waiting,
                         "verdict": _verdict(len(items), interviews, rejected, waiting)})
        rows.sort(key=lambda r: (-r["interviews"], -r["applications"], r["name"]))
        return rows

    by_role = table(lambda j: role_type(j.get("title", "")))
    by_role.sort(key=lambda r: r["name"] == ROLE_UNKNOWN)          # the unknown group goes last
    return {"by_role": by_role, "by_source": table(_source), "applications": len(apps)}


def salaries(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """What the postings in the list say they pay (gross CZK per month), next to the target."""
    from . import salary
    rows = []
    for j in jobs:
        if j.get("status") not in store.LEAD_STATUSES | store.APPLICATION_STATUSES:
            continue
        pay = salary.stated(j)
        if not pay:
            continue
        target = j.get("desired_monthly_czk") or 0
        try:
            target = int(target)
        except (TypeError, ValueError):
            target = 0
        rows.append({"id": j["id"], "title": j.get("title", ""), "company": j.get("company", ""), "low": pay["low"],
                     "high": pay["high"], "text": pay["text"], "target": target, "score": j.get("match_score"),
                     "verdict": "" if not target else "above your target" if pay["low"] >= target
                                else "below your target" if pay["high"] < target else "around your target"})
    rows.sort(key=lambda r: (-(r["score"] or 0), -r["high"]))
    considered = sum(1 for j in jobs if j.get("status") in store.LEAD_STATUSES | store.APPLICATION_STATUSES)
    mids = sorted((r["low"] + r["high"]) // 2 for r in rows)
    return {"rows": rows, "stated": len(rows), "postings": considered,
            "median": mids[len(mids) // 2] if mids else 0, "lowest": min((r["low"] for r in rows), default=0),
            "highest": max((r["high"] for r in rows), default=0)}


_FILLER = {"junior", "senior", "entry", "level", "graduate", "intern", "trainee", "the", "and", "for", "in", "prague", "czech"}


def _query_words(query: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#]+", (query or "").lower()) if w not in _FILLER and len(w) > 1}


def keyword_of(job: dict[str, Any], queries: list[str]) -> tuple[str, bool]:
    """The search keyword a lead belongs to: the one recorded when it was found,
    else the best guess from the title (second value False = guessed)."""
    if job.get("query"):
        return job["query"], True
    title = set(re.findall(r"[a-z0-9+#]+", (job.get("title") or "").lower()))
    best, score = "", 0
    for q in queries:
        words = _query_words(q)
        if words and words <= title and len(words) > score:
            best, score = q, len(words)
    return best, False


def keyword_stats(jobs: list[dict[str, Any]], queries: list[str], threshold: int = 30) -> list[dict[str, Any]]:
    """Per search keyword: how many leads it brought and how they scored."""
    rows: dict[str, dict[str, Any]] = {q: {"keyword": q, "leads": 0, "scored": 0, "good": 0, "strong": 0,
                                           "skipped": 0, "guessed": 0, "total": 0} for q in queries}
    for j in jobs:
        if j.get("status") not in store.LEAD_STATUSES | store.APPLICATION_STATUSES | {store.NOT_INTERESTED}:
            continue
        if j.get("source") in ("manual", "email"):
            continue
        q, exact = keyword_of(j, queries)
        if q not in rows:
            continue
        row = rows[q]
        row["leads"] += 1
        row["guessed"] += 0 if exact else 1
        if j.get("match_score") is not None:
            row["scored"] += 1
            row["total"] += j["match_score"]
            row["good"] += j["match_score"] >= threshold
            row["strong"] += j["match_score"] >= 50
        elif j.get("prefilter"):
            row["skipped"] += 1
    out = []
    for row in rows.values():
        row["average"] = round(row["total"] / row["scored"]) if row["scored"] else None
        if row["leads"] == 0:
            row["verdict"] = "no jobs found with it yet"
        elif row["scored"] < MIN_GROUP:
            row["verdict"] = "too few to say"
        elif row["good"] == 0:
            row["verdict"] = "consider dropping: %d scored, none reached %d" % (row["scored"], threshold)
        elif row["strong"]:
            row["verdict"] = "working: %d of %d scored 50 or more" % (row["strong"], row["scored"])
        else:
            row["verdict"] = "weak: %d of %d reached %d, none 50" % (row["good"], row["scored"], threshold)
        out.append(row)
    out.sort(key=lambda r: (-r["strong"], -r["good"], -r["leads"], r["keyword"]))
    return out


_LANGUAGES = {"English", "Czech", "German", "French"}
# asked for everywhere, but not something to "learn" from a list
_SOFT = {"Troubleshooting", "Agile", "Scrum", "Jira", "Confluence", "Excel", "Office 365", "Networking"}


def skill_gaps(jobs: list[dict[str, Any]], cv_text: str, limit: int = 15) -> dict[str, Any]:
    """Technologies asked for in the postings that the CV does not show, most asked first."""
    have = set(keywords.extract(cv_text))
    postings = [j for j in jobs if j.get("status") in store.LEAD_STATUSES | store.APPLICATION_STATUSES
                and (j.get("description") or "").strip()]
    asked, asked_relevant, languages = Counter(), Counter(), Counter()
    relevant = 0
    for j in postings:
        wanted = set(keywords.extract(j["description"]))
        close = (j.get("match_score") or 0) >= 30 or j.get("status") in store.APPLICATION_STATUSES
        relevant += close
        for k in wanted - have:
            if k in _LANGUAGES:
                languages[k] += 1
            elif k not in _SOFT:
                asked[k] += 1
                asked_relevant[k] += close
    rows = [{"skill": k, "postings": n, "relevant": asked_relevant[k],
             "share": round(100 * n / len(postings)) if postings else 0}
            for k, n in asked.most_common()]
    rows.sort(key=lambda r: (-r["relevant"], -r["postings"], r["skill"]))
    return {"postings": len(postings), "relevant": relevant, "skills": rows[:limit],
            "languages": [{"language": k, "postings": n} for k, n in languages.most_common()],
            "in_cv": sorted(have - _LANGUAGES)}
