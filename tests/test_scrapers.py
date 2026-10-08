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


# ── found on a real posting: a company-branded page that loads its text by script ──
BRANDED = """<html><head>
<title>Junior AI Engineer - Praha - Detail pozice | ENERGETICKÝ A PRŮMYSLOVÝ HOLDING, a.s.</title>
<meta property="og:title" content="Junior AI Engineer - Praha - Detail pozice | ENERGETICKÝ A PRŮMYSLOVÝ HOLDING, a.s.">
<meta name="description" content="Jsi AI nadšenec? Nebaví Tě stereotypy? Máš schopnost strukturovat úkoly, podporovat inovace, navrhovat řešení a chceš se rozvíjet?">
</head><body><div class="main-menu">Aktivity O nás Kariéra</div><div class="cp-loader"></div></body></html>"""


def test_a_script_loaded_page_still_gives_company_and_language():
    from jobhelper import language, scrapers_cz
    description, company = scrapers_cz.parse_detail(BRANDED)
    assert company == "ENERGETICKÝ A PRŮMYSLOVÝ HOLDING, a.s."
    assert description.startswith("Jsi AI nadšenec?") and language.is_english(description) is False     # a Czech ad is seen as one


def test_a_normal_page_is_read_as_before():
    from jobhelper import scrapers_cz
    page = "<html><head><title>Python Developer | jobs.cz</title></head><body><main>" + "We are hiring a Python developer. " * 5 + "</main></body></html>"
    description, company = scrapers_cz.parse_detail(page)
    assert description.startswith("We are hiring a Python developer.") and company == ""                # the board's own name is not a company
    assert scrapers_cz.parse_detail("<html><body><p>short</p></body></html>") == ("", "")
    generic = '<html><head><meta name="description" content="Kariéra v Acme a.s. Podívejte se na aktuální volné pozice a zjistěte více."></head><body></body></html>'
    assert scrapers_cz.parse_detail(generic)[0] == ""                                                 # a careers-site blurb is not the ad


def test_details_fill_a_missing_company_but_never_replace_one(monkeypatch):
    from jobhelper import scrapers_cz, store
    monkeypatch.setattr(scrapers_cz, "_fetch_detail", lambda url: ("Text of the ad in English, long enough.", "Company From The Page"))
    monkeypatch.setattr(scrapers_cz.time, "sleep", lambda s: None)
    jobs = [store.new_job(id="1", title="A", company="", url="https://x/1"), store.new_job(id="2", title="B", company="Listed Name", url="https://x/2")]
    scrapers_cz._add_details(jobs)
    assert [j["company"] for j in jobs] == ["Company From The Page", "Listed Name"] and all(j["description"] for j in jobs)


def test_an_id_made_from_an_address_is_the_same_on_every_run():
    import subprocess
    import sys
    from pathlib import Path

    from jobhelper import store
    ROOT = Path(store.__file__).resolve().parent.parent
    code = "from jobhelper import store; print(store.url_id('https://eph.jobs.cz/pd/2001469399'))"
    runs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT)).stdout.strip() for _ in range(2)}
    assert runs == {store.url_id("https://eph.jobs.cz/pd/2001469399")} and len(next(iter(runs))) == 16
    for name in ("scrapers_cz", "scrapers_intl", "scrapers_remote"):
        assert "hash(" not in (ROOT / "jobhelper" / f"{name}.py").read_text(encoding="utf-8").replace("url_id(", ""), name
