import pytest

from jobhelper import scrapers_cz, web


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
    assert description.startswith("Jsi AI nadšenec?") and language.detect(description) == "Czech"     # a Czech ad is seen as one


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

    def get(url):
        asked.append(url)
        return _Page(SITE_SCRIPT if "script.min.js" in url else BRANDED_PAGE, "https://example.jobs.cz/vacancy-detail?r=detail&id=2001452066")

    def post(url, **kw):
        posted.append((url, kw))
        return _Answer(_answer(FULL_HTML))
    monkeypatch.setattr(scrapers_cz, "_read_link", get)
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
    monkeypatch.setattr(scrapers_cz, "_read_link", lambda url: _Page(SITE_SCRIPT, url) if "script.min.js" in url else page)
    for answer in (_Answer({}, fail=True), _Answer({"errors": [{"message": "denied"}]}), _Answer(_answer("<p>tiny</p>"))):
        monkeypatch.setattr(scrapers_cz.requests, "post", lambda url, answer=answer, **kw: answer)
        assert scrapers_cz._fetch_detail("https://example.jobs.cz/pd/2001452066") == (summary, "Example Group")

    def no_network(url, **kw):
        raise scrapers_cz.requests.ConnectionError("down")
    monkeypatch.setattr(scrapers_cz.requests, "post", no_network)
    assert scrapers_cz._fetch_detail("https://example.jobs.cz/pd/2001452066")[0] == summary


def test_an_ordinary_page_with_its_text_asks_nothing_more(monkeypatch):
    full = "<html><body><main>" + "Our team builds data pipelines in Python and SQL every day. " * 12 + "</main></body></html>"
    monkeypatch.setattr(scrapers_cz, "_read_link", lambda url: _Page(full, url))

    def never(*a, **k):
        raise AssertionError("an ordinary page needs no second question")
    monkeypatch.setattr(scrapers_cz.requests, "post", never)
    assert len(scrapers_cz._fetch_detail("https://www.jobs.cz/rpd/1/")[0]) > 400

    def gone(url, params=None):
        raise scrapers_cz.requests.ConnectionError("down")
    monkeypatch.setattr(scrapers_cz, "_read_link", gone)
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
    monkeypatch.setattr(scrapers_cz, "_read_link", lambda url: asked.append(url) or _Page(INLINE_PAGE, "https://example.jobs.cz/vacancy-detail?r=detail&id=2001408263&rps=0"))
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
    def __init__(self, body=b"", status=200, kind="text/html; charset=utf-8", pieces=None, to=""):
        self.status_code, self.headers = status, {"Content-Type": kind, **({"Location": to} if to else {})}
        self.encoding = "utf-8" if "charset=utf-8" in kind else "ISO-8859-1"    # what requests says for text/* without one
        self.is_redirect = bool(to)
        self._pieces, self.read = pieces if pieces is not None else [body], 0

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, size):
        for piece in self._pieces:
            self.read += len(piece)
            yield piece


_NAMES = {"careers.example.com": "93.184.216.34", "jobs.example.org": "93.184.216.35", "intranet.example.com": "10.0.0.5",
          "localhost": "127.0.0.1", "split.example.com": ("93.184.216.36", "192.168.1.9"),
          "nat64.example.com": "64:ff9b::a00:5", "sitelocal.example.com": "fec0::1", "v6.example.com": "2606:2800:220:1::1"}


@pytest.fixture
def names(monkeypatch):
    """Host names looked up without the network: a public, a private and a mixed one."""
    from jobhelper import web

    def getaddrinfo(host, port, *a, **k):
        found = _NAMES.get(host, host)
        if not any(c.isdigit() for c in str(found)) and ":" not in str(found):
            raise web.socket.gaierror("no such name")
        return [(None, None, None, "", (ip, port)) for ip in (found if isinstance(found, tuple) else (found,))]
    monkeypatch.setattr(web.socket, "getaddrinfo", getaddrinfo)


def test_only_a_public_address_is_read(names):
    from jobhelper import web
    assert web.public_address("https://careers.example.com/jobs/1") and web.public_address("https://v6.example.com/")
    for private in ("http://nat64.example.com/", "http://sitelocal.example.com/", "http://127.0.0.1/", "http://[::1]/x", "http://localhost:8080/", "http://intranet.example.com/",
                    "http://169.254.169.254/latest/meta-data", "http://split.example.com/", "http://no-such.invalid/",
                    "ftp://careers.example.com/", "file:///etc/hosts", "https://careers.example.com:notaport/", "http://127.0.0.1\\@example.com/",
                    "http://169.254.169.254\\@careers.example.com/", "http://careers.example.com/\x00", "", None):
        assert not web.public_address(private), private


def test_a_slow_name_lookup_is_given_up_and_a_known_name_is_not_asked_again(monkeypatch, names):
    """#98: each hop of each link asked the name server with no time limit, so a slow one could stall a search."""
    import time
    asked, real = [], web.socket.getaddrinfo

    def counted(host, port, *a, **k):
        asked.append(host)
        return real(host, port, *a, **k)
    monkeypatch.setattr(web.socket, "getaddrinfo", counted)
    assert web.public_address("https://careers.example.com/a") and web.public_address("https://careers.example.com/b")
    assert asked == ["careers.example.com"], "one lookup for the name, then its answer is used again"
    web.forget_lookups()
    assert web.public_address("https://careers.example.com/c") and len(asked) == 2, "a new search asks afresh"
    monkeypatch.setattr(web, "LOOKUP_TIMEOUT", 0.2)
    monkeypatch.setattr(web.socket, "getaddrinfo", lambda *a, **k: time.sleep(2) or real(*a, **k))
    started = time.monotonic()
    assert web.public_address("https://slow.example.com/") is False and time.monotonic() - started < 1.5


def test_a_name_that_cannot_be_looked_up_costs_one_wait_and_an_answer_is_kept_only_briefly(monkeypatch, names):
    """Review of #98: a dead name server cost a full wait for every link, and a kept answer made a name that changes its
    address (DNS rebinding) a sure thing for a quarter of an hour."""
    import time
    asked = []

    def hung(host, port, *a, **k):
        asked.append(host)
        time.sleep(2)
        return []
    monkeypatch.setattr(web, "LOOKUP_TIMEOUT", 0.2)
    monkeypatch.setattr(web.socket, "getaddrinfo", hung)
    started = time.monotonic()
    assert not web.public_address("https://dead.example.com/a") and not web.public_address("https://dead.example.com/b")
    assert asked == ["dead.example.com"] and time.monotonic() - started < 1.0, "the second link does not wait again"
    assert web.LOOKUP_KEPT <= 30, "an answer is kept for the redirects of one link, not for long"


def test_a_page_s_address_after_its_redirects_and_its_guessed_character_set(monkeypatch, names):
    """Review of #98: the jobs.cz widget path asked page.url, which web.Page did not have, so a short posting ended the
    detail pass; a page with no character set must still read in windows-1250."""
    calls = []
    page = b"<html><head><title>Analyst | Acme</title></head><body><main>Short.</main></body></html>"
    monkeypatch.setattr(web.requests, "get", lambda url, **kw: _Stream(page))
    monkeypatch.setattr(scrapers_cz, "_fetch_widget", lambda html, url: calls.append(url) or ("", ""))
    scrapers_cz._fetch_detail("https://careers.example.com/rpd/123")
    assert calls == ["https://careers.example.com/rpd/123"]
    text = ("<html><body><p>Účetní – příliš žluťoučký kůň úpěl ďábelské ódy, přesně podle zadání.</p></body></html>"
            ).encode("cp1250")
    monkeypatch.setattr(web.requests, "get", lambda url, **kw: _Stream(text, kind="text/html"))     # no charset named
    assert "Účetní" in web.public_page("https://careers.example.com/cz").text


def test_a_page_that_sends_slowly_is_not_read_for_ever(monkeypatch, names):
    """#98: each read had a time limit, but a page that sent a little at a time could keep a fetch open for long."""
    import requests
    import time
    from jobhelper import scrapers_page

    class Dripping(_Stream):
        def iter_content(self, size):
            for _ in range(50):
                time.sleep(0.02)
                yield b"<p>"
    monkeypatch.setattr(web, "FETCH_TOTAL", 0.1)
    monkeypatch.setattr(web.requests, "get", lambda url, **kw: Dripping())
    with pytest.raises(requests.Timeout):
        web.public_page("https://careers.example.com/slow")
    assert scrapers_page.posting_text("https://careers.example.com/slow") == "", "the search goes on without that page"


def test_a_search_looks_its_names_up_afresh(monkeypatch):
    from jobhelper import agent2_search, job_sources
    forgot = []
    monkeypatch.setattr(web, "forget_lookups", lambda: forgot.append(1))
    monkeypatch.setattr(agent2_search.job_sources, "sources_for", lambda *a, **k: [job_sources.Board("fake", lambda q, w, n: [])])
    assert agent2_search.search(["python"], where="Prague") == [] and forgot == [1]


def test_one_accent_fold_for_the_whole_app():
    from jobhelper import cv_tailor, email_client, textfmt
    assert textfmt.plain_letters("Projektový Manažer") == "Projektovy Manazer" and textfmt.fold("ČSOB") == "csob"
    assert scrapers_cz._slug("Ústí nad Labem") == "usti-nad-labem" and email_client.norm_company("ČSOB (KBC)") == email_client.norm_company("CSOB")
    assert cv_tailor._camel("Účetní analytik") == "UcetniAnalytik"


def test_a_redirect_never_takes_the_reader_to_a_private_address(monkeypatch, names):
    """#76: requests followed every redirect of a posting's link, also to this Mac or the local network."""
    from jobhelper import scrapers_page
    page = ("<html>" + _ld({"@type": "JobPosting", "description": "Write tests."}) + "</html>").encode()
    asked = []

    def get(url, **kw):
        asked.append(url)
        assert kw["allow_redirects"] is False
        return answers.pop(0)
    monkeypatch.setattr(scrapers_page.requests, "get", get)
    answers = [_Stream(status=302, to="http://169.254.169.254/latest/meta-data")]
    assert scrapers_page.posting_text("https://careers.example.com/jobs/1") == "" and asked == ["https://careers.example.com/jobs/1"]
    asked.clear()
    answers = [_Stream(status=301, to="/jobs/2"), _Stream(status=302, to="https://jobs.example.org/2"), _Stream(page)]
    assert scrapers_page.posting_text("https://careers.example.com/jobs/1") == "Write tests."
    assert asked == ["https://careers.example.com/jobs/1", "https://careers.example.com/jobs/2", "https://jobs.example.org/2"]
    answers = [_Stream(status=302, to="/again")] * (scrapers_page.web.MAX_HOPS + 1)
    assert scrapers_page.posting_text("https://careers.example.com/loop") == ""
    asked.clear()
    assert scrapers_page.posting_text("http://intranet.example.com/jobs/1") == "" and asked == []


def test_a_page_without_a_character_set_is_read_as_its_own_bytes_say(monkeypatch, names):
    """#76: the server named no character set, requests guessed Latin-1, and "Projektový manažer" came out broken."""
    from jobhelper import scrapers_page
    page = ("<html>" + _ld({"@type": "JobPosting", "description": "Projektový manažer, Brno"}) + "</html>").encode("utf-8")
    monkeypatch.setattr(scrapers_page.requests, "get", lambda url, **kw: _Stream(page, kind="text/html"))
    assert scrapers_page.posting_text("https://careers.example.com/jobs/1") == "Projektový manažer, Brno"
    latin = ('<html><meta charset="windows-1250">' + _ld({"@type": "JobPosting", "description": "Účetní"}) + "</html>").encode("cp1250")
    monkeypatch.setattr(scrapers_page.requests, "get", lambda url, **kw: _Stream(latin, kind="text/html"))
    assert scrapers_page.posting_text("https://careers.example.com/jobs/2") == "Účetní", "the page's own meta charset"


def test_a_posting_page_is_read_with_care(monkeypatch, names):
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
    assert scrapers_page.posting_text("https://careers.example.com/big") == "" and endless.read <= web.MAX_PAGE + 1_000_000

    def down(url, **kw):
        raise scrapers_page.requests.ConnectionError("down")
    monkeypatch.setattr(scrapers_page.requests, "get", down)
    assert scrapers_page.posting_text("https://careers.example.com/jobs/1") == ""


def test_a_jobs_cz_link_to_a_private_address_is_never_asked(monkeypatch, names):
    """#76: the jobs.cz reader followed a posting's link and its script's address anywhere."""
    asked = []
    monkeypatch.setattr(scrapers_cz.requests, "get", lambda url, **kw: asked.append(url) or _Stream(b"<html></html>"))
    assert scrapers_cz._fetch_detail("http://intranet.example.com/rpd/1/") == ("", "") and asked == []
    monkeypatch.setattr(scrapers_cz.requests, "get", lambda url, **kw: asked.append(url) or _Stream(status=302, to="http://127.0.0.1:8080/"))
    assert scrapers_cz._fetch_detail("https://careers.example.com/rpd/1/") == ("", "") and asked == ["https://careers.example.com/rpd/1/"]


def test_a_board_that_cannot_be_read_says_so_instead_of_finding_nothing(monkeypatch):
    """#76: LinkedIn and the remote boards turned a failure into an empty list, so the search said it found nothing."""
    from jobhelper import scrapers_intl, scrapers_remote
    requests = scrapers_intl.requests

    class _Refused:
        status_code, text = 429, ""
    monkeypatch.setattr(scrapers_intl.requests, "get", lambda *a, **kw: _Refused())
    with pytest.raises(requests.HTTPError):
        scrapers_intl.linkedin("python", "Prague", 10)
    monkeypatch.setattr(scrapers_remote, "_remoteok_payload", lambda: (_ for _ in ()).throw(ValueError("not a list")))
    with pytest.raises(requests.ConnectionError):
        scrapers_remote.remoteok("python", "Prague", 10)
    monkeypatch.setattr(scrapers_remote, "wwr_feeds", lambda: ["a", "b"])
    monkeypatch.setattr(scrapers_remote, "_wwr_feed", lambda feed: (_ for _ in ()).throw(requests.ConnectionError("down")))
    with pytest.raises(requests.ConnectionError):
        scrapers_remote.weworkremotely("python", "Prague", 10)
    monkeypatch.setattr(scrapers_remote, "_wwr_feed", lambda feed: "<rss></rss>" if feed == "b" else (_ for _ in ()).throw(requests.ConnectionError("down")))
    assert scrapers_remote.weworkremotely("python", "Prague", 10) == [], "one feed down: the other is still read"


def test_the_board_s_own_search_needs_no_name_check(monkeypatch):
    """A VPN that hands out its own addresses must not stop the jobs.cz search, which asks a fixed address."""
    from jobhelper import web
    monkeypatch.setattr(web, "public_address", lambda url: False)
    monkeypatch.setattr(scrapers_cz.requests, "get", lambda url, **kw: type("R", (), {"raise_for_status": lambda self: None, "text": "<html></html>"})())
    assert scrapers_cz._get("https://www.jobs.cz/prace/praha/", params={"q": "python"}).text == "<html></html>"
    with pytest.raises(scrapers_cz.requests.ConnectionError):
        scrapers_cz._read_link("https://www.jobs.cz/rpd/1/")                   # a posting's link is checked
