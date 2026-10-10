// FocusCatcher: a shared building block of the JobHelper window (used in the dialogs).
// A press on empty space ends the editing of a text field, so that its accent outline and its
// cursor go away. Put one in a dialog's background and one as the first child of each scroll
// area: it lies under everything else, lets the press pass on, and touches nothing but focus.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

MouseArea {
    // In a scroll area the content can be shorter than what is seen: the space under it counts as well.
    width: parent.width; height: Math.max(parent.height, parent.parent ? parent.parent.height : 0)
    onPressed: function (mouse) {
        var item = Window.window ? Window.window.activeFocusItem : null;
        if (item && item.cursorPosition !== undefined) item.focus = false;      // only a field that is being typed in
        mouse.accepted = false;
    }
}
