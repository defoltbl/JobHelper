from jobhelper import agent2_search, store


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


def test_active_providers_czech_default():
    names = [n for n, _ in agent2_search.active_providers("czech")]
    # the Czech job boards + LinkedIn always lead; "careers" is appended only
    # when the user has configured company career centers (data/companies.json)
    assert names[:3] == ["jobs.cz", "prace.cz", "linkedin"]
    assert set(names) <= {"jobs.cz", "prace.cz", "linkedin", "careers"}


def test_active_providers_linkedin_only():
    names = [n for n, _ in agent2_search.active_providers("linkedin")]
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
    assert not language.is_english(jp)
    assert not language.is_english(ru)
    assert language.is_english("We are looking for a Python developer with strong Django experience.")


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
