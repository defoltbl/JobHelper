// RowsEditor: a shared building block of the JobHelper window (used in the assistant's My details page).
// A list of rows of text fields that can grow: one row per job, one per degree. It only edits the
// ListModel it is given and says when something changed; what is wrong comes from outside (`problem`).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

ColumnLayout {
    id: ed
    property var store                     // the ListModel that is edited
    property var cols: []                  // [{key, label, most, hint}]
    property string listName: ""           // "experience": how the back end names a place in the list ("experience.1.title")
    property bool withCurrent: false       // each row has a "current" switch (a job that goes on has no end date)
    property var problem: ({})             // {field, msg} of the first thing wrong
    signal changed()
    spacing: 8
    Repeater {
        model: ed.store
        Rectangle {
            id: card
            readonly property int row: index
            readonly property bool isCurrent: ed.withCurrent && model.current === true
            readonly property string where: ed.listName + "." + index
            readonly property bool wrong: ed.problem.field === where || ("" + (ed.problem.field || "")).indexOf(where + ".") === 0
            Layout.fillWidth: true; radius: 10; color: theme.surface2
            border.width: 1; border.color: wrong ? theme.crit : theme.line
            implicitHeight: inner.implicitHeight + 20
            ColumnLayout {
                id: inner
                x: 10; y: 10; width: parent.width - 20; spacing: 6
                GridLayout { Layout.fillWidth: true; columns: width > 460 ? 2 : 1; columnSpacing: 10; rowSpacing: 6
                    Repeater {
                        model: ed.cols.filter(function (c) { return c.area !== true; })
                        ColumnLayout { Layout.fillWidth: true; Layout.preferredWidth: 100; spacing: 2
                            Text { text: modelData.label; color: theme.soft; font.pixelSize: 11; font.bold: true }
                            TextField {
                                id: cellBox
                                readonly property bool off: modelData.key === "end" && card.isCurrent
                                Layout.fillWidth: true; implicitHeight: 30; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                enabled: !off
                                placeholderText: off ? "now" : (modelData.hint || ""); placeholderTextColor: theme.faint
                                Component.onCompleted: text = ed.store.get(card.row)[modelData.key] || ""
                                onOffChanged: if (off) text = ""
                                background: Rectangle { radius: 7; color: theme.surface; border.width: 1; opacity: cellBox.enabled ? 1 : 0.55
                                    border.color: ed.problem.field === card.where + "." + modelData.key || cellBox.text.length > modelData.most ? theme.crit
                                                : (cellBox.activeFocus ? theme.accent : theme.line) }
                                onTextEdited: { ed.store.setProperty(card.row, modelData.key, text); ed.changed(); }
                            }
                            TooLong { Layout.fillWidth: true; length: cellBox.text.length; most: modelData.most }
                        }
                    }
                }
                // a column of several lines (what you did in a job): a box across the whole row that grows with its text
                Repeater {
                    model: ed.cols.filter(function (c) { return c.area === true; })
                    ColumnLayout { Layout.fillWidth: true; spacing: 2
                        Text { text: modelData.label; color: theme.soft; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                        TextArea {
                            id: areaBox
                            objectName: "rowArea_" + modelData.key
                            Layout.fillWidth: true; implicitHeight: Math.max(64, contentHeight + 16); wrapMode: TextEdit.Wrap
                            color: theme.ink; font.pixelSize: 12; selectByMouse: true
                            placeholderText: modelData.hint || ""; placeholderTextColor: theme.faint
                            Component.onCompleted: text = ed.store.get(card.row)[modelData.key] || ""
                            background: Rectangle { radius: 7; color: theme.surface; border.width: 1
                                border.color: ed.problem.field === card.where + "." + modelData.key || areaBox.text.length > modelData.most ? theme.crit
                                            : (areaBox.activeFocus ? theme.accent : theme.line) }
                            onTextChanged: if (activeFocus) { ed.store.setProperty(card.row, modelData.key, text); ed.changed(); }
                        }
                        TooLong { Layout.fillWidth: true; length: areaBox.text.length; most: modelData.most }
                    }
                }
                RowLayout { Layout.fillWidth: true; spacing: 8
                    ThemedSwitch { visible: ed.withCurrent; checked: card.isCurrent
                        onToggled: { ed.store.setProperty(card.row, "current", checked); if (checked) ed.store.setProperty(card.row, "end", ""); ed.changed(); } }
                    Text { visible: ed.withCurrent; text: "I work here now"; color: theme.ink; font.pixelSize: 12 }
                    Item { Layout.fillWidth: true }
                    SmallButton { text: "Remove"; onClicked: { ed.store.remove(card.row); ed.changed(); } }
                }
                Text { visible: card.wrong; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11; font.bold: true
                    text: ed.problem.msg || "" }
            }
        }
    }
}
