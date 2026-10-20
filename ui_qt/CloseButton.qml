// CloseButton: the ✕ at the top right of every dialog. One button for all of them: Tab reaches it, Space or Return
// presses it, it has an accessible name, and it looks the same everywhere.
import QtQuick
import QtQuick.Controls.Basic

Button {
    id: cb
    implicitWidth: 28; implicitHeight: 28
    padding: 0
    Accessible.name: "Close"
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    scale: cb.down ? 0.95 : 1
    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
    background: Rectangle { radius: 8
        color: cb.hovered ? Qt.lighter(theme.surface2, 1.25) : theme.surface2
        border.color: cb.visualFocus ? theme.accent : (cb.hovered ? theme.steel : theme.line)
        border.width: cb.visualFocus ? 2 : 1 }          // reached with Tab: an outline shows where the keyboard is
    contentItem: Text { text: "✕"; color: theme.soft; font.pixelSize: 13
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
}
