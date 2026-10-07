// StepRow: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

RowLayout {
    id: sr
    property alias ok: dot.ok
    property alias busy: dot.busy
    property alias label: dot.label
    property string title: ""
    property string sub: ""
    property color subColor: theme.soft
    property int order: 0
    default property alias actions: act.data
    Layout.fillWidth: true; spacing: 12
    opacity: Math.max(0, Math.min(1, card.appear * 2.2 - order * 0.35))
    transform: Translate { y: (1 - sr.opacity) * 10 }
    StepDot { id: dot }
    ColumnLayout { Layout.fillWidth: true; spacing: 1
        Text { text: sr.title; color: theme.ink; font.pixelSize: 14; font.bold: true }
        Text { text: sr.sub; color: sr.subColor; font.pixelSize: 12; Layout.fillWidth: true
            maximumLineCount: 3; elide: Text.ElideRight; wrapMode: Text.WordWrap } }
    Row { id: act; spacing: 6; Layout.alignment: Qt.AlignVCenter }
}
