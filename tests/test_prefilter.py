"""The free first look before scoring, and scoring several postings per call."""
import time

import pytest

from jobhelper import agent3_letters, config, llm, prefilter, store

CV = "Python, Kotlin, SQL, PostgreSQL, FastAPI, Docker, Azure, Git, Linux, React, Android. English B2."
CV_KEYS = {"Python", "Kotlin", "SQL", "PostgreSQL", "FastAPI", "Docker", "Azure", "Git", "Linux", "React", "Android", "English"}


def _job(title, description="", **kw):
    return store.new_job(id=kw.pop("id", title), title=title, company="Acme", location="Prague", description=description, **kw)


# ── what is skipped for free ────────────────────────────────────────────────
@pytest.mark.parametrize("title, word", [
    ("Major Account Executive, France", "account executive"),
    ("Mechanical Engineer - Technical Configurator Specialist", "mechanical"),
    ("PLC Engineer | Industrial Automation", "plc"),
    ("Investment Analyst Junior – Public Equities & M&A", "investment"),
    ("Junior Crypto Analyst & Trader", "crypto"),
    ("Logistic Trainee", "logistic"),
    ("Video Data Annotator", "annotator"),
    ("General Support Agent - Nightshift (all genders)", "nightshift"),
    ("Projektant / Projektant junior tramvajových vozidel", "projektant"),
])
def test_other_professions_are_skipped(title, word):
    assert word in prefilter.reason_to_skip(_job(title), CV_KEYS).lower()


@pytest.mark.parametrize("title", ["Customer Care Specialist (German)", "Technical Service Coordinator with German - Zličín",
                                   "Tier 1 Autoline Sales Support Analyst - Dutch Speaking", "Android Automotive Entwickler (m/w/d)"])
def test_roles_needing_another_language_are_skipped(title):
    assert "another language" in prefilter.reason_to_skip(_job(title), CV_KEYS)


@pytest.mark.parametrize("title", ["Quant AI/ML Model Developer VP", "Network managed service engineer (L3)"])
def test_levels_far_above_a_graduate_are_skipped(title):
    assert "senior level" in prefilter.reason_to_skip(_job(title), CV_KEYS)


def test_posting_with_none_of_your_technologies_is_skipped():
    job = _job("Field IT Support", "Office 365, Active Directory, Networking and ServiceNow on site.")
    assert "None of the technologies" in prefilter.reason_to_skip(job, CV_KEYS)


# ── what must always reach the model (each scored 30+ in the first real runs) ──
@pytest.mark.parametrize("title, description", [
    ("IT Helpdesk Operator - Farmacie", ""),
    ("Mobile Test Automation Engineer for George (Digital Banking)", ""),
    ("Intern in the Cloud & Data Analytics Department (f/m/x)", ""),
    ("Internal Tools Engineer", ""),
    ("IT Support / IT Administrator", ""),
    ("Engineer Operations for Market Risk applications", ""),
    ("API Engineer (Python)", "3+ years of experience with Python and REST APIs."),
    ("Software Engineer - Sales Tools", "Python and PostgreSQL."),
    ("Junior Data Scientist", "Statistics, R and Python."),
    ("IT Application Support Specialist", "SQL and ticketing tools. Jira."),
])
def test_plausible_roles_are_never_skipped(title, description):
    assert prefilter.reason_to_skip(_job(title, description), CV_KEYS) == ""


def test_apply_marks_only_unscored_leads_and_respects_an_override():
    jobs = [_job("Major Account Executive", id="sales"),
            _job("Junior Python Developer", id="dev"),
            _job("Mechanical Designer", id="scored", match_score=15),
            _job("Mechanical Designer", id="applied", status="waiting"),
            _job("Mechanical Designer", id="forced")]
    jobs[-1]["prefilter_override"] = True
    assert prefilter.apply(jobs, CV) == 1
    by = {j["id"]: j for j in jobs}
    assert "another profession" in by["sales"]["prefilter"]
    assert all("prefilter" not in by[k] or not by[k]["prefilter"] for k in ("dev", "scored", "applied", "forced"))
    assert prefilter.apply(jobs, CV) == 0                    # nothing new the second time


def test_skipped_jobs_cost_no_model_call(isolate_data, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: calls.append(prompt) or {"match_score": 10, "match_reason": "x"})
    jobs = [_job("Major Account Executive", id="sales"), _job("Forklift Operator", id="forklift"),
            _job("Junior Python Developer", "Python and Docker.", id="dev")]
    stats = agent3_letters.process(jobs, {"summary": "x"}, threshold=60, cv_text=CV)
    assert stats["prefiltered"] == 2 and stats["scored"] == 1 and len(calls) == 1
    assert [j["match_score"] for j in jobs] == [None, None, 10]
    assert agent3_letters.process(jobs, {"summary": "x"}, threshold=60, cv_text=CV)["scored"] == 0     # and never later


def test_a_job_sent_back_to_scoring_is_scored(isolate_data, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 10, "match_reason": "x"})
    jobs = [_job("Major Account Executive", id="sales")]
    agent3_letters.process(jobs, {"summary": "x"}, threshold=60, cv_text=CV)
    assert jobs[0]["match_score"] is None
    jobs[0]["prefilter_override"] = True
    agent3_letters.process(jobs, {"summary": "x"}, threshold=60, cv_text=CV)
    assert jobs[0]["match_score"] == 10 and not jobs[0].get("prefilter")


# ── several postings per call ───────────────────────────────────────────────
def _devs(n):
    return [_job(f"Junior Developer {i}", "Python and Docker.", id=f"d{i}") for i in range(n)]


def test_five_postings_are_scored_in_one_call(isolate_data, monkeypatch):
    prompts = []

    def ask_json(prompt, **k):
        prompts.append(prompt)
        n = prompt.count("### J")
        return {"scores": [{"id": f"J{i}", "match_score": 10 + i, "match_reason": f"reason {i}"} for i in range(1, n + 1)]}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    jobs = _devs(12)
    stats = agent3_letters.process(jobs, {"summary": "x"}, threshold=60)
    assert len(prompts) == 3 and stats["scored"] == 12                    # 5 + 5 + 2 instead of 12 calls
    assert [j["match_score"] for j in jobs[:6]] == [11, 12, 13, 14, 15, 11]
    assert jobs[4]["match_reason"] == "reason 5"
    assert "Junior Developer 0" in prompts[0] and "Junior Developer 5" in prompts[1]
    assert "Do not assume a requirement" in prompts[0] and "up to 2 years" in prompts[0]   # same rules as single scoring


def test_a_posting_missing_from_the_reply_is_asked_alone(isolate_data, monkeypatch):
    calls = []

    def ask_json(prompt, **k):
        calls.append(prompt)
        if "### J" in prompt:
            return {"scores": [{"id": "J1", "match_score": 40, "match_reason": "a"},
                               {"id": "J9", "match_score": 99, "match_reason": "not a posting we sent"},
                               {"id": "J3", "match_score": "high", "match_reason": "not a number"}]}
        return {"match_score": 25, "match_reason": "single"}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    jobs = _devs(3)
    agent3_letters.process(jobs, {"summary": "x"}, threshold=60)
    assert [j["match_score"] for j in jobs] == [40, 25, 25] and len(calls) == 3


def test_an_unusable_batch_reply_falls_back_to_single_calls(isolate_data, monkeypatch):
    calls = []

    def ask_json(prompt, **k):
        calls.append(prompt)
        if "### J" in prompt:
            raise ValueError("Could not parse JSON from model reply")
        return {"match_score": 20, "match_reason": "single"}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    jobs = _devs(3)
    assert agent3_letters.process(jobs, {"summary": "x"}, threshold=60)["scored"] == 3 and len(calls) == 4


def test_limit_in_the_middle_of_a_batch_repeats_that_batch(isolate_data, monkeypatch):
    calls, pauses = [], []

    def ask_json(prompt, **k):
        calls.append(prompt)
        if len(calls) == 2:
            raise llm.LimitReached("limit", time.time() + 60)
        n = prompt.count("### J")
        return {"scores": [{"id": f"J{i}", "match_score": 10, "match_reason": "x"} for i in range(1, n + 1)]}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    jobs = _devs(8)
    agent3_letters.process(jobs, {"summary": "x"}, threshold=60, on_limit=lambda e: pauses.append(1))
    assert pauses == [1] and len(calls) == 3 and all(j["match_score"] == 10 for j in jobs)


def test_status_lines_say_what_is_being_done(isolate_data, monkeypatch):
    lines = []
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: {"scores": [{"id": "J1", "match_score": 70, "match_reason": "x"},
                                                                         {"id": "J2", "match_score": 10, "match_reason": "x"}]})
    monkeypatch.setattr(llm, "ask", lambda *a, **k: "Dear team,\n\nI would like to apply.\n\nRegards")
    agent3_letters.process(_devs(2), {"summary": "x"}, threshold=60, status=lines.append)
    assert lines[0] == "Scoring jobs 1–2 of 2…" and lines[1].startswith("Writing CV and letter 1 of 1")


def test_batch_size_comes_from_config(isolate_data, monkeypatch):
    calls = []
    monkeypatch.setattr(config, "SCORE_BATCH", 1)
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: calls.append(prompt) or {"match_score": 10, "match_reason": "x"})
    agent3_letters.process(_devs(3), {"summary": "x"}, threshold=60)
    assert len(calls) == 3 and all("### J" not in c for c in calls)
