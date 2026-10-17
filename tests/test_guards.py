"""Rules the app must never break: the user's own letters stay untouched, closed
postings leave the list, emails link to the right company, progress is reported."""
from pathlib import Path

import pytest

from jobhelper import job_sources, api_core, agent2_search, agent3_letters, config, email_client, filters, llm, store

ENGLISH_AD = ("We are looking for a junior Python developer to join our team in Prague. "
              "You will work with the backend team and write clean, tested code every day.")


# ── the user's own cover letters ────────────────────────────────────────────
def _letter(name: str) -> None:
    config.ensure_dirs()
    (config.LETTERS_DIR / name).write_bytes(b"letter")


def test_manual_letter_is_not_a_generated_one(isolate_data):
    _letter("mine.docx")
    job = store.new_job(id="m1", source="manual", cover_letter_file="mine.docx")
    assert agent3_letters._generated_letter(job) is False


def test_letter_stored_outside_the_app_folder_is_not_generated(isolate_data):
    config.ensure_dirs()
    job = store.new_job(id="m2", source="linkedin", cover_letter_file="from_documents.docx")
    assert agent3_letters._generated_letter(job) is False


def test_app_written_letter_is_generated(isolate_data):
    _letter("AlexNovak_CoverLetter_Acme_Dev.docx")
    job = store.new_job(id="g1", source="linkedin", cover_letter_file="AlexNovak_CoverLetter_Acme_Dev.docx")
    assert agent3_letters._generated_letter(job) is True


def test_rewrite_never_replaces_the_users_own_letter(isolate_data, monkeypatch):
    _letter("mine.docx")
    job = store.new_job(id="m1", title="Dev", company="Acme", source="manual",
                        cover_letter_file="mine.docx", status="waiting")

    def forbidden(*args, **kwargs):
        raise AssertionError("the user's own letter must never be rewritten")

    monkeypatch.setattr(agent3_letters, "_make_letter", forbidden)
    done = agent3_letters.generate_for(job, cv_text="", rewrite_letter=True)
    assert done["letter"] is False
    assert job["cover_letter_file"] == "mine.docx"
    assert (config.LETTERS_DIR / "mine.docx").read_bytes() == b"letter"


def test_rewrite_replaces_an_app_written_letter(isolate_data, monkeypatch):
    _letter("old.docx")
    job = store.new_job(id="g1", title="Dev", company="Acme", source="linkedin", cover_letter_file="old.docx")
    monkeypatch.setattr(agent3_letters, "_make_letter", lambda *a, **k: "new.docx")
    done = agent3_letters.generate_for(job, cv_text="", rewrite_letter=True)
    assert done["letter"] is True and job["cover_letter_file"] == "new.docx"


# ── closed postings ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "No longer accepting applications",
    "This position has been filled.",
    "Pozice byla obsazena",
])
def test_is_closed_detects_closed_postings(text):
    assert filters.is_closed(text)


def test_is_closed_leaves_open_postings():
    assert not filters.is_closed("We are accepting applications until Friday.")
    assert not filters.is_closed("")


def test_closed_postings_leave_the_list_and_applications_are_kept():
    closed = "No longer accepting applications"
    jobs = [store.new_job(id="lead-closed", description=closed),
            store.new_job(id="lead-open", description="Join us"),
            store.new_job(id="applied", description=closed, status="waiting")]
    dropped = []
    assert agent2_search.check_closed(jobs, dropped=dropped, network=False) == {"asked": 0, "removed": 1, "marked": 0}
    assert [j["id"] for j in jobs] == ["lead-open", "applied"]
    assert dropped[0]["group"] == "closed" and dropped[0]["reason"] == agent2_search.CLOSED_REASON and dropped[0]["job"]["id"] == "lead-closed"


# ── matching emails to jobs ─────────────────────────────────────────────────
@pytest.mark.parametrize("left, right", [
    ("Valeo", "Valeo s.r.o."),
    ("Siemens", "Siemens, s.r.o."),
    ("Foo", "Foo a.s."),
    ("HP", "HP Inc."),
    ("NN", "NN Group"),
])
def test_norm_company_ignores_legal_suffixes(left, right):
    assert email_client.norm_company(left) == email_client.norm_company(right)


def test_norm_company_keeps_different_companies_apart():
    assert email_client.norm_company("Valeo") != email_client.norm_company("Veolia")
    assert email_client.norm_company("A.S. Watson") != email_client.norm_company("Watson")


def test_best_job_for_company_picks_the_matching_role():
    jobs = [store.new_job(id="v1", title="Embedded C Engineer", company="Valeo"),
            store.new_job(id="v2", title="SW Tool Developer Python", company="Valeo s.r.o."),
            store.new_job(id="o1", title="SW Tool Developer", company="Other")]
    best = email_client.best_job_for_company_role("Valeo", "Application received: SW Tool Developer", jobs)
    assert best["id"] == "v2"


def test_best_job_for_untracked_company_is_none():
    jobs = [store.new_job(id="v1", title="Dev", company="Valeo")]
    assert email_client.best_job_for_company_role("Unknown Corp", "Your application", jobs) is None
    assert email_client.best_job_for_company_role("", "Your application", jobs) is None


def test_match_job_prefers_sender_over_footer_mentions():
    jobs = [store.new_job(id="valeo", title="SW Tool Developer", company="Valeo"),
            store.new_job(id="ms", title="Support Engineer", company="Microsoft")]
    hit = email_client.match_job("careers@valeo.com", "Your application for SW Tool Developer",
                                 "Thank you. Sent with Microsoft 365 Outlook.", jobs)
    assert hit["id"] == "valeo"


# ── progress reporting ──────────────────────────────────────────────────────
def test_search_reports_progress_per_request(monkeypatch):
    def provider(query, where, limit):
        return [store.new_job(id="p-" + query, title="Junior Python Developer " + query.upper(), company="Acme",
                              location=where, description=ENGLISH_AD)]

    monkeypatch.setattr(agent2_search.job_sources, "sources_for", lambda source, max_age_days=0, country="": [job_sources.Board("one", provider), job_sources.Board("two", provider)])
    seen = []
    found = agent2_search.search(["a", "b", "c"], where="Prague", progress=lambda done, total: seen.append((done, total)))
    assert seen == [(i, 6) for i in range(6)]
    assert {j["id"] for j in found} == {"p-a", "p-b", "p-c"}


def test_search_without_progress_callback_still_works(monkeypatch):
    monkeypatch.setattr(agent2_search.job_sources, "sources_for", lambda source, max_age_days=0, country="": [job_sources.Board("one", lambda q, w, n: [])])
    assert agent2_search.search(["a"], where="Prague") == []


def test_scoring_reports_progress_only_for_jobs_it_processes(isolate_data, monkeypatch):
    jobs = [store.new_job(id="1", title="Dev", company="A", location="Praha"),
            store.new_job(id="done", title="Dev", company="B", location="Praha", match_score=70, cover_letter_file="l.docx"),
            store.new_job(id="applied", title="Dev", company="C", location="Praha", status="waiting"),
            store.new_job(id="2", title="Dev", company="D", location="Praha")]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 10, "match_reason": "weak"})
    seen = []
    stats = agent3_letters.process(jobs, {"summary": "x"}, threshold=60,
                                   progress=lambda done, total: seen.append((done, total)))
    assert seen == [(0, 4), (2, 4), (3, 4)]          # one scoring step for both, then one step per job
    assert stats["scored"] == 2 and stats["skipped"] == 2


# ── what the first real search brought in ───────────────────────────────────
@pytest.mark.parametrize("location", ["Fremont, NE", "Prague, NE", "Austin, TX", "New York, NY, United States", "Remote, USA"])
def test_us_locations_are_recognised(location):
    assert filters.is_us_location(location)


@pytest.mark.parametrize("location", ["Prague", "Praha – Karlín", "Prague, Prague, Czechia", "Prague, CZ", "Brno, Czech Republic",
                                      "Remote", "Anywhere in the World", "Berlin, DE", ""])
def test_european_and_remote_locations_are_kept(location):
    assert not filters.is_us_location(location)


@pytest.mark.parametrize("text, years", [
    ("Requires 8+ years of infrastructure/platform security experience.", 8),
    ("Minimum 5 years of professional experience in sales engineering.", 5),
    ("1-2 years of professional technical work experience", 1),
    ("3 to 5 years experience with Java", 3),
    ("Founded 25 years ago. We offer 5 weeks of holiday.", 0),
    ("", 0),
])
def test_years_required(text, years):
    assert filters.years_required(text) == years


def test_many_years_only_blocks_junior_level_candidates():
    text = "Requires 5+ years of backend experience."
    assert filters.needs_too_many_years(text, "junior") and filters.needs_too_many_years(text, "graduate")
    assert not filters.needs_too_many_years(text, "mid") and not filters.needs_too_many_years(text, "senior")
    assert not filters.needs_too_many_years("2 years of experience", "junior")


def test_search_drops_us_jobs_heavy_experience_and_duplicates(monkeypatch):
    def provider(query, where, limit):
        return [
            store.new_job(id="good", title="Junior Python Developer", company="Acme s.r.o.", location="Prague", description=ENGLISH_AD),
            store.new_job(id="dup", title="Junior Python Developer (m/f)", company="Acme", location="Praha", description=ENGLISH_AD + " More details."),
            store.new_job(id="us", title="Machine Operator Nights", company="Mars", location="Fremont, NE", description=ENGLISH_AD),
            store.new_job(id="old-hand", title="Security Engineer, Cloud", company="Vercel", location="Anywhere in the World",
                          description=ENGLISH_AD + " Requires 8+ years of platform security experience."),
        ]

    monkeypatch.setattr(agent2_search.job_sources, "sources_for", lambda source, max_age_days=0, country="": [job_sources.Board("one", provider)])
    found = agent2_search.search(["python"], where="Prague")
    assert [j["id"] for j in found] == ["dup"]            # of the two copies, the fuller description wins


def test_duplicate_leads_keep_the_copy_with_a_letter_and_never_touch_applications():
    jobs = [store.new_job(id="plain", title="IT Helpdesk Specialist", company="RÖDL", description="x" * 500),
            store.new_job(id="with-letter", title="IT Helpdesk Specialist", company="Rödl", status="letter_ready",
                          cover_letter_file="l.docx", match_score=70),
            store.new_job(id="applied", title="IT Helpdesk Specialist", company="RÖDL", status="waiting"),
            store.new_job(id="other-role", title="IT Administrator", company="RÖDL"),
            store.new_job(id="no-company-1", title="Forklift Operator", company=""),
            store.new_job(id="no-company-2", title="Forklift Operator", company="")]
    removed = agent2_search.prune_duplicate_leads(jobs)
    assert [j["id"] for j in removed] == ["plain"]
    assert [j["id"] for j in jobs] == ["with-letter", "applied", "other-role", "no-company-1", "no-company-2"]


def test_scoring_prompt_forbids_guessing_requirements():
    prompt = agent3_letters.SCORE_PROMPT.replace("{rules}", agent3_letters._SCORE_RULES)
    assert "Do not assume a requirement" in prompt and "English-speaking role" in prompt
    assert "do not invent requirements" in prompt


# ── full-time only, and internships as experience ───────────────────────────
@pytest.mark.parametrize("title, description, expected", [
    ("SAP iXp Intern - IT Data & Analytics (limited, part time)", "", True),
    ("Data Engineer", "Join us as a Data Engineer (part-time) on a flagship engagement.", True),
    ("Platform Engineer", "Hours: Part-time, 32 hours per week. Contract: fixed-term.", True),
    ("Junior Developer", "Práce na částečný úvazek.", True),
    ("Junior Developer", "Full-time or part-time, as you prefer.", False),
    ("Junior Developer", "A full-time role in our Prague office.", False),
    ("Junior Developer", "", False),
])
def test_part_time_detection(title, description, expected):
    assert filters.is_part_time(title, description) is expected


def test_search_hides_part_time_roles_unless_allowed(monkeypatch):
    def provider(query, where, limit):
        return [store.new_job(id="full", title="Junior Python Developer", company="Acme", location="Prague", description=ENGLISH_AD),
                store.new_job(id="part", title="Python Intern (part time)", company="Beta", location="Prague", description=ENGLISH_AD)]

    monkeypatch.setattr(agent2_search.job_sources, "sources_for", lambda source, max_age_days=0, country="": [job_sources.Board("one", provider)])
    assert [j["id"] for j in agent2_search.search(["python"], where="Prague")] == ["full"]
    assert [j["id"] for j in agent2_search.search(["python"], where="Prague", full_time_only=False)] == ["full", "part"]


def test_one_to_two_years_of_experience_is_not_filtered_out():
    for text in ("1-2 years of professional experience", "At least 2 years of experience", "2+ years experience"):
        assert not filters.needs_too_many_years(text, "junior"), text
    assert filters.needs_too_many_years("4+ years of experience", "junior")


def test_scoring_counts_internships_as_experience(isolate_data, monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: seen.update(prompt=prompt) or {"match_score": 10, "match_reason": "x"})
    profile = {"summary": "s", "years_experience": 1.7, "internships": ["ML Research Intern - Northwind Labs, Sep 2025 - Apr 2026 (8 months)"]}
    agent3_letters.process([store.new_job(id="1", title="Dev", company="A", location="Prague")], profile, threshold=60)
    assert "Internships, traineeships and practical training are work experience" in seen["prompt"]
    assert "up to 2 years" in seen["prompt"] and "ML Research Intern - Northwind Labs" in seen["prompt"]


def test_a_copy_without_a_company_name_is_a_duplicate_of_the_named_one():
    title = "Intern in the Cloud & Data Analytics Department"
    jobs = [store.new_job(id="jobscz", title=title, company="Porsche Engineering", match_score=65, cover_letter_file="l.docx",
                          status="letter_ready"),
            store.new_job(id="pracecz", title=title, company="", match_score=70),
            store.new_job(id="other", title="Forklift Operator", company=""),
            store.new_job(id="short", title="Intern", company=""),
            store.new_job(id="short2", title="Intern", company="Acme")]
    removed = agent2_search.prune_duplicate_leads(jobs)
    assert [j["id"] for j in removed] == ["pracecz"]
    assert [j["id"] for j in jobs] == ["jobscz", "other", "short", "short2"]


# ── words you choose to skip, with exceptions ───────────────────────────────
@pytest.mark.parametrize("title, word", [
    ("Data Analyst Intern - Technology Consulting", "intern"),
    ("SAP iXp Intern - IT End User Support Specialist", "intern"),
    ("Software Engineering Internship Opportunities", "internship"),
    ("Summer Interns 2027", "intern"),
    ("INTERN in the Cloud & Data Analytics Department", "intern"),
])
def test_titles_with_a_skip_word_are_skipped(title, word):
    assert filters.skipped_word(title, ["intern", "internship"]) == word


@pytest.mark.parametrize("title", ["Internal Tools Engineer", "International Sales Support", "Junior Python Developer", ""])
def test_similar_words_are_not_skipped(title):
    assert filters.skipped_word(title, ["intern", "internship"]) == ""


def test_exceptions_beat_skip_words_and_phrases_and_accents_work():
    assert filters.skipped_word("Graduate Program Intern", ["intern"], ["graduate program"]) == ""
    assert filters.skipped_word("Stáž - vývojář", ["staz"]) == "staz"                       # accents are ignored
    assert filters.skipped_word("Working Student (m/f/d)", ["working student"]) == "working student"
    assert filters.skipped_word("Student ambassador", ["working student"]) == ""
    assert filters.skipped_word("Anything", [], []) == "" and filters.skipped_word("Intern", None) == ""


def test_search_leaves_out_skipped_titles(monkeypatch):
    def provider(query, where, limit):
        return [store.new_job(id="dev", title="Junior Python Developer", company="Acme", location="Prague", description=ENGLISH_AD),
                store.new_job(id="intern", title="Data Analyst Intern", company="PwC", location="Prague", description=ENGLISH_AD),
                store.new_job(id="grad", title="Graduate Program Intern", company="SAP", location="Prague", description=ENGLISH_AD),
                store.new_job(id="internal", title="Internal Tools Engineer", company="Alma", location="Prague", description=ENGLISH_AD)]

    monkeypatch.setattr(agent2_search.job_sources, "sources_for", lambda source, max_age_days=0, country="": [job_sources.Board("one", provider)])
    assert [j["id"] for j in agent2_search.search(["x"], where="Prague", skip_words=["intern"])] == ["dev", "internal"]
    assert [j["id"] for j in agent2_search.search(["x"], where="Prague", skip_words=["intern"], keep_words=["graduate program"])] == ["dev", "grad", "internal"]
    assert len(agent2_search.search(["x"], where="Prague")) == 4


def test_roles_requiring_czech_are_only_dropped_with_english_only(monkeypatch):
    czech_role = ENGLISH_AD + " Fluent Czech is required for this role."
    monkeypatch.setattr(agent2_search.job_sources, "sources_for", lambda source, max_age_days=0, country="": [job_sources.Board("one", lambda q, w, n: [store.new_job(id="cz", title="IT Support Specialist", company="Acme", location="Prague", description=czech_role)])])
    assert agent2_search.search(["x"], where="Prague") == []                                      # English only (the default)
    assert [j["id"] for j in agent2_search.search(["x"], where="Prague", english_only=False)] == ["cz"]     # for someone who speaks Czech


# ── found by reading the code line by line ──────────────────────────────────
def test_a_wrong_number_in_env_does_not_stop_the_app(monkeypatch):
    from jobhelper import config
    for value, expected in (("abc", 50), ("", 50), ("  70 ", 70), ("999", 100), ("-5", 0), ("12.5", 50)):
        monkeypatch.setenv("JOBHELPER_THRESHOLD", value)
        assert config._int_env("JOBHELPER_THRESHOLD", 50, 0, 100) == expected, value
    monkeypatch.delenv("JOBHELPER_THRESHOLD")
    assert config._int_env("JOBHELPER_THRESHOLD", 50, 0, 100) == 50
    text = Path(config.__file__).read_text(encoding="utf-8")
    assert "int(os.getenv(" not in text                              # every number in .env goes through the tolerant reader


def test_two_writers_of_one_file_do_not_share_a_temporary_file(tmp_path):
    import threading

    from jobhelper import vault
    target, errors = tmp_path / "jobs.json", []

    def write(n):
        try:
            for _ in range(60):
                vault._write_atomic(target, (str(n) * 4000).encode())
        except Exception as e:  # noqa: BLE001 - any failure is what this test is about
            errors.append(e)
    threads = [threading.Thread(target=write, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    data = target.read_bytes()
    assert errors == [] and len(data) == 4000 and len(set(data)) == 1          # one writer's text, whole
    assert list(tmp_path.glob("*.tmp")) == []


def test_usage_is_written_whole(isolate_data, monkeypatch):
    from jobhelper import config, usage
    usage.record({"input_tokens": 5, "cost_usd": 0.5}, tag="t")
    before = config.USAGE_JSON.read_text(encoding="utf-8")

    def fail(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(usage.os, "replace", fail)
    with pytest.raises(OSError):
        usage.record({"input_tokens": 5}, tag="t")
    assert config.USAGE_JSON.read_text(encoding="utf-8") == before and usage._load()["totals"]["calls"] == 1


@pytest.mark.parametrize("weekday, hour, minute", [(8, 9, 0), (1, 24, 0), (1, 9, 60), (-1, 9, 0), ("Mon", 9, 0), (1, None, 0)])
def test_a_day_or_time_that_does_not_exist_is_refused(monkeypatch, weekday, hour, minute):
    from jobhelper import schedule
    monkeypatch.setattr(schedule, "available", lambda: True)
    monkeypatch.setattr(schedule.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nothing may be installed")))
    got = schedule.write_schedule(True, weekday, hour, minute)
    assert got["ok"] is False and ("day and time" in got["msg"] or "Choose a day" in got["msg"])


def test_claude_is_never_asked_with_the_paid_api_key_set(monkeypatch):
    from jobhelper import llm
    asked = []

    async def answer(prompt, system, model):
        asked.append(prompt)
        return "ok", {"model": model}
    monkeypatch.setattr(llm, "_ask_async", answer)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key")
    for call in (lambda: llm.ask("hello"), lambda: llm.ask("hello", force=True), lambda: llm.ask_json("{}")):
        with pytest.raises(llm.PaidApiRefused) as refused:
            call()
        assert "paid API" in str(refused.value) and "sk-test" not in str(refused.value)
    assert asked == []
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert llm.ask("hello") == "ok" and asked == ["hello"]


def test_the_command_line_refuses_the_paid_api_too(isolate_data, monkeypatch, capsys):
    import run
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setattr("sys.argv", ["run.py", "--where", "Prague"])
    assert run.main() == 2
    out = capsys.readouterr().out
    assert "paid API" in out and "sk-test" not in out


def test_only_web_links_and_plain_file_names_are_opened(isolate_data, monkeypatch):
    from jobhelper import config, ui_api
    opened = []
    monkeypatch.setattr(api_core.Desktop, "open", lambda self, target: opened.append(str(target)))
    config.ensure_dirs()
    (config.LETTERS_DIR / "L.docx").write_bytes(b"x")
    (config.DATA_DIR / "secret.docx").write_bytes(b"x")
    store.save_jobs([store.new_job(id="web", title="T", company="C", url="https://example.com/job"),
                     store.new_job(id="file", title="T", company="C", url="file:///etc/hosts"),
                     store.new_job(id="app", title="T", company="C", url="x-custom-scheme://run"),
                     store.new_job(id="none", title="T", company="C")])
    api = ui_api.Api()
    assert api.open_url("web")["ok"] is True and [api.open_url(i)["ok"] for i in ("file", "app", "none", "zzz")] == [False] * 4
    assert api.open_doc("letter", "L.docx")["ok"] is True
    assert api.open_doc("letter", "../secret.docx")["ok"] is False and api.open_doc("letter", str(config.DATA_DIR / "secret.docx"))["ok"] is False
    assert opened == ["https://example.com/job", str(config.LETTERS_DIR / "L.docx")]


def test_a_reply_that_is_not_an_object_does_not_end_the_scan(isolate_data, monkeypatch):
    from jobhelper import agent5_responses, email_client, llm
    mails = [{"msg_id": f"<{n}@x>", "date": "Mon, 5 Oct 2026 10:00:00 +0200", "sender": "hr@acme.com", "subject": "Your application", "body": "b",
              "was_html_only": False} for n in range(3)]
    answers = iter([["not", "an", "object"], "text", {"is_response": True, "stage": "interview", "company": "Acme"}])
    monkeypatch.setattr(email_client, "fetch_recent", lambda days=None: mails)
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: next(answers))
    stats = agent5_responses.process_inbox([store.new_job(id="a", title="Dev", company="Acme", status="waiting")])
    assert stats["new_responses"] == 1 and stats["invites"] == ["Acme"]


def test_a_company_known_only_from_an_unclear_email_becomes_a_real_application(isolate_data):
    from jobhelper import agent5_responses, db
    db.upsert_response({"msg_id": "<1@x>", "company": "Quiet Lake", "stage": "other", "received_date": "2026-10-01"})
    jobs = []
    assert agent5_responses.reconcile_jobs(jobs) == 1
    assert jobs[0]["status"] == "waiting" and jobs[0]["status"] in store.APPLICATION_STATUSES      # never a status that is in no list


def test_statuses_the_app_does_not_know_can_be_repaired(isolate_data):
    import status
    jobs = [store.new_job(id="a", title="T", company="A", status="applied", source="email"),
            store.new_job(id="b", title="T", company="B", status="weird"),
            store.new_job(id="c", title="T", company="C", status="interview")]
    fixed = status.repair_statuses(jobs)
    assert [j["id"] for j in fixed] == ["a", "b"] and [j["status"] for j in jobs] == ["waiting", "found", "interview"]
    assert 'Status was "applied"' in jobs[0]["notes"] and status.repair_statuses(jobs) == []


def test_the_note_the_app_writes_uses_an_en_dash():
    from jobhelper import agent3_letters
    job = store.new_job(id="a", title="T", company="C", match_score=55, match_tier="moderate")
    agent3_letters._flag_moderate(job)
    assert "Moderate match (55%) – review" in job["notes"] and "—" not in job["notes"]


def test_the_preparation_text_survives_locked_data(isolate_data, monkeypatch):
    from jobhelper import ui_api, vault

    def locked():
        raise vault.VaultError("locked")
    monkeypatch.setattr(store, "load_jobs", locked)
    api = ui_api.Api()
    assert api.prep_text("a") == "" and api.prep_parts("a") == {}


# ── two companies are one only when their names say so ──────────────────────
@pytest.mark.parametrize("a, b, same", [
    ("Accenture Czech Republic", "PwC Czech Republic", False),          # a country is not a name
    ("Good Data", "NTT DATA", False), ("Deutsche Bank", "Deutsche Börse", False), ("Global Payments Inc.", "KBC Global Services", False),
    ("FLAE ROBOTICS a.s.", "Brightline Robotics", False), ("ACTUM Digital", "NN Digital Hub", False), ("Acme", "", False), ("", "", False),
    ("CSOB", "ČSOB (KBC)", True), ("Valeo", "Valeo s.r.o.", True), ("TD SYNNEX", "TD SYNNEX Czech Republic", True),
    ("BRIGHTLINE", "Brightline Robotics", True), ("Aon", "Aon Central and Eastern Europe a.s.", True), ("Veeam", "Veeam Software", True),
    ("Data Systems", "Data Systems Europe", True),                      # only common words, but one name is the other plus more
    ("HP", "HP Inc.", True), ("NN", "NN Group", True),
])
def test_same_company(a, b, same):
    assert email_client.same_company(a, b) is same and email_client.same_company(b, a) is same


def test_applying_at_one_company_does_not_drop_the_same_role_at_another():
    applied = [store.new_job(id="a", title="Data Engineer", company="PwC Czech Republic", status="waiting"),
               store.new_job(id="b", title="Backend Developer", company="Good Data", status="rejected")]
    found = [store.new_job(id="n1", title="Data Engineer", company="Accenture Czech Republic"),     # another company: stays
             store.new_job(id="n2", title="Junior Data Engineer", company="PwC"),                   # the same company and role: dropped
             store.new_job(id="n3", title="Backend Developer", company="NTT DATA"),                 # shares only the word "data": stays
             store.new_job(id="n4", title="Backend Developer", company="GoodData s.r.o.")]          # another spelling of the same name: dropped
    dropped = []
    kept, n = agent2_search.drop_known_applications(found, applied, dropped=dropped)
    assert [j["id"] for j in kept] == ["n1", "n3"] and n == 2 and [d["job"]["id"] for d in dropped] == ["n2", "n4"]
    jobs = applied + [store.new_job(id=j["id"], title=j["title"], company=j["company"]) for j in found]
    removed = agent2_search.prune_applied_leads(jobs)
    assert [j["id"] for j in removed] == ["n2", "n4"] and {j["id"] for j in jobs} == {"a", "b", "n1", "n3"}


def test_a_reply_from_one_company_does_not_count_for_another(isolate_data):
    from jobhelper import agent5_responses, db
    db.upsert_response({"msg_id": "<1@x>", "company": "Accenture Czech Republic", "role": "Data Engineer", "stage": "interview",
                        "received_date": "2026-10-01"})
    jobs = [store.new_job(id="p", title="(existing application)", company="PwC Czech Republic", status="waiting", source="manual")]
    assert agent5_responses.backfill_roles(jobs) == 0 and jobs[0]["title"] == "(existing application)"     # not PwC's role
    assert agent5_responses.reconcile_jobs(jobs) == 1 and jobs[-1]["company"] == "Accenture Czech Republic"  # its own record
    agent5_responses.annotate_progress(jobs)
    assert jobs[0]["status"] == "waiting" and not jobs[0].get("stages_path")                                # PwC is still waiting
    assert email_client.best_job_for_company_role("Accenture Czech Republic", "Data Engineer", jobs[:1]) is None


# ── found by reading the code line by line (second part) ────────────────────
def test_every_search_reads_the_boards_afresh(monkeypatch):
    """Each source forgets what an earlier search read: the app can stay open for days."""
    from jobhelper import scrapers_ats
    scrapers_ats._cache[("greenhouse", "acme")] = [store.new_job(id="old", title="Dev", company="Acme")]
    forgot = []
    stub = job_sources.Board("stub", lambda q, where, n: [], forget=lambda: forgot.append("stub"))
    careers = job_sources.Board("careers", lambda q, where, n: [], forget=scrapers_ats.forget)
    monkeypatch.setattr(agent2_search.job_sources, "sources_for", lambda source, max_age_days=0, country="": [stub, careers])
    agent2_search.search(["dev"], where="Prague")
    assert forgot == ["stub"] and scrapers_ats._cache == {}          # what a search three days ago was told is not used again
    from jobhelper import scrapers_remote
    told = []
    for module, name in ((scrapers_remote, "forget_remoteok"), (scrapers_remote, "forget_wwr"), (scrapers_ats, "forget")):
        monkeypatch.setattr(module, name, lambda name=name: told.append(name))
    for source in job_sources.all_sources():                         # each board that remembers something forgets it
        source.reset()
    assert sorted(told) == ["forget", "forget_remoteok", "forget_wwr"]


def test_the_cv_you_chose_is_the_master_whatever_else_is_in_the_folder(isolate_data):
    from jobhelper import agent1_cv, ui_api
    config.ensure_dirs()
    (config.CV_DIR / "Anna_CV.docx").write_bytes(b"old")
    (config.CV_DIR / "Zed_CV.docx").write_bytes(b"new")
    assert agent1_cv.find_cv().name == "Anna_CV.docx"                # nothing chosen: the first by name, as before
    agent1_cv.remember_cv("Zed_CV.docx")
    assert agent1_cv.find_cv().name == "Zed_CV.docx"
    api = ui_api.Api()
    assert api.save_options({**api.options(), "threshold": 55})["ok"] is True
    assert agent1_cv.find_cv().name == "Zed_CV.docx"                 # saving Options does not forget it
    (config.CV_DIR / "Zed_CV.docx").unlink()
    assert agent1_cv.find_cv().name == "Anna_CV.docx"                # the chosen file is gone: back to what is there
    agent1_cv.remember_cv("../../somewhere/else.docx")
    assert agent1_cv.find_cv().name == "Anna_CV.docx" and config.ui_settings()["master_cv"] == "else.docx"


@pytest.mark.parametrize("change, words", [
    ({"threshold": 101}, "“threshold” must be a whole number from 0 to 100"), ({"threshold": "fifty"}, "whole number"),
    ({"per_query": 0}, "from 1 to 100"), ({"max_years": 2.5}, "whole number"), ({"keep_backups": True}, "whole number"),
    ({"skip_words": "intern"}, "must be a list of words"), ({"queries": ["x" * 101]}, "101 characters long; the most is 100"),
    ({"wanted_roles": [f"role {n}" for n in range(61)]}, "has 61 entries; the most is 60"),
    ({"about_experience": "x" * (config.MAX_EXPERIENCE_NOTES + 1)}, "Shorten it"), ({"where": ["Prague"]}, "must be text"),
    ({"full_time_only": "yes"}, "must be on or off"),
])
def test_options_that_cannot_be_used_are_refused_by_the_backend(isolate_data, change, words):
    from jobhelper import ui_api
    api = ui_api.Api()
    assert api.save_options({**api.options(), "threshold": 45})["ok"] is True
    got = api.save_options({**api.options(), **change})
    assert got["ok"] is False and words in got["msg"]
    assert api.options()["threshold"] == 45                           # nothing of the refused set was saved


def test_options_are_tidied_and_keep_what_the_window_does_not_send(isolate_data):
    from jobhelper import ui_api
    api = ui_api.Api()
    assert api.save_options({"threshold": 60.0, "skip_words": [" intern ", "", "intern", 7, "trainee"], "where": "  Prague "})["ok"] is True
    saved = config.ui_settings()
    assert saved["threshold"] == 60 and isinstance(saved["threshold"], int) and saved["skip_words"] == ["intern", "trainee"] and saved["where"] == "Prague"
    assert api.save_options({"max_years": 3})["ok"] is True
    assert config.ui_settings()["threshold"] == 60 and config.ui_settings()["max_years"] == 3
    assert api.save_options("not options")["ok"] is False and api.save_options(None)["ok"] is True


@pytest.mark.parametrize("address", ["", "   ", "not an address", "a@b", "two@@x.com", "a b@x.com", "x" * 250 + "@x.com"])
def test_an_address_that_is_not_one_is_refused_by_the_backend(isolate_data, monkeypatch, address):
    from jobhelper import qt_bridge
    saved = []
    monkeypatch.setattr(config, "set_imap", lambda *a, **k: saved.append(a))
    monkeypatch.setattr(config, "set_imap2", lambda *a, **k: saved.append(a))
    bridge = qt_bridge.Bridge()
    assert bridge._save_email_checked(1, address, "abcdabcdabcdabcd")["ok"] is False
    assert bridge._save_email_checked(2, address, "abcdabcdabcdabcd")["ok"] is False
    assert saved == []


def test_an_address_needs_a_password_the_first_time(isolate_data, monkeypatch):
    from jobhelper import qt_bridge
    monkeypatch.setattr(config, "IMAP_PASSWORD", "")
    monkeypatch.setattr(config, "IMAP_PASSWORD_2", "")
    saved = []
    monkeypatch.setattr(config, "set_imap", lambda *a, **k: saved.append(a))
    bridge = qt_bridge.Bridge()
    assert "Enter the password" in bridge._save_email_checked(1, "me@gmail.com", "  ")["msg"]
    assert "Enter the password" in bridge._save_email_checked(2, "two@gmail.com", "")["msg"]
    assert bridge._save_email_checked(1, "me@gmail.com", "abcdabcdabcdabcd")["ok"] is True and saved == [("me@gmail.com", "abcdabcdabcdabcd")]


# ── found by reading filters.py line by line (10 October 2026) ──────────────
@pytest.mark.parametrize("location, where, country, us", [
    ("Prague, NE", "Prague", "", True), ("Austin, TX", "Prague", "", True), ("Remote, USA", "Bangalore", "India", True),
    ("Bangalore, IN", "Bangalore", "India", False), ("Indianapolis, IN", "Prague", "", True), ("Toronto, CA", "Toronto", "", False),
    ("San Jose, CA", "Brno", "", True), ("Tel Aviv, IL", "Tel Aviv", "Israel", False), ("Jakarta, ID", "Jakarta", "", False),
    ("Chicago, IL, United States", "Tel Aviv", "Israel", True), ("Praha", "Prague", "", False),
    ("Rabat, MA", "Rabat", "", False), ("Boston, MA", "Prague", "", True)])
def test_a_state_code_is_not_the_united_states_for_someone_whose_country_has_that_code(location, where, country, us, monkeypatch):
    """IN is Indiana and India, CA is California and Canada, IL is Illinois and Israel. For someone searching in such a country
    every local posting written "City, XX" was filtered out as "Located in the United States"."""
    from jobhelper import config
    monkeypatch.setattr(config, "search_country", lambda: country)
    assert filters.is_us_location(location, where) is us
    assert filters.is_us_location("Bangalore, IN") is True, "without a search city the old, wide reading stays"


def test_the_run_notices_any_change_to_your_own_data_folder():
    """The session guard in conftest compares data/ before and after the run (sizes and times, never contents)."""
    from tests.conftest import data_changes
    before = {"jobs.json": (100, 1), "my_details.json": (50, 1)}
    assert data_changes(before, dict(before)) == []
    assert data_changes(before, {"jobs.json": (100, 2), "my_details.json": (50, 1), "new.json": (1, 1)}) == ["jobs.json", "new.json"]
    assert data_changes(before, {"jobs.json": (100, 1)}) == ["my_details.json"]
