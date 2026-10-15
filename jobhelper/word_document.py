"""A Word document (.docx) as the app reads and changes it.

A .docx file is a zip archive. Its text is in one part, `word/document.xml`; styles, fonts,
images and the rest are other parts. `WordDocument` opens the archive once, gives the body
and its paragraphs, and saves the file with only the text part changed: every other part is
copied byte for byte, so the look of the document stays exactly as its owner made it.
`Paragraph` reads one paragraph's text and writes new text into its existing runs, so the
formatting of those runs (font, size, bold) stays.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
P, R, T = f"{{{W}}}p", f"{{{W}}}r", f"{{{W}}}t"


def text_of(element) -> str:
    """All the text inside an element of the document (a paragraph, a run)."""
    return "".join(t.text or "" for t in element.iter(T))


def set_run_text(run, text: str) -> None:
    """Put `text` into a run, in its first text node; the run keeps its formatting."""
    ts = run.findall(T)
    if not ts:
        ts = [etree.SubElement(run, T)]
    ts[0].text = text
    ts[0].set(XML_SPACE, "preserve")
    for extra in ts[1:]:
        run.remove(extra)


class Paragraph:
    """One paragraph of a document."""

    def __init__(self, element) -> None:
        self.element = element

    @property
    def text(self) -> str:
        return text_of(self.element)

    @property
    def runs(self) -> list:
        """The runs that hold the paragraph's own text (not text inside a link or a form control)."""
        return self.element.findall(R)

    @property
    def writable(self) -> bool:
        """Whether new text can be written into it: it needs at least one run of its own."""
        return bool(self.runs)

    def write(self, text: str) -> None:
        """Replace the paragraph's text, keeping the formatting of its first run. ValueError when it has no run."""
        runs = self.runs
        if not runs:
            raise ValueError("The paragraph has no run of its own to write into.")
        set_run_text(runs[0], text)
        for r in runs[1:]:
            set_run_text(r, "")


class WordDocument:
    """A .docx file: its text part to read and change, every other part kept as it was."""

    TEXT = "word/document.xml"

    def __init__(self, path) -> None:
        with zipfile.ZipFile(path) as z:
            self._parts = [(info, z.read(info.filename)) for info in z.infolist()]
        self._root = etree.fromstring(self.part(self.TEXT))

    @property
    def body(self):
        """The body element of the text: its children are the paragraphs and tables in order."""
        return self._root.find(f"{{{W}}}body")

    def paragraphs(self) -> list[Paragraph]:
        """The paragraphs of the body, in order (not those inside tables)."""
        return [Paragraph(p) for p in self.body if p.tag == P]

    def names(self) -> list[str]:
        return [info.filename for info, _data in self._parts]

    def part(self, name: str) -> bytes:
        """One part of the file as it was read (the text part before any change)."""
        return next(data for info, data in self._parts if info.filename == name)

    def text_xml(self) -> bytes:
        """The text part as it is now, with the changes made."""
        return etree.tostring(self._root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def save(self, out_path) -> None:
        """Write the document to `out_path`: the text part as it is now, every other part as it was."""
        new_text = self.text_xml()
        with zipfile.ZipFile(out_path, "w") as zout:
            for info, data in self._parts:
                zout.writestr(info, new_text if info.filename == self.TEXT else data, compress_type=zipfile.ZIP_DEFLATED)

    def save_over(self, path) -> None:
        """Write the document over the file at `path` safely: a draft first, then swapped in, so a failure
        halfway leaves the old file whole."""
        path = Path(path)
        draft = path.with_name(path.stem + ".retitling.docx")
        try:
            self.save(draft)
            draft.replace(path)
        finally:
            draft.unlink(missing_ok=True)
