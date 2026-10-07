// StepDot: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Item {
    id: sd
    property bool ok: false
    property bool busy: false
    property string label: "1"
    implicitWidth: 26; implicitHeight: 26
    Rectangle { anchors.fill: parent; radius: 13
        color: sd.ok ? theme.goodbg : theme.inset
        border.color: sd.ok ? theme.good : theme.line; border.width: 1.5
        Behavior on color { ColorAnimation { duration: win.motion } } }
    Text { anchors.centerIn: parent; text: sd.label; visible: !sd.ok && !sd.busy
        color: theme.soft; font.pixelSize: 12; font.bold: true }
    Item { anchors.fill: parent; visible: sd.busy && !sd.ok
        RotationAnimation on rotation { running: sd.busy && !sd.ok; from: 0; to: 360; duration: 900; loops: Animation.Infinite }
        Rectangle { x: 11.5; y: 3; width: 3; height: 7; radius: 1.5; color: theme.accent } }
    Item {                                  // clip grows left→right so the tick is "drawn"
        x: 6; y: 6; height: 14; clip: true
        width: sd.ok ? 14 : 0
        Behavior on width { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
        Shape { width: 14; height: 14; visible: sd.ok
            ShapePath { strokeColor: theme.good; strokeWidth: 2.2; fillColor: "transparent"
                capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                startX: 2; startY: 7.5
                PathLine { x: 5.8; y: 11 } PathLine { x: 12; y: 3.5 } } }
    }
}
