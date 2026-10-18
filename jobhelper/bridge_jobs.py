"""The Qt bridge, part: what the job windows and the lists ask for. Almost every slot hands over
to `ui_api.Api`; the few that take seconds answer later through a signal."""
from __future__ import annotations

import os
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

    @Slot(result="QVariantMap")
    def recoveryKey(self):
        """The key to the encrypted data, to show when the person asks for it in the Account card.
        It is never written to a log or put into a message."""
        from . import vault
        try:
            if vault.state() != "ok":
                return {"ok": False, "msg": "There is no key to show: data protection is not on, or its key is missing."}
            return {"ok": True, "key": vault.recovery_key()}
        except Exception:  # noqa: BLE001 - the reason could carry the key
            return {"ok": False, "msg": "The recovery key could not be read from the Keychain."}

    @Slot(str, result="QVariantMap")
    def restoreKey(self, text):
        """Put a saved recovery key back into the Keychain (a new Mac, or after the Keychain was reset)."""
        from . import vault
        text = str(text or "").strip()
        if not text:
            return {"ok": False, "msg": "Paste your recovery key first."}
        if len(text) > 200 or not text.isascii() or " " in text:
            return {"ok": False, "msg": "That is not a recovery key. It is one line of letters, digits, - and _, with no spaces."}
        try:
            vault.restore_key(text)
        except vault.VaultError as e:
            return {"ok": False, "msg": str(e) if "does not belong" in str(e) else "That is not a recovery key for this data."}
        except Exception:  # noqa: BLE001 - never repeat what was pasted
            return {"ok": False, "msg": "The key could not be put into the Keychain."}
        return {"ok": True}

    @Slot(result="QVariantList")
    def currencies(self):
        return self._api.currencies()

    @Slot(str, result=str)
    def countryOf(self, city):
        return self._api.country_of(city)

    @Slot(result="QVariantList")
    def countries(self):
        """Every country the app knows, for the remote-jobs country picker: [{key, name, area}]."""
        return self._api.countries()

    @Slot(result="QVariantMap")
    def remoteChoices(self):
        """The remote-jobs choices, the parts of the world and the most countries (places.RemoteReach.offered)."""
        return self._api.remote_choices()

    @Slot(str, str, result="QVariantMap")
    def mailServer(self, address, typed):
        """What the app knows about an address's mail provider, for the line under the fields:
        {host, known, gmail, hint, problem}."""
        from . import mailhosts
        return mailhosts.server_for(address, typed)

    @Slot(int, str, str, str)
    def saveEmailChecked(self, box, user, password, host):
        """Try the mailbox's address and password for real, then save them. In the background
        (it talks to the mail server); the answer arrives as emailSaved: {ok, msg, note, box}.
        A refused password is not saved. With no connection it is saved, and `note` says it was not tried.
        `host` is the IMAP server, typed for a provider the app does not know ('' otherwise)."""
        def work():
            try:
                result = self._save_email_checked(box, str(user or ""), str(password or ""), str(host or ""))
            except Exception as e:  # noqa: BLE001 - the card must always get an answer
                trouble.note("saving the mailbox", e)
                result = {"ok": False, "msg": "The mailbox could not be saved."}
            result["box"] = box
            self._post("emailSaved", result)
        threading.Thread(target=work, daemon=True).start()

    def _save_email_checked(self, box, user, password, host=""):
        from . import email_client, mailhosts
        from .qt_bridge import _address_problem
        if box not in (1, 2):
            return {"ok": False, "msg": "There is no such mailbox."}
        user, host = user.strip(), host.strip().lower()
        problem = _address_problem(user)
        if problem:
            return {"ok": False, "msg": problem}
        if box == 2 and user.lower() == config.IMAP_USER.lower():
            return {"ok": False, "msg": "That is already your main job email."}
        server = mailhosts.server_for(user, host)
        if server["problem"]:
            return {"ok": False, "msg": server["problem"]}
        if not server["host"]:
            return {"ok": False, "msg": server["hint"]}
        same_address = user.lower() == (config.IMAP_USER if box == 1 else config.IMAP_USER_2).lower()
        kept = (config.IMAP_PASSWORD if box == 1 else config.IMAP_PASSWORD_2) if same_address or not password.strip() else ""
        if password.strip():
            problem = mailhosts.password_problem(user, server["host"], password)
            if problem:
                return {"ok": False, "msg": problem}
        effective = password.strip() or kept
        if not effective:
            return {"ok": False, "msg": "Enter the password for that address."}
        tried = email_client.try_login(user, effective, host=server["host"])
        if tried.get("ok") is False:
            return {"ok": False, "msg": tried["msg"]}
        if box == 1:
            config.set_imap(user, effective, host=host)        # '' forgets a server typed earlier: the address tells it now
        else:
            config.set_imap2(user, effective, host=host)
        saved = {"ok": True}
        if tried.get("ok") is None:
            saved["note"] = "Saved. " + tried["msg"] + " The first email scan will show whether it works."
        return saved

    @Slot(int)
    def testMailbox(self, box):
        """Sign in to a saved mailbox once, to learn whether it can still be read (an app password may have
        been cancelled). In the background; the answer arrives as emailTested: {box, ok, msg}."""
        def work():
            from . import email_client
            user, password = (config.IMAP_USER, config.IMAP_PASSWORD) if box == 1 else (config.IMAP_USER_2, config.IMAP_PASSWORD_2)
            if box not in (1, 2) or not user or not password:
                result = {"ok": False, "msg": "That mailbox is not connected yet."}
            else:
                try:
                    tried = email_client.try_login(user, password, host=config.imap_host(box))
                    result = {"ok": tried.get("ok") is True,
                              "msg": f"Signed in to {user}: the mailbox can be read." if tried.get("ok") is True else tried.get("msg", "It did not work.")}
                except Exception as e:  # noqa: BLE001 - the card must always get an answer
                    trouble.note("trying a saved mailbox", e)
                    result = {"ok": False, "msg": "The mailbox could not be tried."}
            result["box"] = box
            self._post("emailTested", result)
        threading.Thread(target=work, daemon=True).start()

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
        if self._quiet:
            return 0
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

    # ── the assistant ───────────────────────────────────────────
    @Slot(result="QVariantMap")
    def myDetails(self):
        return self._api.my_details()

    @staticmethod
    def _details(text):
        """The page sends its fields as JSON text: lists of jobs and degrees arrive whole that way."""
        import json
        try:
            return json.loads(text or "")
        except ValueError:
            return None

    @Slot(str, result="QVariantMap")
    def checkMyDetails(self, values):
        return self._api.check_my_details(self._details(values))

    @Slot(str, result="QVariantMap")
    def saveMyDetails(self, values):
        return self._api.save_my_details(self._details(values))

    @Slot(result="QVariantList")
    def assistantJobs(self):
        return self._api.assistant_jobs()

    @Slot(str, str, str)
    def askAssistant(self, text, context_job, chosen_job):
        """Runs in the background (it talks to Chrome and may ask Claude); the answer arrives as assistantReady.
        `context_job` is the job whose window is open, `chosen_job` the one picked in the assistant's own list."""
        def work():
            try:
                result = self._api.assistant_talk(text, context_job, chosen_job,
                                                  progress=lambda words: self._post("assistantProgress", {"text": str(words)}))
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                trouble.note("the assistant's request", e)
                result = {"ok": False, "action": "none", "msg": str(e) or type(e).__name__}
            self._post("assistantReady", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, str, str)
    def assistantDo(self, what, arg, job_id):
        """One of the small things the assistant offers after a fill, in the background; the answer arrives as assistantReady."""
        def work():
            try:
                result = {"open_form": lambda: self._api.assistant_open_form(arg, job_id), "files": lambda: self._api.assistant_files(job_id),
                          "learn": self._api.assistant_learn, "forget": self._api.assistant_forget,
                          "cv_lists": self._api.assistant_cv_lists, "draft": lambda: self._api.draft_my_answer(arg),
                          "confirm": lambda: self._api.assistant_confirm(self._details(arg)),
                          "review": lambda: self._api.assistant_review(job_id),
                          "undo": self._api.assistant_undo, "judge": self._api.assistant_judge_page,
                          "practice": lambda: self._api.assistant_practice(job_id),
                          "practice_answer": lambda: self._api.assistant_practice_answer(
                              job_id, (self._details(arg) or {}).get("question", ""), (self._details(arg) or {}).get("answer", ""))}[what]()
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                trouble.note(f"the assistant's request ({what})", e)
                result = {"ok": False, "msg": str(e) or type(e).__name__}
            result.setdefault("action", what)
            if what in ("files", "learn", "forget", "cv_lists", "draft"):
                result["action"] = what
            self._post("assistantReady", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def noticeForm(self):
        """Looks whether the tab in front is the form of a tracked job (only when turned on); the answer arrives as formNoticed."""
        def work():
            try:
                self._post("formNoticed", self._api.assistant_notice())
            except Exception as e:  # noqa: BLE001 - looking must never disturb anything
                trouble.note("noticing a form in Chrome", e)
        threading.Thread(target=work, daemon=True).start()

    @Slot(result="QVariantMap")
    def assistantBriefing(self):
        return self._api.assistant_briefing()

    @Slot(str, str, result=bool)
    def nudgeDone(self, job_id, kind):
        return bool(self._api.assistant_nudge_done(job_id, kind).get("ok"))

    @Slot(result=bool)
    def assistantWatching(self):
        return self._api.assistant_watching()

    @Slot(bool, result="QVariantMap")
    def setAssistantWatch(self, on):
        return self._api.assistant_set_watch(bool(on))

    @Slot(result="QVariantMap")
    def assistantNotes(self):
        return self._api.assistant_notes_list()

    @Slot(int, result="QVariantMap")
    def forgetNote(self, number):
        return self._api.assistant_forget_note(number)

    @Slot(result="QVariantMap")
    def assistantBrowser(self):
        return self._api.assistant_browser()

    @Slot(str, result="QVariantMap")
    def setAssistantBrowser(self, key):
        return self._api.assistant_set_browser(key)

    @Slot()
    def newTalk(self):
        self._api.assistant_new_talk()

    @Slot()
    def watchForm(self):
        """Looks at the form in Chrome in the background; the answer arrives as formWatched."""
        def work():
            self._post("formWatched", self._api.assistant_watch())
        threading.Thread(target=work, daemon=True).start()

    @Slot(result="QVariantMap")
    def myAnswers(self):
        return self._api.my_answers()

    @Slot(str, str, str, result="QVariantMap")
    def saveMyAnswer(self, question, answer, was):
        return self._api.save_my_answer(question, answer, was)

    @Slot(str, result="QVariantMap")
    def deleteMyAnswer(self, question):
        return self._api.delete_my_answer(question)

    @Slot(str, result=str)
    def localFile(self, url):
        """A file chosen in a file window, as a path ('' when it is not a file on this Mac)."""
        from PySide6.QtCore import QUrl
        path = QUrl(url).toLocalFile() if "://" in str(url) else str(url)
        return path if path and os.path.isfile(path) else ""

    @Slot(result="QVariantMap")
    def assistantMemory(self):
        return self._api.assistant_memory()

    @Slot(result="QVariantMap")
    def weekSummary(self):
        return self._api.week_summary()

    @Slot(bool, result="QVariantMap")
    def selfCheck(self, claude_signed_in):
        """The start-up check; the window passes what its connection check found about Claude."""
        return self._api.self_check(bool(claude_signed_in))

    @Slot(str, result="QVariantMap")
    def fixProblem(self, action):
        """The button on the start-up check's line: repair the statuses, or restore a damaged file from a backup."""
        if self._running:
            return {"ok": False, "msg": "A search or scan is running. Try again when it has finished."}
        return self._api.fix_problem(action)

    @Slot(result=str)
    def notificationPermission(self):
        """Whether macOS shows JobHelper's notifications: "allowed", "off", "not asked" or "unknown"."""
        return self._api.notification_permission()

    @Slot(result="QVariantMap")
    def testNotification(self):
        return self._api.test_notification()

    @Slot()
    def openNotificationSettings(self):
        self._api.open_notification_settings()

    @Slot(result="QVariantList")
    def changelog(self):
        return self._api.changelog()

    @Slot(result="QVariantMap")
    def limits(self):
        """How long what you type may be (SystemService.limits): the window reads these, it keeps no copy."""
        return self._api.limits()

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

    @Slot(result="QVariantMap")
    def usageOverview(self):
        return self._api.usage_overview()

    @Slot(result="QVariantMap")
    def troubleLog(self):
        return self._api.trouble_log()

    @Slot(result="QVariantMap")
    def showTroubleLog(self):
        return self._api.show_trouble_log()

    @Slot(str, str)
    def storage(self, action, folder):
        """Make a full backup ("backup"), check that backups restore ("check") or save a readable copy
        into a folder ("export"). In the background; the answer arrives as storageDone: {action, ok, msg}."""
        def work():
            if self._running:
                result = {"ok": False, "msg": "A search or scan is running. Do this when it has finished."}
            else:
                try:
                    result = {"backup": self._api.backup_all, "check": self._api.backup_check,
                              "export": lambda: self._api.backup_export(folder)}.get(action, lambda: {"ok": False, "msg": "There is no such action."})()
                except Exception as e:  # noqa: BLE001 - the window must always get an answer
                    trouble.note("working with the backups", e)
                    result = {"ok": False, "msg": "That did not work. Nothing was changed."}
            result["action"] = action
            self._post("storageDone", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, result="QVariantList")
    def filingTargets(self, text):
        return self._api.filing_targets(text)

    @Slot(str, str, result="QVariantMap")
    def refileResponse(self, msg_id, job_id):
        if self._running:
            return {"ok": False, "msg": "A search or scan is running. File the reply when it has finished."}
        try:
            return self._api.refile_response(msg_id, job_id)
        except Exception as e:  # noqa: BLE001 - the window must always get an answer
            trouble.note("filing a reply under another application", e)
            return {"ok": False, "msg": "The reply could not be filed there."}

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
