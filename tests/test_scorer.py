"""agent3_letters.Scorer: the one way postings are scored (the search and "score again" both use it)."""
import pytest

from jobhelper import agent3_letters, llm
from jobhelper.agent3_letters import Scorer

PROFILE = {"summary": "Junior Python developer", "seniority": "junior", "key_skills": ["Python"]}


def _jobs(n):
    return [{"id": f"j{i}", "title": f"Developer {i}", "company": "Kestrel", "description": "Python work."} for i in range(1, n + 1)]


def test_a_batch_answer_is_matched_back_and_the_missed_posting_is_asked_alone(monkeypatch):
    asked = []

    def ask_json(prompt, **k):
        asked.append(prompt)
        if "### J1" in prompt:                                            # the batch: J3 is left out of the answer
            return {"scores": [{"id": "J2", "score": 70}, {"id": "J1", "score": 55}, {"id": "J9", "score": 99}]}
        return {"score": 40}
    monkeypatch.setattr(llm, "ask_json", ask_json)
    got = {}
    missed = Scorer(PROFILE, rules="rules").score(_jobs(3), lambda job, r: bool(r) and got.setdefault(job["id"], r["score"]) is not None)
    assert got == {"j1": 55, "j2": 70, "j3": 40} and missed == [] and len(asked) == 2      # one batch, then J3 alone


def test_a_posting_that_gets_no_usable_score_is_returned(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: {"nothing": True})
    missed = Scorer(PROFILE, rules="rules").score(_jobs(2), lambda job, r: isinstance(r, dict) and "score" in r)
    assert [j["id"] for j in missed] == ["j1", "j2"]


def test_the_limit_is_waited_for_when_the_caller_can_and_stops_the_run_when_it_cannot(monkeypatch):
    calls, waits = [], []

    def ask_json(prompt, **k):
        calls.append(1)
        if len(calls) == 1:
            raise llm.LimitReached("used up")
        return {"score": 61}
    monkeypatch.setattr(llm, "ask_json", ask_json)
    assert Scorer(PROFILE, on_limit=waits.append, rules="r").score(_jobs(1), lambda job, r: True) == [] and len(waits) == 1
    calls.clear()
    with pytest.raises(llm.LimitReached):
        Scorer(PROFILE, rules="r").score(_jobs(1), lambda job, r: True)


def test_a_posting_without_location_or_text_is_still_asked_about():
    fields = Scorer(PROFILE, rules="r").fields({"id": "x", "title": "Analyst"})
    assert fields["location"] == "" and fields["description"] == agent3_letters.NO_DESCRIPTION and "—" not in fields["description"]


def test_a_job_with_documents_is_marked_ready_the_same_way_everywhere():
    job = {"status": "found", "match_score": 55, "notes": ""}
    agent3_letters.mark_ready(job)
    assert job["status"] == "letter_ready" and job["match_tier"] == "moderate" and "Moderate match" in job["notes"]
    applied = {"status": "waiting", "match_score": 80}
    agent3_letters.mark_ready(applied)
    assert applied["status"] == "waiting" and applied["match_tier"] == "strong"         # an application keeps its status
