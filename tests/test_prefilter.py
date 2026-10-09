"""The free first look before scoring, and scoring several postings per call."""
import time

import pytest

from jobhelper import agent3_letters, config, llm, prefilter, store

CV = "Python, Kotlin, SQL, PostgreSQL, FastAPI, Docker, Azure, Git, Linux, React, Android. English B2."
CV_KEYS = {"Python", "Kotlin", "SQL", "PostgreSQL", "FastAPI", "Docker", "Azure", "Git", "Linux", "React", "Android", "English"}


TECH = ["software and IT"]                     # what fields_of() gives for a software candidate


def _skip(job, **kw):
    kw.setdefault("mine", TECH)
    return prefilter.reason_to_skip(job, CV_KEYS, **kw)


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
    assert word in _skip(_job(title)).lower()


@pytest.mark.parametrize("title", ["Customer Care Specialist (German)", "Technical Service Coordinator with German - Zličín",
                                   "Tier 1 Autoline Sales Support Analyst - Dutch Speaking", "Android Automotive Entwickler (m/w/d)"])
def test_roles_needing_another_language_are_skipped(title):
    assert "another language" in _skip(_job(title))


@pytest.mark.parametrize("title", ["Quant AI/ML Model Developer VP", "Network managed service engineer (L3)"])
def test_levels_far_above_a_graduate_are_skipped(title):
    assert "senior level" in _skip(_job(title))


def test_posting_with_none_of_your_technologies_is_skipped():
    job = _job("Field IT Support", "Office 365, Active Directory, Networking and ServiceNow on site.")
    assert "None of the technologies" in _skip(job)


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
    assert _skip(_job(title, description)) == ""


# ── whose professions: they follow the roles you look for, not a list in the code ──
def test_your_fields_come_from_the_roles_you_look_for():
    assert prefilter.fields_of(["Junior Backend Developer", "ML Engineer", "Android Developer"]) == ["software and IT"]
    assert prefilter.fields_of(["Registered Nurse", "Caregiver"]) == ["care and health"]
    assert prefilter.fields_of(["Sales Engineer"]) == ["sales and marketing"]
    assert sorted(prefilter.fields_of(["Data Analyst", "Marketing Specialist"])) == ["sales and marketing", "software and IT"]
    assert prefilter.fields_of([]) == [] and prefilter.fields_of(None) == [] and prefilter.fields_of(["", "  "]) == []
    assert prefilter.fields_of(["Beekeeper"]) == []                                   # a role this list does not know: nothing is assumed


def test_without_roles_the_cv_names_the_field():
    assert prefilter.fields_of([], CV) == ["software and IT"]
    assert prefilter.fields_of(["Beekeeper"], "Nurse at a city hospital. Before that a nurse in a care home. I once helped a developer.") == ["care and health"]
    assert prefilter.fields_of([], "I keep bees. One summer I helped a lawyer.") == []          # named once: not enough to go on
    assert prefilter.fields_of(["Registered Nurse"], CV) == ["care and health"]                # roles win over the CV's words


@pytest.mark.parametrize("mine, skipped, kept", [
    (["care and health"], ["Junior Python Developer", "Account Executive", "Mechanical Designer"], ["Staff Nurse", "Nurse - Sales Clinic", "Ward Assistant"]),
    (["sales and marketing"], ["Backend Developer", "Staff Nurse", "Tax Advisor"], ["Account Executive", "Marketing Specialist", "Sales Engineer"]),
    (["finance", "law"], ["QA Tester", "Forklift Driver"], ["Junior Accountant", "Paralegal", "Legal Software Analyst"]),
])
def test_another_candidate_gets_other_skips(mine, skipped, kept):
    for title in skipped:
        assert "another profession" in prefilter.reason_to_skip(_job(title), set(), mine=mine), title
    for title in kept:
        assert prefilter.reason_to_skip(_job(title), set(), mine=mine) == "", title


def test_no_title_is_skipped_for_its_profession_when_your_field_is_not_known():
    for title in ("Major Account Executive", "Staff Nurse", "Junior Python Developer", "Forklift Operator"):
        assert prefilter.reason_to_skip(_job(title), CV_KEYS) == "" and prefilter.reason_to_skip(_job(title), CV_KEYS, mine=["no such field"]) == ""
    assert "senior level" in prefilter.reason_to_skip(_job("Head of Sales"), CV_KEYS)             # the other rules still hold


def test_roles_you_do_not_want_are_skipped_by_name():
    unwanted = ["Tester", "IT support", "C++ Developer"]
    assert _skip(_job("Junior Tester"), unwanted=unwanted) == "You listed this kind of role as not wanted (Tester)."
    assert "not wanted (IT support)" in _skip(_job("IT-Support Specialist"), unwanted=unwanted)
    assert "not wanted (IT support)" in _skip(_job("Junior IT  Support / Admin"), unwanted=unwanted)
    assert "not wanted (C++ Developer)" in _skip(_job("Embedded C++ Developer"), unwanted=unwanted)
    for title in ("Protester Liaison", "Testers Lead", "Support Engineer for IT", "C Developer", "Junior Python Developer"):
        assert _skip(_job(title), unwanted=unwanted) == "", title                                  # whole words, in that order
    assert _skip(_job("Software Developer in Test / Tester"), unwanted=unwanted, wanted=["Software Developer"]) == ""   # also one you want
    assert _skip(_job("Junior Tester"), unwanted=["", "  ", None, 7]) == ""                        # empty and odd entries are ignored


def test_a_language_your_cv_shows_is_not_a_reason_to_skip():
    for title in ("Customer Care Specialist (German)", "Android Automotive Entwickler (m/w/d)", "Support Analyst - German Speaking", "Developer with German"):
        assert "another language" in _skip(_job(title)) and "another language" not in _skip(_job(title), languages={"english", "german"}), title
    assert "another language" in _skip(_job("Sales Support Analyst - Dutch Speaking"), languages={"english", "german"})


def test_apply_reads_the_field_and_languages_from_roles_and_cv():
    nurse_cv = "Registered nurse, 3 years on a surgical ward. German - C1, English - B2."
    jobs = [_job("Junior Python Developer", id="dev"), _job("Staff Nurse", id="nurse"), _job("Pflegefachkraft Nurse (m/w/d)", id="german"),
            _job("Night Nurse", id="unwanted")]
    assert prefilter.apply(jobs, nurse_cv, roles=["Registered Nurse"], unwanted=["Night Nurse"], wanted=["Registered Nurse"]) == 2
    by = {j["id"]: j.get("prefilter", "") for j in jobs}
    assert "another profession (python)" in by["dev"] and "not wanted (Night Nurse)" in by["unwanted"] and by["nurse"] == "" and by["german"] == ""


def test_process_takes_the_roles_from_options_or_the_cv_analysis(isolate_data, monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 10, "match_reason": "x"})
    monkeypatch.setattr(prefilter, "apply", lambda jobs, cv_text, **kw: seen.append(kw) or 0)
    profile = {"summary": "x", "target_roles": ["Backend Developer"], "adjacent_roles": ["QA Engineer"]}
    agent3_letters.process([_job("Dev", id="1")], profile, threshold=60, cv_text=CV)
    assert seen[-1]["roles"] == ["Backend Developer", "QA Engineer"] and seen[-1]["wanted"] == ["Backend Developer"] and seen[-1]["unwanted"] == []
    monkeypatch.setattr(config, "ui_settings", lambda: {"wanted_roles": ["Data Analyst"], "unwanted_roles": ["Tester"]})
    agent3_letters.process([_job("Dev", id="2")], profile, threshold=60, cv_text=CV)
    assert seen[-1]["roles"] == ["Data Analyst", "QA Engineer"] and seen[-1]["wanted"] == ["Data Analyst"] and seen[-1]["unwanted"] == ["Tester"]
    assert seen[-1]["fields"] is None
    monkeypatch.setattr(config, "ui_settings", lambda: {"my_fields": ["finance"]})
    agent3_letters.process([_job("Dev", id="3")], profile, threshold=60, cv_text=CV)
    assert seen[-1]["fields"] == ["finance"]


def test_a_profession_picked_by_hand_is_used_as_it_is():
    assert prefilter.chosen_fields(["law", "finance", "no such field", 7, ""]) == ["finance", "law"]      # known names only, in the app's order
    for nothing in (None, [], "finance", {"finance": 1}, 5):
        assert prefilter.chosen_fields(nothing) == []
    jobs = [_job("Junior Python Developer", id="dev"), _job("Junior Accountant", id="acc"), _job("Staff Nurse", id="nurse")]
    assert prefilter.apply(jobs, CV, roles=["Backend Developer"], fields=["finance"]) == 2                # the pick beats the roles and the CV
    by = {j["id"]: j.get("prefilter", "") for j in jobs}
    assert "another profession" in by["dev"] and "another profession" in by["nurse"] and by["acc"] == ""
    fresh = [_job("Junior Python Developer", id="dev"), _job("Junior Accountant", id="acc")]
    assert prefilter.apply(fresh, CV, roles=["Backend Developer"], fields=["no such field"]) == 1         # a pick the app does not know: read from the roles again
    assert "another profession" in fresh[1]["prefilter"] and not fresh[0].get("prefilter")


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
