// DialogTitle: the name of a dialog in its header. One size and weight for every dialog; a long name wraps.
// Plain text: a title can hold a company's name from a posting or a mail.
import QtQuick
import QtQuick.Layouts

Text {
    Layout.fillWidth: true
    textFormat: Text.PlainText; wrapMode: Text.Wrap
    color: theme.ink; font.pixelSize: 17; font.bold: true
}
