"""The golden set of the letter checks (#78): invented people, postings and sentences in tests/fixtures/letter_evals.json,
each labelled with what the checks must say. The bar is every case as labelled, in every profession; the report names
the cases that differ, by profession, so a gain in one group cannot hide a loss in another."""
import json
from collections import defaultdict
from pathlib import Path

import pytest

from jobhelper import claims, cover_letter, store

SET = json.loads((Path(__file__).parent / "fixtures" / "letter_evals.json").read_text(encoding="utf-8"))
KINDS = ("claimed", "borrowed", "figures", "misplaced", "invented")


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
            "invented": job.get("letter_invented", [])}


def test_the_golden_set_is_well_formed():
    ids = [c["id"] for c in SET["cases"]]
    assert len(ids) == len(set(ids)) and len(ids) >= 15
    assert all(c["person"] in SET["people"] and set(c["expect"]) <= set(KINDS) for c in SET["cases"])
    assert {c["person"] for c in SET["cases"]} == set(SET["people"]), "every profession has its cases"


def test_the_letter_checks_meet_the_golden_set(isolate_data):
    wrong, by_person = [], defaultdict(lambda: [0, 0])
    for case in SET["cases"]:
        expected = {k: case["expect"].get(k, []) for k in KINDS}
        got = said(case)
        ok = {k: sorted(v) for k, v in got.items()} == {k: sorted(v) for k, v in expected.items()}
        by_person[case["person"]][0] += ok
        by_person[case["person"]][1] += 1
        if not ok:
            wrong.append(f"{case['id']}: expected {expected}, got {got}")
    report = ", ".join(f"{p} {good}/{total}" for p, (good, total) in sorted(by_person.items()))
    assert not wrong, f"golden set: {report}\n" + "\n".join(wrong)


@pytest.mark.parametrize("case", [c for c in SET["cases"] if not c["expect"]], ids=lambda c: c["id"])
def test_a_clean_case_raises_nothing(isolate_data, case):
    """Read on their own, so a false alarm names its case."""
    assert not any(said(case).values()), case["text"]
