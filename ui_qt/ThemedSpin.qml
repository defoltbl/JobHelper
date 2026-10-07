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
    background: Rectangle { radius: 8; color: theme.surface
        border.color: sp.activeFocus ? theme.accent : theme.line; border.width: 1 }
    contentItem: TextInput {
        id: spIn
        text: sp.displayText; font: sp.font; color: theme.ink
        selectByMouse: true; cursorVisible: sp.activeFocus
        horizontalAlignment: Qt.AlignHCenter; verticalAlignment: Qt.AlignVCenter
        readOnly: !sp.editable
        validator: IntValidator { bottom: sp.from; top: sp.to }   // can't type out of range
        inputMethodHints: Qt.ImhDigitsOnly
        // What is typed becomes the value at once, so Save never stores the old
        // number because the field still had the cursor in it.
        onTextEdited: if (acceptableInput) sp.value = sp.valueFromText(text, sp.locale)
        // clamp + re-sync the text to the valid value when editing ends
        onEditingFinished: { sp.value = sp.valueFromText(text, sp.locale); text = sp.displayText; }
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
