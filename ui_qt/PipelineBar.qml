// PipelineBar: the bottom bar: the five robots as steps that follow the run.
// A part of the main window, created once in Main.qml. It uses names from Main.qml (theme, win, bridge,
// the dialogs) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Rectangle {
    id: pipelineBarRoot; objectName: "pipelineBar"
    Layout.fillWidth: true; implicitHeight: 44; color: theme.surface
    Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: theme.line }
    RowLayout {
        anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 6
        Repeater {
            model: [ { bot: a1, name: "Profiler" }, { bot: a2, name: "Scout" }, { bot: a3, name: "Scribe" },
                     { bot: a4, name: "Tracker" }, { bot: a5, name: "Postman" } ]
            Row {
                id: stepItem
                spacing: 6
                readonly property var bot: modelData.bot
                Rectangle {                      // link from the previous step, fills when that step is done
                    visible: index > 0; width: 22; height: 2; radius: 1; anchors.verticalCenter: parent.verticalCenter
                    color: theme.line
                    Rectangle { height: 2; radius: 1; color: stepItem.bot.ag
                        width: (stepItem.bot.active || stepItem.bot.done) ? 22 : 0
                        Behavior on width { NumberAnimation { duration: 360; easing.type: Easing.OutCubic } } }
                }
                Rectangle {
                    height: 26; radius: 13; width: stepRow.implicitWidth + 20
                    anchors.verticalCenter: parent.verticalCenter
                    color: stepItem.bot.active ? Qt.rgba(stepItem.bot.ag.r, stepItem.bot.ag.g, stepItem.bot.ag.b, 0.20) : "transparent"
                    border.width: 1
                    border.color: stepItem.bot.active ? stepItem.bot.ag
                                : stepItem.bot.done ? Qt.rgba(stepItem.bot.ag.r, stepItem.bot.ag.g, stepItem.bot.ag.b, 0.5) : theme.line
                    Behavior on color { ColorAnimation { duration: win.motion } }
                    Behavior on border.color { ColorAnimation { duration: win.motion } }
                    Row { id: stepRow; anchors.centerIn: parent; spacing: 6
                        Rectangle { id: stepDot; width: 8; height: 8; radius: 4; anchors.verticalCenter: parent.verticalCenter
                            color: stepItem.bot.active || stepItem.bot.done ? stepItem.bot.ag : theme.steel
                            opacity: stepItem.bot.active || stepItem.bot.done ? 1 : 0.55
                            SequentialAnimation on scale { running: stepItem.bot.active; loops: Animation.Infinite
                                NumberAnimation { to: 1.5; duration: 500 } NumberAnimation { to: 1; duration: 500 }
                                onStopped: stepDot.scale = 1 } }
                        Text { text: modelData.name; font.pixelSize: 12
                            font.bold: stepItem.bot.active
                            color: stepItem.bot.active ? theme.ink : (stepItem.bot.done ? theme.soft : theme.faint) }
                        Text {
                            visible: stepItem.bot.done && !stepItem.bot.active; text: "✓"; color: stepItem.bot.ag; font.pixelSize: 11; font.bold: true }
                    }
                }
            }
        }
        Item { Layout.fillWidth: true }
        Text { color: theme.faint; font.pixelSize: 11; wrapMode: Text.Wrap
            Layout.maximumWidth: 360; horizontalAlignment: Text.AlignRight
            text: "Applied jobs move to Applications automatically" }
    }
}
