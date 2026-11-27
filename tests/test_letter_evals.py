"""The golden set of the letter checks (#78): invented people, postings and sentences in tests/fixtures/letter_evals.json,
each labelled with what the checks must say. The bar is every case as labelled, in every profession; the report names
the cases that differ, by profession, so a gain in one group cannot hide a loss in another."""
import ast
import difflib
import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

from jobhelper import claims, cover_letter, store

SET = json.loads((Path(__file__).parent / "fixtures" / "letter_evals.json").read_text(encoding="utf-8"))
KINDS = ("claimed", "borrowed", "figures", "misplaced", "invented", "impact")
CASES = [c for c in SET["cases"] if "gap" not in c]          # a known gap runs on its own, pinned to what it says today
GAPS = [c for c in SET["cases"] if "gap" in c]


def said(case: dict) -> dict[str, list[str]]:
    """What the checks say about one case: the claim check (the never-claim list with the posting's own skills) and the
    notes a finished letter gets (cover_letter.LetterNotes)."""
    person = SET["people"][case["person"]]
    job = store.new_job(id=case["id"], title="Role", company=person["company"], description=person["posting"])
    check = claims.ClaimCheck(cover_letter.unverified_terms(person["cv"], person["posting"]))
    found = sorted({t for s in claims.sentences(case["text"]) if (t := check.claimed_in(s))})
    cover_letter.LetterNotes(job, [case["text"]], person["cv"]).put_on(job)
    return {"claimed": found, "borrowed": job.get("letter_check", []), "figures": job.get("letter_figures", []),
            "misplaced": [note.rsplit(" at ", 1)[-1] for note in job.get("letter_misplaced", [])],      # the employer, not the wording
            "invented": job.get("letter_invented", []),
            "impact": ["claim"] if job.get("letter_impact") else []}


def test_the_golden_set_is_well_formed():
    ids = [c["id"] for c in SET["cases"]]
    assert len(ids) == len(set(ids)) and len(ids) >= 15
    assert all(c["person"] in SET["people"] and set(c["expect"]) <= set(KINDS) for c in SET["cases"])
    assert all(isinstance(c.get("why", ""), str) for c in SET["cases"]), "the optional note \"why\" is text"
    assert all(len(c["gap"]) > 40 for c in GAPS), "a known gap says why it is missed"
    assert all(isinstance(c.get("now"), dict) and set(c["now"]) <= set(KINDS) for c in GAPS), "a known gap pins what it says today"
    assert {c["person"] for c in SET["cases"]} == set(SET["people"]), "every profession has its cases"


def test_the_letter_checks_meet_the_golden_set(isolate_data):
    wrong, by_person = [], defaultdict(lambda: [0, 0])
    for case in CASES:
        expected = {k: case["expect"].get(k, []) for k in KINDS}
        got = said(case)
        ok = {k: sorted(v) for k, v in got.items()} == {k: sorted(v) for k, v in expected.items()}
        by_person[case["person"]][0] += ok
        by_person[case["person"]][1] += 1
        if not ok:
            wrong.append(f"{case['id']}: expected {expected}, got {got}")
    report = ", ".join(f"{p} {good}/{total}" for p, (good, total) in sorted(by_person.items()))
    report += f"; {len(CASES) - len(wrong)}/{len(CASES)} cases pass, known gaps {len(GAPS)}"
    print(report)
    assert not wrong, f"golden set: {report}\n" + "\n".join(wrong)


@pytest.mark.parametrize("case", [c for c in CASES if not c["expect"]], ids=lambda c: c["id"])
def test_a_clean_case_raises_nothing(isolate_data, case):
    """Read on their own, so a false alarm names its case."""
    assert not any(said(case).values()), case["text"]


def kind_numbers(kind: str) -> tuple[list[str], list[str], int, int]:
    """One kind on its own (#109, #113): of the cases that must name it, the ids it misses or names wrongly; of the ones
    that must not, the ids where it still speaks. Gaps are not counted. Returns missed, false alarms, and the two totals."""
    should = [c for c in CASES if c["expect"].get(kind)]
    clean = [c for c in CASES if not c["expect"].get(kind)]
    missed = [c["id"] for c in should if sorted(said(c)[kind]) != sorted(c["expect"][kind])]
    false_alarms = [c["id"] for c in clean if said(c)[kind]]
    return missed, false_alarms, len(should), len(clean)


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_recall_and_false_alarms(isolate_data, kind):
    """Recall and false alarms per kind, so a gain in one kind or one side cannot hide a loss in another."""
    missed, false_alarms, should, clean = kind_numbers(kind)
    print(f"{kind}: recall {should - len(missed)}/{should}, false alarms {len(false_alarms)}/{clean}, known gaps {len(GAPS)}")
    assert not missed, f"missed or wrong: {missed}"
    assert not false_alarms, f"false alarms: {false_alarms}"


NEAR_COPY = 0.8                  # the share of one wording's words that a development string may repeat, in order


def words_of(text: str) -> list[str]:
    """A sentence as lower case words with no punctuation, so a changed case or a comma hides no copy."""
    return re.findall(r"[a-z0-9]+(?:['’][a-z]+)?", text.lower())


def near_copies(text: str, literals: list[str]) -> list[str]:
    """The strings among `literals` that repeat `text` or nearly: the word lists are alike (difflib ratio >= NEAR_COPY),
    or the held-out words sit unbroken inside a longer string (a prefix or a part copied, NEAR_COPY of the held-out words).
    A string shorter than the held-out sentence is a fragment ("I was a"), not a copy of it, so only the ratio judges it.
    No length pre-filter: a short sentence can be most of a long string. The two quick ratios are upper bounds, so they
    only skip what cannot match by the ratio; the containment test runs for every string with a shared word."""
    mine = words_of(text)
    if not mine:
        return []
    found = []
    for literal in literals:
        theirs = words_of(literal)
        if not theirs:
            continue
        matcher = difflib.SequenceMatcher(None, mine, theirs, autojunk=False)
        if matcher.real_quick_ratio() >= NEAR_COPY and matcher.quick_ratio() >= NEAR_COPY and matcher.ratio() >= NEAR_COPY:
            found.append(literal)
        elif len(mine) <= len(theirs) and matcher.find_longest_match(0, len(mine), 0, len(theirs)).size >= NEAR_COPY * len(mine):
            found.append(literal)
    return found


def test_the_copy_guard_sees_a_near_copy_and_passes_an_unrelated_sentence():
    seen = ["I moved the build to a new runner and cut the time by half.", "Unrelated words about something else entirely."]
    assert near_copies("i MOVED the build, to a new runner and cut the time by half!", seen) == seen[:1]
    assert near_copies("I moved the build to a new runner and trimmed the time by half.", seen) == seen[:1]     # one word changed
    assert not near_copies("At the care home I helped residents with their daily meals.", seen)


def test_the_copy_guard_sees_a_short_sentence_that_opens_a_longer_string():
    """A held-out sentence that is the start of a longer development string: the word ratio is 0.8 but the lengths differ."""
    seen = ["We mapped every bus route in the old town last winter.", "Nothing alike in this one at all."]
    assert near_copies("We mapped every bus route.", seen) == seen[:1]                       # most of the longer string, in order
    assert near_copies("I mapped every bus route in town.", seen) == []                      # a short shared run is not a copy
    assert near_copies("Every bus route in the old town last winter was mapped by a team of ten.", seen) == []      # a longer text only by the ratio


def test_no_held_out_sentence_is_a_development_row():
    """The held-out h113, h131, h142, h143 and h149 cases stay apart from the development rows in tests/test_claims.py: no string there
    repeats such a sentence, as it is or nearly (case, punctuation and a word or two aside). The h113 cases whose wording
    was seen in development were rewritten in #131: the guard exempts no case. (The inv-* and older cases are
    development rows by the fixture's own note.)"""
    tree = ast.parse((Path(__file__).parent / "test_claims.py").read_text(encoding="utf-8"))
    literals = sorted({n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                       and len(words_of(n.value)) >= 3})
    held_out = [c for c in SET["cases"] if c["id"].startswith(("h113", "h131", "h142", "h143", "h149"))]
    copies = {c["id"]: near_copies(c["text"], literals)[:1] for c in held_out if near_copies(c["text"], literals)}
    assert not copies, f"sentences copied or nearly copied into tests/test_claims.py: {copies}"


@pytest.mark.parametrize("case", GAPS, ids=lambda c: c["id"])
def test_a_known_gap_still_says_what_it_said(isolate_data, case):
    """A gap is pinned to its exact output today and must differ from its true label. When a change catches it, this
    fails: take its "gap" (and "now") off so it joins the bar."""
    norm = lambda d: {k: sorted(d.get(k, [])) for k in KINDS}
    got = said(case)
    assert norm(got) == norm(case["now"]), f"the output of a known gap changed: {got}"
    assert norm(got) != norm(case["expect"]), f"{case['id']} is caught now: take its \"gap\" (and \"now\") off so it joins the bar"
