"""Offline tests for the CV adaptation (no LLM, no network)."""
import zipfile
from pathlib import Path

import docx
import pytest

from jobhelper import word_document, config, cv_tailor, llm, store

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


# ── any CV layout: the skills rows end at the next heading, whatever it is called ──
def _cv_docx(path, lines):
    import docx
    doc = docx.Document()
    for line in lines:
        doc.add_paragraph(line)
    doc.save(str(path))
    return path


OTHER_LAYOUT = ["Alex Novak", "Prague · alex@example.com", "SUMMARY", "Accountant with three years in a shared service centre.",
                "SKILLS", "Accounting: IFRS, VAT, accounts payable", "Tools: SAP, Excel", "Languages: English C1",
                "EXPERIENCE", "Junior Accountant, Example s.r.o. (2023 - 2026)", "Month-end close and VAT returns for two entities.",
                "Accounts payable for 40 suppliers.", "EDUCATION", "BSc Economics, 2023", "INTERESTS", "Running"]


def _body(path):
    import zipfile

    from lxml import etree
    with zipfile.ZipFile(path) as z:
        return etree.fromstring(z.read("word/document.xml")).find(f"{{{word_document.W}}}body")


def test_another_cv_layout_keeps_its_experience_section(tmp_path):
    master = _cv_docx(tmp_path / "AlexNovak_CV.docx", OTHER_LAYOUT)
    sec = cv_tailor._sections(_body(master))
    assert cv_tailor._text(sec["profile"]).startswith("Accountant with three years")
    assert [cv_tailor._text(p) for p in sec["rows"]] == OTHER_LAYOUT[5:8]                 # the three skill rows, and not one line more
    assert cv_tailor.adaptable(master) is True and cv_tailor.master_rows(master) == OTHER_LAYOUT[5:8]
    out = tmp_path / "adapted.docx"
    cv_tailor.build_docx(master, out, "Accountant who closes the books on time.",
                         [{"label": "Accounting", "items": "IFRS, VAT"}, {"label": "Tools", "items": "SAP, Excel"}])
    text = [cv_tailor._text(p) for p in cv_tailor._sections(_body(out))["paras"]]
    for line in OTHER_LAYOUT[8:]:                                                           # everything after the skills is still there
        assert line in text, line
    assert "Accountant who closes the books on time." in text and "Accounting: IFRS, VAT" in text and OTHER_LAYOUT[7] not in text
    assert cv_tailor.verify(master, out) == []


def test_a_section_that_went_missing_fails_the_check(tmp_path):
    master = _cv_docx(tmp_path / "master.docx", OTHER_LAYOUT)
    broken = _cv_docx(tmp_path / "broken.docx", [x for x in OTHER_LAYOUT if x not in OTHER_LAYOUT[8:12]])     # no EXPERIENCE at all
    problems = cv_tailor.verify(master, broken)
    assert any("section of the master CV is missing" in p or "locked paragraph" in p for p in problems)


@pytest.mark.parametrize("line, heading", [
    ("EXPERIENCE", True), ("W O R K   E X P E R I E N C E", True), ("WORK EXPERIENCE & PRACTICAL TRAINING", True), ("ZKUŠENOSTI", True),
    ("Accounting: IFRS, VAT", False), ("AWS: EC2, S3", False), ("Python, SQL, Docker", False), ("", False), ("2023", False),
    ("A" * 61, False), ("Junior Accountant, Example s.r.o.", False),
])
def test_what_counts_as_a_heading(line, heading):
    assert cv_tailor._is_heading(line) is heading


def test_a_cv_without_a_profile_or_with_endless_rows_is_left_alone(tmp_path):
    no_profile = _cv_docx(tmp_path / "a.docx", ["Alex Novak", "EXPERIENCE", "Junior Accountant", "EDUCATION", "BSc"])
    assert cv_tailor.adaptable(no_profile) is False and cv_tailor.adaptable(tmp_path / "missing.docx") is False
    (tmp_path / "not_word.docx").write_bytes(b"plain text")
    assert cv_tailor.adaptable(tmp_path / "not_word.docx") is False
    endless = _cv_docx(tmp_path / "b.docx", ["Alex Novak", "PROFILE", "A developer.", "KEY SKILLS"] + [f"Row {n}: thing" for n in range(20)])
    sec = cv_tailor._sections(_body(endless))
    assert sec["rows"] == [] and sec["rows_unclear"] is True and sec["profile"] is not None     # the profile is still adapted
    heading_after = _cv_docx(tmp_path / "c.docx", ["Alex Novak", "PROFILE", "KEY SKILLS", "Tools: Excel"])
    assert cv_tailor._sections(_body(heading_after))["profile"] is None                         # an empty profile section is not a profile


def test_a_word_cv_without_a_profile_section_still_gets_a_profile_note(isolate_data, tmp_path, monkeypatch):
    from jobhelper import agent3_letters, config, llm
    config.ensure_dirs()
    master = _cv_docx(config.CV_DIR / "AlexNovak_CV.docx", ["Alex Novak", "EXPERIENCE", "Junior Accountant", "EDUCATION", "BSc"])
    monkeypatch.setattr(cv_tailor, "tailor", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no profile section: not adaptable")))
    monkeypatch.setattr(llm, "ask", lambda *a, **k: "Accountant with three years of month-end closing.")
    job = store.new_job(id="j1", title="Accountant", company="Example", description="IFRS")
    name = agent3_letters._make_tailored_cv(job, "Alex Novak\nAccountant", master, dict(title="Accountant", company="Example", location="", description="IFRS"))
    assert name.endswith(".md") and "month-end closing" in (config.TAILORED_CV_DIR / name).read_text(encoding="utf-8")


def test_a_replaced_document_is_kept_in_the_backup(isolate_data):
    from jobhelper import agent3_letters, config, vault
    config.ensure_dirs()
    old = config.TAILORED_CV_DIR / "Old_CV.docx"
    old.write_bytes(b"the earlier adapted CV")
    agent3_letters._retire(old)
    kept = list((vault.backups_dir() / "letter_versions").iterdir())
    assert not old.exists() and len(kept) == 1 and vault.read_bytes(kept[0]) == b"the earlier adapted CV"
    agent3_letters._retire(old)                                        # nothing there: nothing happens
    assert len(list((vault.backups_dir() / "letter_versions").iterdir())) == 1


# ── the posting's words stated as the person's experience, in any profession ──
ACCOUNTANT_CV = ("Junior accountant with a bachelor's degree in finance and one year of practice in accounts payable. "
                 "Processed about 300 supplier invoices a month in SAP, prepared weekly payment runs, reconciled supplier statements "
                 "and helped with the month-end closing. Bank reconciliation, VAT returns, SAP FI, MS Excel.")
AP_POSTING = ("You will post invoices with the correct tax codes and cost centers, keep the vendor master data up to date within our "
              "Procure to Pay process, and confirm intercompany balances. Experience with Coupa is a plus. We work in SAP.")


def test_terms_of_the_posting_that_the_cv_knows_nothing_of_are_found():
    """Seen with an accountant's CV: the adapted profile said "coding tax and cost center data" and "vendor master
    data upkeep". The fixed never-claim list knows technologies only, so nothing objected."""
    draft = ("Junior accountant with one year of practice in accounts payable. Experienced in processing supplier invoices, "
             "coding tax codes and cost center data, and vendor master data upkeep in SAP. Keen to grow into intercompany balances and Coupa.")
    found = [p.lower() for p in cv_tailor.borrowed_phrases(draft, AP_POSTING, ACCOUNTANT_CV)]
    assert {"tax codes", "cost center", "vendor master", "master data", "intercompany balances"} <= set(found)
    claimed = [p.lower() for p in cv_tailor.borrowed_claims(draft, AP_POSTING, ACCOUNTANT_CV)]
    assert {"tax codes", "cost center", "vendor master", "master data"} <= set(claimed)
    assert "intercompany balances" not in claimed, "named as an interest: that is the honest way"


def test_wording_the_cv_backs_is_left_alone():
    fine = ("Junior accountant with one year of practice in accounts payable. Experienced in processing supplier invoices, "
            "payment runs and reconciling supplier statements in SAP, and in supporting the month-end closing.")
    assert cv_tailor.borrowed_phrases(fine, AP_POSTING, ACCOUNTANT_CV) == []
    # one shared word is not enough; endings do not matter; what the person wrote in their notes counts as theirs
    assert cv_tailor.borrowed_phrases("I reconciled invoices and posted invoice batches.", AP_POSTING, ACCOUNTANT_CV) == []
    notes = ACCOUNTANT_CV + "\nI also kept the vendor master data up to date."
    assert "vendor master" not in [p.lower() for p in cv_tailor.borrowed_phrases("Kept vendor master data current.", AP_POSTING, notes)]
    assert cv_tailor.borrowed_phrases("", AP_POSTING, ACCOUNTANT_CV) == [] and cv_tailor.borrowed_phrases("Cost centers.", "", ACCOUNTANT_CV) == []
    assert cv_tailor.borrowed_claims("", AP_POSTING, ACCOUNTANT_CV) == []


def test_a_draft_that_borrows_from_the_posting_is_sent_back_and_what_is_left_is_noted(isolate_data, monkeypatch):
    profile, rows, _ = _example_content()
    cv_text = "\n".join(p.text for p in docx.Document(str(MASTER)).paragraphs)
    posting = "You will run quarterly zebra migrations and tune walrus pipelines for our platform."
    assert "zebra" not in cv_text.lower() and "walrus" not in cv_text.lower()
    borrowed = profile.rstrip() + " Experienced in zebra migrations."
    prompts, answers = [], [{"profile": borrowed, "skills": rows, "role_short": "Admin"}, {"profile": profile, "skills": rows, "role_short": "Admin"}]
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: prompts.append(prompt) or answers[min(len(prompts) - 1, 1)])
    job = store.new_job(id="j1", title="Administrator", company="Acme", description=posting)
    name = cv_tailor.tailor(job, cv_text, MASTER)
    assert len(prompts) == 2 and "PROFILE presents 'zebra migrations' as the candidate's experience" in prompts[1]
    assert "cv_check" not in job                                            # the second draft is clean
    text = "\n".join(p.text for p in docx.Document(str(config.TAILORED_CV_DIR / name)).paragraphs)
    assert "zebra" not in text
    # the model insists: the app does not cut the sentence out, it tells the person what to look at
    prompts.clear()
    answers[1] = answers[0]
    job = store.new_job(id="j2", title="Administrator", company="Acme", description=posting)
    cv_tailor.tailor(job, cv_text, MASTER)
    assert job["cv_check"] == ["zebra migrations"]
    # named as an interest, it is neither sent back nor noted
    prompts.clear()
    keen = {"profile": profile.rstrip() + " Keen to grow into zebra migrations.", "skills": rows, "role_short": "Admin"}
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: prompts.append(prompt) or keen)
    job = store.new_job(id="j3", title="Administrator", company="Acme", description=posting)
    cv_tailor.tailor(job, cv_text, MASTER)
    assert not any("zebra migrations' as the candidate" in prompt for prompt in prompts) and "cv_check" not in job
