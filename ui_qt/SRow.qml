// SRow: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Item {
    property string label: ""
    property string hint: ""
    default property alias ctl: slot.data
    Layout.fillWidth: true
    implicitHeight: Math.max(hint !== "" ? 56 : 48, words.implicitHeight + 16)     // a long label or hint makes the row taller
    ColumnLayout {
        id: words
        anchors.left: parent.left; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter
        anchors.right: slot.left; anchors.rightMargin: 10; spacing: 1
        Text { text: label; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Text { visible: hint !== ""; text: hint; color: theme.faint; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
    }
    Item { id: slot; anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
        width: childrenRect.width; height: childrenRect.height }
}
