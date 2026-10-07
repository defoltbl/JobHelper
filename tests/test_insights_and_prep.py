"""Insights worked out locally, and interview preparation built from the CV."""
import pytest

from jobhelper import agent2_search, config, db, insights, interview_prep, llm, store, ui_api

CV = ("Alex Novak\nJunior Software Developer\nPython, Kotlin, SQL, PostgreSQL, FastAPI, Docker, Azure, Git, Linux, React.\n"
      "Built a document search service with FastAPI and pgvector. English B2.")


def _app(id, title, status, source="linkedin", **kw):
    return store.new_job(id=id, title=title, company=f"Co {id}", status=status, source=source, **kw)


# ── what is working ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("title, kind", [
    ("Junior AI Engineer", "AI / machine learning"), ("Machine Learning Engineer", "AI / machine learning"),
    ("Junior Data Scientist", "AI / machine learning"), ("Data Analyst", "Data"), ("Junior Data Engineer", "Data"),
    ("QA Tester", "QA / testing"), ("Test Automation Engineer", "QA / testing"),
    ("IT Support Specialist", "IT support"), ("Help Desk Technician", "IT support"), ("Technical Support Engineer", "IT support"),
    ("Android Developer", "Mobile"), ("Junior Python Developer", "Software development"), ("Backend Engineer", "Software development"),
    ("Marketing Consultant", "Other"), ("(existing application)", insights.ROLE_UNKNOWN), ("", insights.ROLE_UNKNOWN),
])
def test_role_types(title, kind):
    assert insights.role_type(title) == kind


def test_what_works_counts_outcomes_per_role_and_source(isolate_data):
    jobs = [_app("1", "Junior Python Developer", "interview"), _app("2", "Backend Engineer", "rejected"),
            _app("3", "Software Engineer", "waiting"),
            _app("4", "IT Support", "rejected", "jobs.cz"), _app("5", "Help Desk", "rejected", "jobs.cz"),
            _app("6", "Service Desk Agent", "rejected", "jobs.cz"),
            _app("7", "QA Tester", "rejected"),                                   # too few
            _app("8", "Data Analyst", "rejected"),                                # reached an interview earlier
            _app("9", "(existing application)", "waiting", "manual"),
            store.new_job(id="lead", title="Junior Python Developer", company="X", status="found")]
    responses = [{"job_id": "8", "stage": "interview"}, {"job_id": "8", "stage": "rejection"},
                 {"job_id": "2", "stage": "acknowledged"}]
    w = insights.what_works(jobs, responses)
    by = {r["name"]: r for r in w["by_role"]}
    assert w["applications"] == 9 and w["by_role"][-1]["name"] == insights.ROLE_UNKNOWN
    dev = by["Software development"]
    assert (dev["applications"], dev["interviews"], dev["rejected"], dev["waiting"], dev["replied"]) == (3, 1, 1, 1, 1)
    assert dev["verdict"] == "working: 1 of 3 reached an interview"
    assert by["IT support"]["verdict"] == "not working: all 3 rejected"
    assert by["QA / testing"]["verdict"] == "too few to say"
    assert by["Data"]["interviews"] == 1                                          # an earlier interview still counts
    src = {r["name"]: r for r in w["by_source"]}
    assert src["jobs.cz"]["applications"] == 3 and src["your own applications"]["applications"] == 1
    assert sum(r["applications"] for r in w["by_source"]) == 9 == sum(r["applications"] for r in w["by_role"])


# ── search keywords ─────────────────────────────────────────────────────────
def test_keyword_stats_show_which_keywords_waste_scoring():
    def lead(i, title, score, query=None, **kw):
        j = store.new_job(id=str(i), title=title, company="C", match_score=score, **kw)
        if query:
            j["query"] = query
        return j

    jobs = [lead(1, "IT Support Specialist", 10, "it support"), lead(2, "IT Support Engineer", 15, "it support"),
            lead(3, "Senior IT Support", 20, "it support"),
            lead(4, "Junior Python Developer", 70, "junior python developer"), lead(5, "Python Developer", 35, "junior python developer"),
            lead(6, "Python Developer II", 25, "junior python developer"),
            lead(7, "QA Tester", 40),                                             # no keyword recorded: matched by title
            lead(8, "Marketing Manager", 5),                                      # belongs to no keyword
            lead(9, "Old application", 90, "it support", source="manual", status="waiting")]
    rows = {r["keyword"]: r for r in insights.keyword_stats(jobs, ["it support", "junior python developer", "qa tester", "llm engineer"], 30)}
    assert rows["it support"]["verdict"] == "consider dropping: 3 scored, none reached 30" and rows["it support"]["average"] == 15
    assert rows["junior python developer"]["verdict"] == "working: 1 of 3 scored 50 or more"
    assert (rows["qa tester"]["leads"], rows["qa tester"]["guessed"], rows["qa tester"]["verdict"]) == (1, 1, "too few to say")
    assert rows["llm engineer"]["verdict"] == "no jobs found with it yet" and rows["llm engineer"]["average"] is None
    assert sum(r["leads"] for r in rows.values()) == 7                            # the manual one and the unmatched one are left out


def test_search_remembers_which_keyword_found_a_job(monkeypatch):
    ad = ("We are looking for a junior Python developer to join our team in Prague. "
          "You will work with the backend team and write clean, tested code every day.")
    monkeypatch.setattr(agent2_search, "active_providers", lambda source, max_age_days=0: [
        ("one", lambda q, w, n: [store.new_job(id="x-" + q, title="Dev " + q, company="Acme " + q, location="Prague", description=ad)])])
    found = agent2_search.search(["python developer", "qa tester"], where="Prague")
    assert {j["query"] for j in found} == {"python developer", "qa tester"}


# ── skills to learn ─────────────────────────────────────────────────────────
def test_skill_gaps_lists_what_postings_ask_and_the_cv_lacks():
    jobs = [store.new_job(id="1", title="A", company="A", match_score=60, description="Python, AWS, Kubernetes and Docker. Fluent German."),
            store.new_job(id="2", title="B", company="B", match_score=10, description="AWS and Kafka. Agile team, Jira."),
            store.new_job(id="3", title="C", company="C", status="waiting", description="Kubernetes, PostgreSQL."),
            store.new_job(id="4", title="D", company="D", description=""),
            store.new_job(id="5", title="E", company="E", status="not_interested", description="Rust and Scala")]
    g = insights.skill_gaps(jobs, CV)
    assert g["postings"] == 3 and g["relevant"] == 2
    skills = {r["skill"]: r for r in g["skills"]}
    assert set(skills) == {"AWS", "Kubernetes", "Kafka"}                          # not Python/Docker (in the CV), not Agile/Jira
    assert (skills["Kubernetes"]["postings"], skills["Kubernetes"]["relevant"]) == (2, 2)
    assert (skills["AWS"]["postings"], skills["AWS"]["relevant"], skills["AWS"]["share"]) == (2, 1, 67)
    assert g["skills"][0]["skill"] == "Kubernetes"                                # asked most in postings close to you
    assert g["languages"] == [{"language": "German", "postings": 1}]
    assert "Python" in g["in_cv"] and "English" not in g["in_cv"]


def test_skill_gaps_never_change_the_cv_or_a_letter(isolate_data, monkeypatch):
    import inspect
    assert "tailored" not in inspect.getsource(insights) and "LETTERS_DIR" not in inspect.getsource(insights)


def test_api_insights_puts_it_together(isolate_data, monkeypatch):
    config.ensure_dirs()
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: CV)
    job = store.new_job(id="1", title="Junior Python Developer", company="A", match_score=60, description="Python and AWS.")
    store.save_jobs([job, _app("2", "QA Tester", "rejected")])
    api = ui_api.Api()
    api.save_options({**api.options(), "queries": ["junior python developer"], "threshold": 30})
    data = api.insights()
    assert data["threshold"] == 30 and data["keywords"][0]["keyword"] == "junior python developer"
    assert data["gaps"]["skills"][0]["skill"] == "AWS" and data["works"]["applications"] == 1


# ── interview preparation ───────────────────────────────────────────────────
GOOD = {"summary": "Expect questions about Python and your projects.",
        "questions": [
            {"kind": "technical", "question": "How did you build the RAG assistant?", "why": "It is your main project.",
             "answer": "I built it with FastAPI and pgvector, and I ran the model locally."},
            {"kind": "about you", "question": "Tell me about yourself.", "why": "Opening.",
             "answer": "I am a junior developer who works with Python and Kotlin."},
            {"kind": "technical", "question": "Have you used Kubernetes?", "why": "It is in the posting.",
             "answer": "I have not used Kubernetes in a project; the closest I have done is Docker Compose."},
            {"kind": "nonsense kind", "question": "Why us?", "why": "", "answer": "The work matches what I build."},
            {"kind": "practical", "question": "", "answer": "empty question is dropped"}],
        "ask_them": ["What does the first month look like?"], "revise": ["Kubernetes basics"]}


def _job():
    return store.new_job(id="i1", title="Junior Python Developer", company="Acme", status="interview",
                         description="Python, FastAPI, Kubernetes.")


def test_prep_is_cleaned_grouped_and_honest_bridges_are_accepted(isolate_data, monkeypatch):
    prompts = []
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: prompts.append(prompt) or GOOD)
    prep = interview_prep.generate(_job(), CV, [{"stage": "interview", "summary": "Invitation to a 45-minute call."}])
    assert len(prompts) == 1                                                       # nothing to fix: one call
    assert [q["kind"] for q in prep["questions"]] == ["about you", "about you", "technical", "technical"]
    assert all(q["check"] == "" for q in prep["questions"])                        # "have not used Kubernetes" is not a claim
    assert prep["ask_them"] == ["What does the first month look like?"] and prep["made"]
    assert "Invitation to a 45-minute call." in prompts[0] and "Alex Novak" in prompts[0]
    # nothing about the person is written into the code: unknown facts are named as unknown
    assert "Right to work: not stated" in prompts[0] and "Can start: not stated" in prompts[0]
    assert "Czech Republic" not in prompts[0].split("Master CV")[0]


def test_an_answer_claiming_what_the_cv_lacks_is_retried_then_marked(isolate_data, monkeypatch):
    bad = {"summary": "s", "questions": [
        {"kind": "technical", "question": "Kubernetes?", "why": "", "answer": "I have two years of production experience with Kubernetes."},
        {"kind": "about you", "question": "You?", "why": "", "answer": "Alex is a junior developer."}]}
    calls = []
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: calls.append(prompt) or bad)
    prep = interview_prep.generate(_job(), CV)
    assert len(calls) == 2 and "Kubernetes" in calls[1] and "first person" in calls[1]
    marked = {q["question"]: q["check"] for q in prep["questions"]}
    assert marked["Kubernetes?"] == "Kubernetes"                                   # still wrong after the retry: shown, with a warning


def test_unusable_reply_is_an_error(isolate_data, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"questions": []})
    with pytest.raises(ValueError, match="no questions"):
        interview_prep.generate(_job(), CV)


def test_prep_text_for_copying():
    prep = interview_prep._clean(GOOD)
    text = interview_prep.as_text(_job(), prep)
    assert text.startswith("Interview preparation: Junior Python Developer at Acme")
    assert "ABOUT YOU" in text and "TECHNICAL" in text and "QUESTIONS TO ASK THEM" in text and "REVISE BEFORE THE INTERVIEW" in text
    assert "—" not in text


def test_api_makes_keeps_and_returns_the_preparation(isolate_data, monkeypatch):
    config.ensure_dirs()
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: CV)
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: GOOD)
    store.save_jobs([_job(), store.new_job(id="lead", title="Dev", company="B")])
    db.upsert_response({"msg_id": "<1@x>", "job_id": "i1", "company": "Acme", "stage": "interview", "summary": "Call on Friday."})
    api = ui_api.Api()
    assert api.interview_prep("i1") == {} and api.job_detail("i1")["has_prep"] is False
    assert api.make_interview_prep("i1") == {"ok": True}
    saved = api.interview_prep("i1")
    assert saved["company"] == "Acme" and len(saved["questions"]) == 4 and api.job_detail("i1")["has_prep"] is True
    assert "Tell me about yourself." in api.prep_text("i1")
    assert api.make_interview_prep("lead")["ok"] is False                          # only for applications
    assert api.make_interview_prep("nope")["ok"] is False and api.prep_text("lead") == ""

    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: (_ for _ in ()).throw(llm.LimitReached("Claude's 5-hour limit is used up (99%).")))
    failed = api.make_interview_prep("i1")
    assert failed["ok"] is False and "limit is used up" in failed["msg"]
    assert len(api.interview_prep("i1")["questions"]) == 4                         # the earlier one is kept


# ── trends, time to a decision, why jobs score low ──────────────────────────
from datetime import date, datetime, timedelta  # noqa: E402
from email.utils import format_datetime  # noqa: E402

WED = date(2026, 10, 7)                       # a Wednesday; its week starts on Monday 5 October


def _mail(job_id, day, stage):
    return {"job_id": job_id, "stage": stage, "received_date": format_datetime(datetime.combine(day, datetime.min.time()))}


def test_trends_count_by_calendar_week(isolate_data):
    jobs = [_app("1", "Dev", "waiting", date_applied="2026-10-05"), _app("2", "Dev", "rejected", date_applied="2026-10-07"),
            _app("3", "Dev", "waiting", date_applied="2026-10-04"),                 # Sunday: the week before
            _app("4", "Dev", "waiting", date_applied=""),
            store.new_job(id="lead", title="Dev", company="X", status="found", date_applied="2026-10-06")]
    mails = [_mail("2", date(2026, 10, 6), "rejection"), _mail("1", date(2026, 10, 5), "acknowledged"),
             _mail("3", date(2026, 9, 30), "interview"), _mail("9", date(2026, 9, 1), "assessment"), {"job_id": "x", "stage": "other", "received_date": "?"}]
    got = insights.trends(jobs, mails, weeks=8, today=WED)
    assert got[0] == {"week": "2026-10-05", "current": True, "applications": 2, "replies": 2, "invitations": 0, "rejections": 1}
    assert got[1] == {"week": "2026-09-28", "current": False, "applications": 1, "replies": 1, "invitations": 1, "rejections": 0}
    assert got[-1]["week"] == "2026-08-31" and got[-1]["invitations"] == 1          # empty older weeks are cut off
    assert [t["week"] for t in insights.trends([], [], today=WED)] == ["2026-10-05"]


def test_reply_times_and_who_has_waited_too_long(isolate_data):
    def decided(i, applied, after, title="Junior Python Developer", stage="rejection"):
        return _app(str(i), title, "rejected", date_applied=applied), _mail(str(i), date.fromisoformat(applied) + timedelta(days=after), stage)
    pairs = [decided(1, "2026-09-01", 2), decided(2, "2026-09-01", 4), decided(3, "2026-09-01", 6),
             decided(4, "2026-09-01", 8, "IT Support"), decided(5, "2026-09-01", 20, "IT Support", "interview")]
    jobs = [p[0] for p in pairs] + [_app("w1", "Dev", "waiting", date_applied="2026-10-06"),
                                    _app("w2", "Dev", "waiting", date_applied="2026-08-01"),
                                    _app("w3", "Dev", "waiting", date_applied=""),
                                    _app("early", "Dev", "rejected", date_applied="2026-09-10")]
    mails = [p[1] for p in pairs] + [_mail("1", date(2026, 9, 2), "acknowledged"),           # a confirmation is not a decision
                                     _mail("1", date(2026, 9, 9), "rejection"),              # only the first decision counts
                                     _mail("early", date(2026, 9, 1), "rejection")]          # before the apply date: ignored
    got = insights.reply_times(jobs, mails, today=WED)
    assert (got["decisions"], got["middle"], got["most_within"], got["slowest"]) == (5, 6, 20, 20)
    assert got["by_role"] == [{"name": "Software development", "decisions": 3, "middle": 4, "fastest": 2, "slowest": 6}]
    assert (got["waiting"], got["waiting_late"]) == (2, 1) and got["late"][0]["id"] == "w2" and got["late"][0]["days"] == 67
    empty = insights.reply_times([_app("w", "Dev", "waiting", date_applied="2026-01-01")], [], today=WED)
    assert (empty["decisions"], empty["waiting_late"], empty["late"]) == (0, 0, [])           # nothing to compare with: nobody is "late"


def test_low_score_reasons_are_read_from_the_explanations():
    def scored(i, score, reason):
        return store.new_job(id=str(i), title="T", company="C", match_score=score, match_reason=reason)
    jobs = [scored(1, 10, "This is a sales role, completely unrelated to the candidate's software background."),
            scored(2, 15, "Requires 8-10 years of commercial Java experience; the candidate has no Java."),
            scored(3, 20, "German at an advanced level is a must-have requirement."),
            scored(4, 25, "The profile lacks Kubernetes and Terraform, and there is no mention of Java."),
            scored(5, 5, "A poor match overall."),
            scored(6, 80, "Unrelated words in a high score do not count: lacks nothing."),
            scored(7, 10, ""), store.new_job(id="8", title="T", company="C")]
    got = insights.low_score_reasons(jobs, "Python, Docker", threshold=30)
    assert got["jobs"] == 5 and got["threshold"] == 30
    by = {r["reason"]: (r["jobs"], r["share"]) for r in got["rows"]}
    assert by == {"Technology you have not used": (2, 40), "More experience than you have": (1, 20), "A different field": (1, 20),
                  "Another language required": (1, 20), insights.LOW_OTHER: (1, 20)}
    assert got["rows"][0]["reason"] == "Technology you have not used" and got["rows"][-1]["reason"] == insights.LOW_OTHER
    assert got["technologies"] == [{"skill": "Java", "jobs": 2}]                    # named twice, and not in the CV
    assert insights.low_score_reasons([], "")["rows"] == []
