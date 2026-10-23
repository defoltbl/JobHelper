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
    height: Math.min(implicitHeight, win.height - 40)
    property var r: ({})
    property bool picking: false          // the list of applications to file this reply under is open
    property var targets: []
    property string fileNote: ""
    property bool fileBad: false
    function show(msgId) {
        var d = bridge.responseDetail(msgId);
        if (!d || !d.id) { ticker.text = "That reply could not be opened."; return; }
        r = d; picking = false; fileNote = ""; fileBad = false; respFlick.contentY = 0; open();
    }
    function startPicking() {
        fileNote = ""; fileBad = false;
        if (win.appRunning) { fileBad = true; fileNote = "A search or scan is running. File the reply when it has finished."; return; }
        pickFilter.text = ""; targets = bridge.filingTargets(""); picking = true; pickFilter.forceActiveFocus();
    }
    function fileUnder(jobId) {
        var res = bridge.refileResponse(r.id, jobId);
        fileBad = !(res && res.ok);
        fileNote = (res && res.msg) || (fileBad ? "The reply could not be filed there." : "");
        if (!fileBad) {
            picking = false; r = bridge.responseDetail(r.id);
            win.countsData = bridge.counts(); win.refreshOpenView();
        }
    }
    onClosed: { picking = false; fileNote = ""; fileBad = false; }
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
        FocusCatcher {} }
    contentItem: ColumnLayout {
        spacing: 0
        DialogHeader {
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                DialogTitle { objectName: "responseTitle"; text: responseDialog.r.company || "" }
                Text { textFormat: Text.PlainText; text: responseDialog.r.role || ""; visible: text !== ""; color: theme.soft; font.pixelSize: 12
                    Layout.fillWidth: true; wrapMode: Text.WordWrap } }
            Rectangle { visible: !!responseDialog.r.stage; radius: 999; implicitHeight: 22; implicitWidth: rsT.width + 18
                Layout.alignment: Qt.AlignTop; color: win.badgeBg(responseDialog.r.stage || "")
                Text { textFormat: Text.PlainText; id: rsT; anchors.centerIn: parent; text: responseDialog.r.stage || ""; font.pixelSize: 11; font.bold: true
                    color: win.badgeColor(responseDialog.r.stage || "") } }
            CloseButton { Layout.alignment: Qt.AlignTop; onClicked: responseDialog.close() }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        // what the email says can be long: it scrolls, so the buttons and the list under it are never pushed out of the window
        Flickable { id: respFlick; objectName: "respFlick"
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 90; implicitHeight: respCol.implicitHeight + 32
            clip: true; contentHeight: respCol.implicitHeight + 32; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
        ColumnLayout { id: respCol; x: 16; y: 16; width: respFlick.width - 32; spacing: 12
            DetailCard { heading: "What it says"
                Text { textFormat: Text.PlainText; objectName: "responseSummary"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                    text: responseDialog.r.summary || "No summary was saved for this email." } }
            DetailCard { heading: "Rejection"; visible: responseDialog.r.stage === "rejection"
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                    text: (responseDialog.r.category ? "Reason given: " + responseDialog.r.category + "." : "No reason was given.")
                          + (responseDialog.r.reason ? "\n" + responseDialog.r.reason : "") } }
            DetailCard { heading: "Next step"; visible: !!responseDialog.r.next_step
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; text: responseDialog.r.next_step || "" } }
            DetailCard { heading: "The email"
                TextEdit { textFormat: TextEdit.PlainText; Layout.fillWidth: true; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                    color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                    text: "Subject: " + (responseDialog.r.subject || "—") + "\nFrom: " + (responseDialog.r.sender || "—")
                          + "\nReceived: " + (responseDialog.r.date || "—") } }
        }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        DialogFooter {
            Text { textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.faint; font.pixelSize: 11
                text: responseDialog.r.job_id ? ("Belongs to: " + responseDialog.r.job_company + " · " + responseDialog.r.job_title
                                                 + " (" + responseDialog.r.job_status + ")")
                                              : "Not linked to an application in your list." }
            SmallButton { objectName: "fileUnder"; text: responseDialog.picking ? "Cancel" : (responseDialog.r.job_id ? "File under another…" : "File under…")
                onClicked: { if (responseDialog.picking) { responseDialog.picking = false; responseDialog.fileNote = ""; } else responseDialog.startPicking(); } }
            SmallButton { objectName: "openApplication"; visible: !!responseDialog.r.job_id; text: "Open the application"
                onClicked: { var id = responseDialog.r.job_id; responseDialog.close(); detailDialog.show(id); } }
        }
        Text { textFormat: Text.PlainText; objectName: "fileNote"; visible: responseDialog.fileNote !== ""
            Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 14; Layout.bottomMargin: 10; wrapMode: Text.WordWrap
            font.pixelSize: 11; font.bold: responseDialog.fileBad; color: responseDialog.fileBad ? theme.crit : theme.good; text: responseDialog.fileNote }
        // choosing the application this reply belongs to
        ColumnLayout { objectName: "filePicker"; visible: responseDialog.picking
            Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 14; Layout.bottomMargin: 12; spacing: 6
            TextField { id: pickFilter; objectName: "pickFilter"; Layout.fillWidth: true; implicitHeight: 30; maximumLength: 80
                placeholderText: "Type a company or a role to narrow the list"; placeholderTextColor: theme.faint
                color: theme.ink; font.pixelSize: 12; selectByMouse: true
                background: Rectangle { radius: 8; color: theme.inset; border.width: 1; border.color: pickFilter.activeFocus ? theme.accent : theme.line }
                onTextEdited: responseDialog.targets = bridge.filingTargets(text) }
            Text { textFormat: Text.PlainText; objectName: "pickEmpty"; visible: responseDialog.targets.length === 0; Layout.fillWidth: true; wrapMode: Text.WordWrap
                color: theme.warn; font.pixelSize: 11
                text: pickFilter.text.trim() === "" ? "You have no applications yet. A reply is filed under an application: mark the job as applied first."
                                                    : "No application matches “" + pickFilter.text.trim() + "”. Try fewer letters." }
            ListView { id: pickList; objectName: "pickList"; Layout.fillWidth: true; clip: true
                implicitHeight: Math.min(contentHeight, 190); model: responseDialog.targets; spacing: 4
                ScrollBar.vertical: ScrollBar {}
                FocusCatcher { z: 2 }      // over the rows: picking one ends the editing of the filter box first
                delegate: Rectangle { width: pickList.width - 8; radius: 8; implicitHeight: pickRow.implicitHeight + 12
                    readonly property bool here: modelData.id === responseDialog.r.job_id
                    color: pickMouse.containsMouse && !here ? theme.surface2 : theme.inset; border.width: 1; border.color: theme.line
                    RowLayout { id: pickRow; anchors.fill: parent; anchors.margins: 6; spacing: 8
                        Text { textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.Wrap; color: parent.parent.here ? theme.faint : theme.ink; font.pixelSize: 12
                            text: modelData.company + " · " + modelData.title }
                        Text { textFormat: Text.PlainText; color: theme.soft; font.pixelSize: 11
                            text: parent.parent.here ? "filed here" : (modelData.status + (modelData.applied ? " · " + modelData.applied : "")) } }
                    MouseArea { id: pickMouse; anchors.fill: parent; hoverEnabled: true; enabled: !parent.here
                        cursorShape: Qt.PointingHandCursor; onClicked: responseDialog.fileUnder(modelData.id) } } }
            SmallButton { objectName: "fileNowhere"; visible: !!responseDialog.r.job_id; text: "It belongs to none of my applications"
                onClicked: responseDialog.fileUnder("") }
        }
    }
}
