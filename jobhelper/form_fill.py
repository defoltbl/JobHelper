"""Filling in an application form that is open in the browser.

Three steps, each small enough to check:

1. READ: a script lists the fields of the page (what each is called, its kind, whether it
   already holds something). It never sends back what you typed, only "filled" or "empty".
2. plan(): plain rules decide what each field is. Your own details go in as they are saved;
   an open question is handed to form_answers (one Claude call, from your CV); everything
   else is left to you, with the reason.
3. FILL: a script writes the values into fields that are still empty and outlines them, so
   you can see what was done.

A list, a pair of radio buttons or a menu drawn by the page is a "choice": plan() lists them
and form_choices decides them. The CHOOSE script then presses exactly three kinds of thing:
what opens a menu, an entry of a menu, a radio button.

What is never done here: no button is pressed, no box is ticked, no file is attached, no
password, payment or personal-status field is touched, and the form is never sent. Sending
is yours.
"""
from __future__ import annotations

import calendar
import json
import os
import re
import unicodedata
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlsplit

from . import details, email_client, form_answers, mailhosts, places

MAX_FIELDS = 200
_MARK = re.compile(r"__([A-Z]+)__")          # where a script takes a value


def with_values(script: str, **values: Any) -> str:
    """The script with each `__NAME__` in it replaced by that value, written as JSON: data from a page or from a
    person goes in as data and never becomes code."""
    # one pass over the script as written: a value that holds a mark such as "__URL__" is never filled in again
    return _MARK.sub(lambda m: json.dumps(values[m.group(1).lower()]) if m.group(1).lower() in values else m.group(0), script)



FORM_REFUSED = "The page did not answer the way a page with a form does. Reload it and ask me again."


def page_reply(text: str, refused: str = "") -> dict[str, Any] | None:
    """What a script gave back, as an object. A page may answer anything: an answer that is not a JSON object
    raises ValueError(refused) when a message is given, else it is None."""
    try:
        data = json.loads(text or "")
    except ValueError:
        data = None
    if isinstance(data, dict):
        return data
    if refused:
        raise ValueError(refused)
    return None


# The only tick boxes the assistant ticks: "I currently work here" for a job that goes on, and "I am fluent in this
# language". One set of words for the page scripts (READ, CHOOSE) and for plan(): whole phrases, not loose words, so
# "Keep me up to date", "I currently require visa sponsorship" or "I have a current driving licence" are never ticked.
_TICK_END = r"[\s.*]*(?:\(?required\)?[\s.*]*)?$"                # "I currently work here *", "... (required)"
CURRENT_BOX_WORDS = (r"^\s*(?:i (?:am )?(?:currently |still )?work(?:ing)? (?:at|for) this company"
                     r"|i am (?:currently |still )?employed (?:here|there)"
                     r"|i (?:am )?(?:currently |still )?work(?:ing)? (?:here|there)"
                     r"|(?:currently|still) (?:work(?:ing)?|employed)(?: (?:here|there|at this company|for this company))?"
                     r"|current|currently|present|ongoing|till now|until now|to date|still working"
                     r"|(?:current|present) (?:job|role|position|employer)|this is my current (?:job|role|position|employer)"
                     r"|(?:until|till) (?:now|present))(?: now| currently)?" + _TICK_END)
FLUENT_WORDS = r"^\s*(?:i am fluent(?: in this language)?|fluent in this language|i speak this language fluently|(?:i am a )?native speaker)" + _TICK_END
NEVER_TICK_WORDS = (r"agree|consent|terms|privacy|policy|newsletter|subscribe|marketing|keep me|notify|\bupdates?\b|alert"
                    r"|sponsor|visa|licen[cs]e|\brequires?\b|authori[sz]|permit|allow|contact|certif|confirm|declar|accept"
                    r"|acknowledg|gdpr|understand|opt.?in|disclos|\bnot\b|\bno longer\b|\bnever\b|former|\?|true|correct|accurate"
                    r"|\bcall|reference|verify|\bsign")

# A list counts as chosen when what it shows is a real entry: not its first line, not a "Select..." line without a value, not a greyed-out one.
_CHOSEN = ("function chosen(el) { var o = el.options[el.selectedIndex]; "
           "return el.selectedIndex > 0 && !!o && !o.disabled && String(o.value) !== ''; }")

READ = r"""
(function () {
  __CHOSEN__
  var MARK = 'data-jobhelper', OPT = 'data-jobhelper-opt', ADD = 'data-jobhelper-add', fields = [], frames = [], groups = {}, adds = [], n = 0, boxes = 0;
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
    var node = el;
    for (var i = 0; i < 3; i++) {
      node = node.parentElement;
      if (!node) break;
      if (others(node, el)) break;                // further out the words belong to other fields as well
      var around = beside(node, el);
      if (around.length > 160) break;
      if (around) return around;
    }
    return '';
  }
  function beside_value(el) {                    // a list drawn around a text box shows its answer beside the box, not in it
    if (el.getAttribute('role') !== 'combobox' && !el.getAttribute('aria-autocomplete')) return false;
    var node = el;
    for (var up = 0; up < 4; up++) {
      node = node.parentElement;
      if (!node || others(node, el)) return false;
      var held = node.querySelector('[class*="single-value"], [class*="singleValue"], [class*="multi-value"], [class*="multiValue"]');
      if (held && text(held)) return true;
    }
    return false;
  }
  function others(node, el) {
    var all = node.querySelectorAll('input:not([type=hidden]), select, textarea');
    for (var i = 0; i < all.length; i++) if (all[i] !== el && !el.contains(all[i]) && all[i].getClientRects().length) return true;
    return false;
  }
  function beside(node, el) {                    // the words in `node` that are not the field's own: a list's 250 countries are not its name
    var walker = el.ownerDocument.createTreeWalker(node, 4, null), out = '', t;
    while ((t = walker.nextNode()) && out.length < 400) {
      var p = t.parentElement;
      if (!p || el.contains(t) || /^(OPTION|OPTGROUP|SELECT|SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(p.tagName) || p.closest('button') || !p.getClientRects().length) continue;
      out += ' ' + t.nodeValue;
    }
    return clean(out);
  }
  function without(whole, parts) {
    parts.forEach(function (part) { if (part) whole = whole.replace(part, ' '); });
    return clean(whole);
  }
  function question(el, root, name) {            // what a group of choices is asked: its legend, its label, or the words around it
    var set = el.closest('fieldset');
    if (set && set.querySelector('legend') && text(set.querySelector('legend'))) return text(set.querySelector('legend'));
    var group = el.closest('[role=radiogroup]');
    if (group && label(group, root)) return label(group, root);
    var same = root.querySelectorAll('input[type=radio]'), mine = [], node = el;
    for (var i = 0; i < same.length; i++) if (same[i].name === name) mine.push(same[i]);
    var said = mine.map(function (r) { return r.labels && r.labels.length ? text(r.labels[0]) : ''; });
    for (var up = 0; up < 5 && node.parentElement; up++) {
      node = node.parentElement;
      var rest = without(text(node), said);
      if (rest.length > 200) break;
      if (rest) return rest;
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
      if (tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT') {
        var role = el.getAttribute('role');
        el.removeAttribute(MARK);
        el.removeAttribute(ADD);
        if (!shown(el)) continue;
        if ((tag === 'BUTTON' || tag === 'A' || role === 'button') && el.type !== 'submit' && !el.disabled) {
          var says = text(el).slice(0, 80);       // "Add another job": noted, so that a row can be asked for
          if (/^\+?\s*add\b/i.test(says) && !/apply|submit|send|next|continue|save|finish|upload|file|attach/i.test(says)) {
            el.setAttribute(ADD, String(adds.length));
            adds.push({k: adds.length, text: says});
          }
        }
        if (role === 'combobox' || el.getAttribute('aria-haspopup') === 'listbox') {      // a menu drawn by the page itself
          var now = text(el);
          n++;
          el.setAttribute(MARK, String(n));
          fields.push({n: n, type: 'menu', name: '', id: clean(el.id).slice(0, 80), auto: '', label: label(el, root), hint: '',
                       required: el.getAttribute('aria-required') === 'true', most: 0, options: [], combo: false,
                       filled: !!now && !/^(select|choose|please|pick|none|-|\u2014|\.)/i.test(now)});
        } else if (role === 'listbox' || role === 'radio' || role === 'checkbox' || role === 'switch') boxes++;
        continue;
      }
      el.removeAttribute(MARK);
      el.removeAttribute(OPT);
      var type = tag === 'INPUT' ? String(el.getAttribute('type') || 'text').toLowerCase() : tag.toLowerCase();
      if (type === 'hidden' || type === 'submit' || type === 'button' || type === 'reset' || type === 'image') continue;
      // A box the page keeps out of sight of screen readers is its own tool (a list's check that something was chosen), not a field.
      if (type !== 'file' && (el.getAttribute('aria-hidden') === 'true' || el.closest('[aria-hidden=true]'))) continue;
      if (type === 'checkbox' || type === 'radio') {
        if (!(shown(el) || (el.labels && el.labels.length))) continue;
        if (type === 'checkbox' && !el.disabled) {
          var says = clean(el.labels && el.labels.length ? text(el.labels[0]) : (el.getAttribute('aria-label') || '')).slice(0, 120);
          if (/__TICK__/i.test(says) && !/__NEVER_TICK__/i.test(says)) {
            n++;
            el.setAttribute(MARK, String(n));
            fields.push({n: n, type: 'checkbox', name: clean(el.name).slice(0, 80), id: clean(el.id).slice(0, 80), auto: '', label: says, hint: '',
                         required: false, filled: !!el.checked, most: 0, options: [], combo: false});
            continue;
          }
        }
        if (type === 'checkbox' || !el.name || el.disabled) { boxes++; continue; }
        var group = groups[el.name];              // the radio buttons of one question are one field
        if (!group) {
          n++;
          group = groups[el.name] = {n: n, type: 'radio', name: clean(el.name).slice(0, 80), id: '', auto: '', label: question(el, root, el.name),
                                     hint: '', required: !!el.required, filled: false, most: 0, options: [], combo: false};
          fields.push(group);
        }
        el.setAttribute(OPT, group.n + ':' + group.options.length);
        group.options.push(clean(el.labels && el.labels.length ? text(el.labels[0]) : (el.getAttribute('aria-label') || el.value)).slice(0, 80));
        if (el.checked) group.filled = true;
        continue;
      }
      if (type !== 'file' && !shown(el)) continue;
      if (el.disabled || (el.readOnly && el.getAttribute('role') !== 'combobox')) continue;       // a list's box is often read-only: it is pressed, not typed in
      n++;
      el.setAttribute(MARK, String(n));
      var options = [];
      if (tag === 'SELECT') for (var k = 0; k < el.options.length && k < 300; k++) options.push(clean(el.options[k].text).slice(0, 80));
      var filled = false;
      if (type === 'file') filled = !!(el.files && el.files.length);
      else if (type !== 'password') filled = tag === 'SELECT' ? chosen(el) : (String(el.value || '').trim() !== '' || beside_value(el));
      var called = label(el, root), hint = clean(el.getAttribute('placeholder')).slice(0, 120);
      if (tag === 'SELECT' && !called && el.options.length && String(el.options[0].value) === '') hint = clean(el.options[0].text).slice(0, 120);   // "Select your country": all the name it has
      if (el.readOnly) type = 'menu';             // a box that cannot be typed in and opens a list: a menu like any other
      var part = '', group = '';                  // a date split into boxes ("MM" and "YYYY"): which part this is, and what the pair is called ("From")
      var asks = clean(el.getAttribute('aria-label') || hint || called).toLowerCase();
      if (tag === 'INPUT' && /^(mm|month|yyyy|year|dd|day)$/.test(asks)) {
        part = /^(mm|month)$/.test(asks) ? 'month' : (/^(yyyy|year)$/.test(asks) ? 'year' : 'day');
        var holder = el.parentElement ? (el.parentElement.closest('[role=group], fieldset') || el.parentElement) : null;
        var legend = holder && holder.tagName === 'FIELDSET' ? holder.querySelector('legend') : null;
        group = holder ? (legend && text(legend) ? text(legend) : label(holder, root)) : '';
      }
      var code = '';                              // a list of calling codes says which one it shows: the number beside it depends on it
      if (tag === 'SELECT' && filled && options.length >= 10 && options.filter(function (o) { return /\+\d{1,4}\b/.test(o); }).length > options.length * 0.7)
        code = (clean(el.options[el.selectedIndex].text).match(/\+\d{1,4}\b/) || [''])[0];
      fields.push({n: n, type: type, name: clean(el.name).slice(0, 80), id: clean(el.id).slice(0, 80),
                   auto: clean(el.getAttribute('autocomplete')).slice(0, 60), label: called,
                   hint: hint, accept: type === 'file' ? clean(el.getAttribute('accept')).slice(0, 200) : '', code: code, part: part, group: group.slice(0, 120),
                   required: !!(el.required || el.getAttribute('aria-required') === 'true'),
                   filled: filled, most: el.maxLength > 0 ? el.maxLength : 0, options: options,
                   combo: !el.readOnly && (el.getAttribute('role') === 'combobox' || !!el.getAttribute('aria-autocomplete') || el.getAttribute('aria-haspopup') === 'listbox')});
    }
  }
  walk(document);
  return JSON.stringify({url: location.href, title: clean(document.title), from: String(document.referrer || '').slice(0, 2000), fields: fields, frames: frames.slice(0, 5), boxes: boxes, adds: adds.slice(0, 20)});
})()
""".replace("__MOST__", str(MAX_FIELDS)).replace("__CHOSEN__", _CHOSEN).replace("__TICK__", CURRENT_BOX_WORDS + "|" + FLUENT_WORDS) \
    .replace("__NEVER_TICK__", NEVER_TICK_WORDS).strip()

FILL = r"""
(function (items, url, typed) {
  __CHOSEN__
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
      if (chosen(el)) { skipped.push(item.n); return; }
      var want = norm(item.value), pick = -1;
      for (var k = 0; k < el.options.length; k++) {
        if (norm(el.options[k].text) === want || norm(el.options[k].value) === want) { pick = k; break; }
      }
      if (pick < 0) { skipped.push(item.n); return; }
      el.selectedIndex = pick;
    } else {
      if (String(el.value || '').trim() !== '') { skipped.push(item.n); return; }
      var proto = el.tagName === 'TEXTAREA' ? view.HTMLTextAreaElement.prototype : view.HTMLInputElement.prototype, put = false;
      if (typed) {              // the way typing arrives: some pages believe nothing else
        el.focus();
        try { put = el.ownerDocument.execCommand('insertText', false, item.value) && String(el.value || '') !== ''; } catch (e) { put = false; }
        if (!put) {             // the page is not in front: the same events typing makes, made by hand
          Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, item.value);
          el.dispatchEvent(new view.InputEvent('input', {bubbles: true, inputType: 'insertText', data: item.value}));
          put = true;
        }
      } else Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, item.value);
    }
    if (!(typed && el.tagName !== 'SELECT')) tell(el, 'input');
    tell(el, 'change');
    el.style.outline = '2px solid ' + (item.check ? '#f59e0b' : '#22c55e');
    el.style.outlineOffset = '1px';
    done.push(item.n);
  });
  return JSON.stringify({done: done, skipped: skipped});
})(__ITEMS__, __URL__, __TYPED__)
""".replace("__CHOSEN__", _CHOSEN).strip()

# A file goes to the page in pieces (a request to the browser has a size limit), then the pieces are made into the file the
# field is given, the way a file chosen by hand arrives. Only a file field that holds nothing is given one.
PUT = r"""
(function (key, part, url) { if (location.href !== url) return 'moved'; window[key] = (window[key] || '') + part; return String(window[key].length); })(__KEY__, __PART__, __URL__)
""".strip()

ATTACH = r"""
(function (n, key, name, kind, url) {
  var MARK = 'data-jobhelper', data = window[key] || '', found = null;
  try { delete window[key]; } catch (e) { window[key] = ''; }
  if (location.href !== url) return JSON.stringify({moved: true});
  function walk(root) {
    var all = root.querySelectorAll('*');
    for (var i = 0; i < all.length && !found; i++) {
      var el = all[i];
      if (el.shadowRoot) walk(el.shadowRoot);
      if (el.tagName === 'IFRAME') {
        var inner = null;
        try { inner = el.contentDocument; } catch (e) { inner = null; }
        if (inner && inner.body) walk(inner);
        continue;
      }
      if (el.getAttribute(MARK) === String(n)) found = el;
    }
  }
  walk(document);
  if (!found || found.tagName !== 'INPUT' || String(found.type).toLowerCase() !== 'file' || found.disabled) return JSON.stringify({ok: false, why: 'gone'});
  if (found.files && found.files.length) return JSON.stringify({ok: false, why: 'has'});
  try {
    var view = found.ownerDocument.defaultView, raw = atob(data), bytes = new view.Uint8Array(raw.length);
    for (var k = 0; k < raw.length; k++) bytes[k] = raw.charCodeAt(k);
    var box = new view.DataTransfer();
    box.items.add(new view.File([bytes], name, {type: kind, lastModified: Date.now()}));
    found.files = box.files;
  } catch (e) { return JSON.stringify({ok: false, why: 'refused'}); }
  found.dispatchEvent(new (found.ownerDocument.defaultView.Event)('input', {bubbles: true}));
  found.dispatchEvent(new (found.ownerDocument.defaultView.Event)('change', {bubbles: true}));
  var has = found.files && found.files.length === 1 ? found.files[0].size : -1;
  return JSON.stringify({ok: has >= 0, size: has});
})(__N__, __KEY__, __NAME__, __KIND__, __URL__)
""".strip()

EMPTY = r"""
(function (wanted, url) {
  __CHOSEN__
  if (location.href !== url) return JSON.stringify({moved: true});
  var MARK = 'data-jobhelper', empty = [];
  function walk(root) {
    var all = root.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (el.shadowRoot) walk(el.shadowRoot);
      if (el.tagName === 'IFRAME') { var inner = null; try { inner = el.contentDocument; } catch (e) { inner = null; } if (inner && inner.body) walk(inner); continue; }
      var mark = Number(el.getAttribute(MARK));
      if (!mark || wanted.indexOf(mark) < 0) continue;
      if (el.tagName === 'SELECT' ? !chosen(el) : String(el.value || '').trim() === '') empty.push(mark);
    }
  }
  walk(document);
  return JSON.stringify({empty: empty});
})(__WANTED__, __URL__)
""".replace("__CHOSEN__", _CHOSEN).strip()


CHOOSE = r"""
(function (action, n, arg, url) {
  if (location.href !== url) return JSON.stringify({moved: true});
  var MARK = 'data-jobhelper', OPT = 'data-jobhelper-opt', ADD = 'data-jobhelper-add', target = null, entries = [], marked = {}, adders = {};
  function shown(el) {
    var r = el.getBoundingClientRect(), s = el.ownerDocument.defaultView.getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
  }
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
      if (el.getAttribute(MARK) === String(n)) target = el;
      if (el.getAttribute(OPT)) marked[el.getAttribute(OPT)] = el;
      if (el.getAttribute(ADD)) adders[el.getAttribute(ADD)] = el;
      if (el.getAttribute('role') === 'option' && shown(el)) entries.push(el);
    }
  }
  // The only things ever pressed: what opens a menu, an entry of a menu, a radio button. Never a button that sends.
  function may(el) {
    if (!el || el.disabled || el.type === 'submit' || el.closest('[type=submit]')) return false;
    var role = el.getAttribute('role'), opens = role === 'combobox' || el.getAttribute('aria-haspopup') === 'listbox' || !!el.getAttribute('aria-autocomplete');
    if (el.tagName === 'INPUT') return el.type === 'radio' || opens;
    return role === 'option' || opens;
  }
  function press(el) {
    var view = el.ownerDocument.defaultView;
    ['mousedown', 'mouseup', 'click'].forEach(function (name) {
      el.dispatchEvent(new view.MouseEvent(name, {bubbles: true, cancelable: true, view: view}));
    });
  }
  function mark(el) { el.style.outline = '2px solid #f59e0b'; el.style.outlineOffset = '1px'; }
  walk(document);
  if (action === 'add') {
    // A button that adds an empty row for another job or degree, and nothing else: its words are read again here.
    var more = adders[String(arg)], words = more ? String(more.innerText || more.textContent || '').replace(/\s+/g, ' ').trim() : '';
    if (!more || more.disabled || more.type === 'submit' || more.closest('[type=submit]') || !/^\+?\s*add\b/i.test(words)
        || /apply|submit|send|next|continue|save|finish|upload|file|attach/i.test(words)) return JSON.stringify({ok: false});
    press(more);
    return JSON.stringify({ok: true});
  }
  if (action === 'tick') {
    // One kind of tick box only: "I currently work here". Its words are read again here; a box that agrees to anything is refused.
    var box = target, label = box && box.labels && box.labels.length ? String(box.labels[0].innerText || box.labels[0].textContent || '') : (box ? String(box.getAttribute('aria-label') || '') : '');
    label = label.replace(/\s+/g, ' ').trim().slice(0, 120);       // read as READ reads it: one line, never a page of spaces
    if (!box || box.tagName !== 'INPUT' || box.type !== 'checkbox' || box.disabled
        || !/__TICK__/i.test(label) || /__NEVER_TICK__/i.test(label)) return JSON.stringify({ok: false});
    if (!box.checked) press(box);
    if (box.checked) mark(box.labels && box.labels.length ? box.labels[0] : box);
    return JSON.stringify({ok: box.checked});
  }
  if (action === 'radio') {
    var radio = marked[n + ':' + arg];
    if (!may(radio) || radio.type !== 'radio') return JSON.stringify({ok: false});
    if (!radio.checked) press(radio);
    if (radio.checked) mark(radio.labels && radio.labels.length ? radio.labels[0] : radio);
    return JSON.stringify({ok: radio.checked});
  }
  if (action === 'pick') {
    var entry = marked['m' + arg];
    if (!may(entry) || entry.getAttribute('role') !== 'option') return JSON.stringify({ok: false});
    press(entry);
    if (target) mark(target);
    return JSON.stringify({ok: true});
  }
  if (!may(target)) return JSON.stringify({ok: false});
  if (action === 'open') {
    if (target.tagName === 'INPUT') {
      target.focus();
      // A window that is not in front gets no word that the box was entered, and many lists open only on that word: it is said here.
      var seen = target.ownerDocument.defaultView;
      target.dispatchEvent(new seen.FocusEvent('focus', {bubbles: false}));
      target.dispatchEvent(new seen.FocusEvent('focusin', {bubbles: true}));
      press(target);
      if (arg) {
        var view = target.ownerDocument.defaultView;
        Object.getOwnPropertyDescriptor(view.HTMLInputElement.prototype, 'value').set.call(target, arg);
        target.dispatchEvent(new view.Event('input', {bubbles: true}));
      }
    } else press(target);
    return JSON.stringify({ok: true});
  }
  if (action === 'key') {                        // the other way a list opens: the arrow-down key, in the box that opens it
    var down = {key: 'ArrowDown', code: 'ArrowDown', keyCode: 40, which: 40, bubbles: true, cancelable: true}, win = target.ownerDocument.defaultView;
    target.dispatchEvent(new win.KeyboardEvent('keydown', down));
    target.dispatchEvent(new win.KeyboardEvent('keyup', down));
    return JSON.stringify({ok: true});
  }
  if (action === 'options') {
    var own = [], ids = String(target.getAttribute('aria-controls') || target.getAttribute('aria-owns') || '').split(/\s+/).filter(Boolean);
    ids.forEach(function (id) {
      var box = target.ownerDocument.getElementById(id);
      if (box) own = own.concat(Array.prototype.slice.call(box.querySelectorAll('[role=option]')).filter(shown));
    });
    var list = (own.length ? own : entries).slice(0, 300);
    list.forEach(function (el, k) { el.setAttribute(OPT, 'm' + k); });
    return JSON.stringify({options: list.map(function (el) { return String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80); })});
  }
  if (action === 'close') {
    var view2 = target.ownerDocument.defaultView, key = {key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true, cancelable: true};
    target.dispatchEvent(new view2.KeyboardEvent('keydown', key));
    target.dispatchEvent(new view2.KeyboardEvent('keyup', key));
    if (target.tagName === 'INPUT' && String(target.value || '') !== '' && arg) {
      Object.getOwnPropertyDescriptor(view2.HTMLInputElement.prototype, 'value').set.call(target, '');
      target.dispatchEvent(new view2.Event('input', {bubbles: true}));
    }
    if (target.blur) target.blur();
    return JSON.stringify({ok: true});
  }
  return JSON.stringify({ok: false});
})(__ACTION__, __N__, __ARG__, __URL__)
""".replace("__TICK__", CURRENT_BOX_WORDS + "|" + FLUENT_WORDS).replace("__NEVER_TICK__", NEVER_TICK_WORDS).strip()


def choose_script(action: str, n: int, arg: Any, url: str) -> str:
    """The CHOOSE script for one step with a menu or a radio button: "open" (arg: text to type, or ''),
    "options", "pick" (arg: the entry's number), "close" (arg: true to clear typed text), "radio" (arg: the button's number), "add" (arg: the number of a button
    that adds a row for another job or degree; n is not used)."""
    assert action in ("open", "key", "options", "pick", "close", "radio", "add", "tick")
    return with_values(CHOOSE, action=action, n=int(n), arg=arg, url=str(url))


def choose_answer(text: str) -> dict[str, Any]:
    data = page_reply(text)
    if data is None:
        return {"ok": False, "moved": False, "options": []}
    options = data.get("options") if isinstance(data.get("options"), list) else []
    return {"ok": bool(data.get("ok")), "moved": bool(data.get("moved")), "options": [" ".join(str(o).split())[:80] for o in options[:300]]}


VALUES = r"""
(function (wanted, url) {
  if (location.href !== url) return JSON.stringify({moved: true});
  var MARK = 'data-jobhelper', out = {};
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
      if (!mark || wanted.indexOf(Number(mark)) < 0 || el.type === 'password' || el.type === 'file') continue;
      if (el.tagName === 'SELECT') out[mark] = el.selectedIndex >= 0 ? String(el.options[el.selectedIndex].text).replace(/\s+/g, ' ').trim() : '';
      else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') out[mark] = String(el.value || '').slice(0, 3000);
    }
  }
  walk(document);
  return JSON.stringify({values: out});
})(__WANTED__, __URL__)
""".strip()

WATCH = r"""
(function () {
  __CHOSEN__
  var names = [], empty = 0;
  function walk(root) {
    var all = root.querySelectorAll('input, textarea, select, iframe, *');
    for (var i = 0; i < all.length && names.length < 400; i++) {
      var el = all[i];
      if (el.shadowRoot) walk(el.shadowRoot);
      if (el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA' && el.tagName !== 'SELECT') continue;
      var type = String(el.getAttribute('type') || '').toLowerCase();
      if (type === 'hidden' || type === 'submit' || type === 'button' || type === 'password' || type === 'file' || type === 'checkbox' || type === 'radio') continue;
      var r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      names.push(el.name || el.id || el.tagName);
      if (el.tagName === 'SELECT' ? !chosen(el) : String(el.value || '').trim() === '') empty++;
    }
  }
  walk(document);
  return JSON.stringify({url: location.href, fields: names.length, first: names.slice(0, 12).join('|').slice(0, 400), empty: empty});
})()
""".replace("__CHOSEN__", _CHOSEN).strip()


REVIEW = r"""
(function () {
  __CHOSEN__
  var out = [], seen = {};
  function clean(t) { return String(t || '').replace(/\s+/g, ' ').trim(); }
  function text(el) { return el ? clean(el.innerText || el.textContent) : ''; }
  function name(el) {
    if (el.labels && el.labels.length && text(el.labels[0])) return text(el.labels[0]);
    if (el.getAttribute('aria-label')) return clean(el.getAttribute('aria-label'));
    var node = el;
    for (var i = 0; i < 3; i++) { node = node.parentElement; if (!node) break; var t = beside(node, el); if (t.length > 160) break; if (t) return t; }
    return clean(el.getAttribute('placeholder') || el.name || el.id);
  }
  function beside(node, el) {                    // the words around a field without any list's own entries (250 countries are not a name)
    var walker = el.ownerDocument.createTreeWalker(node, 4, null), out = '', t;
    while ((t = walker.nextNode()) && out.length < 400) {
      var p = t.parentElement;
      if (!p || el.contains(t) || /^(OPTION|OPTGROUP|SELECT|SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(p.tagName) || p.closest('button') || !p.getClientRects().length) continue;
      out += ' ' + t.nodeValue;
    }
    return clean(out);
  }
  function walk(root) {
    var all = root.querySelectorAll('*');
    for (var i = 0; i < all.length && out.length < 120; i++) {
      var el = all[i], tag = el.tagName;
      if (el.shadowRoot) walk(el.shadowRoot);
      if (tag === 'IFRAME') { var inner = null; try { inner = el.contentDocument; } catch (e) { inner = null; } if (inner && inner.body) walk(inner); continue; }
      if (tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT') continue;
      var type = tag === 'INPUT' ? String(el.getAttribute('type') || 'text').toLowerCase() : tag.toLowerCase();
      if (type === 'hidden' || type === 'submit' || type === 'button' || type === 'reset' || type === 'image' || type === 'password' || type === 'file' || type === 'checkbox') continue;
      var r = el.getBoundingClientRect();
      if (type === 'radio') {
        if (!el.name) continue;
        var set = el.closest('fieldset'), asked = set && set.querySelector('legend') ? text(set.querySelector('legend')) : el.name;
        if (seen[el.name] === undefined) { seen[el.name] = out.length; out.push({label: asked.slice(0, 200), value: '', required: !!el.required, kind: 'radio'}); }
        if (el.checked) out[seen[el.name]].value = (el.labels && el.labels.length ? text(el.labels[0]) : clean(el.value)).slice(0, 200);
        continue;
      }
      if (r.width < 2 || r.height < 2) continue;
      var value = tag === 'SELECT' ? (chosen(el) ? clean(el.options[el.selectedIndex].text) : '') : String(el.value || '');
      out.push({label: name(el).slice(0, 200), value: value.slice(0, 3000), required: !!(el.required || el.getAttribute('aria-required') === 'true'), kind: type});
    }
  }
  walk(document);
  return JSON.stringify({url: location.href, title: clean(document.title).slice(0, 300), fields: out});
})()
""".replace("__CHOSEN__", _CHOSEN).strip()


def review_answer(text: str) -> dict[str, Any]:
    """What the REVIEW script gave back, checked. A field whose name marks it as personal or as payment keeps
    only whether it is filled in: its value goes no further."""
    data = page_reply(text, FORM_REFUSED)
    if not isinstance(data.get("fields"), list):
        raise ValueError(FORM_REFUSED)
    fields = []
    for raw in data["fields"][:120]:
        if not isinstance(raw, dict):
            continue
        label = " ".join(str(raw.get("label") or "").split())[:200]
        value = str(raw.get("value") or "")[:3000]
        private = _named_private({"label": label})
        fields.append({"label": label or "A field with no name", "value": "" if private else value, "filled": bool(value.strip()),
                       "required": bool(raw.get("required")), "private": private, "kind": str(raw.get("kind") or "text")[:20]})
    return {"url": str(data.get("url") or ""), "title": str(data.get("title") or "")[:300], "fields": fields}


PAGE = r"""
(function () {
  function clean(t) { return String(t || '').replace(/[ \t\u00a0]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim(); }
  var main = document.querySelector('main, article, [role=main]') || document.body;
  var text = clean(main ? main.innerText : '');
  if (text.length < 400 && document.body) text = clean(document.body.innerText);
  // Most job pages also state the job in a form meant for search engines: read there, nothing has to be guessed.
  var stated = null, blocks = document.querySelectorAll('script[type="application/ld+json"]');
  function one(v) { return Array.isArray(v) ? v[0] : v; }
  function find(node) {
    if (!node || typeof node !== 'object' || stated) return;
    if (Array.isArray(node)) { node.forEach(find); return; }
    var kind = node['@type'];
    if (kind === 'JobPosting' || (Array.isArray(kind) && kind.indexOf('JobPosting') >= 0)) {
      var org = one(node.hiringOrganization) || {}, place = one(node.jobLocation) || {}, addr = one(place.address) || {};
      stated = {title: clean(node.title).slice(0, 160), company: clean(typeof org === 'string' ? org : org.name).slice(0, 120),
                location: clean([addr.addressLocality, addr.addressCountry && (addr.addressCountry.name || addr.addressCountry)].filter(function (x) { return typeof x === 'string' && x; }).join(', ')).slice(0, 120)};
      return;
    }
    if (node['@graph']) find(node['@graph']);
  }
  for (var i = 0; i < blocks.length && !stated; i++) { try { find(JSON.parse(blocks[i].textContent)); } catch (e) {} }
  return JSON.stringify({url: location.href, title: clean(document.title).slice(0, 300), text: text.slice(0, 12000), stated: stated});
})()
""".strip()


def page_answer(text: str) -> dict[str, str]:
    """What the PAGE script gave back: the address, the title and the words of the page, as plain text."""
    data = page_reply(text, "The page did not answer. Reload it and ask me again.")
    stated = data.get("stated") if isinstance(data.get("stated"), dict) else {}
    return {"url": str(data.get("url") or "")[:2000], "title": " ".join(str(data.get("title") or "").split())[:300],
            "text": str(data.get("text") or "")[:12000],
            "stated": {key: " ".join(str(stated.get(key) or "").split())[:160] for key in ("title", "company", "location")}}


def values_script(numbers: list[int], url: str) -> str:
    """The VALUES script: what the fields with these numbers hold now. Asked only for fields the assistant itself filled in."""
    return with_values(VALUES, wanted=[int(n) for n in numbers], url=str(url))


def values_answer(text: str) -> dict[int, str]:
    data = page_reply(text) or {}
    values = data.get("values")
    return {int(k): str(v)[:3000] for k, v in values.items() if str(k).isdigit()} if isinstance(values, dict) else {}


def watch_answer(text: str) -> dict[str, Any]:
    """Where the form stands: {url, sign, empty}. `sign` changes when the page shows other fields."""
    data = page_reply(text)
    if data is None:
        return {"url": "", "sign": "", "empty": 0}
    count = data.get("fields") if isinstance(data.get("fields"), int) else 0
    return {"url": str(data.get("url") or "")[:500], "sign": f"{count}:{str(data.get('first') or '')[:400]}",
            "empty": data.get("empty") if isinstance(data.get("empty"), int) else 0}


def fill_script(items: list[dict[str, Any]], url: str, typed: bool = False) -> str:
    """The FILL script for these values. They travel as data (JSON), never as code. `typed` writes them the
    way typing arrives, for a page that threw away what was written the plain way."""
    data = [{"n": int(i["n"]), "value": str(i["value"]), "check": bool(i.get("check"))} for i in items]
    return with_values(FILL, items=data, url=str(url), typed=bool(typed))


PIECE = 150_000                 # characters of a file sent to the page in one request
MAX_FILE = 4 * 1024 * 1024      # a larger file is left to the person
FILE_TYPES = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              ".doc": "application/msword", ".txt": "text/plain", ".rtf": "application/rtf", ".odt": "application/vnd.oasis.opendocument.text"}


def put_scripts(key: str, content: bytes, url: str) -> list[str]:
    """The PUT scripts that carry a file to the page, piece by piece (as text; it is data, never code). A tab in front
    that is no longer the form at `url` gets nothing and answers "moved"."""
    import base64
    text = base64.b64encode(content).decode("ascii")
    return [with_values(PUT, key=str(key), part=text[i:i + PIECE], url=str(url)) for i in range(0, len(text), PIECE)]



def attach_script(n: int, key: str, name: str, url: str) -> str:
    """The ATTACH script: give the file field with this number the file that was carried over under `key`."""
    kind = FILE_TYPES.get(os.path.splitext(str(name))[1].lower(), "application/octet-stream")
    return with_values(ATTACH, n=int(n), key=str(key), name=str(name), kind=kind, url=str(url))


def attach_answer(text: str) -> dict[str, Any]:
    data = page_reply(text)
    if data is None:
        return {"ok": False, "moved": False, "why": "refused", "size": -1}
    return {"ok": data.get("ok") is True, "moved": data.get("moved") is True, "why": str(data.get("why") or ""),
            "size": data.get("size") if isinstance(data.get("size"), int) else -1}


def takes(accept: str, name: str) -> bool:
    """Whether a file field that says it accepts `accept` (".pdf,.docx", "application/pdf", "image/*") takes this file.
    A field that says nothing takes anything."""
    wanted = [w.strip().lower() for w in str(accept or "").split(",") if w.strip()]
    if not wanted:
        return True
    ending = os.path.splitext(str(name))[1].lower()
    kind = FILE_TYPES.get(ending, "")
    return any(w == ending or w == kind or (w.endswith("/*") and kind.startswith(w[:-1])) or w == "*/*" for w in wanted)


_FILE_CV = re.compile(r"resum|\bcv\b|curriculum|vitae|životopis|zivotopis|lebenslauf")
_FILE_LETTER = re.compile(r"cover|motivation|motivační|motivacni|průvodní|pruvodni|\bletter\b|anschreiben")
_FILE_OTHER = re.compile(r"other|additional|further|supporting|attachment|document|certificate|příloh|priloh")
_FILE_NOT = re.compile(r"photo|picture|avatar|portrait|passport|\bid\b|identity|visa|permit|transcript|portfolio|video|signature")


def file_kind(field: dict[str, Any]) -> str:
    """Which file a file field asks for: "cv", "letter", "other" (a place for further documents), or '' when it is not said
    or it is something only you have (a photo, a passport, a transcript)."""
    words = _words(field)
    if _FILE_NOT.search(words):
        return ""
    if _FILE_CV.search(words):
        return "cv"
    if _FILE_LETTER.search(words):
        return "letter"
    return "other" if _FILE_OTHER.search(words) else ""


def empty_script(numbers: list[int], url: str) -> str:
    """The EMPTY script: which of these fields hold nothing now. It says only that, never what a field holds."""
    return with_values(EMPTY, wanted=[int(n) for n in numbers], url=str(url))


def empty_answer(text: str) -> list[int]:
    empty = (page_reply(text) or {}).get("empty")
    return [n for n in empty if isinstance(n, int)] if isinstance(empty, list) else []


# ── what a field is ─────────────────────────────────────────────────────────
PASSWORD = "A password is yours to type."
FILE = "I cannot tell which of your files this field wants. Attach it yourself."
FILE_BUTTON = "This page takes files only through its own buttons, so I cannot attach them. Press its button and choose each file yourself."
FILE_NO_JOB = "Choose the job this form is for, and I will attach its CV and its letter."
FILE_NO_CV = "I found no CV file to attach. Attach it yourself."
FILE_NO_LETTER = "There is no letter file for this job. Attach your own."
FILE_OTHER = "The letter has a field of its own on this form. Further documents (certificates, diplomas) are yours to add."
FILE_FORMAT = "The field takes {accept}; the file I have is {name}. Attach it yourself."
FILE_BIG = "The file {name} is larger than 4 MB. Attach it yourself."
FILE_REFUSED = "The page did not take the file. Attach it yourself."
FILE_CHECK = "Look that the page shows the file."
FILE_MASTER = "This is your own CV, not one adapted to this job. " + FILE_CHECK
FILE_REASONS = (FILE, FILE_BUTTON, FILE_NO_JOB, FILE_NO_CV, FILE_NO_LETTER, FILE_OTHER, FILE_BIG, FILE_REFUSED)
PRIVATE = "Personal or payment information: fill it in yourself."
CHOICE = "Choose it yourself."
DATE = "Pick the date yourself."
UNKNOWN = "I did not recognise this field."
NO_DETAIL = "Not in My details yet: add your {what} there and ask me again."
NO_CURRENT_JOB = "None of your jobs in My details goes on now. Mark the job you have now there, or fill this in yourself."
TOO_LONG = "The field takes {most} characters and this is {size}. Shorten it and paste it yourself."
NO_COUNTRY = "The list has no entry for {country}. Choose it yourself."
NO_JOB = "An open question: choose the job this form is for, and I will draft the answer from your CV."
NO_LETTER = "No letter written by the app for this job. Paste your own."
TOO_MANY = f"More than {form_answers.MAX_QUESTIONS} open questions: ask me again after these are done."

_PRIVATE = re.compile(r"passw|captcha|card ?number|credit card|\bcvv\b|\bcvc\b|\biban\b|\bbank|account number|social security|\bssn\b"
                      r"|signature|sign electronically|\bsign (?:here|below)\b|\bsigned\b|(?:name|initials) to confirm|\bconfirm (?:that|you)\b|to certify|to agree|i declare|signatory|initials"
                      r"|national id|id number|passport|birth|\bdob\b|\bage\b|gender|\bsex\b|pronoun|\brace\b|ethnic|disab|veteran"
                      r"|religio|orientation|marital|criminal|convict|health"
                      # the card's own name and date, citizenship and tax; the same in Czech and German (audit before 1.2.0)
                      r"|name on (?:the )?card|card ?holder|expir(?:y|ation)? ?(?:date|month|year)|valid (?:thru|through|until)"
                      r"|citizenship|nationality"
                      r"|\btax ?(?:id|number|no\b|code|identif)|tax ?payer|\bvat ?(?:id|number|no\b)|\bust.?id"   # not "before tax"
                      r"|security code|\bcvv2\b|\bexp\.? ?date\b|\bnaissance"
                      r"|narozen|pohlav|p[řr][íi]slu[šs]nost|rodn[ée] [čc][íi]slo|ob[čc]ansk|ob[čc]anstv|n[áa]rodnost|\bv[ěe]k\b"
                      r"|da[ňn]ov[ée] identifika|\bdi[čc]\b|rodinn[ýy] stav|[čc][íi]slo (?:karty|[úu][čc]tu|op\b|pasu|pas\b)|platnost karty"
                      r"|geburt|geboren|geschlecht|staatsangeh|staatsb(?:[üu]|ue)rger|nationalit|steuer(?:liche)? ?(?:nummer|nr\b|-?id|ident)"
                      r"|ausweis|reisepass|sozialversicherung|rentenversicherung|\bsv ?nummer|kreditkart|kartennummer|karteninhaber"
                      r"|ablaufdatum|kontonummer|\bkonto ?nr\b|\balter\b|familienstand|national insurance")
# what a page's autocomplete names as payment or personal: never filled, whatever the label says. One token at a time:
# autocomplete may start with a section or "billing" ("section-a cc-csc", "billing cc-number").
_PRIVATE_AUTO = re.compile(r"cc-.*|bday.*|sex|transaction-.*")
# a question in a list or a set of radios that gives consent in your name: yours to answer, never the model's
# ("Are you authorized to work in …?" is a question about you, not consent: "authorize" alone is)
# ("Do you agree to relocate?" and "Experience with GDPR compliance" are questions about you, not consent)
_CONSENT = re.compile(r"\bi (?:hereby )?agree\b|\bagree (?:to|with) (?:the |our |these |your )?(?:terms|conditions|polic|privacy|processing"
                      r"|storage|use of|data)|consent|terms (?:and|&) conditions|terms of (?:use|service)|privacy (?:polic|notice|statement)"
                      r"|personal data"
                      r"|\baccept\b[^?]{0,40}\b(?:terms|polic|conditions|agreement|statement)|\backnowledg|\bauthori[sz]e\b"
                      r"|\bcertify\b|\bi (?:hereby )?(?:confirm|declare)\b|background check"
                      r"|souhlas|zpracov[áa]n[íi] osobn|prohla[šs]uji|potvrzuji|beru na v[ěe]dom[íi]|obchodn[íi] podm[íi]nky"
                      r"|einwillig|zustimm|einverstanden|datenschutz|best[äa]tige|versichere|akzeptiere|nutzungsbedingungen|\bagb\b",
                      re.IGNORECASE)
_NOT_MINE = re.compile(r"company|employer|organi[sz]ation|school|universit|college|referr|referee|reference|emergency|manager|recruiter"
                       r"|supervisor|\btitle\b|position|\brole\b|degree|skill|user ?name|login|nick")
# what forms ask again and again; when it is not in My details, an open question is drafted instead
SOFT = ("employer", "job_title", "school", "degree", "study_field", "notice_period", "salary", "start")
# asked once per job or per degree: the first such field gets the first entry of the list, the next one the second
LISTED = {"lang_name": ("languages", "language"),
          "employer": ("experience", "employer"), "job_title": ("experience", "title"),
          "job_location": ("experience", "location"), "job_description": ("experience", "description"),
          "school": ("education", "school"), "degree": ("education", "degree"), "study_field": ("education", "field")}
# Languages are asked row by row too: "Language", then how well ("Comprehension", "Overall", "Reading" ...), sometimes a "fluent" box.
_FLUENT = re.compile(FLUENT_WORDS)
_CURRENT_BOX = re.compile(CURRENT_BOX_WORDS, re.IGNORECASE)
_NEVER_TICK = re.compile(NEVER_TICK_WORDS, re.IGNORECASE)
_LANG_NAME = re.compile(r"(?:language|jazyk|sprache)(?: \d+)?(?: name)?")
_LANG_LEVEL = re.compile(r"^(?:comprehension|overall|reading|writing|speaking|listening|spoken|written|proficiency|level|fluency|úroveň)\b|"
                         r"\b(?:language )?(?:proficiency|level)$")
LANG_NEAR = 8                  # a language's row is longer than a job's: name, a box, and up to six levels
NO_LANGUAGE = "The list has no entry for {language}. Choose it yourself."
NO_LEVEL = "My details does not say how well you speak {language}. Add the level there, or choose it yourself."
NO_LEVEL_OPTION = "I could not tell which entry means {level}. Choose it yourself."
MORE_LANGUAGES = "You listed {have} in My details, and this is one more. Add it there, or leave this one out."
LEVEL_CHECK = "Chosen from the level you gave in My details ({level}): check it."
# what a form may call each level, the nearest first: when a form has no "Native", "Fluent" is the next best, and so on down
_LEVEL_WORDS = {"Native": ("native", "mother tongue", "bilingual", "fluent", "proficient", "c2", "advanced"),
                "Fluent": ("fluent", "full professional", "proficient", "c2", "c1", "advanced"),
                "Advanced": ("advanced", "professional working", "upper intermediate", "c1", "b2"),
                "Intermediate": ("intermediate", "conversational", "limited working", "b1", "b2"),
                "Basic": ("basic", "beginner", "elementary", "a2", "a1")}


def language_option(options: list[str], language: str) -> str:
    """The entry of a list that is this language ("Ukrainian", "Ukrainian (Українська)"), or ''."""
    want = " ".join(str(language or "").lower().split())
    if not want:
        return ""
    for option in options:
        if " ".join(str(option).lower().split()) == want:
            return str(option)
    starts = [str(o) for o in options if re.match(rf"{re.escape(want)}\b", " ".join(str(o).lower().split()))]
    return starts[0] if len(starts) == 1 else ""


def level_option(options: list[str], level: str) -> str:
    """The entry of a list that says how well you speak a language, for one of details.LEVELS, or ''.
    The form's own words are tried from the nearest meaning to the next best; among entries with the word, the plainest
    one is taken ("Intermediate" before "Upper Intermediate")."""
    for word in _LEVEL_WORDS.get(str(level), ()):
        found = [str(o) for o in options if re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", re.sub(r"[-_/]", " ", str(o).lower()))]
        if word == "intermediate":
            found = [o for o in found if not re.search(r"upper|pre", o.lower())] or found
        if found:
            return min(found, key=len)
    return ""


# inside a job's row a form also asks where the job was and what you did there: the job's own, not yours and not an open question
_ROW_TEXT = re.compile(r"descri(?:ption|be)|responsibilit|duties|what (?:did you|you did)|achievement|accomplishment|tasks?\b|summary of|"
                       r"náplň práce|popis")
ROW_NEAR = 5                   # a field this close after a job's own field still belongs to that job
ROW_PLACE = "This asks where the school was, which My details does not hold. Fill it in yourself."
ROW_WORDS = "This asks about your studies in your own words. Write it yourself."
MORE_ROWS = "You listed {have} in My details, and this is one more. Add it there, or type it."
_ROW_START = re.compile(r"\bstart(?:ed)?\b|\bfrom\b|\bbegan\b|date from|od\b")
_ROW_END = re.compile(r"\bend(?:ed)?\b|\bto\b|\buntil\b|\bfinish|\bleft\b|date to|graduat")
_NOT_A_ROW_DATE = re.compile(r"earliest|availab|can you|notice|birth|expected|preferred|interview|deadline|today|valid|expir|issue")
# when you can start: asked as "earliest start date", "available from", "when can you start" (a plain "start date" may be a job's)
_AVAILABLE = re.compile(r"earliest (?:possible )?(?:start|date)|availab|when (?:can|could|would) you (?:start|join|begin)|(?:possible|desired|preferred|expected|proposed) start"
                        r"|date of (?:joining|entry)|joining date|can you start|start working|nástup")
_LONE_START = re.compile(r"\bstart(?:ing)? date\b|\bdate of start\b")
START_UNKNOWN = "Tell me when you can start in About you (under Options), and ask me again. Or pick the date yourself."
START_NO_DATE = "I cannot turn “{text}” (About you) into a date. Pick the date yourself."
START_CHECK = "Worked out from “{text}” in About you: check the date."
_MONTHS = {name.lower(): n for n, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): n for n, name in enumerate(calendar.month_abbr) if name})
_COUNT = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def start_day(text: str, today: date | None = None) -> tuple[date | None, bool]:
    """The day meant by what you wrote about when you can start: (the day, whether it was worked out and needs a look).
    "2026-11-01", "1.11.2026", "1 November 2026" are taken as written; "November 2026" is its first day; "immediately" is
    today; "one month", "2 weeks' notice" count from today. Anything else, and a day that has passed, gives (None, False)."""
    today = today or date.today()
    low = " ".join(str(text or "").lower().replace(",", " ").split())
    found, worked = None, False
    try:
        m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", low)
        if m:
            found = date(int(m[1]), int(m[2]), int(m[3]))
        if not found:
            m = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", low)
            if m:
                found = date(int(m[3]), int(m[2]), int(m[1]))
        if not found:
            names = "|".join(sorted(_MONTHS, key=len, reverse=True))
            m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)? (?:of )?({names})\.? (\d{{4}})\b", low) or None
            if m:
                found = date(int(m[3]), _MONTHS[m[2]], int(m[1]))
            else:
                m = re.search(rf"\b({names})\.? (\d{{1,2}})(?:st|nd|rd|th)? (\d{{4}})\b", low)
                if m:
                    found = date(int(m[3]), _MONTHS[m[1]], int(m[2]))
                else:
                    m = re.search(rf"\b({names})\.? (\d{{4}})\b", low)
                    if m:
                        found, worked = date(int(m[2]), _MONTHS[m[1]], 1), True
    except ValueError:
        return None, False                          # the 31st of a month that has 30 days
    if not found:
        if re.search(r"immediate|asap|as soon as possible|right away|at once|straight away|\bnow\b|ihned", low):
            found, worked = today, True
        else:
            m = re.search(r"\b(\d{1,2}|" + "|".join(_COUNT) + r")[ -](day|week|month)s?\b", low)
            if m:
                count = int(m[1]) if m[1].isdigit() else _COUNT[m[1]]
                if m[2] == "month":
                    months = today.month - 1 + count
                    year, month = today.year + months // 12, months % 12 + 1
                    found = date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
                else:
                    found = today + timedelta(days=count * (7 if m[2] == "week" else 1))
                worked = True
    if not found or found < today:
        return None, False
    return found, worked


NO_MONTH = "My details has only the year for this. Add the month there, or pick the date yourself."
CHECK_DAY = "The day is not known, so the first of the month was used: check the date."
SKIPPED = "You asked me to leave it out."
THROWN = "The page threw the value away twice. Type this one yourself."
MONTHS = tuple(name.lower() for name in calendar.month_name[1:])


class RowDate:
    """A job's or a degree's date as My details keeps it: "03/2023" (a month and a year) or "2023" (a year only).
    The one reader of that shape for every kind of date field a form has."""

    def __init__(self, when: str) -> None:
        self.text = str(when or "")
        parts = re.split(r"[./\-]", self.text)
        self.year = parts[-1] if self.text else ""
        self.month = int(parts[0]) if len(parts) == 2 and parts[0].isdigit() and 1 <= int(parts[0]) <= 12 else 0

    def __bool__(self) -> bool:
        return bool(self.text)

    @property
    def mm(self) -> str:
        """The month as two digits ('' when only the year is known)."""
        return f"{self.month:02d}" if self.month else ""


def date_option(options: list[str], when: str) -> tuple[str, str]:
    """The entry of a month list or a year list that is this date ("03/2023"): (entry, '') or ('', why not).
    Which of the two the list is shows in its entries: years are four digits."""
    day = RowDate(when)
    if not day:
        return "", ""
    year, month = day.year, day.month
    plain = [" ".join(str(o).lower().split()) for o in options]
    if sum(1 for o in plain if re.fullmatch(r"(?:19|20)\d{2}", o)) >= 3:
        return next((o for o, p in zip(options, plain) if p == year), ""), ""
    if not month:
        return "", NO_MONTH
    names = (MONTHS[month - 1], MONTHS[month - 1][:3], str(month), f"{month:02d}")
    for o, p in zip(options, plain):
        words = [w for w in re.split(r"[^a-z0-9]+", p) if w]
        if p in names or (words and (words[0] in names or words[-1] in names[:2])):
            return o, ""
    return "", ""
_CURRENT = re.compile(r"\b(?:current|present|latest|most recent|last)\b")
_NOW = re.compile(r"\b(?:current|present)\b")                # "current employer": a job that goes on, never an old one
_OR_LAST = re.compile(r"\b(?:most recent|recent|latest|last|previous)\b")      # "current or most recent employer": the newest job
_NOT_THIS_JOB = re.compile(r"appl|desired|interested|preferred|referr|referee|emergency")
# Fields that name one of your details but ask about somebody or something else.
_PERSONAL = ("first_name", "last_name", "full_name", "street", "location", "city", "country", "postcode", "email", "phone")
_OTHER_PERSON = re.compile(r"spouse|partner|\bparents?\b|guardian|\bkin\b|friend|relative|husband|wife|\b(?:father|mother)\b(?! tongue)|contact (?:person|name)"
                           r"|colleague|mentor|co.?worker|relation|sponsor|nominee|recommender|interviewer|hiring|maiden"
                           r"|sibling|brother|sister|child|daughter|\bson\b|dependent|beneficiary|guarantor|co.?applicant|next of|witness")
# Read in the hint and the page's inner names too, so only words that always mean another person ("referral", "partner companies" do not).
_PEOPLE = re.compile(r"\breferr(?:er|ee)s?\b|\breferees?\b|\breferences?\b|\bemergency\b|\bnext of\b|\bmanager\b|\bsupervisor\b"
                     r"|\bspouse\b|\bguardian\b|\bkin\b")
_NAME_OR_PLACE = ("first_name", "last_name", "full_name", "street", "location", "city", "country", "postcode")
_WORKPLACE = re.compile(r"\bwork\b|office|business")      # "Work address": the employer's, not your home
_PAST_PAY = re.compile(r"\b(?:current|present|previous|last|drawn|prior|past)\b")
_YES_NO = re.compile(r"^(?:are|do|can|will|would|have|is) you\b")
_A_PLACE = re.compile(r"address|phone|e ?mail|\bcity\b|\btown\b|country|post ?code|\bzip\b|web ?site|\burl\b|\blink")


def _yours(key: str, words: str, everything: str = "") -> bool:
    """Whether a field that names one of your details asks for your own value: not a referee's phone, a spouse's
    name, the pay you get now, a yes/no question about being available, or an employer's address. `words` is what
    the label says; `everything` adds its hint and the page's inner names, which are read only for a person
    ("Name" with the inner name "referee_name" is the referee's)."""
    if key in _PERSONAL and (_NOT_MINE.search(words) or _OTHER_PERSON.search(words)):
        return False
    if key in _NAME_OR_PLACE and _PEOPLE.search(everything):                # read in the hint and inner names too
        return False
    if key in ("street", "location", "city", "postcode") and _WORKPLACE.search(words):
        return False
    if key in ("employer", "job_title") and (_NOT_THIS_JOB.search(words) or _A_PLACE.search(words)):
        return False                                # "position applied for", "referee's employer", "employer address"
    if key == "salary" and _PAST_PAY.search(words):
        return False                                # "current salary": not the pay you ask for
    return not (key == "start" and _YES_NO.search(words))


_RULES = (("linkedin", re.compile(r"linked ?in")),
          ("github", re.compile(r"git ?hub")),
          ("email", re.compile(r"e ?mail")),
          ("phone", re.compile(r"phone|mobile|\bcell\b|telefon|\btel\b")),
          ("notice_period", re.compile(r"notice period|period of notice|výpovědní")),
          ("start", _AVAILABLE),
          ("salary", re.compile(r"salary|compensation|remuneration|expected pay|pay expectation")),
          ("employer", re.compile(r"(?:current|present|latest|most recent|last) (?:employer|company|organi[sz]ation)|\bemployer\b|^company\b|company ?name")),
          ("job_title", re.compile(r"(?:current|present|latest|most recent|last) (?:job ?)?(?:title|position|role)|\bjob ?title\b|^position\b|^title\b")),
          ("study_field", re.compile(r"field of study|\bmajor\b|area of study|specialisation|specialization|discipline")),
          ("school", re.compile(r"universit|\bschool\b|college|alma mater|institution")),
          ("degree", re.compile(r"\bdegree\b|qualification")),
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
WHAT = {"job_location": "job's place (under your jobs: Where it was)", "job_description": "description of this job (under your jobs: What you did there)",
        "full_name": "name", "location": "city", "employer": "jobs", "job_title": "jobs", "school": "degrees", "degree": "degrees",
        "study_field": "degrees", "salary": "salary", **{key: label.lower() for key, label in details.LABELS.items()}}


def _named_private(field: dict[str, Any]) -> bool:
    """Whether the field's name says it is personal or payment information, read both as written ("DoB", "PassWord")
    and as plain words ("Tax_ID", "Card-number"): a field is private when either reading says so."""
    written = " ".join(str(field.get(k) or "") for k in ("label", "hint", "name", "id")).lower()
    return bool(_PRIVATE.search(written) or _PRIVATE.search(_words(field)))


def _words(field: dict[str, Any]) -> str:
    """What the page calls the field, as plain lower-case words (firstName, first_name -> first name)."""
    parts = unicodedata.normalize("NFC", " ".join(str(field.get(k) or "") for k in ("label", "hint", "name", "id")))   # "č" as one letter
    parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", parts)
    return " ".join(re.sub(r"[_\-.\[\]:()]+", " ", parts).lower().split())


class Field:
    """One field of a form, as the page reports it (the READ script): what it is called, what kind of
    field it is, and what it asks for. It only reads the page's report and never changes it."""

    def __init__(self, raw: dict[str, Any], at: int = 0) -> None:
        self._raw = raw
        self.at = at                                # its place among the fields of the page

    def get(self, key: str, default: Any = None) -> Any:
        """One value of the page's report, as it gave it."""
        return self._raw.get(key, default)

    @property
    def n(self):
        return self._raw["n"]

    @property
    def kind(self) -> str:
        """The kind of field: "text", "select", "radio", "menu" (drawn by the page), "file" …"""
        return str(self._raw.get("type") or "text").lower()

    @property
    def most(self) -> int:
        """How many characters it takes (0 = no limit)."""
        return int(self._raw.get("most") or 0)

    @property
    def options(self) -> list[str]:
        return list(self._raw.get("options") or [])

    @property
    def filled(self) -> bool:
        return bool(self._raw.get("filled"))

    @property
    def combo(self) -> bool:
        """A text box that opens a list as you type."""
        return bool(self._raw.get("combo"))

    @property
    def picked(self) -> bool:
        """Something you pick (a list, a menu, a box, a file) rather than type."""
        return self.kind in ("select", "radio", "menu", "checkbox", "file") or self.combo

    @property
    def words(self) -> str:
        """What the page calls the field, as plain lower-case words."""
        return _words(self._raw)

    @property
    def name(self) -> str:
        """What to call the field when talking to the person."""
        field = self._raw
        for key in ("label", "hint", "name", "id"):
            value = " ".join(str(field.get(key) or "").split())
            if value:
                return value[:120]
        return f"Field {field.get('n', '')}".strip()

    def meaning(self) -> tuple[str, str]:
        """(what it is, why it is left). The first is a key of the details ("email", "full_name",
"location"), "letter", "question", "choice" (something to pick: see form_choices), or ""
when the field is left to the person."""
        field = self._raw
        kind = str(field.get("type") or "text").lower()
        words = _words(field)
        picked = kind in ("select", "radio", "menu") or bool(field.get("combo"))
        if kind == "password":
            return "", PASSWORD
        if kind == "file":
            return "file", ""
        if _named_private(field) or any(_PRIVATE_AUTO.fullmatch(t) for t in str(field.get("auto") or "").lower().split()):
            return "", PRIVATE
        if picked and _CONSENT.search(words):
            return "", CHOICE                           # "Do you agree to the processing of your personal data?": yours alone
        if field.get("part") and kind in ("text", "number", "tel"):
            # one box of a date that is split into a month and a year: the pair's own name says whose date it is
            pair = _words({"label": field.get("group")})
            if not _NOT_A_ROW_DATE.search(pair):
                if _ROW_START.search(pair):
                    return "row_start", ""
                if _ROW_END.search(pair):
                    return "row_end", ""
            return "", DATE
        if kind in ("date", "month") and _AVAILABLE.search(words):
            return "start", ""
        if kind in ("date", "month") or (kind == "text" and re.search(r"\bdates?\b|mm.?yyyy", words)):
            if not _NOT_A_ROW_DATE.search(words):
                if _ROW_START.search(words):
                    return "row_start", ""
                if _ROW_END.search(words):
                    return "row_end", ""
            if kind != "text":
                return "", DATE
        if kind in ("week", "time", "datetime-local"):
            return "", DATE
        if kind in ("range", "color"):
            return "", CHOICE
        auto = (str(field.get("auto") or "").lower().split() or [""])[-1]
        what = _AUTO.get(auto) or _BY_TYPE.get(kind) or ""
        # What the person reads comes first: a field labelled "Location" whose inner name is "schoolLocation-1" is a location.
        # Only a field whose label says nothing is judged by the names the page gives it inside.
        shown = _words({"label": field.get("label"), "hint": field.get("hint")})
        asked = _words({"label": field.get("label")}) or shown or words     # whose value it is: the label decides, not its hint
        for seen in ([shown, words] if shown else [words]):
            if what:
                break
            for key, rule in _RULES:
                if rule.search(seen) and _yours(key, asked, words):
                    what = key
                    break
        if what and not _yours(what, asked, words):
            what = ""                                   # the page says "email", the label says "Referee email"
        has_words = bool(re.search(r"[^\W\d_]{2}", str(field.get("label") or "")))
        if kind == "checkbox":                          # the two kinds of tick box that are reported: "I work here now", "I am fluent in this language"
            said = _words({"label": field.get("label")}).strip(" *") or words
            if _NEVER_TICK.search(said):
                return "", CHOICE
            if _FLUENT.search(said):
                return "fluent_box", ""
            return ("current_box", "") if _CURRENT_BOX.search(said) else ("", CHOICE)
        if _LANG_NAME.fullmatch(_words({"label": field.get("label")}).strip(" *")):
            return "lang_name", ""                      # "Language" in a list of languages: one of yours, row by row
        if kind == "select" and not _NOT_A_ROW_DATE.search(words) and re.search(r"month|year|date|\bfrom\b|\bto\b|start|end", words):
            if _ROW_START.search(words):
                return "row_start", ""
            if _ROW_END.search(words):
                return "row_end", ""
        if picked:
            if kind == "select" and what == "country":
                return "country", ""
            return ("choice", "") if has_words else ("", CHOICE)
        if kind == "textarea" and _LETTER.search(words):
            return "letter", ""
        if what and kind == "textarea" and what not in ("street", "location"):
            what = ""                                   # a big box that mentions "name" or "email" is a question, not a detail
        if kind == "number":
            return ("choice", "") if has_words and what not in ("phone", "postcode") else (("", UNKNOWN) if not what else (what, ""))
        if what:
            return what, ""
        label = str(field.get("label") or "").strip()
        if kind == "textarea" or "?" in label or len(label) >= 20:
            return ("question", "") if has_words else ("", UNKNOWN)
        if has_words and kind in ("text", "search") and not (_NOT_MINE.search(words) or _NOT_THIS_JOB.search(words) or _OTHER_PERSON.search(words)):
            return "guess", ""                          # a few words Claude may copy from the CV; never somebody else's name or employer
        return "", UNKNOWN

    def detail(self) -> str:
        """Which of the details a field asks for, whatever kind of field it is ('' = none): a hint for a choice."""
        field = self._raw
        words = _words(field)
        if _PRIVATE.search(words):
            return ""
        asked = _words({"label": field.get("label")}) or words
        for key, rule in _RULES:
            if rule.search(words) and _yours(key, asked, words):
                return key
        return ""

    def is_code_list(self) -> bool:
        """Whether a list is one of calling codes ("Czech Republic +420"): most of its entries carry one."""
        field = self._raw
        options = field.get("options") or []
        return str(field.get("type")) == "select" and len(options) >= 10 and sum(1 for o in options if _CODE.search(str(o))) > len(options) * 0.7

    def file_kind(self) -> str:
        """Which file a file field asks for (see `file_kind`)."""
        return file_kind(self._raw)


def name_of(field: dict[str, Any]) -> str:
    """What to call the field when talking to the person."""
    return Field(field).name


def classify(field: dict[str, Any]) -> tuple[str, str]:
    """(what it is, why it is left) for one field as the page reports it: see `Field.meaning`."""
    return Field(field).meaning()


def part_for(part: str, when: str) -> tuple[str, str]:
    """One box of a date that a form splits into a month and a year: (value, '') or ('', why it is left)."""
    day = RowDate(when)
    if not day:
        return "", ""
    if part == "year":
        return day.year, ""
    if part == "month":
        return (day.mm, "") if day.month else ("", NO_MONTH)
    return "", DATE                                 # the day is not known


def when_for(kind: str, when: str) -> tuple[str, str]:
    """A job's or a degree's date ("03/2023", "2023") in the form a field of this kind takes:
    (value, what to check) or ('', why it is left)."""
    day = RowDate(when)
    if not day:
        return "", ""
    year, month = day.year, day.mm
    if kind == "month":
        return (f"{year}-{month}", "") if month else ("", NO_MONTH)
    if kind == "date":
        return (f"{year}-{month}-01", CHECK_DAY) if month else ("", NO_MONTH)
    return (f"{month}/{year}" if month else year), ""


def detail_of(field: dict[str, Any]) -> str:
    """Which of the details a field asks for ('' = none): see `Field.detail`."""
    return Field(field).detail()


def value_for(what: str, mine: dict[str, Any], index: int = 0) -> str:
    """What goes into a field of this kind. `index` counts fields of the same kind on the page: the
    second "Employer" gets your second job."""
    if what in LISTED:
        name, key = LISTED[what]
        rows = details.jobs(mine) if name == "experience" else details.degrees(mine)
        return str(rows[index].get(key) or "") if index < len(rows) else ""
    if what == "salary":
        return details.salary_text(mine)
    if what == "full_name":
        return details.full_name(mine) if mine.get("first_name") and mine.get("last_name") else ""
    if what == "location":
        return ", ".join(part for part in (mine.get("city", ""), mine.get("country", "")) if part) if mine.get("city") else ""
    return str(mine.get(what) or "")


_CODE = re.compile(r"\+\d{1,4}\b")
PHONE_CODE = "The list beside this field shows another country's code than your number has: check both."
NO_CODE = "The list has no entry for the country code of your phone number. Choose it yourself."


def is_code_list(field: dict[str, Any]) -> bool:
    """Whether a list is one of calling codes: see `Field.is_code_list`."""
    return Field(field).is_code_list()


def code_option(options: list[str], phone: str, country: str = "") -> tuple[str, str]:
    """(the entry of a list of calling codes that your number begins with, that code), or ('', ''). The longest code wins
    ("+1684" before "+1"); among countries that share a code, yours."""
    digits = "+" + re.sub(r"\D", "", str(phone or "")) if str(phone or "").strip().startswith("+") else ""
    best: list[str] = []
    code = ""
    for option in options:
        found = _CODE.search(str(option))
        if found and digits.startswith(found.group(0)) and len(digits) > len(found.group(0)) + 3:
            if len(found.group(0)) > len(code):
                best, code = [str(option)], found.group(0)
            elif len(found.group(0)) == len(code):
                best.append(str(option))
    if len(best) > 1 and country:
        mine = country_option([_CODE.sub("", re.sub(r"[^\w\s+().'-]", " ", o)).strip(" ()") for o in best], country)
        best = [o for o in best if mine and mine in _CODE.sub("", re.sub(r"[^\w\s+().'-]", " ", o))] or best
    return (best[0], code) if len(best) == 1 else ("", "")


def national(phone: str, code: str) -> str:
    """Your number without its country code, for a field that has the code in a list beside it."""
    rest = str(phone or "").strip()
    return rest[len(code):].lstrip(" -.") if code and rest.startswith(code) else rest


def country_option(options: list[str], country: str) -> str:
    """The entry of a list that is this country, however the list spells it ("Czech Republic" for Czechia), or ''."""
    want = " ".join(str(country or "").lower().split())
    home = places.country_of(want) or want
    for option in options:
        text = " ".join(str(option or "").lower().split())
        if text and (text == want or (places.country_of(text) or text) == home):
            return str(option)
    return ""


class RowTracker:
    """Which job, degree or language a field belongs to.

    Jobs, degrees and languages are asked row by row. A row ends where one of its fields comes round
    again: the second "Company" starts your second job, whatever fields a row is made of."""

    LISTS = ("experience", "education", "languages")

    def __init__(self) -> None:
        self._row = dict.fromkeys(self.LISTS, 0)          # the row being filled in each list
        self._seen: dict[str, set] = {name: set() for name in self.LISTS}
        self.counts = dict.fromkeys(self.LISTS, 0)       # how many rows the form has, as far as it was read
        self.last = ""                                   # the list whose row is being filled: its dates belong to it
        self._at = -99                                   # where the last field of that row stood

    def place(self, what: str, field: "Field") -> int:
        """The row of a field that names a job, a degree or a language (0 = the first)."""
        name = LISTED[what][0]
        if name == "experience" and _CURRENT.search(field.words):
            return 0                                    # "current employer" is your current job wherever it stands
        if what in self._seen[name]:
            self._row[name] += 1
            self._seen[name] = set()
        self._seen[name].add(what)
        self.last = name
        self.counts[name] = self._row[name] + 1
        return self._row[name]

    def row(self, name: str) -> int:
        """The row being filled in a list."""
        return self._row[name]

    def mark(self, at: int) -> None:
        """A field of the current row stands at `at`."""
        self._at = at

    def within(self, at: int, distance: int) -> bool:
        """Whether a field at `at` is close enough after the current row to belong to it."""
        return bool(self.last) and at - self._at <= distance


class FormPlan:
    """What to do with the empty fields of one page: fill, ask Claude, choose, guess, tick, attach, or leave
    to the person with the reason. `as_dict()` is the shape the rest of the app reads."""

    def __init__(self) -> None:
        self.fill: list[dict] = []
        self.ask: list[dict] = []
        self.choose: list[dict] = []
        self.guess: list[dict] = []
        self.tick: list[dict] = []
        self.attach: list[dict] = []
        self.left: list[dict] = []

    def leave(self, label: str, why: str) -> None:
        self.left.append({"label": label, "why": why})

    def leaves(self, why: str) -> bool:
        """Whether some field is already left for this reason."""
        return any(i["why"] == why for i in self.left)

    def as_dict(self, rows: dict[str, int]) -> dict[str, Any]:
        return {"fill": self.fill, "ask": self.ask, "choose": self.choose, "guess": self.guess, "tick": self.tick,
                "attach": self.attach, "left": self.left, "rows": dict(rows)}


class FormPlanner:
    """Decides, field by field, what to do with a form that is still empty, from the person's details.
    One method for each kind of field; `plan()` goes through them in the order of the page."""

    def __init__(self, fields: list[dict[str, Any]], mine: dict[str, Any], letter: str = "", has_job: bool = False) -> None:
        self._fields = [Field(f, at) for at, f in enumerate(fields)]
        self._kinds = [f.meaning()[0] for f in self._fields]
        self._mine, self._letter, self._has_job = mine, letter, has_job
        self._plan, self._rows = FormPlan(), RowTracker()
        self._codes: dict[int, str] = {}               # where a list of calling codes stands, and the code it shows
        self._asked: set[str] = set()

    def plan(self) -> dict[str, Any]:
        for field in self._fields:
            self._one(field)
        return self._plan.as_dict(self._rows.counts)

    # ── what a field is, in its place on the page ──
    def _meaning(self, field: Field) -> tuple[str, str]:
        at, kind, kinds = field.at, field.kind, self._kinds
        what, why = field.meaning()
        # a "Start date" that belongs to no job (no end date, employer or school near it) asks when you can start
        if what == "row_start" and kind in ("date", "month") and _LONE_START.search(field.words) and not field.filled \
                and not {"row_end", "employer", "job_title", "school", "degree", "study_field"} & set(kinds[max(0, at - 4):at] + kinds[at + 1:at + 5]):
            what = "start"
        # inside a job's row: "Location" is where that job was, and "Role description" is what you did there
        near = self._rows.within(at, ROW_NEAR)
        picked = kind in ("select", "radio", "menu", "checkbox", "file") or field.combo
        if near and not picked and what not in LISTED and what not in ("row_start", "row_end", "start"):
            wordy = _ROW_TEXT.search(field.words) and (what in ("question", "guess") or kind == "textarea")
            if self._rows.last == "experience":
                what = "job_location" if what in ("location", "city") else ("job_description" if wordy else what)
            elif what in ("location", "city"):
                what, why = "", ROW_PLACE
            elif wordy:
                what, why = "", ROW_WORDS
        if self._rows.last == "languages" and self._rows.within(at, LANG_NEAR) and what != "lang_name" and kind != "checkbox" \
                and _LANG_LEVEL.search(_words({"label": field.get("label")}).strip(" *")):
            what = "lang_level"
        if what in LISTED or what in ("row_start", "row_end", "current_box", "lang_level", "fluent_box"):
            self._rows.mark(at)
        return what, why

    def _one(self, field: Field) -> None:
        what, why = self._meaning(field)
        if field.is_code_list() and str(self._mine.get("phone") or "").startswith("+"):
            return self._phone_code(field)
        if what == "start" and field.kind in ("date", "month") and not field.filled:
            return self._start_date(field)
        if field.filled:
            if what in LISTED:
                self._rows.place(what, field)            # a row that is filled already is still a row: the next one gets the next job
            return None
        if what == "file":
            return self._file(field)
        if what in ("row_start", "row_end"):
            return self._row_date(field, what)
        if what in ("lang_name", "lang_level", "fluent_box"):
            return self._language(field, what)
        if what == "current_box":
            return self._current_box(field)
        if what == "guess":
            self._plan.guess.append({"n": field.n, "label": field.name, "most": field.most})
        elif not what:
            self._plan.leave(field.name, why)
        elif what == "question":
            self._ask(field)
        elif what == "choice":
            self._choice(field)
        else:
            self._detail(field, what)
        return None

    # ── one method for each kind of field ──
    def _ask(self, field: Field) -> None:
        """An open question: Claude drafts the answer from the CV (one call for the page)."""
        label, question = field.name, str(field.get("label") or "").strip()[:form_answers.MAX_QUESTION]
        if not self._has_job:
            self._plan.leave(label, NO_JOB)
        elif question.lower() in self._asked:
            self._plan.leave(label, "The same question as one above: copy that answer if it fits.")
        elif len(self._plan.ask) >= form_answers.MAX_QUESTIONS:
            self._plan.leave(label, TOO_MANY)
        else:
            self._asked.add(question.lower())
            self._plan.ask.append({"n": field.n, "label": question, "most": field.most})

    def _phone_code(self, field: Field) -> None:
        """The list of calling codes beside a phone field: the code of your own number; the number then goes in without it."""
        if field.filled:
            self._codes[field.at] = str(field.get("code") or "")
            return
        entry, code = code_option(field.options, self._mine["phone"], self._mine.get("country", ""))
        if entry:
            self._codes[field.at] = code
            self._plan.fill.append({"n": field.n, "label": field.name, "value": entry, "kind": "detail"})
        else:
            self._codes[field.at] = ""
            self._plan.leave(field.name, NO_CODE)

    def _start_date(self, field: Field) -> None:
        """When you can start, worked out from what you wrote in Options."""
        said = str(self._mine.get("start") or "").strip()
        day, worked = start_day(said)
        if not said:
            self._plan.leave(field.name, START_UNKNOWN)
        elif not day:
            self._plan.leave(field.name, START_NO_DATE.format(text=said[:60]))
        else:
            self._plan.fill.append({"n": field.n, "label": field.name, "value": day.isoformat()[:7 if field.kind == "month" else 10],
                                    "kind": "detail", "check": START_CHECK.format(text=said[:60]) if worked else ""})

    def _file(self, field: Field) -> None:
        wants = field.file_kind()
        if wants:
            self._plan.attach.append({"n": field.n, "label": field.name, "kind": wants, "accept": str(field.get("accept") or "")})
        elif not str(field.get("label") or field.get("hint") or "").strip():
            # a file field with no words of its own is the page's tool behind its "Select file" buttons: said once, not once per field
            if not self._plan.leaves(FILE_BUTTON):
                self._plan.leave("Files", FILE_BUTTON)
        else:
            self._plan.leave(field.name, FILE)

    def _row_date(self, field: Field, what: str) -> None:
        """The start or end date of the job or degree of this row."""
        name = self._rows.last
        rows = (details.jobs(self._mine) if name == "experience" else details.degrees(self._mine)) if name else []
        entry = rows[self._rows.row(name)] if name and self._rows.row(name) < len(rows) else None
        if entry is None:
            self._plan.leave(field.name, DATE)
            return
        if what == "row_end" and entry.get("current"):
            return                                      # a job that goes on has no end date: the field stays empty, and that is right
        stamp = entry.get("start" if what == "row_start" else "end", "")
        if field.get("part"):
            value, note = part_for(field.get("part"), stamp)
        else:
            value, note = date_option(field.options, stamp) if field.kind == "select" else when_for(field.kind, stamp)
        if value:
            self._plan.fill.append({"n": field.n, "label": field.name, "value": value, "kind": "detail", "check": note})
        else:
            self._plan.leave(field.name, note or DATE)

    def _language(self, field: Field, what: str) -> None:
        """A language of yours, its level, or the box that says you are fluent in it."""
        label, kind = field.name, field.kind
        spoken = details.languages(self._mine)
        index = self._rows.place(what, field) if what == "lang_name" else self._rows.row("languages")
        entry = spoken[index] if self._rows.last == "languages" and index < len(spoken) else None
        options, menu = field.options, kind == "menu" or field.combo
        if entry is None:
            if what != "fluent_box":
                count = f"{len(spoken)} language{'' if len(spoken) == 1 else 's'}"
                self._plan.leave(label, MORE_LANGUAGES.format(have=count) if spoken else NO_DETAIL.format(what="languages"))
        elif what == "fluent_box":
            if entry.get("level") in ("Native", "Fluent"):
                self._plan.tick.append({"n": field.n, "label": label})
        elif what == "lang_level" and not entry.get("level"):
            self._plan.leave(label, NO_LEVEL.format(language=entry["language"]))
        elif menu:                                      # a menu the page draws: its entries are known only once it is open
            self._plan.choose.append({"n": field.n, "kind": "menu", "typed": field.combo, "label": label, "options": [],
                                      "what": what, "value": entry["language"] if what == "lang_name" else entry["level"]})
        elif kind in ("select", "radio"):
            if what == "lang_name":
                value, why = language_option(options, entry["language"]), NO_LANGUAGE.format(language=entry["language"])
            else:
                value, why = level_option(options, entry["level"]), NO_LEVEL_OPTION.format(level=entry["level"])
            if not value:
                self._plan.leave(label, why)
            elif kind == "radio":
                self._plan.choose.append({"n": field.n, "kind": "radio", "typed": False, "label": label, "options": options, "what": what,
                                          "value": entry["language"] if what == "lang_name" else entry["level"]})
            else:
                self._plan.fill.append({"n": field.n, "label": label, "value": value, "kind": "detail",
                                        **({"check": LEVEL_CHECK.format(level=entry["level"])} if what == "lang_level" else {})})
        else:
            self._plan.fill.append({"n": field.n, "label": label, "kind": "detail",
                                    "value": entry["language"] if what == "lang_name" else entry["level"]})

    def _current_box(self, field: Field) -> None:
        """The box "I work here now": ticked when the job of this row goes on."""
        rows = details.jobs(self._mine) if self._rows.last == "experience" else []
        here = self._rows.row("experience")
        if self._rows.last == "experience" and here < len(rows) and rows[here].get("current"):
            self._plan.tick.append({"n": field.n, "label": field.name})

    def _choice(self, field: Field) -> None:
        """A list, a yes/no question or a menu: chosen later by form_choices, with what the field asks about."""
        about, kind = field.detail(), field.kind
        shape = "number" if kind == "number" else ("menu" if kind == "menu" or field.combo else kind)
        self._plan.choose.append({"n": field.n, "kind": shape, "typed": field.combo, "label": field.name,
                                  "options": field.options, "what": about, "value": value_for(about, self._mine) if about else ""})

    def _detail(self, field: Field, what: str) -> None:
        """One of your details, or the letter."""
        label, kind, most, mine = field.name, field.kind, field.most, self._mine
        jobs = details.jobs(mine)
        said = _words({"label": field.name}) or field.words
        if (what in ("employer", "job_title") and _NOW.search(said) and not _OR_LAST.search(said)
                and jobs and not any(j.get("current") for j in jobs)):
            self._plan.leave(label, NO_CURRENT_JOB)
            return
        index = self._rows.place(what, field) if what in LISTED else 0
        value = self._letter if what == "letter" else value_for(what, mine, index)
        if what in LISTED and not value and index:
            have = len(mine.get(LISTED[what][0]) or [])
            if index >= have > 0:                       # the form has more rows than you have jobs or degrees
                count = f"{have} {details.WORD[LISTED[what][0]]}{'' if have == 1 else 's'}"
                self._plan.leave(label, MORE_ROWS.format(have=count))
                return
        if value and what == "country" and kind == "select":
            value = country_option(field.options, value)
            if not value:
                self._plan.leave(label, NO_COUNTRY.format(country=mine["country"]))
                return
        near = [self._codes[k] for k in (field.at - 1, field.at - 2, field.at + 1) if k in self._codes]
        check = ""
        if value and what == "phone" and near and kind in ("text", "tel"):
            if near[0] and value.startswith(near[0]):
                value = national(value, near[0])
            else:
                check = PHONE_CODE
        if value and what == "phone" and most and len(value) > most:
            value = re.sub(r"[ ()./\-]", "", value)     # a short field: the same number without its spaces
        if not value and what in SOFT and (len(str(field.get("label") or "")) >= 20 or "?" in str(field.get("label") or "")):
            self._ask(field)                            # not in My details: drafted like any other question
        elif not value:
            self._plan.leave(label, NO_LETTER if what == "letter" else (START_UNKNOWN if what == "start" else NO_DETAIL.format(what=WHAT.get(what, what))))
        elif most and len(value) > most:
            self._plan.leave(label, TOO_LONG.format(most=most, size=len(value)))
        else:
            self._plan.fill.append({"n": field.n, "label": label, "value": value, "kind": "letter" if what == "letter" else "detail",
                                    **({"check": check} if check else {})})


def plan(fields: list[dict[str, Any]], mine: dict[str, str], letter: str = "", has_job: bool = False) -> dict[str, list]:
    """What to do with each field that is still empty:
    {"fill": [{n, label, value, kind}], "ask": [{n, label, most}], "choose": [{n, kind, typed, label, options, what, value}],
     "left": [{label, why}]}. Fields that already hold something are not touched and not listed. See `FormPlanner`."""
    return FormPlanner(fields, mine, letter, has_job).plan()


def read_answer(text: str) -> dict[str, Any]:
    """What the READ script gave back, checked: a page may answer anything."""
    data = page_reply(text, FORM_REFUSED)
    if not isinstance(data.get("fields"), list):
        raise ValueError(FORM_REFUSED)
    fields = []
    for raw in data["fields"][:MAX_FIELDS]:
        if not isinstance(raw, dict) or not isinstance(raw.get("n"), int):
            continue
        fields.append({"n": raw["n"], "filled": bool(raw.get("filled")), "required": bool(raw.get("required")), "combo": bool(raw.get("combo")),
                       "most": raw.get("most") if isinstance(raw.get("most"), int) else 0,
                       "options": [str(o)[:80] for o in (raw.get("options") or [])[:300]] if isinstance(raw.get("options"), list) else [],
                       **{key: " ".join(str(raw.get(key) or "").split())[:300] for key in ("type", "name", "id", "auto", "label", "hint", "accept", "code", "part", "group")}})
    return {"url": str(data.get("url") or ""), "title": str(data.get("title") or "")[:300], "from": str(data.get("from") or "")[:2000], "fields": fields,
            "frames": [str(f)[:300] for f in (data.get("frames") or [])[:5]] if isinstance(data.get("frames"), list) else [],
            "boxes": data.get("boxes") if isinstance(data.get("boxes"), int) else 0,
            "adds": [{"k": a["k"], "text": " ".join(str(a.get("text") or "").split())[:80], "kind": add_kind(str(a.get("text") or ""))}
                     for a in (data.get("adds") or [])[:20] if isinstance(a, dict) and isinstance(a.get("k"), int)] if isinstance(data.get("adds"), list) else []}


def add_kind(words: str) -> str:
    """Which list a button adds a row to, by its words: "experience", "education" or '' (not clear: never pressed)."""
    low = " ".join(str(words or "").lower().split())
    if not re.match(r"\+?\s*add\b", low) or re.search(r"apply|submit|send|next|continue|save|finish|upload|file|attach", low):
        return ""
    work = bool(re.search(r"job|experience|position|employment|employer|work", low))
    study = bool(re.search(r"education|degree|school|qualification|universit|stud", low))
    speak = bool(re.search(r"language", low))
    if speak:
        return "languages" if not work and not study else ""
    return "experience" if work and not study else ("education" if study and not work else "")


def fill_answer(text: str) -> dict[str, Any]:
    data = page_reply(text, "The page did not say what was filled in. Look at the form: outlined fields were filled.")
    numbers = lambda key: [n for n in (data.get(key) or []) if isinstance(n, int)] if isinstance(data.get(key), list) else []   # noqa: E731
    return {"moved": bool(data.get("moved")), "done": numbers("done"), "skipped": numbers("skipped")}


# ── which job a page belongs to ─────────────────────────────────────────────
def host_of(url: str) -> str:
    try:
        return (urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


RUSSIAN = "This app does not work with Russian services, so I do not {doing}."


def plain_problems(fields: list[dict[str, Any]], email: str = "") -> list[dict[str, str]]:
    """What a form read back by REVIEW shows wrong in plain code, without Claude: a required field left empty, a part
    still in [square brackets], an email address that is not yours. [{field, problem}]"""
    problems = []
    for f in fields:
        if f["required"] and not f["filled"]:
            problems.append({"field": f["label"], "problem": "It is required and still empty."})
        elif "[" in f["value"] and "]" in f["value"]:
            problems.append({"field": f["label"], "problem": "It still has a part in [square brackets] to fill in."})
        elif f["kind"] == "email" and email and f["value"].strip() and f["value"].strip().lower() != email.lower():
            problems.append({"field": f["label"], "problem": f"It is not the address in My details ({email})."})
    return problems


class PageAddress:
    """The address of a page the assistant is asked to work on: a web page (http or https, with a host), and never
    a Russian service. One rule for filling in, reading, opening and noticing a page."""

    def __init__(self, url: str) -> None:
        self.url = str(url or "").strip()
        self.host = host_of(self.url)

    @property
    def is_web(self) -> bool:
        return self.url.lower().startswith(("http://", "https://")) and bool(self.host)

    @property
    def refused(self) -> bool:
        """A Russian service: the assistant does nothing there."""
        return mailhosts.never_used(self.host)

    def refusal(self, doing: str) -> str:
        return RUSSIAN.format(doing=doing)


def _address(url: str) -> str:
    parts = urlsplit(str(url or ""))
    return f"{(parts.hostname or '').lower().removeprefix('www.')}{parts.path.rstrip('/')}"


def _named_in(job: dict[str, Any], text: str) -> bool:
    """Whether the company of a job is named in these words: the whole name, in order ("good data" or "gooddata")."""
    kept = email_client.company_tokens(job.get("company", ""))
    name = [w for w in re.findall(r"[a-z0-9]{3,}", str(job.get("company") or "").lower()) if w in kept]
    if not set(name) - email_client.GENERIC_COMPANY_WORDS:
        return False                                # a name made of words many companies share names nobody
    return bool(re.search(rf"\b(?:{' '.join(name)}|{''.join(name)})\b", text))


def _plain(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def match_job(jobs: list[dict[str, Any]], url: str, title: str, came_from: str = "", text: str = "", opened: str = "") -> str:
    """The id of the one job this page is plainly the form of, or ''.

    A form is rarely at the address of its posting: "Apply" leads to another page, often on another
    site. So, in this order: the address of the posting (of this page, or of the page that led here);
    the company's own name in the page's address or title; the company and the job's title both in
    the words of the page; and the posting you opened from the app a moment ago (`opened`), when the
    page names its company or its title. Two jobs at one company are told apart by their title.
    Anything less certain is left for the person to choose."""
    here = _address(url)
    for where in (here, _address(came_from) if came_from else ""):
        same = [j for j in jobs if where and j.get("url") and _address(j["url"]) == where and urlsplit(j["url"]).path.strip("/")]
        if len(same) == 1:
            return same[0]["id"]
    head, body = _plain(f"{here} {title}"), _plain(text)       # the site's name, the path (boards name the company there), the title
    low = " ".join(str(title or "").lower().split())

    def titled(job, words) -> bool:
        return bool(job.get("title")) and _plain(job["title"]) in words

    named = [j for j in jobs if _named_in(j, head)]
    if len(named) > 1:
        named = [j for j in named if j.get("title") and " ".join(j["title"].lower().split()) in low] or [j for j in named if titled(j, body)]
    if len(named) == 1:
        return named[0]["id"]
    if named:
        return ""                                   # two jobs of one company and nothing tells them apart
    both = [j for j in jobs if _named_in(j, body) and titled(j, f"{head} {body}")]
    if len(both) == 1:
        return both[0]["id"]
    last = next((j for j in jobs if opened and j.get("id") == opened), None)
    if last and (_named_in(last, body) or titled(last, f"{head} {body}")
                 or (came_from and last.get("url") and host_of(came_from) == host_of(last["url"]))):
        return last["id"]
    return ""
