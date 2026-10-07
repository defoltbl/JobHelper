"""Every posting the search filters out is kept with the reason, and shown in the app."""
from datetime import date, timedelta

import pytest

from jobhelper import agent2_search, config, store, ui_api, vault

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
    monkeypatch.setattr(agent2_search, "active_providers",
                        lambda source, max_age_days=0: [("fake", lambda q, where, n: [dict(j) for j in POSTINGS])])


def test_every_removed_posting_has_a_reason(boards):
    dropped = []
    kept = agent2_search.search(["python"], skip_words=["intern"], max_age_days=10, dropped=dropped)
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
    assert [j["id"] for j in agent2_search.search(["python"], skip_words=["intern"], max_age_days=10)] == ["ok"]


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
    monkeypatch.setattr(ui_api.Api, "_open", lambda self, target: opened.append(target))
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
    assert filters.is_too_senior_for(title, "junior") is senior


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
    assert filters.is_too_senior_for(title, "junior", words) is bool(word)


def test_years_limit_from_options():
    from jobhelper import filters
    text = "You have 5+ years of experience in backend development."
    assert filters.needs_too_many_years(text, "junior") is True                 # the CV's level decides
    assert filters.needs_too_many_years(text, "junior", 6) is False             # the user allows more
    assert filters.needs_too_many_years(text, "senior", 5) is True              # or sets a limit as a senior
    assert filters.needs_too_many_years(text, "junior", 0) is False             # 0 = never


def test_a_senior_user_keeps_senior_titles_and_long_experience(boards):
    dropped = []
    kept = agent2_search.search(["python"], skip_words=["intern"], max_age_days=10, dropped=dropped,
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
