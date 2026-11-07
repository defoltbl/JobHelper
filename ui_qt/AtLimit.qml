// AtLimit: the line under a one-line field that has stopped taking letters at its limit, so the field never goes silent
// (#70). The limit is the field's own maximumLength, which comes from the back end (win.limits).
import QtQuick

Text {
    property var field: null
    property string name: ""
    readonly property int most: field ? field.maximumLength : 0
    visible: field !== null && most > 0 && most < 32767 && field.text.length >= most      // 32767: no limit was set
    wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11
    text: name + " takes up to " + most + " characters."
}
