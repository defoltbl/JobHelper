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

import json
import re
from typing import Any
from urllib.parse import urlsplit

from . import details, email_client, form_answers, places

MAX_FIELDS = 200

READ = r"""
(function () {
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
    var own = (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') ? '' : text(el), node = el;     // a list's own entries are not its name
    for (var i = 0; i < 3; i++) {
      node = node.parentElement;
      if (!node) break;
      var around = clean(text(node).replace(own, ''));
      if (around.length > 160) break;
      if (around) return around;
    }
    return '';
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
      if (type === 'checkbox' || type === 'radio') {
        if (!(shown(el) || (el.labels && el.labels.length))) continue;
        if (type === 'checkbox' && !el.disabled) {
          var says = clean(el.labels && el.labels.length ? text(el.labels[0]) : (el.getAttribute('aria-label') || '')).slice(0, 120);
          if (/current|present|still work|i work here|ongoing|to date|till now|until now/i.test(says) && !/agree|consent|terms|privacy|policy|newsletter|subscribe|marketing/i.test(says)) {
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
                   filled: filled, most: el.maxLength > 0 ? el.maxLength : 0, options: options,
                   combo: el.getAttribute('role') === 'combobox' || !!el.getAttribute('aria-autocomplete') || el.getAttribute('aria-haspopup') === 'listbox'});
    }
  }
  walk(document);
  return JSON.stringify({url: location.href, title: clean(document.title), fields: fields, frames: frames.slice(0, 5), boxes: boxes, adds: adds.slice(0, 20)});
})()
""".replace("__MOST__", str(MAX_FIELDS)).strip()

FILL = r"""
(function (items, url, typed) {
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
""".strip()

EMPTY = r"""
(function (wanted, url) {
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
      if (el.tagName === 'SELECT' ? el.selectedIndex <= 0 : String(el.value || '').trim() === '') empty.push(mark);
    }
  }
  walk(document);
  return JSON.stringify({empty: empty});
})(__WANTED__, __URL__)
""".strip()


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
    if (!box || box.tagName !== 'INPUT' || box.type !== 'checkbox' || box.disabled
        || !/current|present|still work|i work here|ongoing|to date|till now|until now/i.test(label)
        || /agree|consent|terms|privacy|policy|newsletter|subscribe|marketing/i.test(label)) return JSON.stringify({ok: false});
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
      press(target);
      if (arg) {
        var view = target.ownerDocument.defaultView;
        Object.getOwnPropertyDescriptor(view.HTMLInputElement.prototype, 'value').set.call(target, arg);
        target.dispatchEvent(new view.Event('input', {bubbles: true}));
      }
    } else press(target);
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
""".strip()


def choose_script(action: str, n: int, arg: Any, url: str) -> str:
    """The CHOOSE script for one step with a menu or a radio button: "open" (arg: text to type, or ''),
    "options", "pick" (arg: the entry's number), "close" (arg: true to clear typed text), "radio" (arg: the button's number), "add" (arg: the number of a button
    that adds a row for another job or degree; n is not used)."""
    assert action in ("open", "options", "pick", "close", "radio", "add", "tick")
    return (CHOOSE.replace("__ACTION__", json.dumps(action)).replace("__N__", json.dumps(int(n)))
            .replace("__ARG__", json.dumps(arg)).replace("__URL__", json.dumps(str(url))))


def choose_answer(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text or "")
    except ValueError:
        data = None
    if not isinstance(data, dict):
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
      if (el.tagName === 'SELECT' ? el.selectedIndex <= 0 : String(el.value || '').trim() === '') empty++;
    }
  }
  walk(document);
  return JSON.stringify({url: location.href, fields: names.length, first: names.slice(0, 12).join('|').slice(0, 400), empty: empty});
})()
""".strip()


REVIEW = r"""
(function () {
  var out = [], seen = {};
  function clean(t) { return String(t || '').replace(/\s+/g, ' ').trim(); }
  function text(el) { return el ? clean(el.innerText || el.textContent) : ''; }
  function name(el) {
    if (el.labels && el.labels.length && text(el.labels[0])) return text(el.labels[0]);
    if (el.getAttribute('aria-label')) return clean(el.getAttribute('aria-label'));
    var node = el;
    for (var i = 0; i < 3; i++) { node = node.parentElement; if (!node) break; var t = text(node); if (t.length > 160) break; if (t) return t; }
    return clean(el.getAttribute('placeholder') || el.name || el.id);
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
      var value = tag === 'SELECT' ? (el.selectedIndex > 0 ? clean(el.options[el.selectedIndex].text) : '') : String(el.value || '');
      out.push({label: name(el).slice(0, 200), value: value.slice(0, 3000), required: !!(el.required || el.getAttribute('aria-required') === 'true'), kind: type});
    }
  }
  walk(document);
  return JSON.stringify({url: location.href, title: clean(document.title).slice(0, 300), fields: out});
})()
""".strip()


def review_answer(text: str) -> dict[str, Any]:
    """What the REVIEW script gave back, checked. A field whose name marks it as personal or as payment keeps
    only whether it is filled in: its value goes no further."""
    try:
        data = json.loads(text or "")
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("fields"), list):
        raise ValueError("The page did not answer the way a page with a form does. Reload it and ask me again.")
    fields = []
    for raw in data["fields"][:120]:
        if not isinstance(raw, dict):
            continue
        label = " ".join(str(raw.get("label") or "").split())[:200]
        value = str(raw.get("value") or "")[:3000]
        private = bool(_PRIVATE.search(label.lower()))
        fields.append({"label": label or "A field with no name", "value": "" if private else value, "filled": bool(value.strip()),
                       "required": bool(raw.get("required")), "private": private, "kind": str(raw.get("kind") or "text")[:20]})
    return {"url": str(data.get("url") or ""), "title": str(data.get("title") or "")[:300], "fields": fields}


PAGE = r"""
(function () {
  function clean(t) { return String(t || '').replace(/[ \t\u00a0]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim(); }
  var main = document.querySelector('main, article, [role=main]') || document.body;
  var text = clean(main ? main.innerText : '');
  if (text.length < 400 && document.body) text = clean(document.body.innerText);
  return JSON.stringify({url: location.href, title: clean(document.title).slice(0, 300), text: text.slice(0, 12000)});
})()
""".strip()


def page_answer(text: str) -> dict[str, str]:
    """What the PAGE script gave back: the address, the title and the words of the page, as plain text."""
    try:
        data = json.loads(text or "")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise ValueError("The page did not answer. Reload it and ask me again.")
    return {"url": str(data.get("url") or "")[:2000], "title": " ".join(str(data.get("title") or "").split())[:300],
            "text": str(data.get("text") or "")[:12000]}


def values_script(numbers: list[int], url: str) -> str:
    """The VALUES script: what the fields with these numbers hold now. Asked only for fields the assistant itself filled in."""
    return VALUES.replace("__WANTED__", json.dumps([int(n) for n in numbers])).replace("__URL__", json.dumps(str(url)))


def values_answer(text: str) -> dict[int, str]:
    try:
        data = json.loads(text or "")
    except ValueError:
        return {}
    values = data.get("values") if isinstance(data, dict) else None
    return {int(k): str(v)[:3000] for k, v in values.items() if str(k).isdigit()} if isinstance(values, dict) else {}


def watch_answer(text: str) -> dict[str, Any]:
    """Where the form stands: {url, sign, empty}. `sign` changes when the page shows other fields."""
    try:
        data = json.loads(text or "")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return {"url": "", "sign": "", "empty": 0}
    count = data.get("fields") if isinstance(data.get("fields"), int) else 0
    return {"url": str(data.get("url") or "")[:500], "sign": f"{count}:{str(data.get('first') or '')[:400]}",
            "empty": data.get("empty") if isinstance(data.get("empty"), int) else 0}


def fill_script(items: list[dict[str, Any]], url: str, typed: bool = False) -> str:
    """The FILL script for these values. They travel as data (JSON), never as code. `typed` writes them the
    way typing arrives, for a page that threw away what was written the plain way."""
    data = [{"n": int(i["n"]), "value": str(i["value"]), "check": bool(i.get("check"))} for i in items]
    return FILL.replace("__ITEMS__", json.dumps(data)).replace("__URL__", json.dumps(str(url))).replace("__TYPED__", "true" if typed else "false")


def empty_script(numbers: list[int], url: str) -> str:
    """The EMPTY script: which of these fields hold nothing now. It says only that, never what a field holds."""
    return EMPTY.replace("__WANTED__", json.dumps([int(n) for n in numbers])).replace("__URL__", json.dumps(str(url)))


def empty_answer(text: str) -> list[int]:
    try:
        data = json.loads(text or "")
    except ValueError:
        return []
    return [n for n in data.get("empty") or [] if isinstance(n, int)] if isinstance(data, dict) and isinstance(data.get("empty"), list) else []


# ── what a field is ─────────────────────────────────────────────────────────
PASSWORD = "A password is yours to type."
FILE = "Attach the file yourself: a page cannot be handed a file from outside."
PRIVATE = "Personal or payment information: fill it in yourself."
CHOICE = "Choose it yourself."
DATE = "Pick the date yourself."
UNKNOWN = "I did not recognise this field."
NO_DETAIL = "Not in My details yet: add your {what} there and ask me again."
TOO_LONG = "The field takes {most} characters and this is {size}. Shorten it and paste it yourself."
NO_COUNTRY = "The list has no entry for {country}. Choose it yourself."
NO_JOB = "An open question: choose the job this form is for, and I will draft the answer from your CV."
NO_LETTER = "No letter written by the app for this job. Paste your own."
TOO_MANY = f"More than {form_answers.MAX_QUESTIONS} open questions: ask me again after these are done."

_PRIVATE = re.compile(r"passw|captcha|card ?number|credit card|\bcvv\b|\bcvc\b|\biban\b|\bbank|account number|social security|\bssn\b"
                      r"|national id|id number|passport|birth|\bdob\b|\bage\b|gender|\bsex\b|pronoun|\brace\b|ethnic|disab|veteran"
                      r"|religio|orientation|marital|criminal|convict|health")
_NOT_MINE = re.compile(r"company|employer|organi[sz]ation|school|universit|college|referr|referee|reference|emergency|manager|recruiter"
                       r"|supervisor|\btitle\b|position|\brole\b|degree|skill|user ?name|login|nick")
# what forms ask again and again; when it is not in My details, an open question is drafted instead
SOFT = ("employer", "job_title", "school", "degree", "study_field", "notice_period", "salary")
# asked once per job or per degree: the first such field gets the first entry of the list, the next one the second
LISTED = {"employer": ("experience", "employer"), "job_title": ("experience", "title"),
          "school": ("education", "school"), "degree": ("education", "degree"), "study_field": ("education", "field")}
MORE_ROWS = "You listed {have} in My details, and this is one more. Add it there, or type it."
_ROW_START = re.compile(r"\bstart(?:ed)?\b|\bfrom\b|\bbegan\b|date from|od\b")
_ROW_END = re.compile(r"\bend(?:ed)?\b|\bto\b|\buntil\b|\bfinish|\bleft\b|date to|graduat")
_NOT_A_ROW_DATE = re.compile(r"earliest|availab|can you|notice|birth|expected|preferred|interview|deadline|today|valid|expir|issue")
NO_MONTH = "My details has only the year for this. Add the month there, or pick the date yourself."
CHECK_DAY = "The day is not known, so the first of the month was used: check the date."
SKIPPED = "You asked me to leave it out."
THROWN = "The page threw the value away twice. Type this one yourself."
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")


def date_option(options: list[str], when: str) -> tuple[str, str]:
    """The entry of a month list or a year list that is this date ("03/2023"): (entry, '') or ('', why not).
    Which of the two the list is shows in its entries: years are four digits."""
    parts = re.split(r"[./-]", str(when or ""))
    if not when:
        return "", ""
    year, month = parts[-1], (int(parts[0]) if len(parts) == 2 else 0)
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
_NOT_THIS_JOB = re.compile(r"appl|desired|interested|preferred|referr|referee|emergency")
_RULES = (("linkedin", re.compile(r"linked ?in")),
          ("github", re.compile(r"git ?hub")),
          ("email", re.compile(r"e ?mail")),
          ("phone", re.compile(r"phone|mobile|\bcell\b|telefon|\btel\b")),
          ("notice_period", re.compile(r"notice period|period of notice|výpovědní")),
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
WHAT = {"full_name": "name", "location": "city", "employer": "jobs", "job_title": "jobs", "school": "degrees", "degree": "degrees",
        "study_field": "degrees", "salary": "salary", **{key: label.lower() for key, label in details.LABELS.items()}}


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
    "location"), "letter", "question", "choice" (something to pick: see form_choices), or ""
    when the field is left to the person."""
    kind = str(field.get("type") or "text").lower()
    words = _words(field)
    picked = kind in ("select", "radio", "menu") or bool(field.get("combo"))
    if kind == "password":
        return "", PASSWORD
    if kind == "file":
        return "", FILE
    if _PRIVATE.search(words):
        return "", PRIVATE
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
    if not what:
        for key, rule in _RULES:
            if rule.search(words):
                if key in ("first_name", "last_name", "full_name", "street", "location", "city", "country", "postcode") and _NOT_MINE.search(words):
                    continue
                if key in ("employer", "job_title") and _NOT_THIS_JOB.search(words):
                    continue                        # "position applied for", "referee's employer": not a job of yours
                what = key
                break
    has_words = bool(re.search(r"[^\W\d_]{2}", str(field.get("label") or "")))
    if kind == "checkbox":
        return "current_box", ""                    # the only kind of tick box that is reported: "I work here now"
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
    if has_words and kind in ("text", "search") and not _NOT_MINE.search(words) and not _NOT_THIS_JOB.search(words):
        return "guess", ""                          # a few words Claude may copy from the CV; never somebody else's name or employer
    return "", UNKNOWN


def when_for(kind: str, when: str) -> tuple[str, str]:
    """A job's or a degree's date ("03/2023", "2023") in the form a field of this kind takes:
    (value, what to check) or ('', why it is left)."""
    parts = re.split(r"[./\-]", str(when or ""))
    if not when:
        return "", ""
    year, month = parts[-1], (parts[0].zfill(2) if len(parts) == 2 else "")
    if kind == "month":
        return (f"{year}-{month}", "") if month else ("", NO_MONTH)
    if kind == "date":
        return (f"{year}-{month}-01", CHECK_DAY) if month else ("", NO_MONTH)
    return (f"{month}/{year}" if month else year), ""


def detail_of(field: dict[str, Any]) -> str:
    """Which of the details a field asks for, whatever kind of field it is ('' = none): a hint for a choice."""
    words = _words(field)
    if _PRIVATE.search(words):
        return ""
    for key, rule in _RULES:
        if rule.search(words) and not (key in ("first_name", "last_name", "full_name", "street") and _NOT_MINE.search(words)) \
                and not (key in ("employer", "job_title") and _NOT_THIS_JOB.search(words)):
            return key
    return ""


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


def country_option(options: list[str], country: str) -> str:
    """The entry of a list that is this country, however the list spells it ("Czech Republic" for Czechia), or ''."""
    want = " ".join(str(country or "").lower().split())
    home = places.country_of(want) or want
    for option in options:
        text = " ".join(str(option or "").lower().split())
        if text and (text == want or (places.country_of(text) or text) == home):
            return str(option)
    return ""


def plan(fields: list[dict[str, Any]], mine: dict[str, str], letter: str = "", has_job: bool = False) -> dict[str, list]:
    """What to do with each field that is still empty:
    {"fill": [{n, label, value, kind}], "ask": [{n, label, most}], "choose": [{n, kind, typed, label, options, what, value}],
     "left": [{label, why}]}. Fields that already hold something are not touched and not listed."""
    out: dict[str, Any] = {"fill": [], "ask": [], "choose": [], "guess": [], "tick": [], "left": [], "rows": {"experience": 0, "education": 0}}
    asked: set[str] = set()
    last = [""]                                     # the list whose row is being filled: its dates belong to that row
    # Jobs and degrees are asked row by row. A row ends where one of its fields comes round again:
    # the second "Company" starts your second job, whatever fields a row is made of.
    row = {"experience": 0, "education": 0}
    seen: dict[str, set] = {"experience": set(), "education": set()}

    def place(what: str, field: dict[str, Any]) -> int:
        name = LISTED[what][0]
        if name == "experience" and _CURRENT.search(_words(field)):
            return 0                                # "current employer" is your current job wherever it stands
        if what in seen[name]:
            row[name] += 1
            seen[name] = set()
        seen[name].add(what)
        last[0] = name
        out["rows"][name] = row[name] + 1
        return row[name]

    def ask(field, label, most) -> None:
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

    for field in fields:
        label, most = name_of(field), int(field.get("most") or 0)
        kind = str(field.get("type") or "text").lower()
        what, why = classify(field)
        if field.get("filled"):
            if what in LISTED:
                place(what, field)                  # a row that is filled already is still a row: the next one gets the next job
            continue
        if what in ("row_start", "row_end"):
            name = last[0]
            rows = (details.jobs(mine) if name == "experience" else details.degrees(mine)) if name else []
            entry = rows[row[name]] if name and row[name] < len(rows) else None
            if entry is None:
                out["left"].append({"label": label, "why": DATE})
            elif what == "row_end" and entry.get("current"):
                continue                            # a job that goes on has no end date: the field stays empty, and that is right
            else:
                stamp = entry.get("start" if what == "row_start" else "end", "")
                value, note = date_option(field.get("options") or [], stamp) if kind == "select" else when_for(kind, stamp)
                if value:
                    out["fill"].append({"n": field["n"], "label": label, "value": value, "kind": "detail", "check": note})
                else:
                    out["left"].append({"label": label, "why": note or DATE})
        elif what == "current_box":
            rows = details.jobs(mine) if last[0] == "experience" else []
            if last[0] == "experience" and row["experience"] < len(rows) and rows[row["experience"]].get("current"):
                out["tick"].append({"n": field["n"], "label": label})       # the job of this row goes on
        elif what == "guess":
            out["guess"].append({"n": field["n"], "label": label, "most": most})
        elif not what:
            out["left"].append({"label": label, "why": why})
        elif what == "question":
            ask(field, label, most)
        elif what == "choice":
            about = detail_of(field)
            shape = "number" if kind == "number" else ("menu" if kind == "menu" or field.get("combo") else kind)
            out["choose"].append({"n": field["n"], "kind": shape, "typed": bool(field.get("combo")), "label": label,
                                  "options": list(field.get("options") or []), "what": about, "value": value_for(about, mine) if about else ""})
        else:
            index = place(what, field) if what in LISTED else 0
            value = letter if what == "letter" else value_for(what, mine, index)
            if what in LISTED and not value and index:
                have = len(mine.get(LISTED[what][0]) or [])
                if index >= have > 0:               # the form has more rows than you have jobs or degrees
                    count = f"{have} {details.WORD[LISTED[what][0]]}{'' if have == 1 else 's'}"
                    out["left"].append({"label": label, "why": MORE_ROWS.format(have=count)})
                    continue
            if value and what == "country" and kind == "select":
                value = country_option(field.get("options") or [], value)
                if not value:
                    out["left"].append({"label": label, "why": NO_COUNTRY.format(country=mine["country"])})
                    continue
            if value and what == "phone" and most and len(value) > most:
                value = re.sub(r"[ ()./\-]", "", value)             # a short field: the same number without its spaces
            if not value and what in SOFT and (len(str(field.get("label") or "")) >= 20 or "?" in str(field.get("label") or "")):
                ask(field, label, most)                              # not in My details: drafted like any other question
            elif not value:
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
        fields.append({"n": raw["n"], "filled": bool(raw.get("filled")), "required": bool(raw.get("required")), "combo": bool(raw.get("combo")),
                       "most": raw.get("most") if isinstance(raw.get("most"), int) else 0,
                       "options": [str(o)[:80] for o in (raw.get("options") or [])[:300]] if isinstance(raw.get("options"), list) else [],
                       **{key: " ".join(str(raw.get(key) or "").split())[:300] for key in ("type", "name", "id", "auto", "label", "hint")}})
    return {"url": str(data.get("url") or ""), "title": str(data.get("title") or "")[:300], "fields": fields,
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
    return "experience" if work and not study else ("education" if study and not work else "")


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
