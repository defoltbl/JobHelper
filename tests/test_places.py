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
    # a city the app has no table for: the city itself, and the country as typed in Options
    ("Tbilisi, Georgia", "Tbilisi", "", True), ("Batumi, Georgia", "Tbilisi", "", False), ("Batumi, Georgia", "Tbilisi", "Georgia", True),
    ("Prague", "Tbilisi", "Georgia", False), ("Remote", "Tbilisi", "Georgia", True), ("EMEA", "Tbilisi", "", True),
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
    monkeypatch.setattr(agent2_search.job_sources, "sources_for", lambda source, max_age_days=0: [job_sources.Board("fake", lambda q, where, n: [dict(j) for j in found])])
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
