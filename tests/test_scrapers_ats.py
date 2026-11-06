"""Offline tests for the ATS career-site provider (no network)."""
import pytest

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


class _Answer:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_smartrecruiters_is_read_to_its_last_page(monkeypatch):
    """#76: only the first 100 postings of a company were read."""
    asked = []

    def get(url, params=None, **kw):
        asked.append(params["offset"])
        start = params["offset"]
        count = max(0, min(100, 237 - start))
        return _Answer({"totalFound": 237, "content": [{"id": f"p{start + i}", "name": "Data Analyst"} for i in range(count)]})
    monkeypatch.setattr(scrapers_ats.requests, "get", get)
    jobs = scrapers_ats._smartrecruiters("Fabrikam", "fabrikam")
    assert len(jobs) == 237 and asked == [0, 100, 200] and len({j["id"] for j in jobs}) == 237
    endless = lambda url, params=None, **kw: _Answer({"content": [{"id": f"q{params['offset'] + i}"} for i in range(100)]})
    monkeypatch.setattr(scrapers_ats.requests, "get", endless)
    assert len(scrapers_ats._smartrecruiters("Fabrikam", "fabrikam")) == scrapers_ats._SR_PAGE * scrapers_ats._SR_PAGES


def test_a_career_site_that_cannot_be_read_is_said_and_named(monkeypatch, capsys):
    """#76: a career site that did not answer gave no postings and no word."""
    scrapers_ats.forget()
    companies = [{"name": "Fabrikam", "ats": "greenhouse", "token": "fabrikam"},
                 {"name": "Contoso", "ats": "lever", "token": "contoso"}]
    monkeypatch.setattr(scrapers_ats, "load_companies", lambda: companies)
    monkeypatch.setattr(scrapers_ats, "_DELAY", 0)

    def down(name, token):
        raise scrapers_ats.requests.ConnectionError("down")
    good = lambda name, token: [scrapers_ats._norm("lv-1", "Python Developer", name, "Prague", "u", "", "")]
    monkeypatch.setattr(scrapers_ats, "_FETCHERS", {"greenhouse": down, "lever": good})
    assert [j["company"] for j in scrapers_ats.careers("python", "Prague", 10)] == ["Contoso"]
    assert "career site of Fabrikam could not be read" in capsys.readouterr().out
    assert scrapers_ats.failed() == ["Fabrikam"]
    scrapers_ats.forget()
    monkeypatch.setattr(scrapers_ats, "_FETCHERS", {"greenhouse": down, "lever": down})
    with pytest.raises(scrapers_ats.requests.ConnectionError):
        scrapers_ats.careers("python", "Prague", 10)                             # none answered: not "nothing fits"
    scrapers_ats.forget()
    assert scrapers_ats.failed() == []


def test_smartrecruiters_keeps_the_pages_it_read_and_says_where_it_stopped(monkeypatch, capsys):
    def get(url, params=None, **kw):
        if params["offset"] >= 200:
            raise scrapers_ats.requests.ConnectionError("down")
        return _Answer({"totalFound": 500, "content": [{"id": f"p{params['offset'] + i}"} for i in range(100)]})
    monkeypatch.setattr(scrapers_ats.requests, "get", get)
    assert len(scrapers_ats._smartrecruiters("Fabrikam", "fabrikam")) == 200
    assert "stopped answering after 200 postings" in capsys.readouterr().out
    monkeypatch.setattr(scrapers_ats.requests, "get", lambda url, params=None, **kw: (_ for _ in ()).throw(scrapers_ats.requests.ConnectionError("down")))
    with pytest.raises(scrapers_ats.requests.ConnectionError):
        scrapers_ats._smartrecruiters("Fabrikam", "fabrikam")                    # nothing read: the site failed
    endless = lambda url, params=None, **kw: _Answer({"content": [{"id": f"q{params['offset'] + i}"} for i in range(100)]})
    monkeypatch.setattr(scrapers_ats.requests, "get", endless)
    scrapers_ats._smartrecruiters("Fabrikam", "fabrikam")
    assert "lists more than 2000 postings" in capsys.readouterr().out


def test_a_career_site_read_in_part_is_named_as_not_read(monkeypatch):
    scrapers_ats.forget()

    def get(url, params=None, **kw):
        if params["offset"] >= 100:
            raise scrapers_ats.requests.ConnectionError("down")
        return _Answer({"totalFound": 300, "content": [{"id": f"p{i}"} for i in range(100)]})
    monkeypatch.setattr(scrapers_ats.requests, "get", get)
    assert len(scrapers_ats._smartrecruiters("Fabrikam", "fabrikam")) == 100
    assert scrapers_ats.failed() == ["Fabrikam"], "so its Filtered out rows are kept and the end of the search names it"
    monkeypatch.setattr(scrapers_ats.requests, "get", lambda url, params=None, **kw: _Answer(["not", "postings"]))
    with pytest.raises(ValueError):
        scrapers_ats._smartrecruiters("Fabrikam", "fabrikam")
    scrapers_ats.forget()
