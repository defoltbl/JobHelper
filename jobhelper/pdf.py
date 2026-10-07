"""PDF copies of the adapted CV and cover letter, made with LibreOffice.

LibreOffice is optional. Without it every function here quietly does nothing and
the app keeps working with .docx files only. With it, each generated document
gets a .pdf next to it and the one-page check uses the real page count.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    str(Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice"),
]


def find_soffice() -> str:
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    for path in _CANDIDATES:
        if Path(path).is_file():
            return path
    return ""


def available() -> bool:
    return bool(find_soffice())


def to_pdf(docx: Path, timeout: int = 120) -> Path | None:
    """Convert one .docx to a .pdf in the same folder. None if it could not be made."""
    docx = Path(docx)
    soffice = find_soffice()
    if not soffice or not docx.is_file() or docx.suffix.lower() != ".docx":
        return None
    out = docx.with_suffix(".pdf")
    try:
        # A private profile folder, so a LibreOffice window the user has open is not disturbed.
        with tempfile.TemporaryDirectory(prefix="jobhelper-lo-") as profile:
            with tempfile.TemporaryDirectory(prefix="jobhelper-pdf-") as work:
                r = subprocess.run(
                    [soffice, f"-env:UserInstallation=file://{profile}", "--headless", "--norestore",
                     "--convert-to", "pdf", "--outdir", work, str(docx)],
                    capture_output=True, text=True, timeout=timeout)
                made = Path(work) / (docx.stem + ".pdf")
                if r.returncode != 0 or not made.is_file() or made.stat().st_size == 0:
                    return None
                shutil.move(str(made), str(out))
    except (OSError, subprocess.SubprocessError):
        return None
    return out


def page_count(pdf: Path) -> int:
    """Number of pages, or 0 if the file cannot be read."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(pdf)).pages)
    except Exception:  # noqa: BLE001
        return 0


def pdf_for(docx: Path) -> Path | None:
    """The existing PDF copy of a document, if there is one."""
    pdf = Path(docx).with_suffix(".pdf")
    return pdf if pdf.is_file() else None


def combine(parts: list[Path], out: Path) -> Path | None:
    """Join PDF files into one, in the given order. None if any part is missing or unreadable."""
    from pypdf import PdfReader, PdfWriter
    try:
        writer = PdfWriter()
        for part in parts:
            for page in PdfReader(str(part)).pages:
                writer.add_page(page)
        if not len(writer.pages):
            return None
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return out
    except Exception:  # noqa: BLE001 - a missing or damaged part: no combined file
        return None
