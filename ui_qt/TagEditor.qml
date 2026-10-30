// TagEditor: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

ColumnLayout {
    id: te
    property string label: ""
    property string hint: ""
    property string placeholder: ""
    property string err: ""
    property color chipTone: theme.ink
    ListModel { id: teModel }
    function setAll(arr) { teModel.clear(); for (var i = 0; i < (arr || []).length; i++) teModel.append({ text: "" + arr[i] }); err = ""; teField.text = ""; }
    readonly property int tagCount: teModel.count
    readonly property string typed: teField.text.trim()      // typed into the box and not added to the list (yet)
    function all() { var out = []; for (var i = 0; i < teModel.count; i++) out.push("" + teModel.get(i).text); return out; }
    function add(txt) {
        var t = (txt || "").trim().toLowerCase();
        err = "";
        if (!t) return false;
        if (win.hasNonLatin(t)) { err = "Use Latin letters, as job titles are written."; return false; }
        if (!/[a-z]/.test(t) || t.length < 2) { err = "Enter a word from a job title, for example: intern."; return false; }
        if (t.length > win.limits.list_word) { err = "That is too long: up to " + win.limits.list_word + " characters. Use one word or a short phrase."; return false; }
        if (teModel.count >= win.limits.list_max) { err = "The list holds up to " + win.limits.list_max + " entries. Remove one first."; return false; }
        for (var i = 0; i < teModel.count; i++)
            if (teModel.get(i).text === t) { err = "That word is already in the list."; return false; }
        teModel.append({ text: t });
        return true;
    }
    Layout.fillWidth: true; spacing: 0
    SRow { label: te.label; hint: te.hint
        RowLayout { spacing: 6
            TextField { id: teField; implicitWidth: 180; implicitHeight: 30; placeholderText: te.placeholder
                placeholderTextColor: theme.faint; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                background: Rectangle { radius: 8; color: theme.surface; border.width: 1
                    border.color: (te.err !== "") ? theme.crit : (teField.activeFocus ? theme.accent : theme.line) }
                onTextEdited: te.err = ""
                onAccepted: if (te.add(text)) text = "" }
            SmallButton { text: "+ Add"; primaryStyle: true; onClicked: { if (te.add(teField.text)) teField.text = ""; } } } }
    Text { visible: te.err !== ""; Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.topMargin: 2
        wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11; font.bold: true; text: te.err }
    Flow {
        Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.bottomMargin: 12
        spacing: 6; visible: teModel.count > 0
        Repeater { model: teModel
            Rectangle {
                radius: 999; color: theme.inset; border.color: theme.line; border.width: 1
                implicitHeight: 24; implicitWidth: teChip.width + 16
                Row { id: teChip; anchors.centerIn: parent; spacing: 5
                    Text { text: model.text; color: te.chipTone; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: "✕"; color: theme.faint; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter
                        MouseArea { anchors.fill: parent; anchors.margins: -4; cursorShape: Qt.PointingHandCursor
                            onClicked: teModel.remove(index) } } }
            } }
    }
}
