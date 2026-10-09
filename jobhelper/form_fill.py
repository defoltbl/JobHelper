"""Filling in an application form that is open in the browser.

Three steps, each small enough to check:

1. READ: a script lists the fields of the page (what each is called, its kind, whether it
   already holds something). It never sends back what you typed, only "filled" or "empty".
2. plan(): plain rules decide what each field is. Your own details go in as they are saved;
   an open question is handed to form_answers (one Claude call, from your CV); everything
   else is left to you, with the reason.
3. FILL: a script writes the values into fields that are still empty and outlines them, so
   you can see what was done.

What is never done here: nothing is clicked, no box is ticked, no file is attached, no
password, payment or personal-status field is touched, and the form is never sent. Sending
is yours.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

from . import details, email_client, form_answers

MAX_FIELDS = 200

READ = r"""
(function () {
  var MARK = 'data-jobhelper', fields = [], frames = [], n = 0, boxes = 0;
  function clean(t) { return String(t || '').replace(/\s+/g, ' ').trim().slice(0, 300); }
  function text(el) { return el ? clean(el.innerText || el.textContent) : ''; }
  function shown(el) {
    var r = el.getBoundingClientRect(), s = el.ownerDocument.defaultView.getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
  }
  function byId(root, id) {
    try { return root.getElementById ? root.getElementById(id) : root.querySelector('#' + CSS.escape(id)); } catch (e) { return null; }
  }
  function label(el, root) {
    if (el.labels && el.labels.length && text(el.labels[0])) return text(el.labels[0]);
    var by = el.getAttribute('aria-labelledby');
    if (by) {
      var parts = by.split(/\s+/).map(function (id) { return text(byId(root, id)); }).filter(Boolean);
      if (parts.length) return clean(parts.join(' '));
    }
    if (el.getAttribute('aria-label')) return clean(el.getAttribute('aria-label'));
    var own = el.tagName === 'SELECT' ? text(el) : '', node = el;
    for (var i = 0; i < 3; i++) {
      node = node.parentElement;
      if (!node) break;
      var around = clean(text(node).replace(own, ''));
      if (around.length > 160) break;
      if (around) return around;
    }
    return '';
  }
  function walk(root) {
    var all = root.querySelectorAll('*');
    for (var i = 0; i < all.length && fields.length < __MOST__; i++) {
      var el = all[i], tag = el.tagName;
      if (el.shadowRoot) walk(el.shadowRoot);
      if (tag === 'IFRAME') {
        var inner = null;
        try { inner = el.contentDocument; } catch (e) { inner = null; }
        if (inner && inner.body) walk(inner); else if (el.src && shown(el)) frames.push(String(el.src).slice(0, 300));
        continue;
      }
      if (tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT') continue;
      el.removeAttribute(MARK);
      var type = tag === 'INPUT' ? String(el.getAttribute('type') || 'text').toLowerCase() : tag.toLowerCase();
      if (type === 'hidden' || type === 'submit' || type === 'button' || type === 'reset' || type === 'image') continue;
      if (type === 'checkbox' || type === 'radio') { if (shown(el) || (el.labels && el.labels.length)) boxes++; continue; }
      if (type !== 'file' && !shown(el)) continue;
      if (el.disabled || el.readOnly) continue;
      n++;
      el.setAttribute(MARK, String(n));
      var options = [];
      if (tag === 'SELECT') for (var k = 0; k < el.options.length && k < 300; k++) options.push(clean(el.options[k].text).slice(0, 80));
      var filled = false;
      if (type !== 'password' && type !== 'file') filled = tag === 'SELECT' ? el.selectedIndex > 0 : String(el.value || '').trim() !== '';
      fields.push({n: n, type: type, name: clean(el.name).slice(0, 80), id: clean(el.id).slice(0, 80),
                   auto: clean(el.getAttribute('autocomplete')).slice(0, 60), label: label(el, root),
                   hint: clean(el.getAttribute('placeholder')).slice(0, 120),
                   required: !!(el.required || el.getAttribute('aria-required') === 'true'),
                   filled: filled, most: el.maxLength > 0 ? el.maxLength : 0, options: options});
    }
  }
  walk(document);
  return JSON.stringify({url: location.href, title: clean(document.title), fields: fields, frames: frames.slice(0, 5), boxes: boxes});
})()
""".replace("__MOST__", str(MAX_FIELDS)).strip()

FILL = r"""
(function (items, url) {
  if (location.href !== url) return JSON.stringify({moved: true});
  var MARK = 'data-jobhelper', found = {}, done = [], skipped = [];
  function walk(root) {
    var all = root.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (el.shadowRoot) walk(el.shadowRoot);
      if (el.tagName === 'IFRAME') {
        var inner = null;
        try { inner = el.contentDocument; } catch (e) { inner = null; }
        if (inner && inner.body) walk(inner);
        continue;
      }
      var mark = el.getAttribute(MARK);
      if (mark) found[mark] = el;
    }
  }
  function tell(el, name) { el.dispatchEvent(new (el.ownerDocument.defaultView.Event)(name, {bubbles: true})); }
  function norm(t) { return String(t || '').replace(/\s+/g, ' ').trim().toLowerCase(); }
  walk(document);
  items.forEach(function (item) {
    var el = found[String(item.n)];
    if (!el || el.disabled || el.readOnly) { skipped.push(item.n); return; }
    var view = el.ownerDocument.defaultView;
    if (el.tagName === 'SELECT') {
      if (el.selectedIndex > 0) { skipped.push(item.n); return; }
      var want = norm(item.value), pick = -1;
      for (var k = 0; k < el.options.length; k++) {
        if (norm(el.options[k].text) === want || norm(el.options[k].value) === want) { pick = k; break; }
      }
      if (pick < 0) { skipped.push(item.n); return; }
      el.selectedIndex = pick;
    } else {
      if (String(el.value || '').trim() !== '') { skipped.push(item.n); return; }
      var proto = el.tagName === 'TEXTAREA' ? view.HTMLTextAreaElement.prototype : view.HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, item.value);
    }
    tell(el, 'input');
    tell(el, 'change');
    el.style.outline = '2px solid ' + (item.check ? '#f59e0b' : '#22c55e');
    el.style.outlineOffset = '1px';
    done.push(item.n);
  });
  return JSON.stringify({done: done, skipped: skipped});
})(__ITEMS__, __URL__)
""".strip()


def fill_script(items: list[dict[str, Any]], url: str) -> str:
    """The FILL script for these values. They travel as data (JSON), never as code."""
    data = [{"n": int(i["n"]), "value": str(i["value"]), "check": bool(i.get("check"))} for i in items]
    return FILL.replace("__ITEMS__", json.dumps(data)).replace("__URL__", json.dumps(str(url)))


# ── what a field is ─────────────────────────────────────────────────────────
PASSWORD = "A password is yours to type."
FILE = "Attach the file yourself: a page cannot be handed a file from outside."
PRIVATE = "Personal or payment information: fill it in yourself."
CHOICE = "Choose it yourself: I only pick from a list when it asks for your country."
DATE = "Pick the date yourself."
UNKNOWN = "I did not recognise this field."
NO_DETAIL = "Not in My details yet: add your {what} there and ask me again."
TOO_LONG = "The field takes {most} characters and this is {size}. Shorten it and paste it yourself."
NO_JOB = "An open question: choose the job this form is for, and I will draft the answer from your CV."
NO_LETTER = "No letter written by the app for this job. Paste your own."
TOO_MANY = f"More than {form_answers.MAX_QUESTIONS} open questions: ask me again after these are done."

_PRIVATE = re.compile(r"passw|captcha|card ?number|credit card|\bcvv\b|\bcvc\b|\biban\b|\bbank|account number|social security|\bssn\b"
                      r"|national id|id number|passport|birth|\bdob\b|\bage\b|gender|\bsex\b|pronoun|\brace\b|ethnic|disab|veteran"
                      r"|religio|orientation|marital|criminal|convict|health")
_NOT_MINE = re.compile(r"company|employer|organi[sz]ation|school|universit|college|referr|referee|reference|emergency|manager|recruiter"
                       r"|supervisor|\btitle\b|position|\brole\b|degree|skill|user ?name|login|nick")
_RULES = (("linkedin", re.compile(r"linked ?in")),
          ("github", re.compile(r"git ?hub")),
          ("email", re.compile(r"e ?mail")),
          ("phone", re.compile(r"phone|mobile|\bcell\b|telefon|\btel\b")),
          ("first_name", re.compile(r"first ?name|given ?name|fore ?name|\bfname\b|křestní")),
          ("last_name", re.compile(r"last ?name|sur ?name|family ?name|\blname\b|příjmení")),
          ("full_name", re.compile(r"full ?name|your name|^name\b|\bname$|\bname \*|jméno")),
          ("website", re.compile(r"web ?site|portfolio|personal site|home ?page|\bblog\b|\burl\b")),
          ("postcode", re.compile(r"post ?code|postal|\bzip\b|psč")),
          ("city", re.compile(r"\bcity\b|\btown\b|město|municipality")),
          ("country", re.compile(r"country|země|\bstát\b")),
          ("street", re.compile(r"street|address|ulice")),
          ("location", re.compile(r"location|where are you (?:based|located)|residence")))
_AUTO = {"given-name": "first_name", "family-name": "last_name", "name": "full_name", "email": "email", "tel": "phone",
         "tel-national": "phone", "street-address": "street", "address-line1": "street", "address-level2": "city",
         "postal-code": "postcode", "country": "country", "country-name": "country", "url": "website"}
_LETTER = re.compile(r"cover ?letter|motivation|motivační|průvodní")
_BY_TYPE = {"email": "email", "tel": "phone"}
WHAT = {"full_name": "name", "location": "city", **{key: label.lower() for key, label in details.LABELS.items()}}


def _words(field: dict[str, Any]) -> str:
    """What the page calls the field, as plain lower-case words (firstName, first_name -> first name)."""
    parts = " ".join(str(field.get(k) or "") for k in ("label", "hint", "name", "id"))
    parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", parts)
    return " ".join(re.sub(r"[_\-.\[\]:()]+", " ", parts).lower().split())


def name_of(field: dict[str, Any]) -> str:
    """What to call the field when talking to the person."""
    for key in ("label", "hint", "name", "id"):
        value = " ".join(str(field.get(key) or "").split())
        if value:
            return value[:120]
    return f"Field {field.get('n', '')}".strip()


def classify(field: dict[str, Any]) -> tuple[str, str]:
    """(what it is, why it is left). The first is a key of the details ("email", "full_name",
    "location"), "letter", "question", or "" when the field is left to the person."""
    kind = str(field.get("type") or "text").lower()
    words = _words(field)
    if kind == "password":
        return "", PASSWORD
    if kind == "file":
        return "", FILE
    if _PRIVATE.search(words):
        return "", PRIVATE
    if kind in ("date", "month", "week", "time", "datetime-local"):
        return "", DATE
    if kind in ("range", "color"):
        return "", CHOICE
    auto = (str(field.get("auto") or "").lower().split() or [""])[-1]
    what = _AUTO.get(auto) or _BY_TYPE.get(kind) or ""
    if not what:
        for key, rule in _RULES:
            if rule.search(words):
                if key in ("first_name", "last_name", "full_name", "street", "location", "city", "country", "postcode") and _NOT_MINE.search(words):
                    continue
                what = key
                break
    if kind == "select":
        return (what, "") if what == "country" else ("", CHOICE)
    if kind == "textarea" and _LETTER.search(words):
        return "letter", ""
    if what and kind == "textarea" and what not in ("street", "location"):
        what = ""                                   # a big box that mentions "name" or "email" is a question, not a detail
    if what:
        return what, ""
    label = str(field.get("label") or "").strip()
    if kind == "number":
        return "", UNKNOWN
    if kind == "textarea" or "?" in label or len(label) >= 20:
        return ("question", "") if re.search(r"[^\W\d_]{2}", label) else ("", UNKNOWN)
    return "", UNKNOWN


def value_for(what: str, mine: dict[str, str]) -> str:
    if what == "full_name":
        return details.full_name(mine) if mine.get("first_name") and mine.get("last_name") else ""
    if what == "location":
        return ", ".join(part for part in (mine.get("city", ""), mine.get("country", "")) if part) if mine.get("city") else ""
    return str(mine.get(what) or "")


def plan(fields: list[dict[str, Any]], mine: dict[str, str], letter: str = "", has_job: bool = False) -> dict[str, list]:
    """What to do with each field that is still empty:
    {"fill": [{n, label, value, kind}], "ask": [{n, label, most}], "left": [{label, why}]}.
    Fields that already hold something are not touched and not listed."""
    out: dict[str, list] = {"fill": [], "ask": [], "left": []}
    asked: set[str] = set()
    for field in fields:
        if field.get("filled"):
            continue
        label, most = name_of(field), int(field.get("most") or 0)
        what, why = classify(field)
        if not what:
            out["left"].append({"label": label, "why": why})
        elif what == "question":
            question = str(field.get("label") or "").strip()[:form_answers.MAX_QUESTION]
            if not has_job:
                out["left"].append({"label": label, "why": NO_JOB})
            elif question.lower() in asked:
                out["left"].append({"label": label, "why": "The same question as one above: copy that answer if it fits."})
            elif len(out["ask"]) >= form_answers.MAX_QUESTIONS:
                out["left"].append({"label": label, "why": TOO_MANY})
            else:
                asked.add(question.lower())
                out["ask"].append({"n": field["n"], "label": question, "most": most})
        else:
            value = letter if what == "letter" else value_for(what, mine)
            if not value:
                out["left"].append({"label": label, "why": NO_LETTER if what == "letter" else NO_DETAIL.format(what=WHAT.get(what, what))})
            elif most and len(value) > most:
                out["left"].append({"label": label, "why": TOO_LONG.format(most=most, size=len(value))})
            else:
                out["fill"].append({"n": field["n"], "label": label, "value": value, "kind": "letter" if what == "letter" else "detail"})
    return out


def read_answer(text: str) -> dict[str, Any]:
    """What the READ script gave back, checked: a page may answer anything."""
    try:
        data = json.loads(text or "")
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("fields"), list):
        raise ValueError("The page did not answer the way a page with a form does. Reload it and ask me again.")
    fields = []
    for raw in data["fields"][:MAX_FIELDS]:
        if not isinstance(raw, dict) or not isinstance(raw.get("n"), int):
            continue
        fields.append({"n": raw["n"], "filled": bool(raw.get("filled")), "required": bool(raw.get("required")),
                       "most": raw.get("most") if isinstance(raw.get("most"), int) else 0,
                       "options": [str(o)[:80] for o in (raw.get("options") or [])[:300]] if isinstance(raw.get("options"), list) else [],
                       **{key: " ".join(str(raw.get(key) or "").split())[:300] for key in ("type", "name", "id", "auto", "label", "hint")}})
    return {"url": str(data.get("url") or ""), "title": str(data.get("title") or "")[:300], "fields": fields,
            "frames": [str(f)[:300] for f in (data.get("frames") or [])[:5]] if isinstance(data.get("frames"), list) else [],
            "boxes": data.get("boxes") if isinstance(data.get("boxes"), int) else 0}


def fill_answer(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text or "")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise ValueError("The page did not say what was filled in. Look at the form: outlined fields were filled.")
    numbers = lambda key: [n for n in (data.get(key) or []) if isinstance(n, int)] if isinstance(data.get(key), list) else []   # noqa: E731
    return {"moved": bool(data.get("moved")), "done": numbers("done"), "skipped": numbers("skipped")}


# ── which job a page belongs to ─────────────────────────────────────────────
def host_of(url: str) -> str:
    try:
        return (urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _address(url: str) -> str:
    parts = urlsplit(str(url or ""))
    return f"{(parts.hostname or '').lower().removeprefix('www.')}{parts.path.rstrip('/')}"


def match_job(jobs: list[dict[str, Any]], url: str, title: str) -> str:
    """The id of the one job this page is plainly the form of, or ''. The same address as the
    posting, or the company's own name in the page's address or title; two jobs at one
    company are told apart by their title. Anything less certain is left for the person to choose."""
    here = _address(url)
    same = [j for j in jobs if j.get("url") and _address(j["url"]) == here and urlsplit(j["url"]).path.strip("/")]
    if len(same) == 1:
        return same[0]["id"]
    text = " ".join(re.findall(r"[a-z0-9]+", f"{here} {title}".lower()))       # the site's name, the path (boards name the company there), the title
    named = []
    for job in jobs:
        kept = email_client.company_tokens(job.get("company", ""))
        name = [w for w in re.findall(r"[a-z0-9]{3,}", str(job.get("company") or "").lower()) if w in kept]
        if not set(name) - email_client.GENERIC_COMPANY_WORDS:
            continue                                # a name made of words many companies share names nobody
        if re.search(rf"\b(?:{' '.join(name)}|{''.join(name)})\b", text):      # the whole name, in order: "good data" or "gooddata"
            named.append(job)
    if len(named) > 1:
        low = " ".join(str(title or "").lower().split())
        named = [j for j in named if j.get("title") and " ".join(j["title"].lower().split()) in low]
    return named[0]["id"] if len(named) == 1 else ""
