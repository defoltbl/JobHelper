// DialogFooter: the bottom row of a dialog with its note and buttons. One place for its margins and spacing; the
// message that shows over the windows (Main.qml's toast) finds the footer by `dialogFooter` and keeps above it.
import QtQuick
import QtQuick.Layouts

RowLayout {
    readonly property bool dialogFooter: true
    Layout.fillWidth: true; Layout.margins: 12
    spacing: 6
}
