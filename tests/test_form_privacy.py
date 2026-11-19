"""#89: what personal data the assistant keeps to itself. A private field is never filled, and in a review of a form
its value never goes to Claude. Read by the field's name (a labelled set of hard cases on both sides) and by the
shape of the value (a card number, an IBAN, a social security number), whatever the page calls the field."""
import json
import os
import subprocess
import sys
import time
from datetime import date

import pytest

from jobhelper import api_core, chrome, details, form_fill, llm, ui_api
from tests.conftest import FIXTURES


def _field(label="", kind="text", **more):
    return {"n": 1, "type": kind, "label": label, "name": "", "id": "", "auto": "", "hint": "", "filled": False, "most": 0, "options": [], **more}


def _reviewed(*fields):
    """The review of a page with these fields: (private, value kept) for each."""
    page = form_fill.review_answer(json.dumps({"url": "https://x.example/apply", "title": "Apply", "fields": list(fields)}))
    return [(f["private"], f["value"]) for f in page["fields"]]


# private by the label: the #89 cases, and a sample of the older ones so the new rules cannot crowd them out
PRIVATE_LABELS = [
    "Card", "Debit card", "Number on card", "Token", "Secret", "Client secret", "API key", "Secret key", "SMS code", "Access code",
    "Heslo", "Číslo platební karty", "Kennwort", "Kartenprüfnummer", "Blood type", "Passphrase",
    # a key, a code or a card as the end of the label, with a hint or a mark after it; a company card is typed by you (#89)
    "Card number", "Card details", "Card details (required)", "Card PIN", "SMS code (6 digits)", "Confirmation code:", "API key*",
    "What is your API key?", "Company card", "Business card",
    "Password", "Passport photo", "Credit card number", "IBAN", "CVV", "Date of birth", "Rodné číslo", "Kreditkartennummer"]
# hard negatives: they share a word with a private field and are ordinary questions
NOT_PRIVATE_LABELS = [
    "Pass rate", "Postcode", "Code sample", "Promo code", "Referral code", "Key skills",
    "Key achievements", "Keywords", "Token economy experience", "Card design portfolio", "Secretary", "Secret Santa organiser",
    "Panel interview availability", "Access to a car", "Account manager experience", "Security clearance level",
    # a key, a code, a token or a card with more words after it, or asked as your experience (#89)
    "Auth token experience", "Payment cards experience", "Do you have experience with payment cards?", "Product code",
    "Private key infrastructure", "Private code repository link", "Authorization code grant", "Debit card processing experience",
    "Payment card industry (PCI) experience", "Prepaid card products", "Years with API key management",
    "Experience with access tokens (OAuth)", "Security tokens experience", "Product key features you shipped", "Business card design"]


@pytest.mark.parametrize("label", PRIVATE_LABELS)
def test_a_private_label_is_left_to_you_and_its_value_stays_out_of_the_review(label):
    assert form_fill.classify(_field(label)) == ("", form_fill.PRIVATE)
    assert _reviewed({"label": label, "value": "x1"}) == [(True, "")]


@pytest.mark.parametrize("label", NOT_PRIVATE_LABELS)
def test_a_label_that_only_shares_a_word_with_a_private_one_is_not_private(label):
    assert form_fill.classify(_field(label))[1] != form_fill.PRIVATE
    assert _reviewed({"label": label, "value": "x1"}) == [(False, "x1")]


@pytest.mark.parametrize("name", ["pass", "acct_no", "nin", "pan", "passphrase", "api_key", "access_token", "client-secret", "debitCard",
                                  "sms_code"])
def test_a_private_inner_name_behind_a_plain_label_is_left_to_you(name):
    assert form_fill.classify(_field("Your answer", name=name)) == ("", form_fill.PRIVATE)
    assert form_fill.classify(_field("Your answer", id=name)) == ("", form_fill.PRIVATE)


@pytest.mark.parametrize("name", ["pass_rate", "panel", "nine", "token_economy", "secretary", "keywords", "api_key_management",
                                  "payment_card_experience", "product_code"])
def test_an_inner_name_that_only_starts_like_a_private_one_is_not_private(name):
    assert form_fill.classify(_field("Your answer", name=name))[1] != form_fill.PRIVATE


@pytest.mark.parametrize("label", ["Ｐａｓｓｗｏｒｄ", "Pass​word", "Pass­word", "Pass⁠word", "﻿Password",
                                   "Ｃａｒｄ ｎｕｍｂｅｒ", "He​slo", "Kartenprüfnummer", "Číslo platební karty",
                                   "Pass\u180eword", "Pass\u2061word", "Pass\u200fword", "Pass\u202eword"])
def test_a_label_written_in_look_alike_or_hidden_signs_is_read_as_it_shows(label):
    """Fullwidth letters, zero-width signs, soft hyphens and the other format signs (a Mongolian vowel separator, an
    invisible function sign, bidi marks) hid a private label; a letter and its separate accent are one."""
    assert form_fill.classify(_field(label)) == ("", form_fill.PRIVATE)
    assert form_fill.classify(_field("Your answer", name=label)) == ("", form_fill.PRIVATE)


def test_the_plain_words_of_a_field_fold_look_alike_signs_and_keep_accented_letters():
    assert form_fill._words({"label": "Ｆｉｒｓｔ​Ｎａｍｅ"}) == "first name"
    assert form_fill._words({"label": "Číslo účtu"}) == "číslo účtu" == form_fill._words({"label": "Číslo účtu"})
    assert form_fill._words({"label": "Straße"}) == "straße"


PRIVATE_VALUES = [
    "4111111111111111", "4111 1111 1111 1111", "4111-1111-1111-1111", "4111/1111/1111/1111", "My card is 4111.1111.1111.1111, thanks",
    "Ref 12 4111 1111 1111 1111", "3782 822463 10005", "４１１１ １１１１ １１１１ １１１１", "4111​1111​1111​1111",
    "CZ65 0800 0000 1920 0014 5399", "cz6508000000192000145399", "IBAN: DE89 3704 0044 0532 0130 00 please",
    "GB82 WEST 1234 5698 7654 32", "My IBAN is CZ65 0800 0000 1920 0014 5399 thanks", "NO93 8601 1117 947",
    "123-45-6789", "SSN 078-05-1120.",
    # #89: any gap the person may type between a card's groups, one kind all through; an IBAN in groups cut by dashes
    "4111  1111 1111 1111", "4111\n1111\n1111\n1111", "4111 - 1111 - 1111 - 1111", "4111\t1111\t1111\t1111", "4111_1111_1111_1111",
    "4111,1111,1111,1111", "4111\u20101111\u20101111\u20101111", "4111\u20151111\u20151111\u20151111", "3056 930902 5904",
    "CZ65  0800 0000 1920 0014 5399", "CZ65-0800-0000-1920-0014-5399"]
NOT_PRIVATE_VALUES = [
    "+420 777 123 456", "+1 (555) 010-0199", "+44 20 7946 0958", "Order 4111-1111-1111-1112", "1234 5678 9012 3456",
    "2024-05-01", "01/05/2024", "110 00", "SW1A 1AA", "2019-2024", "50.000", "CZ65 0800 0000 1920 0014 5398",
    "ISO 9001 and ISO 27001", "000-12-3456", "666-12-3456", "912-34-5678", "123-00-4567", "123-45-0000", "1234-45-6789",
    "I led a team of 12 people from 2019 to 2024", "፩" * 16,
    # #89: lists that pass the Luhn check when their groups are run together, but are no card's print: year ranges,
    # dates, versions, phones; groups of 6 to 9 digits
    "2019-2021 2021-2023 2023-2025 2017-2019", "1.5.2024 2.6.2024 3.7.2024 4.8.2024 5.9.2024", "v10.20.30 2024.11.14 1.2.3",
    "+420 777 123 456, +420 608 111 222, +420 731 000 999", "424242 424242 4242",
    "1.2.2019 3.4.2020 5.6.2021 7.8.2022 9.10.2023", "10:30", "1|2|3"]


@pytest.mark.parametrize("value", PRIVATE_VALUES)
def test_a_value_shaped_like_a_card_an_iban_or_a_social_security_number_stays_out_of_the_review(value):
    """The review read only a whole value of digits as a card; a card in a sentence, an IBAN or an SSN in a
    "Reference" or "Notes" box went to Claude."""
    assert form_fill.PrivateShape(value).found
    assert _reviewed({"label": "Notes", "value": value}) == [(True, "")]


@pytest.mark.parametrize("value", NOT_PRIVATE_VALUES)
def test_a_phone_a_date_a_postcode_or_a_number_that_fails_its_check_is_not_private(value):
    assert not form_fill.PrivateShape(value).found
    assert _reviewed({"label": "Notes", "value": value}) == [(False, value)]


def test_a_card_number_with_a_typo_is_not_private():
    """#89 point a: a mistyped card number fails the Luhn check and cannot be told from any other 16-digit number, so it
    is not withheld (closed with this reason). The same number typed right is."""
    assert form_fill.PrivateShape("4111111111111111").card and not form_fill.PrivateShape("4111111111111112").found
    assert not form_fill.PrivateShape("4111 1111 1111 1121").found


def test_a_number_like_a_social_security_number_with_spaces_or_no_dashes_is_not_one():
    """An SSN is read with its dashes only: "123 45 6789" is as likely a phone, and a bare 9-digit run is any number."""
    assert not form_fill.PrivateShape("123 45 6789").found and not form_fill.PrivateShape("123456789").found


def test_a_review_sends_claude_no_private_value_no_password_and_no_consent_answer(isolate_data, monkeypatch):
    """The boundary itself: the whole review, from the page's report to the one prompt, with the model call stubbed.
    A card number in a "Notes" box, a "Password" field's value and a consent list's answers never reach the prompt;
    an ordinary answer does."""
    page = {"url": "https://careers.northwind.example/jobs/42", "title": "Apply", "fields": [
        {"label": "Notes", "value": "Pay with 4111 1111 1111 1111 please", "kind": "textarea", "name": "notes"},
        {"label": "Password", "value": "Tr0ub4dor&3", "kind": "text", "name": "pw"},
        {"label": "Your answer", "value": "I agree", "kind": "select", "name": "q_7", "options": ["Please select", "I agree", "I do not agree"]},
        {"label": "Why Northwind?", "value": "I built SQL reports at Globex.", "kind": "textarea", "name": "why"}]}
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: "Alex Novak\nJunior analyst. SQL, Excel, Python.")
    monkeypatch.setattr(chrome, "active_tab", lambda: {"url": page["url"], "title": page["title"]})
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps(page))
    prompts = []
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: prompts.append(prompt + "\n" + str(kw.get("system") or "")) or {"problems": []})
    assert ui_api.Api().assistant_review()["ok"]
    assert len(prompts) == 1 and "I built SQL reports at Globex." in prompts[0]
    for never in ("4111", "Tr0ub4dor&3", "Password", "I agree", "I do not agree", "Your answer"):
        assert never not in prompts[0], never


def test_each_shape_is_told_apart():
    card, iban, ssn = (form_fill.PrivateShape(v) for v in ("4111 1111 1111 1111", "CZ65 0800 0000 1920 0014 5399", "123-45-6789"))
    assert (card.card, card.iban, card.ssn) == (True, False, False)
    assert (iban.card, iban.iban, iban.ssn) == (False, True, False)
    assert (ssn.card, ssn.iban, ssn.ssn) == (False, False, True)
    assert not form_fill.PrivateShape("").found and not form_fill.PrivateShape(None).found


@pytest.mark.parametrize("value", ["1 " * 25_000, "1-" * 25_000, "1" * 50_000, "AB12 " * 10_000, "ab12" * 12_500,
                                   "123-45-" * 7_000, "a" * 50_000, "1111 " * 10_000, "1111 - " * 7_000, "1 \u2010\n" * 16_000,
                                   "1111" + " " * 50_000 + "1", "AB12  " * 8_000, "ab12-" * 10_000, "\u200b" * 50_000,
                                   "1:|+\u00b7\u2212" * 10_000, "1111:|" * 8_000, "ab12._/" * 7_000, "123\u2010" * 12_500,
                                   "123\u201045\u2015" * 6_000])
def test_a_long_hostile_value_is_read_at_once(value):
    """The shape rules read text from the page: no rule may try every way to split a long run. "1 1 1 …" and "1111 1111
    …" never pass the Luhn check (13 to 19 ones sum to 19, 21, 22, 24, 25, 27, 28), so every window is read."""
    start = time.perf_counter()
    found = form_fill.PrivateShape(value).found
    assert time.perf_counter() - start < 1.5 and not found


@pytest.mark.parametrize("text", ["a" * 50_000, "token " * 8_000 + "x", "pass" + " " * 50_000 + "x", "api " * 12_000 + "x",
                                  "(" * 50_000, "(a" * 25_000, "api key " * 6_000 + "x", "debit card" + " " * 50_000 + "x",
                                  "é\u200b" * 25_000, "experience " * 4_500 + "api key"])
def test_a_long_hostile_label_is_read_at_once(text):
    start = time.perf_counter()
    form_fill._private({"label": text, "hint": text, "name": text, "id": text})
    assert time.perf_counter() - start < 1.5


# ── #89, second part: consent read by a list's options in a review, consent names, the current-job box, "to" in a question ──
# (P1b) Each rule below read page words too eagerly or too little; each set holds the hard cases on both sides.


def _on_a_page(tmp_path, html, *scripts):
    """The scripts' answers on a page of our own, in a real browser engine with no network (as test_assistant's _in_page)."""
    page = tmp_path / "form.html"
    page.write_text(html, encoding="utf-8")
    done = subprocess.run([sys.executable, str(FIXTURES / "run_in_page.py"), str(page)], input=json.dumps(list(scripts)),
                          capture_output=True, text=True, timeout=120, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert "Traceback" not in done.stderr, done.stderr[-1500:]
    if done.returncode != 0:
        said = f"the browser engine did not start here: {done.stderr[-200:]}"
        pytest.fail(said) if os.environ.get("CI") else pytest.skip(said)
    return json.loads(done.stdout), page.resolve().as_uri()


# d) a list or radios with a plain label: consent by its options, in the review as in the planner
REVIEWED_CHOICES = [  # (label, kind, options, chosen, consent)
    ("Your answer", "select", ["Please select", "Yes", "I agree"], "Yes", True),
    ("Please select", "radio", ["Accept", "Decline"], "Accept", True),
    ("Your answer", "radio", ["Yes", "I agree"], "I agree", True),
    ("Please select", "select", ["Please select", "Agree", "Disagree"], "Disagree", True),
    ("Your answer", "radio", ["Yes", "No"], "Yes", False),
    ("Do you agree to relocate?", "select", ["Yes", "No"], "No", False),
    ("Country", "select", ["Select", "Czechia", "Germany"], "Germany", False),
    ("How did you hear about us?", "select", ["LinkedIn", "Company newsletter", "Job alerts email"], "Company newsletter", False),
    ("Your answer", "menu", ["Accept", "Decline"], "Accept", True), ("Your answer", "menu", ["Yes", "No"], "No", False)]


@pytest.mark.parametrize("label, kind, options, chosen, consent", REVIEWED_CHOICES)
def test_a_review_reads_a_lists_options_as_the_planner_does(label, kind, options, chosen, consent):
    """The review read consent from a list's label only, so "Your answer" with "Yes" / "I agree" went to Claude with its
    answer; the planner reads the options and leaves such a list to you. Both now ask one rule."""
    assert _reviewed({"label": label, "kind": kind, "options": options, "value": chosen}) == [(consent, "" if consent else chosen)]
    assert (form_fill.classify(_field(label, kind, options=options)) == ("", form_fill.CONSENT)) is consent


def test_a_review_with_options_in_a_wrong_shape_reads_none_of_them():
    assert _reviewed({"label": "Your answer", "kind": "select", "options": "I agree", "value": "Yes"},
                     {"label": "Your answer", "kind": "radio", "options": [None, 7, "No"], "value": "No"}) == [(False, "Yes"), (False, "No")]
    assert _reviewed({"label": "Your answer", "kind": "text", "options": ["I agree"], "value": "Blue"}) == [(False, "Blue")], \
        "a text box is read by its label and name, as the planner reads it"


# e) a text box named for consent only by its whole name
CONSENT_NAMES = ["consent", "consent_text", "accept_terms", "gdpr_consent", "terms_agree", "acceptTerms", "TermsAndConditions",
                 "i_agree", "consent-1", "agreeCheckbox", "gdpr[consent][0]",
                 # consent on main, kept: a consent word with other words that say nothing else the box holds (#89)
                 "consent_required", "marketing_consent", "agree_to_terms", "termsAccepted", "form[consent]", "gdpr_consent_required",
                 "privacy_consent", "data_processing_consent", "i_agree_to_the_terms", "terms_and_conditions_accepted", "acceptedTerms",
                 "tos_agree", "consentGiven", "agreement_type"]
# a consent word beside a noun that says what else the box holds: a link, an address, a phone, a date, notes
NOT_CONSENT_NAMES = ["agreement_url", "terms_email", "acceptance_date", "contract_terms_notes", "gdpr_experience",
                     "consent_management_tool", "opt_in_comments", "text_box", "terms_link", "consent_phone", "privacy_consent_website"]


@pytest.mark.parametrize("name", CONSENT_NAMES)
def test_a_text_box_the_page_names_for_consent_is_yours(name):
    for where in ("name", "id"):
        assert form_fill.classify(_field("Your answer", **{where: name})) == ("", form_fill.CONSENT), where
        assert _reviewed({"label": "Your answer", where: name, "value": "x1"}) == [(True, "")], where


@pytest.mark.parametrize("name", NOT_CONSENT_NAMES)
def test_one_consent_word_inside_a_longer_name_is_no_consent(name):
    """#89: name="agreement_url" on a "Portfolio" box and name="terms_email" on an email box were refused as consent."""
    assert form_fill.classify(_field("Your answer", name=name))[1] != form_fill.CONSENT
    assert _reviewed({"label": "Your answer", "name": name, "value": "x1"}) == [(False, "x1")]


def test_a_portfolio_or_an_email_box_with_a_consent_word_in_its_name_is_filled():
    assert form_fill.classify(_field("Portfolio", name="agreement_url")) == ("website", "")
    assert form_fill.classify(_field("Email", kind="email", name="terms_email")) == ("email", "")


@pytest.mark.parametrize("name", ["consent " * 7_000 + "x", "1 " * 25_000 + "x", "agree" * 10_000, "i " * 25_000, "url_" * 12_500,
                                  "consent e" * 6_000 + "mail"])
def test_a_long_hostile_name_is_read_at_once(name):
    start = time.perf_counter()
    form_fill._consent({"label": "", "name": name, "id": name})
    assert time.perf_counter() - start < 1.5


# f) the "I work here now" box: its label decides; an inner name vetoes it only with a consent word
@pytest.mark.parametrize("more", [{"id": "current_notify_1"}, {"name": "contact_current"}, {"name": "notify", "id": "contact"}])
def test_the_current_job_box_is_ticked_whatever_its_inner_name_says_about_contact(more):
    """#89: "notify" or "contact" in the inner name of a box labelled "I currently work here" refused the tick."""
    box = _field("I currently work here", "checkbox", n=2, **more)
    assert form_fill.classify(box) == ("current_box", "")
    job = {"employer": "Northwind", "title": "Junior analyst", "start": "03/2023", "end": "", "location": "", "description": "", "current": True}
    todo = form_fill.plan([_field("Company", n=1), box], {**details.empty(), "experience": [job]})
    assert todo["tick"] == [{"n": 2, "label": "I currently work here"}]


@pytest.mark.parametrize("label, more", [
    ("", {"name": "notify_me"}), ("", {"id": "contact_me"}), ("I currently work here", {"name": "accept_terms"}),
    ("I currently work here", {"name": "gdpr_current"}), ("I currently work here", {"id": "marketing_consent"}),
    ("I currently work here", {"name": "newsletter"}), ("Current", {"name": "terms_and_conditions"}),
    ("Notify me", {"id": "current"}), ("Contact me about this job", {"name": "current_job"}), ("Keep me updated", {"name": "current"}),
    # #89: a word of privacy or marketing in the inner name refuses the tick too
    ("I currently work here", {"name": "privacy_current"}), ("I currently work here", {"name": "policy_current"}),
    ("I currently work here", {"id": "marketing_current"}), ("I currently work here", {"name": "marketing"}),
    ("I currently work here", {"name": "tos"}), ("I currently work here", {"id": "ccpa"})])
def test_a_box_that_notifies_or_agrees_is_never_ticked(label, more):
    assert form_fill.classify(_field(label, "checkbox", **more)) == ("", form_fill.CHOICE)


CURRENT_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Apply</title></head><body>
<form onsubmit="window.sent = true; return false;">
  <p><input type="checkbox" id="current_notify_1" name="contact_current"><label for="current_notify_1">I currently work here</label></p>
  <p><input type="checkbox" id="x2" name="notify_me"><label for="x2">Notify me about similar jobs</label></p>
  <p><label for="pick">Your answer</label><select id="pick" name="q_7"><option value="">Please select</option><option>Yes</option>
     <option selected>I agree</option></select></p>
  <fieldset><legend>Please select</legend><label><input type="radio" name="q_8" value="a" checked>Accept</label>
     <label><input type="radio" name="q_8" value="d">Decline</label></fieldset>
  <fieldset><legend>Do you agree to relocate?</legend><label><input type="radio" name="q_9" value="y" checked>Yes</label>
     <label><input type="radio" name="q_9" value="n">No</label></fieldset>
</form></body></html>"""


def test_the_page_scripts_read_ticks_and_consent_options_as_plan_does(tmp_path):
    """In a real browser engine: READ reports the current-job box behind its "contact" name and leaves out the "Notify me"
    box; CHOOSE ticks it (the label read again); REVIEW reports a list's and a radio set's options, so the two consent
    answers stay out of the review and the relocation answer goes on."""
    first, url = _on_a_page(tmp_path, CURRENT_PAGE, form_fill.READ, form_fill.REVIEW)
    read = form_fill.read_answer(first[0])
    boxes = [f for f in read["fields"] if f["type"] == "checkbox"]
    assert [(b["n"], b["label"]) for b in boxes] == [(1, "I currently work here")]
    assert form_fill.classify(boxes[0]) == ("current_box", "")
    reviewed = form_fill.review_answer(first[1])["fields"]
    assert [(f["label"], f["private"], f["value"]) for f in reviewed] == [
        ("Your answer", True, ""), ("Please select", True, ""), ("Do you agree to relocate?", False, "Yes")]
    ticked, _ = _on_a_page(tmp_path, CURRENT_PAGE, form_fill.READ, form_fill.choose_script("tick", 1, "", url),
                           "JSON.stringify([document.getElementById('current_notify_1').checked, !!window.sent])")
    assert form_fill.choose_answer(ticked[1])["ok"] is True and json.loads(ticked[2]) == [True, False]


# g) "to" in a question is no job's end date
@pytest.mark.parametrize("label, kind", [
    ("Do you agree to relocate?", "select"), ("Do you agree to relocate?", "text"), ("Do you agree to relocate?", "radio"),
    ("Do you agree to relocate?", "date"), ("Do you agree to relocate?", "month"), ("Are you willing to start within a month?", "date"),
    ("Are you willing to start within a month?", "month"), ("Are you able to travel on these dates?", "date"),
    ("Are you able to travel on these dates?", "month"), ("Are you able to travel on these dates?", "select"),
    ("Happy to travel to Berlin?", "select"),
    ("Do you agree to relocate", "select"), ("Would you be willing to relocate to Prague?", "select"),
    ("Which year did you move to Prague", "select"), ("Are you willing to relocate within a month?", "select"),
    ("Are you willing to start within a month?", "select"), ("Are you able to travel on these dates?", "text"),
    ("Willing to travel to clients (days per month)", "select")])
def test_a_question_with_to_or_start_in_it_is_no_jobs_date(label, kind):
    """#89: "Do you agree to relocate?" as a list was read as the end of a job and filled with a year."""
    assert form_fill.classify(_field(label, kind, options=["Yes", "No"]))[0] not in ("row_start", "row_end")


@pytest.mark.parametrize("field, what", [
    (_field("To", "date"), "row_end"), (_field("To*", "month"), "row_end"), (_field("To year", "select"), "row_end"),
    (_field("To (month)", "select"), "row_end"), (_field("Date to", "month"), "row_end"), (_field("Dates: to (MM/YYYY)"), "row_end"),
    (_field("Until", "month"), "row_end"), (_field("End date", "select"), "row_end"), (_field("To present", "month"), "row_end"),
    (_field("Month", "select", name="work[0][to]"), "row_end"), (_field("Year", "select", name="to_year"), "row_end"),
    (_field("Month", "select", name="date_to"), "row_end"), (_field("Year", n=1, part="year", group="To*"), "row_end"),
    (_field("From", "month"), "row_start"), (_field("Start date", "select"), "row_start"), (_field("Month", n=1, part="month", group="From"), "row_start"),
    # #89: what main read as a job's date, kept: a question about when, and "to" before a hint
    *[(_field(label, kind, options=["Jan", "Feb"] if kind == "select" else []), "row_start")
      for label in ("When did you start this job?", "Start date (MM/YYYY)?") for kind in ("date", "month", "select")],
    *[(_field(label, kind, options=["Jan", "Feb"] if kind == "select" else []), "row_end")
      for label in ("To (optional)", "To (e.g. 03/2022)", "To (if applicable)", "To (or leave blank)", "To Mon/YYYY", "To the present", "To:",
                    "To", "To year", "Date to", "Worked here to", "Period to") for kind in ("month", "select")],
    *[(_field("Month", "select", name=name, options=["Jan"]), "row_end") for name in ("to_month", "toMonth", "employment_to", "date_to")],
    (_field("To", "select", name="q_12", options=["Jan"]), "row_end"), (_field("From – To", "month"), "row_start"),
    (_field("Period from", "month"), "row_start"), (_field("Od", "month"), "row_start"), (_field("Datum od", "month"), "row_start")])
def test_the_short_labels_of_a_jobs_dates_still_count(field, what):
    """"Period to" was read as a start: "od" (Czech "from") matched the end of "period". "From – To" in one field is
    read as a start, as main reads it."""
    assert form_fill.classify(field) == (what, "")


@pytest.mark.parametrize("label", ["to a " * 12_500, "to " * 16_000 + "x", "to" + " " * 50_000 + "x", "date to ? " * 5_000,
                                   "to the " * 7_000 + "x", "? " * 25_000, "are you " * 6_000, "when " * 10_000 + "?", "od" * 25_000])
def test_a_long_hostile_date_label_is_read_at_once(label):
    start = time.perf_counter()
    form_fill.classify(_field(label, "select"))
    assert time.perf_counter() - start < 1.5


# #89 round 3: a card printed with mixed gaps or other gap signs, an IBAN with dots, underscores or slashes, an SSN with
# a typographic dash
@pytest.mark.parametrize("value", [
    "4111-1111 1111-1111", "4111 - 1111 1111-1111", "4111 1111-1111.1111", "Card: 4111-1111 1111-1111, thanks",
    "4111:1111:1111:1111", "4111|1111|1111|1111", "4111+1111+1111+1111", "4111·1111·1111·1111",
    "4111−1111−1111−1111", "CZ65.0800.0000.1920.0014.5399", "CZ65_0800_0000_1920_0014_5399",
    "CZ65/0800/0000/1920/0014/5399", "123‐45‐6789", "123\u201445-6789"])
def test_a_card_with_mixed_or_other_gaps_an_iban_with_dots_and_an_ssn_with_a_dash_are_private(value):
    """Main stripped every space and dash from a value, so "4111-1111 1111-1111" was a card there; the group reading
    must still find it."""
    assert form_fill.PrivateShape(value).found
    assert _reviewed({"label": "Notes", "value": value}) == [(True, "")]


@pytest.mark.parametrize("value", ["2019-2021 2021-2023 2023-2025 2017-2019", "1.2.2019 3.4.2020 5.6.2021 7.8.2022 9.10.2023",
                                   "123 45 6789", "10:30", "1|2|3", "2012-2013 2013-2018", "2012–2013, 2013–2018",
                                   "From 2012-2013 2013-2018 2018-2020", "1999-2004 2004-2012 2012",
                                   "1005 2019-2021 2021-2023", "Room 1005, 2012-2013 2013-2018", "Room 1002, 2012-2013 2013-2018",
                                   "1234-2019 2020-2021 5", "1001-2019 2020-2021 5"])
def test_a_list_of_years_dates_or_times_with_mixed_gaps_is_not_private(value):
    """Mixed gaps do not make a card of a list whose groups all look like years, dates or times."""
    assert not form_fill.PrivateShape(value).found
    assert _reviewed({"label": "Notes", "value": value}) == [(False, value)]


@pytest.mark.parametrize("value", ["4111-1111 1111-1111 123", "Card 4111-1111 1111-1111, 12/26", "4111 1111-1111 1111 and 12/26",
                                   "12:30 4111-1111 1111-1111 3"])  # the last one holds a real card after a time
def test_a_card_with_mixed_gaps_inside_a_longer_run_of_digits_is_private(value):
    assert form_fill.PrivateShape(value).found
    assert _reviewed({"label": "Notes", "value": value}) == [(True, "")]


@pytest.mark.parametrize("sign", ["\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212"])
def test_every_dash_sign_and_the_minus_is_read_like_a_hyphen_in_a_card_and_an_ssn(sign):
    assert form_fill.PrivateShape(f"4111{sign}1111{sign}1111{sign}1111").found
    assert form_fill.PrivateShape(f"123{sign}45{sign}6789").found


@pytest.mark.parametrize("value", ["2019 4111-1111 1111-1111", "4111 1111 1111 1111 2020-2021"])
def test_a_card_next_to_a_year_is_still_private(value):
    assert form_fill.PrivateShape(value).found


@pytest.mark.parametrize("point", form_fill._DASH_POINTS)
def test_an_iban_with_any_dash_or_the_minus_as_its_gap_is_private(point):
    """The IBAN's gaps were only spaces, dots, underscores, slashes and the hyphen, so "CZ65–0800–…" went to Claude."""
    sign = chr(point)
    assert form_fill.PrivateShape(sign.join(["CZ65", "0800", "0000", "1920", "0014", "5399"])).iban
    assert not form_fill.PrivateShape(sign.join(["CZ65", "0800", "0000", "1920", "0014", "5398"])).iban   # bad check digits


def test_a_long_hostile_iban_value_reads_fast():
    started = time.perf_counter()
    assert not form_fill.PrivateShape("ab12\u2013" * 10000).found
    assert time.perf_counter() - started < 1.5


@pytest.mark.parametrize("label, kind", [(label, kind) for label in (
    "Open to March", "Free to May", "Move to May", "Relocate to March", "Contract to March", "Reply to Mar",
    "Date moved to May") for kind in ("month", "select")])
def test_a_month_after_a_to_inside_the_label_is_no_jobs_date(label, kind):
    """A month's name ends a job's dates only after a "to" that opens the label: "Open to March" asks you."""
    assert form_fill.classify(_field(label, kind, options=["Jan", "Feb"] if kind == "select" else []))[0] != "row_end"


@pytest.mark.parametrize("label, kind, what", [
    *[(label, kind, what) for label, what in (("From?", "row_start"), ("To Sept", "row_end"), ("To?", "row_end"), ("To Jan", "row_end"),
                                              ("To January", "row_end"), ("To Quarter", "row_end"),
                                              ("To quarter (Q1-Q4)", "row_end")) for kind in ("month", "select")]])
def test_a_short_date_label_with_a_mark_or_a_month_still_counts_as_a_jobs_date(label, kind, what):
    assert form_fill.classify(_field(label, kind, options=["Jan", "Feb"] if kind == "select" else [])) == (what, "")


@pytest.mark.parametrize("label, kind", [("Ready to start?", "select"), ("Free to start?", "select"), ("Start now?", "select"),
                                         ("Ready to start?", "month"), ("Free to start?", "month"), ("Start now?", "month")])
def test_a_short_question_about_starting_work_is_no_jobs_date(label, kind):
    assert form_fill.classify(_field(label, kind, options=["Yes", "No"]))[0] not in ("row_start", "row_end")


@pytest.mark.parametrize("value", ["4111-1111 " * 5000, "2019-2020 " * 5000])
def test_a_long_hostile_value_is_read_for_a_card_at_once(value):
    start = time.perf_counter()
    form_fill.PrivateShape(value).found
    assert time.perf_counter() - start < 1.5


@pytest.mark.parametrize("label", ["to jan " * 7000, "to quarter " * 4500, "? " * 25000])
def test_a_long_hostile_short_date_label_is_read_at_once_by_the_new_rules(label):
    start = time.perf_counter()
    form_fill.classify(_field(label, "month"))
    assert time.perf_counter() - start < 1.5


@pytest.mark.parametrize("name", ["working_conditions", "medical_conditions", "conditions", "workingConditions"])
def test_conditions_alone_in_a_name_is_no_consent(name):
    assert form_fill.classify(_field("Your answer", name=name))[1] != form_fill.CONSENT
    assert not form_fill._consent_name(name)


@pytest.mark.parametrize("name", ["terms_and_conditions", "TermsAndConditions", "termsConditions"])
def test_conditions_beside_terms_is_consent_and_its_box_is_never_ticked(name):
    assert form_fill._consent_name(name)
    assert form_fill.classify(_field("Your answer", name=name)) == ("", form_fill.CONSENT)
    assert form_fill.classify(_field("I currently work here", "checkbox", name=name)) == ("", form_fill.CHOICE)


@pytest.mark.parametrize("kind", ["month", "select"])
def test_to_when_is_a_jobs_end_date_again(kind):
    """Main read "To when?" as a job's end date; "Do you agree to relocate?" stays a question."""
    options = ["Jan", "Feb"] if kind == "select" else []
    assert form_fill.classify(_field("To when?", kind, options=options)) == ("row_end", "")
    assert form_fill.classify(_field("Do you agree to relocate?", kind, options=options))[0] not in ("row_start", "row_end")


def test_the_review_reads_a_lists_consent_by_its_kind_alone():
    """The page's review script sends no "combo" flag: a list is read by its options, a text box by its words."""
    assert _reviewed({"label": "Your answer", "kind": "select", "name": "q_7", "value": "I agree",
                      "options": ["Please select", "I agree", "I do not agree"]}) == [(True, "")]
    assert _reviewed({"label": "Your answer", "kind": "text", "name": "q_8", "value": "Blue"}) == [(False, "Blue")]


# #139: a yes-or-no list behind a one-word "?" label asks you; it holds no job's date
YES_NO_OPTIONS = [["Yes", "No"], ["", "Yes", "No"], ["Select…", "Yes", "No"], ["-- Please choose --", "yes", "no"], ["Choose one", "YES.", "NO."],
                  ["Ano", "Ne"], ["Vyberte", "ano", "ne"], ["Ja", "Nein"], ["Bitte wählen", "Ja", "Nein"], ["Sí", "No"], ["Si", "No"],
                  ["Oui", "Non"], ["Ｙｅｓ", "Ｎｏ"]]


@pytest.mark.parametrize("label", ["Started?", "Ended?", "From?", "To?", "Start?", "End?"])
@pytest.mark.parametrize("options", YES_NO_OPTIONS)
def test_a_one_word_question_with_yes_and_no_is_a_choice_and_never_a_date(label, options):
    """A "Started?" list with "Yes" / "No" was read as a job's start and left with "Pick the date yourself."."""
    field = _field(label, "select", options=options)
    assert form_fill.classify(field) == ("choice", "")
    job = {"employer": "Northwind Traders", "title": "Clerk", "start": "2020-01", "end": "", "current": True}
    todo = form_fill.plan([field], {**details.empty(), "experience": [job]})
    assert all(left["why"] != form_fill.DATE for left in todo["left"])
    assert [entry["n"] for entry in todo["choose"]] == [1]


@pytest.mark.parametrize("label, options, what", [
    ("From?", ["Jan", "Feb", "Mar"], "row_start"), ("From?", ["Select…", "January", "February"], "row_start"),
    ("From?", ["", "2019", "2020", "2021"], "row_start"), ("To?", ["Jan", "Feb"], "row_end"), ("To?", ["2019", "2020"], "row_end"),
    ("Started?", ["2019", "2020"], "row_start"), ("Ended?", ["Jan", "Feb"], "row_end"),
    ("Started?", ["Yes", "No", "2020"], "row_start")])
def test_a_one_word_date_list_with_months_or_years_still_counts_as_a_jobs_date(label, options, what):
    assert form_fill.classify(_field(label, "select", options=options)) == (what, "")


@pytest.mark.parametrize("label, kind, what", [("Started?", "month", "row_start"), ("Ended?", "date", "row_end"), ("From?", "date", "row_start")])
def test_a_one_word_date_field_keeps_its_jobs_date(label, kind, what):
    assert form_fill.classify(_field(label, kind, options=["Yes", "No"])) == (what, "")


NEW_HIDDEN = ["͏", "ㅤ", "⠀", "︀", "️", "\U000e0100", "\U000e01ef", "ᅟ", "ᅠ", "ﾠ"]
NEW_DASHES = ["⁃", "֊", "・"]


@pytest.mark.parametrize("sign", NEW_HIDDEN)
def test_a_card_an_ssn_and_an_iban_hidden_with_a_blank_sign_are_private(sign):
    for value in ("4111 1111 1111 1111", "123-45-6789", "CZ65 0800 0000 1920 0014 5399"):
        hidden = sign.join(value)
        assert form_fill.PrivateShape(hidden).found, (hidden, value)
        assert _reviewed({"label": "Notes", "value": hidden}) == [(True, "")]


@pytest.mark.parametrize("sign", NEW_HIDDEN)
def test_a_label_written_with_a_blank_sign_is_read_as_it_shows(sign):
    assert form_fill.classify(_field(sign.join("Password"))) == ("", form_fill.PRIVATE)


# the Default_Ignorable_Code_Point signs outside Cf that the first list missed (fix round 1 of #139)
IGNORABLE_HIDDEN = ["឴", "឵", "᠋", "᠌", "᠍", "᠏", "⁥", "￰", "￸",
                    "\U000e0000", "\U000e0020", "\U000e0080", "\U000e01f0", "\U000e0fff"]


@pytest.mark.parametrize("sign", IGNORABLE_HIDDEN)
def test_a_card_an_ssn_an_iban_and_a_label_hidden_with_an_ignorable_sign_are_private(sign):
    assert form_fill.PrivateShape(sign.join(["4111", "1111", "1111", "1111"])).card
    assert form_fill.PrivateShape(sign.join("123-45-6789")).ssn
    assert form_fill.PrivateShape(sign.join("CZ65 0800 0000 1920 0014 5399")).iban
    assert form_fill.PrivateShape(sign.join("4111 1111 1111 1111")).card
    assert _reviewed({"label": "Notes", "value": f"Card 4111{sign}1111{sign}1111{sign}1111, thanks"}) == [(True, "")]
    assert form_fill.classify(_field(sign.join("Password"))) == ("", form_fill.PRIVATE)
    assert not form_fill.PrivateShape(sign.join(["4111", "1111", "1111", "1112"])).found        # a bad Luhn check stays plain


@pytest.mark.parametrize("sign", NEW_DASHES)
def test_a_card_an_ssn_and_an_iban_with_a_new_dash_are_private(sign):
    assert form_fill.PrivateShape(sign.join(["4111", "1111", "1111", "1111"])).card
    assert form_fill.PrivateShape(f"123{sign}45{sign}6789").ssn
    assert form_fill.PrivateShape(sign.join(["CZ65", "0800", "0000", "1920", "0014", "5399"])).iban
    assert _reviewed({"label": "Notes", "value": f"Card 4111{sign}1111{sign}1111{sign}1111, thanks"}) == [(True, "")]


@pytest.mark.parametrize("sign", NEW_HIDDEN + NEW_DASHES)
def test_a_plain_value_with_a_blank_sign_or_a_new_dash_is_not_private(sign):
    for value in (f"Room{sign} 12", f"2019{sign}2021 2021{sign}2023", f"+420{sign}777{sign}123{sign}456", f"4111{sign}1111{sign}1111{sign}1112"):
        assert not form_fill.PrivateShape(value).found, value


@pytest.mark.parametrize("text, day, worked", [
    ("1 March 2027", date(2027, 3, 1), False), ("March 2027", date(2027, 3, 1), True), ("1st of March 2027", date(2027, 3, 1), False),
    ("March 2 2027", date(2027, 3, 2), False), ("3 Sep 2027", date(2027, 9, 3), False), ("Dec. 2027", date(2027, 12, 1), True)])
def test_a_start_text_with_a_months_name_still_reads_as_a_day(text, day, worked):
    """#139: the month names in `start_day` are escaped now; what it reads stays the same."""
    assert form_fill.start_day(text, date(2026, 11, 15)) == (day, worked)


@pytest.mark.parametrize("value", ["".join(NEW_HIDDEN) * 5_000, "".join(IGNORABLE_HIDDEN) * 5_000, "1⠀" * 25_000, "ㅤ " * 25_000, "ab12・" * 10_000,
                                   ("4111" + "️" * 10) * 2_000])
def test_a_long_hostile_value_full_of_blank_signs_is_read_at_once(value):
    start = time.perf_counter()
    found = form_fill.PrivateShape(value).found
    _reviewed({"label": "Notes", "value": value})
    assert time.perf_counter() - start < 1.5 and not found


# ── look-alike letters, labels in other languages, and cards or IBANs in other digits or gaps ──
# Letters are written as escapes so no reader mistakes a Cyrillic or Greek letter for a Latin one.
CY_A, CY_O, CY_C, CY_P, GR_O = "\u0430", "\u043e", "\u0421", "\u0420", "\u03bf"
LOOK_ALIKE_PRIVATE = [
    f"Card n{CY_A}mber", f"P{CY_A}ssword", f"Security c{CY_O}de", f"Passw{GR_O}rd", f"{CY_C}ard number", f"{CY_P}IN",
    # a word that mixes alphabets is private on the safe side
    f"N{CY_A}me"]
LOOK_ALIKE_NOT_PRIVATE = ["Ім'я / Name", "Місто", "Прізвище", "Ім'я", "Досвід роботи", "Мова", "Όνομα", "Příjmení", "Straße"]
OTHER_LANGUAGE_PRIVATE = [
    "Пароль", "Номер картки", "Номер карты", "Код безпеки", "Код безопасности", "CVV", "Дата народження", "Дата рождения", "Паспорт",
    "Серія паспорта", "ІПН", "РНОКПП", "ИНН", "IBAN", "ПІН-код", "Hasło", "Numer karty", "Data urodzenia", "Dátum narodenia"]
OTHER_LANGUAGE_NOT_PRIVATE = ["Код вакансії", "Номер телефону", "Номер замовлення"]


@pytest.mark.parametrize("label", LOOK_ALIKE_PRIVATE + OTHER_LANGUAGE_PRIVATE)
def test_a_label_with_look_alike_letters_or_in_another_language_is_left_to_you(label):
    assert form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(True, "")]


@pytest.mark.parametrize("label", LOOK_ALIKE_NOT_PRIVATE + OTHER_LANGUAGE_NOT_PRIVATE + NOT_PRIVATE_LABELS)
def test_a_plain_label_in_another_alphabet_or_language_is_not_private(label):
    assert not form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(False, "x1")]


@pytest.mark.parametrize("name", [f"p{CY_A}ssword", f"passw{GR_O}rd", f"{CY_C}ard_number", f"api_k{CY_O}y"])
def test_a_private_inner_name_written_with_look_alike_letters_is_left_to_you(name):
    assert form_fill._private(_field("Your answer", name=name))
    assert form_fill._private(_field("Your answer", id=name))
    assert _reviewed({"label": "Your answer", "name": name, "value": "x1"}) == [(True, "")]


CARD_OTHER_FORMS = ["٤١١١ ١١١١ ١١١١ ١١١١", "४१११ ११११ ११११ ११११", "4111~1111~1111~1111", "4111*1111*1111*1111", "4111•1111•1111•1111",
                    "4111#1111#1111#1111"]


@pytest.mark.parametrize("value", CARD_OTHER_FORMS + ["CZ65·0800·0000·1920·0014·5399"])
def test_a_card_in_other_digits_or_gaps_and_an_iban_with_middle_dots_stay_out_of_the_review(value):
    assert form_fill.PrivateShape(value).found
    assert _reviewed({"label": "Notes", "value": value}) == [(True, "")]


def test_each_new_form_is_told_apart_as_a_card_or_an_iban():
    for value in CARD_OTHER_FORMS:
        shape = form_fill.PrivateShape(value)
        assert (shape.card, shape.iban) == (True, False), value
    iban = form_fill.PrivateShape("CZ65·0800·0000·1920·0014·5399")
    assert (iban.card, iban.iban) == (False, True)


@pytest.mark.parametrize("value", ["2019~2021 2021~2023 2023~2025 2017~2019", "2019*2021*2021*2023", "+420 (777) 123-456",
                                   "Order 4111~1111~1111~1112", "Order 4111#1111#1111#1112", "٤١١١ ١١١١ ١١١١ ١١١٢"])
def test_year_lists_phones_and_numbers_that_fail_the_check_stay_not_private_with_the_new_gaps(value):
    assert not form_fill.PrivateShape(value).found
    assert _reviewed({"label": "Notes", "value": value}) == [(False, value)]


@pytest.mark.parametrize("value", ["1" + "~1" * 50_000, "1" + "*1" * 50_000, "1" + "•1" * 50_000, "1" + "#1" * 50_000,
                                   "١" + " ١" * 50_000, "а" * 100_000 + "x", "1" + "·" + "1" * 100_000])
def test_a_long_hostile_value_with_the_new_gaps_or_look_alike_letters_is_read_at_once(value):
    start = time.perf_counter()
    form_fill.PrivateShape(value)
    _reviewed({"label": "Notes", "value": value})
    form_fill._private({"label": value, "hint": value, "name": value, "id": value})
    assert time.perf_counter() - start < 1.5


# ── round two: the fold itself, other scripts, units, gaps, currency, experience, more languages, gender and age ──
# Every letter that is not Latin is written as an escape; the comment after it says what the word shows.
def _luhn_ok(digits: str) -> bool:
    total = 0
    for place, char in enumerate(reversed(digits)):
        number = int(char) * (2 if place % 2 else 1)
        total += number - 9 if number > 9 else number
    return total % 10 == 0


def _card_groups(first=("4000", "4500", "5000", "550")) -> list[str]:
    """Four groups of four digits that pass the Luhn check: the last digit is the one that makes it pass."""
    head = "".join(first)
    last = next(d for d in "0123456789" if _luhn_ok(head + d))
    return [*first[:-1], first[-1] + last]


def test_the_card_helper_makes_numbers_that_pass_the_check():
    groups = _card_groups()
    assert len(groups) == 4 and all(len(g) == 4 for g in groups) and _luhn_ok("".join(groups))
    assert form_fill.PrivateShape(" ".join(groups)).card


# A. words made only of look-alikes: private only after the fold
@pytest.mark.parametrize("text, latin", [("\u0455\u0435\u0445", "sex"), ("\u0420\u0410\u0405\u0405", "PASS"),
                                         ("\u03a1\u0399\u039d", "PIN"), ("\u0421\u0412\u0412", "CBB")])
def test_a_text_of_look_alikes_is_read_as_the_latin_letters_it_shows(text, latin):
    assert form_fill.PrivacyReading(text).latin == latin


@pytest.mark.parametrize("text", ["\u0455\u0435\u0445", "\u0420\u0410\u0405\u0405", "\u03a1\u0399\u039d"])
def test_a_word_made_only_of_look_alikes_is_private_as_a_label_a_name_a_hint_and_in_a_review(text):
    assert form_fill._private(_field(text))
    assert form_fill._private(_field("Your answer", name=text))
    assert form_fill._private(_field("Your answer", id=text))
    assert form_fill._private(_field("Your answer", hint=text))
    assert _reviewed({"label": text, "value": "x1"}) == [(True, "")]
    assert _reviewed({"label": "Your answer", "name": text, "value": "x1"}) == [(True, "")]


def test_an_iban_typed_with_a_cyrillic_c_is_an_iban():
    shape = form_fill.PrivateShape("\u0421Z65 0800 0000 1920 0014 5399")
    assert (shape.card, shape.iban, shape.found) == (False, True, True)
    assert _reviewed({"label": "Notes", "value": "\u0421Z65 0800 0000 1920 0014 5399"}) == [(True, "")]
    assert form_fill.PrivacyReading("\u0421Z65 0800").latin == "CZ65 0800"


def test_without_the_look_alike_fold_those_tests_could_not_pass(monkeypatch):
    """The fold is what makes them pass: with it gone a word made only of look-alikes is no longer private."""
    assert form_fill._private(_field("\u0455\u0435\u0445"))
    monkeypatch.setattr(form_fill, "_LOOK_ALIKE", {})
    assert not form_fill._private(_field("\u0455\u0435\u0445"))
    assert not form_fill.PrivateShape("\u0421Z65 0800 0000 1920 0014 5399").iban


# B. a Cyrillic word with a Greek letter, and other scripts that look like Latin letters
MIXED_ALPHABET_PRIVATE = [
    "\u041f\u0430\u0440\u03bf\u043b\u044c",             # Парοль: Cyrillic with a Greek omicron
    "Pass\u1d21ord",                                   # small capital w
    "P\u0251ssword",                                   # Latin alpha
    "Pass\u0555ord",                                   # Armenian Oh
    "\u13e2\u13aaSS\u13d4\u13be\u13a1\u13a0",           # Cherokee with Latin S
    "\u2c62\u2c81ssword"]                                  # Coptic with Latin letters


@pytest.mark.parametrize("label", MIXED_ALPHABET_PRIVATE)
def test_a_password_written_with_letters_of_other_scripts_is_left_to_you(label):
    assert form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(True, "")]


# C. units are no private word; the safe side stays private
UNITS = ["Size (\u00b5m)", "Rate (\u00b5g/mL)", "Pull-up 10 k\u03a9", "Size (\u03bcm)"]


@pytest.mark.parametrize("label", UNITS)
def test_a_unit_with_a_micro_or_ohm_sign_is_no_private_word(label):
    assert not form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(False, "x1")]


@pytest.mark.parametrize("label", ["\u041f\u0440i\u0437\u0432\u0438\u0449\u0435", "\u0412\u0406\u0421"])
def test_a_word_with_a_stray_latin_letter_in_a_ukrainian_label_stays_private(label):
    assert form_fill._private(_field(label))


# D. an IBAN with any sign as its gap
@pytest.mark.parametrize("sign", ["~", "*", "#", "\u2022", "|", "+", ",", ":"])
def test_an_iban_with_any_sign_as_its_gap_is_an_iban(sign):
    value = sign.join(["CZ65", "0800", "0000", "1920", "0014", "5399"])
    shape = form_fill.PrivateShape(value)
    assert (shape.card, shape.iban) == (False, True), value
    assert _reviewed({"label": "Notes", "value": value}) == [(True, "")]


# E. a currency sign or a percent sign is no gap: a list of amounts is no card, though its digits pass the check
@pytest.mark.parametrize("sign", ["\u20ac", "$", "\u00a3", "\u00a5", "\u20b4", "%"])
def test_a_list_of_amounts_with_a_currency_or_percent_sign_is_no_card(sign):
    groups = _card_groups()
    assert _luhn_ok("".join(groups))
    for value in [" ".join(g + sign for g in groups), " ".join(sign + g for g in groups),
                  f"{sign}{groups[0]}-{sign}{groups[1]} {sign}{groups[2]}-{sign}{groups[3]}", f"{groups[0]}{sign}, {groups[1]}{sign}, {groups[2]}{sign}, {groups[3]}{sign}"]:
        assert not form_fill.PrivateShape(value).found, value
        assert _reviewed({"label": "Notes", "value": value}) == [(False, value)]


@pytest.mark.parametrize("sign", ["~", "*", "#", "\u2022"])
def test_the_same_digits_with_a_real_gap_are_a_card(sign):
    value = sign.join(_card_groups())
    assert form_fill.PrivateShape(value).card
    assert _reviewed({"label": "Notes", "value": value}) == [(True, "")]


# F. experience and invoice labels in Ukrainian and Russian
NOT_PRIVATE_CYRILLIC = ["\u0414\u043e\u0441\u0432\u0456\u0434 \u0440\u043e\u0431\u043e\u0442\u0438 \u0437 \u043f\u0430\u0440\u043e\u043b\u044f\u043c\u0438",
                        "\u0414\u043e\u0441\u0432\u0456\u0434 \u0437 \u0443\u043f\u0440\u0430\u0432\u043b\u0456\u043d\u043d\u044f \u043f\u0430\u0441\u043f\u043e\u0440\u0442\u043d\u0438\u043c \u0441\u0442\u043e\u043b\u043e\u043c",
                        "\u041e\u043f\u044b\u0442 \u0440\u0430\u0431\u043e\u0442\u044b \u0441 \u043f\u0430\u0440\u043e\u043b\u044f\u043c\u0438",
                        "\u041d\u043e\u043c\u0435\u0440 \u0440\u0430\u0445\u0443\u043d\u043a\u0443-\u0444\u0430\u043a\u0442\u0443\u0440\u0438",
                        "\u041d\u0430\u0440\u043e\u0434\u0436\u0435\u043d\u0438\u0445 \u0434\u0456\u0442\u0435\u0439"]


@pytest.mark.parametrize("label", NOT_PRIVATE_CYRILLIC)
def test_an_experience_or_invoice_label_in_ukrainian_or_russian_is_no_private_field(label):
    assert not form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(False, "x1")]


@pytest.mark.parametrize("label", ["\u041d\u043e\u043c\u0435\u0440 \u0440\u0430\u0445\u0443\u043d\u043a\u0443",
                                   "\u041c\u0456\u0441\u0446\u0435 \u043d\u0430\u0440\u043e\u0434\u0436\u0435\u043d\u043d\u044f"])
def test_an_account_number_and_a_place_of_birth_stay_private(label):
    assert form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(True, "")]


# G. more Ukrainian, Russian, Polish and Slovak labels
MORE_PRIVATE = [
    "\u041d\u043e\u043c\u0435\u0440 \u0440\u0430\u0445\u0443\u043d\u043a\u0443", "\u041d\u043e\u043c\u0435\u0440 \u0441\u0447\u0451\u0442\u0430", "\u041d\u043e\u043c\u0435\u0440 \u0441\u0447\u0435\u0442\u0430",
    "\u0411\u0430\u043d\u043a\u0456\u0432\u0441\u044c\u043a\u0430 \u043a\u0430\u0440\u0442\u043a\u0430", "\u041a\u0440\u0435\u0434\u0438\u0442\u043d\u0430 \u043a\u0430\u0440\u0442\u043a\u0430",
    "\u041f\u043b\u0430\u0442\u0456\u0436\u043d\u0430 \u043a\u0430\u0440\u0442\u043a\u0430", "\u0411\u0430\u043d\u043a\u043e\u0432\u0441\u043a\u0430\u044f \u043a\u0430\u0440\u0442\u0430",
    "\u041f\u0418\u041d", "\u0406\u0434\u0435\u043d\u0442\u0438\u0444\u0456\u043a\u0430\u0446\u0456\u0439\u043d\u0438\u0439 \u043d\u043e\u043c\u0435\u0440",
    "\u0406\u0434\u0435\u043d\u0442\u0438\u0444\u0456\u043a\u0430\u0446\u0456\u0439\u043d\u0438\u0439 \u043a\u043e\u0434",
    "Numer konta", "Numer rachunku", "Has\u0142a", "D\u00e1tum narodenie"]
NOT_PRIVATE_MORE = ["Numer zam\u00f3wienia", "Data publikacji", "D\u00e1tum n\u00e1stupu", "Imi\u0119", "Nazwisko",
                    "\u041c\u0456\u0441\u0446\u0435 \u0440\u043e\u0431\u043e\u0442\u0438"]


@pytest.mark.parametrize("label", MORE_PRIVATE)
def test_more_private_labels_in_ukrainian_russian_polish_and_slovak_are_left_to_you(label):
    assert form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(True, "")]


@pytest.mark.parametrize("label", NOT_PRIVATE_MORE)
def test_ordinary_polish_slovak_and_ukrainian_labels_are_no_private_field(label):
    assert not form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(False, "x1")]


def test_a_private_word_in_the_inner_name_with_underscores_is_read_as_words():
    name = "\u043d\u043e\u043c\u0435\u0440_\u043a\u0430\u0440\u0442\u043a\u0438"      # номер_картки
    assert form_fill._private(_field("Your answer", name=name))
    assert _reviewed({"label": "Your answer", "name": name, "value": "x1"}) == [(True, "")]


@pytest.mark.parametrize("hint", ["\u041f\u0430\u0440\u043e\u043b\u044c", "P\u0430ssword", "Passw\u03bfrd", "\u041d\u043e\u043c\u0435\u0440 \u043a\u0430\u0440\u0442\u043a\u0438"])
def test_a_private_word_in_the_hint_alone_is_left_to_you(hint):
    assert form_fill._private(_field("Your answer", hint=hint))
    assert _reviewed({"label": "Your answer", "hint": hint, "value": "x1"}) == [(True, "")]


# H. gender, citizenship, nationality, age and marital status in Ukrainian and Russian
PERSONAL_CYRILLIC = [
    "\u0421\u0442\u0430\u0442\u044c", "\u0413\u0440\u043e\u043c\u0430\u0434\u044f\u043d\u0441\u0442\u0432\u043e", "\u0413\u0440\u0430\u0436\u0434\u0430\u043d\u0441\u0442\u0432\u043e",
    "\u041d\u0430\u0446\u0456\u043e\u043d\u0430\u043b\u044c\u043d\u0456\u0441\u0442\u044c", "\u041d\u0430\u0446\u0438\u043e\u043d\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c",
    "\u0412\u0456\u043a", "\u0412\u043e\u0437\u0440\u0430\u0441\u0442", "\u0421\u0456\u043c\u0435\u0439\u043d\u0438\u0439 \u0441\u0442\u0430\u043d",
    "\u0421\u0435\u043c\u0435\u0439\u043d\u043e\u0435 \u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0435", "\u041f\u043e\u043b"]
NOT_PERSONAL_CYRILLIC = ["\u0421\u0442\u0430\u0442\u0443\u0441", "\u0421\u0442\u0430\u0442\u0442\u0456", "\u0421\u0442\u0430\u0436", "\u0412\u0456\u043a\u043d\u043e"]


@pytest.mark.parametrize("label", PERSONAL_CYRILLIC)
def test_gender_age_citizenship_and_marital_status_in_ukrainian_or_russian_are_private_like_in_english(label):
    assert form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(True, "")]


@pytest.mark.parametrize("label", NOT_PERSONAL_CYRILLIC)
def test_a_word_that_only_starts_like_gender_or_age_is_no_private_field(label):
    assert not form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(False, "x1")]


# J. speed
@pytest.mark.parametrize("value", ["CZ65" + "~0" * 50_000, "CZ65" + "*0" * 50_000, "a\u1d21" * 50_000, "CZ65" + " 0" * 50_000])
def test_a_long_hostile_iban_gap_or_mixed_word_is_read_at_once(value):
    start = time.perf_counter()
    form_fill.PrivateShape(value)
    _reviewed({"label": "Notes", "value": value})
    form_fill._private({"label": value, "hint": value, "name": value, "id": value})
    assert time.perf_counter() - start < 1.5


# K. round 3: bracket hints, more Cyrillic forms, modifier letters, CJK next to Latin words
ROUND3_PRIVATE = [
    "\u041f\u0430\u0440\u043e\u043b\u044c (\u0434\u043e\u0441\u0432\u0456\u0434)", "\u041f\u0430\u0441\u043f\u043e\u0440\u0442 (\u0441\u0442\u0430\u0436)", "\u041f\u0430\u0440\u043e\u043b\u044c \u0434\u043e\u0441\u0432\u0456\u0434", "\u0414\u0430\u0442\u0430 \u043d\u0430\u0440\u043e\u0434\u0436\u0435\u043d\u043d\u044f (\u0441\u0442\u0430\u0436)", "\u041d\u043e\u043c\u0435\u0440 \u043f\u0430\u0441\u043f\u043e\u0440\u0442\u0430 (\u0437\u043d\u0430\u043d\u043d\u044f \u043d\u0435 \u043f\u043e\u0442\u0440\u0456\u0431\u043d\u0435)",
    "\u041f\u043e\u043b (\u043c/\u0436)", "\u041f\u043e\u043b:", "\u0421\u0442\u0430\u0442\u044c (\u043c/\u0436)", "\u0421\u0442\u0430\u0442\u044c:", "\u0412\u0430\u0448\u0430 \u0441\u0442\u0430\u0442\u044c", "\u041d\u043e\u043c\u0435\u0440 \u043a\u0440\u0435\u0434\u0438\u0442\u043d\u043e\u0457 \u043a\u0430\u0440\u0442\u043a\u0438", "\u041a\u0440\u0435\u0434\u0438\u0442\u043d\u043e\u044e \u043a\u0430\u0440\u0442\u043a\u043e\u044e",
    "\u0406\u0434\u0435\u043d\u0442\u0438\u0444\u0456\u043a\u0430\u0446\u0456\u0439\u043d\u043e\u0433\u043e \u043d\u043e\u043c\u0435\u0440\u0430", "\u0421\u0456\u043c\u0435\u0439\u043d\u043e\u0433\u043e \u0441\u0442\u0430\u043d\u0443", "E\u043c\u0435\u0439\u043b", "\u03bcsername", "Pass\u02bcword", "Pass\u02c8word", "Pas\u02b0sword", "Pass\u02b7ord", "Pa\u02e2sword", "Pas\u02b3sword"]
ROUND3_NOT_PRIVATE = [
    "\u0414\u043e\u0441\u0432\u0456\u0434 \u0440\u043e\u0431\u043e\u0442\u0438 \u0437 \u043f\u0430\u0440\u043e\u043b\u044f\u043c\u0438", "\u041e\u043f\u044b\u0442 \u0440\u0430\u0431\u043e\u0442\u044b \u0441 \u043f\u0430\u0441\u043f\u043e\u0440\u0442\u0430\u043c\u0438", "\u0417\u043d\u0430\u043d\u043d\u044f \u0441\u0438\u0441\u0442\u0435\u043c \u043f\u0430\u0440\u043e\u043b\u0456\u0432", "\u0421\u0442\u0430\u0436 \u0440\u043e\u0431\u043e\u0442\u0438", "\u0445\u043e\u0442\u0438\u0442\u0435 \u0441\u0442\u0430\u0442\u044c \u0447\u0430\u0441\u0442\u044c\u044e \u043a\u043e\u043c\u0430\u043d\u0434\u044b",
    "\u042d\u0442\u0430\u0436, \u043f\u043e\u043b", "E\u30e1\u30fc\u30eb", "T\u30b7\u30e3\u30c4", "CV\u7b80\u5386", "GitHub\u94fe\u63a5", "Email\u90ae\u7bb1", "LinkedIn\ud504\ub85c\ud544", "\u0406\u043c\u02bc\u044f", "Size (\u00b5m)"]


@pytest.mark.parametrize("label", ROUND3_PRIVATE)
def test_a_private_label_with_a_bracket_hint_a_new_word_form_or_a_modifier_letter_is_left_to_you(label):
    assert form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(True, "")]


@pytest.mark.parametrize("label", ROUND3_NOT_PRIVATE)
def test_an_experience_question_or_a_latin_word_beside_cjk_is_no_private_field(label):
    assert not form_fill._private(_field(label))
    assert _reviewed({"label": label, "value": "x1"}) == [(False, "x1")]


@pytest.mark.parametrize("label", ["\u043a\u0440\u0435\u0434\u0438\u0442\u043d" + "\u044e" * 100_000 + " \u043a\u0430\u0440\u0442", "Pass" + "\u02bc" * 100_000 + "word", "Pass" + "\u02b7" * 100_000 + "ord"])
def test_a_long_hostile_word_form_or_modifier_run_is_read_at_once(label):
    start = time.perf_counter()
    form_fill._private(_field(label))
    assert time.perf_counter() - start < 1.5
