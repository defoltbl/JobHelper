"""The Qt bridge, part: what the job windows and the lists ask for. Almost every slot hands over
to `ui_api.Api`; the few that take seconds answer later through a signal."""
from __future__ import annotations

import threading

from PySide6.QtCore import Slot

from . import (config, notify, planner, trouble)


class JobSlots:
    """Mixed into `qt_bridge.Bridge`; uses its `_api`, `_running`, `_post` and signals."""

    @Slot(str, str, result="QVariantMap")
    def setDescription(self, job_id, text):
        return self._api.set_description(job_id, text)

    @Slot(str, result="QVariantMap")
    def rereadPosting(self, job_id):
        return self._api.reread_posting(job_id)

    @Slot(str, result="QVariantMap")
    def shelveDocs(self, job_id):
        return self._api.shelve_docs(job_id)

    @Slot(str, result="QVariantMap")
    def unshelveDocs(self, job_id):
        if self._running:
            return {"ok": False, "msg": "A search or scan is running. Put the documents back when it has finished."}
        return self._api.unshelve_docs(job_id)

    @Slot(int, result="QVariantMap")
    def shelfStatus(self, days):
        try:
            return self._api.shelf_status(days)
        except Exception as e:  # noqa: BLE001 - Options must open whatever the backup folder looks like
            return {"ok": False, "msg": str(e) or type(e).__name__}

    @Slot(int, int, result="QVariantMap")
    def tidyShelf(self, days, expected):
        if self._running:
            return {"ok": False, "msg": "A search or scan is running. Remove old copies when it has finished."}
        try:
            return self._api.tidy_shelf(days, expected)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": str(e) or type(e).__name__}

    @Slot(result="QVariantMap")
    def lastShelved(self):
        return self._api.last_shelved()

    @Slot(str, result="QVariantMap")
    def unshelveLast(self, batch):
        if self._running:
            return {"ok": False, "msg": "A search or scan is running. Put the documents back when it has finished."}
        return self._api.unshelve_last(batch)

    @Slot(result="QVariantList")
    def staleDocs(self):
        return self._api.stale_docs_list()

    @Slot(int, result="QVariantMap")
    def shelveAllDocs(self, expected):
        if self._running:
            return {"ok": False, "msg": "A search or scan is running. Move the documents when it has finished."}
        return self._api.shelve_all_docs(expected)

    @Slot(result="QVariantMap")
    def rescorePlan(self):
        return self._api.rescore_plan()

    # ── job detail and follow-ups ───────────────────────────────
    @Slot(str, result="QVariantMap")
    def jobDetail(self, job_id):
        return self._api.job_detail(job_id)

    @Slot(str, result="QVariantMap")
    def followupDraft(self, job_id):
        return self._api.followup_draft(job_id)

    @Slot(str, str, result="QVariantMap")
    def setStatus(self, job_id, status):
        return self._api.set_status(job_id, status)

    @Slot(str, str, result="QVariantMap")
    def setApplyDate(self, job_id, text):
        return self._api.set_apply_date(job_id, text)

    @Slot(str, result="QVariantMap")
    def scoreAnyway(self, job_id):
        return self._api.score_anyway(job_id)

    @Slot(str, str, result="QVariantMap")
    def mergeJobs(self, keep_id, drop_id):
        return self._api.merge_jobs(keep_id, drop_id)

    @Slot(str, str, result="QVariantMap")
    def keepSeparate(self, a_id, b_id):
        return self._api.keep_separate(a_id, b_id)

    @Slot(str, str, result="QVariantMap")
    def saveEmail2(self, user, password):
        """Add or change the optional second mailbox (blank password keeps the current one)."""
        try:
            from .qt_bridge import _address_problem
            problem = _address_problem(user)
            if problem:
                return {"ok": False, "msg": problem}
            if user.strip().lower() == config.IMAP_USER.lower():
                return {"ok": False, "msg": "That is already your main job email."}
            if not (password.strip() or config.IMAP_PASSWORD_2):
                return {"ok": False, "msg": "Enter the App Password for that address."}
            config.set_imap2(user.strip(), password.strip() or config.IMAP_PASSWORD_2)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": str(e)}

    @Slot(str, result=str)
    def countryOf(self, city):
        return self._api.country_of(city)

    @Slot(int, str, str)
    def saveEmailChecked(self, box, user, password):
        """Try the mailbox's address and App Password for real, then save them. In the background
        (it talks to the mail server); the answer arrives as emailSaved: {ok, msg, note, box}.
        A refused password is not saved. With no connection it is saved, and `note` says it was not tried."""
        def work():
            try:
                result = self._save_email_checked(box, str(user or ""), str(password or ""))
            except Exception as e:  # noqa: BLE001 - the card must always get an answer
                trouble.note("saving the mailbox", e)
                result = {"ok": False, "msg": "The mailbox could not be saved."}
            result["box"] = box
            self._post("emailSaved", result)
        threading.Thread(target=work, daemon=True).start()

    def _save_email_checked(self, box, user, password):
        from . import email_client
        from .qt_bridge import _address_problem
        if box not in (1, 2):
            return {"ok": False, "msg": "There is no such mailbox."}
        problem = _address_problem(user)
        if problem:
            return {"ok": False, "msg": problem}
        if box == 2 and user.strip().lower() == config.IMAP_USER.lower():
            return {"ok": False, "msg": "That is already your main job email."}
        effective = password.strip() or (config.IMAP_PASSWORD if box == 1 else config.IMAP_PASSWORD_2)
        if not effective:
            return {"ok": False, "msg": "Enter the App Password for that address."}
        tried = email_client.try_login(user.strip(), effective)
        if tried.get("ok") is False:
            return {"ok": False, "msg": tried["msg"]}
        saved = self.saveEmail(user, password) if box == 1 else self.saveEmail2(user, password)
        if saved.get("ok") and tried.get("ok") is None:
            saved["note"] = "Saved. " + tried["msg"] + " The first email scan will show whether it works."
        return saved

    @Slot(result="QVariantMap")
    def removeEmail2(self):
        try:
            config.remove_imap2()
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": str(e)}

    @Slot(str, str, str, str, str, result="QVariantMap")
    def setEvent(self, job_id, day, time_text, kind, note):
        return self._api.set_event(job_id, day, time_text, kind, note)

    @Slot(str, result="QVariantMap")
    def clearEvent(self, job_id):
        return self._api.clear_event(job_id)

    @Slot(result="QVariantList")
    def upcoming(self):
        return self._api.upcoming(4)

    @Slot(result=int)
    def remind(self):
        """Announce dates that are tomorrow or today (once per day each). Returns how many."""
        due = self._api.due_reminders()
        for item in due:
            notify.send(planner.reminder_text(item), "Reminder")
        return len(due)

    @Slot(str, "QVariantMap", result="QVariantMap")
    def saveCompanyNotes(self, company, fields):
        return self._api.save_company_notes(company, dict(fields or {}))

    @Slot(str, str)
    def addReply(self, job_id, text):
        """Runs in the background (it may ask Claude); the answer arrives as replyReady."""
        def work():
            try:
                result = self._api.add_reply(job_id, text)
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                result = {"ok": False, "msg": str(e) or type(e).__name__}
            result["job_id"] = job_id
            self._post("replyReady", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot(result="QVariantMap")
    def myLetters(self):
        return self._api.my_letters()

    @Slot(result="QVariantMap")
    def openMyLetters(self):
        return self._api.open_my_letters()

    @Slot(str, str, result="QVariantMap")
    def showInFolder(self, kind, job_id):
        return self._api.show_in_folder(kind, job_id)

    @Slot(str, str, result="QVariantMap")
    def applyStep(self, job_id, step):
        return self._api.apply_step(job_id, step)

    @Slot(str, result="QVariantMap")
    def combinedPdf(self, job_id):
        return self._api.combined_pdf(job_id)

    @Slot(str, result="QVariantMap")
    def exportEvent(self, job_id):
        return self._api.export_event(job_id)

    @Slot(str, result="QVariantMap")
    def thanksDraft(self, job_id):
        return self._api.thanks_draft(job_id)

    @Slot(str, result=bool)
    def markThanked(self, job_id):
        return self._api.mark_thanked(job_id)

    @Slot(str, result="QVariantMap")
    def formAnswers(self, job_id):
        return self._api.form_answers(job_id)

    @Slot(str, result="QVariantMap")
    def checkQuestions(self, questions_text):
        return self._api.check_questions(questions_text)

    @Slot(str, str)
    def draftAnswers(self, job_id, questions_text):
        """Runs in the background (it asks Claude); the answer arrives as answersReady."""
        def work():
            try:
                result = self._api.make_form_answers(job_id, questions_text)
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                result = {"ok": False, "msg": str(e) or type(e).__name__}
            result["job_id"] = job_id
            self._post("answersReady", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, "QVariantList", result="QVariantMap")
    def saveFormAnswers(self, job_id, items):
        return self._api.save_form_answers(job_id, [dict(i) for i in (items or [])])

    @Slot(result="QVariantMap")
    def weekSummary(self):
        return self._api.week_summary()

    @Slot(bool, result="QVariantMap")
    def selfCheck(self, claude_signed_in):
        """The start-up check; the window passes what its connection check found about Claude."""
        return self._api.self_check(bool(claude_signed_in))

    @Slot(result="QVariantList")
    def changelog(self):
        return self._api.changelog()

    @Slot(result="QVariantMap")
    def filteredOut(self):
        return self._api.filtered_out()

    @Slot(int, result="QVariantMap")
    def bringBack(self, index):
        return self._api.bring_back(index)

    @Slot(int, result="QVariantMap")
    def openFiltered(self, index):
        return self._api.open_filtered(index)

    @Slot(str, result="QVariantMap")
    def cvCompare(self, job_id):
        return self._api.cv_compare(job_id)

    @Slot(str, result="QVariantMap")
    def interviewPrep(self, job_id):
        return self._api.interview_prep(job_id)

    @Slot(str)
    def prepareInterview(self, job_id):
        """Runs in the background (it asks Claude); the answer arrives as prepReady."""
        def work():
            try:
                result = self._api.make_interview_prep(job_id)
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                result = {"ok": False, "msg": str(e) or type(e).__name__}
            result["job_id"] = job_id
            self._post("prepReady", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, result="QVariantMap")
    def prepParts(self, job_id):
        return self._api.prep_parts(job_id)

    @Slot(str, "QVariantList", result="QVariantMap")
    def savePrepParts(self, job_id, parts):
        return self._api.save_prep_parts(job_id, [dict(p) for p in (parts or [])])

    @Slot(str, bool, result="QVariantMap")
    def prepDocument(self, job_id, reveal):
        return self._api.prep_document(job_id, bool(reveal))

    @Slot(str, result=str)
    def prepText(self, job_id):
        return self._api.prep_text(job_id)

    @Slot(result="QVariantMap")
    def insights(self):
        return self._api.insights()

    @Slot(str, result="QVariantMap")
    def dismissJob(self, job_id):
        return self._api.dismiss_job(job_id)

    @Slot(str, result="QVariantMap")
    def restoreJob(self, job_id):
        return self._api.restore_job(job_id)

    @Slot(result="QVariantList")
    def dismissedLeads(self):
        return self._api.dismissed()

    @Slot(str, result="QVariantMap")
    def letterForEdit(self, job_id):
        return self._api.letter_for_edit(job_id)

    @Slot(str, "QVariantList", result="QVariantMap")
    def saveLetter(self, job_id, paragraphs):
        return self._api.save_letter(job_id, [str(p) for p in (paragraphs or [])])

    @Slot(str, "QVariantList", int, str)
    def rewriteParagraph(self, job_id, paragraphs, index, hint):
        """Runs in the background (it asks Claude); the answer arrives as paragraphReady."""
        texts = [str(p) for p in (paragraphs or [])]

        def work():
            try:
                result = self._api.rewrite_paragraph(job_id, texts, index, hint)
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                result = {"ok": False, "msg": str(e) or type(e).__name__}
            result.setdefault("index", int(index))
            result["job_id"] = job_id
            self._post("paragraphReady", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, result="QVariantMap")
    def responseDetail(self, msg_id):
        return self._api.response_detail(msg_id)

    @Slot(str, result=bool)
    def markFollowedUp(self, job_id):
        return bool(self._api.mark_followed_up(job_id).get("ok"))

    @Slot(str, result=bool)
    def copyText(self, text):
        """Put text on the clipboard (the follow-up draft). Nothing is sent anywhere."""
        from PySide6.QtGui import QGuiApplication
        board = QGuiApplication.clipboard()
        if board is None:
            return False
        board.setText(text or "")
        return True
