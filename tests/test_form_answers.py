"""Answers for one job's application form: drafted per job, from the CV, never beyond it."""
import pytest

from jobhelper import api_core, config, form_answers, llm, store, ui_api

CV = ("Alex Novak\nJunior Software Developer\nPython, Kotlin, SQL, PostgreSQL, FastAPI, Docker, Git, Linux.\n"
      "Built a document search service with FastAPI and pgvector. English B2.")
JOB = {"id": "a", "title": "Junior Python Developer", "company": "Acme", "location": "Prague",
       "description": "We build data tools in Python and Kubernetes.", "desired_monthly_czk": 60000}


def _reply(*answers):
    return {"answers": [{"n": n, "answer": a, "needs_you": need} for n, (a, need) in enumerate(answers, 1)]}


# ── reading the pasted questions ────────────────────────────────────────────
def test_questions_are_read_one_per_line_without_list_marks():
    text = "1. What are your salary expectations? *\n\n- Why do you want to work with us?\n(3) When can you start?\n" \
           "• Why do you want to work with us?\n   \nDo you need a visa"
    assert form_answers.check_questions(text)["questions"] == ["What are your salary expectations?", "Why do you want to work with us?",
                                                  "When can you start?", "Do you need a visa"]
    assert form_answers.check_questions("")["questions"] == [] and form_answers.check_questions(None)["questions"] == []


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
    assert "Acme" in seen["prompt"] and "document search service" in seen["prompt"] and seen["tag"] == "form_answers"


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


def test_a_figure_claude_invents_is_sent_back_once_and_then_flagged(monkeypatch):
    """The prompt said never to invent numbers, but nothing checked: an answer could claim '40% faster' for an employer."""
    prompts = []

    def ask(prompt, **kw):
        prompts.append(prompt)
        return _reply(("My search service cut search time by 40% for 1,200 users.", ""))
    monkeypatch.setattr(llm, "ask_json", ask)
    items = form_answers.generate(JOB, CV, ["What did you achieve?"])
    assert len(prompts) == 2 and "states the figure 40" in prompts[1] and "1,200" in prompts[1]
    assert items[0]["check"] == "States 40, 1,200, which your CV and your details do not give. Check it."


def test_figures_from_the_sources_or_in_brackets_are_fine_but_not_one_the_question_asks_for(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: calls.append(1) or _reply(
        ("I expect 60,000 CZK and can start soon [check: notice period 30 days].", "")))
    items = form_answers.generate(JOB, CV, ["Salary expectations?"])
    assert len(calls) == 1 and "States" not in items[0]["check"]                 # "60 000" in the salary line, "60,000" here
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: _reply(("Yes, I have 5 years of Java experience.", "Check the years")))
    items = form_answers.generate(JOB, CV, ["Do you have 5+ years of Java?"])
    assert "States 5" in items[0]["check"] and "Check the years" in items[0]["check"], "asked for, not shown; both notes kept"
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: _reply(("In situation 3, I fixed a slow report.", "")))
    assert form_answers.generate(JOB, CV, ["Tell us about situation 3."])[0]["check"] == "", "a figure the question names, as a reference"


def test_rewriting_an_answer_checks_its_figures_too(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"answer": "I made the search service 40% faster."})
    done = form_answers.rewrite(JOB, CV, "What did you achieve?", "I built a document search service.", "add results")
    assert done["check"] == "States 40, which your CV and your details do not give. Check it."
    flagged = form_answers.rewrite(JOB, CV, "What did you achieve?", "It was 40% faster.", "shorter")
    assert "States 40" in flagged["check"], "a flagged figure does not pass by being rewritten"
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"answer": "I led a team of 8."})
    assert "States 8" in form_answers.rewrite(JOB, CV, "Leadership?", "I led a team of 8 engineers.", "shorter")["check"]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"answer": "I led a team of 8 people."})
    assert form_answers.rewrite(JOB, CV, "Leadership?", "I led a team.", "say I led a team of 8 people")["check"] == ""


@pytest.mark.parametrize("text, sources, references, invented", [
    ("I expect 60,000 CZK.", ("about 60 000 CZK",), (), []),
    ("I expect 60000 CZK.", ("about 60 000 CZK",), (), []),
    ("I expect 60.000 CZK.", ("about 60 000 CZK",), (), []),
    ("I can start on 1.10.2026.", ("You can start: 2026-10-01",), (), []),
    ("I can start in 2 weeks.", ("You can start: in two weeks",), (), []),
    ("I have 1,5 years of SQL.", ("15 projects",), (), ["1,5"]),
    ("We grew 2022 300 users.", ("2022",), (), ["300"]),
    ("Version 3.5 shipped to 40 teams.", ("Python 3.5",), (), ["40"]),
    ("I have 3 years and cut costs by 40%.", ("3 years",), (), ["40"]),
    ("I want to join 3M in Praha 4.", (), ("3M", "Praha 4"), []),                   # the job's own names: a reference
    ("Your team of 50 builds the platform.", (), ("a team of 50",), []),
    ("I have 5 years of Java.", (), ("5+ years of Java required",), ["5"]),          # the posting's figure as my amount
    ("I have five years of Java and ten clients.", ("Java",), (), ["5", "10"]),     # words used as amounts are checked
    ("I led 15 developers.", ("5 developers",), (), ["15"]),
    ("I led 8 developers for 8 weeks.", (), ("Have you led 8+ developers?",), ["8"]),
    ("I have 5 years of SQL.", ("SQL developer, 05/2019 - 08/2022",), (), ["5"]),     # a month of a job date is not 5 years
    ("I have 3 years of Python.", ("Python 3.5",), (), ["3"]),                        # nor a part of a version
    ("I worked there from 2019 to 2022.", ("05/2019 - 08/2022",), (), []),           # but the date itself is backed
    ("I expect around 60k CZK.", ("about 60 000 CZK",), (), []),
    ("I'd like to join one team of experts.", ("CV",), (), []),
    ("I saved 5 million.", (), ("a company with 5 million users",), ["5000000"]),    # still an amount after scaling
    ("I raised 40k.", (), ("a budget of 40k",), ["40000"]),
    ("I earned 16.1k.", ("16 100 CZK",), (), []),
    ("I have 5 years of SQL.", ("SQL developer 05/2019-08/2022",), (), ["5"]),       # a range written without spaces
    ("Uptime was 99.9999% and I paid 1500.50 CZK.", ("uptime 99.9999%, 1500.50 CZK",), (), []),   # decimals, not dates
])
def test_how_figures_are_read(text, sources, references, invented):
    from jobhelper import claims
    assert claims.unbacked_figures(text, sources, references) == invented


def test_a_letter_keeps_no_brackets_but_an_answer_may():
    from jobhelper import claims
    assert claims.unbacked_figures("It saved [40%].", ("CV",), brackets_ok=False) == ["40"]
    assert claims.unbacked_figures("It saved [40%].", ("CV",)) == []


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
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: CV)
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
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: "")
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


# ── what was pasted is judged before anything is asked ──────────────────────
@pytest.mark.parametrize("text, problem", [
    ("", "Paste the questions"), ("   \n\n", "Paste the questions"),
    ("12345\n?!\n--", "No question found"),
    ("Why us?\n" + "word " * 100, "Line 2 is 499 characters long"),
    ("\n".join(f"Question number {i}?" for i in range(20)), "That is 20 questions; one draft takes up to 15"),
])
def test_bad_pasted_text_is_explained_not_cut_silently(text, problem):
    got = form_answers.check_questions(text)
    assert problem in got["problem"] and got["questions"] == []
    assert form_answers.check_questions(text)["questions"] == []


def test_good_text_says_what_was_left_out():
    got = form_answers.check_questions("1. Why us?\n- why us?\n???\nWhen can you start?\n42")
    assert got["questions"] == ["Why us?", "When can you start?"] and got["problem"] == ""
    assert got["note"] == "1 repeated line was left out; 2 lines with no words were left out"
    assert form_answers.check_questions("Why us?") == {"questions": ["Why us?"], "problem": "", "note": ""}
    exactly = form_answers.check_questions("\n".join(f"Question number {i}?" for i in range(15)))
    assert len(exactly["questions"]) == 15 and exactly["problem"] == ""


def test_api_refuses_bad_text_with_the_same_words_and_asks_no_one(api, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("must not ask Claude"))
    many = "\n".join(f"Question number {i}?" for i in range(16))
    assert api.check_questions(many)["problem"] == api.make_form_answers("a", many)["msg"]
    assert "one draft takes up to 15" in api.make_form_answers("a", many)["msg"]
    assert api.check_questions("Why us?\nSalary?") == {"count": 2, "problem": "", "note": ""}
    assert "characters long" in api.make_form_answers("a", "x" * 400)["msg"]


def test_form_answers_use_your_own_salary_figure(isolate_data, monkeypatch):
    from jobhelper import ui_api
    seen = []
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: seen.append(prompt) or _reply(("I expect about 3 200 EUR gross per month.", "")))
    api = ui_api.Api()
    assert api.save_options({**api.options(), "where": "Berlin", "salary_target": 3200, "salary_currency": "EUR"})["ok"] is True
    form_answers.generate(JOB, CV, ["Salary?"])
    assert "Salary target: about 3 200 EUR gross per month (the candidate's own figure" in seen[-1]
    assert api.save_options({**api.options(), "salary_target": 0})["ok"] is True
    form_answers.generate(JOB, CV, ["Salary?"])
    assert "Salary target: not stated" in seen[-1], "no Prague figure for a search in Berlin"
    assert api.save_options({**api.options(), "where": "Prague"})["ok"] is True
    form_answers.generate(JOB, CV, ["Salary?"])
    assert "about 60 000 CZK gross per month (an estimate for this kind of role" in seen[-1]


def test_salary_settings_are_checked(isolate_data):
    from jobhelper import ui_api
    api = ui_api.Api()
    for wrong in ({"salary_target": -1}, {"salary_target": 2.5}, {"salary_target": "a lot"}, {"salary_target": 10**9},
                  {"salary_currency": "XXX"}, {"salary_currency": ""}, {"salary_currency": 5}):
        result = api.save_options({**api.options(), **wrong})
        assert result["ok"] is False and "salary" in result["msg"], wrong
    assert api.save_options({**api.options(), "salary_target": 4000, "salary_currency": "gbp"})["ok"] is True
    assert (api.options()["salary_target"], api.options()["salary_currency"]) == (4000, "GBP")
    assert "CZK" in api.currencies() and "EUR" in api.currencies()
    from jobhelper import about_you, salary
    assert salary.estimate_available({"where": "Prague"}) and salary.estimate_available({}) and not salary.estimate_available({"where": "Berlin"})
    assert not salary.estimate_available({"where": "Prague", "country": "Germany"})                  # the Country from Options wins
    assert "no estimate for this country" in about_you.AboutYou({"where": "Berlin"}).salary_estimates(["python developer"])["note"]


def test_the_salary_list_by_role_is_checked(isolate_data):
    from jobhelper import ui_api
    api = ui_api.Api()
    for wrong, part in (([{"role": "s", "amount": 5}], "kind of role in words"), ([{"role": "123", "amount": 5}], "kind of role in words"),
                        ([{"role": "support", "amount": 0}], "whole number above 0"), ([{"role": "support", "amount": 2.5}], "whole number above 0"),
                        ([{"role": "support", "amount": 1}, {"role": "Support", "amount": 2}], "already in the list"), ("support=5", "must be a list"),
                        ([{"role": f"role {chr(97 + n)}", "amount": 5} for n in range(21)], "up to 20 kinds of role"), (["support"], "kind of role in words")):
        result = api.save_options({**api.options(), "salary_by_role": wrong})
        assert result["ok"] is False and part in result["msg"], wrong
    assert api.save_options({**api.options(), "salary_by_role": [{"role": " support ", "amount": 42000}]})["ok"] is True
    assert api.options()["salary_by_role"] == [{"role": "support", "amount": 42000}]
