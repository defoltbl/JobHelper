"""One owner each for an event's time, a dated note on a job, the placeholder titles and tidy pasted text."""
from datetime import date, datetime

from jobhelper import insights, merge, planner, store, textfmt


def test_an_event_reads_its_day_and_start_once():
    e = planner.Event({"date": "2026-10-20", "time": "13:30"})
    assert e.day == date(2026, 10, 20) and e.start == datetime(2026, 10, 20, 13, 30)
    assert e.leaves_at() == datetime(2026, 10, 20, 14, 30) and e.minutes_left(datetime(2026, 10, 20, 12, 30)) == 60
    whole_day = planner.Event({"date": "2026-10-20", "time": ""})
    assert whole_day.start is None and whole_day.leaves_at() == datetime(2026, 10, 21) and whole_day.minutes_left(datetime.now()) is None
    assert planner.Event({"date": "soon"}).leaves_at() is None and planner.Event(None).day is None
    assert planner.leaves_at({"date": "2026-10-20", "time": "13:30"}) == e.leaves_at()


def test_a_new_date_starts_its_reminders_again():
    from datetime import timedelta
    soon = (date.today() + timedelta(days=30)).isoformat()
    job = {"event": {"date": soon}, "event_notified": "x", "event_marks": ["x"]}
    assert planner.set_event(job, soon, "10:00") == ""
    assert job["event"]["date"] == soon and job["event"]["time"] == "10:00" and "event_notified" not in job and "event_marks" not in job


def test_a_dated_note_goes_on_top():
    job = {"notes": "[2026-10-01] Applied."}
    store.add_note(job, "Followed up by email.", "2026-10-11")
    assert job["notes"] == "[2026-10-11] Followed up by email.\n[2026-10-01] Applied."
    empty = {}
    store.add_note(empty, "Sent a thank-you note.")
    assert empty["notes"] == f"[{date.today().isoformat()}] Sent a thank-you note."


def test_the_placeholder_titles_are_one_list():
    for title in (store.EXISTING_APPLICATION, store.FROM_EMAIL, "(Unknown role)", "", "  "):
        assert not store.has_real_title({"title": title}) and merge.is_placeholder({"title": title})
        assert insights.role_type(title) == insights.ROLE_UNKNOWN
    assert store.has_real_title({"title": "(Junior) Data Engineer"}) and not merge.is_placeholder({"title": "(Junior) Data Engineer"})


def test_pasted_text_is_tidied_in_one_place():
    assert textfmt.tidy_lines("a  \r\nb\r\r\r\rc \n") == "a\nb\n\nc"
