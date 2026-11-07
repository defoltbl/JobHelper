// Chip: one word or phrase in a row of chips (a search role, a skip word, a keyword). It is as wide as its text, but never
// wider than the row it stands in: a long one wraps onto more lines inside the window instead of being cut off (#70).
// A removable chip has a ✕ that sends remove().
import QtQuick

Rectangle {
    id: chip
    property string label: ""
    property color tone: theme.ink
    property color fill: theme.inset
    property color edge: theme.line
    property bool bold: false
    property bool removable: false
    property int padX: 8                    // the space each side of the text
    signal remove()
    readonly property int most: parent ? parent.width : 400              // the width of the row (the Flow)
    readonly property int closeRoom: removable ? closeMark.implicitWidth + 5 : 0
    radius: 12; color: fill; border.color: edge; border.width: 1
    width: Math.max(24, Math.min(chipText.implicitWidth + closeRoom + 2 * padX, most))
    height: Math.max(24, chipText.implicitHeight + 8)
    Text { id: chipText; objectName: "chipText"; x: chip.padX; anchors.verticalCenter: parent.verticalCenter
        width: chip.width - 2 * chip.padX - chip.closeRoom; wrapMode: Text.Wrap
        text: chip.label; color: chip.tone; font.pixelSize: 11; font.bold: chip.bold }
    Text { id: closeMark; visible: chip.removable; text: "✕"; color: theme.faint; font.pixelSize: 11
        anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
        MouseArea { anchors.fill: parent; anchors.margins: -4; cursorShape: Qt.PointingHandCursor; onClicked: chip.remove() } }
}
