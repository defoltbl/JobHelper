"""Answers for one job's application form: drafted per job, from the CV, never beyond it."""
import pytest

from jobhelper import config, form_answers, llm, store, ui_api

CV = ("Alex Novak\nJunior Software Developer\nPython, Kotlin, SQL, PostgreSQL, FastAPI, Docker, Git, Linux.\n"
      "Built a document search service with FastAPI and pgvector. English B2.")
JOB = {"id": "a", "title": "Junior Python Developer", "company": "Acme", "location": "Prague",
       "description": "We build data tools in Python and Kubernetes.", "desired_monthly_czk": 60000}


def _reply(*answers):
    return {"answers": [{"n": n, "answer": a, "needs_you": need} for n, (a, need) in enumerate(answers, 1)]}


# ── reading the pasted questions ────────────────────────────────────────────
def test_questions_are_read_one_per_line_without_list_marks():
    text = "1. What are your salary expectations? *\n\n- Why do you want to work with us?\n(3) When can you start?\n" \
           "• Why do you want to work with us?\nok\n   \nDo you need a visa"
    assert form_answers.parse_questions(text) == ["What are your salary expectations?", "Why do you want to work with us?",
                                                  "When can you start?", "Do you need a visa"]
    assert form_answers.parse_questions("") == [] and form_answers.parse_questions(None) == []
    assert len(form_answers.parse_questions("\n".join(f"Question number {i}?" for i in range(40)))) == form_answers.MAX_QUESTIONS
    assert len(form_answers.parse_questions("Q" * 900)[0]) == form_answers.MAX_QUESTION


def test_common_questions_name_the_company():
    assert "Why do you want to work at Acme?" in form_answers.common_questions(JOB)
    assert "Why do you want to work at this company?" in form_answers.common_questions({})


# ── drafting ────────────────────────────────────────────────────────────────
def test_answers_come_back_in_the_order_of_the_questions(monkeypatch):
    seen = {}

    def ask(prompt, **kw):
        seen.update(prompt=prompt, system=kw.get("system"), tag=kw.get("tag"))
        return {"answers": [{"n": 2, "answer": "I can start within two weeks.", "needs_you": ""},
                            {"n": 1, "answer": "I expect about 60 000 CZK gross per month — open to discussion.", "needs_you": ""}]}
    monkeypatch.setattr(llm, "ask_json", ask)
    items = form_answers.generate(JOB, CV, ["Salary expectations?", "When can you start?"])
    assert [i["question"] for i in items] == ["Salary expectations?", "When can you start?"]
    assert items[0]["answer"].startswith("I expect about 60 000 CZK") and "—" not in items[0]["answer"]      # em dash cleaned
    assert items[1] == {"question": "When can you start?", "answer": "I can start within two weeks.", "check": ""}
    assert "1. Salary expectations?\n2. When can you start?" in seen["prompt"] and "about 60 000 CZK gross per month" in seen["prompt"]
    assert "Acme" in seen["prompt"] and "RAG assistant" in seen["prompt"] and seen["tag"] == "form_answers"


def test_what_the_app_cannot_know_is_marked_for_you(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: _reply(
        ("My notice period is [your notice period].", "Your notice period"),
        ("You can reach my referee at [name and email].", ""),
        ("", "")))
    items = form_answers.generate({**JOB, "desired_monthly_czk": ""}, CV, ["Notice period?", "A reference?", "Anything else?"])
    assert items[0]["check"] == "Your notice period"
    assert items[1]["check"] == "Fill in the part in square brackets."
    assert items[2]["answer"] == "" and items[2]["check"] == "No answer was drafted. Write this one yourself."


def test_a_claim_outside_the_cv_is_sent_back_once_and_then_flagged(monkeypatch):
    prompts = []

    def ask(prompt, **kw):
        prompts.append(prompt)
        return _reply(("I have two years of production experience with Kubernetes.", ""))
    monkeypatch.setattr(llm, "ask_json", ask)
    items = form_answers.generate(JOB, CV, ["Describe your Kubernetes experience."])
    assert len(prompts) == 2 and "previous version was rejected" in prompts[1] and "Kubernetes" in prompts[1]
    assert items[0]["check"] == "Mentions Kubernetes as experience, which is not in your CV."


def test_an_honest_answer_about_a_missing_skill_is_accepted(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: calls.append(1) or _reply(
        ("I have not used Kubernetes in a project; the closest I have done is deploying with Docker.", "")))
    items = form_answers.generate(JOB, CV, ["Describe your Kubernetes experience."])
    assert len(calls) == 1 and items[0]["check"] == ""


@pytest.mark.parametrize("answer", [
    "No, I do not have professional experience with Kubernetes. My closest experience is Docker.",     # from a real draft
    "I don't have experience with Kubernetes yet.", "I have no commercial experience with Kubernetes.",
    "I have no experience with Kubernetes, but I would learn it quickly.",
])
def test_saying_no_plainly_is_not_a_claim(monkeypatch, answer):
    calls = []
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: calls.append(1) or _reply((answer, "")))
    items = form_answers.generate(JOB, CV, ["Do you have professional experience with Kubernetes?"])
    assert len(calls) == 1 and items[0]["check"] == ""


def test_an_answer_about_the_candidate_by_name_is_sent_back(monkeypatch):
    replies = [_reply(("Alex is a motivated developer.", "")), _reply(("I am a motivated developer.", ""))]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: replies.pop(0))
    assert form_answers.generate(JOB, CV, ["Tell us about yourself."])[0]["answer"] == "I am a motivated developer."


@pytest.mark.parametrize("reply", [["not", "dicts"], {"answers": "nonsense"}, {}, {"answers": [{"n": "x", "answer": ""}]}])
def test_an_unusable_reply_is_an_error_not_empty_answers(monkeypatch, reply):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: reply)
    with pytest.raises(ValueError, match="no answers"):
        form_answers.generate(JOB, CV, ["Why us?"])


def test_nothing_to_answer_asks_no_one(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("must not ask Claude"))
    with pytest.raises(ValueError, match="at least one question"):
        form_answers.generate(JOB, CV, ["", "   "])


def test_a_reply_without_numbers_is_matched_by_position(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"answers": [{"answer": "First."}, {"answer": "Second."}]})
    assert [i["answer"] for i in form_answers.generate(JOB, CV, ["One?", "Two?"])] == ["First.", "Second."]


def test_no_salary_target_is_said_plainly(monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: seen.append(prompt) or _reply(("[your expected salary]", "Your figure")))
    form_answers.generate({**JOB, "desired_monthly_czk": ""}, CV, ["Salary?"])
    assert "- Salary target: not stated" in seen[0]


def test_tidy_keeps_only_what_belongs():
    got = form_answers.tidy([{"question": " Why us? ", "answer": " Because. ", "check": "", "extra": 1}, {"question": "", "answer": "orphan"},
                             "junk", {"question": "Q" * 900, "answer": "A" * 9000, "check": "c" * 900}])
    assert got[0] == {"question": "Why us?", "answer": "Because.", "check": ""}
    assert len(got) == 2 and (len(got[1]["question"]), len(got[1]["answer"]), len(got[1]["check"])) == (300, 3000, 200)
    assert form_answers.tidy(None) == [] and form_answers.tidy("x") == []


# ── through the app ─────────────────────────────────────────────────────────
@pytest.fixture
def api(isolate_data, monkeypatch):
    config.ensure_dirs()
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: CV)
    store.save_jobs([store.new_job(**JOB), store.new_job(id="b", title="QA", company="Beta")])
    return ui_api.Api()


def test_api_drafts_keeps_and_lets_you_edit(api, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: _reply(("Because of your data tools.", ""), ("[your figure]", "Your figure")))
    start = api.form_answers("a")
    assert start["items"] == [] and start["company"] == "Acme" and len(start["common"]) == 5
    assert api.make_form_answers("a", "Why us?\nSalary?") == {"ok": True, "count": 2, "to_check": 1}
    kept = api.form_answers("a")
    assert [i["question"] for i in kept["items"]] == ["Why us?", "Salary?"] and kept["made"]
    assert api.job_detail("a")["has_answers"] is True and api.job_detail("b")["has_answers"] is False
    edited = [{**kept["items"][0], "answer": "Because I use your product every day."}, {**kept["items"][1], "answer": "60 000 CZK", "check": ""}]
    assert api.save_form_answers("a", edited) == {"ok": True, "count": 2}
    again = ui_api.Api().form_answers("a")                                     # after a restart too
    assert again["items"][0]["answer"] == "Because I use your product every day." and again["made"] == kept["made"]
    assert api.form_answers("b")["items"] == []                                # another job has its own answers
    assert api.save_form_answers("a", []) == {"ok": True, "count": 0} and api.job_detail("a")["has_answers"] is False


def test_api_says_why_nothing_was_drafted(api, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("must not ask Claude"))
    assert "Paste the questions" in api.make_form_answers("a", "  \n ")["msg"]
    assert "not in the list" in api.make_form_answers("zzz", "Why us?")["msg"]
    assert api.form_answers("zzz") == {} and api.save_form_answers("zzz", [])["ok"] is False
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "")
    assert "master CV could not be read" in api.make_form_answers("a", "Why us?")["msg"]


def test_api_keeps_old_answers_when_the_limit_is_reached(api, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: _reply(("First draft.", "")))
    api.make_form_answers("a", "Why us?")

    def limit(*a, **k):
        raise llm.LimitReached("Claude's 5-hour limit is used up (99%). It resets at 18:00.")
    monkeypatch.setattr(llm, "ask_json", limit)
    got = api.make_form_answers("a", "Why us?\nSalary?")
    assert got["ok"] is False and "limit is used up" in got["msg"]
    assert api.form_answers("a")["items"][0]["answer"] == "First draft."       # nothing lost


def test_the_old_answers_bank_is_gone():
    from pathlib import Path
    root = Path(ui_api.__file__).resolve().parent.parent
    assert not (root / "jobhelper" / "answers.py").exists() and not (root / "ui_qt" / "AnswersDialog.qml").exists()
    assert not hasattr(ui_api.Api, "save_answers") and not hasattr(ui_api.Api, "fill_answer")
