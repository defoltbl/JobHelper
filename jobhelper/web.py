"""How the app introduces itself when it reads a job site: as a desktop browser does. One place for it,
so every scraper sends the same thing."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

MAX_HOPS = 5          # redirects followed, each one checked
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


def public_address(url: str) -> bool:
    """Whether the app may read a web address it was handed (a posting's link, a redirect): http or https, and every
    address its host name stands for is on the public internet – never this Mac, the local network or a cloud's
    metadata address (#76). shortcut: the name is looked up again when the page is asked for (a name that changes in
    between is not caught); pin the address in the request if the app ever reads pages for other people."""
    text = str(url or "")
    if "\\" in text or any(ord(c) <= 32 or ord(c) == 127 for c in text):
        return False             # "http://127.0.0.1\@example.com/": urlparse sees example.com, requests goes to 127.0.0.1
    parts = urlparse(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        found = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
        addresses = {ipaddress.ip_address(info[4][0].split("%")[0]) for info in found}
    except (OSError, ValueError, UnicodeError):            # no such name, a port that is not a number
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
