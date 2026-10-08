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
    modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
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
        jobId = job; err = ""; note = ""; busy = false;
        fill(d);
        fmQuestions.text = (d.items || []).map(function (i) { return i.question; }).join("\n");
        fmFlick.contentY = 0; open();
    }
    function all() {
        var out = [];
        for (var i = 0; i < fmModel.count; i++) { var r = fmModel.get(i); out.push({ question: r.question, answer: r.answer, check: r.check }); }
        return out;
    }
    function draft() {
        err = ""; note = "";
        if (fmQuestions.text.trim() === "") { err = "Paste the questions from the form first, one per line."; return; }
        busy = true;
        bridge.draftAnswers(jobId, fmQuestions.text);
    }
    function save() {
        var r = bridge.saveFormAnswers(jobId, all());
        if (r && r.ok) { dirty = false; note = "Saved with this job."; detailDialog.refresh(); }
        else err = "Couldn't save the answers.";
    }
    function copy(i) {
        var text = fmModel.get(i).answer;
        if (text.trim() === "") { note = ""; err = "That answer is still empty."; return; }
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
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                Text { text: "Answers for this form"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                Text { objectName: "formFor"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                    text: (formDialog.info.company || "") + "  ·  " + (formDialog.info.title || "") } }
            Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                Layout.alignment: Qt.AlignTop
                Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: formDialog.close() } }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        Flickable {
            id: fmFlick
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentHeight: fmCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            ColumnLayout {
                id: fmCol
                x: 16; y: 14; width: fmFlick.width - 32; spacing: 12
                DetailCard { heading: "The form's questions"
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                        text: "Every form asks something different. Paste this form's questions here, one per line." }
                    Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1
                        border.color: fmQuestions.activeFocus ? theme.accent : (formDialog.err !== "" && fmQuestions.text.trim() === "" ? theme.crit : theme.line)
                        implicitHeight: Math.max(96, fmQuestions.implicitHeight + 16)
                        TextEdit { id: fmQuestions; objectName: "fmQuestions"; x: 8; y: 8; width: parent.width - 16
                            wrapMode: TextEdit.Wrap; selectByMouse: true; color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                            readOnly: formDialog.busy
                            onTextChanged: if (activeFocus) { formDialog.err = ""; formDialog.note = ""; }
                            Text { visible: fmQuestions.text === ""; color: theme.faint; font.pixelSize: 12
                                text: "What are your salary expectations?\nWhy do you want to work with us?" } } }
                    RowLayout { Layout.fillWidth: true; spacing: 6
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                            text: "Claude drafts the answers in one call, from your CV, this posting and About you in Options. Nothing outside your CV is claimed." }
                        SmallButton { objectName: "fmCommon"; enabled: !formDialog.busy; text: "Common questions"
                            onClicked: { fmQuestions.text = (formDialog.info.common || []).join("\n"); formDialog.err = ""; formDialog.note = ""; } }
                        SmallButton { objectName: "fmDraft"; primaryStyle: true; enabled: !formDialog.busy
                            text: formDialog.busy ? "Asking Claude…" : (fmModel.count > 0 ? "Draft again" : "Draft answers")
                            onClicked: formDialog.draft() }
                    }
                    Text { objectName: "fmErr"; visible: formDialog.err !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: theme.crit; font.pixelSize: 12; font.bold: true; text: formDialog.err }
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
                                border.color: fmAns.activeFocus ? theme.accent : theme.line
                                implicitHeight: Math.max(52, fmAns.implicitHeight + 16)
                                TextEdit { id: fmAns; x: 8; y: 8; width: parent.width - 16; wrapMode: TextEdit.Wrap; selectByMouse: true
                                    color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                                    Component.onCompleted: text = model.answer
                                    onTextChanged: if (activeFocus) { fmModel.setProperty(index, "answer", text); formDialog.dirty = true; formDialog.note = ""; }
                                    Text { visible: fmAns.text === ""; text: "Write this answer yourself"; color: theme.faint; font.pixelSize: 12 } } }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
            Text { objectName: "fmNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                color: formDialog.note !== "" ? theme.good : theme.faint
                text: formDialog.note !== "" ? formDialog.note
                    : formDialog.dirty ? "Edited, not saved yet."
                    : fmModel.count > 0 ? "Kept with this job" + (formDialog.info.made ? " · drafted " + formDialog.info.made : "") + ". Read every answer before you send it."
                    : "The answers are kept with this job, so you can come back to them." }
            SmallButton { text: "Close"; onClicked: formDialog.close() }
            PillButton { objectName: "fmSave"; visible: fmModel.count > 0; primaryStyle: true; text: "Save"; onClicked: formDialog.save() }
        }
    }
}
