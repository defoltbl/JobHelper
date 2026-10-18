"""About you: the facts about the person besides the CV, in their own window (jobhelper/about_you.py)."""
from datetime import date

from jobhelper import about_you, config, details, form_answers, ui_api
from jobhelper.about_you import AboutYou, WorkNotes

MY_JOBS = [{"employer": "Northwind", "title": "Junior analyst", "current": True}, {"employer": "Acme", "title": "Intern"}]


def test_work_notes_get_a_box_for_each_job_and_keep_a_note_whose_job_is_gone():
    notes = WorkNotes([{"job": "Intern, Acme", "notes": "Wrote tests."}, {"job": "Tester, Gone Ltd", "notes": "Ran checks."}], "Built a game.")
    boxes = notes.boxes(MY_JOBS)
    assert [(b["job"], b["notes"], b["earlier"]) for b in boxes] == [
        ("Junior analyst, Northwind", "", False), ("Intern, Acme", "Wrote tests.", False), ("Tester, Gone Ltd", "Ran checks.", True)]
    assert notes.text() == "At Intern, Acme: Wrote tests.\n\nAt Tester, Gone Ltd: Ran checks.\n\nBuilt a game."


def test_work_notes_are_checked_together():
    assert WorkNotes([{"job": "A, B", "notes": "x" * 3000}], "y" * 1001).problem().startswith("The notes about your work are 4001")
    assert WorkNotes([{"job": "", "notes": "text"}]).problem() == "A note on a job needs the job's name."
    assert WorkNotes([{"job": "A, B", "notes": "ok"}], "fine").problem() == ""
    assert WorkNotes([{"job": "A, B", "notes": ""}]).as_options()["about_jobs"] == []           # an empty box is not saved


def test_the_notes_everyone_reads_include_each_job(isolate_data):
    api = ui_api.Api()
    assert api.save_about_you({"about_jobs": [{"job": "Intern, Acme", "notes": "Wrote the importer."}],
                               "about_experience": "Built a game."})["ok"] is True
    assert config.experience_notes() == "At Intern, Acme: Wrote the importer.\n\nBuilt a game."
    # the claim checks read it too: a tool named only in a note is backed
    assert "Kafka" not in form_answers.cover_letter.unverified_terms("Python\n" + "At Intern, Acme: I used Kafka.")


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
