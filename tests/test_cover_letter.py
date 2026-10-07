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
