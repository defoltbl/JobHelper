"""Any other posting page: the text a job site publishes about its own posting.

Most job sites and company career pages put a machine-readable copy of each posting
in the page (schema.org "JobPosting", for search engines). Boards that only hand out
a snippet (an aggregator's summary, a feed) link to such a page. Only that copy is
read: guessing which part of an unknown page is the posting would sooner or later
score a job on a cookie notice.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en;q=0.9",
}
_TIMEOUT = 20
_MAX_PAGE = 3_000_000      # bytes of a page that are looked at
_MAX_TEXT = 6000           # like the other boards


def _postings(node: Any, depth: int = 0):
    """Every JobPosting object inside a decoded JSON-LD value."""
    if depth > 6:
        return
    if isinstance(node, list):
        for item in node:
            yield from _postings(item, depth + 1)
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "JobPosting" in kinds:
            yield node
        for key in ("@graph", "mainEntity", "itemListElement", "item"):
            if key in node:
                yield from _postings(node[key], depth + 1)


def parse_posting(html_text: str) -> str:
    """The longest JobPosting description in a page, as plain text ('' if the page has none)."""
    soup = BeautifulSoup(html_text, "lxml")
    best = ""
    for tag in soup.find_all("script", attrs={"type": re.compile(r"^application/ld\+json", re.IGNORECASE)}):
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw, strict=False)
        except ValueError:
            continue
        for posting in _postings(data):
            description = posting.get("description")
            if not isinstance(description, str):
                continue
            # the description is HTML, sometimes with its tags escaped once more
            text = BeautifulSoup(description, "lxml").get_text(" ", strip=True)
            if "<" in text and ">" in text:
                text = BeautifulSoup(text, "lxml").get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > len(best):
                best = text
    return best[:_MAX_TEXT]


def posting_text(url: str) -> str:
    """Read a posting's own page and return its published text ('' if it has none or cannot be read)."""
    if urlparse(url or "").scheme not in ("http", "https"):
        return ""
    try:
        with requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, stream=True) as resp:
            if resp.status_code != 200 or "html" not in (resp.headers.get("Content-Type") or "").lower():
                return ""
            body = b""
            for chunk in resp.iter_content(65536):
                body += chunk
                if len(body) >= _MAX_PAGE:
                    break
            return parse_posting(body.decode(resp.encoding or "utf-8", errors="replace"))
    except (requests.RequestException, ValueError):
        return ""
