"""Keyword comparison between a posting and the CV (no model call)."""
import pytest

from jobhelper import keywords

CV = "Python, Kotlin, SQL (PostgreSQL), FastAPI, Docker, GitHub Actions (CI/CD), React, Git, Linux. English B2, Czech beginner."


def test_splits_posting_keywords_by_what_the_cv_shows():
    posting = "We use Python and FastAPI on Kubernetes (k8s) with Kafka. Docker and CI/CD are a must. Fluent English."
    result = keywords.compare(posting, CV)
    assert result["matched"] == ["Python", "FastAPI", "Docker", "CI/CD", "English"]
    assert result["missing"] == ["Kubernetes", "Kafka"]


def test_order_follows_the_posting_and_has_no_duplicates():
    found = keywords.extract("Docker first, then Python, then docker again and PYTHON.")
    assert found == ["Docker", "Python"]


@pytest.mark.parametrize("text, expected", [
    ("Experience with Node.js and REST APIs", ["Node.js", "REST"]),
    ("C# and .NET developer", ["C#", ".NET"]),
    ("Strong C++ skills", ["C++"]),
    ("C/C++ for embedded devices", ["C", "C++"]),
    ("Python or R for analysis", ["Python", "R"]),
    ("Golang services", ["Go"]),
    ("Spring Boot microservices", ["Spring", "Microservices"]),
    ("Postgres and MS Excel", ["PostgreSQL", "Excel"]),
    ("large language models and retrieval-augmented generation", ["LLM", "RAG"]),
    ("Fluent German and Czech required", ["German", "Czech"]),
])
def test_recognises_spellings(text, expected):
    assert keywords.extract(text) == expected


@pytest.mark.parametrize("text", [
    "You will go far and react quickly to change.",
    "Category C driving licence, R&D department, vitamin C.",
    "You will excel in a swift, agile-minded express team this spring.",
    "Based in the Czech Republic, close to Germany.",
    "JavaScript is not Java",          # checked separately below
])
def test_ordinary_words_are_not_keywords(text):
    found = keywords.extract(text)
    if text.startswith("JavaScript"):
        assert found == ["JavaScript", "Java"]
    else:
        assert [k for k in found if k not in ("Agile", "Driving licence")] == []     # a driving licence is a real requirement


def test_node_js_does_not_count_as_javascript():
    assert "JavaScript" not in keywords.extract("Backend in Node.js")


def test_empty_inputs():
    assert keywords.compare("", CV) == {"matched": [], "missing": []}
    assert keywords.compare("Python", "") == {"matched": [], "missing": ["Python"]}


def test_extract_remembers_a_text_and_hands_out_fresh_lists():
    from jobhelper import keywords
    text = "We use Python, Docker and Kubernetes every day."
    first = keywords.extract(text)
    first.append("changed by the caller")
    again = keywords.extract(text)
    assert again == ["Python", "Docker", "Kubernetes"] and keywords.extract("") == [] and keywords.extract(None) == []
    before = keywords._extract.cache_info().hits
    keywords.extract(text)
    assert keywords._extract.cache_info().hits == before + 1


# ── other professions ───────────────────────────────────────────────────────
def test_terms_of_other_professions_are_found():
    cases = {
        "Month-end close under IFRS, VAT returns, accounts payable and reconciliations.": ["IFRS", "VAT", "Accounts payable", "Reconciliation"],
        "You run SEO and PPC campaigns in Google Ads and report in GA4; HubSpot is our CRM.": ["SEO", "PPC", "Google Ads", "Google Analytics", "HubSpot", "CRM"],
        "Patient care on the ward, medication administration, first aid.": ["Patient care", "Medication administration", "First aid"],
        "3D models in SolidWorks and AutoCAD, FMEA, technical drawings, ISO 9001.": ["SolidWorks", "AutoCAD", "FMEA", "Technical drawing", "ISO 9001"],
        "Layouts in Figma and Photoshop; wireframes first.": ["Figma", "Photoshop", "Wireframing"],
        "HACCP and food safety in a busy kitchen; some front desk shifts.": ["HACCP", "Food safety", "Front desk"],
        "Lesson planning and classroom management; a CELTA is a plus.": ["Lesson planning", "Classroom management", "TEFL"],
        "HPLC, PCR and cell culture under GLP.": ["HPLC", "PCR", "Cell culture", "GLP"],
        "BIM coordination, site management, health and safety on site.": ["BIM", "Site management", "Health and safety"],
    }
    for text, expected in cases.items():
        assert keywords.extract(text) == expected, text


def test_ordinary_words_are_not_taken_for_skills():
    text = ("We care about compliance and a smooth onboarding. You will sketch ideas, word your findings clearly, blend into the team, "
            "work day to day with others, illustrate your point, intercom the office if locked out and lean on your colleagues. "
            "Forecasting, budgeting, negotiation and customs paperwork are handled by another team; the forklift is not yours to drive.")
    assert keywords.extract(text) == []
    assert keywords.extract("Our barista makes great coffee. Barista experience required.") == ["Barista"]


def test_a_cv_from_another_field_is_compared_like_a_software_one():
    cv = "Accountant. IFRS, VAT, bookkeeping, payroll. Excel. English - C1."
    got = keywords.compare("Bookkeeping and VAT returns under IFRS; QuickBooks and Xero. English.", cv)
    assert got == {"matched": ["Bookkeeping", "VAT", "IFRS", "English"], "missing": ["QuickBooks", "Xero"]}
