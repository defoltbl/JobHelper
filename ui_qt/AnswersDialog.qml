// AnswersDialog: one window of the JobHelper app, created once in Main.qml as `answersDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: answersDialog; objectName: "answersDialog"
    modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(720, win.width - 60); height: Math.min(740, win.height - 50)
    padding: 0
    property string jobId: ""             // the job whose company and role fill {company} and {role}
    property string info: ""
    property bool dirty: false
    ListModel { id: answersModel }
    function show(job) {
        jobId = job || ""; info = ""; dirty = false;
        answersModel.clear();
        var list = bridge.answers();
        for (var i = 0; i < list.length; i++) answersModel.append({ question: list[i].question, answer: list[i].answer });
        ansFlick.contentY = 0; open();
    }
    function all() {
        var out = [];
        for (var i = 0; i < answersModel.count; i++) out.push({ question: answersModel.get(i).question, answer: answersModel.get(i).answer });
        return out;
    }
    function save() {
        var r = bridge.saveAnswers(all());
        if (r && r.ok) { dirty = false; info = "Saved."; show(jobId); info = "Saved."; }
        else info = "Couldn't save the answers.";
    }
    function copy(i) {
        var text = answersModel.get(i).answer;
        if (text.trim() === "") { info = "That answer is still empty."; return; }
        bridge.copyAnswer(text, jobId);
        info = "Copied" + (jobId !== "" && /\{(company|role)\}/.test(text) ? ", with this job's company and role filled in." : ".");
    }
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                Text { text: "Your answers"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                    text: "Write each answer once, then copy it into application forms. {company} and {role} are replaced with the job's when you open this from a job window." } }
            Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                Layout.alignment: Qt.AlignTop
                Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: answersDialog.close() } }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        Flickable {
            id: ansFlick
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentHeight: ansCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            ColumnLayout {
                id: ansCol
                x: 16; y: 14; width: ansFlick.width - 32; spacing: 12
                Repeater {
                    model: answersModel
                    Rectangle { Layout.fillWidth: true; radius: 12; color: theme.surface2; border.color: theme.line; border.width: 1
                        implicitHeight: ansItem.implicitHeight + 24
                        ColumnLayout { id: ansItem; x: 12; y: 12; width: parent.width - 24; spacing: 6
                            RowLayout { Layout.fillWidth: true; spacing: 6
                                TextField { Layout.fillWidth: true; implicitHeight: 28; text: model.question; color: theme.ink
                                    font.pixelSize: 13; font.bold: true; selectByMouse: true; maximumLength: 200
                                    placeholderText: "The question"; placeholderTextColor: theme.faint
                                    background: Rectangle { radius: 7; color: theme.inset; border.width: 1
                                        border.color: parent.activeFocus ? theme.accent : theme.line }
                                    onTextEdited: { answersModel.setProperty(index, "question", text); answersDialog.dirty = true; answersDialog.info = ""; } }
                                SmallButton { text: "Copy"; onClicked: answersDialog.copy(index) }
                                SmallButton { text: "Remove"
                                    onClicked: { answersModel.remove(index); answersDialog.dirty = true; answersDialog.info = ""; } }
                            }
                            Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1
                                border.color: ansEdit.activeFocus ? theme.accent : theme.line
                                implicitHeight: Math.max(56, ansEdit.implicitHeight + 16)
                                TextEdit { id: ansEdit; x: 8; y: 8; width: parent.width - 16; wrapMode: TextEdit.Wrap; selectByMouse: true
                                    color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                                    Component.onCompleted: text = model.answer
                                    onTextChanged: if (activeFocus) { answersModel.setProperty(index, "answer", text); answersDialog.dirty = true; answersDialog.info = ""; }
                                    Text { visible: ansEdit.text === ""; text: "Your answer"; color: theme.faint; font.pixelSize: 12 } } }
                        }
                    }
                }
                SmallButton { objectName: "answersAdd"; text: "+ Add a question"
                    onClicked: { answersModel.append({ question: "", answer: "" }); answersDialog.dirty = true; answersDialog.info = ""; } }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
            Text { objectName: "answersInfo"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                color: answersDialog.info !== "" ? theme.good : theme.faint
                text: answersDialog.info !== "" ? answersDialog.info
                    : answersDialog.dirty ? "Not saved yet." : "Kept encrypted on this Mac. A question with no text is dropped when you save." }
            SmallButton { text: "Close"; onClicked: answersDialog.close() }
            PillButton { objectName: "answersSave"; primaryStyle: true; text: "Save"; onClicked: answersDialog.save() }
        }
    }
}
