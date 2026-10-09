"""The documentation keeps its own rules: the user guide needs no terminal, every figure and table
is numbered and referred to, and in the PDFs nothing is split across pages."""
import importlib.util
import os
import re

import pytest

from tests.conftest import ROOT

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DOCS = ROOT / "docs"


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guide_pdf, guide_number = _script("guide_pdf"), _script("guide_number")


@pytest.fixture(scope="module", params=["GUIDE", "CODE"])
def laid_out(request):
    _doc, report, _title = guide_pdf.compose(DOCS / f"{request.param}.md")
    return request.param, report


# ── the text ────────────────────────────────────────────────────────────────
def test_the_user_guide_needs_no_terminal():
    """It is for someone who only uses the app: no commands, no code, no developer documents."""
    guide = (DOCS / "GUIDE.md").read_text(encoding="utf-8")
    for word in ("```", "python ", "pytest", ".py", "pip ", "status.py", "run.py", "COMMANDS", "README", "HANDBOOK", "ANTHROPIC_API_KEY", "terminal"):
        assert word not in guide, word
    assert "invented" in guide and "[CODE.md](CODE.md)" in guide          # where the pictures come from; where the code is described
    for word in ("Recovery key", "Open my data"):                          # what needed a command is done in the window
        assert f"**{word}**" in guide
    assert word in (ROOT / "ui_qt" / "WelcomeOverlay.qml").read_text(encoding="utf-8")


def test_the_technical_documentation_holds_what_the_guide_left_out():
    code = (DOCS / "CODE.md").read_text(encoding="utf-8")
    for part in ("python app_qt.py", "python run.py", "python status.py sync", "python -m pytest", "tests/guide_shots.py",
                 "scripts/guide_pdf.py", "scripts/guide_number.py", "requirements.lock", "claude auth login"):
        assert part in code, part
    listed = set(re.findall(r"`((?:agent\d_|scrapers_|api_|bridge_)?[a-z_]+\d?[a-z_]*)`", code))
    modules = {f.stem for f in (ROOT / "jobhelper").glob("*.py")}
    named = {name for name in listed if name in modules}
    assert len(named) >= 40, sorted(modules - named)                       # the structure section names the modules that exist
    for name in re.findall(r"`((?:agent\d|scrapers|api|bridge)_[a-z_]+)`", code):
        assert name in modules, f"{name} is named but does not exist"
    commands = set(re.findall(r"python status\.py ([a-z-]+)", code))
    status = (ROOT / "status.py").read_text(encoding="utf-8")
    for command in commands:
        assert f'"{command}"' in status, command


@pytest.mark.parametrize("name", ["GUIDE", "CODE"])
def test_headings_follow_the_rules(name):
    text = (DOCS / f"{name}.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^# ", text, re.M)) == 1                        # one title
    chapters = re.findall(r"^## (.+)$", text, re.M)
    numbered = [c for c in chapters if re.match(r"\d+\. ", c)]
    assert [int(c.split(".")[0]) for c in numbered] == list(range(1, len(numbered) + 1))
    assert not re.search(r"^####", text, re.M)                             # title, chapters, sub-tasks: three levels
    assert "### Prerequisites" in text and "Before you begin" not in text
    for section in re.findall(r"\]\(#([^)]+)\)", text):                    # every entry of the contents leads somewhere
        assert any(re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") == section for h in chapters), section
    for link in re.findall(r"\]\(((?:\.\./)?[A-Za-z_]+\.(?:md|pdf))\)", text):
        assert (DOCS / link).resolve().is_file(), link
    assert "click here" not in text.lower()


@pytest.mark.parametrize("name", ["GUIDE", "CODE"])
def test_every_figure_and_table_is_numbered_captioned_and_referred_to(name):
    text = (DOCS / f"{name}.md").read_text(encoding="utf-8")
    assert guide_number.problems(text) == []
    assert guide_number.renumber(text) == text


def test_the_numbering_tool_renumbers_and_finds_what_is_wrong():
    text = ("See Figure 900 and Table 5.\\n\\n![A](img/a.png)\\n\\n*Figure 900. A*\\n\\nAs Figure 1 shows.\\n\\n![B](img/b.png)\\n\\n*Figure 1. B*\\n\\n"
            "*Table 5. T*\\n\\n| a |\\n|---|\\n| 1 |\\n").replace("\\n", "\n")
    fresh = guide_number.renumber(text)
    assert "See Figure 1 and Table 1." in fresh and "*Figure 1. A*" in fresh and "As Figure 2 shows." in fresh and "*Figure 2. B*" in fresh
    assert guide_number.problems(fresh) == []
    assert any("not 1 to" in p for p in guide_number.problems(text))
    lonely = "![A](img/a.png)\n\ntext\n\n| a |\n|---|\n| 1 |\n"
    found = guide_number.problems(lonely)
    assert any("no caption under it" in p for p in found) and any("no caption above it" in p for p in found)
    assert any("never referred to" in p for p in guide_number.problems("![A](img/a.png)\n\n*Figure 1. A*\n"))
    assert any("does not exist" in p for p in guide_number.problems("As Table 3 shows.\n"))
    with pytest.raises(ValueError):
        guide_number.renumber("*Figure 1. A*\n\n*Figure 1. B*\n")


def test_the_pictures_exist_and_come_from_their_scripts():
    guide = (DOCS / "GUIDE.md").read_text(encoding="utf-8")
    code = (DOCS / "CODE.md").read_text(encoding="utf-8")
    used = re.findall(r"\]\(img/([^)]+)\)", guide)
    assert len(used) >= 30 and len(set(used)) == len(used)
    shots = (ROOT / "tests" / "guide_shots.py").read_text(encoding="utf-8")
    assert set(re.findall(r'shot\("([^"]+)"', shots)) == {name[:-4] for name in used}, "every picture the script takes is in the guide, and the other way round"
    drawn = re.findall(r"\]\(img/([^)]+)\)", code)
    assert drawn == ["code_pipeline.png"] and "code_pipeline.png" in (ROOT / "scripts" / "code_diagram.py").read_text(encoding="utf-8")
    assert sorted(p.name for p in (DOCS / "img").glob("*.png")) == sorted(used + drawn), "no picture is left over in docs/img"


# ── the pages ───────────────────────────────────────────────────────────────
def test_a_figure_is_never_split_across_two_pages(laid_out):
    _name, report = laid_out
    assert report["figures"], "the document has figures"
    for figure in report["figures"]:
        assert figure["first_page"] == figure["last_page"], f"Figure {figure['number']} runs from page {figure['first_page']} to {figure['last_page']}"
        assert figure["height"] < report["page_height"]


def test_a_table_stays_on_one_page_and_a_long_one_continues_with_its_heading_row(laid_out):
    name, report = laid_out
    first = {}
    for table in report["tables"]:
        assert table["first_page"] == table["last_page"], f"Table {table['number']} is split between pages {table['first_page']} and {table['last_page']}"
        assert table["height"] < report["page_height"]
        if table["continued"]:
            start = first[table["number"]]
            assert table["heading"] == start["heading"] != "", "the heading row is repeated on the next page"
            assert table["first_page"] > start["first_page"]
        else:
            first[table["number"]] = table
    numbers = [t["number"] for t in report["tables"] if not t["continued"]]
    assert numbers == list(range(1, len(numbers) + 1))
    if name == "GUIDE":
        assert any(t["continued"] for t in report["tables"]), "the long Search table is the case this rule is for"


def test_a_heading_is_never_left_alone_at_the_bottom_of_a_page(laid_out):
    _name, report = laid_out
    for heading in report["headings"]:
        assert not heading["next_page"] or heading["next_page"] == heading["page"], heading["text"]


def test_the_contents_give_the_real_page_numbers(laid_out):
    _name, report = laid_out
    front = sum(1 for h in report["headings"] if h["text"] in ("Contents", "List of figures", "List of tables"))
    assert report["contents"]["headings"] == [h["page"] for h in report["headings"]][front:]
    assert report["contents"]["figures"] == [f["first_page"] for f in report["figures"]]
    assert report["contents"]["tables"] == [t["first_page"] for t in report["tables"] if not t["continued"]]
    assert all(page > 1 for page in report["contents"]["headings"])
    body = [h for h in report["headings"] if h["level"] == 2 and h["text"] not in ("Contents", "List of figures", "List of tables")]
    lists = [h for h in report["headings"] if h["text"] in ("Contents", "List of figures", "List of tables")]
    assert body[0]["page"] > max(h["page"] for h in lists), "the text starts after the contents and the lists"


def test_a_table_too_long_for_a_page_is_cut_between_rows():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    opening = '<table border="1" cellspacing="0" cellpadding="4">'
    head = "<tr><td>Setting</td><td>What it does</td></tr>"
    rows = [f"<tr><td>Row {i}</td><td>{'words ' * 30}</td></tr>" for i in range(40)]
    parts = guide_pdf._split_rows(opening, head, rows, DOCS, 500, 400)
    assert len(parts) > 2 and [row for part in parts for row in part] == rows          # every row once, in order, none cut
    assert all(part for part in parts)
    assert guide_pdf._split_rows(opening, head, rows[:2], DOCS, 500, 400) == [rows[:2]]   # one that fits is left whole
    _ = app


def test_a_column_with_more_text_gets_more_room():
    row = lambda *cells: "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"      # noqa: E731
    shares = guide_pdf._column_shares([row("Name", "Used for", "Why"), row("Python", "All the logic", "words " * 40), row("Qt", "The window", "words " * 50)])
    assert sum(shares) == 100 and shares[2] > shares[1] >= shares[0] >= 12
    even = guide_pdf._column_shares([row("a", "b"), row("c", "d")])
    assert even == [50, 50] and guide_pdf._column_shares([]) == []
    many = guide_pdf._column_shares([row(*["x"] * 6), row("y" * 300, *["x"] * 5)])
    assert sum(many) == 100 and min(many) >= 12, "no column becomes too narrow to read"


def test_the_technical_documentation_explains_its_tech_stack():
    """What each part is used for and why it was chosen, so that a change does not replace one blindly."""
    code = (DOCS / "CODE.md").read_text(encoding="utf-8")
    chapter = code[code.index("## 2. Know the tech stack"):code.index("## 3. Install the app")]
    assert chapter.count("| Technology | Used for | Why it was chosen |") >= 5 and "| Not used | Why not |" in chapter
    for part in ("Python", "PySide6", "QML", "claude-agent-sdk", "python-docx", "pypdf", "openpyxl", "SQLite", "JSON", "requests", "imaplib",
                 "AES-256-GCM", "Keychain", "LaunchAgent", "requirements.lock", "pytest", "pyflakes", "Git", "LibreOffice"):
        assert part in chapter, part
    wanted = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for package in re.findall(r"^([A-Za-z0-9_-]+)>=", wanted, re.M):
        assert package.lower() in chapter.lower() or package in ("python-dotenv", "lxml"), f"{package} is installed but not explained"
    for row in re.findall(r"^\| .+ \| .+ \| (.+) \|$", chapter, re.M):
        assert row == "Why it was chosen" or len(row) > 40, "every part says why, in a sentence"


@pytest.mark.parametrize("name", ["GUIDE", "CODE"])
def test_the_pdf_matches_its_text(name):
    """Each PDF carries a fingerprint of the text, the pictures and the layout it was made from;
    when this fails, run: python scripts/guide_pdf.py"""
    from pypdf import PdfReader
    path = DOCS / f"{name}.pdf"
    assert path.is_file(), f"docs/{name}.pdf is missing: python scripts/guide_pdf.py"
    reader = PdfReader(str(path))
    assert guide_pdf.fingerprint(DOCS / f"{name}.md") in (reader.metadata.creator or ""), f"docs/{name}.md changed after its PDF was made: python scripts/guide_pdf.py"
    text = " ".join(" ".join(page.extract_text() for page in reader.pages[:12]).split())
    for part in ("Contents", "List of tables", "List of figures", "Table 1.", "Figure 1."):
        assert part in text, part
    pictures = sum(len(page.images) for page in reader.pages)
    assert pictures >= (33 if name == "GUIDE" else 1)
    last = " ".join(reader.pages[-1].extract_text().split())
    assert last.endswith(str(len(reader.pages))), "every page carries its number"
