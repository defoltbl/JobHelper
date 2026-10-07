// ChipFlow: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Flow {
    id: cf
    property var items: []
    property color tone: theme.soft
    property color fill: theme.inset
    Layout.fillWidth: true; spacing: 6
    Repeater { model: cf.items
        Rectangle { height: 24; radius: 12; width: cfT.implicitWidth + 18; color: cf.fill
            border.color: Qt.rgba(cf.tone.r, cf.tone.g, cf.tone.b, 0.45); border.width: 1
            Text { id: cfT; anchors.centerIn: parent; text: modelData; color: cf.tone; font.pixelSize: 11; font.bold: true } } }
}
