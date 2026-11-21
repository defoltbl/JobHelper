"""German consent with the verb split around its object ("Ich stimme der Datenverarbeitung zu", "Ich willige … ein"):
the person answers it, never the model, and a tick box with such a label is never ticked."""
import re
import time

import pytest

from jobhelper import details, form_fill

SPLIT_CONSENT = ["Ich stimme der Datenverarbeitung zu", "Ich stimme den AGB zu", "Ich stimme hiermit der Verarbeitung meiner Daten zu",
                 "Stimmen Sie der Datenschutzerklärung zu?", "Ich willige in die Verarbeitung meiner Daten ein",
                 "Stimmen Sie der Speicherung Ihrer Bewerbungsunterlagen zu?", "Willigen Sie in die Weitergabe Ihrer Unterlagen ein? *",
                 "Ich stimme hiermit der Verarbeitung meiner personenbezogenen Daten gemäß der Erklärung zu.",
                 # the fail-safe choice: a skills question in the words of consent is left to the person too
                 "Stimmen Sie der Aussage zu: ich arbeite gern im Team",
                 # the informal "du" and "ihr" forms of the same verbs
                 "Stimmst du der Verarbeitung deiner Daten zu?", "Stimmt ihr der Speicherung eurer Unterlagen zu?",
                 "Willigst du in die Weitergabe deiner Unterlagen ein?", "Ihr willigt in die Speicherung ein"]
NOT_CONSENT = ["Wie viele Jahre Erfahrung haben Sie mit Python?", "Stimmt Ihre Adresse?", "Bestimmen Sie Ihren Starttermin",
               "Ich stimme mit dem Team ab", "Zuständigkeit", "Stimmen Sie zum Jahresende ab", "Sind Sie bereit, zu reisen?",
               "Stimmt die Telefonnummer noch?", "Stimmst du mit dem Team ab?", "Willigst du nur ungern ab?"]


def _field(label, kind, n=1):
    options = ["Ja", "Nein"] if kind in ("select", "radio") else []
    return {"n": n, "type": kind, "label": label, "name": "", "id": "", "auto": "", "hint": "", "filled": False, "most": 0, "options": options}


@pytest.mark.parametrize("kind", ["select", "radio"])
@pytest.mark.parametrize("label", SPLIT_CONSENT)
def test_a_split_german_consent_is_yours_to_answer(label, kind):
    assert form_fill.Field(_field(label, kind)).meaning() == ("", form_fill.CONSENT)
    assert form_fill.classify(_field(label, kind)) == ("", form_fill.CONSENT)


@pytest.mark.parametrize("label", SPLIT_CONSENT)
def test_the_plan_leaves_a_split_german_consent_to_you(label, isolate_data):
    todo = form_fill.plan([_field(label, "radio")], {**details.empty(), "first_name": "Alex"}, has_job=True)
    assert todo["choose"] == [] and todo["fill"] == [] and todo["left"] == [{"label": label, "why": form_fill.CONSENT}]


@pytest.mark.parametrize("label", SPLIT_CONSENT)
def test_a_tick_box_with_a_split_german_consent_is_never_ticked(label):
    assert form_fill.NEVER_TICK_WORDS.startswith(form_fill.CONSENT_WORDS + "|")
    assert form_fill.classify(_field(label, "checkbox")) == ("", form_fill.CHOICE)
    assert re.search(form_fill.NEVER_TICK_WORDS, label, re.IGNORECASE), "the page script refuses the box too"


@pytest.mark.parametrize("label", NOT_CONSENT)
def test_ordinary_german_questions_are_no_consent(label):
    """"stimm" inside "bestimmen", "stimmt", "stimme … ab" and "zu" inside a word or before a verb give no consent."""
    assert form_fill.classify(_field(label, "radio"))[1] != form_fill.CONSENT
    assert not re.search(form_fill.CONSENT_WORDS, label, re.IGNORECASE)


@pytest.mark.parametrize("text", ["Ich stimme " + "wort " * 2000 + "zu", "stimme a " * 5600, "stimmen" + " " * 50000 + "x",
                                  "Ich willige " + "x" * 50000 + " " + "in " * 3000 + "ein"])
def test_a_padded_label_is_read_fast(text):
    """A hostile label cannot slow the check: the word window is fixed, so each start reads at most eleven words."""
    rule = re.compile(form_fill.CONSENT_WORDS, re.IGNORECASE)
    started = time.perf_counter()
    rule.search(text)
    assert time.perf_counter() - started < 0.5


def test_the_consent_words_read_alike_in_the_page_script():
    """The page's JavaScript gets the same pattern in /…/i: no inline flag and no "/" may be in it."""
    assert not re.search(r"\(\?[a-zA-Z]", form_fill.CONSENT_WORDS) and "/" not in form_fill.CONSENT_WORDS


# ── names: a label that holds both names, a bare "Name" beside a surname field, a name that is not yours to fill ──
# (the rules were tried first name, last name, full name: "Jméno a příjmení" got only the first name, "Middle name" the whole name)
MINE = {**details.empty(), "first_name": "Alex", "last_name": "Novak"}
BOTH_NAMES = ["Jméno a příjmení", "First and last name", "Name and surname", "First name and surname", "Křestní jméno a příjmení",
              "Příjmení a jméno", "Last name, first name", "First name / Last name", "First & Last Name *"]
NOT_A_NAME_TO_FILL = ["Middle name", "Preferred name", "Nickname", "Nick name"]


def _values(labels):
    """What the plan writes into a form with these text fields, by label; and the labels it leaves to the person."""
    fields = [_field(label, "text", n) for n, label in enumerate(labels, 1)]
    todo = form_fill.plan(fields, MINE, has_job=True)
    return {i["label"]: i["value"] for i in todo["fill"]}, [i["label"] for i in todo["left"]]


@pytest.mark.parametrize("label", BOTH_NAMES)
def test_a_label_with_both_names_is_the_full_name(label):
    assert form_fill.classify(_field(label, "text")) == ("full_name", "")
    assert form_fill.detail_of(_field(label, "select")) == "full_name"


@pytest.mark.parametrize("with_surname", [False, True])
@pytest.mark.parametrize("label", BOTH_NAMES)
def test_the_plan_writes_the_whole_name_into_a_label_with_both(label, with_surname, isolate_data):
    filled, _left = _values([label, "Příjmení"] if with_surname else [label])
    assert filled[label] == "Alex Novak"


@pytest.mark.parametrize("bare, surname", [("Jméno", "Příjmení"), ("Name", "Surname"), ("Name *", "Last name"),
                                           ("Jméno *", "Příjmení *"), ("Name", "Family name")])
def test_a_bare_name_beside_a_surname_field_is_the_first_name(bare, surname, isolate_data):
    """The form asks the surname in a field of its own, so "Name" asks only the first name; in either order on the page."""
    assert _values([bare, surname])[0] == {bare: "Alex", surname: "Novak"}
    assert _values([surname, bare])[0] == {surname: "Novak", bare: "Alex"}


@pytest.mark.parametrize("bare, surname", [("Name", "Surname"), ("Jméno", "Příjmení")])
def test_a_bare_name_a_few_fields_from_a_surname_field_is_the_first_name(bare, surname, isolate_data):
    """A field or two between them is still one name block: "Name", "E-mail", "Surname"."""
    assert _values([bare, "E-mail", surname])[0] == {bare: "Alex", surname: "Novak"}
    assert _values([surname, "E-mail", bare])[0] == {surname: "Novak", bare: "Alex"}


@pytest.mark.parametrize("bare, surname", [("Name", "Surname"), ("Jméno", "Příjmení")])
def test_a_bare_name_far_from_a_surname_field_is_the_full_name(bare, surname, isolate_data):
    """A newsletter "Name" at the top and the application's "Surname" far below: the surname is no part of that name."""
    between = ["E-mail", "Phone", "City", "Postcode", "Country"][:form_fill.NAME_NEAR + 1]
    assert _values([bare, *between, surname])[0][bare] == "Alex Novak"
    assert _values([surname, *between, bare])[0][bare] == "Alex Novak"


@pytest.mark.parametrize("bare", ["Jméno", "Name", "Name *", "Jméno *"])
def test_a_bare_name_on_a_form_without_a_surname_field_is_the_full_name(bare, isolate_data):
    assert form_fill.classify(_field(bare, "text")) == ("full_name", "")
    assert _values([bare, "E-mail"])[0][bare] == "Alex Novak"


def test_a_bare_name_beside_both_first_and_last_name_fields_keeps_the_full_name(isolate_data):
    """Only a missing first-name field makes "Name" the first name: with both on the form, it stays as it was."""
    assert _values(["Name", "First name", "Last name"])[0] == {"Name": "Alex Novak", "First name": "Alex", "Last name": "Novak"}


@pytest.mark.parametrize("with_surname", [False, True])
@pytest.mark.parametrize("label", NOT_A_NAME_TO_FILL)
def test_a_middle_or_preferred_name_is_left_to_you(label, with_surname, isolate_data):
    """Not in My details: never the whole name, and never a guess from the CV ("preferred" holds "referr", so main already left it)."""
    assert form_fill.classify(_field(label, "text")) == ("", form_fill.UNKNOWN)
    filled, left = _values([label, "Příjmení"] if with_surname else [label])
    assert label not in filled and label in left


@pytest.mark.parametrize("label, what", [("First name", "first_name"), ("Last name", "last_name"), ("Full name", "full_name"),
                                         ("Your name", "full_name"), ("Křestní jméno", "first_name"), ("Name *", "full_name"),
                                         ("Surname", "last_name"), ("Příjmení", "last_name"), ("Given name", "first_name"),
                                         ("Family name", "last_name")])
def test_the_one_name_labels_keep_their_meaning(label, what):
    assert form_fill.classify(_field(label, "text")) == (what, "")


def test_a_form_with_first_and_last_name_fields_gets_each_part(isolate_data):
    assert _values(["Křestní jméno", "Příjmení"])[0] == {"Křestní jméno": "Alex", "Příjmení": "Novak"}
    assert _values(["First name", "Last name", "Full name"])[0] == {"First name": "Alex", "Last name": "Novak", "Full name": "Alex Novak"}


@pytest.mark.parametrize("word", form_fill.FIRST_NAME_WORDS)
def test_each_first_name_word_reads_alone_and_joined(word):
    """One list of words for both rules: a new first-name word is a first name alone and the whole name beside a surname."""
    assert form_fill.classify(_field(word + " name", "text")) == ("first_name", "")
    assert form_fill.classify(_field(word + " name and surname", "text")) == ("full_name", "")
    assert form_fill.classify(_field("Last name, " + word + " name", "text")) == ("full_name", "")


@pytest.mark.parametrize("word", form_fill.LAST_NAME_WORDS)
def test_each_last_name_word_reads_alone_and_joined(word):
    assert form_fill.classify(_field(word + " name", "text")) == ("last_name", "")
    assert form_fill.classify(_field("First name / " + word + " name", "text")) == ("full_name", "")
    assert form_fill.classify(_field(word + " name, first name", "text")) == ("full_name", "")
    assert form_fill.classify(_field("Name and " + word + " name", "text")) == ("full_name", ""), "a bare name joined with it"
