"""Offline tests for the CV adaptation (no LLM, no network)."""
import zipfile
from pathlib import Path

import docx
import pytest

from jobhelper import config, cv_tailor, llm, store

ROOT = Path(__file__).resolve().parent.parent
# A frozen copy of the master CV the approved examples were made from, so these
# tests do not change when the real CV in data/cv/ is edited.
MASTER = Path(__file__).parent / "fixtures" / "Candidate_CV_EN.docx"
EXAMPLE = Path(__file__).parent / "fixtures" / "cv_example_deutscheborse.docx"

pytestmark = pytest.mark.skipif(not MASTER.exists(), reason="master CV not present")


def _example_content():
    paras = [p.text for p in docx.Document(str(EXAMPLE)).paragraphs]
    profile = paras[4]
    rows = []
    for text in paras[6:13]:
        label, items = text.split(": ", 1)
        rows.append({"label": label, "items": items})
    return profile, rows, paras


def test_rebuilds_the_approved_example_exactly(tmp_path):
    profile, rows, example_paras = _example_content()
    out = tmp_path / "out.docx"
    cv_tailor.build_docx(MASTER, out, profile, rows)
    assert [p.text for p in docx.Document(str(out)).paragraphs] == example_paras
    assert cv_tailor.verify(MASTER, out) == []


def test_only_document_xml_changes(tmp_path):
    profile, rows, _ = _example_content()
    out = tmp_path / "out.docx"
    cv_tailor.build_docx(MASTER, out, profile, rows)
    with zipfile.ZipFile(MASTER) as zm, zipfile.ZipFile(out) as zo:
        assert zm.namelist() == zo.namelist()
        for name in zm.namelist():
            if name != "word/document.xml":
                assert zm.read(name) == zo.read(name)


def test_approved_example_passes_the_content_checks():
    profile, rows, _ = _example_content()
    master_text = "\n".join(p.text for p in docx.Document(str(MASTER)).paragraphs)
    unverified = cv_tailor.unverified_terms(master_text)
    assert "Kubernetes" in unverified and "Docker" not in unverified
    m = docx.Document(str(MASTER)).paragraphs
    assert cv_tailor.content_problems(profile, rows, m[4].text, cv_tailor.master_rows(MASTER),
                                      unverified, master_text) == []


def test_unverified_tech_is_rejected_and_stripped():
    unverified = ["Kubernetes", "Kafka"]
    profile = "MSc graduate. Experienced with Kubernetes in production. Keen to grow into Kafka."
    rows = [{"label": "Containers", "items": "Docker, Kubernetes, Docker Compose (multi-service stacks)"}]
    problems = cv_tailor.content_problems(profile, rows * 4, "x" * 500, ["y" * 100] * 6, unverified)
    assert any("KEY SKILLS" in p for p in problems) and any("only as an interest" in p for p in problems)
    new_profile, new_rows = cv_tailor.enforce(profile, rows, unverified)
    assert "Experienced with Kubernetes" not in new_profile
    assert "Keen to grow into Kafka." in new_profile          # interest sentence is allowed
    assert new_rows[0]["items"] == "Docker, Docker Compose (multi-service stacks)"


def test_clean_removes_em_dash_and_emoji():
    assert cv_tailor.clean("Azure — App Service 🚀") == "Azure – App Service"


def test_file_name_follows_the_instruction():
    job = {"company": "Deutsche Börse Group", "title": "Junior Middleware Administrator (f/m/d)"}
    assert cv_tailor.file_stem(MASTER, job, "Middleware Admin") == "Candidate_CV_DeutscheBorse_MiddlewareAdmin"


def test_tailor_end_to_end_with_mocked_model(isolate_data, monkeypatch):
    profile, rows, example_paras = _example_content()
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {
        "profile": profile, "skills": rows, "role_short": "Middleware Admin"})
    job = store.new_job(id="linkedin-1", title="Junior Middleware Administrator",
                        company="Deutsche Börse Group", description="Linux, Kubernetes, Kafka")
    cv_text = "\n".join(p.text for p in docx.Document(str(MASTER)).paragraphs)
    name = cv_tailor.tailor(job, cv_text, MASTER)
    assert name == "Candidate_CV_DeutscheBorse_MiddlewareAdmin.docx"
    out = config.TAILORED_CV_DIR / name
    assert [p.text for p in docx.Document(str(out)).paragraphs] == example_paras


def test_skill_terms_must_exist_in_the_master():
    master_text = "\n".join(p.text for p in docx.Document(str(MASTER)).paragraphs)
    assert cv_tailor.unknown_skill_terms("Docker, PostgreSQL, schema design, GitHub Actions", master_text) == []
    assert cv_tailor.unknown_skill_terms("Docker, Snowflake, AWS S3", master_text) == ["Snowflake", "AWS", "S3"]
    _, rows = cv_tailor.enforce("Fine.", [{"label": "Data", "items": "PostgreSQL, Snowflake, pgvector"}], [], master_text)
    assert rows[0]["items"] == "PostgreSQL, pgvector"


@pytest.mark.parametrize("master, prefix", [
    ("JaneDoe_CV_EN.docx", "JaneDoe"), ("Jane Doe Resume.docx", "JaneDoe"), ("jane-doe-cv.docx", "janedoe"),
    ("JaneDoe.docx", "JaneDoe"), ("CV.docx", "Candidate"), ("Candidate_CV_EN.docx", "Candidate"),
])
def test_file_names_work_for_any_persons_cv(master, prefix):
    job = store.new_job(id="x", title="Data Analyst (m/f/d)", company="Acme s.r.o.")
    stem = cv_tailor.file_stem(master, job, "Data Analyst")
    assert stem == f"{prefix}_CV_Acme_DataAnalyst"
    from jobhelper import cover_letter
    assert cover_letter.file_stem(master, job, "Data Analyst") == f"{prefix}_CoverLetter_Acme_DataAnalyst"


def test_without_a_rules_file_the_general_rules_are_used(isolate_data):
    assert not config.CV_INSTRUCTION.exists()
    assert cv_tailor.load_rules("Jane Doe") == cv_tailor.GENERIC_RULES
    config.CV_INSTRUCTION.write_text("## 1. What changes\nAdapt the profile of {{first_name}}.\n## 2. Skipped\nx\n", encoding="utf-8")
    assert cv_tailor.load_rules("Jane Doe\nAnalyst") == "## 1. What changes\nAdapt the profile of Jane."
