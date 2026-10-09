// PillButton: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Button {
    id: pb
    property color bg: theme.surface
    property bool primaryStyle: false
    property color tint: "transparent"   // tinted secondary style when set
    readonly property bool tinted: tint != Qt.rgba(0, 0, 0, 0)
    implicitHeight: 34
    leftPadding: 14; rightPadding: 14
    font.pixelSize: 13; font.bold: true
    HoverHandler { cursorShape: Qt.PointingHandCursor; enabled: pb.enabled }
    scale: pb.down ? 0.96 : 1
    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
    background: Rectangle {
        radius: 10
        color: pb.primaryStyle ? (pb.hovered ? Qt.lighter(theme.accent, 1.08) : theme.accent)
             : pb.tinted ? Qt.rgba(pb.tint.r, pb.tint.g, pb.tint.b, pb.hovered ? 0.28 : 0.16)
             : (pb.hovered ? theme.surface2 : pb.bg)
        border.color: pb.primaryStyle ? "transparent"
                    : pb.tinted ? Qt.rgba(pb.tint.r, pb.tint.g, pb.tint.b, 0.55)
                    : (pb.hovered ? theme.steel : theme.line)
        border.width: pb.tinted ? 1.5 : 1
        opacity: pb.enabled ? 1 : 0.5
    }
    property string glyph: ""            // "mail" draws an envelope before the label
    readonly property color fg: primaryStyle ? theme.onAccent : (tinted ? tint : theme.ink)
    contentItem: Item {
        implicitWidth: btnRow.implicitWidth; implicitHeight: btnRow.implicitHeight
        Row {
            id: btnRow; anchors.centerIn: parent; spacing: 8
            Item {                           // envelope icon, drawn so it is crisp at any size
                visible: pb.glyph === "mail"; width: 18; height: 13
                anchors.verticalCenter: parent.verticalCenter
                Rectangle { anchors.fill: parent; radius: 3; color: "transparent"; border.color: pb.fg; border.width: 1.6 }
                Shape {
                    anchors.fill: parent
                    ShapePath { strokeColor: pb.fg; strokeWidth: 1.6; fillColor: "transparent"
                        capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                        startX: 2.5; startY: 3
                        PathLine { x: 9; y: 8 } PathLine { x: 15.5; y: 3 } }
                }
            }
            Rectangle {                      // help icon: a ring with a question mark
                visible: pb.glyph === "help"; width: 16; height: 16; radius: 8
                anchors.verticalCenter: parent.verticalCenter
                color: "transparent"; border.color: pb.fg; border.width: 1.6
                Text { anchors.centerIn: parent; text: "?"; color: pb.fg; font.pixelSize: 11; font.bold: true }
            }
            Item {                           // gear icon: a ring with eight teeth
                visible: pb.glyph === "gear"; width: 16; height: 16
                anchors.verticalCenter: parent.verticalCenter
                Repeater { model: 4
                    Rectangle { x: 6.5; y: 0; width: 3; height: 16; radius: 1.2; color: pb.fg
                        rotation: index * 45; antialiasing: true } }
                Rectangle { x: 2.5; y: 2.5; width: 11; height: 11; radius: 5.5; color: pb.fg }
                Rectangle { x: 5.5; y: 5.5; width: 5; height: 5; radius: 2.5
                    color: pb.hovered ? theme.surface2 : pb.bg }
            }
            Text { text: pb.text; font: pb.font; color: pb.fg; anchors.verticalCenter: parent.verticalCenter }
        }
    }
}
