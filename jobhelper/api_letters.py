"""The window's back end, part: editing a letter the app wrote, your own letters, and the
letter and CV in one PDF."""
from __future__ import annotations

import os

from datetime import date

from . import (agent3_letters, config, cover_letter, pdf, store, vault)
from .api_base import _guarded, _stem


class LettersApi:
    """Mixed into `ui_api.Api`; uses its `_change`, `_cv_text`, `_open` and `live`."""

    # ── editing a letter the app wrote ──────────────────────────
    def _letter_path(self, j):
        return (config.LETTERS_DIR / j.get("cover_letter_file", "")).with_suffix(".docx")

    def _editable_letter(self, j) -> bool:
        if not (bool(j) and agent3_letters._generated_letter(j) and self._letter_path(j).is_file()
                and config.LETTER_TEMPLATE.exists()):
            return False
        try:        # letters from an early version have fewer paragraphs than the template: Word only
            return len(cover_letter.read_letter(self._letter_path(j))["paragraphs"]) \
                == len(cover_letter.read_letter(config.LETTER_TEMPLATE)["paragraphs"])
        except Exception:  # noqa: BLE001 - not a letter built from the template
            return False

    def _old_format_letter(self, j) -> bool:
        """A Word letter the app wrote, but in an earlier layout: it opens in Word, not in the editor here."""
        return bool(j) and agent3_letters._generated_letter(j) and self._letter_path(j).is_file() \
            and config.LETTER_TEMPLATE.exists() and not self._editable_letter(j)

    @_guarded(dict)
    def letter_for_edit(self, job_id):
        j = store.find(store.load_jobs(), job_id)
        if not j:
            return {"ok": False, "msg": "That job is not in the list any more."}
        if not self._editable_letter(j):
            if self._old_format_letter(j):
                return {"ok": False, "msg": "This letter was made in an older format. Open it in Word to change it."}
            return {"ok": False, "msg": "This letter is your own, or was not made from the current letter template. "
                                        "Open it in Word to change it."}
        try:
            parts = cover_letter.read_letter(self._letter_path(j))
        except Exception:  # noqa: BLE001
            return {"ok": False, "msg": "The letter file could not be read. Open it in Word instead."}
        return {"ok": True, "id": j["id"], "company": j["company"], "title": j["title"], **parts,
                "min_words": cover_letter.MIN_WORDS, "max_words": cover_letter.MAX_WORDS}

    def save_letter(self, job_id, paragraphs):
        """Write the edited paragraphs back into the letter (same head, date, fonts and layout).
        The previous version is kept in an encrypted backup. Rule breaks are returned as warnings."""
        jobs = store.load_jobs()
        j = store.find(jobs, job_id)
        if not self._editable_letter(j):
            return {"ok": False, "msg": "This letter cannot be edited here."}
        texts = [cover_letter.clean(str(p)).strip() for p in (paragraphs or [])]
        if len(texts) != cover_letter.BODY_PARAGRAPHS or any(not t for t in texts):
            return {"ok": False, "msg": f"The letter needs all {cover_letter.BODY_PARAGRAPHS} paragraphs; none may be empty."}
        path = self._letter_path(j)
        parts = cover_letter.read_letter(path)
        draft = path.with_name(path.stem + ".editing.docx")
        try:
            cover_letter.build_docx(config.LETTER_TEMPLATE, draft, cover_letter.own_title(self._cv_text()) or parts["title_line"], texts,
                                    date_text=parts["date_text"])
            # Only a damaged file stops the save. Wording that breaks a letter rule is
            # your call in a hand edit: it comes back as a warning below.
            problems = [x for x in cover_letter.verify(config.LETTER_TEMPLATE, draft, []) if "admits a gap" not in x]
            if problems:
                return {"ok": False, "msg": "The letter could not be saved: " + "; ".join(problems)}
            vault.keep_copy(path, "letter_versions")
            draft.replace(path)
        finally:
            draft.unlink(missing_ok=True)
        warnings = cover_letter.letter_warnings(texts, self._cv_text())
        made = pdf.to_pdf(path)
        if made and pdf.page_count(made) > 1:
            warnings.append("The letter is now longer than one page.")
        self._change(job_id, lambda all_jobs, job: job.__setitem__("last_update", date.today().isoformat()), render=False)
        return {"ok": True, "warnings": warnings, "words": sum(len(t.split()) for t in texts)}

    def rewrite_paragraph(self, job_id, paragraphs, index, hint=""):
        """Ask Claude for a new version of one paragraph (not saved). One or two calls."""
        j = store.find(store.load_jobs(), job_id)
        if not self._editable_letter(j):
            return {"ok": False, "msg": "Only letters the app wrote can be rewritten here."}
        texts = [str(p) for p in (paragraphs or [])]
        cv_text = self._cv_text()
        if not cv_text.strip():
            return {"ok": False, "msg": "Your master CV could not be read, so the paragraph cannot be checked against it."}
        try:
            return {"ok": True, "index": int(index),
                    "paragraph": cover_letter.rewrite_paragraph(j, cv_text, texts, int(index), hint or "")}
        except Exception as e:  # noqa: BLE001 - shown to the user as the reason
            return {"ok": False, "msg": str(e)}

    # ── letter and CV in one PDF ────────────────────────────────
    def _pdf_parts(self, j, make: bool = False):
        """[letter.pdf, cv.pdf] for a job, or None when a single PDF is not possible.
        A missing PDF copy is made from the Word file when make=True; with make=False
        it is enough that it could be made (LibreOffice is installed)."""
        parts = []
        for base, name in ((config.LETTERS_DIR, (j or {}).get("cover_letter_file", "")),
                           (config.TAILORED_CV_DIR, (j or {}).get("tailored_cv_file", ""))):
            if not name:
                return None
            docx = (base / name).with_suffix(".docx")
            found = pdf.pdf_for(docx)
            if found is None and docx.is_file():
                if make:
                    found = pdf.to_pdf(docx)
                elif pdf.available():
                    found = docx                       # can be made when asked for
            if found is None and base == config.LETTERS_DIR:
                # a letter of your own: used when it is a PDF already (the app writes nothing into your own folder)
                own = config.COVER_LETTERS_DIR / os.path.basename(str(name))
                found = next((path for path in (own, own.with_suffix(".pdf")) if path.suffix.lower() == ".pdf" and path.is_file()), None)
            if found is None:
                return None
            parts.append(found)
        return parts

    def _can_combine(self, j) -> bool:
        return self._pdf_parts(j) is not None

    def combined_pdf(self, job_id):
        """Write the letter followed by the CV as one PDF (data/combined/) and open it."""
        j = store.find(store.load_jobs(), job_id)
        parts = self._pdf_parts(j, make=True) if j else None
        if not parts:
            return {"ok": False, "msg": "A single PDF needs both a letter and an adapted CV as PDF. The app makes those copies "
                                        "with LibreOffice; a letter of your own must be a PDF already."}
        stem = _stem(j["tailored_cv_file"]).replace("_CV_", "_Application_")
        if "_Application_" not in stem:
            stem += "_application"
        out = pdf.combine(parts, config.DATA_DIR / "combined" / f"{stem}.pdf")
        if out is None:
            return {"ok": False, "msg": "The two PDF files could not be joined."}
        self._open(out)
        return {"ok": True, "file": out.name, "pages": pdf.page_count(out)}

    def my_letters(self):
        """Where your own letters go, and how many are there."""
        folder = config.COVER_LETTERS_DIR
        try:
            count = sum(1 for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".docx", ".pdf"))
        except OSError:
            count = 0
        return {"folder": str(folder), "name": folder.name, "count": count, "inside_app": folder == config.MY_LETTERS_DIR}

    def open_my_letters(self):
        folder = config.COVER_LETTERS_DIR
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return {"ok": False}
        self._open(folder)
        return {"ok": True}
