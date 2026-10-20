// PrepEditDialog: edit a saved interview preparation part by part, created once in Main.qml as `prepEditDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: prepEditDialog; objectName: "prepEditDialog"
    modal: true; anchors.centerIn: parent
    readonly property bool holdsWork: dirty                 // unsaved changes
    closePolicy: holdsWork ? Popup.NoAutoClose : Popup.CloseOnEscape      // Esc must not throw away edits ...
    Shortcut { sequence: "Escape"; enabled: prepEditDialog.holdsWork && win.onTop(prepEditDialog); onActivated: prepEditDialog.tryClose() }   // ... nor do nothing
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(780, win.width - 60); height: Math.min(800, win.height - 40)
    padding: 0
    property string jobId: ""
    property var info: ({})
    property int maxPart: 0
    property bool dirty: false
    property bool confirmClose: false
    property string err: ""
    property string note: ""
    ListModel { id: peModel }
    function show(job) {
        var d = bridge.prepParts(job);
        if (!d || !d.ok) { ticker.text = (d && d.msg) ? d.msg : "This preparation cannot be edited."; return; }
        jobId = job; info = d; maxPart = d.max_part; maxLines = d.max_items; maxLine = d.max_item; err = ""; note = ""; dirty = false; confirmClose = false;
        peModel.clear();
        for (var i = 0; i < d.parts.length; i++) peModel.append({ key: d.parts[i].key, label: d.parts[i].label, text: d.parts[i].text, kind: d.parts[i].kind });
        peFlick.contentY = 0; open();
    }
    function all() {
        var out = [];
        for (var i = 0; i < peModel.count; i++) out.push({ key: peModel.get(i).key, text: peModel.get(i).text });
        return out;
    }
    function tooLong() {            // the first part over the limit, to say it before anything is sent
        for (var i = 0; i < peModel.count; i++)
            if (peModel.get(i).kind !== "list" && peModel.get(i).text.length > maxPart) return peModel.get(i).label;
        return "";
    }
    property int maxLines: 0              // these three come with the preparation (interview_prep: MAX_PART, MAX_ITEMS, MAX_ITEM)
    property int maxLine: 0
    function listProblem(text) {    // what is wrong with a list, while it is typed ("" if nothing)
        var lines = ("" + text).split("\n").filter(function (l) { return l.trim() !== ""; });
        if (lines.length > maxLines) return lines.length + " lines; the most is " + maxLines + ". Remove some.";
        for (var i = 0; i < lines.length; i++)
            if (lines[i].trim().length > maxLine) return "Line " + (i + 1) + " is " + lines[i].trim().length + " characters long; the most is " + maxLine + ".";
        return "";
    }
    function badList() {
        for (var i = 0; i < peModel.count; i++)
            if (peModel.get(i).kind === "list" && listProblem(peModel.get(i).text) !== "") return peModel.get(i).label + ": " + listProblem(peModel.get(i).text);
        return "";
    }
    function save() {
        err = ""; note = ""; confirmClose = false;
        var long = tooLong();
        if (long !== "") { err = "“" + long.substring(0, 60) + "” is longer than " + maxPart + " characters. Shorten it, then save."; return; }
        var list = badList();
        if (list !== "") { err = list; return; }
        var r = bridge.savePrepParts(jobId, all());
        if (!(r && r.ok)) { err = (r && r.msg) ? r.msg : "The changes could not be saved."; return; }
        dirty = false;
        note = "Saved." + ((r.to_check || 0) > 0 ? " " + r.to_check + (r.to_check === 1 ? " part mentions" : " parts mention")
                                                    + " something that is not in your CV; they are marked in the sheet." : "");
        detailDialog.refresh();
        if (prepDialog.visible) prepDialog.show(jobId);
    }
    function tryClose() {
        if (dirty && !confirmClose) {
            confirmClose = true; note = "";
            err = "You changed the sheet and did not save it. Press Save, or Close once more to discard the changes.";
            return;
        }
        dirty = false; close();
    }
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
        FocusCatcher {} }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                Text { text: "Edit the preparation"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                Text { objectName: "peFor"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                    text: (prepEditDialog.info.company || "") + "  ·  " + (prepEditDialog.info.title || "")
                          + "  ·  your changes stay until you press Make again" } }
            CloseButton { Layout.alignment: Qt.AlignTop; onClicked: prepEditDialog.tryClose() }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        Flickable {
            id: peFlick
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentHeight: peCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            FocusCatcher {}                // a press on empty space in the scroll area
            ColumnLayout {
                id: peCol
                x: 16; y: 14; width: peFlick.width - 32; spacing: 12
                Repeater {
                    model: peModel
                    ColumnLayout { Layout.fillWidth: true; spacing: 4
                        readonly property bool over: model.kind !== "list" && peText.text.length > prepEditDialog.maxPart
                        readonly property string listSays: model.kind === "list" ? prepEditDialog.listProblem(peText.text) : ""
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; font.bold: true; text: model.label }
                        Text { visible: model.kind === "list"; color: theme.faint; font.pixelSize: 11; text: "One per line. Delete a line to remove it." }
                        Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1
                            border.color: parent.over || parent.listSays !== "" ? theme.crit : (peText.activeFocus ? theme.accent : theme.line)
                            implicitHeight: Math.max(44, peText.implicitHeight + 16)
                            TextEdit { id: peText; x: 8; y: 8; width: parent.width - 16; wrapMode: TextEdit.Wrap; selectByMouse: true
                                color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                                Component.onCompleted: text = model.text
                                onTextChanged: if (activeFocus) { peModel.setProperty(index, "text", text); prepEditDialog.dirty = true
                                                                  prepEditDialog.err = ""; prepEditDialog.note = ""; prepEditDialog.confirmClose = false; } } }
                        Text { visible: parent.listSays !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.crit
                            font.pixelSize: 11; font.bold: true; text: parent.listSays }
                        Text { visible: parent.over; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11; font.bold: true
                            text: (peText.text.length - prepEditDialog.maxPart) + " characters too long (the limit is " + prepEditDialog.maxPart + ")" }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
            Text { objectName: "peNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap
                font.pixelSize: prepEditDialog.err !== "" ? 12 : 11; font.bold: prepEditDialog.err !== ""
                color: prepEditDialog.err !== "" ? theme.crit : (prepEditDialog.note !== "" ? theme.good : theme.faint)
                text: prepEditDialog.err !== "" ? prepEditDialog.err
                    : prepEditDialog.note !== "" ? prepEditDialog.note
                    : prepEditDialog.dirty ? "Changed, not saved yet."
                    : "Change any part in your own words. “Open as document” then uses your version." }
            SmallButton { objectName: "peClose"; text: "Close"; onClicked: prepEditDialog.tryClose() }
            PillButton { objectName: "peSave"; primaryStyle: true; text: "Save"; onClicked: prepEditDialog.save() }
        }
    }
}
