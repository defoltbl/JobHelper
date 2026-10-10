// ThemedSpin: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

SpinBox {
    id: sp
    editable: true
    wheelEnabled: false          // scrolling the page must never change a number
    implicitHeight: 32; implicitWidth: 120
    font.pixelSize: 12
    palette.text: theme.ink; palette.highlightedText: "#ffffff"
    leftPadding: 36; rightPadding: 36; topPadding: 0; bottomPadding: 0
    property string note: ""             // what is wrong with the typed number, or what was changed
    property bool noteBad: false
    background: Rectangle { radius: 8; color: theme.surface
        border.color: sp.note !== "" && sp.noteBad ? theme.crit : (sp.activeFocus ? theme.accent : theme.line); border.width: 1 }
    Timer { id: noteTimer; interval: 4500; onTriggered: sp.note = "" }
    // shown under the field, on top of whatever is below it, so no row has to make room
    Rectangle {
        visible: sp.note !== ""; z: 50
        x: sp.width - width; y: sp.height + 4; width: noteText.implicitWidth + 16; height: noteText.implicitHeight + 10
        radius: 7; color: sp.noteBad ? theme.critbg : theme.surface2; border.width: 1; border.color: sp.noteBad ? theme.crit : theme.steel
        Text { id: noteText; objectName: "spinNote"; anchors.centerIn: parent; text: sp.note; color: theme.ink; font.pixelSize: 11; font.bold: sp.noteBad }
    }
    contentItem: TextInput {
        id: spIn
        text: sp.displayText; font: sp.font; color: theme.ink
        selectByMouse: true; cursorVisible: sp.activeFocus
        horizontalAlignment: Qt.AlignHCenter; verticalAlignment: Qt.AlignVCenter
        readOnly: !sp.editable
        validator: IntValidator { bottom: 0; top: 999999 }        // any number can be typed, so a wrong one can be explained
        inputMethodHints: Qt.ImhDigitsOnly
        // What is typed becomes the value at once, so Save never stores the old
        // number because the field still had the cursor in it. A number outside the
        // range is not taken: the field turns red and says what it accepts.
        onTextEdited: {
            var v = parseInt(text, 10);
            noteTimer.stop();
            if (text === "" || isNaN(v)) { sp.note = ""; return; }
            if (v < sp.from || v > sp.to) { sp.noteBad = true; sp.note = "Between " + sp.from + " and " + sp.to; return; }
            sp.note = ""; sp.value = v;
        }
        // when editing ends the field shows a valid number again, and says so if it had to change it
        onEditingFinished: {
            var v = parseInt(text, 10);
            if (text === "" || isNaN(v)) { sp.noteBad = false; sp.note = "Left at " + sp.value; noteTimer.restart(); }
            else if (v < sp.from || v > sp.to) {
                sp.value = v < sp.from ? sp.from : sp.to;
                sp.noteBad = false; sp.note = "Changed to " + sp.value + ", the " + (v < sp.from ? "lowest" : "highest") + " allowed"; noteTimer.restart();
            } else { sp.value = v; sp.note = ""; }
            text = Qt.binding(function () { return sp.displayText; });     // bound again, so + and - go on changing what is shown
        }
    }
    down.indicator: Rectangle {
        x: 1; y: 1; width: 34; height: sp.height - 2
        radius: 7; color: sp.down.pressed ? theme.inset : (sp.down.hovered ? theme.surface2 : "transparent")
        Text { anchors.centerIn: parent; text: "−"; color: theme.ink; font.pixelSize: 16 }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
    }
    up.indicator: Rectangle {
        x: sp.width - 35; y: 1; width: 34; height: sp.height - 2
        radius: 7; color: sp.up.pressed ? theme.inset : (sp.up.hovered ? theme.surface2 : "transparent")
        Text { anchors.centerIn: parent; text: "+"; color: theme.ink; font.pixelSize: 15 }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
    }
}
