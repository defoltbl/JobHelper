"""The objects behind form_fill.plan(): Field, RowTracker, FormPlan and FormPlanner."""
from jobhelper import form_fill


def test_a_field_reads_the_page_report_and_never_changes_it():
    raw = {"n": 3, "type": "SELECT", "label": "Country of residence", "options": ["Czechia", "Slovakia"], "most": "40", "combo": False}
    before = dict(raw)
    field = form_fill.Field(raw, at=7)
    assert (field.n, field.at, field.kind, field.most, field.filled, field.picked) == (3, 7, "select", 40, False, True)
    assert field.name == "Country of residence" and field.words == "country of residence"
    assert field.meaning() == ("country", "") == form_fill.classify(raw)                   # the old function gives the same answer
    field.options.append("changed")                                                        # a copy: the report stays as it was
    assert raw == before
    assert form_fill.Field({"n": 1, "type": "password"}).meaning() == ("", form_fill.PASSWORD)
    assert form_fill.Field({"n": 2}).name == "Field 2"


def test_rows_follow_the_fields_that_come_round_again():
    rows = form_fill.RowTracker()
    employer, title = form_fill.Field({"n": 1, "label": "Employer"}), form_fill.Field({"n": 2, "label": "Job title"})
    assert rows.place("employer", employer) == 0 and rows.place("job_title", title) == 0
    assert rows.place("employer", employer) == 1                                           # the second "Employer" starts the second job
    assert rows.counts["experience"] == 2 and rows.last == "experience" and rows.row("experience") == 1
    assert rows.place("employer", form_fill.Field({"n": 9, "label": "Current employer"})) == 0   # your current job wherever it stands
    rows.mark(10)
    assert rows.within(15, form_fill.ROW_NEAR) and not rows.within(16, form_fill.ROW_NEAR)


def test_a_plan_says_each_reason_once_and_keeps_its_shape():
    plan = form_fill.FormPlan()
    plan.leave("Files", form_fill.FILE_BUTTON)
    assert plan.leaves(form_fill.FILE_BUTTON) and not plan.leaves(form_fill.FILE)
    shape = plan.as_dict({"experience": 1, "education": 0, "languages": 0})
    assert list(shape) == ["fill", "ask", "choose", "guess", "tick", "attach", "left", "rows"]
    assert shape["left"] == [{"label": "Files", "why": form_fill.FILE_BUTTON}] and shape["rows"]["experience"] == 1


def test_the_planner_handles_each_kind_of_field_in_its_own_step():
    mine = {"first_name": "Alex", "last_name": "Novak", "email": "alex@example.com", "phone": "+420 777 123 456", "country": "Czechia",
            "start": "", "experience": [{"employer": "Acme", "title": "Analyst", "start": "03/2023", "end": "", "current": True}]}
    fields = [{"n": 1, "type": "text", "label": "First name"}, {"n": 2, "type": "email", "label": "Email"},
              {"n": 3, "type": "file", "label": ""}, {"n": 4, "type": "file", "label": ""},
              {"n": 5, "type": "text", "label": "Employer"}, {"n": 6, "type": "month", "label": "Start date"},
              {"n": 7, "type": "month", "label": "End date"}, {"n": 8, "type": "checkbox", "label": "I currently work here"},
              {"n": 9, "type": "textarea", "label": "Why do you want this job?"}]
    out = form_fill.FormPlanner(fields, mine, has_job=True).plan()
    assert out == form_fill.plan(fields, mine, has_job=True)                               # the entry point is the planner
    filled = {f["n"]: f["value"] for f in out["fill"]}
    assert filled == {1: "Alex", 2: "alex@example.com", 5: "Acme", 6: "2023-03"}
    assert [i["why"] for i in out["left"]].count(form_fill.FILE_BUTTON) == 1               # two bare file fields: said once
    assert out["tick"] == [{"n": 8, "label": "I currently work here"}]                    # the job goes on: no end date, the box ticked
    assert out["ask"] == [{"n": 9, "label": "Why do you want this job?", "most": 0}] and out["rows"]["experience"] == 1
