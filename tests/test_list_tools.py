"""Not interested, and editing a letter the app wrote."""
import shutil
from pathlib import Path

import pytest

from jobhelper import api_core, agent2_search, agent3_letters, config, cover_letter, llm, store, ui_api, vault

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "data" / "cover_letter_template.docx"
CV = "Alex Novak\nJunior Software Developer\nPython, Kotlin, PostgreSQL, FastAPI, Docker, Azure."
PARAS = [("I am applying for this role because the work on data pipelines matches what I build. " * 4).strip() for _ in range(5)]

pytestmark = pytest.mark.skipif(not TEMPLATE.exists(), reason="letter template not present")


@pytest.fixture
def api(isolate_data, monkeypatch):
    config.ensure_dirs()
    shutil.copy2(TEMPLATE, config.LETTER_TEMPLATE)
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: CV)
    return ui_api.Api()


def _lead_with_docs(job_id="lead", source="linkedin"):
    letter = config.LETTERS_DIR / f"Letter_{job_id}.docx"
    cover_letter.build_docx(config.LETTER_TEMPLATE, letter, "Junior Developer", PARAS, date_text="7 October 2026")
    (config.LETTERS_DIR / f"Letter_{job_id}.pdf").write_bytes(b"%PDF")
    (config.TAILORED_CV_DIR / f"CV_{job_id}.docx").write_bytes(b"cv")
    return store.new_job(id=job_id, title="Junior Developer", company="Acme", status="letter_ready", source=source,
                         match_score=55, match_tier="moderate", cover_letter_file=letter.name,
                         tailored_cv_file=f"CV_{job_id}.docx", description="Python and Docker.")


# ── not interested ──────────────────────────────────────────────────────────
def test_not_interested_removes_the_lead_and_stashes_its_documents(api):
    store.save_jobs([_lead_with_docs(), store.new_job(id="other", title="QA", company="Beta")])
    assert api.dismiss_job("lead") == {"ok": True}
    job = store.find(store.load_jobs(), "lead")
    assert job["status"] == store.NOT_INTERESTED and job["cover_letter_file"] == "" and job["tailored_cv_file"] == ""
    assert [r["id"] for r in api.leads()] == ["other"] and api.counts()["leads"] == 1
    assert [r["id"] for r in api.dismissed()] == ["lead"]
    assert list(config.LETTERS_DIR.glob("Letter_lead.*")) == [] and list(config.TAILORED_CV_DIR.glob("CV_lead.*")) == []
    stashed = sorted(p.name.split(".")[0] for p in (vault.backups_dir() / "not_interested").iterdir())
    assert stashed == ["CV_lead", "Letter_lead", "Letter_lead"]                 # letter docx + pdf, and the CV
    assert all(vault.file_is_encrypted(p) for p in (vault.backups_dir() / "not_interested").iterdir())


def test_not_interested_never_touches_a_letter_of_your_own(api):
    (config.LETTERS_DIR / "mine.docx").write_bytes(b"my own letter")
    store.save_jobs([store.new_job(id="m", title="Dev", company="Acme", status="letter_ready", source="manual",
                                   cover_letter_file="mine.docx")])
    assert api.dismiss_job("m")["ok"]
    assert (config.LETTERS_DIR / "mine.docx").read_bytes() == b"my own letter"
    assert store.find(store.load_jobs(), "m")["cover_letter_file"] == "mine.docx"


def test_only_leads_can_be_dismissed_and_only_dismissed_restored(api):
    store.save_jobs([store.new_job(id="app", title="Dev", company="Acme", status="waiting"),
                     store.new_job(id="lead", title="Dev", company="Beta")])
    assert api.dismiss_job("app")["ok"] is False and api.restore_job("lead")["ok"] is False
    assert api.dismiss_job("missing")["ok"] is False


def test_restore_brings_it_back_and_documents_are_written_again(api, monkeypatch):
    job = _lead_with_docs(); job["doc_attempts"] = 2
    store.save_jobs([job])
    api.dismiss_job("lead")
    assert api.restore_job("lead") == {"ok": True}
    job = store.load_jobs()[0]
    assert job["status"] == "found" and job["doc_attempts"] == 0
    monkeypatch.setattr(llm, "ask", lambda *a, **k: "Dear team,\n\nI would like to apply.\n\nRegards")
    monkeypatch.setattr(config, "LETTER_TEMPLATE", config.DATA_DIR / "no_template.docx")
    jobs = store.load_jobs()
    assert agent3_letters.process(jobs, {"summary": "x"}, threshold=50)["letters"] == 1     # scored 55: no new scoring call


def test_a_dismissed_job_does_not_come_back_from_a_later_search(api):
    gone = store.new_job(id="linkedin-1", title="Junior Developer (m/f/d)", company="Acme s.r.o.", status=store.NOT_INTERESTED)
    jobs = [gone]
    found = [store.new_job(id="linkedin-1", title="Junior Developer (m/f/d)", company="Acme s.r.o."),     # the same posting
             store.new_job(id="jobscz-9", title="Junior Developer", company="Acme"),                      # reposted elsewhere
             store.new_job(id="jobscz-10", title="Data Analyst", company="Acme")]                         # another role: fine
    kept, dropped = agent2_search.drop_known_applications(found, jobs)
    added, _ = store.upsert(jobs, kept)
    assert dropped >= 1 and added == 1
    assert sorted(j["id"] for j in jobs) == ["jobscz-10", "linkedin-1"]
    assert jobs[0]["status"] == store.NOT_INTERESTED


def test_scoring_and_documents_skip_dismissed_jobs(api, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("a dismissed job must not be scored"))
    jobs = [store.new_job(id="x", title="Dev", company="A", location="Prague", status=store.NOT_INTERESTED)]
    assert agent3_letters.process(jobs, {"summary": "x"}, threshold=30)["scored"] == 0


# ── encrypted side copies ───────────────────────────────────────────────────
def test_keep_copy_and_stash(isolate_data):
    config.ensure_dirs()
    f = config.LETTERS_DIR / "a.docx"; f.write_bytes(b"version one")
    copy = vault.keep_copy(f, "letter_versions")
    assert f.exists() and copy.parent.name == "letter_versions" and vault.read_bytes(copy) == b"version one"
    assert b"version one" not in copy.read_bytes()
    assert vault.stash([f, config.LETTERS_DIR / "missing.docx"], "gone") == 1 and not f.exists()
    assert vault.keep_copy(f, "x") is None


# ── editing a letter ────────────────────────────────────────────────────────
def test_letter_is_offered_for_editing_only_when_the_app_wrote_it(api):
    (config.LETTERS_DIR / "mine.docx").write_bytes(b"own")
    store.save_jobs([_lead_with_docs(),
                     store.new_job(id="own", title="Dev", company="B", status="waiting", source="manual", cover_letter_file="mine.docx"),
                     store.new_job(id="none", title="Dev", company="C")])
    d = api.letter_for_edit("lead")
    assert d["ok"] and d["paragraphs"] == PARAS and d["title_line"] == "Junior Developer" and d["date_text"] == "7 October 2026"
    assert api.job_detail("lead")["letter_editable"] is True
    for job_id in ("own", "none"):
        assert api.letter_for_edit(job_id)["ok"] is False and api.job_detail(job_id)["letter_editable"] is False
    assert "your own" in api.letter_for_edit("own")["msg"]
    assert api.save_letter("own", PARAS)["ok"] is False and (config.LETTERS_DIR / "mine.docx").read_bytes() == b"own"
    assert api.rewrite_paragraph("own", PARAS, 0)["ok"] is False


def test_an_old_text_letter_is_not_offered_for_editing(api):
    """A letter from an early version that exists only as a .md file opens, but cannot be edited in the app."""
    _lead_with_docs()
    (config.LETTERS_DIR / "old.md").write_text("Dear Hiring Team,\n\nText.", encoding="utf-8")
    store.save_jobs([store.new_job(id="old", title="Dev", company="D", status="letter_ready", cover_letter_file="old.md")])
    assert api.job_detail("old")["letter_editable"] is False
    assert api.letter_for_edit("old")["ok"] is False
    assert api.rewrite_paragraph("old", ["a"], 0)["ok"] is False


def test_a_letter_with_another_shape_than_the_template_is_not_offered_for_editing(api):
    """Letters built by an early version have two or three paragraphs: the editor could never save them."""
    import zipfile

    from lxml import etree
    job = _lead_with_docs()
    path = config.LETTERS_DIR / job["cover_letter_file"]
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    root = etree.fromstring(parts["word/document.xml"])
    body = root.find(f"{{{cover_letter.W}}}body")
    for p in cover_letter._slots(body)["body"][:3]:
        body.remove(p)
    parts["word/document.xml"] = etree.tostring(root)
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    store.save_jobs([job])
    assert len(cover_letter.read_letter(path)["paragraphs"]) == 2
    assert api.job_detail("lead")["letter_editable"] is False
    got = api.letter_for_edit("lead")
    assert got["ok"] is False and "Open it in Word" in got["msg"]
    assert api.rewrite_paragraph("lead", ["a", "b"], 0)["ok"] is False
    assert api.job_detail("lead")["letter_old_format"] is True and "older format" in got["msg"]


def test_only_an_app_letter_in_an_old_layout_is_called_older_format(api):
    (config.LETTERS_DIR / "mine.docx").write_bytes(b"own")
    store.save_jobs([_lead_with_docs(),
                     store.new_job(id="own", title="Dev", company="B", status="waiting", source="manual", cover_letter_file="mine.docx"),
                     store.new_job(id="none", title="Dev", company="C")])
    assert [api.job_detail(i)["letter_old_format"] for i in ("lead", "own", "none")] == [False, False, False]


def test_saving_changes_only_the_paragraphs_and_keeps_the_old_version(api):
    store.save_jobs([_lead_with_docs()])
    path = config.LETTERS_DIR / "Letter_lead.docx"
    before = cover_letter.read_letter(path)
    new = list(PARAS); new[2] = "I built a REST API in Kotlin and deployed it on Azure — with CI in GitHub Actions. " * 3
    result = api.save_letter("lead", new)
    assert result["ok"] is True
    after = cover_letter.read_letter(path)
    assert after["paragraphs"][2].startswith("I built a REST API") and "—" not in after["paragraphs"][2]    # em dash cleaned
    assert after["date_text"] == before["date_text"]
    assert before["title_line"] == "Junior Developer" and after["title_line"] == cover_letter.own_title(api.cv_text()) != "", \
        "the head carries your own title from your CV, also in a letter written before that was so"
    assert after["paragraphs"][0] == PARAS[0]
    assert cover_letter.verify(config.LETTER_TEMPLATE, path, []) == []                 # layout identical to the template
    old = list((vault.backups_dir() / "letter_versions").iterdir())
    assert len(old) == 1 and vault.file_is_encrypted(old[0])


@pytest.mark.parametrize("bad", [PARAS[:4], PARAS + ["six"], [PARAS[0], "", *PARAS[2:]], []])
def test_a_letter_must_keep_five_paragraphs(api, bad):
    store.save_jobs([_lead_with_docs()])
    result = api.save_letter("lead", bad)
    assert result["ok"] is False and "5 paragraphs" in result["msg"]
    assert cover_letter.read_letter(config.LETTERS_DIR / "Letter_lead.docx")["paragraphs"] == PARAS


def test_rule_breaks_in_a_hand_edit_are_warnings_not_refusals(api):
    store.save_jobs([_lead_with_docs()])
    new = ["Alex is a strong candidate with years of production Kubernetes experience.",
           "Although I have limited experience, I learn fast.", "Short.", "Short.", "Short."]
    result = api.save_letter("lead", new)
    assert result["ok"] is True
    text = " ".join(result["warnings"])
    assert "short" in text and "Paragraph 1" in text and "first person" in text and "Paragraph 2" in text and "gap" in text


def test_rewrite_changes_one_paragraph_follows_the_rules_and_saves_nothing(api, monkeypatch):
    store.save_jobs([_lead_with_docs()])
    prompts = []

    def ask_json(prompt, **k):
        prompts.append(prompt)
        return {"paragraph": "My RAG assistant is the clearest evidence: I built its retrieval pipeline in Python — end to end."}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    result = api.rewrite_paragraph("lead", PARAS, 1, "more about the RAG project")
    assert result["ok"] and result["index"] == 1 and "—" not in result["paragraph"] and "RAG assistant" in result["paragraph"]
    assert "Rewrite paragraph 2" in prompts[0] and "more about the RAG project" in prompts[0] and "Alex Novak" in prompts[0]
    assert cover_letter.read_letter(config.LETTERS_DIR / "Letter_lead.docx")["paragraphs"] == PARAS      # untouched


def test_rewrite_retries_once_then_reports_the_reason(api, monkeypatch):
    store.save_jobs([_lead_with_docs()])
    calls = []
    replies = [{"paragraph": "Alex would like to bring this drive to the team."},
               {"paragraph": "I would like to bring this drive to the team."}]
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: calls.append(prompt) or replies[len(calls) - 1])
    assert api.rewrite_paragraph("lead", PARAS, 3)["paragraph"] == "I would like to bring this drive to the team."
    assert len(calls) == 2 and "first person" in calls[1]

    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"paragraph": "Although I lack experience, Alex learns fast."})
    failed = api.rewrite_paragraph("lead", PARAS, 3)
    assert failed["ok"] is False and failed["msg"]

    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: (_ for _ in ()).throw(llm.LimitReached("Claude's 5-hour limit is used up (99%).")))
    assert "limit is used up" in api.rewrite_paragraph("lead", PARAS, 3)["msg"]
    assert api.rewrite_paragraph("lead", PARAS, 9)["ok"] is False
