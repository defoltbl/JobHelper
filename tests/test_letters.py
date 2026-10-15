from jobhelper import api_core, letters, store


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


# ── your own letters live inside the app's folder ───────────────────────────
def test_own_letters_folder_is_inside_the_data_folder_by_default(isolate_data):
    from pathlib import Path

    from jobhelper import config
    assert config.own_letters_dir(None) == config.MY_LETTERS_DIR == isolate_data / "my_letters"
    assert config.own_letters_dir("") == config.MY_LETTERS_DIR and config.own_letters_dir("   ") == config.MY_LETTERS_DIR   # an empty line in .env
    assert config.own_letters_dir("~/somewhere/else") == Path("~/somewhere/else").expanduser()
    source = (Path(config.__file__)).read_text(encoding="utf-8")
    assert 'MY_LETTERS_DIR = DATA_DIR / "my_letters"' in source and "Documents" not in source


def test_the_folder_is_made_with_the_others_and_scanned(isolate_data):
    from jobhelper import config, letters, store
    config.ensure_dirs()
    assert config.COVER_LETTERS_DIR.is_dir()
    (config.COVER_LETTERS_DIR / "Alex_Novak_CoverLetter_Acme.docx").write_bytes(b"mine")
    jobs = [store.new_job(id="a", title="Dev", company="Acme")]
    assert letters.import_letters(jobs)["linked"] == 1 and jobs[0]["cover_letter_file"] == "Alex_Novak_CoverLetter_Acme.docx"


def test_the_app_counts_opens_and_never_changes_your_own_letters(isolate_data, monkeypatch):
    from jobhelper import config, store, ui_api
    config.ensure_dirs()
    opened = []
    monkeypatch.setattr(api_core.Desktop, "open", lambda self, target: opened.append(target))
    api = ui_api.Api()
    assert api.my_letters() == {"folder": str(config.COVER_LETTERS_DIR), "name": "my_letters", "count": 0, "inside_app": True}
    mine = config.COVER_LETTERS_DIR / "Alex_Novak_CoverLetter_Acme.docx"
    mine.write_bytes(b"mine")
    (config.COVER_LETTERS_DIR / "notes.txt").write_text("not a letter")
    assert api.my_letters()["count"] == 1
    assert api.open_my_letters() == {"ok": True} and opened == [config.COVER_LETTERS_DIR]
    store.save_jobs([store.new_job(id="a", title="Dev", company="Acme", status="waiting", source="manual", cover_letter_file=mine.name)])
    assert api.open_doc("letter", mine.name) == {"ok": True} and opened[-1] == mine          # opened from its own folder
    assert api.open_doc("letter", "../../etc/passwd")["ok"] is False
    detail = api.job_detail("a")
    assert detail["letter_editable"] is False and api.save_letter("a", ["x"] * 5)["ok"] is False
    assert mine.read_bytes() == b"mine"


# ── found on real data: a shared word is not the same company ───────────────
def test_one_shared_word_does_not_link_a_letter_to_another_company(tmp_path):
    (tmp_path / "AlexNovak_CoverLetter_GoodData.docx").write_text("x")
    jobs = [store.new_job(id="ntt", title="Data Engineer", company="NTT DATA, Inc.")]
    stats = letters.import_letters(jobs, tmp_path)
    assert jobs[0]["cover_letter_file"] == "" and jobs[0]["status"] == "found"          # not the NTT DATA lead
    assert stats == {"linked": 0, "seeded": 1, "scanned": 1} and jobs[1]["company"] == "Good Data"


def test_same_company_written_differently_still_links(tmp_path):
    for name in ("AlexNovak_CoverLetter_TDSYNNEX.docx", "AlexNovak_CoverLetter_ESET.docx", "AlexNovak_CoverLetter_GoodData.docx"):
        (tmp_path / name).write_text("x")
    jobs = [store.new_job(id="td", title="Dev", company="TD SYNNEX", status="waiting"),
            store.new_job(id="eset", title="Dev", company="ESET Research Czech Republic s.r.o.", status="waiting"),
            store.new_job(id="gd", title="Dev", company="GoodData", status="waiting")]
    stats = letters.import_letters(jobs, tmp_path)
    assert stats == {"linked": 3, "seeded": 0, "scanned": 3} and len(jobs) == 3
    assert [j["cover_letter_file"][-12:] for j in jobs] == ["DSYNNEX.docx", "er_ESET.docx", "oodData.docx"]


def test_a_letter_already_on_a_job_never_seeds_a_second_application(tmp_path):
    (tmp_path / "AlexNovak_CoverLetter_OldName.docx").write_text("x")
    jobs = [store.new_job(id="merged", title="Dev", company="Completely New Name a.s.", status="rejected",
                          cover_letter_file="AlexNovak_CoverLetter_OldName.docx")]
    for _ in range(2):                                                                   # every search runs the import
        assert letters.import_letters(jobs, tmp_path) == {"linked": 1, "seeded": 0, "scanned": 1}
    assert len(jobs) == 1 and jobs[0]["status"] == "rejected"


# ── a letter belongs to the application it was written for ──────────────────
def _letter(folder, name, days_old):
    import os
    import time
    path = folder / name
    path.write_text("x")
    when = time.time() - days_old * 86400
    os.utime(path, (when, when))
    return path


def _days_ago(n):
    from datetime import date, timedelta
    return (date.today() - timedelta(days=n)).isoformat()


def test_an_old_letter_is_not_put_on_a_new_job_at_the_same_company(tmp_path):
    from jobhelper import agent3_letters
    _letter(tmp_path, "AlexNovak_CoverLetter_Acme.docx", days_old=60)
    jobs = [store.new_job(id="new", title="Data Engineer", company="Acme", status="found", date_found=_days_ago(2))]
    stats = letters.import_letters(jobs, tmp_path)
    lead = jobs[0]
    assert lead["cover_letter_file"] == "" and lead["status"] == "found" and "own_letter" not in lead      # the app will write a fresh one
    assert stats == {"linked": 0, "seeded": 1, "scanned": 1}
    assert jobs[1]["title"] == "(existing application)" and jobs[1]["cover_letter_file"].endswith("_Acme.docx")
    assert letters.import_letters(jobs, tmp_path) == {"linked": 1, "seeded": 0, "scanned": 1}              # and it stays that way
    assert agent3_letters._generated_letter(jobs[1]) is False                                              # your letter is never replaced


def test_a_letter_written_after_the_job_was_found_is_for_that_job(tmp_path):
    from jobhelper import agent3_letters
    _letter(tmp_path, "AlexNovak_CoverLetter_Acme.docx", days_old=1)
    jobs = [store.new_job(id="new", title="Data Engineer", company="Acme", status="found", date_found=_days_ago(5))]
    assert letters.import_letters(jobs, tmp_path) == {"linked": 1, "seeded": 0, "scanned": 1}
    assert jobs[0]["cover_letter_file"].endswith("_Acme.docx") and jobs[0]["status"] == "letter_ready" and jobs[0]["own_letter"] is True
    assert agent3_letters._generated_letter(jobs[0]) is False and len(jobs) == 1


def test_an_application_at_the_company_gets_the_letter_before_any_lead(tmp_path):
    _letter(tmp_path, "AlexNovak_CoverLetter_Acme.docx", days_old=1)
    jobs = [store.new_job(id="lead", title="Data Engineer", company="Acme", status="found", date_found=_days_ago(5)),
            store.new_job(id="app", title="Python Developer", company="Acme s.r.o.", status="rejected")]
    assert letters.import_letters(jobs, tmp_path) == {"linked": 1, "seeded": 0, "scanned": 1}
    assert jobs[1]["cover_letter_file"].endswith("_Acme.docx") and jobs[0]["cover_letter_file"] == ""


def test_a_lead_that_already_has_a_letter_keeps_it(tmp_path):
    _letter(tmp_path, "AlexNovak_CoverLetter_Acme.docx", days_old=0)
    jobs = [store.new_job(id="lead", title="Data Engineer", company="Acme", status="letter_ready", date_found=_days_ago(5),
                          cover_letter_file="Alex_Novak_CoverLetter_Acme_Data_Engineer.docx")]
    letters.import_letters(jobs, tmp_path)
    assert jobs[0]["cover_letter_file"] == "Alex_Novak_CoverLetter_Acme_Data_Engineer.docx" and len(jobs) == 2
