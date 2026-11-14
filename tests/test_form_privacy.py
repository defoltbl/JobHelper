"""#89: what personal data the assistant keeps to itself. A private field is never filled, and in a review of a form
its value never goes to Claude. Read by the field's name (a labelled set of hard cases on both sides) and by the
shape of the value (a card number, an IBAN, a social security number), whatever the page calls the field."""
import json
import os
import subprocess
import sys
import time

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
                                   "123 45 6789", "10:30", "1|2|3", "12:30 4111-1111 1111-1111 3"])
def test_a_list_a_time_or_a_card_inside_a_longer_run_with_mixed_gaps_is_not_private(value):
    """Mixed gaps count only when the card is the whole run of digits."""
    assert not form_fill.PrivateShape(value).found


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
