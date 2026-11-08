"""How the app introduces itself when it reads a job site: as a desktop browser does. One place for it,
so every scraper sends the same thing."""
from __future__ import annotations

import ipaddress
import socket
import threading
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests

MAX_HOPS = 5          # redirects followed, each one checked
LOOKUP_TIMEOUT = 5.0  # seconds a name lookup may take: a slow name server must not stall a search (#98)
# seconds a looked-up name is used again: the redirects of one link, never long enough to make a name that changes its
# address after the check (DNS rebinding) a sure thing; a search starts afresh (forget_lookups)
LOOKUP_KEPT = 10.0
LOOKUP_FAILED_KEPT = 60.0   # seconds a name that could not be looked up is not asked again: a dead name server costs one wait
READ_PIECE = 4096     # bytes read at a time, so the total time is checked often
MAX_PAGE = 3_000_000  # bytes of a page that are read
FETCH_TOTAL = 60.0    # seconds one fetch may take in all: a page that sends slowly is not read for ever (#98)
# what Python calls "global" but leads back into a private network: NAT64 (a translator in front of IPv4 addresses) and
# the old IPv6 site-local range
_NOT_PUBLIC = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("fec0::/10"), ipaddress.ip_network("::/96"),
               ipaddress.ip_network("192.0.0.0/24"))

BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def headers(language: str | None = "en;q=0.9", accept: str | None = None) -> dict[str, str]:
    """The request headers of a browser that reads pages in `language` (None: no preference) and accepts `accept`."""
    out = {"User-Agent": BROWSER}
    if accept:
        out["Accept"] = accept
    if language:
        out["Accept-Language"] = language
    return out


_lookups: dict[tuple[str, int], tuple[float, frozenset | None]] = {}     # None: the lookup failed or took too long
_lookups_lock = threading.Lock()


def forget_lookups() -> None:
    """Look every name up afresh (a new search, a test)."""
    with _lookups_lock:
        _lookups.clear()


def _keep(key: tuple[str, int], addresses: frozenset | None) -> None:
    with _lookups_lock:
        _lookups[key] = (time.monotonic(), addresses)


def _addresses(host: str, port: int) -> frozenset:
    """The addresses a host name stands for, within LOOKUP_TIMEOUT, kept for LOOKUP_KEPT; OSError when the name cannot
    be found, TimeoutError when the lookup takes longer (both kept for LOOKUP_FAILED_KEPT, so a dead name server costs
    one wait, not one per link). Each lookup runs in a thread of its own that never holds up the app's end: a hung one
    is left behind."""
    key, now = (host.lower(), port), time.monotonic()
    with _lookups_lock:
        kept = _lookups.get(key)
    if kept and now - kept[0] < (LOOKUP_KEPT if kept[1] is not None else LOOKUP_FAILED_KEPT):
        if kept[1] is None:
            raise OSError("The name could not be looked up a moment ago.")
        return kept[1]
    answer: list = []

    def look():
        try:
            answer.append(socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP))
        except Exception as e:  # noqa: BLE001 - handed to the caller as it is
            answer.append(e)
    worker = threading.Thread(target=look, name="lookup", daemon=True)
    worker.start()
    worker.join(LOOKUP_TIMEOUT)
    first = answer[0] if answer else None          # read once: a lookup that ends just now cannot change it in between
    if not isinstance(first, list):
        _keep(key, None)
        raise first or TimeoutError(f"Looking up {host} took more than {LOOKUP_TIMEOUT:.0f} seconds.")
    addresses = frozenset(ipaddress.ip_address(info[4][0].split("%")[0]) for info in first)
    _keep(key, addresses)
    return addresses


def public_address(url: str) -> bool:
    """Whether the app may read a web address it was handed (a posting's link, a redirect): http or https, and every
    address its host name stands for is on the public internet – never this Mac, the local network or a cloud's
    metadata address (#76). shortcut: the name is looked up again when the page is asked for, and an answer is kept for
    LOOKUP_KEPT seconds, so a name that changes its address in between is not caught; pin the address in the request if
    the app ever reads pages for other people."""
    text = str(url or "")
    if "\\" in text or any(ord(c) <= 32 or ord(c) == 127 for c in text):
        return False             # "http://127.0.0.1\@example.com/": urlparse sees example.com, requests goes to 127.0.0.1
    parts = urlparse(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = _addresses(parts.hostname, port)
    except (OSError, ValueError, UnicodeError, TimeoutError):   # no such name, a port that is not a number, a slow lookup
        return False
    return bool(addresses) and all(a.is_global and not any(a in net for net in _NOT_PUBLIC if a.version == net.version)
                                   for a in addresses)


def public_get(url: str, params: dict | None = None, headers: dict | None = None, timeout: float = 20,
               stream: bool = False) -> requests.Response | None:
    """GET a link the app was handed, following its redirects by hand so each one is checked (public_address); None
    when one is not public or there are more than MAX_HOPS. A network error raises as requests does."""
    for _hop in range(MAX_HOPS + 1):
        try:
            url = requests.Request("GET", url, params=params).prepare().url     # checked as requests will ask it
        except (requests.RequestException, ValueError):
            return None
        if not public_address(url):
            return None
        resp = requests.get(url, headers=headers, timeout=timeout, stream=stream, allow_redirects=False)
        if not resp.is_redirect:
            return resp
        resp.close()
        url, params = urljoin(url, resp.headers.get("Location") or ""), None
    return None


@dataclass(frozen=True)
class Page:
    """A page read with public_page: its status, its content type, at most MAX_PAGE bytes of its body, and its address
    after the redirects."""
    status: int
    kind: str
    body: bytes
    encoding: str | None
    url: str = ""

    @property
    def text(self) -> str:
        """The body as text, in the character set the server named, or as requests guesses it when it named none (a Czech
        board's page in windows-1250 stays readable)."""
        encoding = self.encoding
        if not encoding and self.body:
            encoding = requests.compat.chardet.detect(self.body).get("encoding")
        return self.body.decode(encoding or "utf-8", errors="replace")

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise requests.HTTPError(f"The page answered {self.status}.")


def public_page(url: str, headers: dict | None = None, timeout: float = 20) -> Page | None:
    """A page behind a link the app was handed (public_get), read to at most MAX_PAGE bytes and within FETCH_TOTAL
    seconds in all (requests.Timeout when it takes longer); None when the link is not public (#98)."""
    resp = public_get(url, headers=headers, timeout=timeout, stream=True)
    if resp is None:
        return None
    deadline, body = time.monotonic() + FETCH_TOTAL, bytearray()
    with resp:
        for chunk in resp.iter_content(READ_PIECE):
            body += chunk
            if len(body) >= MAX_PAGE:
                break
            if time.monotonic() > deadline:
                raise requests.Timeout(f"The page took more than {FETCH_TOTAL:.0f} seconds to send.")
        kind = (resp.headers.get("Content-Type") or "").lower()
        named = resp.encoding if "charset=" in kind else None     # requests says ISO-8859-1 for any text page that names none
        return Page(resp.status_code, kind, bytes(body[:MAX_PAGE]), named, str(getattr(resp, "url", "") or url))
