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
    modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
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
    property bool scoreBusy: false
    property string scoreJob: ""
    property string scoreNote: ""
    property bool scoreBad: false
    function scoreAgain() {
        scoreNote = ""; scoreBad = false; scoreBusy = true; scoreJob = job.id;
        bridge.rescoreJob(job.id);
    }
    Connections { target: bridge
        function onRescoreReady(res) {
            if (res.job_id !== detailDialog.scoreJob) return;
            detailDialog.scoreBusy = false;
            var here = res.job_id === detailDialog.job.id;
            var text = res.ok ? (res.before === res.score ? "Scored again: still " + res.score + "."
                                                          : "Scored again: " + res.before + " before, " + res.score + " now.")
                              : ("Not scored again: " + (res.msg || "unknown reason"));
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
        if (r && r.ok) { refresh(); win.upcomingData = bridge.upcoming(); ticker.text = "Date saved. You will be reminded the day before."; }
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
        if (r && r.ok) refresh();
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
        if (r && r.ok) { refresh(); win.countsData = bridge.counts(); win.refreshOpenView(); ticker.text = "Apply date saved."; }
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
        job = d; draft = ({}); note = ""; dateErr = ""; if (!prepBusy) prepErr = "";
        eventErr = ""; notesInfo = ""; notesBad = false; replyErr = ""; replyInfo = ""; replyOpen = false; thanks = ({}); thanksNote = "";
        detailFlick.contentY = 0;
        open();
    }
    function refresh() { var d = bridge.jobDetail(job.id); if (d && d.id) job = d; }
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
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
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight }
                Text { color: theme.soft; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight
                    text: (detailDialog.job.company || "") + (detailDialog.job.location ? "  ·  " + detailDialog.job.location : "") } }
            Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                Layout.alignment: Qt.AlignTop
                Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: detailDialog.close() } }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }

        Flickable {
            id: detailFlick
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentHeight: detailCol.implicitHeight + 28
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            ColumnLayout {
                id: detailCol
                x: 16; y: 14; width: detailFlick.width - 32; spacing: 12

                ChipFlow {
                    items: [ detailDialog.job.status ? ("" + detailDialog.job.status).replace("_", " ") : "",
                             detailDialog.job.tier ? detailDialog.job.tier + " match" : "",
                             detailDialog.job.posted ? "posted " + detailDialog.job.posted : "",
                             detailDialog.job.applied ? (detailDialog.job.applied_from_email ? "first email " : "applied ") + detailDialog.job.applied : "",
                             detailDialog.job.source || "",
                             detailDialog.job.desired ? Number(detailDialog.job.desired).toLocaleString() + " CZK/mo target" : "",
                             (detailDialog.job.pay && detailDialog.job.pay.low)
                                ? ("posting says " + (detailDialog.job.pay.low === detailDialog.job.pay.high
                                      ? Math.round(detailDialog.job.pay.low / 1000) + "k"
                                      : Math.round(detailDialog.job.pay.low / 1000) + "–" + Math.round(detailDialog.job.pay.high / 1000) + "k") + " CZK/mo") : "",
                             detailDialog.job.letter_old_format === true ? "letter: older format, open in Word" : ""
                           ].filter(function (t) { return t !== ""; })
                }

                // everything needed to apply, in order; ticks are kept with the job
                DetailCard { heading: "Before you apply"; objectName: "applyCard"
                    visible: detailDialog.job.is_lead === true && (!!detailDialog.job.cv || !!detailDialog.job.letter)
                    border.color: theme.accent
                    Repeater {
                        model: detailDialog.applySteps
                        RowLayout { Layout.fillWidth: true; spacing: 10
                            readonly property bool ticked: (detailDialog.job.apply_steps || []).indexOf(modelData.key) >= 0
                            Rectangle { implicitWidth: 20; implicitHeight: 20; radius: 10
                                color: parent.ticked ? theme.good : "transparent"; border.width: 1; border.color: parent.ticked ? theme.good : theme.line
                                Text { anchors.centerIn: parent; text: parent.parent.ticked ? "✓" : ""; color: "#ffffff"; font.pixelSize: 12; font.bold: true } }
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
                            onClicked: { bridge.applyJob(detailDialog.job.id); ticker.text = "Moved to Applications (waiting).";
                                         detailDialog.close(); tableDialog.close(); win.reloadAll(); } }
                    }
                }

                DetailCard { heading: "Why this score"
                    RowLayout { visible: detailDialog.job.can_rescore === true; Layout.fillWidth: true; spacing: 10
                        Text { objectName: "scoreNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 12
                            font.bold: detailDialog.scoreBad
                            color: detailDialog.scoreNote === "" ? theme.faint : (detailDialog.scoreBad ? theme.crit : theme.good)
                            text: detailDialog.scoreBusy ? "Asking Claude…"
                                : detailDialog.scoreNote !== "" ? detailDialog.scoreNote
                                : (detailDialog.job.score_before !== null && detailDialog.job.score_before !== undefined)
                                    ? "It was " + detailDialog.job.score_before + " before it was scored again."
                                    : "Scored with the rules of that day. Score again to apply your current Options (one Claude call)." }
                        SmallButton { objectName: "scoreAgain"; enabled: !detailDialog.scoreBusy && !win.appRunning
                            text: detailDialog.scoreBusy ? "Scoring…" : "Score again"; onClicked: detailDialog.scoreAgain() }
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
                        text: detailDialog.job.description ? "No known technologies were found in this posting."
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
                        Text { Layout.fillWidth: true; elide: Text.ElideRight; color: theme.faint; font.pixelSize: 11
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
                                    color: parent.on ? "#ffffff" : theme.soft }
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
                            onClicked: { bridge.clearEvent(detailDialog.job.id); detailDialog.refresh(); win.upcomingData = bridge.upcoming(); } }
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
                    Text { objectName: "notesOver"; visible: cnNotes.text.length > detailDialog.notesMax; Layout.fillWidth: true
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
            SmallButton { objectName: "notInterested"; visible: detailDialog.job.is_lead === true; text: "Not interested"
                onClicked: { var r = bridge.dismissJob(detailDialog.job.id);
                             if (r && r.ok) { ticker.text = "Removed. It will not come back in later searches (see the “not interested” filter to undo).";
                                 detailDialog.close(); win.countsData = bridge.counts(); win.refreshOpenView(); }
                             else ticker.text = (r && r.msg) ? r.msg : "Couldn't remove that job."; } }
            SmallButton { visible: detailDialog.job.is_dismissed === true; primaryStyle: true; text: "Restore to New Jobs"
                onClicked: { bridge.restoreJob(detailDialog.job.id); detailDialog.refresh();
                             win.countsData = bridge.counts(); win.refreshOpenView(); ticker.text = "Back in New Jobs."; } }
            PillButton { visible: detailDialog.job.is_lead === true; primaryStyle: true; text: "Mark applied"
                onClicked: { bridge.applyJob(detailDialog.job.id); ticker.text = "Moved to Applications (waiting).";
                             detailDialog.close(); tableDialog.close(); win.reloadAll(); } }
        }
    }
}
