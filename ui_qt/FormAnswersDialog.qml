// FormAnswersDialog: answers for one job's application form, created once in Main.qml as `formDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: formDialog; objectName: "formDialog"
    modal: true; anchors.centerIn: parent
    readonly property bool holdsWork: dirty || busy        // unsaved changes, or Claude still drafting
    closePolicy: holdsWork ? Popup.NoAutoClose : Popup.CloseOnEscape      // Esc must not throw away edits ...
    Shortcut { sequence: "Escape"; enabled: formDialog.holdsWork && win.onTop(formDialog)   // ... nor do nothing
               onActivated: formDialog.tryClose() }
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(740, win.width - 60); height: Math.min(760, win.height - 50)
    padding: 0
    property string jobId: ""
    property var info: ({})               // company, title, the common questions
    property bool busy: false             // Claude is drafting
    property bool dirty: false            // an answer was edited and not saved
    property string err: ""
    property string note: ""
    property var checked: ({ count: 0, problem: "", note: "" })     // what the pasted text holds, judged as you type
    readonly property int maxAnswer: win.limits.answer
    function tooLong() {            // the first answer over the limit, to say it before anything is sent
        for (var i = 0; i < fmModel.count; i++) if (fmModel.get(i).answer.length > maxAnswer) return fmModel.get(i).question;
        return "";
    }
    property bool confirmDraft: false     // "Draft again" was pressed once and would replace answers
    property bool confirmClose: false     // Close was pressed once with unsaved edits
    function recheck() { checked = bridge.checkQuestions(fmQuestions.text); confirmDraft = false; }
    function tryClose() {
        if (busy) { err = "Claude is still drafting. Wait for the answers, then close."; return; }
        if (dirty && !confirmClose) {
            confirmClose = true; note = "";
            err = "You changed an answer and did not save it. Press Save, or Close once more to discard the change.";
            return;
        }
        dirty = false; close();
    }
    ListModel { id: fmModel }
    function fill(d) {
        info = d || {};
        fmModel.clear();
        var items = info.items || [];
        for (var i = 0; i < items.length; i++) fmModel.append({ question: items[i].question, answer: items[i].answer, check: items[i].check || "" });
        dirty = false;
    }
    function show(job) {
        var d = bridge.formAnswers(job);
        if (!d || !d.id) { ticker.text = "That job is not in the list any more."; return; }
        jobId = job; err = ""; note = ""; busy = false; confirmClose = false;
        fill(d);
        fmQuestions.text = (d.items || []).map(function (i) { return i.question; }).join("\n");
        recheck();
        fmFlick.contentY = 0; open();
    }
    function all() {
        var out = [];
        for (var i = 0; i < fmModel.count; i++) { var r = fmModel.get(i); out.push({ question: r.question, answer: r.answer, check: r.check }); }
        return out;
    }
    function draft() {
        err = ""; note = ""; confirmClose = false;
        checked = bridge.checkQuestions(fmQuestions.text);
        if (checked.problem !== "") {               // said once, in red, right under the box (and below only when the box is empty)
            if (fmQuestions.text.trim() === "") err = checked.problem;
            confirmDraft = false; return;
        }
        if (fmModel.count > 0 && !confirmDraft) {       // never replace answers (and edits) without saying so
            confirmDraft = true;
            err = "Drafting again replaces the " + fmModel.count + (fmModel.count === 1 ? " answer" : " answers") + " below"
                  + (dirty ? ", including the changes you have not saved" : "") + ". Press Draft again once more to go on.";
            return;
        }
        confirmDraft = false; busy = true;
        bridge.draftAnswers(jobId, fmQuestions.text);
    }
    function save() {
        err = ""; note = ""; confirmClose = false; confirmDraft = false;
        var long = tooLong();
        if (long !== "") { err = "The answer to “" + long.substring(0, 60) + "” is longer than " + maxAnswer + " characters. Shorten it, then save."; return; }
        var empty = 0, open = 0;
        for (var i = 0; i < fmModel.count; i++) {
            var a = fmModel.get(i).answer;
            if (a.trim() === "") empty++; else if (/\[[^\]]+\]/.test(a)) open++;
        }
        var r = bridge.saveFormAnswers(jobId, all());
        if (!(r && r.ok)) { err = (r && r.msg) ? r.msg : "The answers could not be saved. The job may have been removed from the list."; return; }
        dirty = false; detailDialog.refresh();
        note = "Saved with this job." + (empty > 0 ? " " + empty + (empty === 1 ? " answer is" : " answers are") + " still empty." : "")
               + (open > 0 ? " " + open + (open === 1 ? " answer still has" : " answers still have") + " a part in [square brackets] to fill in." : "");
    }
    function copy(i) {
        var text = fmModel.get(i).answer;
        note = ""; confirmClose = false; confirmDraft = false;
        if (text.trim() === "") { err = "That answer is still empty. Write it first, then copy."; return; }
        if (/\[[^\]]+\]/.test(text)) { err = "This answer still has a part in [square brackets]. Replace it with your own words, then copy."; return; }
        err = "";
        bridge.copyText(text);
        note = fmModel.get(i).check !== "" ? "Copied. Check it first: " + fmModel.get(i).check : "Copied.";
        bridge.applyStep(jobId, "answers"); detailDialog.refresh();
    }
    Connections { target: bridge
        function onAnswersReady(res) {
            if (res.job_id !== formDialog.jobId) return;
            formDialog.busy = false;
            if (res.ok) {
                formDialog.fill(bridge.formAnswers(formDialog.jobId));
                formDialog.note = "Drafted " + res.count + (res.count === 1 ? " answer" : " answers")
                                  + (res.to_check > 0 ? ". " + res.to_check + " need your attention (marked below)." : ". Read them before you copy.");
                bridge.applyStep(formDialog.jobId, "answers"); detailDialog.refresh();
            } else formDialog.err = res.msg || "The answers could not be drafted.";
        } }
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
        FocusCatcher {} }
    contentItem: ColumnLayout {
        spacing: 0
        DialogHeader {
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                DialogTitle { text: "Answers for this form" }
                Text { objectName: "formFor"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                    text: (formDialog.info.company || "") + "  ·  " + (formDialog.info.title || "") } }
            CloseButton { Layout.alignment: Qt.AlignTop; onClicked: formDialog.tryClose() }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        Flickable {
            id: fmFlick
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentHeight: fmCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            FocusCatcher {}                // a press on empty space in the scroll area
            ColumnLayout {
                id: fmCol
                x: 16; y: 14; width: fmFlick.width - 32; spacing: 12
                DetailCard { heading: "The form's questions"
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                        text: "Every form asks something different. Paste this form's questions here, one per line." }
                    Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1
                        border.color: (formDialog.err !== "" && fmQuestions.text.trim() === "") || (fmQuestions.text.trim() !== "" && formDialog.checked.problem !== "")
                              ? theme.crit : (fmQuestions.activeFocus ? theme.accent : theme.line)
                        implicitHeight: Math.max(96, fmQuestions.implicitHeight + 16)
                        TextEdit { id: fmQuestions; objectName: "fmQuestions"; x: 8; y: 8; width: parent.width - 16
                            wrapMode: TextEdit.Wrap; selectByMouse: true; color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                            readOnly: formDialog.busy
                            onTextChanged: { formDialog.recheck(); if (activeFocus) { formDialog.err = ""; formDialog.note = ""; } }
                            Text { visible: fmQuestions.text === ""; color: theme.faint; font.pixelSize: 12
                                text: "What are your salary expectations?\nWhy do you want to work with us?" } } }
                    RowLayout { Layout.fillWidth: true; spacing: 6
                        Text { objectName: "fmHint"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                            // what the text holds, as you type: a problem in red, otherwise the count
                            color: fmQuestions.text.trim() !== "" && formDialog.checked.problem !== "" ? theme.crit : theme.faint
                            font.bold: fmQuestions.text.trim() !== "" && formDialog.checked.problem !== ""
                            text: fmQuestions.text.trim() === "" ? "Claude drafts the answers in one call, from your CV, this posting and About you. Nothing outside your CV is claimed."
                                : formDialog.checked.problem !== "" ? formDialog.checked.problem
                                : formDialog.checked.count + (formDialog.checked.count === 1 ? " question" : " questions") + " found"
                                  + (formDialog.checked.note !== "" ? " · " + formDialog.checked.note : "") + " · one Claude call" }
                        SmallButton { objectName: "fmCommon"; enabled: !formDialog.busy; text: "Common questions"
                            onClicked: {
                                formDialog.note = "";
                                if (fmQuestions.text.trim() !== "" && fmQuestions.text.trim() !== (formDialog.info.common || []).join("\n")) {
                                    // do not throw away what was pasted: add the common ones below it
                                    fmQuestions.text = fmQuestions.text.replace(/\s+$/, "") + "\n" + (formDialog.info.common || []).join("\n");
                                    formDialog.note = "Added below what you pasted.";
                                } else fmQuestions.text = (formDialog.info.common || []).join("\n");
                                formDialog.err = ""; } }
                        SmallButton { objectName: "fmDraft"; primaryStyle: true; enabled: !formDialog.busy
                            text: formDialog.busy ? "Asking Claude…" : (fmModel.count > 0 ? "Draft again" : "Draft answers")
                            onClicked: formDialog.draft() }
                    }
                }
                Repeater {
                    model: fmModel
                    Rectangle { Layout.fillWidth: true; radius: 12; color: theme.surface2; border.width: 1
                        border.color: model.check !== "" ? theme.warn : theme.line
                        implicitHeight: fmItem.implicitHeight + 24
                        ColumnLayout { id: fmItem; x: 12; y: 12; width: parent.width - 24; spacing: 6
                            RowLayout { Layout.fillWidth: true; spacing: 8
                                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; font.bold: true
                                    text: model.question }
                                SmallButton { text: "Copy"; onClicked: formDialog.copy(index) }
                            }
                            Text { visible: model.check !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                                color: theme.warn; font.pixelSize: 11; font.bold: true; text: "Check: " + model.check }
                            Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1
                                border.color: fmAns.text.length > formDialog.maxAnswer ? theme.crit : (fmAns.activeFocus ? theme.accent : theme.line)
                                implicitHeight: Math.max(52, fmAns.implicitHeight + 16)
                                TextEdit { id: fmAns; x: 8; y: 8; width: parent.width - 16; wrapMode: TextEdit.Wrap; selectByMouse: true
                                    color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                                    Component.onCompleted: text = model.answer
                                    onTextChanged: if (activeFocus) { fmModel.setProperty(index, "answer", text); formDialog.dirty = true
                                                                      formDialog.note = ""; formDialog.err = ""; formDialog.confirmClose = false; }
                                    Text { visible: fmAns.text === ""; text: "Write this answer yourself"; color: theme.faint; font.pixelSize: 12 } } }
                            Text { visible: fmAns.text.length > formDialog.maxAnswer; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11; font.bold: true
                                text: (fmAns.text.length - formDialog.maxAnswer) + " characters too long (the limit is " + formDialog.maxAnswer + ")" }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        DialogFooter {
            // always in view, wherever the list is scrolled: what went wrong (red) or what was done (green)
            Text { objectName: "fmNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap
                font.pixelSize: formDialog.err !== "" ? 12 : 11; font.bold: formDialog.err !== ""
                color: formDialog.err !== "" ? theme.crit : (formDialog.note !== "" ? theme.good : theme.faint)
                text: formDialog.err !== "" ? formDialog.err
                    : formDialog.note !== "" ? formDialog.note
                    : formDialog.dirty ? "Edited, not saved yet."
                    : fmModel.count > 0 ? "Kept with this job" + (formDialog.info.made ? " · drafted " + formDialog.info.made : "") + ". Read every answer before you send it."
                    : "The answers are kept with this job, so you can come back to them." }
            SmallButton { objectName: "fmClose"; text: "Close"; onClicked: formDialog.tryClose() }
            PillButton { objectName: "fmSave"; visible: fmModel.count > 0; primaryStyle: true; text: "Save"; onClicked: formDialog.save() }
        }
    }
}
