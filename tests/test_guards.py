"""Rules the app must never break: the user's own letters stay untouched, closed
postings leave the list, emails link to the right company, progress is reported."""
import pytest

from jobhelper import agent2_search, agent3_letters, config, email_client, filters, llm, store

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


def test_prune_closed_leads_keeps_applications():
    closed = "No longer accepting applications"
    jobs = [store.new_job(id="lead-closed", description=closed),
            store.new_job(id="lead-open", description="Join us"),
            store.new_job(id="applied", description=closed, status="waiting")]
    removed = agent2_search.prune_closed_leads(jobs)
    assert [j["id"] for j in removed] == ["lead-closed"]
    assert [j["id"] for j in jobs] == ["lead-open", "applied"]


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

    monkeypatch.setattr(agent2_search, "active_providers", lambda source, max_age_days=0: [("one", provider), ("two", provider)])
    seen = []
    found = agent2_search.search(["a", "b", "c"], progress=lambda done, total: seen.append((done, total)))
    assert seen == [(i, 6) for i in range(6)]
    assert {j["id"] for j in found} == {"p-a", "p-b", "p-c"}


def test_search_without_progress_callback_still_works(monkeypatch):
    monkeypatch.setattr(agent2_search, "active_providers", lambda source, max_age_days=0: [("one", lambda q, w, n: [])])
    assert agent2_search.search(["a"]) == []


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

    monkeypatch.setattr(agent2_search, "active_providers", lambda source, max_age_days=0: [("one", provider)])
    found = agent2_search.search(["python"])
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
    prompt = agent3_letters.SCORE_PROMPT
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

    monkeypatch.setattr(agent2_search, "active_providers", lambda source, max_age_days=0: [("one", provider)])
    assert [j["id"] for j in agent2_search.search(["python"])] == ["full"]
    assert [j["id"] for j in agent2_search.search(["python"], full_time_only=False)] == ["full", "part"]


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

    monkeypatch.setattr(agent2_search, "active_providers", lambda source, max_age_days=0: [("one", provider)])
    assert [j["id"] for j in agent2_search.search(["x"], skip_words=["intern"])] == ["dev", "internal"]
    assert [j["id"] for j in agent2_search.search(["x"], skip_words=["intern"], keep_words=["graduate program"])] == ["dev", "grad", "internal"]
    assert len(agent2_search.search(["x"])) == 4


def test_roles_requiring_czech_are_only_dropped_with_english_only(monkeypatch):
    czech_role = ENGLISH_AD + " Fluent Czech is required for this role."
    monkeypatch.setattr(agent2_search, "active_providers", lambda source, max_age_days=0: [
        ("one", lambda q, w, n: [store.new_job(id="cz", title="IT Support Specialist", company="Acme", location="Prague", description=czech_role)])])
    assert agent2_search.search(["x"]) == []                                      # English only (the default)
    assert [j["id"] for j in agent2_search.search(["x"], english_only=False)] == ["cz"]     # for someone who speaks Czech
