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
    implicitHeight: 32; font.pixelSize: 12
    palette.text: theme.ink; palette.highlightedText: theme.ink
    palette.buttonText: theme.ink; palette.windowText: theme.ink; palette.base: theme.surface
    background: Rectangle { radius: 7; color: theme.surface
        border.color: cb.activeFocus ? theme.accent : theme.line; border.width: 1 }
    delegate: ItemDelegate {
        width: cb.width; height: 30
        contentItem: Text {
            text: cb.plainText ? modelData : (cb.textRole ? (modelData[cb.textRole] !== undefined ? modelData[cb.textRole] : model[cb.textRole]) : modelData)
            color: theme.ink; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; leftPadding: 8; elide: Text.ElideRight }
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
    // editable field: text colour follows the theme (also after switching it),
    // and the text can be selected with the mouse
    Binding { target: cb.contentItem; property: "color"; value: theme.ink; when: cb.editable }
    Component.onCompleted: if (editable && contentItem) {
        try { contentItem.selectByMouse = true } catch (e) {}
    }
}
