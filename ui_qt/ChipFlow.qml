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
        Chip { label: modelData; tone: cf.tone; fill: cf.fill; bold: true; padX: 9
            edge: Qt.rgba(cf.tone.r, cf.tone.g, cf.tone.b, 0.45) } }
}
