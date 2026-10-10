#!/usr/bin/env python3
"""Make the PDF of a document in docs/ (the user guide, the technical documentation).

    python scripts/guide_pdf.py            # docs/GUIDE.pdf and docs/CODE.pdf
    python scripts/guide_pdf.py GUIDE      # one of them

The PDF is laid out like a thesis: a title page, the contents (dotted lines lead to the page
numbers), then the text with its page number at the top right of every page. Figures and tables
are numbered inside their chapter: "Figure 4.2 – Title" stands centred under a picture,
"Table 4.2 – Title" above a table. The rules it keeps, whatever the text:

- a figure (a picture with its caption) is never split across two pages;
- a table stays on one page, with its caption; only a table longer than a page continues on
  the next one, and then between two rows, under the line "Continuation of Table 4.2" and with
  its heading row repeated there;
- a heading is never left alone at the bottom of a page;
- no page is left half empty because a figure or a table had to start on the next one: the text
  that follows it is brought forward to fill the space, as in a thesis: text of the same section
  first, then the beginning of the next section of the same chapter. Nothing crosses a chapter.

In the PDF the entries of the contents, references such as "Figure 4.2" and "Table 9.1", and links
to another chapter can be selected: they lead to that place. The chapters are also in the PDF's own outline.

Uses Qt, which the app already needs: no other program is started. Run it again whenever a
document or a picture changes; a test fails when a PDF is older than its text.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
GUIDE, OUT = DOCS / "GUIDE.md", DOCS / "GUIDE.pdf"
DOCUMENTS = {"GUIDE": "User guide", "CODE": "Technical documentation"}
PICTURE_SCALE = 0.5        # a picture is taken at twice the size it is shown at
MAX_PICTURE_HEIGHT = 0.62  # of the page, so a picture and its caption always fit on one
MAX_TABLE_HEIGHT = 0.86    # of the page: a longer table is continued on the next page, between two rows
NEARLY_A_PAGE = 0.6        # of the page: a table this long may begin on the page before and go on overleaf
MIN_GAP = 46               # points of empty page worth filling (about three lines)
MARGIN, HEADER = 48, 24    # points around the text; room above it for the page number
NUMBER = r"\d+\.\d+"       # of a figure or a table: its chapter, then its place in the chapter
CONTINUED = "Continuation of Table "
CONTENTS = "Contents"
NUMBER_ROOM = 34           # points at the right of the contents, kept free for the page numbers

CSS = """
body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 10pt; color: #182230; }
h1 { font-size: 20pt; margin-top: 0; }
h2 { font-size: 16pt; margin-top: 26px; margin-bottom: 10px; color: #8a4a05; }
h3 { font-size: 12pt; margin-top: 16px; margin-bottom: 4px; }
p { margin-top: 4px; margin-bottom: 8px; }
code, pre { font-family: Menlo, Monaco, monospace; font-size: 9pt; background-color: #eef1f5; }
table { border-collapse: collapse; margin-top: 4px; margin-bottom: 10px; }
td { border: 1px solid #c9d2dc; padding: 5px; font-size: 9.5pt; }
td.plain, td.edge, td.note, td.figure { border: 0px; }
td.note { font-size: 10pt; }
td.figure { font-size: 9.5pt; color: #45556b; }
p.caption { font-size: 9.5pt; color: #45556b; margin-top: 10px; margin-bottom: 3px; }
a { color: #1d4ed8; text-decoration: none; }
ul { list-style-type: square; }
"""

# A note in the text ("> **Tip**" and the lines after it) becomes a tinted box with a coloured edge.
CALLOUTS = {"Note": ("#1d4ed8", "#eaf1fe"), "Tip": ("#15803d", "#e9f7ee"),
            "Important": ("#7e22ce", "#f4ecfd"), "Warning": ("#b91c1c", "#fdecec")}


def fingerprint(source: Path = GUIDE) -> str:
    """What a PDF was made from: the text, every picture it shows, and this script (its look)."""
    text = source.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8"))
    digest.update(Path(__file__).read_bytes())
    for name in sorted(set(re.findall(r"\]\((img/[^)]+)\)", text))):
        digest.update((source.parent / name).read_bytes())
    return digest.hexdigest()[:20]


_LONG: dict[str, dict] = {}       # the tables that may go on overleaf (longer than most of a page), by their number


def _table_parts(number: str, title: str, opening: str, head: str, parts: list[list[str]]) -> list[str]:
    out = []
    for i, part in enumerate(parts):
        mark = f' data-caption="{number}"' if i == 0 else ' data-continued="1"'
        label = f"Table {number} – {title}" if i == 0 else f"{CONTINUED}{number}"
        out.append(f'<p class="caption"{mark}>{label}</p>{opening}{head}{"".join(part)}</table>')
    return out


# ── from Markdown to the HTML that is laid out ──────────────────────────────
def _body_html(source: Path, page_width: float, page_height: float) -> str:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QImage, QTextDocument

    _LONG.clear()
    text = source.read_text(encoding="utf-8")
    text = re.sub(r"\]\(\.\./([^)#]+)\)", r"](\1)", text)            # links to other documents: by name, they are not in the PDF
    text = re.sub(r"^# .*\n", "", text, count=1)                      # the title has a page of its own
    text = re.sub(r"\n## In this (?:guide|document)\n.*?(?=\n### |\n## |\n---)", "\n", text, count=1, flags=re.S)   # the PDF has contents with page numbers
    doc = QTextDocument()
    doc.setBaseUrl(QUrl.fromLocalFile(str(source.parent) + "/"))
    doc.setMarkdown(text)
    html = doc.toHtml()
    html = html[html.index("<body"):]
    html = re.sub(r"^<body[^>]*>|</body></html>\s*$", "", html)
    html = re.sub(r"<hr[^>]*>", "", html)                             # a chapter starts on a new page instead
    # The points of a list stand out: a heavy square before each, a bold number before each step. The mark takes the
    # weight of its item, so the item is made bold and its words are given back their own weight.
    html = re.sub(r'<li( style="[^"]*)"', r'<li\1 font-weight:700; color:#0b1220;"', html)
    html = re.sub(r"(<li[^>]*>)(.*?)(?=<(?:ul|ol|li|/li)\b)", r'\1<span style=" font-weight:400; color:#182230;">\2</span>', html, flags=re.S)

    def callout(match) -> str:
        kind, body = match.group(1), match.group(2)
        edge, fill = CALLOUTS[kind]
        return (f'<table data-kind="callout" width="100%" cellspacing="0" cellpadding="7"><tr>'
                f'<td class="edge" width="4" bgcolor="{edge}"></td>'
                f'<td class="note" bgcolor="{fill}"><span style="font-weight:700; color:{edge};">{kind}</span><br>{body}</td></tr></table>')
    html = re.sub(r'<p style="[^"]*margin-left:40px;[^"]*">\s*<span style=" font-weight:700;">(Note|Tip|Important|Warning)</span>\s*(.*?)</p>',
                  callout, html, flags=re.S)

    # a picture and the caption under it: one frame, so that they are kept together and on one page
    def figure(match) -> str:
        src, number, title = match.group(1), match.group(2), match.group(3)
        picture = QImage(str(source.parent / src))
        width, height = picture.width() * PICTURE_SCALE, picture.height() * PICTURE_SCALE
        shrink = min(1.0, (page_width - 8) / width, page_height * MAX_PICTURE_HEIGHT / height) if width and height else 1.0
        size = f' width="{round(width * shrink)}" height="{round(height * shrink)}"' if width and height else ""
        return (f'<table data-kind="figure" data-number="{number}" width="100%" cellspacing="0" cellpadding="4"><tr><td class="figure" align="center">'
                f'<img src="{src}"{size}><br>Figure {number} – {title}</td></tr></table>')
    html = re.sub(r'<p[^>]*>\s*<img src="([^"]+)"[^>]*>\s*</p>\s*<p[^>]*>\s*<span style=" font-style:italic;">Figure (' + NUMBER + r') – (.*?)</span>\s*</p>',
                  figure, html, flags=re.S)

    # a table: its caption above it, its first row as the heading row
    def table(match) -> str:
        number, title, opening, first_row, rest = match.groups()
        rows = re.findall(r"<tr>.*?</tr>", rest, flags=re.S)
        shares = iter(_column_shares([first_row] + rows))
        head = re.sub(r"<td>", lambda _m: f'<td bgcolor="#e8edf3" width="{next(shares)}%">', first_row)
        opening = f'<table data-kind="data" data-number="{number}" width="100%" border="1" cellspacing="0" cellpadding="4" style="border-collapse:collapse;">'
        parts = _split_rows(opening, head, rows, source.parent, page_width, page_height * MAX_TABLE_HEIGHT)
        # kept, so that it can be cut again where it really begins on its page: a table longer than a page, and one that
        # fills most of a page (alone it would push itself to the next page and leave this one nearly empty)
        if len(parts) > 1 or len(_split_rows(opening, head, rows, source.parent, page_width, page_height * NEARLY_A_PAGE)) > 1:
            _LONG[number] = {"opening": opening, "head": head, "rows": rows, "title": title}
        return "".join(_table_parts(number, title, opening, head, parts))
    html = re.sub(r'<p[^>]*>\s*<span style=" font-style:italic;">Table (' + NUMBER + r') – (.*?)</span>\s*</p>\s*(<table[^>]*>)\s*(<tr>.*?</tr>)(.*?</table>)',
                  table, html, flags=re.S)
    return html


def _column_shares(rows: list[str]) -> list[int]:
    """How wide each column is, in per cent: a column with much text gets more room, so a table
    is shorter and more of them fit on a page. No column gets less than a readable minimum."""
    cells = [[len(re.sub(r"<[^>]+>", "", cell)) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)] for row in rows]
    count = max((len(row) for row in cells), default=0)
    if not count:
        return []
    weight = []
    for column in range(count):
        lengths = [row[column] for row in cells if column < len(row)]
        weight.append(max(8.0, (sum(lengths) / len(lengths)) ** 0.75 if lengths else 8.0))      # long cells count, but not in full
    least = max(12, round(60 / count))
    shares = [max(least, round(100 * w / sum(weight))) for w in weight]
    while sum(shares) > 100:                                     # the minimums pushed it over: take from the widest
        shares[shares.index(max(shares))] -= 1
    while sum(shares) < 100:
        shares[shares.index(max(shares))] += 1
    return shares


def _split_rows(opening: str, head: str, rows: list[str], base: Path, width: float, most: float, first: float = 0) -> list[list[str]]:
    """The rows of a table in as few parts as fit on a page each (with the heading row). A table
    that fits is one part. Rows are never cut: a part ends between two rows. `first` is the room the
    first part has when the table begins in the middle of a page (0 = a whole page)."""
    from PySide6.QtCore import QSizeF, QUrl
    from PySide6.QtGui import QTextDocument, QTextTable

    doc = QTextDocument()
    doc.setBaseUrl(QUrl.fromLocalFile(str(base) + "/"))
    doc.setDefaultStyleSheet(CSS)
    doc.setDocumentMargin(0)
    doc.setHtml(opening + head + "".join(rows) + "</table>")
    doc.setPageSize(QSizeF(width, 10_000_000))              # one endless page: only the heights are wanted
    layout = doc.documentLayout()
    frame = next(f for f in doc.rootFrame().childFrames() if isinstance(f, QTextTable))
    whole = layout.frameBoundingRect(frame)
    if whole.height() <= most or len(rows) < 2:
        return [rows]
    tops = [layout.blockBoundingRect(frame.cellAt(r, 0).firstCursorPosition().block()).top() for r in range(frame.rows())]
    tops.append(whole.bottom())
    heights = [tops[i + 1] - tops[i] for i in range(frame.rows())]          # heights[0] is the heading row
    parts, current, used = [], [], heights[0]
    for row, tall in zip(rows, heights[1:]):
        if current and used + tall > (first if first and not parts else most):
            parts.append(current)
            current, used = [], heights[0]
        current.append(row)
        used += tall
    parts.append(current)
    return parts


_BLOCK = re.compile(r"<(/?)(p|h[1-6]|ul|ol|pre|table|div|blockquote)\b[^>]*>")


def _segments(html: str) -> list[dict]:
    """The body as the pieces that follow each other on a page: a heading, a paragraph, a list, a figure,
    a table with its caption, a note. Each says what it is and whether it may be cut by a page end."""
    out, depth, start = [], 0, 0
    for m in _BLOCK.finditer(html):
        if not m.group(1):
            if depth == 0:
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                piece = html[start:m.end()]
                tag = m.group(2)
                kind = "text"
                if tag in ("h2", "h3"):
                    kind = tag
                elif tag == "table":
                    kind = re.search(r'data-kind="(\w+)"', piece).group(1) if 'data-kind="' in piece else "data"
                out.append({"html": piece, "kind": kind, "tries": 0})
    merged: list[dict] = []
    for seg in out:                                  # a table's caption is the paragraph above it: one piece
        if seg["kind"] == "data" and merged and 'class="caption"' in merged[-1]["html"] and merged[-1]["kind"] == "text":
            cap = merged.pop()
            seg = {"html": cap["html"] + seg["html"], "kind": "more" if "data-continued" in cap["html"] else "data", "tries": 0}
        merged.append(seg)
    return merged


def _height(seg: dict, base: Path, width: float) -> float:
    """How tall a piece is on a page of this width (measured once)."""
    if "height" not in seg:
        from PySide6.QtCore import QSizeF, QUrl
        from PySide6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setBaseUrl(QUrl.fromLocalFile(str(base) + "/"))
        doc.setDefaultStyleSheet(CSS)
        doc.setDocumentMargin(0)
        doc.setHtml(seg["html"])
        doc.setPageSize(QSizeF(width, 10_000_000))
        seg["height"] = doc.size().height()
    return seg["height"]


def _fill_gaps(body: str, base: Path, width: float, height: float) -> tuple[str, int]:
    """The body with text brought forward wherever a figure or a table had to start on the next page and left
    the rest of its page empty. Text of the same section moves first; when there is none, the next section of the
    same chapter begins in the space (a heading only with text under it, and never a chapter). A figure, a table
    or a note moves only whole, and the order of the moved pieces among themselves stays. Returns (body, moves)."""
    segs = _segments(body)
    if "".join(s["html"] for s in segs).count("<table") != body.count("<table"):
        return body, 0                               # a shape this does not know: the document is left as it was written
    moves, section = 0, 0
    for seg in segs:                                 # which section each piece was written in: a heading opens the next one
        section += seg["kind"] in ("h2", "h3")
        seg["sec"] = section
    for _round in range(16):
        _doc, report = _layout("".join(s["html"] for s in segs), base, width, height)
        owners = [s for s in segs if s["kind"] in ("figure", "data", "more", "callout", "list")]
        if len(owners) != len(report["gaps"]):
            break
        changed = False
        for owner, gap in reversed(list(zip(owners, report["gaps"]))):          # from the end, so that earlier places stay where they are
            number = (re.search(r'data-number="([\d.]+)"', owner["html"]) or [None, ""])[1]
            # a table that may go on overleaf is cut again whenever what stands before it has moved (its own count, so that
            # the tries spent on bringing text forward do not leave it cut for a place it no longer has)
            recut = owner["kind"] == "data" and number in _LONG and gap > 150 and owner.get("cuts", 0) < 8
            if owner["kind"] not in ("figure", "data") or gap < MIN_GAP or (owner["tries"] >= 4 and not recut):
                continue
            i = next(k for k, s in enumerate(segs) if s is owner)
            end = next((k for k in range(i + 1, len(segs)) if segs[k]["kind"] == "h2"), len(segs))       # never out of its chapter
            owner["tries"] += 1
            # 1. text of the same section comes forward; a figure, a table or a note comes only if all of it fits,
            #    and otherwise keeps its place after this one (figures and tables stay in their order)
            #    When the section has no more text, the next section of the same chapter begins in the space: its
            #    heading comes with the text under it, never alone.
            room, taken, stay, rest = gap - 4, [], [], segs[i + 1:end]
            for k, seg in enumerate(rest):
                tall = _height(seg, base, width)
                # from the section after its own only the heading and text come forward, and nothing from further on:
                # figures and tables keep their order, and a figure stays next to what it shows
                if seg["sec"] > owner["sec"] + 1 or (seg["sec"] != owner["sec"] and seg["kind"] not in ("text", "h3")):
                    stay += rest[k:]
                    break
                if seg["kind"] == "h3":
                    after = rest[k + 1] if k + 1 < len(rest) else None
                    if stay or room <= 0 or after is None or after["kind"] != "text" or tall + min(_height(after, base, width), 48) > room:
                        stay += rest[k:]
                        break
                    taken.append(seg)
                    room -= tall
                    continue
                if room <= 0 or seg["kind"] == "more" or (seg["kind"] != "text" and tall > room) or (stay and seg["kind"] != "text"):
                    stay.append(seg)
                    continue
                taken.append(seg)
                room -= tall
            if taken and taken[-1]["kind"] == "h3":     # a heading whose text did not come with it goes back
                stay.insert(0, taken.pop())
            if owner["tries"] > 4:
                taken = []                              # its tries at bringing text forward are spent: only the cut is left
            if taken:
                segs[i:end] = taken + [owner] + stay
                moves += len(taken)
                changed = True
                continue
            # 2. a table longer than a page begins where the page has room, and goes on overleaf
            if recut:
                long = _LONG[number]
                # the space is measured as if the page were empty, but a heading and a line of text may stand above the table:
                # each further try leaves more room for them
                parts = _split_rows(long["opening"], long["head"], long["rows"], base, width, height * MAX_TABLE_HEIGHT,
                                    first=gap - 34 - 55 * owner.get("cuts", 0))
                last = next((k for k in range(i + 1, len(segs)) if segs[k]["kind"] != "more"), len(segs))
                if len(parts[0]) >= 2:
                    fresh = _table_parts(number, long["title"], long["opening"], long["head"], parts)
                    segs[i:last] = [{"html": h, "kind": "data" if n == 0 else "more", "tries": owner["tries"], "sec": owner["sec"], "cuts": owner.get("cuts", 0) + 1}
                                    for n, h in enumerate(fresh)]
                    moves += 1
                    changed = True
                    continue
            # 3. a picture that almost fits is shown a little smaller instead of leaving most of a page empty
            if owner["kind"] == "figure":
                size = re.search(r'<img src="[^"]+" width="(\d+)" height="(\d+)"', owner["html"])
                if size:
                    wide, tall = int(size.group(1)), int(size.group(2))
                    factor = (gap - 34) / tall
                    if 0.66 <= factor < 1:
                        owner["html"] = owner["html"].replace(size.group(0), size.group(0).replace(f'width="{wide}" height="{tall}"', f'width="{round(wide * factor)}" height="{round(tall * factor)}"'))
                        owner.pop("height", None)
                        owner["tries"] = 9
                        moves += 1
                        changed = True
        if not changed:
            break
    return "".join(s["html"] for s in segs), moves


def _entries(html: str) -> list[tuple[str, str]]:
    """What goes into the contents: (level, title) of every chapter and section, in the order of the text."""
    plain = lambda s: html_lib.unescape(re.sub(r"<[^>]+>", "", s)).strip()       # noqa: E731
    return [(m.group(1), plain(m.group(2))) for m in re.finditer(r"<h([23])[^>]*>(.*?)</h\1>", html, flags=re.S)]


def _counted(html: str) -> tuple[int, int]:
    """How many figures and tables the text has."""
    return len(re.findall(r'data-kind="figure"', html)), len(re.findall(r'data-caption="', html))


def _front(title: str, subtitle: str, entries: list, pages: list, counted: tuple[int, int]) -> str:
    """The title page and the contents. The dotted line and the page number of each entry are
    drawn onto the page later, on the last line of its title."""
    rows = ""
    for (level, text), page in zip(entries, pages):
        left = 0 if level == "2" else 16
        rows += (f'<tr><td class="plain" style="padding-left:{left}px;">{html_lib.escape(text)}</td>'
                 f'<td class="plain" width="{NUMBER_ROOM}" data-page="{page}"></td></tr>')
    figures, tables = counted
    return (f'<p style="margin-top:170px; font-size:11pt; color:#8a4a05; font-weight:700;">JOBHELPER</p>'
            f'<p style="font-size:30pt; font-weight:700; margin-top:6px; margin-bottom:6px;">{html_lib.escape(title)}</p>'
            f'<p style="font-size:13pt; color:#45556b;">{html_lib.escape(subtitle)}</p>'
            f'<p style="margin-top:300px; font-size:10pt; color:#45556b;">For JobHelper on macOS<br>'
            f'{figures} figure{"" if figures == 1 else "s"} · {tables} tables</p>'
            f'<h2 align="center" style="page-break-before:always;">{CONTENTS}</h2>'
            f'<table data-kind="list" width="100%" cellspacing="0" cellpadding="3">{rows}</table>')


# ── laying it out by the rules ──────────────────────────────────────────────
def _kinds(html: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2) or "") for m in re.finditer(r'<table data-kind="(\w+)"(?: data-number="([\d.]+)")?', html)]


def _layout(html: str, base: Path, width: float, height: float):
    """The document laid out on pages of this size, with every rule kept. Returns (doc, report)."""
    from PySide6.QtCore import QSizeF, QUrl
    from PySide6.QtGui import QTextCursor, QTextDocument, QTextFormat, QTextTable

    doc = QTextDocument()
    doc.setBaseUrl(QUrl.fromLocalFile(str(base) + "/"))
    doc.setDefaultStyleSheet(CSS)
    doc.setDocumentMargin(0)
    doc.setHtml(html)       # a chapter follows on the same page; only the contents and the lists start a page of their own
    doc.setPageSize(QSizeF(width, height))
    layout = doc.documentLayout()
    kinds = _kinds(html)
    tables = [f for f in doc.rootFrame().childFrames() if isinstance(f, QTextTable)]
    assert len(tables) == len(kinds), (len(tables), len(kinds))
    def page_of(y: float) -> int:
        return int(y // height)

    def top_of(block) -> float:
        """Where a block's first line really stands. A paragraph whose line did not fit at the end of a page begins,
        for Qt, on that page, while its words stand on the next one: the place of the first line is what counts."""
        box = layout.blockBoundingRect(block)
        lines = block.layout()
        return box.top() + (lines.lineAt(0).y() if lines.lineCount() else 0.0)

    def caption_of(frame):
        """The caption of a data table: the block just above it, which moves with it."""
        block = doc.findBlock(frame.firstPosition() - 1)
        return block if block.isValid() and block.text().startswith(("Table ", CONTINUED)) else None

    def break_before_block(block) -> None:
        cursor = QTextCursor(block)
        fmt = cursor.blockFormat()
        fmt.setPageBreakPolicy(QTextFormat.PageBreak_AlwaysBefore)
        cursor.setBlockFormat(fmt)

    def break_before_table(frame, kind) -> None:
        if kind == "data" and caption_of(frame) is not None:
            break_before_block(caption_of(frame))
            return
        fmt = frame.format()
        fmt.setPageBreakPolicy(QTextFormat.PageBreak_AlwaysBefore)
        frame.setFormat(fmt)

    def text_after(block):
        """The next block that holds something (Qt leaves empty ones between a heading and a list or a table)."""
        following = block.next()
        while following.isValid() and not following.text().strip() and following.next().isValid():
            following = following.next()
        return following

    def first_problem():
        for frame, (kind, _number) in zip(tables, kinds):
            rect = layout.frameBoundingRect(frame)
            top = rect.top()
            if kind == "data" and caption_of(frame) is not None:
                top = layout.blockBoundingRect(caption_of(frame)).top()
            whole = rect.bottom() - top
            if page_of(top) == page_of(rect.bottom() - 1):
                continue
            if whole <= height * 0.97:                  # it fits on a page: it must be on one
                return lambda f=frame, k=kind: break_before_table(f, k)
            if kind == "list" and (top % height) > height * 0.75:
                return lambda f=frame, k=kind: break_before_table(f, k)       # the contents do not begin at the very bottom
        block = doc.begin()
        while block.isValid():
            following = text_after(block)
            if block.blockFormat().headingLevel() and following.isValid():
                if page_of(top_of(block)) != page_of(top_of(following)) and block.blockFormat().pageBreakPolicy() == QTextFormat.PageBreak_Auto:
                    return lambda b=block: break_before_block(b)
            block = block.next()
        return None

    for _round in range(600):
        fix = first_problem()
        if fix is None:
            break
        fix()
    else:
        raise RuntimeError("the pages would not settle")

    def gap_before(frame, top: float) -> float:
        """The empty space at the end of the page before the one this begins: only when it stands at the top of
        its page with at most a heading and a line of text above it."""
        page = page_of(top)
        if page == 0 or top - page * height > height * 0.22:
            return 0.0
        block = doc.findBlock(frame.firstPosition() - 1)
        while block.isValid() and top_of(block) >= page * height - 0.5:
            block = block.previous()
        if not block.isValid():
            return 0.0
        end = layout.blockBoundingRect(block).bottom()
        inside = block.document().frameAt(block.position())
        while inside is not None and isinstance(inside, QTextTable) is False and inside.parentFrame() is not None:
            inside = inside.parentFrame()
        if isinstance(inside, QTextTable):
            end = max(end, layout.frameBoundingRect(inside).bottom())
        return max(0.0, page * height - end) if page_of(end - 0.5) == page - 1 else 0.0

    report = {"pages": doc.pageCount(), "page_height": height, "figures": [], "tables": [], "headings": [], "leaders": [], "gaps": []}
    for frame, (kind, number) in zip(tables, kinds):
        rect = layout.frameBoundingRect(frame)
        top = rect.top()
        caption = caption_of(frame) if kind == "data" else None
        if caption is not None:
            top = layout.blockBoundingRect(caption).top()
        report["gaps"].append(gap_before(frame, top))
        if kind == "list":
            report["leaders"] = [_leader(layout, frame, row) for row in range(frame.rows())]
        item = {"number": number, "caption": caption.text() if caption is not None else "", "first_page": page_of(top) + 1, "last_page": page_of(rect.bottom() - 1) + 1,
                "top": top, "gap": report["gaps"][-1],
                "height": rect.bottom() - top, "heading": frame.cellAt(0, 0).firstCursorPosition().block().text() if kind == "data" else ""}
        if kind == "figure":
            report["figures"].append(item)
        elif kind == "data":
            item["continued"] = any(t["number"] == item["number"] for t in report["tables"])
            report["tables"].append(item)
    block = doc.begin()
    while block.isValid():
        level = block.blockFormat().headingLevel()
        if level in (2, 3):
            following = text_after(block)
            report["headings"].append({"text": block.text(), "level": level, "page": page_of(top_of(block)) + 1, "top": top_of(block),
                                       "next_page": page_of(top_of(following)) + 1 if following.isValid() else 0})
        block = block.next()
    report["spots"] = _spots(doc, layout)
    return doc, report


_REFERENCE = re.compile(r"\b(Figure|Table) (\d+\.\d+)\b")


def _spots(doc, layout) -> list[dict]:
    """The places in the text that lead somewhere when selected: a link to another chapter ("#4-run-a-search"),
    and every mention of a figure or a table by its number. Each is {"x0", "x1", "top", "bottom", "to"} in the
    document's own coordinates; `to` is "#slug", "Figure 4.2" or "Table 9.1"."""
    out = []

    def place(block, start: int, end: int, to: str) -> None:
        lines = block.layout()
        line = lines.lineForTextPosition(start)
        if not line.isValid():
            return
        box = layout.blockBoundingRect(block)
        last = min(end, line.textStart() + line.textLength())
        x0, x1 = line.cursorToX(start), line.cursorToX(last)
        x0, x1 = (x0[0] if isinstance(x0, tuple) else x0), (x1[0] if isinstance(x1, tuple) else x1)
        if x1 - x0 > 2:
            out.append({"x0": box.left() + x0, "x1": box.left() + x1, "top": box.top() + line.y(), "bottom": box.top() + line.y() + line.height(), "to": to})

    block = doc.begin()
    while block.isValid():
        text = block.text()
        it = block.begin()
        while not it.atEnd():
            piece = it.fragment()
            fmt = piece.charFormat()
            if piece.isValid() and fmt.isAnchor() and fmt.anchorHref().startswith("#"):
                at = piece.position() - block.position()
                place(block, at, at + piece.length(), fmt.anchorHref())
            it += 1
        caption = re.match(r"(Figure|Table) \d+\.\d+ \u2013 ", text) or text.startswith(CONTINUED)
        for m in ([] if caption else _REFERENCE.finditer(text)):
            place(block, m.start(), m.end(), m.group(0))
        block = block.next()
    return out


def slug(heading: str) -> str:
    """A heading as a link names it: "4. Run a search" -> "4-run-a-search"."""
    return re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-")


def _leader(layout, frame, row: int) -> dict:
    """Where the dotted line of one entry of the contents runs: from the end of its title (the
    last line of it, when the title needed two) to the right edge, where its page number stands."""
    block = frame.cellAt(row, 0).lastCursorPosition().block()
    lines = block.layout()
    line = lines.lineAt(lines.lineCount() - 1)
    box = layout.blockBoundingRect(block)
    return {"from": box.left() + line.naturalTextWidth(), "to": layout.frameBoundingRect(frame).right(),
            "base": box.top() + line.y() + line.ascent(), "title": block.text()}


def compose(source: Path = GUIDE):
    """The whole document, laid out: (doc, report, title). The page numbers in the contents are the real ones."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QGuiApplication, QPageLayout, QPageSize

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    area = QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0), QPageLayout.Point).fullRectPoints()
    width, height = area.width() - 2 * MARGIN, area.height() - 2 * MARGIN - HEADER
    text = source.read_text(encoding="utf-8")
    title = re.search(r"^# (.+)$", text, re.M).group(1).strip()
    subtitle = {"GUIDE": "How to use every part of the app, step by step", "CODE": "How the app is built, run and tested"}.get(source.stem, "")
    body, moved = _fill_gaps(_body_html(source, width, height), source.parent, width, height)
    entries = _entries(body)
    pages = ["000"] * len(entries)
    doc = report = None
    for _attempt in range(6):                           # the numbers are known only once the pages are laid out
        doc, report = _layout(_front(title, subtitle, entries, pages, _counted(body)) + '<p style="page-break-before:always;"></p>' + body,
                              source.parent, width, height)
        found = [h["page"] for h in report["headings"]][1:]         # the first heading is the contents themselves
        for leader, page in zip(report["leaders"], pages):
            leader["page"] = page
        if found == pages:
            break
        pages = found
    else:
        raise RuntimeError("the page numbers in the contents would not settle")
    report["contents"] = pages
    report["title"] = title
    report["moved"] = moved
    _ = app
    return doc, report, title


def build(source: Path = GUIDE, out: Path | None = None) -> Path:
    from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPageLayout, QPageSize, QPainter, QPdfWriter

    out = out or source.with_suffix(".pdf")
    doc, report, title = compose(source)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(out))
    writer.setTitle(f"JobHelper: {title}")
    writer.setCreator(f"JobHelper guide_pdf {fingerprint(source)}")       # how the test knows the PDF matches its text
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0), QPageLayout.Point))
    writer.setResolution(72)                                              # one point per pixel: sizes above are points
    height, width = report["page_height"], doc.pageSize().width()
    painter = QPainter(writer)
    plain = QFont("Helvetica Neue")
    plain.setPointSizeF(10 * 96 / 72)        # the size the text of the document is drawn at
    painter.setFont(plain)
    measure = QFontMetricsF(plain, writer)
    top = MARGIN + HEADER
    for page in range(report["pages"]):
        if page:
            writer.newPage()
        painter.save()
        painter.translate(MARGIN, top - page * height)
        doc.drawContents(painter, QRectF(0, page * height, width, height))
        painter.setPen(QColor("#182230"))
        for leader in report["leaders"]:                                  # the contents: a dotted line, then the page number
            if not page * height <= leader["base"] < (page + 1) * height:
                continue
            number = str(leader["page"])
            painter.drawText(QPointF(leader["to"] - measure.horizontalAdvance(number), leader["base"]), number)
            end = leader["to"] - NUMBER_ROOM + 8
            dots = "." * max(0, int((end - leader["from"] - 5) / measure.horizontalAdvance(".")))
            painter.drawText(QPointF(end - measure.horizontalAdvance(dots), leader["base"]), dots)
        painter.restore()
        if page:                                                          # not on the title page; at the top right, as in a thesis
            painter.setPen(QColor("#182230"))
            painter.drawText(QRectF(MARGIN, MARGIN - 6, width, HEADER), Qt.AlignRight | Qt.AlignTop, str(page + 1))
    painter.end()
    del writer
    _link_up(out, report, MARGIN, top)
    return out


def _link_up(path: Path, report: dict, left: float, top: float) -> int:
    """Make the PDF answer to a click: every entry of the contents, every link to another chapter and every mention
    of a figure or a table leads to its place, and the chapters stand in the PDF's own outline. Returns how many
    places were made. (Qt writes the pages; a PDF library that the app already uses adds the links.)"""
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import Link
    from pypdf.generic import ArrayObject, Fit, FloatObject, NameObject, NullObject

    reader = PdfReader(str(path))
    writer = PdfWriter(clone_from=reader)
    tall = float(reader.pages[0].mediabox.height)
    height = report["page_height"]

    def on_page(y: float) -> tuple[int, float]:
        """A height in the laid-out document as (page, height from the bottom of that page)."""
        page = int(y // height)
        return page, tall - (top + (y - page * height))

    targets: dict[str, float] = {}
    for h in report["headings"]:
        targets.setdefault("#" + slug(h["text"]), h["top"])
    for f in report["figures"]:
        targets.setdefault(f"Figure {f['number']}", f["top"])
    for t in report["tables"]:
        if not t["continued"]:
            targets.setdefault(f"Table {t['number']}", t["top"])
    spots = list(report["spots"])
    chapters = [h for h in report["headings"]][1:]                 # without the contents themselves
    for leader, heading in zip(report["leaders"], chapters):       # a whole line of the contents
        spots.append({"x0": 0, "x1": leader["to"], "top": leader["base"] - 11, "bottom": leader["base"] + 4, "to": heading["top"]})
    made = 0
    for spot in spots:
        goal = spot["to"] if isinstance(spot["to"], float) else targets.get(spot["to"])
        if goal is None:
            continue
        page, upper = on_page(spot["top"])
        _same, lower = on_page(spot["bottom"] - 0.01)
        to_page, to_top = on_page(goal)
        if page >= len(writer.pages) or to_page >= len(writer.pages):
            continue
        added = writer.add_annotation(page_number=page, annotation=Link(rect=(left + spot["x0"], lower, left + spot["x1"], upper), border=[0, 0, 0],
                                                                        target_page_index=to_page, fit=Fit.xyz(left=left - 6, top=min(tall, to_top + 14))))
        # the page itself, not its number: that is what a place inside the same PDF must name for every reader to follow it
        added[NameObject("/Dest")] = ArrayObject([writer.pages[to_page].indirect_reference, NameObject("/XYZ"), FloatObject(left - 6),
                                                  FloatObject(min(tall, to_top + 14)), NullObject()])
        made += 1
    parent = None
    for heading in chapters:
        to_page, to_top = on_page(heading["top"])
        item = writer.add_outline_item(heading["text"], to_page, parent=None if heading["level"] == 2 else parent, fit=Fit.xyz(left=left - 6, top=min(tall, to_top + 14)))
        if heading["level"] == 2:
            parent = item
    if reader.metadata:
        writer.add_metadata({k: str(v) for k, v in reader.metadata.items()})
    with open(path, "wb") as handle:
        writer.write(handle)
    report["links"] = made
    return made


if __name__ == "__main__":
    wanted = [a.upper() for a in sys.argv[1:]] or list(DOCUMENTS)
    for name in wanted:
        source = DOCS / f"{name}.md"
        if not source.is_file():
            print(f"docs/{name}.md is not there")
            continue
        made = build(source)
        print(f"{made.relative_to(ROOT)}  ({made.stat().st_size // 1024} KB)")
