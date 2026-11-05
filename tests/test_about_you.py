"""About you: the facts about the person besides the CV, in their own window (jobhelper/about_you.py)."""
from datetime import date

from jobhelper import about_you, config, details, form_answers, ui_api
from jobhelper.about_you import AboutYou, WorkNotes

MY_JOBS = [{"employer": "Northwind", "title": "Junior analyst", "current": True}, {"employer": "Acme", "title": "Intern"}]
NAMES = [WorkNotes.job_name(r) for r in MY_JOBS]
CV = """Alex Novak
EXPERIENCE
Junior Analyst – Northwind Traders (Mar 2023 – present)
- Built the monthly SQL reports.
Intern, Acme (2021 – 2022)
- Wrote tests.
EDUCATION
BSc Computer Science – Example University (2018 – 2021)
"""


def test_work_notes_get_a_box_for_each_job_and_keep_a_note_whose_job_is_gone():
    notes = WorkNotes([{"job": "Intern, Acme", "notes": "Wrote tests."}, {"job": "Tester, Gone Ltd", "notes": "Ran checks."}], "Built a game.")
    boxes = notes.boxes(NAMES)
    assert [(b["job"], b["notes"], b["earlier"]) for b in boxes] == [
        ("Junior analyst, Northwind", "", False), ("Intern, Acme", "Wrote tests.", False), ("Tester, Gone Ltd", "Ran checks.", True)]
    assert notes.text() == "At Intern, Acme: Wrote tests.\n\nAt Tester, Gone Ltd: Ran checks.\n\nBuilt a game."


def test_work_notes_are_checked_together():
    assert WorkNotes([{"job": "A, B", "notes": "x" * 3000}], "y" * 1001).problem().startswith("The notes about your work are 4012")
    assert WorkNotes([{"job": "", "notes": "text"}]).problem() == "A job needs a name. Write one, or remove the job."
    assert WorkNotes([{"job": "A, B", "notes": "ok"}], "fine").problem() == ""
    assert WorkNotes([{"job": "A, B", "notes": ""}]).as_options()["about_jobs"] == []           # an empty box is not saved


def test_the_jobs_come_from_the_master_cv_and_can_be_renamed_or_removed():
    """Owner, 5 Nov: the boxes should come from the master CV, and each should be renamed or removed as needed."""
    from jobhelper import claims
    names = claims.EmployerCheck.job_names(CV)
    assert names == ["Junior Analyst, Northwind Traders", "Intern, Acme"], "a degree is no job"
    notes = WorkNotes([{"job": "Reporting analyst", "from": names[0], "notes": "Built the reports."},
                       {"job": names[1], "from": names[1], "removed": True},
                       {"job": "Tester, Gone Ltd", "notes": "Ran checks."}])
    boxes = notes.boxes(names)
    assert [(b["job"], b["from"], b["removed"], b["earlier"]) for b in boxes] == [
        ("Reporting analyst", names[0], False, False), (names[1], names[1], True, False), ("Tester, Gone Ltd", "", False, True)]
    assert notes.text() == "At Reporting analyst: Built the reports.\n\nAt Tester, Gone Ltd: Ran checks.", "a removed job says nothing"
    kept = notes.as_options()["about_jobs"]
    assert {"job": names[1], "from": names[1], "removed": True} in kept, "a removed job stays removed"
    assert WorkNotes([{"job": "My name", "from": names[0]}]).as_options()["about_jobs"] == [{"job": "My name", "from": names[0]}], \
        "a rename without notes is kept too"
    assert WorkNotes([{"job": "", "from": names[0]}]).problem().startswith("A job needs a name")
    # a note written before this change (named as in My details, no "from") stays with its job, however it is written
    assert WorkNotes([{"job": "Intern, Acme", "notes": "Old note."}]).boxes(names)[1]["notes"] == "Old note."
    assert WorkNotes([{"job": "Junior analyst, Northwind", "notes": "Old."}]).boxes(names)[0]["notes"] == "Old.", \
        "the same title at the employer the CV names in full"
    assert WorkNotes([{"job": "Senior analyst, Northwind", "notes": "Other."}]).boxes(names)[0]["notes"] == "", "another title is another job"
    assert not WorkNotes.same_job("Intern, Acme", "Intern, Acmeville"), "a longer word is another employer"


def test_a_month_before_the_year_is_no_part_of_a_job_s_name():
    """Check of 5 Nov: "…, Jan 2022 – Mar 2023" gave "…, Northwind Parcel, Jan", so a note lost its job when the dates changed."""
    from jobhelper import claims
    cv = "EXPERIENCE\nJunior Developer – Northwind Parcel, Jan 2022 – Mar 2023\n- Built things.\nTester, Acme (Sept. 2020 – 2021)\n"
    assert claims.EmployerCheck.job_names(cv) == ["Junior Developer, Northwind Parcel", "Tester, Acme"]


def test_two_jobs_never_share_a_name():
    two = WorkNotes([{"job": "Analyst, Acme", "from": "A, B", "notes": "x"}, {"job": "analyst, acme", "from": "C, D", "notes": "y"}])
    assert two.problem().startswith("Two jobs have the same name")


def test_the_jobs_of_my_details_are_used_when_the_cv_names_none():
    page = AboutYou({}).job_boxes({**details.empty(), "experience": MY_JOBS}, "Alex Novak\nPython developer.")
    assert page["jobs_from"] == "details" and [b["job"] for b in page["boxes"]] == NAMES
    assert AboutYou({}).job_boxes({**details.empty(), "experience": MY_JOBS}, CV)["jobs_from"] == "cv"
    assert AboutYou({}).job_boxes(details.empty(), "")["jobs_from"] == ""


def test_the_window_says_why_each_part_is_worth_filling_in_and_where_it_is_used():
    """Owner, 5 Nov: say why I need to fill it in and where it will be used."""
    uses = AboutYou({}).page(details.empty(), "junior", CV)["uses"]
    assert set(uses) == {"salary", "right", "start", "work"}
    assert all(text.startswith("Why: ") and "Used in: " in text for text in uses.values())
    assert "interview preparation" in uses["work"] and "form answers" in uses["salary"]


def test_the_notes_everyone_reads_include_each_job(isolate_data):
    api = ui_api.Api()
    assert api.save_about_you({"about_jobs": [{"job": "Intern, Acme", "notes": "I deployed it with Kafka."}],
                               "about_experience": "Built a game."})["ok"] is True
    assert config.experience_notes() == "At Intern, Acme: I deployed it with Kafka.\n\nBuilt a game."
    # the claim check of a form answer: a tool the CV lacks but a job's note names is backed, through experience_notes
    cv = "Alex Novak\nPython developer. Python, SQL."
    unverified = form_answers.cover_letter.unverified_terms(cv + "\n" + config.experience_notes())
    assert "Kafka" not in unverified and "Kafka" in form_answers.cover_letter.unverified_terms(cv)


def test_the_size_counts_what_everyone_reads_so_nothing_is_cut():
    """The window counted only the notes; the job names and gaps were added after, and the end was cut without a word."""
    notes = WorkNotes([{"job": "Junior analyst, Northwind", "notes": "x" * 3990}])
    assert notes.size() == len(notes.text()) == len("At Junior analyst, Northwind: ") + 3990
    assert notes.problem().startswith("The notes about your work are") and notes.text().endswith("x" * 10)


def test_a_job_name_may_be_as_long_as_my_details_allows():
    longest = "T" * 100 + ", " + "E" * 100                    # a title and an employer, each at My details' limit
    most = sum(m for key, _label, m in details.ROWS["experience"] if key in ("title", "employer")) + 2
    assert WorkNotes([{"job": longest, "notes": "ok"}]).problem() == "" and WorkNotes.MAX_JOB_NAME == most
    assert "takes up to" in WorkNotes([{"job": "x" * (most + 1), "notes": "ok"}]).problem()


def test_save_about_you_stores_only_its_own_facts(isolate_data):
    api = ui_api.Api()
    api.save_options({**api.options(), "where": "Brno"})
    assert api.save_about_you({"about_start": "one month", "where": "Berlin"})["ok"] is True
    assert api.options()["where"] == "Brno" and api.options()["about_start"] == "one month"
    assert api.save_about_you({"where": "Berlin"}) == {"ok": False, "msg": "Nothing to save."}
    refused = api.save_about_you({"about_jobs": [{"job": "A, B", "notes": "x" * 5000}]})
    assert refused["ok"] is False and "4000" in refused["msg"] and "about_jobs" not in config.ui_settings()
    assert "must be a list of notes" in api.save_about_you({"about_jobs": "text"})["msg"]


def test_the_start_preview_says_the_date_forms_get():
    today = date(2026, 10, 18)
    assert AboutYou.start_preview("2026-11-01", today) == {"ok": True, "text": "Forms get: 1 November 2026"}
    two_weeks = AboutYou.start_preview("within two weeks", today)
    assert two_weeks["ok"] and two_weeks["text"].startswith("Forms get: 1 November 2026 (worked out")
    assert AboutYou.start_preview("after my exams", today)["ok"] is False and AboutYou.start_preview("", today) == {"ok": True, "text": ""}


def test_right_to_work_choices_name_the_country_of_the_search():
    assert AboutYou({"where": "Prague"}).right_to_work_choices()[0] == "Full right to work in Czechia"
    assert AboutYou({"where": "Berlin", "country": "Germany"}).right_to_work_choices()[2] == "Work permit for Germany"
    assert "the country of the job" in AboutYou({}).right_to_work_choices()[0]


def test_the_salary_estimate_is_shown_where_the_app_has_one():
    prague = AboutYou({"where": "Prague"}).salary_estimates(["junior python developer", "accountant", "junior python developer"])
    assert prague["available"] and [r["role"] for r in prague["rows"]] == ["junior python developer"]
    assert prague["rows"][0]["text"].endswith(" CZK")
    assert AboutYou({"where": "Berlin"}).salary_estimates(["python developer"]) == {
        "available": False, "rows": [], "note": "The app has no estimate for this country. With 0, forms leave the salary for you to fill in."}
    assert "none of your roles" in AboutYou({"where": "Prague"}).salary_estimates(["accountant"])["note"]


def test_the_window_gets_its_boxes_from_my_details(isolate_data):
    details.save({**details.empty(), "first_name": "Alex", "last_name": "Novak", "email": "alex@example.com",
                  "experience": [{"employer": "Northwind", "title": "Junior analyst", "start": "03/2023", "end": "", "current": True}]})
    page = ui_api.Api().about_you()
    assert [b["job"] for b in page["boxes"]] == ["Junior analyst, Northwind"] and page["max_notes"] == WorkNotes.MAX_TOTAL
    assert set(about_you.KEYS) <= set(page) and page["start"] == {"ok": True, "text": ""}


def test_the_cv_level_has_one_reading():
    from jobhelper import agent1_cv
    assert agent1_cv.level_of({"seniority": "mid"}) == "mid"
    assert agent1_cv.level_of({"seniority": ""}) == agent1_cv.level_of(None) == agent1_cv.level_of({}) == "junior"


def test_about_you_estimates_the_roles_you_want_else_the_ones_you_search():
    assert AboutYou({"wanted_roles": ["data analyst"], "queries": ["python developer"]}).roles() == ["data analyst"]
    assert AboutYou({"wanted_roles": [], "queries": ["python developer"]}).roles() == ["python developer"]
    assert AboutYou({}).roles() == []


def test_a_role_with_ordinary_punctuation_is_english():
    """The first English check refused a curly apostrophe: and every Options save checks every saved line."""
    from jobhelper.api_options import OptionsService
    check = OptionsService.__new__(OptionsService)
    assert check.pay_problem("Customer’s support – level 1", 30000) == ""
    assert "English" in check.pay_problem("поддержка", 30000)
    assert "up to 20 kinds of role" in check.pay_problem("support", 30000, [f"role {n}" for n in range(20)])


def test_the_window_and_the_back_end_name_the_same_scripts_as_not_latin():
    import re
    from pathlib import Path
    from jobhelper import textfmt
    main = (Path(__file__).resolve().parent.parent / "ui_qt" / "Main.qml").read_text(encoding="utf-8")
    pattern = re.search(r"function hasNonLatin\(s\) \{\s*return /\[(.+?)\]/", main).group(1)
    window = [f"{ord(a):04x}-{ord(b):04x}" for a, b in re.findall(r"(.)-(.)", pattern)]
    back = [f"{ord(a):04x}-{ord(b):04x}" for a, b in (r.split("-") for r in textfmt.NON_LATIN_RANGES)]
    assert window == back


def test_a_form_answer_backed_only_by_a_job_note_is_not_marked(isolate_data, monkeypatch):
    """Through the real path: form_answers.generate gets the notes and must count them as backing (not only the CV)."""
    from jobhelper import llm
    api = ui_api.Api()
    api.save_about_you({"about_jobs": [{"job": "Intern, Acme", "notes": "I ran our queues on Kafka."}]})
    cv = "Alex Novak\nPython developer. Python, SQL."
    answer = {"answers": [{"n": 1, "answer": "I have worked with Kafka for the message queues."}]}
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: answer)
    with_notes = form_answers.generate({"title": "Developer", "company": "Orbis"}, cv, ["Which tools?"], config.experience_notes())
    without = form_answers.generate({"title": "Developer", "company": "Orbis"}, cv, ["Which tools?"], "")
    assert with_notes[0]["check"] == "" and "Kafka" in without[0]["check"]


def test_one_rule_says_when_two_kinds_of_role_are_the_same_line():
    from jobhelper.api_options import OptionsService
    service = OptionsService.__new__(OptionsService)
    assert OptionsService.pay_key("Python  Developer ") == OptionsService.pay_key("python developer")
    assert "already in the list" in service.pay_problem("Python  Developer", 30000, ["python developer"])
    assert OptionsService.own_figure(58000, "CZK") == 58000 and OptionsService.own_figure(58000, "EUR") == 2300
