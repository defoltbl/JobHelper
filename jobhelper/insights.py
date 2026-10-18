"""What the search history says, worked out locally (no model call).

* what_works  - which kinds of role and which sources got confirmations and
                interviews, and which only rejections;
* keyword_stats - how each search keyword performs, so the ones that only
                  produce low scores can be dropped;
* skill_gaps  - technologies the postings ask for most that the CV does not
                show: a learning list. It is only ever displayed; nothing from
                it is added to a CV or a letter;
* trends      - applications and replies week by week;
* reply_times - how long companies took to decide, and which waiting
                applications are past that point;
* low_score_reasons - what the scorer's explanations say about low scores.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date
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
    if not store.has_real_title({"title": title}):
        return ROLE_UNKNOWN                # an application the app knows only by its company
    for name, pattern in _ROLE_RE:
        if pattern.search(title or ""):
            return name
    from . import prefilter                 # not a software role: the profession it names, if the app knows one
    fields = [f for f in prefilter.fields_of([title]) if f != "software and IT"]
    return fields[0].capitalize() if fields else "Other"


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
    """What the postings in the list say they pay (gross per month, in your currency), next to what you ask."""
    from . import salary
    rows = []
    currency = salary.currency_of()
    for j in jobs:
        if j.get("status") not in store.LEAD_STATUSES | store.APPLICATION_STATUSES:
            continue
        target, asked_in, _yours = salary.asked(j)
        if target:
            currency = asked_in
        pay = salary.stated(j, currency)
        if not pay:
            continue
        rows.append({"id": j["id"], "title": j.get("title", ""), "company": j.get("company", ""), "low": pay["low"],
                     "high": pay["high"], "text": pay["text"], "target": target, "score": j.get("match_score"),
                     "top_text": salary.brief(pay["high"]), "range_text": salary.span(pay["low"], pay["high"], currency),
                     "target_text": salary.brief(target) if target else "",
                     "verdict": "" if not target else "above your target" if pay["low"] >= target
                                else "below your target" if pay["high"] < target else "around your target"})
    rows.sort(key=lambda r: (-(r["score"] or 0), -r["high"]))
    considered = sum(1 for j in jobs if j.get("status") in store.LEAD_STATUSES | store.APPLICATION_STATUSES)
    mids = sorted((r["low"] + r["high"]) // 2 for r in rows)
    return {"rows": rows, "stated": len(rows), "postings": considered, "currency": currency,
            "median_text": salary.brief(mids[len(mids) // 2]) if mids else "",
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
_SOFT = {"Troubleshooting", "Agile", "Scrum", "Jira", "Confluence", "Excel", "Office 365", "Networking",
         "Project management", "MS Office", "PowerPoint", "B2B", "Driving licence"}


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


# ── trends: what happened week by week ──────────────────────────────────────
def _day(text: str) -> date | None:
    try:
        return date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def trends(jobs: list[dict[str, Any]], responses: list[dict[str, Any]], weeks: int = 8,
           today: date | None = None) -> list[dict[str, Any]]:
    """The last `weeks` weeks (Monday to Sunday), newest first:
    {week (its Monday), applications, replies, invitations, rejections, current}."""
    from datetime import timedelta
    from . import db
    today = today or date.today()
    this_monday = today - timedelta(days=today.weekday())
    out = []
    for n in range(weeks):
        start = this_monday - timedelta(days=7 * n)
        end = start + timedelta(days=7)
        inside = lambda d: d is not None and start <= d < end                         # noqa: E731
        got = [r for r in responses if inside(db.received_at(r.get("received_date", "")).date())]
        out.append({
            "week": start.isoformat(), "current": n == 0,
            "applications": sum(1 for j in jobs if j.get("status") in store.APPLICATION_STATUSES
                                and inside(_day(j.get("date_applied", "")))),
            "replies": len(got),
            "invitations": sum(1 for r in got if r.get("stage") in ("interview", "assessment", "offer")),
            "rejections": sum(1 for r in got if r.get("stage") == "rejection"),
        })
    while len(out) > 1 and not (out[-1]["applications"] or out[-1]["replies"]):
        out.pop()                                       # no empty weeks before your first activity
    return out


# ── how long companies take to decide ───────────────────────────────────────
_DECISIONS = ("rejection", "interview", "assessment", "offer")


def _middle(values: list[int]) -> int:
    values = sorted(values)
    return values[len(values) // 2] if values else 0


def reply_times(jobs: list[dict[str, Any]], responses: list[dict[str, Any]], today: date | None = None) -> dict[str, Any]:
    """Days from applying to the first decision (a rejection or an invitation),
    overall and per kind of role, and how many waiting applications are already
    past the point by which 4 of 5 decisions had arrived."""
    from . import db
    today = today or date.today()
    first: dict[str, date] = {}
    for r in responses:
        if r.get("stage") in _DECISIONS and r.get("job_id"):
            when = db.received_at(r.get("received_date", ""))
            if when.year > 1 and (r["job_id"] not in first or when.date() < first[r["job_id"]]):
                first[r["job_id"]] = when.date()
    days_by_kind: dict[str, list[int]] = {}
    for j in jobs:
        applied = _day(j.get("date_applied", ""))
        decided = first.get(j.get("id", ""))
        if j.get("status") in store.APPLICATION_STATUSES and applied and decided and decided >= applied:
            days_by_kind.setdefault(role_type(j.get("title", "")), []).append((decided - applied).days)
    everything = sorted(d for group in days_by_kind.values() for d in group)
    most = everything[min(len(everything) - 1, int(len(everything) * 0.8))] if everything else 0
    waiting = [j for j in jobs if j.get("status") == "waiting" and _day(j.get("date_applied", ""))]
    late = [j for j in waiting if (today - _day(j["date_applied"])).days > most] if everything else []
    kinds = [{"name": name, "decisions": len(d), "middle": _middle(d), "fastest": min(d), "slowest": max(d)}
             for name, d in days_by_kind.items() if len(d) >= MIN_GROUP]
    kinds.sort(key=lambda k: (-k["decisions"], k["name"]))
    return {"decisions": len(everything), "middle": _middle(everything), "most_within": most,
            "slowest": everything[-1] if everything else 0, "by_role": kinds,
            "waiting": len(waiting), "waiting_late": len(late),
            "late": [{"id": j["id"], "company": j.get("company", ""), "title": j.get("title", ""),
                      "days": (today - _day(j["date_applied"])).days} for j in sorted(late, key=lambda j: j["date_applied"])[:8]]}


# ── why jobs score low ──────────────────────────────────────────────────────
# Read from the scorer's own explanation. One reason can count under several headings.
_LOW_REASONS = [
    ("A different field", r"unrelated|different (?:domain|field|profession|discipline)|no overlap|non-technical|"
                          r"entirely (?:different|outside)|not a (?:software|technical|development)|outside (?:the|your) (?:candidate'?s? )?(?:field|profile)"),
    ("More experience than you have", r"\b\d{1,2}\s*(?:\+|-\s*\d{1,2}\s*)?\+?\s*years|years of (?:professional|commercial|hands-on|dedicated)|"
                                      r"\bsenior\b|proven track record|extensive (?:\w+ )?experience"),
    ("Another language required", r"\b(?:german|czech|french|dutch|italian|spanish|polish|hungarian|slovak)\b[^.]{0,60}"
                                  r"(?:fluen|required|must|native|level|communicat|speak)|"
                                  r"(?:fluen\w+|native|speak\w*|proficien\w+) (?:in )?(?:german|czech|french|dutch|italian|spanish|polish)"),
    ("Technology you have not used", r"\blacks?\b|absent|none of which|not (?:mentioned|evident|reflected|demonstrated)|no (?:mention|evidence|experience)|"
                                     r"neither of which|does not have|doesn't have|\b(?:has|have|with) no\b|missing|unmet"),
]
_LOW_RE = [(name, re.compile(pattern, re.IGNORECASE)) for name, pattern in _LOW_REASONS]
LOW_OTHER = "Other reasons"


def low_score_reasons(jobs: list[dict[str, Any]], cv_text: str = "", threshold: int = 30) -> dict[str, Any]:
    """Why the jobs below `threshold` scored low: how many explanations mention each
    kind of reason, and the technologies named most often that are not in the CV."""
    low = [j for j in jobs if isinstance(j.get("match_score"), int) and j["match_score"] < threshold
           and (j.get("match_reason") or "").strip()]
    counts = {name: 0 for name, _ in _LOW_RE}
    counts[LOW_OTHER] = 0
    have = set(keywords.extract(cv_text)) if cv_text else set()
    tech: dict[str, int] = {}
    for j in low:
        reason = j["match_reason"]
        hit = False
        for name, pattern in _LOW_RE:
            if pattern.search(reason):
                counts[name] += 1
                hit = True
        if not hit:
            counts[LOW_OTHER] += 1
        for word in set(keywords.extract(reason)):
            if word not in have and word not in _LANGUAGES and word not in _SOFT:
                tech[word] = tech.get(word, 0) + 1
    rows = [{"reason": name, "jobs": n, "share": round(100 * n / len(low)) if low else 0}
            for name, n in counts.items() if n]
    rows.sort(key=lambda r: (r["reason"] == LOW_OTHER, -r["jobs"]))
    named = sorted(tech.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    return {"jobs": len(low), "threshold": threshold, "rows": rows,
            "technologies": [{"skill": k, "jobs": n} for k, n in named if n >= 2]}
