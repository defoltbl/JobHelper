// PrepDialog: one window of the JobHelper app, created once in Main.qml as `prepDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: prepDialog; objectName: "prepDialog"
    modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(760, win.width - 60); height: Math.min(780, win.height - 50)
    padding: 0
    property var prep: ({})
    property string note: ""
    function who(q) {       // older saved preparations have no audience: questions about the work itself go to the specialist
        if (q && (q.audience === "hr" || q.audience === "technical")) return q.audience;
        return q && (q.kind === "technical" || q.kind === "your projects") ? "technical" : "hr";
    }
    function show(jobId) {
        var d = bridge.interviewPrep(jobId);
        if (!d || !d.id) { ticker.text = "No interview preparation is saved for this job yet."; return; }
        prep = d; note = ""; prepFlick.contentY = 0; open();
    }
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
        FocusCatcher {} }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                Text { text: "Interview preparation"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                Text { objectName: "prepFor"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.soft; font.pixelSize: 12
                    text: (prepDialog.prep.company || "") + "  ·  " + (prepDialog.prep.title || "") } }
            Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                Layout.alignment: Qt.AlignTop
                Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: prepDialog.close() } }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        Flickable {
            id: prepFlick
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentHeight: prepCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            FocusCatcher {}                // a press on empty space in the scroll area
            ColumnLayout {
                id: prepCol
                x: 16; y: 14; width: prepFlick.width - 32; spacing: 12
                DetailCard { heading: "What to expect"; visible: !!prepDialog.prep.summary
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                        text: prepDialog.prep.summary || "" } }
                Repeater {
                    model: prepDialog.prep.questions || []
                    ColumnLayout { Layout.fillWidth: true; spacing: 6
                        // the questions come in two groups: what HR asks, and what someone who does the work asks
                        Text { visible: index === 0 || (prepDialog.who(prepDialog.prep.questions[index - 1]) !== prepDialog.who(modelData))
                            Layout.fillWidth: true; wrapMode: Text.WordWrap; Layout.topMargin: index === 0 ? 0 : 10
                            text: prepDialog.who(modelData) === "hr" ? "If you speak with HR or a recruiter: plain words, no jargon"
                                                                     : "If you speak with someone who does this work or the hiring manager: precise answers"
                            color: theme.ink; font.pixelSize: 14; font.bold: true }
                        Text { visible: index === 0 || (prepDialog.prep.questions[index - 1].kind !== modelData.kind)
                                        || (prepDialog.who(prepDialog.prep.questions[index - 1]) !== prepDialog.who(modelData))
                            text: modelData.kind; color: theme.accent; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.4
                            font.capitalization: Font.AllUppercase; Layout.topMargin: index === 0 ? 0 : 6 }
                        Rectangle { Layout.fillWidth: true; radius: 12; color: theme.surface2; border.width: 1
                            border.color: modelData.check ? theme.warn : theme.line
                            implicitHeight: qaCol.implicitHeight + 24
                            ColumnLayout { id: qaCol; x: 14; y: 12; width: parent.width - 28; spacing: 6
                                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 14; font.bold: true
                                    text: (index + 1) + ".  " + modelData.question }
                                Text { visible: !!modelData.why; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                    text: "Why they ask: " + (modelData.why || "") }
                                TextEdit { Layout.fillWidth: true; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                                    text: modelData.answer; color: theme.ink; font.pixelSize: 13; selectionColor: theme.accent }
                                Text { visible: !!modelData.check; Layout.fillWidth: true; wrapMode: Text.WordWrap
                                    color: theme.warn; font.pixelSize: 11; font.bold: true
                                    text: "Check this answer: it talks about " + (modelData.check || "") + ", which is not in your CV. Say only what is true." }
                            }
                        }
                    }
                }
                DetailCard { heading: "What you can ask HR or the recruiter"; objectName: "askHr"
                    visible: (prepDialog.prep.ask_hr || []).length > 0
                    Repeater { model: prepDialog.prep.ask_hr || []
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                            text: "•  " + modelData } } }
                DetailCard { heading: "What you can ask the people you would work with or the hiring manager"; objectName: "askTech"
                    visible: (prepDialog.prep.ask_technical || []).length > 0
                    Repeater { model: prepDialog.prep.ask_technical || []
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                            text: "•  " + modelData } } }
                DetailCard { heading: "Questions to ask them"
                    visible: (prepDialog.prep.ask_them || []).length > 0 && (prepDialog.prep.ask_hr || []).length === 0
                             && (prepDialog.prep.ask_technical || []).length === 0
                    Repeater { model: prepDialog.prep.ask_them || []
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; text: "•  " + modelData } } }
                DetailCard { heading: "Revise before the interview"; visible: (prepDialog.prep.revise || []).length > 0
                    Repeater { model: prepDialog.prep.revise || []
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; text: "•  " + modelData } } }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                color: prepDialog.note !== "" ? theme.good : theme.faint
                text: prepDialog.note !== "" ? prepDialog.note
                    : "Answers are a starting point built from your CV. Say them in your own words." }
            SmallButton { objectName: "prepEdit"; text: "Edit"; onClicked: prepEditDialog.show(prepDialog.prep.id) }
            SmallButton { objectName: "prepDoc"; primaryStyle: true; text: "Open as document"
                onClicked: { var r = bridge.prepDocument(prepDialog.prep.id, false);
                    prepDialog.note = (r && r.ok) ? "Opened " + r.file + " in Word." : "";
                    if (!(r && r.ok)) ticker.text = (r && r.msg) || "Couldn't write the document."; } }
            SmallButton { objectName: "prepShow"; text: "Show in folder"
                onClicked: { var r = bridge.prepDocument(prepDialog.prep.id, true);
                    prepDialog.note = (r && r.ok) ? "Shown in its folder: " + r.file : "";
                    if (!(r && r.ok)) ticker.text = (r && r.msg) || "Couldn't write the document."; } }
            SmallButton { objectName: "prepCopy"; text: "Copy all"
                onClicked: { bridge.copyText(bridge.prepText(prepDialog.prep.id)); prepDialog.note = "Copied. Paste it into Notes or a document."; } }
            PillButton { primaryStyle: true; text: "Close"; onClicked: prepDialog.close() }
        }
    }
}
