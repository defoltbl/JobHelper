#!/usr/bin/env python3
"""Make docs/GUIDE.pdf from docs/GUIDE.md (the same text and pictures, as one file to read or print).

    python scripts/guide_pdf.py

Uses Qt, which the app already needs: no other program is started. Run it again whenever
GUIDE.md or a picture changes; a test fails when the PDF is older than the guide's text.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE, OUT = ROOT / "docs" / "GUIDE.md", ROOT / "docs" / "GUIDE.pdf"
IMAGE_WIDTH = 640          # points of page width a picture takes (the text area of an A4 page is about 680)

CSS = """
body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 10pt; color: #182230; }
h1 { font-size: 22pt; margin-top: 0; }
h2 { font-size: 15pt; margin-top: 22px; color: #8a4a05; }
h3 { font-size: 12pt; margin-top: 14px; }
p { margin-top: 4px; margin-bottom: 8px; }
code, pre { font-family: Menlo, Monaco, monospace; font-size: 9pt; background-color: #eef1f5; }
table { border-collapse: collapse; margin-top: 6px; margin-bottom: 6px; }
th { background-color: #e8edf3; font-weight: bold; }
th, td { border: 1px solid #c9d2dc; padding: 5px; font-size: 9.5pt; }
a { color: #1d4ed8; text-decoration: none; }
td.edge, td.note { border: 0px; }
td.note { font-size: 10pt; }
"""


# A note in the guide ("> **Tip**" and the lines after it) becomes a tinted box with a coloured edge.
CALLOUTS = {"Note": ("#1d4ed8", "#eaf1fe"), "Tip": ("#15803d", "#e9f7ee"),
            "Important": ("#7e22ce", "#f4ecfd"), "Warning": ("#b91c1c", "#fdecec")}


def callout(match) -> str:
    kind, text = match.group(1), match.group(2)
    edge, fill = CALLOUTS[kind]
    return (f'<table class="callout" width="100%" cellspacing="0" cellpadding="7"><tr>'
            f'<td class="edge" width="4" bgcolor="{edge}"></td>'
            f'<td class="note" bgcolor="{fill}"><span style="font-weight:700; color:{edge};">{kind}</span><br>{text}</td></tr></table>')


def head_row(match) -> str:
    """The first row of a table is its heading: tinted, as in the stylesheet's `th`."""
    if 'class="edge"' in match.group(2):
        return match.group(0)
    return match.group(1) + match.group(2).replace("<td>", '<td bgcolor="#e8edf3">') + match.group(3)


def fingerprint() -> str:
    """What the PDF was made from: the guide's text and every picture it shows."""
    text = GUIDE.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8"))
    digest.update(Path(__file__).read_bytes())            # and how it is laid out: a new look needs a new PDF too
    for name in sorted(set(re.findall(r"\]\((img/[^)]+)\)", text))):
        digest.update((GUIDE.parent / name).read_bytes())
    return digest.hexdigest()[:20]


def build(out: Path = OUT) -> Path:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QMarginsF, QSizeF, QUrl
    from PySide6.QtGui import QGuiApplication, QImage, QPageLayout, QPageSize, QPdfWriter, QTextDocument

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    text = GUIDE.read_text(encoding="utf-8")
    text = re.sub(r"\]\(\.\./([^)#]+)\)", r"](\1)", text)            # links to the other documents: by name, they are not in the PDF
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(out))
    writer.setTitle("JobHelper: the illustrated guide")
    writer.setCreator(f"JobHelper guide_pdf {fingerprint()}")          # how the test knows the PDF matches the guide
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(16, 16, 16, 16), QPageLayout.Millimeter))
    writer.setResolution(72)                                            # one point per pixel: sizes below are points
    page = writer.pageLayout().paintRectPixels(72)

    doc = QTextDocument()
    doc.setBaseUrl(QUrl.fromLocalFile(str(GUIDE.parent) + "/"))
    doc.setMarkdown(text)
    html = doc.toHtml()

    def sized(match):                       # every picture as wide as the text, with the height that goes with it
        src = match.group(1)
        picture = QImage(str(GUIDE.parent / src))
        width = min(IMAGE_WIDTH, page.width() - 4)
        height = round(width * picture.height() / picture.width()) if not picture.isNull() and picture.width() else 0
        return f'<img src="{src}" width="{width}"' + (f' height="{height}"' if height else "") + ">"
    html = re.sub(r'<img src="([^"]+)"[^>]*>', sized, html)
    html = re.sub(r'<p style="[^"]*margin-left:40px;[^"]*">\s*<span style=" font-weight:700;">(Note|Tip|Important|Warning)</span>\s*(.*?)</p>',
                  callout, html, flags=re.S)
    html = re.sub(r"(<table[^>]*>\s*<tr>)(.*?)(</tr>)", head_row, html, flags=re.S)
    doc = QTextDocument()
    doc.setBaseUrl(QUrl.fromLocalFile(str(GUIDE.parent) + "/"))
    doc.setDefaultStyleSheet(CSS)
    doc.setHtml(html)
    doc.setPageSize(QSizeF(page.width(), page.height()))
    doc.print_(writer)
    del writer
    _ = app
    return out


if __name__ == "__main__":
    made = build()
    print(f"{made.relative_to(ROOT)}  ({made.stat().st_size // 1024} KB)")
