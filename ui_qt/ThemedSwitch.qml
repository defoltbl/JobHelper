// ThemedSwitch: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Switch {
    id: sw
    implicitWidth: 42; implicitHeight: 24; padding: 0
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    indicator: Rectangle {
        width: 42; height: 24; radius: 12
        color: sw.checked ? theme.accent : theme.inset
        border.color: sw.checked ? theme.accent : theme.line; border.width: 1
        Behavior on color { ColorAnimation { duration: 120 } }
        Rectangle {
            width: 18; height: 18; radius: 9; y: 3
            x: sw.checked ? parent.width - width - 3 : 3
            color: "#ffffff"; border.color: theme.line; border.width: sw.checked ? 0 : 1
            Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        }
    }
    contentItem: Item {}
}
