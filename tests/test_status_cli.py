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


# ── found by reading the file line by line (10 October 2026) ────────────────
def test_apply_is_for_a_new_job_and_does_not_reopen_an_application(isolate_data, monkeypatch, capsys):
    config.ensure_dirs()
    store.save_jobs([store.new_job(id="lead", title="Dev", company="Acme", status="letter_ready"),
                     store.new_job(id="closed", title="QA", company="Beta", status="rejected", date_applied="2026-09-01")])
    assert _run(monkeypatch, "apply", "closed") == 1
    out = capsys.readouterr().out
    assert "not a new job any more (status: rejected)" in out and "status.py update closed" in out
    assert store.find(store.load_jobs(), "closed")["status"] == "rejected", "a rejection is not turned into a waiting application by a slip"
    assert _run(monkeypatch, "apply", "lead") == 0
    applied = store.find(store.load_jobs(), "lead")
    assert applied["status"] == "waiting" and applied["date_applied"] == date.today().isoformat()
    assert _run(monkeypatch, "apply", "nobody") == 1 and "No job with id" in capsys.readouterr().out
    assert _run(monkeypatch, "update", "lead", "applied") == 1 and "Unknown status 'applied'" in capsys.readouterr().out
    assert "update adzuna-123 applied" not in status.__doc__ and "waiting" in status.__doc__, "the file's own examples are commands that work"


def test_responses_scan_keeps_what_was_read_when_the_limit_is_reached(isolate_data, monkeypatch, capsys):
    from jobhelper import agent5_responses, llm
    config.ensure_dirs()
    store.save_jobs([store.new_job(id="a", title="Dev", company="Acme", status="waiting", date_applied="2026-09-01")])
    asked = []

    def read(jobs, lookback_days=None, **kw):
        asked.append(lookback_days)
        jobs[0]["status"] = "interview"                     # one reply was read before the limit
        raise llm.LimitReached("Claude's 5-hour limit is used up (100%).")
    monkeypatch.setattr(agent5_responses, "process_inbox", read)
    assert _run(monkeypatch, "responses", "--scan") == 3
    assert "What was read is saved" in capsys.readouterr().out and store.find(store.load_jobs(), "a")["status"] == "interview"
    assert asked == [status.scan_days()], "without --days it looks as far back as the app's Options say, not nowhere"
    monkeypatch.setattr(agent5_responses, "process_inbox", lambda jobs, lookback_days=None, **kw: (_ for _ in ()).throw(RuntimeError("No mailbox is connected.")))
    assert _run(monkeypatch, "responses", "--scan") == 1 and "No mailbox is connected." in capsys.readouterr().out


def test_repair_emails_says_why_it_cannot_read_the_mailbox(isolate_data, monkeypatch, capsys):
    from jobhelper import email_client, vault
    config.ensure_dirs()
    backups = []
    monkeypatch.setattr(vault, "make_backup", lambda label: backups.append(label))
    monkeypatch.setattr(email_client, "fetch_recent", lambda days=None: (_ for _ in ()).throw(RuntimeError("No mailbox is connected. Add your job email in the app's Account card.")))
    assert _run(monkeypatch, "repair-emails") == 1
    assert "No mailbox is connected" in capsys.readouterr().out and backups == [], "nothing was read, so nothing is backed up or changed"


def test_the_package_and_the_example_settings_describe_the_app_as_it_is():
    import jobhelper
    from pathlib import Path
    root = Path(status.__file__).resolve().parent
    assert "Agent 5" in jobhelper.__doc__ and "4-agent" not in jobhelper.__doc__ and "form" in jobhelper.__doc__
    env = (root / ".env.example").read_text(encoding="utf-8")
    assert "Email sync (Agent 5" in env and "ANTHROPIC_API_KEY=" not in env.replace("Do NOT set ANTHROPIC_API_KEY", "")
    script = (root / "weekly_jobhelper.sh").read_text(encoding="utf-8")
    assert "send the week" not in script, "the app never sends anything: the summary is a notification"


def test_a_mailbox_that_refuses_or_cannot_be_reached_is_one_sentence_in_the_log(isolate_data, monkeypatch, capsys):
    """The weekly run writes what these commands print into its log. A wrong password or no network used to leave a traceback."""
    import imaplib
    from jobhelper import agent5_responses, email_client
    config.ensure_dirs()
    store.save_jobs([store.new_job(id="a", title="Dev", company="Acme", status="waiting", date_applied="2026-09-01")])
    for error, words in ((imaplib.IMAP4.error("[AUTHENTICATIONFAILED] hunter2"), "Couldn't sign in to your email"),
                         (TimeoutError("timed out"), "could not be reached"), (KeyError("odd"), "could not be read (KeyError)")):
        monkeypatch.setattr(agent5_responses, "process_inbox", lambda jobs, lookback_days=None, _e=error, **kw: (_ for _ in ()).throw(_e))
        monkeypatch.setattr(email_client, "fetch_recent", lambda days=None, _e=error: (_ for _ in ()).throw(_e))
        for command in (("sync",), ("responses", "--scan"), ("repair-emails",)):
            assert _run(monkeypatch, *command) == 1
            out = capsys.readouterr().out
            assert words in out and "Traceback" not in out and "hunter2" not in out, (command, out)


def test_the_mail_server_gets_a_time_limit_and_an_empty_answer_is_no_mail(monkeypatch):
    from jobhelper import email_client
    made = {}

    class Server:
        def __init__(self, host, port, timeout=None):
            made.update(host=host, timeout=timeout)

        def login(self, user, password): pass
        def select(self, folder, readonly=False): made["readonly"] = readonly
        def search(self, *args): return "OK", [None]
        def logout(self): made["out"] = True
    monkeypatch.setattr(email_client.imaplib, "IMAP4_SSL", Server)
    assert email_client._fetch_box("me@example.com", "pw", "01-Oct-2026", host="imap.example.com") == []
    assert made == {"host": "imap.example.com", "timeout": email_client.SERVER_TIMEOUT, "readonly": True, "out": True}
    assert email_client._numbers([b"1 2 3"]) == [b"1", b"2", b"3"] and email_client._numbers([]) == [] and email_client._numbers(None) == []
