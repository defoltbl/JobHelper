// ThemedCombo: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

ComboBox {
    id: cb
    property bool plainText: false   // true = string model (no textRole)
    font.pixelSize: 12
    palette.text: theme.ink; palette.highlightedText: theme.ink
    palette.buttonText: theme.ink; palette.windowText: theme.ink; palette.base: theme.surface
    background: Rectangle { radius: 7; color: theme.surface
        border.color: cb.activeFocus ? theme.accent : theme.line; border.width: 1 }
    delegate: ItemDelegate {
        width: cb.width; height: Math.max(30, comboLine.implicitHeight + 10)
        contentItem: Text {
            id: comboLine
            text: cb.plainText ? modelData : (cb.textRole ? (modelData[cb.textRole] !== undefined ? modelData[cb.textRole] : model[cb.textRole]) : modelData)
            color: theme.ink; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; leftPadding: 8; wrapMode: Text.Wrap }
        background: Rectangle { color: (cb.highlightedIndex === index) ? theme.surface2 : "transparent" }
        highlighted: cb.highlightedIndex === index
    }
    popup: Popup {
        y: cb.height + 2; width: cb.width; padding: 1
        implicitHeight: Math.min(lv.contentHeight + 2, 240)
        background: Rectangle { radius: 8; color: theme.surface; border.color: theme.line; border.width: 1 }
        contentItem: ListView { id: lv; clip: true; implicitHeight: contentHeight
            model: cb.popup.visible ? cb.delegateModel : null; currentIndex: cb.highlightedIndex
            ScrollBar.vertical: ScrollBar {} }
    }
    // A choice too long for the box goes onto a second line and the box grows; it is never cut.
    // (An editable box keeps its one-line field, where long text scrolls as you type.)
    implicitHeight: (!editable && ownLine.createdLine) ? Math.max(32, ownLine.createdLine.implicitHeight + 12) : 32
    Component { id: wrappedLine
        Text { objectName: "comboLine"; leftPadding: 10; rightPadding: 4      // the box gives this line the width left of its arrow
            text: cb.displayText; color: theme.ink; font.pixelSize: 12
            verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap } }
    QtObject { id: ownLine; property Item createdLine: null }
    // editable field: text colour follows the theme (also after switching it),
    // and the text can be selected with the mouse
    Binding { target: cb.contentItem; property: "color"; value: theme.ink; when: cb.editable }
    Component.onCompleted: {
        if (editable && contentItem) { try { contentItem.selectByMouse = true } catch (e) {} }
        if (!editable) { ownLine.createdLine = wrappedLine.createObject(cb); contentItem = ownLine.createdLine; }
    }
}
