// AutoField: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Item {
    id: af
    property var suggestions: []
    property string placeholder: ""
    property alias text: tf.text
    signal add(string value)
    signal edited()
    implicitHeight: 32; implicitWidth: 180
    TextField {
        id: tf; anchors.fill: parent
        placeholderText: af.placeholder; color: theme.ink; font.pixelSize: 12; selectByMouse: true
        background: Rectangle { radius: 7; color: theme.surface; border.width: 1
            border.color: tf.activeFocus ? theme.accent : theme.line }
        onTextEdited: { af.edited(); sugPop.refresh(); }
        onActiveFocusChanged: if (!activeFocus) sugPop.close()
        Keys.onReturnPressed: { af.add(tf.text); sugPop.close(); }
        Keys.onEnterPressed: { af.add(tf.text); sugPop.close(); }
        Keys.onDownPressed: if (sugPop.opened) sugList.incrementCurrentIndex()
    }
    Popup {
        id: sugPop
        y: tf.height + 3; x: 0; width: Math.max(tf.width, 220); padding: 1
        closePolicy: Popup.NoAutoClose
        implicitHeight: Math.min(sugList.contentHeight + 2, 190)
        background: Rectangle { radius: 8; color: theme.surface; border.color: theme.line; border.width: 1 }
        ListModel { id: sugModel }
        function refresh() {
            var q = tf.text.toLowerCase().trim();   // case-insensitive
            sugModel.clear();
            if (q.length < 1) { close(); return; }
            var n = 0;
            for (var i = 0; i < af.suggestions.length && n < 8; i++) {
                var s = af.suggestions[i];
                if (s.toLowerCase().indexOf(q) !== -1) { sugModel.append({ t: s }); n++; }
            }
            if (n > 0) open(); else close();
        }
        contentItem: ListView {
            id: sugList; clip: true; implicitHeight: contentHeight; model: sugModel
            delegate: ItemDelegate {
                width: sugList.width; height: 30
                contentItem: Text { text: t; color: theme.ink; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; leftPadding: 8 }
                background: Rectangle { color: hovered ? theme.surface2 : "transparent" }
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                onClicked: { af.add(t); sugPop.close(); }
            }
        }
    }
}
