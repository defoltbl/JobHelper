// CompareDialog: one window of the JobHelper app, created once in Main.qml as `compareDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: compareDialog; objectName: "compareDialog"
    modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(980, win.width - 40); height: Math.min(760, win.height - 50)
    padding: 0
    property var data: ({})
    function show(jobId) {
        var d = bridge.cvCompare(jobId);
        if (!d || !d.ok) { ticker.text = (d && d.msg) ? d.msg : "These CVs cannot be compared."; return; }
        data = d; cmpFlick.contentY = 0; open();
    }
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                Text { text: "Your CV, before and after"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                Text { objectName: "compareSummary"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                    text: (compareDialog.data.company || "") + "  ·  " + (compareDialog.data.changed || 0) + (compareDialog.data.changed === 1 ? " paragraph changed" : " paragraphs changed")
                          + ((compareDialog.data.added || 0) > 0 ? ", " + compareDialog.data.added + " added" : "")
                          + ((compareDialog.data.removed || 0) > 0 ? ", " + compareDialog.data.removed + " removed" : "")
                          + "  ·  " + (compareDialog.data.same || 0) + " identical (not shown)" } }
            CloseButton { Layout.alignment: Qt.AlignTop; onClicked: compareDialog.close() }
        }
        RowLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 8; spacing: 12
            Text { Layout.fillWidth: true; Layout.preferredWidth: 1; text: "MASTER CV"; color: theme.faint; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.4 }
            Text { Layout.fillWidth: true; Layout.preferredWidth: 1; text: "ADAPTED FOR THIS JOB"; color: theme.accent; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.4 }
        }
        Rectangle { objectName: "olderMaster"; visible: compareDialog.data.older_master === true
            Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 8
            radius: 8; color: theme.inset; border.color: theme.warn; border.width: 1; implicitHeight: omT.implicitHeight + 14
            Text { id: omT; x: 10; y: 7; width: parent.width - 20; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 12
                text: "This CV was adapted before you last changed your master CV. Differences outside the profile and the skills come from that older master, not from the adaptation." } }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        Flickable {
            id: cmpFlick
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentHeight: cmpCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            ColumnLayout {
                id: cmpCol
                x: 16; y: 14; width: cmpFlick.width - 32; spacing: 10
                Text { visible: (compareDialog.data.rows || []).length === 0; Layout.fillWidth: true; wrapMode: Text.WordWrap
                    color: theme.soft; font.pixelSize: 13; text: "The adapted CV is identical to your master CV." }
                Repeater {
                    model: compareDialog.data.rows || []
                    ColumnLayout { Layout.fillWidth: true; spacing: 4
                        Text { visible: index === 0 || compareDialog.data.rows[index - 1].section !== modelData.section
                            text: modelData.section || "Start of the CV"; color: theme.faint; font.pixelSize: 10; font.bold: true
                            font.letterSpacing: 1.2; font.capitalization: Font.AllUppercase; Layout.topMargin: index === 0 ? 0 : 6 }
                        RowLayout { Layout.fillWidth: true; spacing: 12
                            Rectangle { Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.alignment: Qt.AlignTop
                                radius: 9; color: theme.surface2; border.color: theme.line; border.width: 1
                                implicitHeight: lT.implicitHeight + 18
                                Text { id: lT; x: 10; y: 9; width: parent.width - 20; wrapMode: Text.WordWrap; textFormat: Text.StyledText
                                    color: theme.soft; font.pixelSize: 12; lineHeight: 1.25
                                    text: modelData.master !== "" ? modelData.master : "<i>not in the master CV</i>" } }
                            Rectangle { Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.alignment: Qt.AlignTop
                                radius: 9; color: theme.surface2; border.width: 1
                                border.color: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.6)
                                implicitHeight: rT.implicitHeight + 18
                                Text { id: rT; x: 10; y: 9; width: parent.width - 20; wrapMode: Text.WordWrap; textFormat: Text.StyledText
                                    color: theme.ink; font.pixelSize: 12; lineHeight: 1.25
                                    text: modelData.adapted !== "" ? modelData.adapted : "<i>removed in the adapted CV</i>" } }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                text: "Left: words that were replaced are struck through. Right: new words are bold." }
            SmallButton { text: "Open the adapted CV"; onClicked: bridge.openDoc("cv", compareDialog.data.file || "") }
            PillButton { primaryStyle: true; text: "Close"; onClicked: compareDialog.close() }
        }
    }
}
