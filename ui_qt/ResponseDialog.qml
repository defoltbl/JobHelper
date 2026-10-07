// ResponseDialog: one window of the JobHelper app, created once in Main.qml as `responseDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: responseDialog; objectName: "responseDialog"
    modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(620, win.width - 80); padding: 0
    property var r: ({})
    function show(msgId) {
        var d = bridge.responseDetail(msgId);
        if (!d || !d.id) { ticker.text = "That reply could not be opened."; return; }
        r = d; open();
    }
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                Text { objectName: "responseTitle"; text: responseDialog.r.company || ""; color: theme.ink; font.pixelSize: 17; font.bold: true
                    Layout.fillWidth: true; elide: Text.ElideRight }
                Text { text: responseDialog.r.role || ""; visible: text !== ""; color: theme.soft; font.pixelSize: 12
                    Layout.fillWidth: true; wrapMode: Text.WordWrap } }
            Rectangle { visible: !!responseDialog.r.stage; radius: 999; implicitHeight: 22; implicitWidth: rsT.width + 18
                Layout.alignment: Qt.AlignTop; color: win.badgeBg(responseDialog.r.stage || "")
                Text { id: rsT; anchors.centerIn: parent; text: responseDialog.r.stage || ""; font.pixelSize: 11; font.bold: true
                    color: win.badgeColor(responseDialog.r.stage || "") } }
            Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                Layout.alignment: Qt.AlignTop
                Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: responseDialog.close() } }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        ColumnLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
            DetailCard { heading: "What it says"
                Text { objectName: "responseSummary"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                    text: responseDialog.r.summary || "No summary was saved for this email." } }
            DetailCard { heading: "Rejection"; visible: responseDialog.r.stage === "rejection"
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                    text: (responseDialog.r.category ? "Reason given: " + responseDialog.r.category + "." : "No reason was given.")
                          + (responseDialog.r.reason ? "\n" + responseDialog.r.reason : "") } }
            DetailCard { heading: "Next step"; visible: !!responseDialog.r.next_step
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; text: responseDialog.r.next_step || "" } }
            DetailCard { heading: "The email"
                TextEdit { Layout.fillWidth: true; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                    color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                    text: "Subject: " + (responseDialog.r.subject || "—") + "\nFrom: " + (responseDialog.r.sender || "—")
                          + "\nReceived: " + (responseDialog.r.date || "—") } }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
            Text { Layout.fillWidth: true; elide: Text.ElideRight; color: theme.faint; font.pixelSize: 11
                text: responseDialog.r.job_id ? ("Belongs to: " + responseDialog.r.job_company + " · " + responseDialog.r.job_title
                                                 + " (" + responseDialog.r.job_status + ")")
                                              : "Not linked to an application in your list." }
            SmallButton { objectName: "openApplication"; visible: !!responseDialog.r.job_id; text: "Open the application"
                onClicked: { var id = responseDialog.r.job_id; responseDialog.close(); detailDialog.show(id); } }
        }
    }
}
