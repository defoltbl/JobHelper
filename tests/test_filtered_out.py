"""Every posting the search filters out is kept with the reason, and shown in the app."""
from datetime import date, timedelta

import pytest

from jobhelper import job_sources, api_core, agent2_search, config, store, ui_api, vault

EN = "We are hiring a developer to join our team and build backend services in Python. "


def _job(id, title, **kw):
    kw.setdefault("description", EN)
    kw.setdefault("company", f"Co {id}")
    kw.setdefault("location", "Prague")
    return store.new_job(id=id, title=title, url=f"https://example.com/{id}", **kw)


POSTINGS = [
    _job("ok", "Junior Python Developer"),
    _job("closed", "Junior Tester", description=EN + "This job is no longer accepting applications."),
    _job("us", "Junior Developer", location="Austin, TX"),
    _job("years", "Backend Developer", description=EN + "You have 6+ years of experience with Java."),
    _job("intern", "Software Engineering Intern"),
    _job("part", "Junior Developer (part-time)"),
    _job("dup", "Junior Python Developer", company="Co ok"),
    _job("senior", "Senior Python Engineer"),
    _job("czech", "Junior Developer", description=EN + "Fluent Czech is required for this role."),
    _job("cs", "Vývojář", description="Nabízíme práci a požadujeme znalost jazyka. Hledáme vývojáře do našeho týmu."),
    _job("old", "Junior QA Engineer", date_posted=(date.today() - timedelta(days=40)).isoformat()),
]


@pytest.fixture
def boards(monkeypatch):
    monkeypatch.setattr(agent2_search.job_sources, "sources_for",
                        lambda source, max_age_days=0, country="": [job_sources.Board("fake", lambda q, where, n: [dict(j) for j in POSTINGS])])


def test_every_removed_posting_has_a_reason(boards):
    dropped = []
    kept = agent2_search.search(["python"], where="Prague", skip_words=["intern"], max_age_days=10, dropped=dropped)
    assert [j["id"] for j in kept] == ["ok"]
    assert len(dropped) == len(POSTINGS) - 1                                   # nothing disappears without a note
    by = {d["url"].rsplit("/", 1)[-1]: d for d in dropped}
    assert by["closed"]["group"] == "closed"
    assert by["us"]["reason"] == "Located in the United States (Austin, TX)." and by["us"]["group"] == "other country"
    assert by["years"]["reason"] == "Asks for 6+ years of experience."
    assert by["intern"]["reason"] == 'The title has a word you skip ("intern").'
    assert by["part"]["group"] == "part-time"
    assert by["dup"]["group"] == "duplicate"
    assert by["senior"]["reason"] == 'The title has a level you skip ("senior").' and by["senior"]["group"] == "level"
    assert by["czech"]["reason"] == "Requires Czech at a working level."
    assert by["cs"]["reason"] == "The ad is written in Czech."
    assert by["old"]["reason"] == "Posted more than 10 days ago."
    assert all(d["title"] and d["reason"].endswith(".") for d in dropped)


def test_search_works_without_asking_for_reasons(boards):
    assert [j["id"] for j in agent2_search.search(["python"], where="Prague", skip_words=["intern"], max_age_days=10)] == ["ok"]


def test_a_role_you_already_applied_for_is_noted_too():
    applied = [store.new_job(id="x", company="Acme", title="Python Developer", status="rejected")]
    dropped = []
    kept, n = agent2_search.drop_known_applications([_job("1", "Junior Python Developer", company="Acme s.r.o."),
                                                     _job("2", "Data Analyst", company="Acme")], applied, dropped=dropped)
    assert [j["id"] for j in kept] == ["2"] and n == 1
    assert dropped[0]["group"] == "already applied" and "already applied" in dropped[0]["reason"]


def test_the_list_is_saved_encrypted_and_replaced_by_the_next_search(isolate_data):
    assert agent2_search.load_dropped() == {"when": "", "total": 0, "rows": []}
    rows = [{"title": f"T{i}", "company": "Secret Co", "url": "", "group": "duplicate", "reason": "R."}
            for i in range(agent2_search.MAX_DROPPED + 5)]
    agent2_search.save_dropped(rows)
    got = agent2_search.load_dropped()
    assert got["total"] == len(rows) and len(got["rows"]) == agent2_search.MAX_DROPPED and got["when"]
    raw = (isolate_data / "filtered_out.json").read_bytes()
    assert raw.startswith(b"JHENC1\n") and b"Secret Co" not in raw
    assert isolate_data / "filtered_out.json" in vault.data_files()
    agent2_search.save_dropped([])
    assert agent2_search.load_dropped()["rows"] == []
    (isolate_data / "filtered_out.json").write_text("{broken")
    assert agent2_search.load_dropped()["total"] == 0


def test_api_lists_them_and_opens_only_a_saved_web_link(isolate_data, monkeypatch):
    config.ensure_dirs()
    opened = []
    monkeypatch.setattr(api_core.Desktop, "open", lambda self, target: opened.append(target))
    agent2_search.save_dropped([{"title": "A", "company": "C", "url": "https://example.com/a", "group": "closed", "reason": "R."},
                                {"title": "B", "company": "C", "url": "file:///etc/passwd", "group": "closed", "reason": "R."},
                                {"title": "D", "company": "C", "url": "", "group": "closed", "reason": "R."}])
    api = ui_api.Api()
    assert [r["title"] for r in api.filtered_out()["rows"]] == ["A", "B", "D"]
    assert api.open_filtered(0) == {"ok": True} and opened == ["https://example.com/a"]
    for index in (1, 2, 3, -1):
        assert api.open_filtered(index) == {"ok": False}
    assert opened == ["https://example.com/a"]


# ── a wrong rule the list exposed on real postings ──────────────────────────
@pytest.mark.parametrize("title, senior", [
    ("Backend Engineer, Create: Repository Management", False),      # a field, not a level
    ("Data & Reporting Analyst, Enterprise Risk Management", False),
    ("Management Consulting Analyst (Junior+)", False),
    ("Junior Project Manager", False),                               # the title itself says junior
    ("Graduate Sales Manager", False),
    ("Product Manager", True), ("Engineering Manager", True), ("Senior Python Engineer", True),
    ("Head of Data", True), ("Staff Engineer", True), ("Team Lead", True),
])
def test_management_as_a_field_is_not_a_senior_title(title, senior):
    from jobhelper import filters
    assert bool(filters.level_word(title, "junior")) is senior


# ── level words and the years limit come from Options ───────────────────────
def test_defaults_follow_the_level_in_the_cv():
    from jobhelper import filters
    assert "senior" in filters.default_level_words("junior") and "manager" in filters.default_level_words("mid")
    assert filters.default_level_words("senior") == [] == filters.default_level_words("lead")
    assert (filters.default_max_years("junior"), filters.default_max_years("mid"), filters.default_max_years("senior")) == (4, 7, 0)
    assert "management" not in filters.LEVEL_WORDS


@pytest.mark.parametrize("title, words, word", [
    ("Senior Python Engineer", ["senior", "lead"], "senior"),
    ("Tech Lead", ["senior", "lead"], "lead"), ("Team Leads", ["lead"], "lead"),
    ("Leading Edge Developer", ["lead"], ""),                         # a whole word only
    ("Senior Python Engineer", [], ""),                               # a senior user emptied the list
    ("Principal Engineer", ["senior"], ""),                           # only the words in the list count
    ("Junior Project Manager", ["manager"], ""),                      # the title itself says junior
    ("Vedoucí týmu", ["vedoucí"], "vedoucí"),
])
def test_level_words_from_options_decide(title, words, word):
    from jobhelper import filters
    assert filters.level_word(title, "junior", words) == word
    assert bool(filters.level_word(title, "junior", words)) is bool(word)


def test_years_limit_from_options():
    from jobhelper import filters
    text = "You have 5+ years of experience in backend development."
    assert filters.needs_too_many_years(text, "junior") is True                 # the CV's level decides
    assert filters.needs_too_many_years(text, "junior", 6) is False             # the user allows more
    assert filters.needs_too_many_years(text, "senior", 5) is True              # or sets a limit as a senior
    assert filters.needs_too_many_years(text, "junior", 0) is False             # 0 = never


def test_a_senior_user_keeps_senior_titles_and_long_experience(boards):
    dropped = []
    kept = agent2_search.search(["python"], where="Prague", skip_words=["intern"], max_age_days=10, dropped=dropped,
                                level_words=[], max_years=0)
    assert {"ok", "senior", "years"} <= {j["id"] for j in kept}
    assert not [d for d in dropped if d["group"] in ("level", "too many years")]


def test_prefilter_level_rule_can_be_switched_off():
    from jobhelper import prefilter
    job = store.new_job(id="d", title="Director of Engineering", company="Acme", description=EN)
    assert "senior level" in prefilter.reason_to_skip(job, {"Python"})
    assert prefilter.reason_to_skip(job, {"Python"}, check_level=False) == ""


def test_options_start_from_the_cv_level_and_keep_what_you_save(isolate_data, monkeypatch):
    from jobhelper import agent1_cv
    config.ensure_dirs()
    monkeypatch.setattr(agent1_cv, "load_profile", lambda current_only=False: {"seniority": "senior"})
    api = ui_api.Api()
    assert api.options()["level_words"] == [] and api.options()["max_years"] == 0
    monkeypatch.setattr(agent1_cv, "load_profile", lambda current_only=False: {"seniority": "junior"})
    o = api.options()
    assert "senior" in o["level_words"] and o["max_years"] == 4
    api.save_options({**o, "level_words": ["senior"], "max_years": 6})
    assert (api.options()["level_words"], api.options()["max_years"]) == (["senior"], 6)


# ── bringing a filtered-out posting back ────────────────────────────────────
@pytest.fixture
def filtered(isolate_data, boards, monkeypatch):
    from jobhelper import agent4_tracker
    config.ensure_dirs()
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)
    dropped = []
    agent2_search.search(["python"], where="Prague", skip_words=["intern"], max_age_days=10, dropped=dropped)
    agent2_search.save_dropped(dropped)
    return ui_api.Api()


def _index(api, group):
    return next(i for i, r in enumerate(api.filtered_out()["rows"]) if r["group"] == group)


def test_a_posting_can_be_brought_back_and_will_be_scored(filtered):
    api = filtered
    rows = api.filtered_out()["rows"]
    assert all("job" not in r for r in rows)                                    # the window does not get whole postings
    assert {r["group"]: r["can_return"] for r in rows}["duplicate"] is False
    i = _index(api, "level")
    when = agent2_search.load_dropped()["when"]
    assert api.bring_back(i) == {"ok": True, "title": "Senior Python Engineer"}
    job = store.find(store.load_jobs(), "senior")
    assert job["status"] == "found" and job["prefilter_override"] is True and job["desired_monthly_czk"]
    assert "level you skip" in job["brought_back"] and job["url"] == "https://example.com/senior"
    left = agent2_search.load_dropped()
    assert "Senior Python Engineer" not in [r["title"] for r in left["rows"]] and left["when"] == when
    assert len(left["rows"]) == len(rows) - 1


def test_bring_back_refuses_what_cannot_last_or_is_already_there(filtered):
    api = filtered
    assert "same reason" in api.bring_back(_index(api, "duplicate"))["msg"]
    assert "same reason" in api.bring_back(_index(api, "closed"))["msg"]
    assert api.bring_back(99)["ok"] is False and api.bring_back(-1)["ok"] is False
    i = _index(api, "part-time")
    store.save_jobs([store.new_job(id="part", title="Junior Developer (part-time)", company="Co part")])
    assert "already in your lists" in api.bring_back(i)["msg"]
    agent2_search.save_dropped([{"title": "Old", "company": "C", "url": "", "group": "level", "reason": "R."}])
    assert api.filtered_out()["rows"][0]["can_return"] is False               # saved before postings were kept whole
    assert "without its details" in api.bring_back(0)["msg"]


def test_a_posting_brought_back_during_a_run_reaches_that_run(filtered):
    api = filtered
    api.live = []
    assert api.bring_back(_index(api, "too many years"))["ok"] is True
    assert [j["id"] for j in api.live] == ["years"]


# ── found by the first real search after these changes ──────────────────────
def test_an_error_never_shows_the_api_key():
    text = ("503 Server Error: Service Temporarily Unavailable for url: "
            "https://api.adzuna.com/v1/api/jobs/pl/search/1?app_id=abc123&app_key=SECRETKEY99&what=python")
    safe = agent2_search.safe_error(Exception(text))
    assert safe == "503 Server Error: Service Temporarily Unavailable for url: https://api.adzuna.com/v1/api/jobs/pl/search/1"
    assert "SECRETKEY99" not in safe and "app_id" not in safe
    assert agent2_search.safe_error("no address here") == "no address here"


def test_a_failing_board_prints_no_key(monkeypatch, capsys):
    import requests

    def failing(q, where, n):
        raise requests.HTTPError("503 for url: https://api.example.com/search?app_key=SECRETKEY99&q=x")
    monkeypatch.setattr(agent2_search.job_sources, "sources_for", lambda source, max_age_days=0, country="": [job_sources.Board("example", failing)])
    assert agent2_search.search(["python"], where="Prague") == []
    out = capsys.readouterr().out
    assert "example error for 'python'" in out and "SECRETKEY99" not in out and "app_key" not in out


@pytest.mark.parametrize("description, company", [
    ("Nabídky práce Detail nabídky UX Designer Plat neuveden Odpovědět Firma: Thales DIS Czech Republic s.r.o. ( zaměstnavatel ) Místo pracoviště: Praha",
     "Thales DIS Czech Republic s.r.o"),
    ("About the role\nCompany: Acme Robotics\nLocation: Prague", "Acme Robotics"),
    ("We are a company: fast, friendly and growing.", ""),            # a sentence, not a label
    ("Firma: 12345 (", ""), ("", ""),
])
def test_company_is_taken_from_the_posting_text_when_the_listing_has_none(description, company):
    job = store.new_job(id="x", title="UX Designer", company="", description=description)
    agent2_search.fill_company(job)
    assert job["company"] == company
    named = store.new_job(id="y", title="T", company="Real Name", description="Firma: Other ( zaměstnavatel )")
    agent2_search.fill_company(named)
    assert named["company"] == "Real Name"                            # a name the listing gave is never replaced


# ── a second try at reading a posting that came back empty ──────────────────
def test_postings_without_text_are_read_once_more(monkeypatch):
    texts = {"en": EN * 6, "cz": "Hledáme vývojáře do našeho týmu. Nabízíme zajímavou práci a přátelský kolektiv. " * 5, "still": ""}
    monkeypatch.setattr(agent2_search, "refetch_description", lambda job: texts.get(job["id"], "must not be asked"))
    jobs = [store.new_job(id="en", title="Python Developer", company="A", url="https://x/en"),
            store.new_job(id="cz", title="IT Support Administrator", company="B", url="https://x/cz"),
            store.new_job(id="still", title="Tester", company="C", url="https://x/still"),
            store.new_job(id="has", title="QA", company="D", url="https://x/has", description="Already read. " * 40),
            store.new_job(id="nolink", title="QA", company="E"),
            store.new_job(id="app", title="QA", company="F", url="https://x/app", status="waiting")]
    dropped = []
    stats = agent2_search.reread_missing(jobs, english_only=True, dropped=dropped, pause=0)
    assert stats == {"read": 2, "removed": 1}
    by = {j["id"]: j for j in jobs}
    assert by["en"]["description"].startswith("We are hiring") and "cz" not in by            # the Czech ad leaves the list …
    assert dropped[0]["title"] == "IT Support Administrator" and dropped[0]["reason"] == "The ad is written in Czech."   # … with its reason
    assert by["still"]["description"] == "" and by["has"]["description"] == "Already read. " * 40 and by["app"]["description"] == ""


def test_a_czech_ad_stays_when_you_read_czech_or_already_have_its_documents(monkeypatch):
    czech = "Hledáme vývojáře do našeho týmu. Nabízíme zajímavou práci a přátelský kolektiv. " * 5
    monkeypatch.setattr(agent2_search, "refetch_description", lambda job: czech)
    jobs = [store.new_job(id="a", title="Vývojář", company="A", url="https://x/a")]
    assert agent2_search.reread_missing(jobs, english_only=False, pause=0) == {"read": 1, "removed": 0} and len(jobs) == 1
    kept = [store.new_job(id="b", title="Tester", company="B", url="https://x/b", cover_letter_file="L.docx")]
    assert agent2_search.reread_missing(kept, english_only=True, pause=0)["removed"] == 0 and len(kept) == 1


def test_refetch_knows_where_each_board_keeps_the_text(monkeypatch):
    from jobhelper import scrapers_cz, scrapers_intl
    monkeypatch.undo()                                    # the real function, with the network replaced below
    asked = []
    monkeypatch.setattr(scrapers_intl, "_fetch_detail", lambda job_id: asked.append(("linkedin", job_id)) or ("LinkedIn text", False, ""))
    monkeypatch.setattr(scrapers_cz, "_fetch_detail", lambda url: asked.append(("cz", url)) or ("Czech board text", ""))
    assert agent2_search.refetch_description({"id": "linkedin-4455367720", "source": "linkedin", "url": "https://cz.linkedin.com/jobs/view/x-4455367720"}) == "LinkedIn text"
    assert agent2_search.refetch_description({"id": "jobscz-1", "source": "jobs.cz", "url": "https://www.jobs.cz/rpd/1/"}) == "Czech board text"
    from jobhelper import scrapers_page
    monkeypatch.setattr(scrapers_page, "posting_text", lambda url: asked.append(("page", url)) or "The page's own copy")
    assert agent2_search.refetch_description({"id": "x", "source": "remoteok", "url": "https://remoteok.com/1"}) == "The page's own copy"
    assert agent2_search.refetch_description({"id": "c", "source": "careers", "url": "https://careers.example.com/jobs/7"}) == "The page's own copy"
    assert agent2_search.refetch_description({"id": "j", "source": "jooble/x", "url": "https://jooble.org/desc/123"}) == ""      # it turns programs away: not asked
    assert agent2_search.refetch_description({"id": "n", "source": "manual", "url": ""}) == ""
    assert asked == [("linkedin", "4455367720"), ("cz", "https://www.jobs.cz/rpd/1/"), ("page", "https://remoteok.com/1"), ("page", "https://careers.example.com/jobs/7")]

    def broken(job_id):
        raise OSError("no network")
    monkeypatch.setattr(scrapers_intl, "_fetch_detail", broken)
    assert agent2_search.refetch_description({"id": "linkedin-1234567", "source": "linkedin", "url": ""}) == ""


def test_a_title_only_score_is_not_kept_once_the_text_arrives(monkeypatch):
    from jobhelper import agent3_letters
    monkeypatch.setattr(agent2_search, "refetch_description", lambda job: EN * 6)
    held = store.new_job(id="held", title="Python Developer", company="A", url="https://x/h", match_score=40)
    held["hold"], held["doc_attempts"] = agent3_letters.NO_TEXT, 2
    other_hold = store.new_job(id="other", title="Python Developer", company="B", url="https://x/o", match_score=20)
    other_hold["hold"] = agent3_letters.NO_COMPANY
    with_docs = store.new_job(id="docs", title="Tester", company="C", url="https://x/d", match_score=55, cover_letter_file="L.docx")
    fresh = store.new_job(id="fresh", title="QA", company="D", url="https://x/f")
    jobs = [held, other_hold, with_docs, fresh]
    assert agent2_search.reread_missing(jobs, pause=0)["read"] == 4
    assert held["match_score"] is None and held["score_before"] == 40 and "hold" not in held and held["doc_attempts"] == 0
    assert other_hold["hold"] == agent3_letters.NO_COMPANY and other_hold["match_score"] is None    # another reason to hold stays
    assert with_docs["match_score"] == 55 and "score_before" not in with_docs                        # its documents rest on this score
    assert fresh["match_score"] is None and "score_before" not in fresh


def test_a_short_summary_gets_a_second_read_and_then_is_left_be(monkeypatch):
    from jobhelper import agent3_letters
    summary = "A short summary of the role, much less than the posting says."
    answers = {"grows": EN * 6, "same": summary, "less": "tiny", "empty": ""}
    monkeypatch.setattr(agent2_search, "refetch_description", lambda job: answers[job["id"]])
    jobs = [store.new_job(id=i, title="Python Developer", company=i.upper(), url="https://x/" + i, description=summary, match_score=45) for i in answers]
    jobs.append(store.new_job(id="long", title="Dev", company="L", url="https://x/long", description="x" * agent3_letters.SHORT_TEXT))
    assert agent2_search.reread_missing(jobs, pause=0) == {"read": 1, "removed": 0}
    by = {j["id"]: j for j in jobs}
    assert by["grows"]["description"] == (EN * 6).strip() and by["grows"]["match_score"] is None and by["grows"]["score_before"] == 45
    assert "text_tries" not in by["grows"] and "text_tries" not in by["long"]
    for name in ("same", "less", "empty"):
        assert by[name]["description"] == summary and by[name]["match_score"] == 45 and by[name]["text_tries"] == 1   # never replaced by less
    asked = []
    monkeypatch.setattr(agent2_search, "refetch_description", lambda job: asked.append(job["id"]) or "")
    for _ in range(agent2_search.REREAD_TRIES + 2):
        agent2_search.reread_missing(jobs, pause=0)
    assert sorted(asked) == sorted(["same", "less", "empty"] * (agent2_search.REREAD_TRIES - 1))             # then the board is left alone
    by["same"]["text_tries"] = "many"                                                                       # a damaged count starts again
    agent2_search.reread_missing(jobs, pause=0)
    assert by["same"]["text_tries"] == 1


# ── postings that stopped accepting applications after they were found ──────
def test_a_search_asks_the_pages_of_new_jobs_whether_they_are_still_open(monkeypatch):
    answers = {"gone": True, "docs": True, "open": False, "silent": None}
    asked = []
    monkeypatch.setattr(agent2_search, "posting_closed", lambda job: asked.append(job["id"]) or answers.get(job["id"]))
    jobs = [store.new_job(id="gone", title="Dev", company="A", url="https://www.linkedin.com/jobs/view/1"),
            store.new_job(id="docs", title="Dev", company="B", url="https://www.linkedin.com/jobs/view/2", status="letter_ready", cover_letter_file="L.docx"),
            store.new_job(id="open", title="Dev", company="C", url="https://www.linkedin.com/jobs/view/3"),
            store.new_job(id="silent", title="Dev", company="D", url="https://www.linkedin.com/jobs/view/4"),
            store.new_job(id="app", title="Dev", company="E", url="https://www.linkedin.com/jobs/view/5", status="waiting")]
    jobs[2]["closed"] = True                                         # was marked earlier and is open again
    dropped = []
    stats = agent2_search.check_closed(jobs, dropped=dropped, today="2026-10-09", pause=0)
    assert stats == {"asked": 3, "removed": 1, "marked": 1} and sorted(asked) == ["docs", "gone", "open", "silent"]   # never an application
    by = {j["id"]: j for j in jobs}
    assert "gone" not in by and dropped[0]["job"]["id"] == "gone" and dropped[0]["group"] == "closed"
    assert by["docs"]["closed"] is True and by["docs"]["cover_letter_file"] == "L.docx"          # what was written stays
    assert "closed" not in by["open"] and by["open"]["closed_checked"] == "2026-10-09"
    assert "closed_checked" not in by["silent"]                                                  # no answer: asked again next time

    asked.clear()
    agent2_search.check_closed(jobs, today="2026-10-10", pause=0)
    assert asked == ["silent"]                                       # the others were asked a day ago
    asked.clear()
    agent2_search.check_closed(jobs, today="2026-10-12", pause=0)    # three days on, everyone again; the marked one is not counted twice
    assert sorted(asked) == ["docs", "open", "silent"] and agent2_search.check_closed(jobs, today="2026-10-20", pause=0)["marked"] == 0


def test_only_so_many_pages_are_asked_per_search_longest_unchecked_first(monkeypatch):
    asked = []
    monkeypatch.setattr(agent2_search, "posting_closed", lambda job: asked.append(job["id"]) or False)
    jobs = [store.new_job(id=f"j{i:03}", title="Dev", company="A", url="https://www.linkedin.com/jobs/view/1") for i in range(agent2_search.CLOSED_PER_SEARCH + 5)]
    for j in jobs[:5]:
        j["closed_checked"] = "2026-09-01"                            # asked long ago; the rest never
    agent2_search.check_closed(jobs, today="2026-10-09", pause=0)
    assert len(asked) == agent2_search.CLOSED_PER_SEARCH and not set(asked) & {j["id"] for j in jobs[:5]}
    asked.clear()
    agent2_search.check_closed(jobs, today="2026-10-09", pause=0)
    assert sorted(asked) == [j["id"] for j in jobs[:5]]               # the next search does the others


def test_postings_that_cannot_be_asked_do_not_take_the_places_of_those_that_can(monkeypatch):
    """Found by reading the code: a posting from a board that cannot be asked was never marked as asked, so on every search
    such postings stood at the head of the line and used up the forty places. On real data 72 LinkedIn postings had never
    been asked whether they were still open."""
    asked = []
    monkeypatch.setattr(agent2_search, "posting_closed", lambda job: asked.append(job["id"]) or False)
    others = [store.new_job(id=f"jobscz-{i}", title="Dev", company="A", url=f"https://www.jobs.cz/rpd/{i}/") for i in range(60)]
    linked = [store.new_job(id=f"linkedin-{4000000 + i}", title="Dev", company="B", url="") for i in range(30)]
    jobs = others + linked
    stats = agent2_search.check_closed(jobs, today="2026-10-10", pause=0)
    assert sorted(asked) == sorted(j["id"] for j in linked) and stats["asked"] == 30, "every posting that can be asked was, and no other"
    assert all(agent2_search.can_ask_if_closed(j) for j in linked) and not any(agent2_search.can_ask_if_closed(j) for j in others)
    assert agent2_search.can_ask_if_closed({"id": "x", "url": "https://www.linkedin.com/jobs/view/123456"}) and not agent2_search.can_ask_if_closed({})


def test_one_board_that_cannot_be_read_does_not_end_the_search(monkeypatch, capsys):
    """A board that changed its pages makes its reader stumble over something no network error covers. The search used to end there."""
    from jobhelper import scrapers_ats, scrapers_cz, scrapers_intl
    good = store.new_job(id="jobscz-1", title="Junior Python Developer", company="Northwind", location="Prague", url="https://www.jobs.cz/rpd/1/",
                         description="We build services in Python. " * 20)
    monkeypatch.setattr(scrapers_cz, "jobs_cz", lambda q, where, n: [dict(good)])
    monkeypatch.setattr(scrapers_cz, "prace_cz", lambda q, where, n: (_ for _ in ()).throw(AttributeError("'NoneType' object has no attribute 'find_all'")))
    monkeypatch.setattr(scrapers_intl, "linkedin", lambda q, where, n, max_age_days=0: [{"title": "no id at all"}])
    monkeypatch.setattr(scrapers_ats, "load_companies", lambda: [])
    found = agent2_search.search(["python"], where="Prague")
    assert [j["id"] for j in found] == ["jobscz-1"], "what the other boards gave is kept"
    out = capsys.readouterr().out
    assert "prace.cz could not be read for 'python' (AttributeError)" in out and "linkedin could not be read" in out


def test_a_damaged_list_of_filtered_postings_reads_as_empty(isolate_data):
    from jobhelper import config, vault
    config.ensure_dirs()
    path = config.DATA_DIR / "filtered_out.json"
    for text, rows, total in (("[1, 2]", 0, 0), ('{"rows": "none", "total": "many"}', 0, 0), ('{"rows": [{"title": "A"}, 7], "total": "x"}', 1, 1),
                              ('{"rows": [{"title": "A"}], "total": 900, "when": 5}', 1, 900), ('{"rows": [{"title": "A"}], "total": true}', 1, 1)):
        vault.write_text(path, text)
        got = agent2_search.load_dropped()
        assert (len(got["rows"]), got["total"]) == (rows, total) and isinstance(got["when"], str), text


def test_only_boards_that_give_a_clear_answer_are_asked(monkeypatch):
    from jobhelper import scrapers_intl
    monkeypatch.undo()
    replies = {"111111": ("Text of the posting", False, ""), "222222": ("", True, ""), "333333": ("", False, "")}
    monkeypatch.setattr(scrapers_intl, "_fetch_detail", lambda number: replies[number])
    assert agent2_search.posting_closed({"id": "linkedin-111111", "url": ""}) is False
    assert agent2_search.posting_closed({"id": "x", "url": "https://www.linkedin.com/jobs/view/dev-222222"}) is True
    assert agent2_search.posting_closed({"id": "linkedin-333333", "url": ""}) is None           # an empty answer (too many requests) is not "closed"
    assert agent2_search.posting_closed({"id": "jobscz-1", "url": "https://www.jobs.cz/rpd/1/"}) is None
    assert agent2_search.posting_closed({"id": "linkedin-abc", "url": ""}) is None

    def down(number):
        raise OSError("no network")
    monkeypatch.setattr(scrapers_intl, "_fetch_detail", down)
    assert agent2_search.posting_closed({"id": "linkedin-111111", "url": ""}) is None


def test_english_only_says_which_language_it_is(monkeypatch):
    from jobhelper import agent2_search as a2
    reason = a2.language_reason
    job = lambda description, title="Developer": {"title": title, "description": description}     # noqa: E731
    assert reason(job("Wir suchen einen Entwickler für unser Team. Ihre Aufgaben sind die Entwicklung und der Betrieb unserer "
                      "Dienste. Sie bringen Erfahrung mit Python mit und wir bieten flexible Arbeitszeiten.")) == "The ad is written in German."
    assert reason(job("We build tools for planners. You will need fluent German to talk to our customers every day.")) \
        == "Requires German at a working level."
    assert reason(job("Excellent communication skills in Czech or Slovak are required.")) == "Requires Czech or Slovak at a working level."
    assert reason(job("Znalost češtiny je nutná.", "Tester")) == "Requires Czech at a working level."
    # English asked for, another language only as a plus, or no language named: nothing against it
    assert reason(job("Fluent English is required. German is a plus. You will work with Python.")) == ""
    assert reason(job("You will work with Python and SQL in a team of five.")) == ""
    assert reason(job("")) == ""
    assert a2.LANGUAGE_GROUP == "other language"


def test_a_search_leaves_out_an_ad_in_any_other_language(monkeypatch):
    german = ("Wir suchen einen Softwareentwickler für unser Team. Ihre Aufgaben sind die Entwicklung und der Betrieb unserer "
              "Dienste. Sie bringen Erfahrung mit Python mit und wir bieten flexible Arbeitszeiten sowie ein gutes Gehalt.")
    found = [_job("de", "Softwareentwickler", description=german), _job("en", "Software Developer"),
             _job("fr", "Support Agent", description=EN + "You must speak fluent French with our customers every day.")]
    monkeypatch.setattr(agent2_search.job_sources, "sources_for",
                        lambda source, max_age_days=0, country="": [job_sources.Board("fake", lambda q, where, n: [dict(j) for j in found])])
    dropped = []
    kept = agent2_search.search(["developer"], where="Prague", dropped=dropped)
    assert [j["id"] for j in kept] == ["en"]
    assert {d["reason"] for d in dropped} == {"The ad is written in German.", "Requires French at a working level."}
    assert {d["group"] for d in dropped} == {"other language"}
    dropped = []
    kept = agent2_search.search(["developer"], where="Prague", dropped=dropped, english_only=False)      # someone who works in other languages too
    assert sorted(j["id"] for j in kept) == ["de", "en", "fr"] and dropped == []


def test_a_role_on_two_boards_is_not_lost_when_the_kept_copy_is_filtered_out(monkeypatch):
    # The longer copy would be kept as the duplicate's winner; it is in Czech, the other copy is in English.
    czech = ("Hledáme nového kolegu do našeho týmu. Budeš vyvíjet software pro naše klienty a pracovat s moderními "
             "technologiemi. Nabízíme práci v Praze, vzdělávání a dobrý kolektiv lidí, kteří tě rádi všechno naučí.") * 3
    found = [_job("cs", "Junior Software Engineer", company="Acme", description=czech),
             _job("en", "Junior Software Engineer", company="Acme"),
             _job("en-old", "Junior QA Engineer", company="Beta", description=EN * 3,
                  date_posted=(date.today() - timedelta(days=40)).isoformat()),
             _job("en-new", "Junior QA Engineer", company="Beta")]
    monkeypatch.setattr(agent2_search.job_sources, "sources_for",
                        lambda source, max_age_days=0, country="": [job_sources.Board("fake", lambda q, where, n: [dict(j) for j in found])])
    dropped = []
    kept = agent2_search.search(["engineer"], where="Prague", max_age_days=10, dropped=dropped)
    assert sorted(j["id"] for j in kept) == ["en", "en-new"]
    by = {d["url"].rsplit("/", 1)[-1]: d["reason"] for d in dropped}
    assert by == {"cs": "The ad is written in Czech.", "en-old": "Posted more than 10 days ago."}
    # Two copies that both pass the filters: one is kept, the other is noted as the duplicate.
    dropped = []
    kept = agent2_search.search(["engineer"], where="Prague", max_age_days=10, dropped=dropped, english_only=False)
    assert sorted(j["id"] for j in kept) == ["cs", "en-new"]
    assert {d["url"].rsplit("/", 1)[-1]: d["group"] for d in dropped} == {"en": "duplicate", "en-old": "too old"}
