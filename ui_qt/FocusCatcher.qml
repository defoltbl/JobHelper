// FocusCatcher: a shared building block of the JobHelper window (used in the dialogs).
// A press on empty space ends the editing of a text field and lets go of a list that was chosen from, so that the
// accent outline (and a field's cursor) goes away. Put one in a dialog's background and one as the first child of each scroll
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
        // a field that is being typed in, or a list (it keeps its outline after a choice was made): nothing else
        if (item && (item.cursorPosition !== undefined || (item.popup !== undefined && item.currentIndex !== undefined))) item.focus = false;
        mouse.accepted = false;
    }
}
