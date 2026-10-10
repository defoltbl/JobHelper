// DetailDialog: one window of the JobHelper app, created once in Main.qml as `detailDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: detailDialog; objectName: "detailDialog"
    modal: true; anchors.centerIn: parent
    // text you typed here and did not save yet: Esc and ✕ must not throw it away unasked
    readonly property var pending: {
        var out = [], n = job.company_notes || {}, e = job.event || {};
        if (pastedText.text.trim() !== "") out.push("the pasted posting text");
        if (replyText.text.trim() !== "") out.push("the pasted reply");
        if (cnContact.text !== (n.contact || "") || cnSalary.text !== (n.salary || "") || cnAsked.text !== (n.asked || "")
                || cnNotes.text !== (n.notes || "")) out.push("the notes about the company");
        if (evDate.text !== (e.date || "") || evTime.text !== (e.time || "") || evNote.text !== (e.note || "")) out.push("the date to remember");
        if (dateField.text !== (job.applied || "")) out.push("the day you applied");
        return out;
    }
    closePolicy: pending.length > 0 ? Popup.NoAutoClose : Popup.CloseOnEscape
    property bool confirmClose: false
    property string closeNote: ""
    property string confirmAction: ""     // the button that was asked about once ("apply", "dismiss")
    // A button that closes this window with text still unsaved asks once, as the ✕ does.
    function mayLeave(action, label) {
        if (pending.length > 0 && confirmAction !== action) {
            confirmAction = action; confirmClose = false;
            closeNote = "Not saved yet: " + pending.join(", ") + ". Save it, or press " + label + " once more to discard it.";
            return false;
        }
        return true;
    }
    // ── going through a list of jobs one after another ("Review these N one by one" in New Jobs) ──
    property var reviewQueue: []          // the ids still to look at, in the order of the list
    property int reviewTotal: 0
    property int reviewDone: 0            // how many were decided (applied or dismissed) in this round
    readonly property int reviewAt: reviewQueue.indexOf(job.id || "")
    readonly property bool reviewing: reviewQueue.length > 0 && reviewAt >= 0
    property string reviewNote: ""
    function startReview(ids) {
        reviewQueue = ids || []; reviewTotal = reviewQueue.length; reviewDone = 0; reviewNote = "";
        if (reviewQueue.length > 0) show(reviewQueue[0]);
    }
    function reviewStep(by) {             // -1 = the one before, +1 = the next one; the job itself is left as it is
        if (!reviewing || !mayLeave("step" + by, by > 0 ? "Next" : "Previous")) return;
        var to = reviewAt + by;
        if (to < 0 || to >= reviewQueue.length) return;
        var keep = reviewQueue, total = reviewTotal, done = reviewDone;
        show(keep[to]); reviewQueue = keep; reviewTotal = total; reviewDone = done;
    }
    // after a decision on the job in view: on to the one that followed it, or the end of the round
    function reviewAfterDecision(what) {
        var at = reviewAt, rest = reviewQueue.filter(function (id) { return id !== job.id; });
        var total = reviewTotal, done = reviewDone + 1;
        win.countsData = bridge.counts(); win.refreshOpenView();
        if (rest.length === 0) { reviewQueue = []; close(); ticker.text = what + " That was the last of the " + total + " jobs."; return; }
        show(rest[Math.min(at, rest.length - 1)]);
        reviewQueue = rest; reviewTotal = total; reviewDone = done; reviewNote = what;
    }
    function markApplied() {
        if (!mayLeave("apply", "Mark applied")) return;
        var wasReviewing = reviewing;
        if (!bridge.applyJob(job.id)) {           // refused (already an application, or gone): say so, do not claim it moved
            ticker.text = "That job was not moved: it is already among your applications, or it is no longer in the list."; close(); win.reloadAll(); return;
        }
        ticker.text = "Moved to Applications (waiting).";
        if (wasReviewing) { reviewAfterDecision("Moved to Applications."); win.reloadAll(); return; }
        close(); tableDialog.close(); win.reloadAll();
    }
    function notInterested() {
        if (!mayLeave("dismiss", "Not interested")) return;
        var wasReviewing = reviewing;
        var r = bridge.dismissJob(job.id);
        if (r && r.ok) { ticker.text = "Removed. It will not come back in later searches (see the “not interested” filter to undo).";
            if (wasReviewing) { reviewAfterDecision("Removed from New Jobs."); return; }
            close(); win.countsData = bridge.counts(); win.refreshOpenView(); }
        else ticker.text = (r && r.msg) ? r.msg : "Couldn't remove that job.";
    }
    function tryClose() {                 // the ✕ and, with unsaved text, the Esc key: ask once
        if (pending.length > 0 && !confirmClose) {
            confirmClose = true; confirmAction = "";
            closeNote = "Not saved yet: " + pending.join(", ") + ". Save it, or close once more to discard it.";
            return;
        }
        close();
    }
    onClosed: { confirmClose = false; confirmAction = ""; closeNote = ""; reviewQueue = []; reviewNote = ""; }
    Shortcut { sequence: "Escape"
        enabled: detailDialog.visible && detailDialog.pending.length > 0 && !(formDialog.visible || prepDialog.visible || prepEditDialog.visible
                 || compareDialog.visible || letterDialog.visible || responseDialog.visible)
        onActivated: detailDialog.tryClose() }
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(760, win.width - 80); height: Math.min(700, win.height - 70)
    padding: 0
    property var job: ({})
    property var draft: ({})
    property string note: ""
    property string dateErr: ""
    property bool prepBusy: false
    property string prepErr: ""
    property string prepJob: ""
    property string eventErr: ""
    property string eventKind: "interview"
    property string notesInfo: ""
    property bool replyOpen: false
    property bool replyBusy: false
    property string replyInfo: ""
    property string replyErr: ""
    property string replyJob: ""
    // the apply checklist: only the steps this job has something for
    readonly property var applySteps: {
        var j = job, out = [];
        if (j.url) out.push({ key: "posting", label: "Read the posting and open its application form", button: "Open posting ↗" });
        if (j.cv) out.push({ key: "cv", label: "Check your adapted CV", button: j.cv_pdf === true ? "Open CV PDF" : "Open CV" });
        if (j.letter) out.push({ key: "letter", label: "Check your cover letter", button: j.letter_pdf === true ? "Open letter PDF" : "Open letter" });
        if (j.can_combine === true) out.push({ key: "combined", label: "If the form takes one file: letter and CV as a single PDF", button: "Make one PDF" });
        out.push({ key: "answers", label: "Answers for this job's form, drafted from your CV", button: j.has_answers === true ? "Open answers" : "Form answers" });
        return out;
    }
    readonly property int stepsDone: {
        var done = job.apply_steps || [], n = 0;
        for (var i = 0; i < applySteps.length; i++) if (done.indexOf(applySteps[i].key) >= 0) n++;
        return n;
    }
    function onePdf() {
        var r = bridge.combinedPdf(job.id);
        ticker.text = (r && r.ok) ? "Opened one PDF with the letter and the CV (" + r.pages + " pages)." : ((r && r.msg) || "Couldn't make the single PDF.");
        return !!(r && r.ok);
    }
    function showFile(kind) {       // select the file in Finder, ready to drag into an application form
        var r = bridge.showInFolder(kind, job.id);
        ticker.text = (r && r.ok) ? "Shown in its folder: " + r.file : ((r && r.msg) || "Couldn't show that file.");
    }
    function doStep(key) {
        var ok = true;
        if (key === "posting") { var r = bridge.openUrl(job.id); ok = !!(r && r.ok); ticker.text = ok ? "Opened the job posting in your browser." : "No link for this job."; }
        else if (key === "cv") bridge.openDoc(job.cv_pdf === true ? "cv_pdf" : "cv", job.cv);
        else if (key === "letter") bridge.openDoc(job.letter_pdf === true ? "letter_pdf" : "letter", job.letter);
        else if (key === "combined") ok = onePdf();
        else if (key === "answers") { formDialog.show(job.id); return; }      // ticked there, once an answer is drafted or copied
        if (ok) { bridge.applyStep(job.id, key); refresh(); }
    }
    property bool confirmRemake: false
    // the posting's text, pasted by hand when the app could not read it
    property bool pasteOpen: false
    property string pasteErr: ""
    readonly property int pasteMin: 200
    readonly property int pasteMax: 20000
    function savePasted() {
        pasteErr = "";
        var n = pastedText.text.trim().length;
        if (n < pasteMin) { pasteErr = "That is only " + n + " characters. Paste the whole posting (at least " + pasteMin + ")."; return; }
        if (n > pasteMax) { pasteErr = "That is " + n + " characters; the most is " + pasteMax + ". Paste only the posting itself."; return; }
        var r = bridge.setDescription(job.id, pastedText.text);
        if (!(r && r.ok)) { pasteErr = (r && r.msg) || "The text could not be saved."; return; }
        pastedText.text = ""; pasteOpen = false; refresh(); win.refreshOpenView();
        scoreAfterText("The posting's text is saved.");
    }
    function readAgain() {
        var r = bridge.rereadPosting(job.id);
        if (r && r.ok) { refresh(); win.refreshOpenView(); scoreAfterText("Read " + r.chars + " characters of the posting."); }
        else { scoreBad = true; scoreNote = (r && r.msg) || "The posting could not be read.";
               if (job.can_rescore !== true) ticker.text = scoreNote; }
    }
    // New text for a posting makes its old score out of date: score it again at once (one Claude call),
    // or say plainly why that has to wait.
    property string scoreLead: ""         // what just happened, said before the result of the scoring
    function scoreAfterText(what) {
        scoreBad = false; scoreLead = "";
        if (job.can_rescore !== true) { scoreNote = what + " The next search will score it."; ticker.text = scoreNote; return; }
        if (win.appRunning) { scoreNote = what + " A search or scan is running: press Score again when it has finished."; return; }
        if (scoreBusy) { scoreNote = what + " Another job is being scored: press Score again when it has finished."; return; }
        scoreAgain(); scoreLead = what + " ";
    }
    // documents written when the score was higher than your limit is now
    property bool confirmShelve: false
    property string shelveNote: ""
    property bool shelveBad: false
    function shelve() {
        if (!confirmShelve) {
            confirmShelve = true; shelveBad = false;
            shelveNote = "The letter and CV the app wrote go to an encrypted backup; the job stays in the list. Press once more to move them.";
            return;
        }
        confirmShelve = false;
        var r = bridge.shelveDocs(job.id);
        shelveBad = !(r && r.ok);
        shelveNote = (r && r.ok) ? r.moved + (r.moved === 1 ? " file" : " files") + " moved to the backup." : ((r && r.msg) || "Couldn't move the documents.");
        if (r && r.ok) { refresh(); win.countsData = bridge.counts(); win.refreshOpenView(); }
    }
    function unshelve() {
        confirmShelve = false;
        if (win.appRunning) { shelveBad = true; shelveNote = "A search or scan is running. Put the documents back when it has finished."; return; }
        var r = bridge.unshelveDocs(job.id);
        shelveBad = !(r && r.ok);
        shelveNote = (r && r.ok) ? r.restored + (r.restored === 1 ? " file is" : " files are") + " back in place."
                                 : ((r && r.msg) || "Couldn't put the documents back.");
        if (r && r.ok) { refresh(); win.countsData = bridge.counts(); win.refreshOpenView(); }
    }
    function dayTime(iso) { return (iso || "").replace("T", " ").slice(0, 16); }
    property bool docsBusy: false         // the CV and the letter of a job are being written
    property string docsJob: ""
    property string docsNote: ""
    property bool docsBad: false
    function writeDocs() {
        docsNote = ""; docsBad = false;
        if (win.appRunning) { docsBad = true; docsNote = "A search or scan is running. Write the documents when it has finished."; return; }
        if (docsBusy) { docsBad = true; docsNote = "Documents of another job are being written. Try again when they are done."; return; }
        docsBusy = true; docsJob = job.id;
        bridge.writeDocuments(job.id);
    }
    Connections { target: bridge
        function onDocsReady(res) {
            if (res.job_id !== detailDialog.docsJob) return;
            detailDialog.docsBusy = false;
            var text = res.ok ? (res.msg || "Written.") : ("Not written: " + (res.msg || "unknown reason"));
            if (res.job_id === detailDialog.job.id) { detailDialog.docsBad = !res.ok; detailDialog.docsNote = text; if (res.ok) detailDialog.refresh(); }
            else ticker.text = text;
            if (res.ok) { win.countsData = bridge.counts(); win.refreshOpenView(); }
        } }
    property bool scoreBusy: false
    property string scoreJob: ""
    property string scoreNote: ""
    property bool scoreBad: false
    function scoreAgain() {
        scoreNote = ""; scoreBad = false; scoreLead = ""; scoreBusy = true; scoreJob = job.id;
        bridge.rescoreJob(job.id);
    }
    Connections { target: bridge
        function onRescoreReady(res) {
            if (res.job_id !== detailDialog.scoreJob) return;
            detailDialog.scoreBusy = false;
            var here = res.job_id === detailDialog.job.id;
            var lead = detailDialog.scoreLead; detailDialog.scoreLead = "";
            var text = lead + (res.ok ? (res.before === res.score ? "Scored again: still " + res.score + "."
                                                          : "Scored again: " + res.before + " before, " + res.score + " now.")
                              : ("Not scored again: " + (res.msg || "unknown reason")));
            if (here) { detailDialog.scoreBad = !res.ok; detailDialog.scoreNote = text; if (res.ok) detailDialog.refresh(); }
            else ticker.text = text;
            if (res.ok) { win.countsData = bridge.counts(); win.refreshOpenView(); }
        } }
    property bool notesBad: false         // the line under the company notes is a problem, not a confirmation
    readonly property int notesMax: 2000
    readonly property int replyMax: 8000
    // a single-line field stops taking letters at its limit: say so instead of going silent
    function full(field, what) { return field.text.length >= field.maximumLength ? what + " takes up to " + field.maximumLength + " characters." : ""; }
    property var thanks: ({})
    property string thanksNote: ""
    function saveEvent() {
        eventErr = "";
        var r = bridge.setEvent(job.id, evDate.text, evTime.text, eventKind, evNote.text);
        if (r && r.ok) { refresh("event"); win.upcomingData = bridge.upcoming(); ticker.text = "Date saved. You will be reminded the day before."; }
        else eventErr = (r && r.msg) ? r.msg : "Couldn't save that date.";
    }
    function saveNotes() {
        if (cnNotes.text.length > notesMax) {
            notesBad = true; notesInfo = "The notes are " + (cnNotes.text.length - notesMax) + " characters too long (the limit is " + notesMax + "). Shorten them, then save.";
            return;
        }
        var r = bridge.saveCompanyNotes(job.company || "", { contact: cnContact.text, salary: cnSalary.text, asked: cnAsked.text, notes: cnNotes.text });
        notesBad = !(r && r.ok);
        notesInfo = (r && r.ok) ? "Saved for " + (job.company || "this company") + "." : ((r && r.msg) || "Couldn't save the notes.");
        if (r && r.ok) refresh("notes");
    }
    function fileReply() {
        replyErr = ""; replyInfo = "";
        if (replyText.text.trim().length < 20) { replyErr = "Paste the whole message: that is too short to read."; return; }
        if (replyText.text.length > replyMax) {
            replyErr = "That is " + replyText.text.length + " characters. Paste only the message itself, not the whole page (up to " + replyMax + ").";
            return;
        }
        replyBusy = true; replyJob = job.id;
        bridge.addReply(job.id, replyText.text);
    }
    Connections { target: bridge
        function onReplyReady(res) {
            if (res.job_id !== detailDialog.replyJob) return;
            detailDialog.replyBusy = false;
            if (res.job_id !== detailDialog.job.id) {           // another job is open now: only refresh the lists
                if (res.ok) { win.reloadAll(); win.refreshOpenView(); ticker.text = "The pasted reply was filed as: " + res.stage + "."; }
                else ticker.text = res.msg || "The pasted reply could not be filed.";
                return;
            }
            if (res.ok) {
                detailDialog.replyInfo = "Filed as: " + res.stage + (res.by_rules ? " (read by the app's rules, not by Claude)" : "") + ".";
                replyText.text = ""; detailDialog.replyOpen = false;
                detailDialog.refresh(); win.reloadAll(); win.refreshOpenView();
            } else detailDialog.replyErr = res.msg || "The message could not be filed.";
        } }
    Connections { target: bridge
        function onPrepReady(res) {
            if (res.job_id !== detailDialog.prepJob) return;
            detailDialog.prepBusy = false;
            if (res.ok) { ticker.text = "Interview preparation is ready.";
                          if (detailDialog.visible && detailDialog.job.id === res.job_id) { detailDialog.refresh(); prepDialog.show(res.job_id); } }
            else { detailDialog.prepErr = "Not prepared: " + (res.msg || "unknown reason"); ticker.text = detailDialog.prepErr; }
        } }
    readonly property var fu: job.followup || ({})
    function setStatus(s) {
        var r = bridge.setStatus(job.id, s);
        if (r && r.ok) { refresh(); win.countsData = bridge.counts(); win.refreshOpenView();
                         ticker.text = "Marked " + s.replace("_", " ") + "."; }
        else ticker.text = (r && r.msg) ? r.msg : "Couldn't change the status.";
    }
    function saveDate() {
        dateErr = "";
        var r = bridge.setApplyDate(job.id, dateField.text);
        if (r && r.ok) { refresh("date"); win.countsData = bridge.counts(); win.refreshOpenView(); ticker.text = "Apply date saved."; }
        else dateErr = (r && r.msg) ? r.msg : "Couldn't save that date.";
    }
    onJobChanged: {
        dateField.text = job.applied || "";
        var e = job.event || {};
        evDate.text = e.date || ""; evTime.text = e.time || ""; evNote.text = e.note || ""; eventKind = e.kind || "interview";
        var n = job.company_notes || {};
        cnContact.text = n.contact || ""; cnSalary.text = n.salary || ""; cnAsked.text = n.asked || ""; cnNotes.text = n.notes || "";
    }
    readonly property bool hasWords: (job.matched || []).length + (job.missing || []).length > 0
    function show(jobId) {
        var d = bridge.jobDetail(jobId);
        if (!d || !d.id) { ticker.text = "That job could not be opened."; return; }
        confirmRemake = false; if (!scoreBusy) { scoreNote = ""; scoreBad = false; }
        confirmClose = false; confirmAction = ""; closeNote = ""; replyText.text = ""; docsNote = ""; docsBad = false;
        pasteOpen = false; pasteErr = ""; pastedText.text = ""; confirmShelve = false; shelveNote = ""; shelveBad = false;
        job = d; draft = ({}); note = ""; dateErr = ""; if (!prepBusy) prepErr = "";
        eventErr = ""; notesInfo = ""; notesBad = false; replyErr = ""; replyInfo = ""; replyOpen = false; thanks = ({}); thanksNote = "";
        detailFlick.contentY = 0;
        open();
    }
    // The job is read again after every change. What is typed in this window and not saved yet stays as it is:
    // saving the notes must not empty a date you were still writing. `saved` names the part that was just saved
    // ("notes", "event", "date"), which then shows what was stored.
    function refresh(saved) {
        var d = bridge.jobDetail(job.id);
        if (!(d && d.id)) return;
        var n = job.company_notes || {}, e = job.event || {};
        var notes = saved !== "notes" && (cnContact.text !== (n.contact || "") || cnSalary.text !== (n.salary || "") || cnAsked.text !== (n.asked || "")
                                          || cnNotes.text !== (n.notes || ""))
                    ? [cnContact.text, cnSalary.text, cnAsked.text, cnNotes.text] : null;
        var event = saved !== "event" && (evDate.text !== (e.date || "") || evTime.text !== (e.time || "") || evNote.text !== (e.note || "")
                                          || eventKind !== (e.kind || "interview"))
                    ? [evDate.text, evTime.text, evNote.text, eventKind] : null;
        var day = saved !== "date" && dateField.text !== (job.applied || "") ? dateField.text : null;
        job = d;                              // fills every field from what is stored (onJobChanged)
        if (notes) { cnContact.text = notes[0]; cnSalary.text = notes[1]; cnAsked.text = notes[2]; cnNotes.text = notes[3]; }
        if (event) { evDate.text = event[0]; evTime.text = event[1]; evNote.text = event[2]; eventKind = event[3]; }
        if (day !== null) dateField.text = day;
    }
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
        FocusCatcher {} }
    contentItem: ColumnLayout {
        spacing: 0
        // header
        RowLayout {
            Layout.fillWidth: true; Layout.margins: 16; spacing: 12
            Rectangle { visible: detailDialog.job.score !== undefined && detailDialog.job.score !== null
                implicitWidth: 46; implicitHeight: 46; radius: 12
                color: win.badgeBg(detailDialog.job.tier || ""); border.width: 1
                border.color: win.badgeColor(detailDialog.job.tier || "")
                Text { anchors.centerIn: parent; text: "" + detailDialog.job.score
                    color: win.badgeColor(detailDialog.job.tier || ""); font.pixelSize: 17; font.bold: true } }
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                Text { objectName: "detailTitle"; text: detailDialog.job.title || ""; color: theme.ink; font.pixelSize: 17; font.bold: true
                    Layout.fillWidth: true; wrapMode: Text.Wrap }
                Text { color: theme.soft; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap
                    text: (detailDialog.job.company || "") + (detailDialog.job.location ? "  ·  " + detailDialog.job.location : "") } }
            Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                Layout.alignment: Qt.AlignTop
                Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: detailDialog.tryClose() } }
        }
        // going through a list: where you are, and the way to the next one
        Rectangle { objectName: "reviewBar"; visible: detailDialog.reviewing; Layout.fillWidth: true; color: theme.infobg
            implicitHeight: reviewRow.implicitHeight + 14
            RowLayout { id: reviewRow; anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 8
                Text { objectName: "reviewWhere"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 12
                    text: "Reviewing " + (detailDialog.reviewAt + 1) + " of " + detailDialog.reviewQueue.length + " left"
                          + (detailDialog.reviewDone > 0 ? " · " + detailDialog.reviewDone + " decided" : "")
                          + (detailDialog.reviewNote !== "" ? " · " + detailDialog.reviewNote : "")
                          + ". Decide with Not interested or Mark applied below, or go on and leave this one as it is." }
                SmallButton { objectName: "reviewPrev"; text: "‹ Previous"; enabled: detailDialog.reviewAt > 0; onClicked: detailDialog.reviewStep(-1) }
                SmallButton { objectName: "reviewNext"; primaryStyle: true; text: "Next ›"
                    enabled: detailDialog.reviewAt < detailDialog.reviewQueue.length - 1; onClicked: detailDialog.reviewStep(1) } } }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }

        Flickable {
            id: detailFlick
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentHeight: detailCol.implicitHeight + 28
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            FocusCatcher {}                // a press on empty space in the scroll area
            ColumnLayout {
                id: detailCol
                x: 16; y: 14; width: detailFlick.width - 32; spacing: 12

                ChipFlow {
                    items: [ detailDialog.job.status ? ("" + detailDialog.job.status).replace("_", " ") : "",
                             detailDialog.job.tier ? detailDialog.job.tier + " match" : "",
                             detailDialog.job.posted ? "posted " + detailDialog.job.posted : "",
                             detailDialog.job.applied ? (detailDialog.job.applied_from_email ? "first email " : "applied ") + detailDialog.job.applied : "",
                             detailDialog.job.source || "",
                             detailDialog.job.desired_text || "",
                             detailDialog.job.pay_text || "",
                             detailDialog.job.letter_old_format === true ? "letter: older format, open in Word" : "",
                             (detailDialog.job.score !== null && detailDialog.job.score !== undefined)
                                ? (detailDialog.job.basis === "title" ? "scored from the title only"
                                   : detailDialog.job.basis === "summary" ? "scored from a short summary" : "") : "",
                             detailDialog.job.closed === true ? "no longer accepts applications" : ""
                           ].filter(function (t) { return t !== ""; })
                }

                // everything needed to apply, in order; ticks are kept with the job
                DetailCard { heading: "Before you apply"; objectName: "applyCard"
                    visible: detailDialog.job.is_lead === true && (!!detailDialog.job.cv || !!detailDialog.job.letter)
                    border.color: theme.accent
                    // words of the posting that the adapted CV states as your experience, though your own CV has neither word
                    Text { objectName: "cvCheck"; visible: (detailDialog.job.cv_check || []).length > 0
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.warn; font.pixelSize: 12; font.bold: true
                        text: "Check your adapted CV before you send it. It speaks of " + (detailDialog.job.cv_check || []).join(", ")
                              + ", which " + ((detailDialog.job.cv_check || []).length === 1 ? "is a term" : "are terms")
                              + " of the posting that your own CV does not mention. Keep it only if it is true of you; Compare CV shows where it stands." }
                    Text { objectName: "letterCheck"; visible: (detailDialog.job.letter_check || []).length > 0
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.warn; font.pixelSize: 12; font.bold: true
                        text: "Check your cover letter before you send it. It says you have done something with " + (detailDialog.job.letter_check || []).join(", ")
                              + ", which " + ((detailDialog.job.letter_check || []).length === 1 ? "is a term" : "are terms")
                              + " of the posting that your own CV does not mention. Keep it only if it is true of you; Edit letter lets you change the sentence." }
                    Repeater {
                        model: detailDialog.applySteps
                        RowLayout { Layout.fillWidth: true; spacing: 10
                            readonly property bool ticked: (detailDialog.job.apply_steps || []).indexOf(modelData.key) >= 0
                            Rectangle { implicitWidth: 20; implicitHeight: 20; radius: 10
                                color: parent.ticked ? theme.good : "transparent"; border.width: 1; border.color: parent.ticked ? theme.good : theme.line
                                Text { anchors.centerIn: parent; text: parent.parent.ticked ? "✓" : ""; color: theme.accentInk; font.pixelSize: 12; font.bold: true } }
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 13
                                color: parent.ticked ? theme.soft : theme.ink; text: modelData.label }
                            SmallButton { visible: modelData.key === "cv" || modelData.key === "letter"
                                               || (modelData.key === "combined" && parent.ticked)
                                text: "Show in folder"; onClicked: detailDialog.showFile(modelData.key) }
                            SmallButton { text: modelData.button; onClicked: detailDialog.doStep(modelData.key) }
                        }
                    }
                    RowLayout { Layout.fillWidth: true; spacing: 10
                        Text { objectName: "applyCount"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                            text: detailDialog.stepsDone + " of " + detailDialog.applySteps.length + " done. Then send your application and press Mark applied." }
                        PillButton { objectName: "applyNow"; primaryStyle: true; text: "Mark applied"
                            onClicked: detailDialog.markApplied() }
                    }
                }

                DetailCard { heading: "Why this score"
                    RowLayout { visible: detailDialog.job.can_rescore === true; Layout.fillWidth: true; spacing: 10
                        Text { objectName: "scoreNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 12
                            font.bold: detailDialog.scoreBad
                            color: detailDialog.scoreNote === "" ? theme.faint : (detailDialog.scoreBad ? theme.crit : theme.good)
                            text: detailDialog.scoreBusy ? (detailDialog.scoreJob === detailDialog.job.id ? detailDialog.scoreLead : "") + "Asking Claude…"
                                : detailDialog.scoreNote !== "" ? detailDialog.scoreNote
                                : (detailDialog.job.score_before !== null && detailDialog.job.score_before !== undefined)
                                    ? "It was " + detailDialog.job.score_before + " before it was scored again."
                                    : "Scored with the rules of that day. Score again to apply your current Options (one Claude call)." }
                        SmallButton { objectName: "scoreAgain"; enabled: !detailDialog.scoreBusy && !win.appRunning
                            text: detailDialog.scoreBusy ? "Scoring…" : "Score again"; onClicked: detailDialog.scoreAgain() }
                    }
                    // a job the search wrote no documents for (below your limit, or scored again since): on request
                    RowLayout { objectName: "writeDocsRow"; Layout.fillWidth: true; spacing: 10
                        visible: detailDialog.job.can_write_docs === true || detailDialog.docsNote !== ""
                                 || (detailDialog.docsBusy && detailDialog.docsJob === detailDialog.job.id)
                        Text { objectName: "docsNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                            font.bold: detailDialog.docsBad
                            color: detailDialog.docsNote === "" ? theme.faint : (detailDialog.docsBad ? theme.crit : theme.good)
                            text: (detailDialog.docsBusy && detailDialog.docsJob === detailDialog.job.id) ? "Writing the CV and the letter. This takes about a minute…"
                                : detailDialog.docsNote !== "" ? detailDialog.docsNote
                                : (!detailDialog.job.cv && !detailDialog.job.letter)
                                    ? "No CV or letter was written for this job. You can have them written now (a few Claude calls)."
                                    : "One of the two documents is missing. You can have it written now." }
                        SmallButton { objectName: "writeDocs"; visible: detailDialog.job.can_write_docs === true
                            enabled: !detailDialog.docsBusy && !win.appRunning
                            text: detailDialog.docsBusy ? "Writing…" : (!detailDialog.job.cv && !detailDialog.job.letter ? "Write CV and letter" : "Write what is missing")
                            onClicked: detailDialog.writeDocs() }
                    }
                    // documents left over from a higher score
                    RowLayout { objectName: "staleRow"
                        visible: detailDialog.job.docs_stale === true || detailDialog.job.can_unshelve === true || detailDialog.shelveNote !== ""
                        Layout.fillWidth: true; spacing: 10
                        Text { objectName: "staleText"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 12
                            font.bold: detailDialog.shelveBad
                            color: detailDialog.shelveBad ? theme.crit : (detailDialog.shelveNote !== "" && !detailDialog.confirmShelve ? theme.good : theme.warn)
                            text: detailDialog.shelveNote !== "" ? detailDialog.shelveNote
                                : detailDialog.job.can_unshelve === true
                                  ? "The documents the app wrote for this job were moved to the backup on " + detailDialog.dayTime(detailDialog.job.shelved_when) + "."
                                : "The letter and CV were written when this job scored higher. It is now below your limit of "
                                  + (detailDialog.job.threshold || 0) + ", so check before you use them." }
                        SmallButton { objectName: "shelveDocs"; visible: detailDialog.job.docs_stale === true
                            primaryStyle: detailDialog.confirmShelve
                            text: detailDialog.confirmShelve ? "Yes, move them" : "Move documents to backup"; onClicked: detailDialog.shelve() }
                        SmallButton { objectName: "unshelveDocs"; visible: detailDialog.job.can_unshelve === true
                            text: "Put them back"; onClicked: detailDialog.unshelve() }
                    }
                    // a score that rests on little text: say so, and let the posting's text be pasted in
                    RowLayout { objectName: "basisRow"; visible: detailDialog.job.can_paste_text === true; Layout.fillWidth: true; spacing: 10
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.warn; font.pixelSize: 12
                            text: detailDialog.job.basis === "title"
                                  ? "The app could not read this posting, so the score rests on the title alone and is kept at 40 or below."
                                  : "The app got only a short summary of this posting, so the score rests on little text." }
                        SmallButton { objectName: "rereadPosting"; visible: !!detailDialog.job.url && !detailDialog.pasteOpen; text: "Read it again"
                            enabled: !detailDialog.scoreBusy; onClicked: detailDialog.readAgain() }
                        SmallButton { objectName: "pasteToggle"; text: detailDialog.pasteOpen ? "Cancel" : "Paste the posting's text"
                            onClicked: { detailDialog.pasteOpen = !detailDialog.pasteOpen; detailDialog.pasteErr = ""; } }
                    }
                    ColumnLayout { visible: detailDialog.pasteOpen && detailDialog.job.can_paste_text === true; Layout.fillWidth: true; spacing: 6
                        Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1; implicitHeight: 130; clip: true
                            border.color: detailDialog.pasteErr !== "" || pastedText.text.length > detailDialog.pasteMax ? theme.crit
                                          : (pastedText.activeFocus ? theme.accent : theme.line)
                            Flickable { anchors.fill: parent; anchors.margins: 8; contentHeight: pastedText.implicitHeight; clip: true
                                TextEdit { id: pastedText; objectName: "pastedText"; width: parent.width; wrapMode: TextEdit.Wrap; selectByMouse: true
                                    color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                                    onTextChanged: if (activeFocus) detailDialog.pasteErr = ""
                                    Text { visible: pastedText.text === ""; width: parent.width; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 12
                                        text: "Open the posting, copy its whole text and paste it here" } } } }
                        RowLayout { Layout.fillWidth: true; spacing: 8
                            Text { objectName: "pasteHint"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                                readonly property bool bad: detailDialog.pasteErr !== "" || pastedText.text.length > detailDialog.pasteMax
                                color: bad ? theme.crit : theme.faint; font.bold: bad
                                text: detailDialog.pasteErr !== "" ? detailDialog.pasteErr
                                    : pastedText.text.length > detailDialog.pasteMax
                                        ? (pastedText.text.length - detailDialog.pasteMax) + " characters too long (the limit is " + detailDialog.pasteMax + ")"
                                    : pastedText.text.trim().length + " characters · at least " + detailDialog.pasteMin + " · then press Score again" }
                            SmallButton { objectName: "pasteSave"; primaryStyle: true; text: "Save text"; onClicked: detailDialog.savePasted() }
                        }
                    }
                    Text { objectName: "holdNote"; visible: !!detailDialog.job.hold; Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: theme.warn; font.pixelSize: 13; font.bold: true; lineHeight: 1.25; text: detailDialog.job.hold || "" }
                    RowLayout { visible: !!detailDialog.job.prefilter; Layout.fillWidth: true; spacing: 10
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                            text: "Not scored, to save a Claude call. " + (detailDialog.job.prefilter || "") }
                        SmallButton { objectName: "scoreAnyway"; text: "Score it anyway"
                            onClicked: { bridge.scoreAnyway(detailDialog.job.id); detailDialog.refresh(); win.refreshOpenView();
                                         ticker.text = "It will be scored on the next Run search."; } } }
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                        visible: !detailDialog.job.prefilter
                        text: detailDialog.job.score_queued ? "You asked for this one to be scored. It is scored on the next Run search."
                            : detailDialog.job.reason ? detailDialog.job.reason
                            : (detailDialog.job.score === undefined || detailDialog.job.score === null)
                                ? (detailDialog.job.is_application ? "This application came from your emails or your letters folder, so it was never scored."
                                                                   : "This job has not been scored yet. It is scored on the next Run search.")
                                : "No explanation was saved with this score." } }

                DetailCard { heading: "Keywords in the posting"
                    Text { visible: !detailDialog.hasWords; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                        text: detailDialog.job.description ? "No known skills or tools were found in this posting."
                                                           : "No description is saved for this job, so keywords cannot be compared." }
                    Text { visible: (detailDialog.job.matched || []).length > 0; text: "In your CV"; color: theme.good; font.pixelSize: 12; font.bold: true }
                    ChipFlow { objectName: "matchedChips"; visible: (detailDialog.job.matched || []).length > 0
                        items: detailDialog.job.matched || []; tone: theme.good; fill: theme.goodbg }
                    Text { visible: (detailDialog.job.missing || []).length > 0; text: "Not in your CV"; color: theme.warn; font.pixelSize: 12; font.bold: true
                        Layout.topMargin: 2 }
                    ChipFlow { objectName: "missingChips"; visible: (detailDialog.job.missing || []).length > 0
                        items: detailDialog.job.missing || []; tone: theme.warn; fill: theme.warnbg }
                    Text { visible: (detailDialog.job.missing || []).length > 0; Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: theme.faint; font.pixelSize: 11
                        text: "Shown for your information only. A keyword that is not in your master CV is never added to an adapted CV." }
                }

                DetailCard { heading: "Same application twice?"; visible: !!(detailDialog.job.duplicate && detailDialog.job.duplicate.id)
                    border.color: theme.steel
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                        text: detailDialog.job.duplicate && detailDialog.job.duplicate.id
                            ? ("This looks like the same application as \"" + detailDialog.job.duplicate.company + " · "
                               + detailDialog.job.duplicate.title + "\" (" + detailDialog.job.duplicate.status + "). "
                               + "Merging keeps one row with both histories, letters and emails.") : "" }
                    RowLayout { Layout.fillWidth: true; spacing: 6
                        Item { Layout.fillWidth: true }
                        SmallButton { text: "They are different"
                            onClicked: { bridge.keepSeparate(detailDialog.job.id, detailDialog.job.duplicate.id);
                                         detailDialog.refresh(); win.countsData = bridge.counts(); win.refreshOpenView(); } }
                        SmallButton { objectName: "mergeButton"; primaryStyle: true; text: "Merge into one"
                            onClicked: { var d = detailDialog.job.duplicate;
                                         var r = bridge.mergeJobs(d.keep, d.drop);
                                         if (r && r.ok) { ticker.text = "Merged into one application.";
                                             win.countsData = bridge.counts(); win.refreshOpenView(); detailDialog.show(d.keep); } } }
                    }
                }

                DetailCard { heading: "Your application"; visible: detailDialog.job.is_application === true
                    RowLayout { Layout.fillWidth: true; spacing: 6
                        Text { text: "Status"; color: theme.soft; font.pixelSize: 12; Layout.preferredWidth: 78 }
                        Repeater {
                            model: [ { s: "waiting", label: "Waiting" }, { s: "interview", label: "Interview" },
                                     { s: "offer", label: "Offer" }, { s: "rejected", label: "Rejected" } ]
                            Rectangle {
                                objectName: "status_" + modelData.s
                                readonly property bool current: detailDialog.job.status === modelData.s
                                implicitHeight: 26; implicitWidth: stT.implicitWidth + 20; radius: 13
                                color: current ? win.badgeBg(modelData.s) : (stMa.containsMouse ? theme.inset : win.clearOf(theme.inset))
                                border.width: 1; border.color: current ? win.badgeColor(modelData.s) : theme.line
                                Behavior on color { ColorAnimation { duration: 140 } }
                                Text { id: stT; anchors.centerIn: parent; text: modelData.label; font.pixelSize: 11; font.bold: true
                                    color: parent.current ? win.badgeColor(modelData.s) : theme.soft }
                                MouseArea { id: stMa; anchors.fill: parent; hoverEnabled: true
                                    cursorShape: parent.current ? Qt.ArrowCursor : Qt.PointingHandCursor
                                    onClicked: if (!parent.current) detailDialog.setStatus(modelData.s) }
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    RowLayout { Layout.fillWidth: true; spacing: 6
                        Text { text: "Applied on"; color: theme.soft; font.pixelSize: 12; Layout.preferredWidth: 78 }
                        TextField { id: dateField; objectName: "dateField"; implicitWidth: 130; implicitHeight: 28
                            placeholderText: "YYYY-MM-DD"; placeholderTextColor: theme.faint
                            color: theme.ink; font.pixelSize: 12; selectByMouse: true
                            inputMethodHints: Qt.ImhDate
                            background: Rectangle { radius: 7; color: theme.inset; border.width: 1
                                border.color: dateField.activeFocus ? theme.accent : (detailDialog.dateErr !== "" ? theme.crit : theme.line) }
                            onTextEdited: detailDialog.dateErr = ""
                            onAccepted: detailDialog.saveDate() }
                        SmallButton { objectName: "dateSave"; text: "Save date"; onClicked: detailDialog.saveDate() }
                        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.faint; font.pixelSize: 11
                            text: detailDialog.job.applied_from_email ? "taken from the first email" : "" }
                    }
                    Text { objectName: "dateErr"; visible: detailDialog.dateErr !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: theme.crit; font.pixelSize: 11; font.bold: true; text: detailDialog.dateErr }
                }

                DetailCard { heading: "A date to remember"; objectName: "eventCard"
                    visible: detailDialog.job.is_application === true
                    border.color: (detailDialog.job.event && detailDialog.job.event.date) ? theme.a2 : theme.line
                    Flow { Layout.fillWidth: true; spacing: 6
                        Repeater { model: ["interview", "deadline", "test task", "call", "other"]
                            Rectangle {
                                readonly property bool on: detailDialog.eventKind === modelData
                                height: 24; radius: 12; width: ekT.implicitWidth + 18
                                color: on ? theme.accent : (ekMa.containsMouse ? theme.inset : "transparent")
                                border.width: 1; border.color: on ? "transparent" : theme.line
                                Text { id: ekT; anchors.centerIn: parent; text: modelData; font.pixelSize: 11; font.bold: parent.on
                                    color: parent.on ? theme.accentInk : theme.soft }
                                MouseArea { id: ekMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onClicked: detailDialog.eventKind = modelData } } } }
                    RowLayout { Layout.fillWidth: true; spacing: 6
                        TextField { id: evDate; objectName: "evDate"; implicitWidth: 118; implicitHeight: 28; placeholderText: "YYYY-MM-DD"
                            placeholderTextColor: theme.faint; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                            background: Rectangle { radius: 7; color: theme.inset; border.width: 1
                                border.color: evDate.activeFocus ? theme.accent : (detailDialog.eventErr !== "" ? theme.crit : theme.line) }
                            onTextEdited: detailDialog.eventErr = "" }
                        TextField { id: evTime; objectName: "evTime"; implicitWidth: 70; implicitHeight: 28; placeholderText: "HH:MM"
                            placeholderTextColor: theme.faint; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                            background: Rectangle { radius: 7; color: theme.inset; border.width: 1
                                border.color: evTime.activeFocus ? theme.accent : theme.line }
                            onTextEdited: detailDialog.eventErr = "" }
                        TextField { id: evNote; objectName: "evNote"; Layout.fillWidth: true; implicitHeight: 28; placeholderText: "note, e.g. Teams call with the team lead"
                            placeholderTextColor: theme.faint; color: theme.ink; font.pixelSize: 12; selectByMouse: true; maximumLength: 200
                            background: Rectangle { radius: 7; color: theme.inset; border.width: 1
                                border.color: evNote.activeFocus ? theme.accent : theme.line }
                            onTextEdited: detailDialog.eventErr = detailDialog.full(evNote, "The note") }
                        SmallButton { objectName: "evSave"; primaryStyle: true; text: "Save"; onClicked: detailDialog.saveEvent() }
                        SmallButton { objectName: "evCalendar"; visible: !!(detailDialog.job.event && detailDialog.job.event.date)
                            text: "Add to calendar"
                            onClicked: { var c = bridge.exportEvent(detailDialog.job.id);
                                if (c && c.ok) ticker.text = "Opened a calendar file. Confirm it in Calendar and it syncs to your phone.";
                                else detailDialog.eventErr = (c && c.msg) || "Couldn't make the calendar file."; } }
                        SmallButton { visible: !!(detailDialog.job.event && detailDialog.job.event.date); text: "Clear"
                            onClicked: { bridge.clearEvent(detailDialog.job.id); detailDialog.refresh("event"); win.upcomingData = bridge.upcoming(); } }
                    }
                    Text { objectName: "eventErr"; visible: detailDialog.eventErr !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: theme.crit; font.pixelSize: 11; font.bold: true; text: detailDialog.eventErr }
                    Text { visible: detailDialog.eventErr === ""; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                        text: "Shown on the main screen. A notification comes the day before and on the day; with a time, also about three hours and one hour before." }
                }

                DetailCard { heading: "After the " + ((detailDialog.job.event && detailDialog.job.event.kind) || "interview"); objectName: "thanksCard"
                    visible: detailDialog.job.thanks_due === true
                    border.color: theme.a2
                    RowLayout { Layout.fillWidth: true; spacing: 10
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 13; color: theme.ink
                            text: "A short thank-you note the same or the next day is a good habit. Here is a draft to adjust and send yourself." }
                        SmallButton { objectName: "thanksToggle"; text: detailDialog.thanks.body ? "Hide draft" : "Draft thank-you"
                            onClicked: { detailDialog.thanksNote = "";
                                detailDialog.thanks = detailDialog.thanks.body ? ({}) : bridge.thanksDraft(detailDialog.job.id); } }
                    }
                    ColumnLayout { visible: !!detailDialog.thanks.body; Layout.fillWidth: true; spacing: 6
                        TextEdit { Layout.fillWidth: true; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                            text: "Subject: " + (detailDialog.thanks.subject || ""); color: theme.ink; font.pixelSize: 12; font.bold: true
                            selectionColor: theme.accent }
                        Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.color: theme.line; border.width: 1
                            implicitHeight: thanksBody.implicitHeight + 20
                            TextEdit { id: thanksBody; objectName: "thanksBody"; x: 10; y: 10; width: parent.width - 20
                                readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                                text: detailDialog.thanks.body || ""; color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent } }
                        RowLayout { Layout.fillWidth: true; spacing: 6
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                                color: detailDialog.thanksNote !== "" ? theme.good : theme.faint
                                text: detailDialog.thanksNote !== "" ? detailDialog.thanksNote
                                    : "The app never sends email. Add one thing you really talked about before you send it." }
                            SmallButton { text: "Copy"
                                onClicked: { bridge.copyText((detailDialog.thanks.subject || "") + "\n\n" + (detailDialog.thanks.body || ""));
                                             detailDialog.thanksNote = "Copied. Paste it into your mail app."; } }
                            SmallButton { objectName: "thanksDone"; primaryStyle: true; text: "Mark as sent"
                                onClicked: { if (bridge.markThanked(detailDialog.job.id)) {
                                                 detailDialog.refresh(); ticker.text = "Thank-you noted."; } } }
                        }
                    }
                }

                DetailCard { heading: "A reply that is not in your mailbox"; objectName: "replyCard"
                    visible: detailDialog.job.is_application === true
                    RowLayout { Layout.fillWidth: true; spacing: 10
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 13
                            color: detailDialog.replyErr !== "" ? theme.crit : (detailDialog.replyInfo !== "" ? theme.good : theme.ink)
                            text: detailDialog.replyBusy ? "Reading the message…"
                                : detailDialog.replyErr !== "" ? detailDialog.replyErr
                                : detailDialog.replyInfo !== "" ? detailDialog.replyInfo
                                : "Got an answer on LinkedIn or in a company portal? Paste it here and it is filed like an email." }
                        SmallButton { objectName: "replyToggle"; visible: !detailDialog.replyBusy
                            text: detailDialog.replyOpen ? "Cancel" : "Paste a reply"
                            onClicked: { detailDialog.replyOpen = !detailDialog.replyOpen; detailDialog.replyErr = ""; } }
                    }
                    ColumnLayout { visible: detailDialog.replyOpen; Layout.fillWidth: true; spacing: 6
                        Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1
                            border.color: replyText.text.length > detailDialog.replyMax ? theme.crit : (replyText.activeFocus ? theme.accent : theme.line)
                            implicitHeight: 110; clip: true
                            Flickable { anchors.fill: parent; anchors.margins: 8; contentHeight: replyText.implicitHeight; clip: true
                                TextEdit { id: replyText; objectName: "replyText"; width: parent.width; wrapMode: TextEdit.Wrap; selectByMouse: true
                                    color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                                    Text { visible: replyText.text === ""; text: "Paste the message text here"; color: theme.faint; font.pixelSize: 12 } } } }
                        RowLayout { Layout.fillWidth: true
                            Text { objectName: "replyHint"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                                color: replyText.text.length > detailDialog.replyMax ? theme.crit : theme.faint
                                font.bold: replyText.text.length > detailDialog.replyMax
                                text: replyText.text.length > detailDialog.replyMax
                                      ? (replyText.text.length - detailDialog.replyMax) + " characters too long: paste only the message itself (up to " + detailDialog.replyMax + ")"
                                      : "Claude reads it (one call). If the limit is used up, the app's own rules decide." }
                            SmallButton { objectName: "replyFile"; primaryStyle: true; enabled: !detailDialog.replyBusy
                                text: detailDialog.replyBusy ? "Reading…" : "File it"; onClicked: detailDialog.fileReply() } }
                    }
                }

                DetailCard { heading: "Notes about " + (detailDialog.job.company || "this company")
                    objectName: "notesCard"
                    // for a job you have not applied to, only when you already keep notes on that company
                    visible: !!detailDialog.job.company && detailDialog.job.company !== "unknown"
                             && (detailDialog.job.is_application === true
                                 || !!(detailDialog.job.company_notes && detailDialog.job.company_notes.updated))
                    GridLayout { Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 6
                        Text { text: "Who you spoke to"; color: theme.soft; font.pixelSize: 12 }
                        TextField { id: cnContact; objectName: "cnContact"; Layout.fillWidth: true; implicitHeight: 28; color: theme.ink; font.pixelSize: 12
                            selectByMouse: true; maximumLength: 200; placeholderText: "name, role"; placeholderTextColor: theme.faint
                            background: Rectangle { radius: 7; color: theme.inset; border.width: 1; border.color: cnContact.activeFocus ? theme.accent : theme.line }
                            onTextEdited: { detailDialog.notesInfo = detailDialog.full(cnContact, "“Who you spoke to”"); detailDialog.notesBad = detailDialog.notesInfo !== ""; } }
                        Text { text: "Salary mentioned"; color: theme.soft; font.pixelSize: 12 }
                        TextField { id: cnSalary; objectName: "cnSalary"; Layout.fillWidth: true; implicitHeight: 28; color: theme.ink; font.pixelSize: 12
                            selectByMouse: true; maximumLength: 200; placeholderText: "what they said, what you said"; placeholderTextColor: theme.faint
                            background: Rectangle { radius: 7; color: theme.inset; border.width: 1; border.color: cnSalary.activeFocus ? theme.accent : theme.line }
                            onTextEdited: { detailDialog.notesInfo = detailDialog.full(cnSalary, "“Salary mentioned”"); detailDialog.notesBad = detailDialog.notesInfo !== ""; } }
                        Text { text: "What they asked"; color: theme.soft; font.pixelSize: 12 }
                        TextField { id: cnAsked; objectName: "cnAsked"; Layout.fillWidth: true; implicitHeight: 28; color: theme.ink; font.pixelSize: 12
                            selectByMouse: true; maximumLength: 400; placeholderText: "questions, tasks"; placeholderTextColor: theme.faint
                            background: Rectangle { radius: 7; color: theme.inset; border.width: 1; border.color: cnAsked.activeFocus ? theme.accent : theme.line }
                            onTextEdited: { detailDialog.notesInfo = detailDialog.full(cnAsked, "“What they asked”"); detailDialog.notesBad = detailDialog.notesInfo !== ""; } }
                    }
                    Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1
                        border.color: cnNotes.text.length > detailDialog.notesMax ? theme.crit : (cnNotes.activeFocus ? theme.accent : theme.line)
                        implicitHeight: Math.max(54, cnNotes.implicitHeight + 16)
                        TextEdit { id: cnNotes; objectName: "cnNotes"; x: 8; y: 8; width: parent.width - 16; wrapMode: TextEdit.Wrap; selectByMouse: true
                            color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                            onTextChanged: if (activeFocus) { detailDialog.notesInfo = ""; detailDialog.notesBad = false; }
                            Text { visible: cnNotes.text === ""; text: "Anything else worth remembering"; color: theme.faint; font.pixelSize: 12 } } }
                    Text { objectName: "notesOver"; visible: cnNotes.text.length > detailDialog.notesMax; Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: theme.crit; font.pixelSize: 11; font.bold: true
                        text: (cnNotes.text.length - detailDialog.notesMax) + " characters too long (the limit is " + detailDialog.notesMax + ")" }
                    RowLayout { Layout.fillWidth: true; spacing: 6
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                            objectName: "notesLine"; font.bold: detailDialog.notesBad
                            color: detailDialog.notesInfo === "" ? theme.faint : (detailDialog.notesBad ? theme.crit : theme.good)
                            text: detailDialog.notesInfo !== "" ? detailDialog.notesInfo
                                : "Kept for the company, so they show again on every job there"
                                  + ((detailDialog.job.company_notes && detailDialog.job.company_notes.updated) ? " · last changed " + detailDialog.job.company_notes.updated : "") + "." }
                        SmallButton { objectName: "notesSave"; text: "Save notes"; onClicked: detailDialog.saveNotes() }
                    }
                }

                DetailCard { heading: "Interview preparation"; visible: detailDialog.job.is_application === true
                    border.color: detailDialog.job.status === "interview" ? theme.good : theme.line
                    RowLayout { Layout.fillWidth: true; spacing: 10
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                            text: detailDialog.prepBusy ? "Preparing questions and answers from your CV… this takes about a minute."
                                : detailDialog.prepErr !== "" ? detailDialog.prepErr
                                : detailDialog.job.has_prep ? ("Questions and answers are ready (made " + detailDialog.job.prep_made + ").")
                                : detailDialog.job.status === "interview" ? "You have an interview here. Get likely questions with answers built from your CV."
                                : "Likely questions for this role, with answers built from your CV." 
                            Binding on color { when: detailDialog.prepErr !== "" && !detailDialog.prepBusy; value: theme.crit } }
                        SmallButton { visible: detailDialog.job.has_prep === true && !detailDialog.prepBusy; text: "Open"
                            primaryStyle: true; objectName: "prepOpen"; onClicked: prepDialog.show(detailDialog.job.id) }
                        SmallButton { objectName: "prepDocument"; visible: detailDialog.job.has_prep === true && !detailDialog.prepBusy
                            text: "Document"
                            onClicked: { var r = bridge.prepDocument(detailDialog.job.id, false);
                                         ticker.text = (r && r.ok) ? "Opened " + r.file + "." : ((r && r.msg) || "Couldn't write the document."); } }
                        SmallButton { objectName: "prepMake"; enabled: !detailDialog.prepBusy
                            text: detailDialog.prepBusy ? "Preparing…" : (detailDialog.job.has_prep ? "Make again" : "Prepare")
                            onClicked: {
                                // making it again replaces what you changed by hand: say so first, never on one click
                                if (detailDialog.job.prep_edited === true && !detailDialog.confirmRemake) {
                                    detailDialog.confirmRemake = true;
                                    detailDialog.prepErr = "Making it again replaces the changes you made in the sheet. Press Make again once more to go on.";
                                    return;
                                }
                                detailDialog.confirmRemake = false;
                                detailDialog.prepErr = ""; detailDialog.prepBusy = true; detailDialog.prepJob = detailDialog.job.id;
                                bridge.prepareInterview(detailDialog.job.id); } }
                    }
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                        text: "Asks Claude once or twice (uses your limit). You get a sheet to read before the call: the company, the role, your fit, the honest gap, an opening pitch and likely questions with answers. Only what your CV shows is claimed." }
                }

                DetailCard { heading: "Follow-up"; visible: detailDialog.job.status === "waiting"
                    border.color: detailDialog.fu.due ? theme.warn : theme.line
                    RowLayout { Layout.fillWidth: true; spacing: 10
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 13
                            color: detailDialog.fu.due ? theme.warn : theme.ink
                            text: !detailDialog.fu.since ? "The app does not know when you applied, so it will not remind you about this one."
                                : detailDialog.fu.stale ? ("Silent for " + win.daysText(detailDialog.fu.days_waiting) + ". This one has most likely gone quiet; no reminder.")
                                : detailDialog.fu.due ? ((detailDialog.fu.had_reply ? "Only a confirmation so far, no decision for " : "No reply for ")
                                                         + win.daysText(detailDialog.fu.days_waiting) + ". A short follow-up is reasonable now.")
                                : (detailDialog.fu.days_waiting === 0 ? "Last activity today"
                                   : "Last activity " + win.daysText(detailDialog.fu.days_waiting) + " ago")
                                  + (
                                     detailDialog.fu.followed_up ? " (you followed up on " + detailDialog.fu.followed_up + ")." : ".") }
                        SmallButton { text: detailDialog.draft.body ? "Hide draft" : "Draft follow-up"
                            onClicked: { detailDialog.note = "";
                                detailDialog.draft = detailDialog.draft.body ? ({}) : bridge.followupDraft(detailDialog.job.id); } }
                    }
                    ColumnLayout { visible: !!detailDialog.draft.body; Layout.fillWidth: true; spacing: 6
                        TextEdit { Layout.fillWidth: true; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                            text: "Subject: " + (detailDialog.draft.subject || ""); color: theme.ink; font.pixelSize: 12; font.bold: true
                            selectionColor: theme.accent }
                        Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.color: theme.line; border.width: 1
                            implicitHeight: draftBody.implicitHeight + 20
                            TextEdit { id: draftBody; objectName: "draftBody"; x: 10; y: 10; width: parent.width - 20
                                readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                                text: detailDialog.draft.body || ""; color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent } }
                        RowLayout { Layout.fillWidth: true; spacing: 6
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                                color: detailDialog.note !== "" ? theme.good : theme.faint
                                text: detailDialog.note !== "" ? detailDialog.note
                                    : "The app never sends email. Copy the text and send it from your own mail." }
                            SmallButton { text: "Copy"
                                onClicked: { bridge.copyText((detailDialog.draft.subject || "") + "\n\n" + (detailDialog.draft.body || ""));
                                             detailDialog.note = "Copied. Paste it into your mail app."; } }
                            SmallButton { primaryStyle: true; text: "Mark as followed up"
                                onClicked: { if (bridge.markFollowedUp(detailDialog.job.id)) {
                                                 detailDialog.draft = ({}); detailDialog.refresh(); win.countsData = bridge.counts();
                                                 ticker.text = "Follow-up noted. The reminder starts counting again."; } } }
                        }
                    }
                }

                DetailCard { heading: "Notes"; visible: !!detailDialog.job.notes || !!detailDialog.job.next_step
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 12; lineHeight: 1.25
                        text: (detailDialog.job.next_step ? "Next step: " + detailDialog.job.next_step + "\n" : "") + (detailDialog.job.notes || "") } }

                DetailCard { heading: "Description"; visible: !!detailDialog.job.description
                    // laid out for reading: headings on their own lines, list items marked (no word is changed)
                    TextEdit { objectName: "descText"; Layout.fillWidth: true; Layout.maximumWidth: 660; readOnly: true; selectByMouse: true
                        wrapMode: TextEdit.Wrap; text: detailDialog.job.description_text || detailDialog.job.description || ""
                        color: theme.ink; font.pixelSize: 13; selectionColor: theme.accent
                        textFormat: TextEdit.PlainText } }
            }
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        Text { objectName: "closeNote"; visible: detailDialog.closeNote !== ""; text: detailDialog.closeNote
            Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.topMargin: 10
            wrapMode: Text.Wrap; color: theme.crit; font.pixelSize: 12; font.bold: true }
        RowLayout { objectName: "detailFooter"; Layout.fillWidth: true; Layout.margins: 12; spacing: 6
            Flow { objectName: "detailDocs"; Layout.fillWidth: true; Layout.minimumWidth: 120; spacing: 6
            SmallButton { visible: !!detailDialog.job.url; text: "Open posting ↗"
                onClicked: { var r = bridge.openUrl(detailDialog.job.id);
                             ticker.text = (r && r.ok) ? "Opened the job posting in your browser." : "No link for this job."; } }
            SmallButton { visible: !!detailDialog.job.cv; text: "CV"; onClicked: bridge.openDoc("cv", detailDialog.job.cv) }
            SmallButton { visible: detailDialog.job.cv_pdf === true; text: "CV PDF"; onClicked: bridge.openDoc("cv_pdf", detailDialog.job.cv) }
            SmallButton { visible: !!detailDialog.job.letter; text: "Letter"; onClicked: bridge.openDoc("letter", detailDialog.job.letter) }
            SmallButton { visible: detailDialog.job.letter_pdf === true; text: "Letter PDF"; onClicked: bridge.openDoc("letter_pdf", detailDialog.job.letter) }
            SmallButton { objectName: "showCv"; visible: !!detailDialog.job.cv && detailDialog.job.is_lead !== true; text: "CV in folder"; onClicked: detailDialog.showFile("cv") }
            SmallButton { objectName: "showLetter"; visible: !!detailDialog.job.letter && detailDialog.job.is_lead !== true; text: "Letter in folder"; onClicked: detailDialog.showFile("letter") }
            SmallButton { objectName: "onePdf"; visible: detailDialog.job.can_combine === true; text: "One PDF"
                onClicked: detailDialog.onePdf() }
            SmallButton { objectName: "compareCv"; visible: detailDialog.job.can_compare === true; text: "Compare CV"
                onClicked: compareDialog.show(detailDialog.job.id) }
            SmallButton { objectName: "editLetter"; visible: detailDialog.job.letter_editable === true; text: "Edit letter"
                onClicked: letterDialog.show(detailDialog.job.id) }
            }
            SmallButton { objectName: "answersOpen"; visible: detailDialog.job.is_dismissed !== true
                text: "Form answers"; onClicked: formDialog.show(detailDialog.job.id) }
            SmallButton { objectName: "assistantOpen"; visible: detailDialog.job.is_dismissed !== true
                text: "Fill the form"; onClicked: assistantDialog.forJob(detailDialog.job.id) }
            SmallButton { objectName: "notInterested"; visible: detailDialog.job.is_lead === true; text: "Not interested"
                onClicked: detailDialog.notInterested() }
            SmallButton { visible: detailDialog.job.is_dismissed === true; primaryStyle: true; text: "Restore to New Jobs"
                onClicked: { bridge.restoreJob(detailDialog.job.id); detailDialog.refresh();
                             win.countsData = bridge.counts(); win.refreshOpenView(); ticker.text = "Back in New Jobs."; } }
            PillButton { objectName: "applyBottom"; visible: detailDialog.job.is_lead === true; primaryStyle: true; text: "Mark applied"
                onClicked: detailDialog.markApplied() }
        }
    }
}
