"""Calendar file, thank-you note, one PDF, the apply checklist and the weekly summary."""
from datetime import date, datetime, timedelta
from email.utils import format_datetime

import pytest

from jobhelper import config, db, planner, store, summary, ui_api

TODAY = date(2026, 10, 7)


def _app(id="a", **kw):
    extra = {k: kw.pop(k) for k in ("event", "thanked_for") if k in kw}
    job = store.new_job(id=id, title=kw.pop("title", "QA Engineer"), company=kw.pop("company", "Acme"),
                        status=kw.pop("status", "waiting"), **kw)
    job.update(extra)
    return job


def _event(day, time="", kind="interview", note=""):
    return {"date": day, "time": time, "kind": kind, "note": note}


# ── calendar file ───────────────────────────────────────────────────────────
def test_calendar_file_with_a_time():
    job = _app(event=_event("2026-10-15", "14:30", note="Teams; bring ID, laptop"), url="https://example.com/job")
    text = planner.ics(job, now=datetime(2026, 10, 7, 9, 0, 0))
    lines = text.split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR" and text.endswith("\r\n")
    assert "UID:jobhelper-a@jobhelper.local" in lines and "DTSTAMP:20261007T090000" in lines
    assert "DTSTART:20261015T143000" in lines and "DTEND:20261015T153000" in lines
    assert "SUMMARY:Interview: Acme" in lines
    assert r"DESCRIPTION:QA Engineer\nTeams\; bring ID\, laptop\nhttps://example.com/job" in lines
    assert [x for x in lines if x.startswith("TRIGGER:")] == ["TRIGGER:-P1D", "TRIGGER:-PT1H"]


def test_calendar_file_for_a_whole_day_and_without_a_date():
    text = planner.ics(_app(event=_event("2026-12-31", kind="deadline")))
    assert "DTSTART;VALUE=DATE:20261231" in text and "DTEND;VALUE=DATE:20270101" in text
    assert "TRIGGER:-PT15H" in text and "TRIGGER:PT9H" in text                 # 9:00 the day before and on the day
    assert planner.ics(_app()) == "" and planner.ics(_app(event=_event("soon"))) == ""


def test_the_same_job_keeps_one_calendar_entry():
    a = planner.ics(_app(event=_event("2026-10-15", "14:30")))
    b = planner.ics(_app(event=_event("2026-10-16", "10:00")))
    uid = lambda text: next(x for x in text.split("\r\n") if x.startswith("UID:"))     # noqa: E731
    assert uid(a) == uid(b)                                                    # a changed date updates, not duplicates


# ── thank-you note ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("job, due", [
    (_app(event=_event("2026-10-07")), True), (_app(event=_event("2026-10-05", kind="call")), True),
    (_app(event=_event("2026-10-08")), False),                                 # not yet
    (_app(event=_event("2026-10-07", kind="deadline")), False),                # nothing to thank for
    (_app(event=_event("2026-10-07"), status="rejected"), False),
    (_app(event=_event("2026-10-07"), thanked_for="2026-10-07"), False),       # already sent
    (_app(event=_event("2026-10-07"), thanked_for="2026-09-20"), True),        # a second interview
    (_app(), False),
])
def test_when_a_thank_you_is_offered(job, due):
    assert planner.thanks_due(job, TODAY) is due


def test_thank_you_draft_and_marking_it_sent():
    job = _app(company="Acme s.r.o.", event=_event("2026-10-07", kind="call"))
    d = planner.thanks_draft(job, "Alex Novak", "Jana Novakova, HR")
    assert d["subject"] == "Thank you: QA Engineer"
    assert d["body"].startswith("Dear Jana,\n\nThank you for the call about the QA Engineer position.")
    assert "at Acme s.r.o.\n" in d["body"] and d["body"].endswith("Kind regards,\nAlex Novak") and "—" not in d["body"]
    plain = planner.thanks_draft(job)
    assert plain["body"].startswith("Dear Acme s.r.o team,") and plain["body"].endswith("[Your name]")
    planner.mark_thanked(job, TODAY)
    assert job["thanked_for"] == "2026-10-07" and job["notes"].startswith("[2026-10-07] Sent a thank-you note.")
    assert planner.thanks_due(job, TODAY) is False


# ── the last seven days ─────────────────────────────────────────────────────
def _reply(msg_id, job_id, when, stage):
    db.upsert_response({"msg_id": msg_id, "job_id": job_id, "stage": stage, "company": "C", "subject": "s",
                        "from_addr": "hr@example.com", "received_date": format_datetime(datetime.combine(when, datetime.min.time()))})


def test_week_summary_counts_only_the_last_seven_days(isolate_data):
    recent, old = (TODAY - timedelta(days=2)).isoformat(), (TODAY - timedelta(days=20)).isoformat()
    jobs = [store.new_job(id="n1", title="Dev", company="A", status="letter_ready", date_found=recent),
            store.new_job(id="n2", title="Dev", company="B", status="found", date_found=recent),
            store.new_job(id="o1", title="Dev", company="C", status="letter_ready", date_found=old),
            _app("a1", date_applied=recent), _app("a2", company="D", date_applied=old),
            _app("a3", company="E", date_applied=old, event=_event((TODAY + timedelta(days=1)).isoformat(), "10:00")),
            _app("a4", company="F", date_applied=old, event=_event((TODAY + timedelta(days=30)).isoformat())),
            _app("a5", company="G", date_applied=old, event=_event(TODAY.isoformat(), kind="call"))]
    _reply("m1", "a1", TODAY - timedelta(days=1), "interview")
    _reply("m2", "a2", TODAY - timedelta(days=3), "rejection")
    _reply("m3", "a2", TODAY - timedelta(days=15), "acknowledged")
    w = summary.week(jobs, db.all_responses(), 10, TODAY)
    assert (w["new_jobs"], w["new_ready"], w["ready_total"], w["applied"]) == (2, 1, 2, 1)
    assert (w["replies"], w["invites"], w["rejections"]) == (2, 1, 1)
    assert w["thanks"] == 1 and [c["id"] for c in w["coming"]] == ["a5", "a3"]
    assert w["followups"] >= 1 and summary.week(jobs, db.all_responses(), 0, TODAY)["followups"] == 0
    rows = summary.lines(w)
    assert rows[0] == {"label": "New jobs found", "value": "2", "note": "1 of them with a CV and letter ready"}
    assert rows[3]["note"] == "1 invitation, 1 rejection"
    assert [r["label"] for r in rows[-3:]] == ["Thank-you notes to send", "Coming up", "Coming up"]
    assert summary.headline(w).startswith("2 new jobs (2 ready to send), 2 replies, 1 invitation, ")
    assert summary.headline(w).endswith("2 dates coming up.")


def test_an_empty_week_reads_sensibly(isolate_data):
    w = summary.week([], [], 10, TODAY)
    rows = summary.lines(w)
    assert [r["value"] for r in rows] == ["0", "0", "0", "0", "0"]
    assert rows[0]["note"] == "run a search to look for more" and rows[3]["note"] == "none in the last 7 days"
    assert summary.headline(w) == "0 new jobs (0 ready to send), 0 replies."


# ── through the app ─────────────────────────────────────────────────────────
@pytest.fixture
def api(isolate_data, monkeypatch):
    config.ensure_dirs()
    api = ui_api.Api()
    api.opened = []
    monkeypatch.setattr(ui_api.Api, "_open", lambda self, target: api.opened.append(target))
    return api


def test_api_calendar_file_is_written_and_opened(api):
    store.save_jobs([_app()])
    assert api.export_event("a") == {"ok": False, "msg": "Save a date first."} and api.opened == []
    day = (date.today() + timedelta(days=3)).isoformat()
    api.set_event("a", day, "09:15", "interview", "Office")
    got = api.export_event("a")
    path = config.DATA_DIR / "calendar" / got["file"]
    assert got["ok"] and api.opened == [path] and path.suffix == ".ics"
    assert f"DTSTART:{day.replace('-', '')}T091500" in path.read_bytes().decode("utf-8")
    assert b"\r\n" in path.read_bytes() and api.export_event("zzz")["ok"] is False


def test_api_thank_you_flow_and_week_summary(api, monkeypatch):
    monkeypatch.setattr(ui_api.Api, "_my_name", lambda self: "Alex Novak")
    store.save_jobs([_app(event=_event(date.today().isoformat()))])
    planner.save_company_notes("Acme", {"contact": "Jana"})
    assert api.job_detail("a")["thanks_due"] is True
    assert api.thanks_draft("a")["body"].startswith("Dear Jana,") and api.thanks_draft("zzz") == {}
    assert api.mark_thanked("a") is True and api.job_detail("a")["thanks_due"] is False
    assert api.mark_thanked("zzz") is False
    week = api.week_summary()
    assert week["lines"][0]["label"] == "New jobs found" and week["headline"].endswith(".")


def test_no_thank_you_before_todays_interview_has_started():
    job = _app(event=_event("2026-10-07", "14:30"))
    assert planner.thanks_due(job, TODAY, now=datetime(2026, 10, 7, 9, 0)) is False
    assert planner.thanks_due(job, TODAY, now=datetime(2026, 10, 7, 14, 30)) is True
    assert planner.thanks_due(job, TODAY + timedelta(days=1), now=datetime(2026, 10, 8, 8, 0)) is True


# ── letter and CV in one PDF, and the apply checklist ───────────────────────
def _pdf(path, pages=1):
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        w.write(f)
    return path


def test_combine_joins_pdfs_in_order(tmp_path):
    from jobhelper import pdf
    out = pdf.combine([_pdf(tmp_path / "letter.pdf", 1), _pdf(tmp_path / "cv.pdf", 2)], tmp_path / "out" / "both.pdf")
    assert out is not None and pdf.page_count(out) == 3
    assert pdf.combine([tmp_path / "letter.pdf", tmp_path / "missing.pdf"], tmp_path / "x.pdf") is None
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")
    assert pdf.combine([tmp_path / "bad.pdf"], tmp_path / "y.pdf") is None and pdf.combine([], tmp_path / "z.pdf") is None


def _lead(**kw):
    return store.new_job(id="lead", title="Junior Developer", company="Acme", status="letter_ready",
                         cover_letter_file="Letter_lead.docx", tailored_cv_file="Alex_Novak_CV_Acme_Junior_Developer.docx", **kw)


def test_one_pdf_from_the_existing_copies(api):
    _pdf(config.LETTERS_DIR / "Letter_lead.pdf", 1)
    _pdf(config.TAILORED_CV_DIR / "Alex_Novak_CV_Acme_Junior_Developer.pdf", 2)
    store.save_jobs([_lead(), store.new_job(id="bare", title="T", company="C")])
    assert api.job_detail("lead")["can_combine"] is True and api.job_detail("bare")["can_combine"] is False
    got = api.combined_pdf("lead")
    out = config.DATA_DIR / "combined" / "Alex_Novak_Application_Acme_Junior_Developer.pdf"
    assert got == {"ok": True, "file": out.name, "pages": 3} and api.opened == [out]
    assert api.combined_pdf("bare")["ok"] is False and api.combined_pdf("zzz")["ok"] is False


def test_one_pdf_is_not_offered_without_pdf_copies_or_libreoffice(api):
    (config.LETTERS_DIR / "Letter_lead.docx").write_bytes(b"x")
    (config.TAILORED_CV_DIR / "Alex_Novak_CV_Acme_Junior_Developer.docx").write_bytes(b"x")
    store.save_jobs([_lead()])
    assert api.job_detail("lead")["can_combine"] is False                 # tests run without LibreOffice
    got = api.combined_pdf("lead")
    assert got["ok"] is False and "LibreOffice" in got["msg"] and api.opened == []


def test_one_pdf_makes_the_missing_copies_when_libreoffice_is_there(api, monkeypatch):
    from jobhelper import pdf
    (config.LETTERS_DIR / "Letter_lead.docx").write_bytes(b"x")
    (config.TAILORED_CV_DIR / "Alex_Novak_CV_Acme_Junior_Developer.docx").write_bytes(b"x")
    store.save_jobs([_lead()])
    monkeypatch.setattr(pdf, "find_soffice", lambda: "/fake/soffice")
    monkeypatch.setattr(pdf, "to_pdf", lambda docx, timeout=120: _pdf(docx.with_suffix(".pdf")))
    assert api.job_detail("lead")["can_combine"] is True
    assert api.combined_pdf("lead")["pages"] == 2


def test_apply_steps_are_kept_with_the_job(api):
    store.save_jobs([_lead()])
    assert api.job_detail("lead")["apply_steps"] == []
    assert api.apply_step("lead", "cv") == {"ok": True} and api.apply_step("lead", "posting") == {"ok": True}
    assert api.apply_step("lead", "cv") == {"ok": True}                    # ticking twice changes nothing
    assert api.job_detail("lead")["apply_steps"] == ["cv", "posting"]
    assert api.apply_step("lead", "format-disk") == {"ok": False} and api.apply_step("zzz", "cv") == {"ok": False}
    assert ui_api.Api().job_detail("lead")["apply_steps"] == ["cv", "posting"]      # after a restart too
