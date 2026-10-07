from jobhelper import letters, store


def test_parse_company():
    assert letters.parse_company("AlexNovak_CoverLetter_DeutscheBorse.docx") == "Deutsche Borse"
    assert letters.parse_company("AlexNovak_CoverLetter_SAP.docx") == "SAP"
    assert letters.parse_company("AlexNovak_CoverLetter_SecondFoundation.docx") == "Second Foundation"
    assert letters.parse_company("AlexNovak_CoverLetter_DeutscheBorse_M.docx") == "Deutsche Borse"


def test_scan_dedupes_and_skips_generic(tmp_path):
    (tmp_path / "AlexNovak_CoverLetter_Veeam.docx").write_text("x")
    (tmp_path / "AlexNovak_CoverLetter_Veeam.pdf").write_text("x")  # dup company
    (tmp_path / "Cover_Letter.docx").write_text("x")                       # generic → skipped
    recs = letters.scan(tmp_path)
    assert [r["company"] for r in recs] == ["Veeam"]


def test_import_links_matching_and_seeds_new(tmp_path):
    (tmp_path / "AlexNovak_CoverLetter_Siemens.docx").write_text("x")
    (tmp_path / "AlexNovak_CoverLetter_Mastercard.docx").write_text("x")
    jobs = [store.new_job(id="jobscz-1", company="Siemens Mobility, s.r.o.", title="QA", status="found")]

    stats = letters.import_letters(jobs, tmp_path)
    assert stats["linked"] == 1
    assert stats["seeded"] == 1

    siemens = store.find(jobs, "jobscz-1")
    assert siemens["cover_letter_file"] == "AlexNovak_CoverLetter_Siemens.docx"
    assert siemens["status"] == "letter_ready"

    seeded = [j for j in jobs if j["source"] == "manual"]
    assert seeded[0]["company"] == "Mastercard"
    assert seeded[0]["status"] == "waiting"
    assert seeded[0]["cover_letter_file"].endswith("Mastercard.docx")


def test_scan_missing_dir_returns_empty(tmp_path):
    assert letters.scan(tmp_path / "does_not_exist") == []
