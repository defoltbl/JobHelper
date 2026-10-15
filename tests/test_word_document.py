"""A Word document as the app reads and changes it (jobhelper/word_document.py)."""
import zipfile
from pathlib import Path

import pytest

from jobhelper.word_document import Paragraph, WordDocument

CV = Path(__file__).parent / "fixtures" / "Candidate_CV_EN.docx"


def test_only_the_text_part_changes_and_every_other_part_stays_byte_for_byte(tmp_path):
    doc = WordDocument(CV)
    first = next(p for p in doc.paragraphs() if p.text.strip() and p.writable)
    first.write("A new first line.")
    out = tmp_path / "out.docx"
    doc.save(out)
    with zipfile.ZipFile(CV) as before, zipfile.ZipFile(out) as after:
        assert before.namelist() == after.namelist()
        for name in before.namelist():
            if name != WordDocument.TEXT:
                assert before.read(name) == after.read(name), name
    again = WordDocument(out)
    assert next(p for p in again.paragraphs() if p.text.strip()).text == "A new first line."
    assert WordDocument(CV).part(WordDocument.TEXT) == doc.part(WordDocument.TEXT)        # the original is untouched


def test_a_paragraph_keeps_its_formatting_and_refuses_text_it_cannot_hold():
    doc = WordDocument(CV)
    para = next(p for p in doc.paragraphs() if len(p.runs) > 1)
    style = [r.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr") for r in para.runs]
    para.write("One text.")
    assert para.text == "One text." and len(para.runs) == len(style)                   # the runs, and their formatting, are still there
    empty = Paragraph(doc.paragraphs()[0].element.makeelement(doc.paragraphs()[0].element.tag))
    assert not empty.writable
    with pytest.raises(ValueError):
        empty.write("x")


def test_saving_over_a_file_leaves_no_draft_behind(tmp_path):
    copy = tmp_path / "cv.docx"
    copy.write_bytes(CV.read_bytes())
    doc = WordDocument(copy)
    next(p for p in doc.paragraphs() if p.writable).write("Changed.")
    doc.save_over(copy)
    assert [f.name for f in tmp_path.iterdir()] == ["cv.docx"]
    assert "Changed." in [p.text for p in WordDocument(copy).paragraphs()]
