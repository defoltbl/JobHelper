"""Where "here" is for a search: any city, its country, and remote work that fits."""
import pytest

from jobhelper import job_sources, agent2_search, config, filters, places, scrapers_ats, store, ui_api


@pytest.mark.parametrize("city, country", [
    ("Prague", "czechia"), ("Praha", "czechia"), ("Brno", "czechia"), ("Kraków", "poland"), ("München", "germany"),
    ("Zürich", "switzerland"), ("Vienna", "austria"), ("Wien", "austria"), ("Lisbon", "portugal"), ("Toronto", "canada"),
    ("Germany", "germany"), ("Deutschland", "germany"), ("Czech Republic", "czechia"), ("Smallville", ""), ("", "")])
def test_the_country_of_a_city(city, country):
    assert places.country_of(city) == country


@pytest.mark.parametrize("location, where, country, fits", [
    # the same checks as before for a search in Prague
    ("", "Prague", "", True), ("Prague, Czechia", "Prague", "", True), ("Brno", "Prague", "", True), ("Brno, CZ", "Prague", "", True),
    ("Remote", "Prague", "", True), ("EMEA", "Prague", "", True), ("Remote - Europe", "Prague", "", True), ("Worldwide", "Prague", "", True),
    ("Berlin, Germany", "Prague", "", False), ("Austin, TX", "Prague", "", False), ("Remote, US", "Prague", "", False),
    ("Remote (APAC)", "Prague", "", False), ("Remote - India", "Prague", "", False), ("Bangalore", "Prague", "", False),
    # and the same for anyone else: it used to keep Prague jobs and drop the local ones
    ("Berlin, Germany", "Berlin", "", True), ("Hamburg", "Berlin", "", True), ("München", "Berlin", "", True), ("Prague", "Berlin", "", False),
    ("Remote, Germany", "Berlin", "", True), ("Remote - Europe", "Berlin", "", True), ("Remote, US", "Berlin", "", False),
    ("Remote, Canada", "Toronto", "", True), ("Remote - Europe", "Toronto", "", False), ("Vancouver", "Toronto", "", True),
    ("Remote, US", "Austin", "United States", True), ("New York", "Austin", "United States", True),
    # every country is known now, with its larger cities
    ("Tbilisi, Georgia", "Tbilisi", "", True), ("Batumi, Georgia", "Tbilisi", "", True), ("Prague", "Tbilisi", "", False),
    ("EMEA", "Tbilisi", "", True), ("Seoul, South Korea", "Busan", "", True), ("Remote, South Korea", "Prague", "", False),
    # a place the app has no table for (a typing error, an invented name): the city, and the country as typed in Options
    ("Strelsau, Ruritania", "Zenda", "", False), ("Strelsau, Ruritania", "Zenda", "Ruritania", True),
    ("Prague", "Zenda", "Ruritania", False), ("Remote", "Zenda", "Ruritania", True), ("EMEA", "Zenda", "", True),
    # the country in Options wins over the city's own
    ("Vienna", "Bratislava", "Austria", True), ("Kosice", "Bratislava", "Austria", False),
])
def test_what_counts_as_here(location, where, country, fits):
    assert places.fits(location, where, country) is fits


def test_the_filters_use_the_country_from_options(isolate_data, monkeypatch):
    assert config.search_country() == ""
    assert filters.location_fits("Brno", "Prague") is True and filters.location_fits("Hamburg", "Prague") is False
    assert scrapers_ats._loc_ok("Hamburg", "Berlin") is True and scrapers_ats._loc_ok("Brno", "Berlin") is False
    api = ui_api.Api()
    assert api.save_options({**api.options(), "where": "Tbilisi", "country": "Georgia"})["ok"] is True
    assert config.search_country() == "Georgia"
    assert filters.location_fits("Batumi, Georgia", "Tbilisi") is True and filters.location_fits("Brno", "Tbilisi") is False
    assert filters.location_fits("Brno", "Prague", country="") is True            # a caller may still say which country


@pytest.mark.parametrize("country", ["12345", "Germany 2", "DE;", "<b>", "Germany, Austria", "  -  "])
def test_a_country_that_is_not_a_name_is_refused(isolate_data, country):
    api = ui_api.Api()
    result = api.save_options({**api.options(), "where": "Berlin", "country": country})
    assert result["ok"] is False and "country" in result["msg"] and config.search_country() == ""


@pytest.mark.parametrize("country", ["", "Germany", "United Kingdom", "Côte d'Ivoire", "Bosnia-Herzegovina", "St. Lucia", "  Austria  "])
def test_a_country_name_is_accepted(isolate_data, country):
    api = ui_api.Api()
    assert api.save_options({**api.options(), "where": "Berlin", "country": country})["ok"] is True
    assert config.search_country() == country.strip()
    assert api.save_options({**api.options(), "country": "x" * 61})["ok"] is False


def test_what_the_app_takes_a_city_s_country_to_be():
    api = ui_api.Api()
    assert api.country_of("Prague") == "Czechia" and api.country_of("London") == "United Kingdom"
    assert api.country_of("Smallville") == "" and api.country_of("") == "" and api.country_of(None) == ""


def test_a_search_in_the_united_states_keeps_american_postings(isolate_data, monkeypatch):
    text = "We are looking for a developer to join our team. You will work with Python and SQL, and we offer mentoring."
    found = [store.new_job(id="tx", title="Software Developer", company="Acme", location="Austin, TX", description=text, url="https://example.com/tx")]
    monkeypatch.setattr(agent2_search.job_sources, "sources_for", lambda source, max_age_days=0, country="": [job_sources.Board("fake", lambda q, where, n: [dict(j) for j in found])])
    dropped = []
    assert agent2_search.search(["developer"], where="Prague", dropped=dropped) == [] and "United States" in dropped[0]["reason"]
    dropped = []
    assert [j["id"] for j in agent2_search.search(["developer"], where="Austin", dropped=dropped)] == ["tx"] and dropped == []


def test_a_country_s_name_is_matched_as_a_whole_word():
    """"Indianapolis, Indiana" was read as India, so a search in the United States lost its own postings."""
    assert places.named_countries("Indianapolis, Indiana") == set()
    assert places.fits("Indianapolis, Indiana, United States", "Chicago") is True
    assert places.country_of("Indiana") == "" and places.country_of("India") == "india"
    assert places.named_countries("Francesville") == set() and places.named_countries("Paris, France") == {"france"}
    # the stems of adjectives still match their endings
    assert places.country_of("Czech Republic") == "czechia" and places.country_of("Ceska republika") == "czechia"
    assert places.country_of("Slovensko") == "slovakia" and places.named_countries("Bratislava, Slovakia") == {"slovakia"}


# ── which remote jobs fit: your country and the ones you add, or anywhere ─────
@pytest.mark.parametrize("location, fits", [
    ("Remote", True), ("Remote, Czechia", True), ("Remote - Europe", True), ("Remote (EMEA)", True), ("Anywhere in the world", True),
    ("Remote, South Korea", False), ("Remote, Israel", False), ("Remote - APAC", False), ("Remote, US", False),
    ("Remote, Germany", False), ("Remote - LATAM", False), ("Remote, Papua New Guinea", False),
])
def test_in_my_country_keeps_remote_jobs_open_to_it(location, fits):
    assert places.fits(location, "Prague", "", places.RemoteReach("country")) is fits
    assert places.fits(location, "Prague") is fits                      # the same rule without a choice


def test_added_countries_and_their_regions_count_too():
    reach = places.RemoteReach("country", ["Germany", "south korea", "Atlantis", "germany"])
    assert reach.countries == ("germany", "south korea")                # unknown names and repeats are dropped
    assert places.fits("Remote, Germany", "Prague", "", reach) is True
    assert places.fits("Remote, South Korea", "Prague", "", reach) is True
    assert places.fits("Remote - APAC", "Prague", "", reach) is True     # South Korea is in APAC
    assert places.fits("Remote, Japan", "Prague", "", reach) is False
    assert places.fits("Berlin, Germany", "Prague", "", reach) is False  # an added country is for remote jobs only


def test_anywhere_in_the_world_keeps_jobs_for_any_region_but_never_for_one_other_country():
    reach = places.RemoteReach("world")
    for location in ("Remote", "Remote - APAC", "Remote - Americas", "Remote (EMEA)", "Remote, Czechia"):
        assert places.fits(location, "Prague", "", reach) is True, location
    # tied to a country you may not live or work in: skipped whatever the choice
    for location in ("Remote, South Korea", "Remote, US", "Remote - India", "Remote Ireland; Remote, France"):
        assert places.fits(location, "Prague", "", reach) is False, location
    assert places.fits("Seoul, South Korea", "Prague", "", reach) is False                # on site elsewhere
    added = places.RemoteReach("world", ["United States"])
    assert places.fits("Remote, US", "Prague", "", added) is True and places.fits("Remote, South Korea", "Prague", "", added) is False


def test_a_job_from_a_remote_board_is_remote_even_when_its_location_does_not_say_so():
    assert places.fits("USA Only", "Prague", "", remote=True) is False
    assert places.fits("Europe Only", "Prague", "", remote=True) is True
    assert places.fits("USA Only", "Prague", "", places.RemoteReach("world"), remote=True) is False
    assert places.fits("Americas Only", "Prague", "", places.RemoteReach("world"), remote=True) is True


@pytest.mark.parametrize("options, scope, countries", [
    ({}, "country", ()), ({"remote_where": "world"}, "world", ()), ({"remote_where": "moon"}, "country", ()),
    ({"remote_countries": ["Poland", "Narnia"]}, "country", ("poland",)), ({"remote_countries": "Poland"}, "country", ()),
])
def test_the_choice_is_read_from_options(options, scope, countries):
    reach = places.RemoteReach.from_options(options)
    assert (reach.scope, reach.countries) == (scope, countries)


def test_longer_names_and_lookalikes_are_not_read_as_another_country():
    assert places.named_countries("Port Moresby, Papua New Guinea") == {"papua new guinea"}
    assert places.named_countries("Juba, South Sudan") == {"south sudan"}
    assert places.named_countries("Kinshasa, Democratic Republic of the Congo") == {"dr congo"}
    assert places.named_countries("Albuquerque, New Mexico, United States") == {"united states"}
    assert places.named_countries("Atlanta, Georgia, United States") == {"united states"}
    assert places.named_countries("Tbilisi, Georgia") == {"georgia"}
    assert places.named_countries("Kuala Lumpur, Malaysia") == {"malaysia"} and places.named_regions("Malaysia") == set()
    assert places.named_regions("Remote - Asia Pacific") == {"asia", "apac"}
    assert places.named_regions("Remote (European time zones)") == {"europe"}


def test_every_country_has_a_name_to_show_and_a_part_of_the_world():
    every = places.all_countries()
    assert len(every) == len(places.COUNTRIES) >= 190
    assert all(c["area"] for c in every), [c["key"] for c in every if not c["area"]]
    names = [c["name"] for c in every]
    assert names == sorted(names) and "South Korea" in names and "Bosnia and Herzegovina" in names and "DR Congo" in names
    assert places.shown("united kingdom") == "United Kingdom" and places.shown("czechia") == "Czechia"


def _remote_postings():
    text = "We are looking for a developer to join our team. You will work with Python and SQL, and we offer mentoring."
    rows = [("plain", "careers", "Remote"), ("korea", "careers", "Remote, South Korea"), ("germany", "linkedin", "Remote, Germany"),
            ("usa-board", "remoteok", "USA Only"), ("eu-board", "weworkremotely", "Europe Only"), ("seoul", "careers", "Seoul, South Korea"),
            ("brno", "jobs.cz", "Brno")]
    return [store.new_job(id=i, title="Software Developer", company=f"Co {i}", location=loc, source=src, description=text,
                          url=f"https://example.com/{i}") for i, src, loc in rows]


def _kept(monkeypatch, **options):
    found = _remote_postings()
    monkeypatch.setattr(agent2_search.job_sources, "sources_for",
                        lambda source, max_age_days=0, country="": [job_sources.Board("fake", lambda q, where, n: [dict(j) for j in found])])
    api = ui_api.Api()
    assert api.save_options({**api.options(), "where": "Prague", **options})["ok"] is True
    dropped = []
    kept = sorted(j["id"] for j in agent2_search.search(["developer"], where="Prague", dropped=dropped))
    return kept, {d["url"].rsplit("/", 1)[-1]: d["reason"] for d in dropped}


def test_a_search_keeps_the_remote_jobs_open_to_your_country(isolate_data, monkeypatch):
    kept, dropped = _kept(monkeypatch)
    assert kept == ["brno", "eu-board", "plain"]
    assert dropped["korea"] == "A remote job for people in another part of the world (Remote, South Korea)."
    assert dropped["usa-board"] == "A remote job for people in another part of the world (USA Only)."
    assert dropped["germany"].startswith("A remote job") and dropped["seoul"].startswith("A career-site job somewhere else")


def test_a_search_with_added_countries_or_anywhere(isolate_data, monkeypatch):
    kept, _ = _kept(monkeypatch, remote_countries=["Germany", "South Korea"])
    assert kept == ["brno", "eu-board", "germany", "korea", "plain"]
    kept, dropped = _kept(monkeypatch, remote_where="world", remote_countries=[])
    assert kept == ["brno", "eu-board", "plain"] and sorted(dropped) == ["germany", "korea", "seoul", "usa-board"]
    kept, _ = _kept(monkeypatch, remote_where="world", remote_countries=["United States"])
    assert kept == ["brno", "eu-board", "plain", "usa-board"]


def test_the_remote_choice_is_saved_and_checked(isolate_data):
    api = ui_api.Api()
    assert api.options()["remote_where"] == "country" and api.options()["remote_countries"] == []    # before it was ever set
    assert api.save_options({**api.options(), "remote_where": "world", "remote_countries": ["South Korea", "germany", "Germany"]})["ok"]
    assert api.options()["remote_where"] == "world" and api.options()["remote_countries"] == ["south korea", "germany"]
    for bad, says in ((({"remote_where": "moon"}), "in your country or anywhere"),
                      ({"remote_countries": "Germany"}, "list of countries"), ({"remote_countries": [3]}, "list of countries"),
                      ({"remote_countries": ["Narnia"]}, "“Narnia” is not a country the app knows"),
                      ({"remote_countries": ["Germany"] * 41}, "up to 40 countries")):
        result = api.save_options({**api.options(), **bad})
        assert result["ok"] is False and says in result["msg"], (bad, result)
    assert api.options()["remote_where"] == "world"                                   # nothing was saved


def test_the_window_gets_every_country_by_name():
    every = ui_api.Api().countries()
    korea = next(c for c in every if c["key"] == "south korea")
    assert (korea["name"], korea["area"]) == ("South Korea", "asia") and isinstance(korea["names"], list)
    assert ui_api.Api().country_of("Sarajevo") == "Bosnia and Herzegovina"


def test_the_window_asks_the_rule_what_it_offers():
    offered = ui_api.Api().remote_choices()
    assert [s["key"] for s in offered["scopes"]] == ["country", "world"] and offered["most"] == places.RemoteReach.MAX_COUNTRIES
    assert offered["areas"][0] == {"key": "", "name": "All"}
    assert {a["key"] for a in offered["areas"][1:]} == set(places.AREA_OF.values())     # every part of the world a country is in
    assert {"key": "middle east", "name": "Middle East"} in offered["areas"]


def test_the_check_of_the_remote_choice_lives_with_the_rule():
    assert places.RemoteReach.problem({}) == "" and places.RemoteReach.problem({"remote_countries": ["Poland"]}) == ""
    assert "anywhere in the world" in places.RemoteReach.problem({"remote_where": "moon"})
    assert "Narnia" in places.RemoteReach.problem({"remote_countries": ["Narnia"]})


def test_a_source_knows_whether_it_lists_remote_jobs_only():
    remote_only = {s.name for s in job_sources.all_sources() if s.remote_only}
    assert remote_only == {"remoteok", "weworkremotely"}
    assert job_sources.is_remote_board("remoteok") and not job_sources.is_remote_board("linkedin")


def test_the_picker_gets_every_other_name_of_a_country():
    by_key = {c["key"]: c for c in places.all_countries()}
    assert "usa" in by_key["united states"]["names"] and "england" in by_key["united kingdom"]["names"]
    assert by_key["germany"]["key"] not in by_key["germany"]["names"]                # the key itself is not repeated
    assert all(isinstance(c["names"], list) for c in by_key.values())


def test_a_typed_country_is_one_the_app_knows_by_any_of_its_names():
    """Review of the Options fixes: Singapore, UK and Britain could not be entered; "Foo-DE" passed by its code."""
    for country, (names, _cities) in places.COUNTRIES.items():
        for name in (country, *names):
            assert places.country_named(name) == country, name
    for text, country in (("Singapore", "singapore"), ("UK", "united kingdom"), ("Britain", "united kingdom"),
                          ("Czech Republic", "czechia"), ("Bosnia-Herzegovina", "bosnia and herzegovina"), ("Côte d'Ivoire", "ivory coast"),
                          ("St. Lucia", "saint lucia"), ("U.S.", "united states"),
                          ("United States of America", "united states"), ("St Lucia", "saint lucia")):
        assert places.country_named(text) == country, text
    for wrong in ("Narnia", "Prague", "Foo-DE", "Narnia-US", "Xy-DE", "A-US", "Of-UK", "Germany, Austria", "Republic of Narnia", ""):
        assert places.country_named(wrong) == "", wrong
