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
    modal: true; anchors.centerIn: parent
    closePolicy: Popup.NoAutoClose        // Esc goes through tryClose, so a change is never thrown away unasked
    Shortcut { sequence: "Escape"; enabled: win.onTop(schedDialog); onActivated: schedDialog.tryClose() }
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
    property bool confirmClose: false
    readonly property string footerText: confirmClose ? schedErr : (timeErr || schedErr)
    property string loaded: ""            // the weekly run as the window opened, to tell whether it changed
    function snapshot() { return JSON.stringify([en, wd, hourField.empty ? "" : hourField.value, minField.empty ? "" : minField.value]); }
    function tryClose() {                 // the ✕, Cancel and Esc: ask once before a change is thrown away
        if (snapshot() !== loaded && !confirmClose) {
            confirmClose = true;
            schedErr = "You changed the weekly run and did not save it. Press Save, or close once more to discard the change.";
            return;
        }
        close();
    }
    function changed() { confirmClose = false; schedErr = ""; }
    onClosed: confirmClose = false
    // combo index 0..6 -> Mon..Sun ; launchd weekday Sun = 0
    readonly property var wdVals: [1, 2, 3, 4, 5, 6, 0]
    // live time-range error (empty when both fields are valid, or when the weekly run is off and has no time)
    readonly property var hours: win.limits.schedule.hour        // the ranges schedule.write_schedule accepts
    readonly property var minutes: win.limits.schedule.minute
    readonly property string timeErr: !en ? ""
                                    : hourField.empty ? "Enter the hour, " + hours.join(" to ") + "."
                                    : !hourField.valid ? "Hour must be between " + hours.join(" and ") + "."
                                    : minField.empty ? "Enter the minute, " + minutes.join(" to ") + "."
                                    : (!minField.valid ? "Minute must be between " + minutes.join(" and ") + "." : "")
    function load() {
        en = win.schedData.enabled === true;
        hh = win.schedData.hour !== undefined ? win.schedData.hour : 9;
        mm = win.schedData.minute !== undefined ? win.schedData.minute : 0;
        wd = win.schedData.weekday !== undefined ? win.schedData.weekday : 1;
        dayCombo.currentIndex = Math.max(0, wdVals.indexOf(wd));
        hourField.reset(hh); minField.reset(mm);
        schedErr = ""; confirmClose = false;
        loaded = snapshot();
    }
    onAboutToShow: load()      // fill + reset BEFORE the window is visible (not after the animation)
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
        MouseArea { anchors.fill: parent; onPressed: function (m) { schedSink.forceActiveFocus(); m.accepted = false; } } }
    Item { id: schedSink }
    contentItem: ColumnLayout {
        spacing: 0
        DialogHeader {
            DialogTitle { text: "🗓️  Weekly run" }
            CloseButton { onClicked: schedDialog.tryClose() } }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        ColumnLayout {
            Layout.fillWidth: true; Layout.margins: 18; spacing: 14
            Text { text: "Automatically search jobs + scan email on a schedule (macOS)."
                color: theme.soft; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            RowLayout { Layout.fillWidth: true
                Text { text: "Enabled"; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true }
                ThemedSwitch { objectName: "schedSwitch"; checked: schedDialog.en; onToggled: { schedDialog.en = checked; schedDialog.changed(); } } }
            RowLayout { Layout.fillWidth: true; enabled: schedDialog.en; opacity: schedDialog.en ? 1 : 0.4
                Text { text: "Day"; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true }
                ThemedCombo { id: dayCombo; objectName: "dayCombo"; Layout.preferredWidth: 150; plainText: true
                    model: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    onActivated: { schedDialog.wd = schedDialog.wdVals[currentIndex]; schedDialog.changed(); } } }
            RowLayout { Layout.fillWidth: true; enabled: schedDialog.en; opacity: schedDialog.en ? 1 : 0.4
                Text { text: "Time"; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true }
                TimeField { id: hourField; objectName: "hourField"; maxv: schedDialog.hours[1]; onEdited: schedDialog.changed() }
                Text { text: ":"; color: theme.ink; font.pixelSize: 15; font.bold: true }
                TimeField { id: minField; objectName: "minField"; maxv: schedDialog.minutes[1]; onEdited: schedDialog.changed() } }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        DialogFooter {
            // the close question first: a wrong time must not hide it before the second Esc discards the change
            Text { Layout.fillWidth: true; visible: schedDialog.footerText !== ""; wrapMode: Text.WordWrap
                color: theme.crit; font.pixelSize: 12; font.bold: true; text: schedDialog.footerText }
            Item { Layout.fillWidth: schedDialog.footerText === "" }
            SmallButton { id: schedCancelBtn; text: schedDialog.confirmClose ? "Discard changes" : "Cancel"; onClicked: schedDialog.tryClose() }
            PillButton { id: schedSaveBtn; objectName: "schedSave"; primaryStyle: true; text: "Save"
                onClicked: {
                    schedDialog.schedErr = ""; schedDialog.confirmClose = false;
                    if (schedDialog.timeErr !== "") return;   // red error already shown; don't save
                    // switched off: the time does not matter, so a wrong one never stops it (the saved one is sent)
                    var r = bridge.setWeeklySchedule(schedDialog.en, schedDialog.wd, schedDialog.en ? hourField.value : schedDialog.hh,
                                                     schedDialog.en ? minField.value : schedDialog.mm);
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
