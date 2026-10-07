// DetailCard: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Rectangle {
    default property alias body: dcCol.data
    property string heading: ""
    Layout.fillWidth: true; radius: 12; color: theme.surface2; border.color: theme.line; border.width: 1
    implicitHeight: dcCol.implicitHeight + 24
    ColumnLayout { id: dcCol; x: 14; y: 12; width: parent.width - 28; spacing: 8
        Text { text: parent.parent.heading; visible: text !== ""; color: theme.faint; font.pixelSize: 10; font.bold: true
            font.letterSpacing: 1.4; font.capitalization: Font.AllUppercase } }
}
