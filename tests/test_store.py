from jobhelper import store


def test_new_job_defaults():
    j = store.new_job(id="x-1", title="Dev", company="Acme")
    assert j["id"] == "x-1"
    assert j["status"] == "found"
    assert j["match_score"] is None
    assert j["date_found"]  # today, defaulted
    # every column key Agent 4 expects is present
    for key in ("location", "url", "salary", "description", "cover_letter_file", "notes"):
        assert key in j


def test_upsert_dedupes_by_id():
    jobs = [store.new_job(id="a", title="A")]
    added, skipped = store.upsert(jobs, [store.new_job(id="a", title="A dup"),
                                         store.new_job(id="b", title="B")])
    assert added == 1
    assert skipped == 1
    assert {j["id"] for j in jobs} == {"a", "b"}


def test_find():
    jobs = [store.new_job(id="a"), store.new_job(id="b")]
    assert store.find(jobs, "b")["id"] == "b"
    assert store.find(jobs, "zzz") is None


def test_slugify():
    assert store.slugify("Acme s.r.o.") == "Acme-sro"
    assert store.slugify("Python Developer (Senior)") == "Python-Developer-Senior"
    assert store.slugify("") == "job"


def test_save_and_load_roundtrip(isolate_data):
    jobs = [store.new_job(id="a", title="Ž vývojář")]  # unicode survives
    store.save_jobs(jobs)
    loaded = store.load_jobs()
    assert loaded[0]["title"] == "Ž vývojář"


def test_statuses_contains_lifecycle():
    for s in ("found", "letter_ready", "waiting", "interview", "offer", "rejected"):
        assert s in store.STATUSES
    assert store.LEAD_STATUSES == {"found", "letter_ready"}
    assert "waiting" in store.APPLICATION_STATUSES
