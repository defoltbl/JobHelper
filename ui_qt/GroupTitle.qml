// GroupTitle: a shared building block of the JobHelper window (used from Main.qml and the dialogs).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Text {
    Layout.leftMargin: 6; Layout.topMargin: 4; Layout.bottomMargin: 2
    color: theme.faint; font.pixelSize: 11; font.bold: true; font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
}
