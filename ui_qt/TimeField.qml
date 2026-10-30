// TimeField: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Item {
    id: tfr
    property int value: 0
    property int maxv: 23
    property bool _typing: false
    property alias text: ti.text          // what is typed, which may be empty
    readonly property bool empty: ti.text.trim() === ""        // nothing typed: not the same as 00
    readonly property bool valid: !empty && value >= 0 && value <= maxv
    signal edited()
    implicitWidth: 112; implicitHeight: 32
    function _fmt(v) { return (v < 10 ? "0" : "") + v; }
    function reset(v) { _typing = false; value = v; ti.text = _fmt(v); }     // what the window shows on opening, whatever was typed before
    onValueChanged: if (!_typing) ti.text = _fmt(value)   // don't reformat mid-type
    Rectangle {
        anchors.fill: parent; radius: 8; color: theme.surface; border.width: 1.5
        border.color: !tfr.valid ? theme.crit : (ti.activeFocus ? theme.accent : theme.line)
    }
    Rectangle {
        x: 1; y: 1; width: 32; height: parent.height - 2; radius: 7
        color: dPress.pressed ? theme.inset : (dMa.hovered ? theme.surface2 : "transparent")
        Text { anchors.centerIn: parent; text: "−"; color: theme.ink; font.pixelSize: 16 }
        HoverHandler { id: dMa; cursorShape: Qt.PointingHandCursor }
        MouseArea { id: dPress; anchors.fill: parent
            onClicked: { tfr._typing = false; if (tfr.value > 0) tfr.value--; else ti.text = tfr._fmt(tfr.value); tfr.edited(); } }
    }
    Rectangle {
        x: parent.width - 33; y: 1; width: 32; height: parent.height - 2; radius: 7
        color: uPress.pressed ? theme.inset : (uMa.hovered ? theme.surface2 : "transparent")
        Text { anchors.centerIn: parent; text: "+"; color: theme.ink; font.pixelSize: 15 }
        HoverHandler { id: uMa; cursorShape: Qt.PointingHandCursor }
        MouseArea { id: uPress; anchors.fill: parent
            onClicked: { tfr._typing = false; if (tfr.value < tfr.maxv) tfr.value++; else ti.text = tfr._fmt(tfr.value); tfr.edited(); } }
    }
    TextInput {
        id: ti; objectName: "timeInput"; anchors.centerIn: parent; width: parent.width - 72
        color: theme.ink; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter
        selectByMouse: true; inputMethodHints: Qt.ImhDigitsOnly
        validator: IntValidator { bottom: 0; top: 99 }   // allow typing 24/25/60… so we can flag them
        Component.onCompleted: text = tfr._fmt(tfr.value)
        // commit the value LIVE while typing so Save always sees the current
        // number (and the red error appears immediately), without reformatting
        onTextEdited: { tfr._typing = true; var v = parseInt(text, 10); tfr.value = isNaN(v) ? 0 : v; tfr.edited(); }
        onEditingFinished: {
            tfr._typing = false;
            if (text.trim() === "") { tfr.edited(); return; }       // left empty: it stays empty and says so, never "00"
            var v = parseInt(text, 10); tfr.value = isNaN(v) ? 0 : v; ti.text = tfr._fmt(tfr.value); tfr.edited();
        }
    }
}
