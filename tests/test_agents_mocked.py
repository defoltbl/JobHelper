"""Agent 1 & 3 logic tests with the LLM mocked — no subscription usage, no network."""
from pathlib import Path

import pytest

from jobhelper import agent1_cv, agent3_letters, config, llm, store

REAL_CV_DIR = Path(__file__).resolve().parent.parent / "data" / "cv"


# ── Agent 1 ─────────────────────────────────────────────────────────────────
def test_read_real_cvs_if_present():
    found = False
    files = sorted(REAL_CV_DIR.glob("*.docx")) + sorted(REAL_CV_DIR.glob("*.pdf")) if REAL_CV_DIR.is_dir() else []
    for p in files:                       # whoever's CV is in data/cv
        found = True
        assert len(agent1_cv.read_cv_text(p)) > 200
    if not found:
        pytest.skip("no real CV files present")


def test_read_txt_cv(isolate_data):
    cv = isolate_data / "cv" / "cv.txt"
    cv.parent.mkdir(parents=True, exist_ok=True)
    cv.write_text("Alex Novak\nJunior Software Developer\nPython, SQL, Git")
    assert "Junior Software Developer" in agent1_cv.read_cv_text(cv)


def test_analyze_saves_profile(isolate_data, monkeypatch):
    cv = isolate_data / "cv" / "cv.txt"
    cv.parent.mkdir(parents=True, exist_ok=True)
    cv.write_text("Alex Novak, Junior Software Developer, Python, SQL, Git, REST APIs.")

    fake_profile = {
        "summary": "Junior developer",
        "seniority": "junior",
        "years_experience": 1,
        "target_roles": ["Junior Python Developer"],
        "key_skills": ["Python", "SQL"],
        "search_queries": ["python junior", "backend developer"],
        "strengths": ["fast learner"],
        "gaps": ["limited production experience"],
    }
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: dict(fake_profile))

    profile = agent1_cv.analyze()
    assert profile["seniority"] == "junior"
    assert profile["_cv_file"] == "cv.txt"
    assert config.PROFILE_JSON.exists()
    assert agent1_cv.load_profile()["search_queries"] == ["python junior", "backend developer"]


def test_analyze_errors_without_cv(isolate_data):
    (isolate_data / "cv").mkdir(parents=True, exist_ok=True)
    with pytest.raises(FileNotFoundError):
        agent1_cv.analyze()


# ── Agent 3 ─────────────────────────────────────────────────────────────────
def test_process_writes_letter_for_strong_match(isolate_data, monkeypatch):
    jobs = [store.new_job(id="jobscz-1", title="Python Developer", company="Acme",
                          location="Praha", description="We need a Python dev.")]
    profile = {"summary": "Junior dev", "seniority": "junior", "years_experience": 1,
               "key_skills": ["Python"], "strengths": ["quick learner"]}

    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 85, "match_reason": "Strong Python fit"})
    monkeypatch.setattr(llm, "ask", lambda *a, **k: "Dear team,\n\nI am excited to apply.\n\nRegards, Alex")

    stats = agent3_letters.process(jobs, profile, threshold=60)
    assert stats["letters"] == 1
    job = jobs[0]
    assert job["match_score"] == 85
    assert job["status"] == "letter_ready"
    assert job["cover_letter_file"].endswith(".md")
    assert (config.LETTERS_DIR / job["cover_letter_file"]).exists()


def test_process_writes_tailored_cv(isolate_data, monkeypatch):
    jobs = [store.new_job(id="jobscz-9", title="Python Developer", company="Acme",
                          location="Praha", description="Python, SQL, REST")]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 85, "match_reason": "fit"})

    def fake_ask(prompt, *a, **k):
        return "# Alex Novak\n\nPython Developer\n- Python, SQL" if "Master CV" in prompt else "Dear team, letter."

    monkeypatch.setattr(llm, "ask", fake_ask)
    stats = agent3_letters.process(jobs, {}, threshold=60,
                                   cv_text="Alex Novak\nJunior Developer\nSkills: Python, SQL")
    assert stats["letters"] == 1
    assert stats["tailored_cvs"] == 1
    job = jobs[0]
    assert job["tailored_cv_file"].startswith("CV-")
    assert (config.TAILORED_CV_DIR / job["tailored_cv_file"]).exists()


def test_process_no_tailored_cv_without_cv_text(isolate_data, monkeypatch):
    jobs = [store.new_job(id="jobscz-10", title="Dev", company="Acme", description="x")]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 85, "match_reason": "fit"})
    monkeypatch.setattr(llm, "ask", lambda *a, **k: "Dear team, letter.")
    stats = agent3_letters.process(jobs, {}, threshold=60)  # no cv_text
    assert stats["tailored_cvs"] == 0
    assert jobs[0]["tailored_cv_file"] == ""


def test_process_skips_weak_match(isolate_data, monkeypatch):
    jobs = [store.new_job(id="jobscz-2", title="ML Researcher", company="Lab",
                          description="PhD required.")]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 30, "match_reason": "Needs PhD"})
    # Letter step must NOT be called for a weak match.
    monkeypatch.setattr(llm, "ask", lambda *a, **k: (_ for _ in ()).throw(AssertionError("letter written for weak match")))
    stats = agent3_letters.process(jobs, {}, threshold=60)
    assert stats["letters"] == 0
    assert jobs[0]["match_score"] == 30
    assert jobs[0]["status"] == "found"  # unchanged
    assert jobs[0]["cover_letter_file"] == ""


def test_process_handles_missing_description(isolate_data, monkeypatch):
    jobs = [store.new_job(id="jobscz-3", title="Backend Engineer", company="Startup", description="")]
    captured = {}

    def fake_score(prompt, *a, **k):
        captured["prompt"] = prompt
        return {"match_score": 70, "match_reason": "ok"}

    monkeypatch.setattr(llm, "ask_json", fake_score)
    monkeypatch.setattr(llm, "ask", lambda *a, **k: "Hello letter")
    agent3_letters.process(jobs, {}, threshold=60)
    assert "No description was available" in captured["prompt"]


def test_saved_profile_is_dropped_when_the_cv_changes(isolate_data, monkeypatch):
    config.ensure_dirs()
    cv = config.CV_DIR / "cv.txt"
    cv.write_text("Alex Novak. Junior developer. Internship Feb - Mar 2024. " * 3, encoding="utf-8")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"seniority": "junior", "years_experience": 0.2})
    agent1_cv.analyze()
    assert agent1_cv.load_profile(current_only=True)["years_experience"] == 0.2
    cv.write_text("Alex Novak. Junior developer. Internship Sep 2023 - Mar 2024. " * 3, encoding="utf-8")
    assert agent1_cv.load_profile(current_only=True) is None          # the pipeline will analyse the new CV
    assert agent1_cv.load_profile()["years_experience"] == 0.2         # the old analysis is still readable


def test_cv_analysis_asks_for_internships_in_the_experience_total():
    assert "INCLUDING internships" in agent1_cv.PROMPT_TEMPLATE and '"internships"' in agent1_cv.PROMPT_TEMPLATE


def test_letters_below_fifty_are_written_when_the_threshold_allows_and_marked_stretch(isolate_data, monkeypatch):
    jobs = [store.new_job(id="jobscz-1", title="IT Support Specialist", company="Acme", location="Praha",
                          description="We need IT support.")]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 35, "match_reason": "Different function."})
    monkeypatch.setattr(llm, "ask", lambda *a, **k: "Dear team,\n\nI would like to apply.\n\nRegards, Alex")
    assert agent3_letters.process([dict(jobs[0])], {"summary": "x"}, threshold=50)["letters"] == 0
    stats = agent3_letters.process(jobs, {"summary": "x"}, threshold=30)
    assert stats["letters"] == 1
    assert jobs[0]["status"] == "letter_ready" and jobs[0]["match_tier"] == "stretch"
    assert "Stretch match (35%)" in jobs[0]["notes"]


def test_tiers():
    assert [agent3_letters._tier(s) for s in (95, 60, 59, 50, 49, 30)] == \
        ["strong", "strong", "moderate", "moderate", "stretch", "stretch"]


# ── no company name: no letter addressed to nobody ──────────────────────────
def test_no_documents_are_written_for_a_posting_without_a_company(isolate_data, monkeypatch, capsys):
    jobs = [store.new_job(id="p1", title="Junior AI Engineer", company="", location="Praha", description=""),
            store.new_job(id="p2", title="UX Designer", company=" ", location="Praha",
                          description="Detail nabídky UX Designer Firma: Thales DIS s.r.o. ( zaměstnavatel ) Místo pracoviště: Praha")]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"scores": [{"id": "J1", "match_score": 75, "match_reason": "from the title"},
                                                                   {"id": "J2", "match_score": 70, "match_reason": "fits"}]})
    wrote = []
    monkeypatch.setattr(llm, "ask", lambda *a, **k: wrote.append(1) or "Dear team,\n\nI am excited to apply.\n\nRegards, Alex")
    stats = agent3_letters.process(jobs, {"seniority": "junior"}, threshold=60)
    nameless, named = jobs
    assert nameless["cover_letter_file"] == "" and nameless["status"] == "found" and nameless["match_score"] == 75
    assert nameless["hold"] == agent3_letters.NO_COMPANY and nameless.get("doc_attempts", 0) == 0
    assert named["company"] == "Thales DIS s.r.o" and named["status"] == "letter_ready" and "hold" not in named   # name found in the text
    assert stats["letters"] == 1 and len(wrote) == 1
    assert "no company name in the posting" in capsys.readouterr().out


def test_the_hold_is_lifted_once_the_company_is_known(isolate_data, monkeypatch):
    job = store.new_job(id="p1", title="Junior AI Engineer", company="", match_score=75)
    monkeypatch.setattr(llm, "ask", lambda *a, **k: "Dear team,\n\nI am excited to apply.\n\nRegards, Alex")
    agent3_letters.process([job], {}, threshold=60)
    assert job["hold"] and job["cover_letter_file"] == ""
    job["company"] = "Acme"                                           # you filled it in, or a later search found it
    agent3_letters.process([job], {}, threshold=60)
    assert "hold" not in job and job["status"] == "letter_ready"
