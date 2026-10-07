from jobhelper import scrapers_cz


def test_parse_jobs_cz(jobs_cz_html):
    jobs = scrapers_cz.parse_jobs_cz(jobs_cz_html, "Praha")
    assert len(jobs) == 3
    for j in jobs:
        assert j["id"].startswith("jobscz-")
        assert j["title"]
        assert j["company"]
        assert "jobs.cz" in j["url"]
        assert j["source"] == "jobs.cz"
        assert j["location"]


def test_parse_prace_cz(prace_cz_html):
    jobs = scrapers_cz.parse_prace_cz(prace_cz_html, "Praha")
    assert len(jobs) == 3
    for j in jobs:
        assert j["id"].startswith("pracecz-")
        assert j["title"]
        assert j["url"].startswith("http")
        assert j["source"] == "prace.cz"


def test_parse_respects_limit(jobs_cz_html):
    assert len(scrapers_cz.parse_jobs_cz(jobs_cz_html, "Praha", limit=1)) == 1


def test_slug_maps_english_city():
    assert scrapers_cz._slug("Prague") == "praha"
    assert scrapers_cz._slug("Brno") == "brno"
    assert scrapers_cz._slug("České Budějovice") == "ceske-budejovice"
