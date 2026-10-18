"""Choosing for a form: an entry of a list, one of a pair of radio buttons, an entry of a menu
the page draws itself, or a number it asks for ("years of experience").

A choice is made only when something settles it: first your own details and what the app knows
about the job (no model call), then one question to Claude for everything that is left, with the
rule that an answer the CV and your facts do not settle stays open. Every choice made for you is
marked for checking; what stays open is left to you with the reason.
"""
from __future__ import annotations

import re
from typing import Any

from . import config, details, filters, form_fill, llm, places

MAX_CHOICES = 12
CHECK = "Chosen for you: check it."
NOT_SETTLED = "Your CV, My details and About you do not settle this. Choose it yourself."
NO_MENU = "The menu did not open for me. Choose it yourself."
TOO_MANY = f"More than {MAX_CHOICES} lists and choices: ask me again after these are done."

SYSTEM = ("You answer the multiple-choice and number fields of one job application form for one candidate. You only use "
          "the candidate's CV and the facts given. When they do not settle a field, you answer null: you never guess, and "
          "you never choose an answer about gender, age, origin, health, religion or family. Reply with only the JSON object.")

PROMPT = """Choose the answers for these fields of a job application form.

Master CV (the only source of truth about the candidate):
---
{cv_text}
---

Facts the candidate gave ("not stated" means you do not know):
{facts}

Job: {title} at {company} ({location})

Fields:
{fields}

For each field:
- a field with options: answer with one option, copied exactly as written. Choose it only when the CV or the facts
  settle it (for example the right to work, a degree level, a language level, where the posting was found);
- a field that takes a few words: copy them exactly from the CV or the facts (a language, a city, a tool, a job title).
  Never write a sentence, and never write anything the CV and the facts do not state;
- a number field: answer with digits only. Whole years may be counted from the dates in the CV; if the CV shows no
  use of the thing asked about, the answer is 0;
- anything the CV and the facts do not settle: null.

Return JSON with exactly this shape, one entry per field:
{{"choices": [{{"n": <field number>, "answer": "<the option, the number, or null>"}}]}}"""

_HEARD = re.compile(r"how did you (?:hear|find|learn)|where did you (?:hear|find|see)|\bsource\b|referral source")


_NUMBERS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
            "ten": "10", "eleven": "11", "twelve": "12"}


def _norm(text: Any) -> str:
    """Words for comparing: lower case, no punctuation, "one" as "1"."""
    words = re.sub(r"[^\w+#. ]+", " ", str(text or "").lower()).split()
    return " ".join(_NUMBERS.get(w, w) for w in words).strip(". ")


def match_option(options: list[str], value: str) -> str:
    """The one option that says the same as `value` ('' when none or several do)."""
    want = _norm(value)
    if not want:
        return ""
    same = [o for o in options if _norm(o) == want]
    if same:
        return same[0]
    near = [o for o in options if len(_norm(o)) >= 3 and (re.search(rf"\b{re.escape(want)}\b", _norm(o)) or re.search(rf"\b{re.escape(_norm(o))}\b", want))]
    return near[0] if len(near) == 1 else ""


def settle(choice: dict[str, Any], mine: dict[str, str], job: dict[str, Any] | None) -> str:
    """The answer that needs no model: from My details and from what the app knows about the job ('' = not settled here)."""
    options, what = list(choice.get("options") or []), choice.get("what") or ""
    if choice.get("kind") == "number":
        return ""
    if what == "country":
        return form_fill.country_option(options, mine.get("country", ""))
    if what == "lang_name":                         # one of your languages, in a list the page draws itself
        return form_fill.language_option(options, choice.get("value") or "")
    if what == "lang_level":
        return form_fill.level_option(options, choice.get("value") or "")
    if what in ("city", "location") and mine.get("city"):
        city = [o for o in options if re.search(rf"\b{re.escape(_norm(mine['city']))}\b", _norm(o))]
        named = _norm(mine["city"])                 # "Brno, Slovakia" is not home because Brno is: only the rest of the entry says the country
        home = [o for o in city if mine.get("country")
                and form_fill.country_option([part for part in re.split(r"[,(/)]", o) if named not in _norm(part)], mine["country"])]
        return (home or city)[0] if len(home) == 1 or len(city) == 1 or home else ""
    if what == "phone":                             # the list of country codes next to a phone field
        return form_fill.code_option(options, mine.get("phone", ""), mine.get("country", ""))[0]
    if choice.get("value"):
        found = match_option(options, choice["value"])
        if found:
            return found
    if job and _HEARD.search(_norm(choice.get("label"))):
        source = _norm(str(job.get("source") or "").split("/")[0])
        for word in [w for w in re.findall(r"[a-z]{4,}", source)] + (["linkedin"] if "linkedin" in str(job.get("url") or "").lower() else []):
            found = [o for o in options if word in _norm(o).replace(" ", "")]
            if len(found) == 1:
                return found[0]
    return ""


def facts_block(cv_text: str, mine: dict[str, str], job: dict[str, Any] | None) -> str:
    lines = [config.facts_block(cv_text)]
    for key, label in (("country", "Lives in"), ("notice_period", "Notice period")):
        lines.append(f"- {label}: {mine.get(key) or 'not stated'}")
    lines += details.facts(mine)                    # every job (which ones are current), every degree, the salary
    source = str((job or {}).get("source") or "").split("/")[0].strip()
    lines.append(f"- Found the posting on: {source or 'not stated'}")
    return "\n".join(lines)


_PERMIT = re.compile(r"authori[sz]ed to work|right to work|work (?:permit|authori[sz]ation|visa)|(?:eligible|entitled|allowed|permitted) to work|"
                     r"legally work|\bsponsor", re.IGNORECASE)


def another_country(label: str, mine: dict[str, Any]) -> str:
    """The country a right-to-work question names when it is not the one you live in ('' otherwise, and when the app does
    not know your country). What you said about your right to work is about your own country: it settles nothing about
    another one, so such a question is never answered for you. (A form for a job in Prague asked about the United Kingdom.)"""
    if not _PERMIT.search(str(label or "")):
        return ""
    home = places.country_of(str(mine.get("country") or "")) \
        or filters.Placement(str(config.ui_settings().get("where") or ""), config.search_country()).home
    named = places.named_countries(str(label))
    return sorted(named)[0].title() if home and named and home not in named else ""


def decide(choices: list[dict[str, Any]], cv_text: str, mine: dict[str, str], job: dict[str, Any] | None) -> dict[int, str]:
    """{field number: answer} for the choices Claude could settle, in one call. An answer that is not
    one of the field's own options, or not a number where a number is asked, is dropped."""
    todo = [c for c in choices if c.get("kind") in ("number", "text") or c.get("options")]
    if not todo:
        return {}
    lines = []
    for c in todo:
        if c["kind"] == "number":
            lines.append(f"{c['n']}. {c['label']}\n   (a number)")
        elif c["kind"] == "text":
            lines.append(f"{c['n']}. {c['label']}\n   (a few words, copied from the CV or the facts)")
        else:
            lines.append(f"{c['n']}. {c['label']}\n   options: " + " | ".join(str(o) for o in c["options"][:60] if str(o).strip()))
    facts = facts_block(cv_text, mine, job)
    data = llm.ask_json(PROMPT.format(cv_text=cv_text[:12000], facts=facts,
                                      title=(job or {}).get("title", "not stated"), company=(job or {}).get("company", "not stated"),
                                      location=(job or {}).get("location", "not stated"), fields="\n".join(lines)),
                        system=SYSTEM, tag="form_answers")
    by_n = {c["n"]: c for c in todo}
    backing = _norm(cv_text + "\n" + facts)
    out: dict[int, str] = {}
    for item in (data.get("choices") if isinstance(data, dict) else None) or []:
        if not isinstance(item, dict) or not isinstance(item.get("n"), int) or item["n"] not in by_n \
                or not isinstance(item.get("answer"), (str, int, float)) or item["answer"] in ("", "null"):
            continue
        choice, answer = by_n[item["n"]], " ".join(str(item["answer"]).split())
        if another_country(choice["label"], mine):
            continue                                # the right to work somewhere else: yours to answer, whatever the model said
        if choice["kind"] == "number":
            if re.fullmatch(r"\d{1,3}(?:\.\d)?", answer):
                out[choice["n"]] = answer
        elif choice["kind"] == "text":              # a field the app did not recognise: only words that stand in the CV or the facts
            if 2 <= len(answer) <= 120 and _norm(answer) in backing:
                out[choice["n"]] = answer
        else:
            exact = [o for o in choice["options"] if _norm(o) == _norm(answer)]
            if exact:
                out[choice["n"]] = exact[0]
    return out
