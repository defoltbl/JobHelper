"""Pinned before the OOP rewrite of the place checks (18 October 2026): the same postings are kept and
dropped for the same reasons, and the run log says the same, in every kind of search."""
import pytest

from jobhelper import agent2_search, job_sources, store, ui_api

TEXT = "We are looking for a developer to join our team. You will work with Python and SQL, and we offer mentoring."
ROWS = [("prague", "jobs.cz", "Prague"), ("nebraska", "linkedin", "Prague, NE"), ("austin", "linkedin", "Austin, TX"),
        ("remote-us", "linkedin", "Remote, US"), ("remote", "linkedin", "Remote"), ("berlin-site", "careers", "Berlin, Germany"),
        ("careers-cz", "careers", "Brno, Czechia"), ("careers-remote-eu", "careers", "Remote - Europe"),
        ("korea", "careers", "Remote, South Korea"), ("usa-board", "remoteok", "USA Only"), ("eu-board", "weworkremotely", "Europe Only"),
        ("anywhere-board", "remoteok", "Worldwide"), ("apac", "weworkremotely", "Remote - APAC"), ("tel-aviv", "careers", "Tel Aviv, IL"),
        ("no-place", "careers", "")]


def _search(monkeypatch, capsys, where, **options):
    found = [store.new_job(id=i, title="Software Developer", company=f"Co {i}", location=loc, source=src, description=TEXT,
                           url=f"https://example.com/{i}") for i, src, loc in ROWS]
    monkeypatch.setattr(agent2_search.job_sources, "sources_for",
                        lambda source, max_age_days=0, country="": [job_sources.Board("fake", lambda q, w, n: [dict(j) for j in found])])
    api = ui_api.Api()
    assert api.save_options({**api.options(), "where": where, "country": "", "remote_where": "country", "remote_countries": [],
                             **options})["ok"]
    capsys.readouterr()
    dropped = []
    kept = sorted(j["id"] for j in agent2_search.search(["developer"], where=where, dropped=dropped))
    log = [line.strip() for line in capsys.readouterr().out.splitlines() if "filtered out" in line]
    return kept, {d["url"].rsplit("/", 1)[-1]: d["reason"] for d in dropped}, log


# What today's code does (generated once from it, then checked by eye), for four kinds of search.
PINNED = {
    'prague': (('Prague', {}),
        ['anywhere-board', 'careers-cz', 'careers-remote-eu', 'eu-board', 'no-place', 'prague', 'remote'],
        {'nebraska': 'Located in the United States (Prague, NE).', 'austin': 'Located in the United States (Austin, TX).', 'tel-aviv': 'Located in the United States (Tel Aviv, IL).', 'remote-us': 'A remote job for people in another part of the world (Remote, US).', 'berlin-site': 'A career-site job somewhere else (Berlin, Germany).', 'korea': 'A remote job for people in another part of the world (Remote, South Korea).', 'usa-board': 'A remote job for people in another part of the world (USA Only).', 'apac': 'A remote job for people in another part of the world (Remote - APAC).'},
        ['· filtered out 3 jobs located in the United States', '· filtered out 5 jobs in other countries, and remote jobs not open to yours']),
    'prague-world-us': (('Prague', {'remote_where': 'world', 'remote_countries': ['United States']}),
        ['anywhere-board', 'apac', 'careers-cz', 'careers-remote-eu', 'eu-board', 'no-place', 'prague', 'remote', 'remote-us', 'usa-board'],
        {'nebraska': 'Located in the United States (Prague, NE).', 'austin': 'Located in the United States (Austin, TX).', 'tel-aviv': 'Located in the United States (Tel Aviv, IL).', 'berlin-site': 'A career-site job somewhere else (Berlin, Germany).', 'korea': 'A remote job for people in another part of the world (Remote, South Korea).'},
        ['· filtered out 3 jobs located in the United States', '· filtered out 2 jobs in other countries, and remote jobs not open to yours']),
    'austin': (('Austin', {}),
        ['anywhere-board', 'austin', 'nebraska', 'no-place', 'prague', 'remote', 'remote-us', 'usa-board'],
        {'berlin-site': 'A career-site job somewhere else (Berlin, Germany).', 'careers-cz': 'A career-site job somewhere else (Brno, Czechia).', 'careers-remote-eu': 'A remote job for people in another part of the world (Remote - Europe).', 'korea': 'A remote job for people in another part of the world (Remote, South Korea).', 'eu-board': 'A remote job for people in another part of the world (Europe Only).', 'apac': 'A remote job for people in another part of the world (Remote - APAC).', 'tel-aviv': 'A career-site job somewhere else (Tel Aviv, IL).'},
        ['· filtered out 7 jobs in other countries, and remote jobs not open to yours']),
    'tel-aviv': (('Tel Aviv', {}),
        ['anywhere-board', 'no-place', 'prague', 'remote', 'tel-aviv'],
        {'nebraska': 'Located in the United States (Prague, NE).', 'austin': 'Located in the United States (Austin, TX).', 'remote-us': 'A remote job for people in another part of the world (Remote, US).', 'berlin-site': 'A career-site job somewhere else (Berlin, Germany).', 'careers-cz': 'A career-site job somewhere else (Brno, Czechia).', 'careers-remote-eu': 'A remote job for people in another part of the world (Remote - Europe).', 'korea': 'A remote job for people in another part of the world (Remote, South Korea).', 'usa-board': 'A remote job for people in another part of the world (USA Only).', 'eu-board': 'A remote job for people in another part of the world (Europe Only).', 'apac': 'A remote job for people in another part of the world (Remote - APAC).'},
        ['· filtered out 2 jobs located in the United States', '· filtered out 8 jobs in other countries, and remote jobs not open to yours']),
}


@pytest.mark.parametrize("case", sorted(PINNED))
def test_the_place_checks_keep_and_drop_as_before(case, isolate_data, monkeypatch, capsys):
    (where, options), kept, dropped, log = PINNED[case]
    got_kept, got_dropped, got_log = _search(monkeypatch, capsys, where, **options)
    assert (got_kept, got_dropped) == (kept, dropped)
    assert [line for line in got_log if "United States" in line or "other countries" in line] == log


def test_a_placement_answers_for_one_search_without_reading_options_again():
    from jobhelper import filters, places
    here = filters.Placement("Prague", "", places.RemoteReach("country", ["germany"]))
    assert here.fits("Brno") and not here.fits("Berlin, Germany") and here.fits("Remote, Germany")
    assert here.us_reason("Austin, TX") == "Located in the United States (Austin, TX)."
    assert here.us_reason("Remote, US") == ""                                   # remote jobs: the remote rule decides
    assert here.place_reason("USA Only", "remoteok", remote_board=True).startswith("A remote job for people")
    assert here.place_reason("Hamburg", "careers") == "A career-site job somewhere else (Hamburg)."
    assert here.place_reason("Hamburg", "jobs.cz") == ""                          # a board searched by place keeps its own
    assert filters.Placement("Austin").in_the_us and filters.Placement("Austin").us_reason("Austin, TX") == ""


def test_the_career_sites_read_options_once_per_search_not_per_posting(isolate_data, monkeypatch):
    from jobhelper import config, scrapers_ats
    jobs = [{"title": f"Python Developer {i}", "location": "Berlin, Germany" if i % 2 else "Prague", "id": f"j{i}"} for i in range(40)]
    monkeypatch.setattr(scrapers_ats, "load_companies", lambda: [{"name": "Acme", "ats": "greenhouse", "token": "acme"}])
    monkeypatch.setattr(scrapers_ats, "_company_jobs", lambda name, ats, token: [dict(j) for j in jobs])
    reads = []
    real = config.ui_settings
    monkeypatch.setattr(config, "ui_settings", lambda: reads.append(1) or real())
    found = scrapers_ats.careers("python developer", "Prague", 50)
    assert [j["location"] for j in found] == ["Prague"] * 20
    assert len(reads) <= 2                                                   # once for the search, not 40 times
