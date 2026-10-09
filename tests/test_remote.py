from jobhelper import scrapers_remote

FAKE_REMOTEOK = (
    {"id": "1", "position": "Python Developer", "company": "Acme", "tags": ["python", "backend"],
     "description": "Build APIs", "location": "Worldwide", "url": "https://remoteok.com/x/1"},
    {"id": "2", "position": "Marketing Manager", "company": "BrandCo", "tags": ["marketing"],
     "description": "Ads", "location": "US", "url": "https://remoteok.com/x/2"},
)

WWR_RSS = """<rss><channel>
<item><title><![CDATA[Acme: Backend Python Engineer]]></title>
<link>https://weworkremotely.com/remote-jobs/acme-backend-python-engineer</link>
<description><![CDATA[We need a Python engineer to build services.]]></description>
<region>Anywhere</region></item>
<item><title>BrandCo: Sales Lead</title>
<link>https://weworkremotely.com/remote-jobs/brandco-sales-lead</link>
<description>Sell things</description><region>US only</region></item>
</channel></rss>"""


def test_remoteok_filters_by_keyword(monkeypatch):
    monkeypatch.setattr(scrapers_remote, "_remoteok_payload", lambda: FAKE_REMOTEOK)
    jobs = scrapers_remote.remoteok("python", "", 10, with_description=False)
    assert len(jobs) == 1
    assert jobs[0]["id"] == "remoteok-1"
    assert jobs[0]["title"] == "Python Developer"
    assert jobs[0]["source"] == "remoteok"


def test_parse_wwr_items():
    items = scrapers_remote._parse_wwr_items(WWR_RSS)
    assert len(items) == 2
    assert items[0]["title"] == "Acme: Backend Python Engineer"
    assert "python" in items[0]["description"].lower()


def test_weworkremotely_splits_company_and_filters(monkeypatch):
    monkeypatch.setattr(scrapers_remote, "_wwr_feed", lambda url: WWR_RSS)
    monkeypatch.setattr(scrapers_remote, "wwr_feeds", lambda fields=None: ["x"])
    jobs = scrapers_remote.weworkremotely("python", "", 10)
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Acme"
    assert jobs[0]["title"] == "Backend Python Engineer"
    assert jobs[0]["source"] == "weworkremotely"


def test_keyword_matching():
    assert scrapers_remote._matches("python developer", "Senior Python Dev", "")
    assert not scrapers_remote._matches("python", "Marketing Manager", "ads")
    assert scrapers_remote._matches("", "anything")  # empty keyword matches


def test_the_remote_board_s_lists_follow_the_profession(isolate_data):
    """Only the programming lists were read, whoever was searching."""
    feeds = scrapers_remote.wwr_feeds
    programming = [u for u in feeds(["software and IT"])]
    assert len(programming) == 2 and all("programming" in u or "devops" in u for u in programming)
    assert feeds([]) == programming and feeds(None) == programming            # nothing known: as before
    assert feeds(["customer support"]) == ["https://weworkremotely.com/categories/remote-customer-support-jobs.rss"]
    assert "remote-sales-and-marketing-jobs.rss" in feeds(["sales and marketing"])[0]
    nurse = feeds(["care and health"])                                         # no list of its own: the general ones
    assert len(nurse) == 2 and nurse[0].endswith("all-other-remote-jobs.rss") and nurse[1].endswith("/remote-jobs.rss")
    both = feeds(["software and IT", "design and media", "design and media"])
    assert len(both) == 3 and len(set(both)) == 3
    assert all(u.startswith("https://weworkremotely.com/") and u.endswith(".rss") for field in scrapers_remote._WWR_BY_FIELD for u in feeds([field]))
    from jobhelper import prefilter
    assert set(scrapers_remote._WWR_BY_FIELD) <= set(prefilter.FIELDS), "the names are the app's own profession names"


def test_the_profession_comes_from_options(isolate_data):
    from jobhelper import ui_api
    api = ui_api.Api()
    assert api.save_options({**api.options(), "my_fields": ["customer support"]})["ok"] is True
    assert scrapers_remote.wwr_feeds() == ["https://weworkremotely.com/categories/remote-customer-support-jobs.rss"]
    assert api.save_options({**api.options(), "my_fields": [], "wanted_roles": ["graphic designer"], "queries": []})["ok"] is True
    assert scrapers_remote.wwr_feeds() == ["https://weworkremotely.com/categories/remote-design-jobs.rss"]
