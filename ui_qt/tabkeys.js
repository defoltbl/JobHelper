// tabkeys.js: Tab in a box of several lines moves to the next field, Shift+Tab to the one before, instead of typing a
// tab character (#69). One rule for every such box (BoxEdit, the column boxes of RowsEditor). Tab with Ctrl, Alt or
// Cmd is left to the system.
.pragma library

function moveOn(item, event) {
    if (event.key !== Qt.Key_Tab && event.key !== Qt.Key_Backtab) return;
    if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) return;
    var next = item.nextItemInFocusChain(event.key === Qt.Key_Tab && !(event.modifiers & Qt.ShiftModifier));
    if (next && next !== item) next.forceActiveFocus(Qt.TabFocusReason);
    event.accepted = true;
}
