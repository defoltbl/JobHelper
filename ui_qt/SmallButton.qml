// SmallButton: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Button {
    id: sb
    property bool primaryStyle: false
    implicitHeight: 26
    leftPadding: 9; rightPadding: 9
    font.pixelSize: 11; font.bold: true
    HoverHandler { cursorShape: Qt.PointingHandCursor; enabled: sb.enabled }
    scale: sb.down ? 0.95 : 1
    opacity: sb.enabled ? 1 : 0.5           // a button that cannot be pressed now looks it
    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
    background: Rectangle { radius: 7
        color: sb.primaryStyle ? (sb.hovered ? Qt.lighter(theme.accent, 1.08) : theme.accent)
                                    : (sb.hovered ? Qt.lighter(theme.surface2, 1.25) : theme.surface2)
        border.color: sb.visualFocus ? theme.accent : sb.primaryStyle ? "transparent" : (sb.hovered ? theme.steel : theme.line)
        border.width: sb.visualFocus ? 2 : 1 }          // reached with Tab: an outline shows where the keyboard is
    contentItem: Text { text: sb.text; font: sb.font
        color: sb.primaryStyle ? theme.accentInk : theme.ink
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
}
