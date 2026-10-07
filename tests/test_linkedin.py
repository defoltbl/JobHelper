from jobhelper import scrapers_intl


def test_parse_linkedin(linkedin_html):
    jobs = scrapers_intl.parse_linkedin(linkedin_html, "Praha")
    assert len(jobs) == 3
    for j in jobs:
        assert j["id"].startswith("linkedin-")
        assert j["title"]
        assert "/jobs/view/" in j["url"]
        assert j["source"] == "linkedin"


def test_linkedin_id_is_numeric_tail(linkedin_html):
    jobs = scrapers_intl.parse_linkedin(linkedin_html, "Praha")
    for j in jobs:
        assert j["id"].replace("linkedin-", "").isdigit()


def test_location_mapping():
    assert scrapers_intl._location("Praha") == "Prague, Czechia"
    assert scrapers_intl._location("Prague") == "Prague, Czechia"
    assert scrapers_intl._location("Brno") == "Brno, Czechia"
