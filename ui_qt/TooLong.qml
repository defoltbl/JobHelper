// TooLong: the red line under a box whose text is over its limit, said while the person types (the back end refuses
// such text with the same numbers; nothing is ever cut silently). The limit comes from the module that checks it.
import QtQuick

Text {
    property int length: 0
    property int most: 0
    visible: most > 0 && length > most
    wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11
    text: "That is " + length + " characters; the most is " + most + "."
}
