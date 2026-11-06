from jobhelper import job_sources, agent2_search, store


def test_is_english_job_uses_description():
    en = store.new_job(id="a", title="Vývojář",  # Czech title...
                       description="We are hiring a backend developer to join our team.")
    # ...but English description wins
    assert agent2_search.is_english_job(en)


def test_is_english_job_falls_back_to_title():
    j = store.new_job(id="b", title="Senior Python Engineer", description="")
    assert agent2_search.is_english_job(j)


def test_czech_job_filtered():
    cz = store.new_job(id="c", title="Softwarový vývojář",
                       description="Nabízíme práci a požadujeme znalost jazyka.")
    assert not agent2_search.is_english_job(cz)


def test_the_czech_setting_asks_the_czech_boards_first():
    names = [s.name for s in job_sources.sources_for("czech")]
    # the Czech job boards + LinkedIn always lead; "careers" is appended only
    # when the user has configured company career centers (data/companies.json)
    assert names[:3] == ["jobs.cz", "prace.cz", "linkedin"]
    assert set(names) <= {"jobs.cz", "prace.cz", "linkedin", "careers"}


def test_the_linkedin_setting_asks_linkedin_only():
    names = [s.name for s in job_sources.sources_for("linkedin")]
    assert names == ["linkedin"]


def test_drop_known_applications_is_role_aware():
    existing = [
        store.new_job(id="x", company="ESET Research", title="Python Developer", status="rejected"),
        store.new_job(id="y", company="Siemens Mobility", title="QA Engineer", status="waiting"),
        store.new_job(id="z", company="OldLead Co", title="Ops", status="found"),  # a lead, not excluded
    ]
    new_jobs = [
        store.new_job(id="1", company="ESET s.r.o.", title="Junior Python Developer"),  # same role+company → drop
        store.new_job(id="2", company="ESET s.r.o.", title="Data Analyst"),             # SAME company, DIFFERENT role → keep
        store.new_job(id="3", company="Siemens", title="QA Engineer"),                  # same role+company → drop
        store.new_job(id="4", company="OldLead Co", title="Ops"),                       # only a lead → keep
        store.new_job(id="5", company="Fresh Startup", title="Engineer"),               # new → keep
    ]
    kept, dropped = agent2_search.drop_known_applications(new_jobs, existing)
    assert dropped == 2
    kept_pairs = {(j["company"], j["title"]) for j in kept}
    assert ("ESET s.r.o.", "Data Analyst") in kept_pairs      # different role at same company kept
    assert ("Fresh Startup", "Engineer") in kept_pairs
    assert ("ESET s.r.o.", "Junior Python Developer") not in kept_pairs


def test_role_key_ignores_seniority():
    assert agent2_search.role_key("Junior Python Developer") == agent2_search.role_key("Senior Python Developer")
    assert agent2_search.role_key("QA Tester") != agent2_search.role_key("Python Developer")


def test_prune_applied_leads():
    jobs = [
        store.new_job(id="app1", company="ESET", title="Python Developer", status="waiting"),
        store.new_job(id="lead1", company="ESET s.r.o.", title="Junior Python Developer", status="letter_ready"),  # same role+company as app1 → prune
        store.new_job(id="lead2", company="ESET", title="QA Tester", status="found"),   # diff role → keep
        store.new_job(id="lead3", company="Fresh Co", title="Backend", status="found"), # unrelated → keep
    ]
    removed = agent2_search.prune_applied_leads(jobs)
    ids = {j["id"] for j in jobs}
    assert "lead1" not in ids            # pruned
    assert {"app1", "lead2", "lead3"} <= ids
    assert [r["id"] for r in removed] == ["lead1"]


def test_is_recent():
    from datetime import date, timedelta
    recent = (date.today() - timedelta(days=3)).isoformat()
    old = (date.today() - timedelta(days=40)).isoformat()
    assert agent2_search._is_recent({"date_posted": recent}, 10)
    assert not agent2_search._is_recent({"date_posted": old}, 10)
    assert agent2_search._is_recent({"date_posted": ""}, 10)        # unknown → kept
    assert agent2_search._is_recent({"date_posted": "garbage"}, 10)  # unparseable → kept


def test_non_latin_ads_rejected():
    from jobhelper import language
    # realistic Japanese ad (mostly CJK, a few English tech terms like the real one)
    jp = ("【このポジションについて】フロントエンド・バックエンドの垣根を越えて、製造業の設計を変える"
          "プロダクトを開発していただきます。第二新卒〜キャリア初期の方を対象に、全領域を担えるエンジニア"
          "へ育っていただくことを想定したポジションです。3D / AI 開発にも携わります。")
    ru = "Мы ищем разработчика Python для нашей команды в Праге опыт работы с Django обязателен"
    assert language.detect(jp) == "Japanese"
    assert language.detect(ru) == "Russian"
    assert language.detect("We are looking for a Python developer with strong Django experience.") == ""


def test_relative_date_handles_years():
    from jobhelper import scrapers_intl
    import datetime
    d = scrapers_intl._relative_to_date("Reposted 2 years ago")
    assert d, "should parse 'years ago'"
    age = (datetime.date.today() - datetime.date.fromisoformat(d)).days
    assert age > 600   # ~2 years


def test_search_refuses_to_run_without_a_city():
    import pytest
    with pytest.raises(RuntimeError, match="No city to search in"):
        agent2_search.search(["python"])
    with pytest.raises(RuntimeError, match="No city"):
        agent2_search.search(["python"], where="  ")


def test_the_same_link_twice_is_one_posting():
    a = store.new_job(id="pracecz-111", title="Global HRIS Specialist", company="", url="https://www.prace.cz/nabidka/abc/", match_score=15)
    b = store.new_job(id="pracecz-999", title="Global HRIS Specialist", company="", url="https://www.prace.cz/nabidka/abc")
    c = store.new_job(id="other", title="Developer", company="Acme", url="https://example.com/1")
    applied = store.new_job(id="app", title="QA", company="Beta", url="https://example.com/2", status="waiting")
    again = store.new_job(id="lead", title="QA Engineer", company="Beta s.r.o.", url="https://example.com/2")
    blank1, blank2 = store.new_job(id="n1", title="One", company="X"), store.new_job(id="n2", title="Two", company="Y")
    jobs = [a, b, c, applied, again, blank1, blank2]
    removed = agent2_search.prune_duplicate_leads(jobs)
    assert sorted(j["id"] for j in removed) == ["lead", "pracecz-999"]            # the scored copy and the application stay
    assert [j["id"] for j in jobs] == ["pracecz-111", "other", "app", "n1", "n2"]  # postings without a link are left alone


# ── a city in another country: the Czech boards are not asked ───────────────
def test_the_czech_boards_are_only_for_places_in_czechia():
    abroad = [s.name for s in job_sources.sources_for("czech", country="germany")]
    assert "jobs.cz" not in abroad and "prace.cz" not in abroad and "linkedin" in abroad
    for here in ("czechia", ""):                       # '' = a place the app does not know: it may be a Czech town
        assert [s.name for s in job_sources.sources_for("czech", country=here)][:2] == ["jobs.cz", "prace.cz"]
    assert "jobs.cz" not in [s.name for s in job_sources.sources_for("all", country="poland")]
    assert job_sources.left_out("czech", "germany") == [(["jobs.cz", "prace.cz"], ("czechia",))]
    assert job_sources.left_out("czech", "czechia") == [] and job_sources.left_out("linkedin", "germany") == []


def _search_in(monkeypatch, where, country_option=""):
    from jobhelper import config, scrapers_ats, scrapers_cz, scrapers_intl
    asked = []
    monkeypatch.setattr(config, "search_country", lambda: country_option)
    monkeypatch.setattr(scrapers_cz, "jobs_cz", lambda q, w, n: asked.append("jobs.cz") or [])
    monkeypatch.setattr(scrapers_cz, "prace_cz", lambda q, w, n: asked.append("prace.cz") or [])
    monkeypatch.setattr(scrapers_intl, "linkedin", lambda q, w, n, max_age_days=0: asked.append("linkedin") or [])
    monkeypatch.setattr(scrapers_ats, "load_companies", lambda: [])
    agent2_search.search(["python developer"], where=where, source="czech")
    return asked


def test_a_search_in_berlin_with_the_czech_setting_never_asks_the_czech_boards(monkeypatch, capsys):
    assert _search_in(monkeypatch, "Berlin") == ["linkedin"]
    assert "jobs.cz and prace.cz: only for places in Czechia, so not used for Berlin" in capsys.readouterr().out


def test_a_search_in_brno_still_asks_them(monkeypatch, capsys):
    assert _search_in(monkeypatch, "Brno") == ["jobs.cz", "prace.cz", "linkedin"]
    assert "not used for" not in capsys.readouterr().out


def test_the_country_in_options_decides_for_a_town_the_app_does_not_know(monkeypatch):
    assert _search_in(monkeypatch, "Kladno") == ["jobs.cz", "prace.cz", "linkedin"]               # may be Czech
    assert _search_in(monkeypatch, "Kladno", country_option="Czechia") == ["jobs.cz", "prace.cz", "linkedin"]
    assert _search_in(monkeypatch, "Freiburg", country_option="Germany") == ["linkedin"]


# ── one rule each (code review, 18 October 2026) ───────────────────────────
def test_both_czech_boards_page_through_results_with_one_loop(monkeypatch):
    import requests
    from jobhelper import scrapers_cz
    pages = {1: ["a", "b"], 2: ["b", "c"], 3: ["c"]}            # page 3 brings nothing new: the loop stops there
    asked = []

    class Page:
        def __init__(self, n): self.text = str(n)

    def fake_get(url, params=None):
        asked.append((url, dict(params or {})))
        return Page(params.get("page", 1))
    monkeypatch.setattr(scrapers_cz, "_get", fake_get)
    monkeypatch.setattr(scrapers_cz.time, "sleep", lambda s: None)
    parse = lambda html, where, limit: [{"id": i} for i in pages[int(html)]]     # noqa: E731
    board = scrapers_cz.LmcBoard("https://board.example/{city}/", "q", parse)
    assert [j["id"] for j in board.search("python", "Praha", 10, with_description=False)] == ["a", "b", "c"]
    assert asked[0] == ("https://board.example/praha/", {"q": "python"}) and asked[1][1] == {"q": "python", "page": 2}
    assert [j["id"] for j in board.search("python", "Praha", 2, with_description=False)] == ["a", "b"]      # the limit
    # a later page that fails keeps what the earlier pages gave; a first page that fails is the search's error
    monkeypatch.setattr(scrapers_cz, "_get", lambda url, params=None: Page(1) if "page" not in params else (_ for _ in ()).throw(requests.ConnectionError()))
    assert [j["id"] for j in board.search("python", "Praha", 10, with_description=False)] == ["a", "b"]
    monkeypatch.setattr(scrapers_cz, "_get", lambda url, params=None: (_ for _ in ()).throw(requests.ConnectionError()))
    import pytest
    with pytest.raises(requests.ConnectionError):
        board.search("python", "Praha", 10, with_description=False)
    assert scrapers_cz.JOBS_CZ._field == "q[]" and scrapers_cz.PRACE_CZ._field == "q"


def test_a_linkedin_posting_is_named_by_one_rule():
    from jobhelper import scrapers_intl
    assert scrapers_intl.posting_number({"id": "linkedin-4479884427"}) == "4479884427"
    assert scrapers_intl.posting_number({"id": "x", "url": "https://cz.linkedin.com/jobs/view/dev-at-acme-4468142745"}) == "4468142745"
    assert scrapers_intl.posting_number({"id": "jobscz-2001470061", "url": "https://www.jobs.cz/rpd/2001470061/"}) == ""
    assert scrapers_intl.read_posting({"id": "jobscz-1"}) == ("", False, "")
    assert not hasattr(scrapers_intl, "_CLOSED_MARKERS") and not hasattr(scrapers_intl, "_fetch_description")


def test_a_role_you_applied_for_is_one_rule_for_the_search_and_the_list():
    applied = agent2_search.AppliedRoles([store.new_job(id="a", title="Junior Python Developer", company="Acme s.r.o.", status="waiting"),
                                          store.new_job(id="n", title="QA Engineer", company="Beta", status="not_interested")],
                                         store.APPLICATION_STATUSES)
    assert applied.covers({"title": "Python Developer (m/f)", "company": "ACME"})        # same role, same company
    assert not applied.covers({"title": "Data Analyst", "company": "Acme"})              # another role there: kept
    assert not applied.covers({"title": "QA Engineer", "company": "Beta"})               # only the statuses asked for
    assert not applied.covers({"title": "Junior Python Developer", "company": ""})
    assert not hasattr(agent2_search, "drop_known_companies")


def test_a_closed_posting_has_one_reason_wherever_it_is_found(monkeypatch):
    found = [store.new_job(id="c", title="Developer", company="Acme", location="Prague", url="https://example.com/c",
                           description="We are hiring a developer. This job is no longer accepting applications.")]
    monkeypatch.setattr(agent2_search.job_sources, "sources_for",
                        lambda source, max_age_days=0, country="": [job_sources.Board("fake", lambda q, w, n: [dict(j) for j in found])])
    monkeypatch.setattr(agent2_search.config, "ui_settings", lambda: {})
    dropped = []
    agent2_search.search(["developer"], where="Prague", dropped=dropped)
    assert [d["reason"] for d in dropped] == [agent2_search.CLOSED_REASON]


def test_the_level_words_are_one_list_for_options_and_the_search():
    from jobhelper import filters
    assert not hasattr(filters, "_SENIOR_RE")
    assert filters.level_word("Sr. Python Developer", "junior") == "sr"
    assert filters.level_word("Engineering Managers", "junior") == "manager"
    assert filters.level_word("Head of Data", "junior") == "head of"
    assert filters.level_word("Junior Project Manager", "junior") == ""           # the title says its level
    assert filters.level_word("Senior Developer", "senior") == ""                   # a senior candidate keeps them
    assert filters.level_word("Vedoucí týmu", "junior") == "vedoucí"


def test_the_search_filters_are_one_object_with_its_rules_in_order(isolate_data):
    """agent2_search.SearchFilters: the rules a search uses follow its settings, and each drop is noted once."""
    from jobhelper import agent2_search, filters
    place = filters.Placement("Prague", "")
    plain = agent2_search.SearchFilters(place, "junior", english_only=False, full_time_only=False)
    assert [s.group for s in plain.sifts()] == ["closed", "other country", "other country", "too many years", "level"]
    every = agent2_search.SearchFilters(place, "junior", skip_words=["intern"], max_age_days=7)
    assert [s.group for s in every.sifts()][-4:] == ["part-time", "level", agent2_search.LANGUAGE_GROUP, "too old"]
    jobs = [{"id": "a", "title": "Python Developer", "company": "Kestrel", "location": "Prague", "description": "We build tools.", "source": "linkedin"},
            {"id": "b", "title": "Python Intern", "company": "Kestrel", "location": "Prague", "description": "We build tools.", "source": "linkedin"},
            {"id": "c", "title": "Senior Python Developer", "company": "Orbis", "location": "Prague", "description": "We build tools.", "source": "linkedin"}]
    dropped: list = []
    kept = every.apply(jobs, dropped)
    assert [j["id"] for j in kept] == ["a"]
    assert [(d["job"]["id"], d["group"]) for d in dropped] == [("b", "skip word"), ("c", "level")]


def test_the_country_of_a_search_is_one_rule():
    """Options' Country when the app knows it, else the city's: the sources, the place checks and the assistant ask Placement."""
    from jobhelper import filters
    assert filters.Placement("Prague", "").home == "czechia"
    assert filters.Placement("Prague", "Germany").home == "germany"
    assert filters.Placement("Prague", "Atlantis").home == "czechia"        # a Country the app does not know: the city's
    assert filters.Placement("Nowhere", "").home == ""


class _Source(job_sources.JobSource):
    def __init__(self, name, answer, failures=()):
        super().__init__(name, "boards")
        self._answer, self._failures = answer, list(failures)

    def find(self, query, where, per_query):
        if isinstance(self._answer, Exception):
            raise self._answer
        return [store.new_job(id=f"{self.name}-{query}", title="Data Analyst", company="Fabrikam", url="https://x.example/1")]

    def failures(self):
        return self._failures


def test_a_search_that_reaches_no_source_is_not_nothing_found(capsys):
    """#76: with the network down every board failed, and the search said it found nothing."""
    import pytest
    import requests
    down = [_Source("jobs.cz", requests.ConnectionError("down")), _Source("linkedin", requests.HTTPError("503"))]
    with pytest.raises(agent2_search.SourcesDown, match="jobs.cz, linkedin"):
        agent2_search._collect(down, ["analyst"], "Brno", 5)
    failed = []
    found = agent2_search._collect([down[0], _Source("careers", None, failures=["Contoso"])], ["analyst"], "Brno", 5,
                                   failed=failed)
    assert [j["id"] for j in found] == ["careers-analyst"] and failed == ["jobs.cz", "careers (Contoso)"]
    assert "Not read this time: jobs.cz, careers (Contoso)" in capsys.readouterr().out
    assert agent2_search.not_read_note(failed) == " Not read this time: jobs.cz, careers (Contoso)." and agent2_search.not_read_note([]) == ""
    failed = []
    with pytest.raises(agent2_search.SourcesDown):
        agent2_search._collect([_Source("careers", requests.ConnectionError("none"), failures=["Contoso", "Fabrikam"])],
                               ["analyst"], "Brno", 5, failed=failed)
    assert failed == ["careers"], "a source that failed as a whole is named once, not with each of its sites"


def test_a_source_that_was_not_read_keeps_its_filtered_out_postings(isolate_data, monkeypatch):
    """#76: a search that could not read a source saved a Filtered out list without that source's postings."""
    monkeypatch.setattr(agent2_search, "check_closed", lambda jobs, dropped=None: {"removed": 0, "marked": 0})
    monkeypatch.setattr(agent2_search, "reread_missing", lambda jobs, english_only=True, dropped=None: {"removed": 0})
    def row(id, source, company="Fabrikam"):
        return {"title": "Analyst", "company": company, "source": source, "group": "level", "reason": "senior",
                "job": store.new_job(id=id, title="Analyst", company=company, source=source)}
    agent2_search.save_dropped([row("old-1", "jobs.cz"), row("old-2", "linkedin"), row("old-3", "careers", "Contoso"),
                                row("old-4", "careers", "Northwind"), row("taken", "jobs.cz")])
    rows = [row("new-1", "prace.cz")]
    agent2_search.take_in([store.new_job(id="taken", title="Analyst")], [], dropped=list(rows), failed=["jobs.cz", "careers (Contoso)"])
    kept = [r["job"]["id"] for r in agent2_search.load_dropped()["rows"]]
    assert kept == ["new-1", "old-1", "old-3"], "only the sources not read keep their rows, never one now in the list"
    agent2_search.take_in([], [], dropped=list(rows), failed=["jobs.cz"])
    assert [r["job"]["id"] for r in agent2_search.load_dropped()["rows"]] == ["new-1", "old-1"], "kept once"
    agent2_search.take_in([], [], dropped=list(rows))
    assert [r["job"]["id"] for r in agent2_search.load_dropped()["rows"]] == ["new-1"], "a full search replaces the list"


def test_a_role_written_with_or_without_accents_is_the_same_role():
    """#76: "Projektový manažer" fell apart into "projektov" and "mana"."""
    assert agent2_search.role_key("Projektový manažer") == agent2_search.role_key("Projektovy Manazer") == {"projektovy", "manazer"}


def test_a_jobs_cz_word_in_an_address_is_not_jobs_cz(monkeypatch):
    """#76: any link with "jobs.cz" in it was read by the jobs.cz reader, without the check of the address."""
    from jobhelper import scrapers_cz, scrapers_page
    asked = []
    monkeypatch.setattr(scrapers_cz, "_fetch_detail", lambda url: asked.append(url) or ("text", ""))
    monkeypatch.setattr(scrapers_page, "posting_text", lambda url: "")
    read = agent2_search.real_refetch_description                              # conftest fakes refetch_description
    assert read({"url": "http://127.0.0.1/?next=jobs.cz", "source": "jooble"}) == ""
    assert asked == []
    assert read({"url": "https://www.jobs.cz/rpd/123/", "source": "jobs.cz"}) == "text"


def test_a_look_alike_link_is_never_taken_for_the_board(monkeypatch):
    from jobhelper import scrapers_cz, scrapers_intl, scrapers_page
    asked = []
    monkeypatch.setattr(scrapers_intl, "read_posting", lambda job: asked.append("linkedin") or ("", False, ""))
    monkeypatch.setattr(scrapers_cz, "_fetch_detail", lambda url: asked.append("cz") or ("", ""))
    monkeypatch.setattr(scrapers_page, "posting_text", lambda url: asked.append("page") or "")
    read = agent2_search.real_refetch_description
    for url in ("https://evil.example/?x=linkedin.com", "https://notjobs.cz/rpd/1", "https://jobs.cz.evil.example/1",
                "https://evil.example/jooble.org/1"):
        read({"url": url, "source": "jooble"})
    assert asked == ["page"] * 4
    read({"url": "https://cz.linkedin.com/jobs/view/1", "source": "x"})
    read({"url": "https://jooble.org/desc/1", "source": "x"})
    assert asked[4:] == ["linkedin"], "a real subdomain counts; jooble is never read twice"
