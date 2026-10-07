// LetterDialog: one window of the JobHelper app, created once in Main.qml as `letterDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: letterDialog; objectName: "letterDialog"
    modal: true; anchors.centerIn: parent; closePolicy: Popup.NoAutoClose
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(760, win.width - 60); height: Math.min(760, win.height - 50)
    padding: 0
    property var meta: ({})
    property var texts: []                // the five paragraphs as edited
    property var original: []
    property int busyIndex: -1            // paragraph Claude is rewriting, -1 = none
    property string err: ""
    property var warnings: []
    property string info: ""
    readonly property bool dirty: JSON.stringify(texts) !== JSON.stringify(original)
    readonly property int words: texts.join(" ").split(/\s+/).filter(function (w) { return w !== ""; }).length
    ListModel { id: paraModel }
    function show(jobId) {
        var d = bridge.letterForEdit(jobId);
        if (!d || !d.ok) { ticker.text = (d && d.msg) ? d.msg : "This letter cannot be edited here."; return; }
        meta = d; original = d.paragraphs.slice(); texts = d.paragraphs.slice();
        paraModel.clear();
        for (var i = 0; i < texts.length; i++) paraModel.append({ body: texts[i] });
        busyIndex = -1; err = ""; warnings = []; info = ""; hintField.text = "";
        letterFlick.contentY = 0;
        open();
    }
    function setText(i, t) { var c = texts.slice(); c[i] = t; texts = c; }
    function rewrite(i) {
        if (busyIndex >= 0) return;
        err = ""; info = ""; busyIndex = i;
        bridge.rewriteParagraph(meta.id, texts, i, hintField.text);
    }
    function save() {
        err = ""; info = "";
        var r = bridge.saveLetter(meta.id, texts);
        if (!r || !r.ok) { err = (r && r.msg) ? r.msg : "The letter could not be saved."; return; }
        original = texts.slice(); warnings = r.warnings || [];
        info = warnings.length === 0 ? "Saved. The Word file and the PDF are updated."
                                     : "Saved, with the notes below. The Word file and the PDF are updated.";
        detailDialog.refresh();
    }
    Connections { target: bridge
        function onParagraphReady(res) {
            if (!letterDialog.visible || res.job_id !== letterDialog.meta.id) return;
            letterDialog.busyIndex = -1;
            if (res.ok) { paraModel.setProperty(res.index, "body", res.paragraph); letterDialog.setText(res.index, res.paragraph);
                          letterDialog.info = "Paragraph " + (res.index + 1) + " was rewritten. Read it, then Save or change it back."; }
            else letterDialog.err = "Paragraph " + (res.index + 1) + " was not rewritten: " + (res.msg || "unknown reason");
        } }
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                Text { text: "Cover letter"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                Text { Layout.fillWidth: true; elide: Text.ElideRight; color: theme.soft; font.pixelSize: 12
                    text: (letterDialog.meta.company || "") + "  ·  " + (letterDialog.meta.title_line || letterDialog.meta.title || "") } }
            Text { objectName: "letterWords"; font.pixelSize: 12; font.bold: true
                color: (letterDialog.words < (letterDialog.meta.min_words || 0) || letterDialog.words > (letterDialog.meta.max_words || 9999)) ? theme.warn : theme.soft
                text: letterDialog.words + " words" }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        Flickable {
            id: letterFlick
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentHeight: letterCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            ColumnLayout {
                id: letterCol
                x: 16; y: 14; width: letterFlick.width - 32; spacing: 12
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                    text: "Only the five paragraphs are edited. The head, date, greeting, signature, fonts and layout stay as they are." }
                Repeater {
                    model: paraModel
                    ColumnLayout { Layout.fillWidth: true; spacing: 4
                        RowLayout { Layout.fillWidth: true; spacing: 8
                            Text { text: "Paragraph " + (index + 1) + "  ·  " + ["hook", "strongest evidence", "second theme", "learning and fit", "close"][index]
                                color: theme.faint; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.0; font.capitalization: Font.AllUppercase
                                Layout.fillWidth: true }
                            Text { color: theme.faint; font.pixelSize: 11
                                text: (letterDialog.texts[index] || "").split(/\s+/).filter(function (w) { return w !== ""; }).length + " words" }
                            SmallButton { objectName: "rewrite" + index
                                text: letterDialog.busyIndex === index ? "Rewriting…" : "Rewrite this paragraph"
                                enabled: letterDialog.busyIndex < 0; onClicked: letterDialog.rewrite(index) }
                        }
                        Rectangle { Layout.fillWidth: true; radius: 9; color: theme.inset; border.width: 1
                            border.color: pEdit.activeFocus ? theme.accent : theme.line
                            implicitHeight: pEdit.implicitHeight + 20
                            opacity: letterDialog.busyIndex === index ? 0.5 : 1
                            TextEdit { id: pEdit; x: 10; y: 10; width: parent.width - 20
                                text: model.body; wrapMode: TextEdit.Wrap; selectByMouse: true
                                readOnly: letterDialog.busyIndex === index
                                color: theme.ink; font.pixelSize: 13; selectionColor: theme.accent
                                onTextChanged: if (text !== letterDialog.texts[index]) letterDialog.setText(index, text) }
                        }
                    }
                }
                RowLayout { Layout.fillWidth: true; spacing: 8
                    Text { text: "For a rewrite"; color: theme.soft; font.pixelSize: 12 }
                    TextField { id: hintField; objectName: "hintField"; Layout.fillWidth: true; implicitHeight: 30
                        placeholderText: "Optional: what should change? e.g. shorter, more about my main project"
                        placeholderTextColor: theme.faint; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                        background: Rectangle { radius: 8; color: theme.inset; border.width: 1
                            border.color: hintField.activeFocus ? theme.accent : theme.line } }
                }
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                    text: "A rewrite asks Claude once or twice and uses your limit. It follows your letter rules and your CV; nothing is saved until you press Save." }
                Text { objectName: "letterErr"; visible: letterDialog.err !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                    color: theme.crit; font.pixelSize: 12; font.bold: true; text: letterDialog.err }
                Text { objectName: "letterInfo"; visible: letterDialog.info !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                    color: theme.good; font.pixelSize: 12; font.bold: true; text: letterDialog.info }
                Repeater { model: letterDialog.warnings
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.warn; font.pixelSize: 12; text: "• " + modelData } }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
            SmallButton { text: "Open in Word"; onClicked: bridge.openDoc("letter", detailDialog.job.letter || "") }
            SmallButton { text: "Undo my changes"; enabled: letterDialog.dirty && letterDialog.busyIndex < 0
                onClicked: { letterDialog.texts = letterDialog.original.slice();
                             for (var i = 0; i < letterDialog.original.length; i++) paraModel.setProperty(i, "body", letterDialog.original[i]);
                             letterDialog.err = ""; letterDialog.info = ""; } }
            Item { Layout.fillWidth: true }
            Text { visible: letterDialog.dirty; text: "not saved"; color: theme.warn; font.pixelSize: 11; font.bold: true }
            SmallButton { text: "Close"; onClicked: letterDialog.close() }
            PillButton { objectName: "letterSave"; primaryStyle: true; text: "Save"
                enabled: letterDialog.dirty && letterDialog.busyIndex < 0; onClicked: letterDialog.save() }
        }
    }
}
