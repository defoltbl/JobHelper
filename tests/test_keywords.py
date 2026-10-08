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
        assert [k for k in found if k not in ("Agile",)] == []


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
