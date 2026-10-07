// LimitDialog: one window of the JobHelper app, created once in Main.qml as `limitDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: limitDialog; objectName: "limitDialog"
    modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(440, win.width - 80); padding: 0
    background: Rectangle { radius: 18; color: theme.winbg; border.color: theme.warn; border.width: 1 }
    contentItem: ColumnLayout {
        spacing: 0
        Item { Layout.preferredHeight: 26 }
        // warning triangle with an exclamation mark
        Item {
            Layout.alignment: Qt.AlignHCenter; implicitWidth: 96; implicitHeight: 84
            Shape {
                anchors.fill: parent
                ShapePath { strokeColor: theme.warn; strokeWidth: 4; fillColor: theme.warnbg
                    joinStyle: ShapePath.RoundJoin; capStyle: ShapePath.RoundCap
                    startX: 48; startY: 6
                    PathLine { x: 92; y: 78 } PathLine { x: 4; y: 78 } PathLine { x: 48; y: 6 } }
            }
            Rectangle { x: 45; y: 30; width: 6; height: 26; radius: 3; color: theme.warn }
            Rectangle { x: 44.5; y: 62; width: 7; height: 7; radius: 3.5; color: theme.warn }
            SequentialAnimation on scale { running: limitDialog.visible; loops: 2
                NumberAnimation { to: 1.08; duration: 260; easing.type: Easing.OutCubic }
                NumberAnimation { to: 1.0; duration: 260; easing.type: Easing.InOutSine } }
        }
        Text { Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 10
            text: "WARNING"; color: theme.warn; font.pixelSize: 13; font.bold: true; font.letterSpacing: 3 }
        Text { objectName: "limitText"
            Layout.fillWidth: true; Layout.leftMargin: 30; Layout.rightMargin: 30; Layout.topMargin: 12
            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 14; lineHeight: 1.3
            text: "Claude's " + (limitData.window || "usage") + " limit is used up"
                  + (limitData.used ? " (" + limitData.used + "%)" : "") + ".\n"
                  + "The run is paused and everything done so far is saved.\n"
                  + (limitData.resets_at ? "It resets at " + limitData.resets_at
                        + (limitData.resets_day ? " on " + limitData.resets_day : "") + ". " : "")
                  + "The Resume button turns blue when you can continue." }
        Item { Layout.preferredHeight: 22 }
        PillButton { objectName: "limitClose"; Layout.alignment: Qt.AlignHCenter; implicitWidth: 150
            primaryStyle: true; text: "Close"; onClicked: limitDialog.close() }
        Item { Layout.preferredHeight: 24 }
    }
}
