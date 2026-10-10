"""The documentation keeps its own rules: the user guide needs no terminal, every figure and table
is numbered inside its chapter and referred to, and the PDFs are laid out like a thesis, with
nothing split across pages."""
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
    """Numbers follow the chapter, as in a thesis: the second figure of chapter 2 is Figure 2.2."""
    text = ("## 1. One\n\nSee Figure 900 and Table 5.\n\n![A](img/a.png)\n\n*Figure 900 – A*\n\n## 2. Two\n\nAs Figure 1.1 shows.\n\n"
            "![B](img/b.png)\n\n*Figure 1.1 – B*\n\n![C](img/c.png)\n\n*Figure 7. C*\n\nAnd Figure 7.\n\n"
            "*Table 5 – T*\n\n| a |\n|---|\n| 1 |\n").replace("\\n", "\n")
    fresh = guide_number.renumber(text)
    assert "See Figure 1.1 and Table 2.1." in fresh and "*Figure 1.1 – A*" in fresh
    assert "As Figure 2.1 shows." in fresh and "*Figure 2.1 – B*" in fresh
    assert "*Figure 2.2 – C*" in fresh and "And Figure 2.2." in fresh, "a caption written the older way is rewritten"
    assert "*Table 2.1 – T*" in fresh
    assert guide_number.problems(fresh) == [] and guide_number.renumber(fresh) == fresh
    found = guide_number.problems(text)
    assert any("should be Figure 1.1" in p for p in found) and any("is not written as" in p for p in found)
    lonely = "## 1. One\n\n![A](img/a.png)\n\ntext\n\n| a |\n|---|\n| 1 |\n"
    found = guide_number.problems(lonely)
    assert any("no caption under it" in p for p in found) and any("no caption above it" in p for p in found)
    assert any("never referred to" in p for p in guide_number.problems("## 1. One\n\n![A](img/a.png)\n\n*Figure 1.1 – A*\n"))
    assert any("never referred to" in p for p in guide_number.problems("## 1. One\n\nSee Figure 1.12.\n\n![A](img/a.png)\n\n*Figure 1.1 – A*\n"))
    assert any("does not exist" in p for p in guide_number.problems("## 1. One\n\nAs Table 1.3 shows.\n"))
    assert any("before the first numbered chapter" in p for p in guide_number.problems("See Table 0.1.\n\n*Table 0.1 – T*\n\n| a |\n|---|\n| 1 |\n"))
    with pytest.raises(ValueError):
        guide_number.renumber("## 1. One\n\n*Figure 1.1 – A*\n\n*Figure 1.1 – B*\n")


def test_the_pictures_exist_and_come_from_their_scripts():
    guide = (DOCS / "GUIDE.md").read_text(encoding="utf-8")
    code = (DOCS / "CODE.md").read_text(encoding="utf-8")
    used = re.findall(r"\]\(img/([^)]+)\)", guide)
    assert len(used) >= 30 and len(set(used)) == len(used)
    shots = (ROOT / "tests" / "guide_shots.py").read_text(encoding="utf-8")
    assert set(re.findall(r'shot\("([^"]+)"', shots)) == {name[:-4] for name in used}, "every picture the script takes is in the guide, and the other way round"
    drawn = re.findall(r"\]\(img/([^)]+)\)", code)
    diagrams = _script("code_diagram")
    assert drawn[0] == "code_pipeline.png" and sorted(drawn[1:]) == sorted(f"{name}.png" for name in diagrams.DIAGRAMS), \
        "every diagram the script draws is in the document, and the other way round"
    assert len(drawn) >= 10, "the technical documentation explains its processes with diagrams"
    for name, spec in diagrams.DIAGRAMS.items():
        assert spec["title"] in code, f"the caption of {name} is its title"
        for start, end, _words in spec["arrows"]:
            assert start in spec["nodes"] and end in spec["nodes"], (name, start, end)
        places = [(c, r) for c, r, _kind, _words in spec["nodes"].values()]
        assert len(set(places)) == len(places), f"{name}: two boxes in one place"
        for start, end, _words in spec["arrows"]:                 # an arrow between two boxes of a row or a column runs through no third box
            (c1, r1), (c2, r2) = spec["nodes"][start][:2], spec["nodes"][end][:2]
            between = [(c, r) for c, r in places if (r == r1 == r2 and min(c1, c2) < c < max(c1, c2)) or (c == c1 == c2 and min(r1, r2) < r < max(r1, r2))]
            assert not between, f"{name}: the arrow {start} -> {end} runs through a box"
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
            assert table["caption"] == f"Continuation of Table {table['number']}"
        else:
            first[table["number"]] = table
    text = (DOCS / f"{name}.md").read_text(encoding="utf-8")
    assert [t["caption"] for t in report["tables"] if not t["continued"]] == [f"Table {n} – {title}".replace("`", "").replace("**", "")
                                                                             for n, title in guide_number.captions(text, "Table")]
    if name == "GUIDE":
        assert any(t["continued"] for t in report["tables"]), "the long Search table is the case this rule is for"


def test_a_heading_is_never_left_alone_at_the_bottom_of_a_page(laid_out):
    _name, report = laid_out
    for heading in report["headings"]:
        assert not heading["next_page"] or heading["next_page"] == heading["page"], heading["text"]


def test_the_contents_give_the_real_page_numbers(laid_out):
    """As in a thesis: the contents come first, every entry has a dotted line that leads to its
    page number, and there is no list of figures or tables in front of the text."""
    _name, report = laid_out
    headings = report["headings"]
    assert headings[0]["text"] == "Contents" and headings[0]["page"] == 2
    assert not any(h["text"].startswith("List of") for h in headings)
    assert report["contents"] == [h["page"] for h in headings[1:]]
    assert all(page > headings[0]["page"] for page in report["contents"]), "the text starts after the contents"
    assert [(leader["title"], leader["page"]) for leader in report["leaders"]] == [(h["text"], h["page"]) for h in headings[1:]]
    for leader in report["leaders"]:
        assert leader["to"] - leader["from"] > 60, f"no room for the dotted line after '{leader['title']}'"
    bases = [leader["base"] for leader in report["leaders"]]
    assert bases == sorted(bases) and len(set(bases)) == len(bases)


def test_captions_are_written_as_in_a_thesis():
    """'Figure 2.1 – Title' under the picture, 'Table 2.1 – Title' above the table; numbers restart in each chapter."""
    for name in ("GUIDE", "CODE"):
        text = (DOCS / f"{name}.md").read_text(encoding="utf-8")
        assert not re.search(r"^\*(Figure|Table) \d+\. ", text, re.M), "no caption is written the older way"
        assert not re.search(r"\b(Figure|Table) \d+(?![\d.]*\d)", text), "every reference carries the chapter"
        chapters = {n.split(".")[0] for kind in ("Figure", "Table") for n, _title in guide_number.captions(text, kind)}
        assert len(chapters) >= 5
    source = (ROOT / "scripts" / "guide_pdf.py").read_text(encoding="utf-8")
    assert "List of figures" not in source and "List of tables" not in source


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
    for part in ("Contents", "Table 1.1 –", "Figure 1.1 –" if name == "CODE" else "Figure 2.1 –", "1. Overview"):
        assert part in text, part
    assert "List of figures" not in text and "List of tables" not in text
    pictures = sum(len(page.images) for page in reader.pages)
    assert pictures >= (33 if name == "GUIDE" else 10)
    last = " ".join(reader.pages[-1].extract_text().split())
    assert str(len(reader.pages)) in last.split(), "every page carries its number"


# ── no half-empty pages; places that can be selected ────────────────────────
def _piece(kind, words=40):
    if kind == "h3":
        return '<h3 style="margin:0px;">A heading</h3>'
    if kind == "figure":
        return ('<table data-kind="figure" data-number="1.1" width="100%" cellspacing="0" cellpadding="4"><tr><td class="figure" align="center">'
                + "<br>".join(["line"] * words) + "<br>Figure 1.1 – A picture</td></tr></table>")
    return '<p style="margin-top:6px; margin-bottom:6px;">' + ("word " * words).strip() + "</p>"


def test_text_of_the_same_section_fills_the_space_a_figure_left(laid_out):
    """A figure that has to start on the next page no longer leaves the rest of its page empty: what follows it in
    its own section is brought forward, and when the section has nothing more, the next section of the same chapter
    begins in the space (asked for on 10 October 2026). Nothing crosses a chapter, and the pieces keep their order."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    width, height = 500.0, 700.0
    after = [_piece("p", 90).replace("word", f"after{i}") for i in range(8)]
    body = _piece("p", 260) + _piece("figure", 28) + "".join(after) + _piece("h3") + _piece("p", 30).replace("word", "next")
    _doc, before = guide_pdf._layout(body, DOCS, width, height)
    assert before["figures"][0]["gap"] > 150, "written as it is, the figure leaves a good part of its page empty"
    filled, moves = guide_pdf._fill_gaps(body, DOCS, width, height)
    _doc, now = guide_pdf._layout(filled, DOCS, width, height)
    assert moves >= 2 and now["figures"][0]["gap"] < guide_pdf.MIN_GAP
    order = [filled.index(word) for word in ("after0 ", "after1 ", 'data-kind="figure"', "A heading", "next")]
    assert order == sorted(order), "the text came before the figure, in its own order, and stayed on its side of the heading"
    assert filled.index("after7 ") < filled.index("A heading") and filled.count("<p") == body.count("<p") and len(filled) == len(body)
    alone = _piece("p", 260) + _piece("figure", 28) + _piece("h3") + _piece("p", 60).replace("word", "next")
    kept, moves = guide_pdf._fill_gaps(alone, DOCS, width, height)
    _doc, then = guide_pdf._layout(kept, DOCS, width, height)
    assert moves == 2 and kept.index("A heading") < kept.index("next") < kept.index('data-kind="figure"'), "the next section begins in the space, heading and text together"
    assert then["figures"][0]["gap"] < before["figures"][0]["gap"] and len(kept) == len(alone)
    bare = _piece("p", 260) + _piece("figure", 28) + _piece("h3") + _piece("figure", 20) + _piece("p", 60).replace("word", "next")
    held = guide_pdf._fill_gaps(bare, DOCS, width, height)[0]
    assert "A heading</h3><p" in held or held == bare, "a heading never comes forward without text under it"
    far = alone + _piece("h3").replace("A heading", "Third part") + _piece("p", 20).replace("word", "third")
    held = guide_pdf._fill_gaps(far, DOCS, width, height)[0]
    assert held.index('data-kind="figure"') < held.index("Third part"), "a figure goes no further than the section after its own"
    chapter = _piece("p", 260) + _piece("figure", 28) + '<h2 style="margin:0px;">A chapter</h2>' + _piece("p", 60).replace("word", "next")
    assert guide_pdf._fill_gaps(chapter, DOCS, width, height) == (chapter, 0), "a figure never leaves its chapter"
    assert guide_pdf._fill_gaps("<p>one</p><table><tr><td>x</td></tr>", DOCS, width, height) == ("<p>one</p><table><tr><td>x</td></tr>", 0)
    _ = app
    name, report = laid_out
    if name == "GUIDE":
        assert report["moved"] >= 40, "the user guide has many such places"
    for item in report["figures"] + report["tables"]:
        assert item["gap"] < report["page_height"] * 0.7, f"{item['number']} leaves most of a page empty"


def test_a_long_table_begins_where_its_page_has_room():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    opening = '<table border="1" cellspacing="0" cellpadding="4">'
    head = "<tr><td>Setting</td><td>What it does</td></tr>"
    rows = [f"<tr><td>Row {i}</td><td>{'words ' * 30}</td></tr>" for i in range(40)]
    whole = guide_pdf._split_rows(opening, head, rows, DOCS, 500, 400)
    fitted = guide_pdf._split_rows(opening, head, rows, DOCS, 500, 400, first=160)
    assert 0 < len(fitted[0]) < len(whole[0]) and [r for part in fitted for r in part] == rows, "a shorter first part, and every row once"
    assert len(fitted[1]) == len(whole[0]), "the parts after it take a whole page again"
    _ = app


def test_the_pdf_answers_to_a_click(tmp_path):
    """The entries of the contents, references to figures and tables, and links to another chapter lead to their place."""
    from pypdf import PdfReader
    assert guide_pdf.slug("4. Run a search") == "4-run-a-search" and guide_pdf.slug("If Claude's limit runs out") == "if-claudes-limit-runs-out"
    for name in ("GUIDE", "CODE"):
        reader = PdfReader(str(DOCS / f"{name}.pdf"))
        links = [(number, a.get_object()) for number, page in enumerate(reader.pages) for a in (page.get("/Annots") or [])]
        links = [(number, a) for number, a in links if a.get("/Subtype") == "/Link"]
        text = (DOCS / f"{name}.md").read_text(encoding="utf-8")
        chapters = len(re.findall(r"^##+ ", text, re.M)) - 1                       # without "In this guide"
        assert len(links) >= chapters + len(guide_number.captions(text, "Table")), f"{name}: {len(links)} places can be selected"
        first = next(a for number, a in links if number == 1)                     # the first line of the contents, on page 2
        goal = next(i for i, p in enumerate(reader.pages) if p.indirect_reference.idnum == first["/Dest"][0].idnum)
        assert "1. Overview" in " ".join(reader.pages[goal].extract_text().split()), "the first entry of the contents leads to chapter 1"
        assert goal > 1 and len(reader.outline) >= 5, "and the chapters stand in the PDF's own outline"
        assert guide_pdf.fingerprint(DOCS / f"{name}.md") in (reader.metadata.creator or ""), "what the PDF was made from is still written in it"


def test_the_points_of_a_list_stand_out(laid_out):
    """A heavy square before each point and a bold number before each step, while the words keep their own weight."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    body = guide_pdf._body_html(DOCS / "GUIDE.md", 500.0, 700.0)
    items = re.findall(r"<li[^>]*>.*?</li>", body, re.S)
    assert len(items) > 150 and "list-style-type: square" in guide_pdf.CSS
    for item in items[:60]:
        assert re.match(r'<li style="[^"]*font-weight:700; color:#0b1220;"><span style=" font-weight:400; color:#182230;">', item), item[:160]
    _ = app, laid_out
