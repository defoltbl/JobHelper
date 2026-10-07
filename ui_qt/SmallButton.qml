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
    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
    background: Rectangle { radius: 7
        color: sb.primaryStyle ? (sb.hovered ? Qt.lighter(theme.accent, 1.08) : theme.accent)
                                    : (sb.hovered ? Qt.lighter(theme.surface2, 1.25) : theme.surface2)
        border.color: sb.primaryStyle ? "transparent" : (sb.hovered ? theme.steel : theme.line); border.width: 1 }
    contentItem: Text { text: sb.text; font: sb.font
        color: sb.primaryStyle ? "#ffffff" : theme.ink
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
}
