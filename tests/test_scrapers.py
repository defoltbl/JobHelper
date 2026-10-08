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


# ── company-branded pages: the full posting comes from the page's own source ──
BRANDED_PAGE = ('<html lang="en"><head><meta property="og:title" content="Internal Tools Engineer | Example Group">'
                '<meta property="og:description" content="' + "A short summary of the role that says very little about it. " * 2 + '"></head><body>'
                '<div id="vacancy-detail" data-widget="main-en" data-assets="/assets/components"></div>'
                '<script src="/assets/js/script.min.js?av=1"></script></body></html>')
SITE_SCRIPT = ('x=JSON.parse(\'{"id":"example","host":"example.jobs.cz","widgets":{"main-cs":{"id":"w-cs","apiKey":"KEY-CS","version":3},'
               '"main-en":{"id":"w-en","apiKey":"KEY-EN","version":3}},"redirects":[]}\')')
FULL_HTML = "<p>You will build internal tools in Python.</p><ul><li>Automate workflows</li><li>Write tests</li></ul>" * 12


class _Page:
    def __init__(self, text, url):
        self.text, self.url = text, url


class _Answer:
    def __init__(self, data, fail=False):
        self._data, self._fail = data, fail

    def raise_for_status(self):
        if self._fail:
            raise scrapers_cz.requests.HTTPError("403 for url with nothing secret in it")

    def json(self):
        return self._data


def _answer(html="", sections=None, company="Example Group s.r.o."):
    return {"data": {"widget": {"jobAd": {"title": "T", "content": {"htmlContent": html, "sections": sections or []},
                                          "employer": {"companyName": company}}}}}


def test_a_branded_page_names_its_widget_and_posting():
    assert scrapers_cz.widget_script(BRANDED_PAGE) == "/assets/js/script.min.js?av=1"
    assert scrapers_cz.widget_script("<html><body><main>An ordinary page</main><script src='/assets/js/script.min.js'></script></body></html>") == ""
    assert scrapers_cz.widget_of(BRANDED_PAGE, SITE_SCRIPT) == {"id": "w-en", "key": "KEY-EN"}          # the one the page names
    assert scrapers_cz.widget_of(BRANDED_PAGE.replace(' data-widget="main-en"', ""), SITE_SCRIPT) == {"id": "w-cs", "key": "KEY-CS"}
    assert scrapers_cz.widget_of(BRANDED_PAGE, "var nothing = 1;") == {} and scrapers_cz.widget_of(BRANDED_PAGE, '"widgets":{broken}},"x"') == {}
    assert scrapers_cz.widget_of(BRANDED_PAGE, '"widgets":{"main-en":{"id":"w"}},"x":1') == {}          # no key, nothing to ask with
    assert scrapers_cz._posting_number("https://example.jobs.cz/vacancy-detail?r=detail&id=2001452066&rps=0") == "2001452066"
    assert scrapers_cz._posting_number("https://example.jobs.cz/pd/2001441194") == "2001441194" and scrapers_cz._posting_number("https://example.jobs.cz/") == ""


def test_the_answer_of_a_branded_page_becomes_plain_text():
    text, company = scrapers_cz.widget_text(_answer(FULL_HTML))
    assert text.startswith("You will build internal tools in Python. Automate workflows Write tests") and "<" not in text and company == "Example Group s.r.o."
    assert scrapers_cz.widget_text(_answer("", [{"title": "What you do", "text": "<p>Build tools.</p>"}, {"title": "We offer", "text": "Time to learn."}]))[0] \
        == "What you do Build tools. We offer Time to learn."
    assert len(scrapers_cz.widget_text(_answer("<p>word </p>" * 5000))[0]) == 6000
    for bad in ({}, {"data": None}, {"data": {"widget": {"jobAd": None}}}, {"errors": [{"message": "no"}]}, None, "text"):
        assert scrapers_cz.widget_text(bad) == ("", "")


def test_a_branded_posting_is_read_in_full(monkeypatch):
    asked, posted = [], []

    def get(url, params=None):
        asked.append(url)
        return _Page(SITE_SCRIPT if "script.min.js" in url else BRANDED_PAGE, "https://example.jobs.cz/vacancy-detail?r=detail&id=2001452066")

    def post(url, **kw):
        posted.append((url, kw))
        return _Answer(_answer(FULL_HTML))
    monkeypatch.setattr(scrapers_cz, "_get", get)
    monkeypatch.setattr(scrapers_cz.requests, "post", post)
    description, company = scrapers_cz._fetch_detail("https://www.jobs.cz/rpd/2001452066/")
    assert len(description) > 800 and description.startswith("You will build internal tools") and company == "Example Group"   # the page's own name wins
    assert asked == ["https://www.jobs.cz/rpd/2001452066/", "https://example.jobs.cz/assets/js/script.min.js?av=1"]
    url, sent = posted[0]
    assert url == scrapers_cz._WIDGET_API and sent["headers"]["X-API-KEY"] == "KEY-EN" and sent["timeout"]
    assert sent["json"]["variables"] == {"widgetId": "w-en", "jobAdId": "2001452066", "host": "example.jobs.cz", "isNotLoggableToSessionLog": True}


def test_a_branded_page_falls_back_to_its_summary(monkeypatch):
    page = _Page(BRANDED_PAGE, "https://example.jobs.cz/pd/2001452066")
    summary = scrapers_cz.parse_detail(BRANDED_PAGE)[0]
    assert 40 < len(summary) < 400
    monkeypatch.setattr(scrapers_cz, "_get", lambda url, params=None: _Page(SITE_SCRIPT, url) if "script.min.js" in url else page)
    for answer in (_Answer({}, fail=True), _Answer({"errors": [{"message": "denied"}]}), _Answer(_answer("<p>tiny</p>"))):
        monkeypatch.setattr(scrapers_cz.requests, "post", lambda url, answer=answer, **kw: answer)
        assert scrapers_cz._fetch_detail("https://example.jobs.cz/pd/2001452066") == (summary, "Example Group")

    def no_network(url, **kw):
        raise scrapers_cz.requests.ConnectionError("down")
    monkeypatch.setattr(scrapers_cz.requests, "post", no_network)
    assert scrapers_cz._fetch_detail("https://example.jobs.cz/pd/2001452066")[0] == summary


def test_an_ordinary_page_with_its_text_asks_nothing_more(monkeypatch):
    full = "<html><body><main>" + "Our team builds data pipelines in Python and SQL every day. " * 12 + "</main></body></html>"
    monkeypatch.setattr(scrapers_cz, "_get", lambda url, params=None: _Page(full, url))

    def never(*a, **k):
        raise AssertionError("an ordinary page needs no second question")
    monkeypatch.setattr(scrapers_cz.requests, "post", never)
    assert len(scrapers_cz._fetch_detail("https://www.jobs.cz/rpd/1/")[0]) > 400

    def gone(url, params=None):
        raise scrapers_cz.requests.ConnectionError("down")
    monkeypatch.setattr(scrapers_cz, "_get", gone)
    assert scrapers_cz._fetch_detail("https://www.jobs.cz/rpd/1/") == ("", "")


INLINE_PAGE = ('<html><head><meta property="og:title" content="Mechanical Designer | Example Works">'
               '<meta property="og:description" content="' + "A short summary that says little about the role itself. " * 2 + '"></head><body>'
               '<div id="widget_container"></div><script>window.__LMC_CAREER_WIDGET__.push({"apiKey":"KEY-IN-PAGE","widgetId":"w-page",'
               '"selector":"#widget_container","shareJobAdUrlTemplate":"https:\\/\\/example.jobs.cz\\/share\\/__jobAdId__","gtm":{"id":"G","insertScript":false}});</script>'
               '<script src="/assets/js/script.min.js?av=2"></script></body></html>')


def test_a_branded_page_that_carries_its_own_settings(monkeypatch):
    assert scrapers_cz.widget_in_page(INLINE_PAGE) == {"id": "w-page", "key": "KEY-IN-PAGE"}
    assert scrapers_cz.widget_in_page(BRANDED_PAGE) == {} and scrapers_cz.widget_in_page("<script>window.__LMC_CAREER_WIDGET__.push({broken});</script>") == {}
    assert scrapers_cz.widget_in_page('<script>window.__LMC_CAREER_WIDGET__.push({"widgetId":"w"});</script>') == {}
    asked, posted = [], []
    monkeypatch.setattr(scrapers_cz, "_get", lambda url, params=None: asked.append(url) or _Page(INLINE_PAGE, "https://example.jobs.cz/vacancy-detail?r=detail&id=2001408263&rps=0"))
    monkeypatch.setattr(scrapers_cz.requests, "post", lambda url, **kw: posted.append(kw) or _Answer(_answer(FULL_HTML, company="Example Works s.r.o.")))
    description, company = scrapers_cz._fetch_detail("https://www.jobs.cz/rpd/2001408263/")
    assert len(description) > 800 and company == "Example Works"
    assert asked == ["https://www.jobs.cz/rpd/2001408263/"]                                # no second page needed
    assert posted[0]["headers"]["X-API-KEY"] == "KEY-IN-PAGE" and posted[0]["json"]["variables"]["widgetId"] == "w-page"
    assert posted[0]["json"]["variables"]["jobAdId"] == "2001408263"


# ── any other posting page: only the copy the page itself publishes ─────────
def _ld(data):
    import json
    return '<script type="application/ld+json">' + json.dumps(data) + "</script>"


def test_a_page_s_own_copy_of_the_posting_is_read():
    from jobhelper import scrapers_page
    body = "<p>You will write Python services.</p><ul><li>Tests</li><li>Reviews</li></ul>"
    plain = "You will write Python services. Tests Reviews"
    assert scrapers_page.parse_posting("<html><head>" + _ld({"@type": "JobPosting", "title": "Dev", "description": body}) + "</head></html>") == plain
    assert scrapers_page.parse_posting(_ld({"@graph": [{"@type": "Organization", "description": "About us"}, {"@type": ["Thing", "JobPosting"], "description": body}]})) == plain
    assert scrapers_page.parse_posting(_ld([{"@type": "BreadcrumbList"}, {"@type": "JobPosting", "description": body.replace("<", "&lt;").replace(">", "&gt;")}])) == plain
    two = _ld({"@type": "JobPosting", "description": "Short one."}) + _ld({"@type": "JobPosting", "description": body})
    assert scrapers_page.parse_posting(two) == plain                                    # the longest wins
    assert len(scrapers_page.parse_posting(_ld({"@type": "JobPosting", "description": "word " * 5000}))) == 6000
    for nothing in ("<html><body><main>" + "Plenty of words on the page but no published copy. " * 30 + "</main></body></html>",
                    '<script type="application/ld+json">{broken</script>', '<script type="application/ld+json"></script>',
                    _ld({"@type": "Organization", "description": "We are a company."}), _ld({"@type": "JobPosting", "description": None}),
                    _ld({"@type": "JobPosting"}), _ld("text"), ""):
        assert scrapers_page.parse_posting(nothing) == ""
    deep = {"@type": "JobPosting", "description": "found"}
    for _ in range(10):
        deep = {"@graph": [deep]}
    assert scrapers_page.parse_posting(_ld(deep)) == ""                                 # nesting without end is not followed


class _Stream:
    def __init__(self, body=b"", status=200, kind="text/html; charset=utf-8", pieces=None):
        self.status_code, self.headers, self.encoding = status, {"Content-Type": kind}, "utf-8"
        self._pieces, self.read = pieces if pieces is not None else [body], 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, size):
        for piece in self._pieces:
            self.read += len(piece)
            yield piece


def test_a_posting_page_is_read_with_care(monkeypatch):
    from jobhelper import scrapers_page
    page = ("<html>" + _ld({"@type": "JobPosting", "description": "<p>You will write Python services and test them.</p>"}) + "</html>").encode()
    asked = []

    def get(url, **kw):
        asked.append((url, kw))
        return answers.pop(0)
    monkeypatch.setattr(scrapers_page.requests, "get", get)
    answers = [_Stream(page)]
    assert scrapers_page.posting_text("https://careers.example.com/jobs/1") == "You will write Python services and test them."
    assert asked[0][1]["timeout"] and asked[0][1]["stream"] is True
    answers = [_Stream(page, status=403), _Stream(page, status=404), _Stream(page, kind="application/pdf"), _Stream(page, kind="")]
    assert [scrapers_page.posting_text("https://careers.example.com/jobs/1") for _ in range(4)] == ["", "", "", ""]   # a no is a no
    for not_a_page in ("", "file:///etc/hosts", "ftp://example.com/x", "javascript:alert(1)", "careers.example.com/jobs/1", None):
        assert scrapers_page.posting_text(not_a_page) == ""
    assert len(asked) == 5                                                              # those were never asked for
    endless = _Stream(pieces=[b"x" * 1_000_000] * 50)
    answers = [endless]
    assert scrapers_page.posting_text("https://careers.example.com/big") == "" and endless.read <= scrapers_page._MAX_PAGE + 1_000_000

    def down(url, **kw):
        raise scrapers_page.requests.ConnectionError("down")
    monkeypatch.setattr(scrapers_page.requests, "get", down)
    assert scrapers_page.posting_text("https://careers.example.com/jobs/1") == ""
