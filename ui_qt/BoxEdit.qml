// BoxEdit: the text of a multi-line box (notes, letters, answers). It fills its frame, so a click anywhere in the frame
// puts the cursor in it, and Tab / Shift+Tab move to the next or the previous field instead of typing a tab (#69).
// Put it in the framed Rectangle; `pad` is the space between the frame and the text. In a Flickable, set its height to
// Math.max(implicitHeight, <the Flickable>.height), pad to 0 and `flick` to the Flickable: the cursor then stays in view.
import QtQuick
import "tabkeys.js" as TabKeys

TextEdit {
    id: box
    property int pad: 8
    property Flickable flick: null
    x: pad; y: pad; width: parent.width - 2 * pad
    height: Math.max(implicitHeight, parent.height - 2 * pad)
    wrapMode: TextEdit.Wrap; selectByMouse: true; activeFocusOnTab: true
    color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
    Keys.onPressed: (event) => TabKeys.moveOn(box, event)
    onCursorRectangleChanged: {             // typing or pasting below the visible part scrolls the box with the cursor
        if (!flick || flick.height <= 0) return;                // a box not laid out yet (hidden) has nothing to show
        const r = cursorRectangle;
        if (r.y < flick.contentY) flick.contentY = r.y;
        else if (r.y + r.height > flick.contentY + flick.height) flick.contentY = r.y + r.height - flick.height;
    }
}
