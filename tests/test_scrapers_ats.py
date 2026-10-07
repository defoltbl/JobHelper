"""Offline tests for the ATS career-site provider (no network)."""
from jobhelper import scrapers_ats


def test_loc_ok_accepts_prague_and_eu_remote():
    ok = scrapers_ats._loc_ok
    assert ok("Prague, Czechia", "Prague")
    assert ok("Remote, Europe", "Prague")
    assert ok("Remote", "Prague")
    assert ok("", "Prague")            # unknown location kept


def test_loc_ok_rejects_non_eu_remote_and_other_cities():
    ok = scrapers_ats._loc_ok
    assert not ok("Remote, US", "Prague")
    assert not ok("Remote, Canada", "Prague")
    assert not ok("Tokyo, Japan", "Prague")


def test_careers_filters_by_keyword_and_location(monkeypatch):
    sample = [
        scrapers_ats._norm("gh-x-1", "Junior Python Developer", "X", "Prague", "u", "", "2026-10-01"),
        scrapers_ats._norm("gh-x-2", "Senior Rust Engineer", "X", "Remote, US", "u", "", "2026-10-01"),
        scrapers_ats._norm("gh-x-3", "Data Analyst", "X", "Remote, Europe", "u", "", "2026-10-01"),
    ]
    monkeypatch.setattr(scrapers_ats, "load_companies", lambda: [{"name": "X", "ats": "greenhouse", "token": "x"}])
    monkeypatch.setattr(scrapers_ats, "_company_jobs", lambda *a: sample)

    res = scrapers_ats.careers("python", "Prague", 10)
    titles = [j["title"] for j in res]
    assert "Junior Python Developer" in titles          # keyword + Prague
    assert "Senior Rust Engineer" not in titles          # non-EU remote dropped
    assert "Data Analyst" not in titles                  # keyword mismatch
