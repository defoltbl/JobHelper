// ScheduleDialog: one window of the JobHelper app, created once in Main.qml as `schedDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: schedDialog; objectName: "schedDialog"
    modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(440, win.width - 80); padding: 0
    property bool en: true
    property int wd: 1
    property int hh: 9
    property int mm: 0
    property string schedErr: ""
    // combo index 0..6 -> Mon..Sun ; launchd weekday Sun = 0
    readonly property var wdVals: [1, 2, 3, 4, 5, 6, 0]
    // live time-range error (empty when both fields are valid)
    readonly property string timeErr: !hourField.valid ? "Hour must be between 0 and 23."
                                    : (!minField.valid ? "Minute must be between 0 and 59." : "")
    function load() {
        en = win.schedData.enabled === true;
        hh = win.schedData.hour !== undefined ? win.schedData.hour : 9;
        mm = win.schedData.minute !== undefined ? win.schedData.minute : 0;
        wd = win.schedData.weekday !== undefined ? win.schedData.weekday : 1;
        dayCombo.currentIndex = Math.max(0, wdVals.indexOf(wd));
        hourField.value = hh; minField.value = mm;
        schedErr = "";
    }
    onAboutToShow: load()      // fill + reset BEFORE the window is visible (not after the animation)
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
        MouseArea { anchors.fill: parent; onPressed: function (m) { schedSink.forceActiveFocus(); m.accepted = false; } } }
    Item { id: schedSink }
    contentItem: ColumnLayout {
        spacing: 0
        DialogHeader {
            DialogTitle { text: "🗓️  Weekly run" }
            CloseButton { onClicked: schedDialog.close() } }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        ColumnLayout {
            Layout.fillWidth: true; Layout.margins: 18; spacing: 14
            Text { text: "Automatically search jobs + scan email on a schedule (macOS)."
                color: theme.soft; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            RowLayout { Layout.fillWidth: true
                Text { text: "Enabled"; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true }
                ThemedSwitch { checked: schedDialog.en; onToggled: schedDialog.en = checked } }
            RowLayout { Layout.fillWidth: true; enabled: schedDialog.en; opacity: schedDialog.en ? 1 : 0.4
                Text { text: "Day"; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true }
                ThemedCombo { id: dayCombo; objectName: "dayCombo"; Layout.preferredWidth: 150; plainText: true
                    model: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    onActivated: schedDialog.wd = schedDialog.wdVals[currentIndex] } }
            RowLayout { Layout.fillWidth: true; enabled: schedDialog.en; opacity: schedDialog.en ? 1 : 0.4
                Text { text: "Time"; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true }
                TimeField { id: hourField; objectName: "hourField"; maxv: 23; onEdited: schedDialog.schedErr = "" }
                Text { text: ":"; color: theme.ink; font.pixelSize: 15; font.bold: true }
                TimeField { id: minField; objectName: "minField"; maxv: 59; onEdited: schedDialog.schedErr = "" } }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        DialogFooter {
            Text { Layout.fillWidth: true; visible: (schedDialog.timeErr || schedDialog.schedErr) !== ""; wrapMode: Text.WordWrap
                color: theme.crit; font.pixelSize: 12; font.bold: true; text: schedDialog.timeErr || schedDialog.schedErr }
            Item { Layout.fillWidth: (schedDialog.timeErr || schedDialog.schedErr) === "" }
            SmallButton { text: "Cancel"; onClicked: schedDialog.close() }
            PillButton { objectName: "schedSave"; primaryStyle: true; text: "Save"
                onClicked: {
                    schedDialog.schedErr = "";
                    if (!hourField.valid || !minField.valid) return;   // red error already shown; don't save
                    var r = bridge.setWeeklySchedule(schedDialog.en, schedDialog.wd, hourField.value, minField.value);
                    win.schedData = bridge.weeklySchedule();
                    if (r && r.ok) {
                        ticker.text = schedDialog.en ? ("✓ Weekly run set for " + (win.schedData.label || "")) : "✓ Weekly run turned off.";
                        schedDialog.close();
                    } else {
                        schedDialog.schedErr = (r && r.msg) ? r.msg : "Couldn't update the schedule.";
                    }
                } } }
    }
}
