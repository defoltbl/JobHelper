// Card: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Rectangle {
    default property alias items: col.data
    Layout.fillWidth: true
    radius: 11; color: theme.surface2; border.color: theme.line; border.width: 1
    implicitHeight: col.implicitHeight + 2
    ColumnLayout { id: col; y: 1
        anchors.left: parent.left; anchors.right: parent.right
        anchors.leftMargin: 1; anchors.rightMargin: 1; spacing: 0 }
}
