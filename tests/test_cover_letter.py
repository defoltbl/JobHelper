"""Offline tests for the cover-letter writer (no LLM, no network)."""
from datetime import date
from pathlib import Path

import docx
import pytest

from jobhelper import config, cover_letter, llm, store

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "data" / "cover_letter_template.docx"
# A frozen copy of the master CV the approved examples were made from, so these
# tests do not change when the real CV in data/cv/ is edited.
MASTER = Path(__file__).parent / "fixtures" / "Candidate_CV_EN.docx"
EXAMPLE = Path(__file__).parent / "fixtures" / "letter_example_deutscheborse.docx"

pytestmark = pytest.mark.skipif(not (TEMPLATE.exists() and MASTER.exists()), reason="template/master not present")


def _example():
    paras = [p.text for p in docx.Document(str(EXAMPLE)).paragraphs]
    return paras[1], paras[7:12], paras


def _master_text():
    return "\n".join(p.text for p in docx.Document(str(MASTER)).paragraphs)


def test_rebuilds_the_approved_example_exactly(tmp_path):
    title, body, example_paras = _example()
    out = tmp_path / "letter.docx"
    cover_letter.build_docx(TEMPLATE, out, title, body, when=date(2026, 10, 6))
    assert [p.text for p in docx.Document(str(out)).paragraphs] == example_paras
    assert cover_letter.verify(TEMPLATE, out) == []


def test_approved_example_passes_the_content_checks():
    _, body, _ = _example()
    unverified = cover_letter.unverified_terms(_master_text())
    assert "Kubernetes" in unverified and "Copilot" in unverified and "Docker" not in unverified
    assert cover_letter.content_problems(body, unverified) == []


def test_gap_admissions_are_rejected_and_removed():
    _, body, _ = _example()
    bad = list(body)
    bad[3] += " Although I have not worked with Kubernetes yet, I am a fast learner."
    problems = cover_letter.content_problems(bad, ["Kubernetes"])
    assert any("admits a gap" in p for p in problems)
    assert "Although" not in cover_letter.enforce(bad, ["Kubernetes"])[3]


def test_unbacked_experience_claim_is_rejected_but_a_wish_is_fine():
    _, body, _ = _example()
    claim = list(body)
    claim[1] += " I have worked with Kubernetes clusters in production."
    assert any("as experience" in p for p in cover_letter.content_problems(claim, ["Kubernetes"]))
    assert "Kubernetes clusters in production" not in cover_letter.enforce(claim, ["Kubernetes"])[1]
    wish = list(body)
    wish[3] += " I would like to work with Terraform next."
    assert cover_letter.content_problems(wish, ["Terraform", "Kubernetes"]) == []


def test_date_format():
    assert cover_letter.letter_date(date(2026, 10, 6)) == "6 October 2026"


def test_write_end_to_end_with_mocked_model(isolate_data, monkeypatch):
    title, body, example_paras = _example()
    monkeypatch.setattr(config, "LETTER_TEMPLATE", TEMPLATE)
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {
        "title_line": title, "paragraphs": body, "role_short": "Middleware Admin"})
    job = store.new_job(id="jobscz-1", title="Junior Middleware Administrator (f/m/d)",
                        company="Deutsche Börse Group", description="Linux, Kubernetes, Kafka")
    name = cover_letter.write(job, _master_text(), MASTER)
    assert name == "Candidate_CoverLetter_DeutscheBorse_MiddlewareAdmin.docx"
    got = [p.text for p in docx.Document(str(config.LETTERS_DIR / name)).paragraphs]
    assert got[1] == title and got[7:12] == body
    assert got[5] == cover_letter.letter_date()            # today's date
    assert got[:5] == example_paras[:5] and got[12:] == example_paras[12:]   # head + closing untouched


# ── first person only (the first real run produced a letter about "Alex ... he") ──
def test_third_person_letter_is_detected():
    about_him = ["The role matches the way Alex already works.", "He would like to bring the same drive to SAP."]
    as_him = ["The role matches the way I already work.", "My thesis was presented at two conferences."]
    assert cover_letter.third_person(about_him, "Alex") is True
    assert cover_letter.third_person(["PostgreSQL work gives the clearest evidence.", "He can start soon."], "Alex") is True
    assert cover_letter.third_person(as_him, "Alex") is False
    assert "third person" in cover_letter.content_problems(about_him, [], "Alex")[0]
    assert cover_letter.candidate_first_name("Alex Novak\nJunior Software Developer") == "Alex"
    assert cover_letter.candidate_first_name("") == ""


def test_third_person_letter_is_retried_and_never_saved(isolate_data, monkeypatch):
    import shutil
    shutil.copy2(TEMPLATE, config.LETTER_TEMPLATE)
    calls = []
    para = ("The role matches the way Alex already works across backend systems and data pipelines. " * 6).strip()

    def ask_json(prompt, **kw):
        calls.append(prompt)
        return {"title_line": "Junior Developer", "paragraphs": [para] * 5, "role_short": "Dev"}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    job = store.new_job(id="linkedin-9", title="Junior Developer", company="Acme", description="Python")
    with pytest.raises(ValueError, match="third person"):
        cover_letter.write(job, _master_text(), MASTER)
    assert len(calls) == 2 and "first person" in calls[1]          # told what was wrong on the retry
    assert list(config.LETTERS_DIR.glob("*.docx")) == []


# ── the posting's words stated as the candidate's own experience ────────────
ACCOUNTANT = ("Junior accountant with one year of practice in accounts payable. Processed about 300 supplier invoices a month in SAP, "
              "prepared weekly payment runs, reconciled supplier statements and helped with the month-end closing.")
POSTING = ("You will post invoices with the correct tax codes and cost centers, keep the vendor master data up to date and confirm "
           "intercompany balances with our entities. Analyst I level. We work in SAP.")


def test_a_letter_that_states_the_posting_s_terms_as_experience_is_noticed():
    claims = cover_letter.borrowed_claims
    said = ["In my current role I process a high volume of invoices in SAP, assigning the correct tax codes and cost centers, "
            "which matches the core requirement of posting invoices for your mother entity."]
    assert {"tax codes", "cost centers"} <= {c.lower() for c in claims(said, POSTING, ACCOUNTANT)}
    # speaking of the role, of the reader or of the future is what a letter is for
    for fine in ("The AP Accountant role caught my attention because it covers tax codes, cost centers and vendor master data.",
                 "Your team keeps the vendor master data current and confirms intercompany balances, which is work I respect.",
                 "I would like to grow into vendor master data and intercompany balances.",
                 "I perform the month-end closing, skills that should translate well to confirming intercompany balances.",
                 "I reconciled supplier statements and prepared payment runs in SAP.",
                 "The Analyst I opening stood out to me because it covers cost centers and tax codes."):
        assert claims([fine], POSTING, ACCOUNTANT) == [], fine
    assert claims([], POSTING, ACCOUNTANT) == [] and claims(said, "", ACCOUNTANT) == []
    # what the person wrote in their own notes is theirs
    assert claims(said, POSTING, ACCOUNTANT + " I assigned tax codes and cost centers to every invoice.") == []


def test_a_letter_that_borrows_is_sent_back_and_what_is_left_is_noted(isolate_data, monkeypatch):
    title, body, _ = _example()
    monkeypatch.setattr(config, "LETTER_TEMPLATE", TEMPLATE)
    posting = "You will run quarterly zebra migrations and tune walrus pipelines for our platform."
    borrowed = list(body)
    borrowed[2] = body[2].rstrip() + " I ran zebra migrations every quarter."
    prompts, answers = [], [{"title_line": title, "paragraphs": borrowed, "role_short": "Admin"}, {"title_line": title, "paragraphs": body, "role_short": "Admin"}]
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: prompts.append(prompt) or answers[min(len(prompts) - 1, 1)])
    job = store.new_job(id="j1", title="Administrator", company="Acme", description=posting)
    name = cover_letter.write(job, _master_text(), MASTER)
    assert len(prompts) == 2 and "The letter presents 'zebra migrations' as the candidate's own experience" in prompts[1]
    assert "letter_check" not in job
    assert "zebra" not in "\n".join(p.text for p in docx.Document(str(config.LETTERS_DIR / name)).paragraphs)
    # the model insists: nothing is cut out silently, the person is told what to look at
    prompts.clear()
    answers[1] = answers[0]
    job = store.new_job(id="j2", title="Administrator", company="Acme", description=posting)
    cover_letter.write(job, _master_text(), MASTER)
    assert job["letter_check"] == ["zebra migrations"]
