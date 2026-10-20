// Gate: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Item {
    id: g
    property color ag: theme.steel
    property string kind: "in"            // in: a document | out: a box
    property string gtitle: "Gate"
    property string caption: ""
    property string badge: ""             // small counter on the beam
    property bool running: false
    property real flash: 0                // 0..1, a package is passing
    width: 94; height: 128
    // glow in the opening when a package passes
    Rectangle { x: 17; y: 18; width: 60; height: 68; radius: 4
        color: g.ag; opacity: 0.10 + 0.45 * g.flash; visible: g.running }
    // portal frame
    Rectangle { x: 4; y: 6; width: 86; height: 12; radius: 5; color: theme.beltDark }   // top beam
    Rectangle { x: 4; y: 6; width: 13; height: 80; radius: 5; color: theme.beltDark }    // left post
    Rectangle { x: 77; y: 6; width: 13; height: 80; radius: 5; color: theme.beltDark }   // right post
    Rectangle { x: 4; y: 6; width: 86; height: 4; radius: 2; color: g.ag }               // accent beam cap
    // light strips down the inside of both posts
    Repeater { model: [19, 72]
        Rectangle { x: modelData; y: 20; width: 3; height: 62; radius: 1.5; color: g.ag
            opacity: g.running ? 0.35 + 0.65 * g.flash : 0.18 } }
    // feet
    Rectangle { x: 1; y: 82; width: 19; height: 5; radius: 2; color: theme.steel; opacity: 0.7 }
    Rectangle { x: 74; y: 82; width: 19; height: 5; radius: 2; color: theme.steel; opacity: 0.7 }
    // beacon lamp on the beam
    Rectangle { id: lamp; x: 10; y: 11; width: 6; height: 6; radius: 3
        color: g.running ? g.ag : theme.steel
        SequentialAnimation on opacity { running: g.running; loops: Animation.Infinite
            NumberAnimation { to: 0.25; duration: 450 } NumberAnimation { to: 1; duration: 450 }
            onStopped: lamp.opacity = 1 } }
    // counter on the beam
    Rectangle { visible: g.badge !== ""; x: 90 - width - 3; y: -3; height: 17; width: Math.max(20, bTxt.implicitWidth + 10)
        radius: 8.5; color: g.ag; border.color: theme.surface; border.width: 1.5
        Text { id: bTxt; anchors.centerIn: parent; text: g.badge; color: theme.labelOn(g.ag); font.pixelSize: 11; font.bold: true } }
    // icon plate in the opening, sitting on the belt
    Rectangle { x: 26; y: 24; width: 42; height: 40; radius: 10
        color: theme.surface2; border.color: g.ag; border.width: 1.5
        scale: 1 + 0.07 * g.flash
        // document
        Item { visible: g.kind === "in"; anchors.centerIn: parent; width: 18; height: 22
            Rectangle { anchors.fill: parent; radius: 3; color: "transparent"; border.color: g.ag; border.width: 1.6 }
            Column { x: 4; y: 5; spacing: 3
                Repeater { model: [10, 7, 10, 5]
                    Rectangle { width: modelData; height: 1.8; radius: 0.9; color: g.ag } } } }
        // box
        Item { visible: g.kind === "out"; anchors.centerIn: parent; width: 22; height: 20
            Rectangle { x: 0; y: 5; width: 22; height: 15; radius: 2.5; color: "transparent"; border.color: g.ag; border.width: 1.6 }
            Rectangle { x: -1; y: 1; width: 24; height: 6; radius: 2; color: theme.surface2; border.color: g.ag; border.width: 1.6 }
            Rectangle { x: 9; y: 9; width: 4; height: 4; radius: 1; color: g.ag } }
    }
    // labels
    Text { anchors.horizontalCenter: parent.horizontalCenter; y: 92
        text: g.gtitle; color: theme.ink; font.pixelSize: 14; font.bold: true }
    Text { anchors.horizontalCenter: parent.horizontalCenter; y: 108
        text: g.caption; color: g.ag; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1 }
}
