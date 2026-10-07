"""status.py commands added with follow-ups and PDF copies."""
from datetime import date, timedelta

import status
from jobhelper import config, pdf, store


def _run(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["status.py", *args])
    return status.main()


def test_followups_lists_quiet_applications(isolate_data, monkeypatch, capsys):
    old = (date.today() - timedelta(days=20)).isoformat()
    new = date.today().isoformat()
    config.ensure_dirs()
    store.save_jobs([store.new_job(id="quiet", title="QA Engineer", company="Acme", status="waiting", date_applied=old, last_update=old),
                     store.new_job(id="fresh", title="Dev", company="Beta", status="waiting", date_applied=new, last_update=new)])
    assert _run(monkeypatch, "followups") == 0
    out = capsys.readouterr().out
    assert "Acme · QA Engineer" in out and "20 days" in out and "Beta" not in out
    assert _run(monkeypatch, "followups", "--days", "30") == 0
    assert "No application has been waiting 30+ days" in capsys.readouterr().out


def test_pdf_command_explains_when_libreoffice_is_missing(isolate_data, monkeypatch, capsys):
    assert _run(monkeypatch, "pdf") == 1
    assert "LibreOffice is not installed" in capsys.readouterr().out


def test_pdf_command_converts_generated_documents_only(isolate_data, monkeypatch, capsys):
    made = []
    monkeypatch.setattr(pdf, "find_soffice", lambda: "/fake/soffice")
    monkeypatch.setattr(pdf, "to_pdf", lambda doc: (made.append(doc.name), doc.with_suffix(".pdf"))[1])
    monkeypatch.setattr(pdf, "page_count", lambda path: 1)
    config.ensure_dirs()
    for name in ("cv.docx", "have.docx"):
        (config.TAILORED_CV_DIR / name).write_bytes(b"x")
    (config.TAILORED_CV_DIR / "have.pdf").write_bytes(b"x")
    for name in ("app_letter.docx", "my_own.docx"):
        (config.LETTERS_DIR / name).write_bytes(b"x")
    store.save_jobs([
        store.new_job(id="1", title="A", company="A", source="linkedin", tailored_cv_file="cv.docx", cover_letter_file="app_letter.docx"),
        store.new_job(id="2", title="B", company="B", source="linkedin", tailored_cv_file="have.docx"),
        store.new_job(id="3", title="C", company="C", source="manual", cover_letter_file="my_own.docx"),
    ])
    assert _run(monkeypatch, "pdf") == 0
    assert sorted(made) == ["app_letter.docx", "cv.docx"]            # not the user's own letter, not the existing PDF
    assert "already there: 1" in capsys.readouterr().out
