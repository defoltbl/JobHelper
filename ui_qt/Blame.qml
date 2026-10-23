// Blame: a window's red line and the box it is about. The window says a fault with say(text, box); the box with that
// name turns red. A message set any other way (or cleared) is about no box, so a box never stays red for a fault
// somewhere else.
import QtQuick

QtObject {
    property string text: ""
    property string box: ""
    property bool saying: false
    function say(t, b) { saying = true; box = t !== "" ? (b || "") : ""; text = t; saying = false; }
    onTextChanged: if (!saying) box = ""
}
