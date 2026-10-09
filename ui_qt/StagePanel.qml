// StagePanel: the middle: the buttons, the assembly line with its robots, and the status line.
// A part of the main window, created once in Main.qml. It uses names from Main.qml (theme, win, bridge,
// the dialogs) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Rectangle {
    id: stagePanelRoot; objectName: "stagePanel"
    // what the rest of the app reaches for by name
    property alias ticker: tickerText
    readonly property Item botA1: a1
    readonly property Item botA2: a2
    readonly property Item botA3: a3
    readonly property Item botA4: a4
    readonly property Item botA5: a5
    readonly property Item assistant: helper
    Layout.fillWidth: true; Layout.fillHeight: true
    color: theme.inset
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 16; spacing: 14
        // one clear line when the start-up check found something; nothing when all is well
        Rectangle { objectName: "healthBanner"; visible: win.healthData.ok === false && !win.healthHidden
            Layout.fillWidth: true; radius: 10; color: theme.critbg; border.color: theme.crit; border.width: 1
            implicitHeight: hbRow.implicitHeight + 16
            RowLayout { id: hbRow; x: 12; y: 8; width: parent.width - 24; spacing: 10
                Text { objectName: "healthText"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 12
                    text: win.healthData.message || "" }
                SmallButton { visible: (win.healthData.problems || 0) > 1; text: "Show all"; onClicked: win.showHealth() }
                SmallButton { text: "Hide"; onClicked: win.healthHidden = true }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            Text { text: "Assembly line"; color: theme.ink; font.pixelSize: 17; font.bold: true }
            Rectangle {
                visible: connData.paid_api === true
                radius: 999; color: theme.critbg; implicitHeight: 24; implicitWidth: paidTxt.width + 18
                Text { id: paidTxt; anchors.centerIn: parent; text: "Paid API key set"; color: theme.crit; font.pixelSize: 11; font.bold: true }
            }
            Item { Layout.fillWidth: true }
            // paused on Claude's limit: Resume replaces Stop. Grey (with the reason on
            // hover) until the limit resets, then blue and clickable.
            Rectangle {
                id: resumeBtn; objectName: "resumeButton"
                visible: win.paused
                implicitHeight: 34; implicitWidth: resumeRow.implicitWidth + 28; radius: 10
                // a darker blue than the robots' own: the white label needs it to read
                color: win.canResume ? (resumeMa.containsMouse ? Qt.lighter(win.resumeBlue, 1.12) : win.resumeBlue) : theme.inset
                border.width: 1; border.color: win.canResume ? win.clearOf(theme.line) : theme.line
                scale: resumeMa.pressed && win.canResume ? 0.96 : 1
                Behavior on color { ColorAnimation { duration: win.motion } }
                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                readonly property string text: "▶ Resume"
                Row { id: resumeRow; anchors.centerIn: parent; spacing: 6
                    Text { text: resumeBtn.text; font.pixelSize: 13; font.bold: true
                        color: win.canResume ? "#ffffff" : theme.faint } }
                MouseArea { id: resumeMa; anchors.fill: parent; hoverEnabled: true
                    cursorShape: win.canResume ? Qt.PointingHandCursor : Qt.ForbiddenCursor
                    onClicked: if (win.canResume) bridge.resumeRun() }
                ToolTip {
                    id: resumeTip; objectName: "resumeTip"
                    visible: resumeMa.containsMouse; delay: 120; timeout: -1
                    y: resumeBtn.height + 8; x: Math.round((resumeBtn.width - width) / 2)
                    text: win.limitWhy
                    contentItem: Text { text: resumeTip.text; color: theme.ink; font.pixelSize: 12; wrapMode: Text.WordWrap
                        width: Math.min(300, implicitWidth) }
                    background: Rectangle { radius: 9; color: theme.surface2
                        border.width: 1; border.color: win.canResume ? theme.a1 : theme.warn }
                }
            }
            SmallButton { objectName: "stopWhilePaused"; visible: win.paused; text: win.stopping ? "Stopping…" : "■ Stop"
                enabled: !win.stopping; implicitHeight: 34; onClicked: win.stopRun() }
            PillButton { objectName: "runButton"; primaryStyle: !win.appRunning; visible: !win.paused
                tint: win.appRunning ? theme.crit : "transparent"; enabled: !win.stopping
                text: win.stopping ? "Stopping…" : (win.appRunning ? "■ Stop" : "▶ Run search")
                onClicked: win.appRunning ? win.stopRun() : win.startRun() }
            PillButton { text: "Scan email"; glyph: "mail"; tint: theme.a1; enabled: !win.appRunning; onClicked: win.startScan() }
            Rectangle {
                implicitWidth: 34; implicitHeight: 34; radius: 9; color: theme.surface2; border.color: theme.line; border.width: 1
                Text { anchors.centerIn: parent; text: win.dark ? "☀" : "☾"; color: theme.soft; font.pixelSize: 15 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: win.dark = !win.dark }
            }
        }

        // factory floor
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            radius: 14; color: theme.surface; border.color: theme.line; border.width: 1; clip: true

            Item {
                id: design
                width: 1000; height: 500
                anchors.centerIn: parent
                property real beltT: 0
                scale: Math.min((parent.width - 28) / 1000, (parent.height - 28) / 500, 1.6)

                NumberAnimation on beltT { running: win.working; from: 0; to: 1; duration: 7000; loops: Animation.Infinite }

                Shape {
                    anchors.fill: parent
                    ShapePath { strokeColor: theme.beltDark; strokeWidth: 40; fillColor: "transparent"
                        capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin; PathSvg { path: win.beltPath } }
                    ShapePath { strokeColor: theme.belt; strokeWidth: 30; fillColor: "transparent"
                        capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin; PathSvg { path: win.beltPath } }
                    ShapePath { strokeColor: theme.steel; strokeWidth: 30; fillColor: "transparent"
                        capStyle: ShapePath.FlatCap; strokeStyle: ShapePath.DashLine; dashPattern: [0.4, 2.0]
                        property real doff: 0; dashOffset: doff
                        PathSvg { path: win.beltPath }
                        NumberAnimation on doff { running: win.working; from: 0; to: 4.8; duration: 550; loops: Animation.Infinite } }
                }

                // packages riding the belt
                PathInterpolator { id: pi0; progress: (design.beltT + 0.0) % 1; path: Path { PathSvg { path: win.beltPath } } }
                PathInterpolator { id: pi1; progress: (design.beltT + 0.25) % 1; path: Path { PathSvg { path: win.beltPath } } }
                PathInterpolator { id: pi2; progress: (design.beltT + 0.5) % 1; path: Path { PathSvg { path: win.beltPath } } }
                PathInterpolator { id: pi3; progress: (design.beltT + 0.75) % 1; path: Path { PathSvg { path: win.beltPath } } }
                // each package starts plain at the input gate and takes the colour
                // of the last station it passed; it fades in/out inside the gates
                Repeater {
                    model: [pi0, pi1, pi2, pi3]
                    Rectangle {
                        readonly property real p: modelData.progress
                        readonly property color tone: p > 0.88 ? theme.a5 : p > 0.744 ? theme.a4
                            : p > 0.352 ? theme.a3 : p > 0.227 ? theme.a2 : p > 0.10 ? theme.a1 : theme.accent
                        visible: win.appRunning; width: 20; height: 22; radius: 4
                        opacity: Math.max(0, Math.min(1, p * 28, (1 - p) * 28))
                        color: win.dark ? "#eef2f7" : "#ffffff"
                        border.color: tone; border.width: 1.6
                        x: modelData.x - 10; y: modelData.y - 11
                        Behavior on border.color { ColorAnimation { duration: 220 } }
                        Rectangle { x: 0; y: 0; width: parent.width; height: 5; radius: 2; color: parent.tone
                            Behavior on color { ColorAnimation { duration: 220 } } }
                        Column { x: 4; y: 8; spacing: 2.5
                            Repeater { model: [12, 8, 11]
                                Rectangle { width: modelData; height: 1.8; radius: 0.9; color: "#8b97a5" } } }
                    }
                }

                // gates at the two ends of the line (belt runs through them)
                Gate { x: 48; y: 136; ag: theme.a2; kind: "in"; gtitle: "Your CV"; caption: "INPUT"
                    running: win.working
                    flash: Math.max(0, 1 - ((design.beltT * 4) % 1) * 6) }
                Gate { x: 103; y: 366; ag: theme.a4; kind: "out"; gtitle: "Applications"; caption: "OUTPUT"
                    running: win.working
                    badge: countsData.applications !== undefined ? "" + countsData.applications : ""
                    flash: Math.max(0, (((design.beltT * 4) % 1) - 0.84) * 6) }

                // robots (hover one for its name / role / result)
                Robot { id: a1; objectName: "a1"; kind: "cv"; theme: win.appTheme; ag: win.appTheme.a1; title: "Profiler"; role: "reads your CV"; agent: "AGENT 1"; x: 190; y: 112 }
                Robot { id: a2; objectName: "a2"; kind: "search"; theme: win.appTheme; ag: win.appTheme.a2; title: "Scout"; role: "searches jobs"; agent: "AGENT 2"; x: 410; y: 112 }
                Robot { id: a3; objectName: "a3"; kind: "write"; theme: win.appTheme; ag: win.appTheme.a3; title: "Scribe"; role: "letters & CVs"; agent: "AGENT 3"; x: 630; y: 112 }
                Robot { id: a5; objectName: "a5"; kind: "mail"; theme: win.appTheme; ag: win.appTheme.a5; title: "Postman"; role: "reads replies"; agent: "AGENT 5"; x: 300; y: 342 }
                Robot { id: a4; objectName: "a4"; kind: "table"; theme: win.appTheme; ag: win.appTheme.a4; title: "Tracker"; role: "builds tables"; agent: "AGENT 4"; x: 540; y: 342 }

                // the assistant: not a station of the line, it stands at its end and helps with the forms
                AssistantBot { id: helper; objectName: "assistantBot"; theme: win.appTheme; x: 906; y: 396
                    busy: assistantDialog.busy
                    onTapped: assistantDialog.show() }
                Connections { target: welcome
                    function onShownChanged() { if (!welcome.shown) helper.greet(); } }
            }
        }

        // status bar: what is happening, which step, how far, how long
        Rectangle {
            id: statusBar
            readonly property bool busy: win.working
            readonly property bool showBar: win.appRunning || win.runResult !== ""
            readonly property color tone: win.runResult === "ok" ? theme.good
                : win.runResult === "error" ? theme.crit
                : win.paused ? theme.warn : (busy ? win.stageColor : theme.steel)
            Layout.fillWidth: true; implicitHeight: Math.max(46, ticker.implicitHeight + 22); radius: 12
            color: theme.surface; border.width: 1
            border.color: (busy || win.paused) ? Qt.rgba(tone.r, tone.g, tone.b, 0.55) : theme.line
            Behavior on border.color { ColorAnimation { duration: win.motion } }
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 10
                anchors.bottomMargin: statusBar.showBar ? 5 : 0
                Behavior on anchors.bottomMargin { NumberAnimation { duration: win.motion; easing.type: Easing.OutCubic } }
                // step pill
                Rectangle {
                    implicitHeight: 24; radius: 12; implicitWidth: pillRow.implicitWidth + 18
                    color: Qt.rgba(statusBar.tone.r, statusBar.tone.g, statusBar.tone.b, 0.16)
                    Behavior on color { ColorAnimation { duration: win.motion } }
                    Behavior on implicitWidth { NumberAnimation { duration: win.motion; easing.type: Easing.OutCubic } }
                    Row { id: pillRow; anchors.centerIn: parent; spacing: 6
                        Rectangle { id: pillDot; width: 8; height: 8; radius: 4; color: statusBar.tone; anchors.verticalCenter: parent.verticalCenter
                            SequentialAnimation on opacity { running: statusBar.busy; loops: Animation.Infinite
                                NumberAnimation { to: 0.3; duration: 600 } NumberAnimation { to: 1; duration: 600 }
                                onStopped: pillDot.opacity = 1 } }
                        Text { color: statusBar.tone; font.pixelSize: 11; font.bold: true
                            text: win.runResult === "ok" ? "Done" : win.runResult === "error" ? "Stopped"
                                : win.paused ? (win.canResume ? "Paused · ready to resume" : "Paused · limit reached")
                                : !statusBar.busy ? "Idle"
                                : win.stopping ? "Stopping"
                            : win.stageKey === "" ? "Starting"
                                : win.runMode === "search"
                                    ? ("Step " + (win.stageOrder.indexOf(win.stageKey) + 1) + " of 4 · " + win.agentInfo[win.stageKey].name)
                                    : win.agentInfo[win.stageKey].name }
                    }
                }
                Text { id: tickerText; text: "Line idle. Press Run search to start the pipeline."
                    color: theme.soft; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Text { visible: statusBar.showBar && (win.runMode === "search" || win.runProgress > 0)
                    text: Math.round(win.runProgress * 100) + "%"
                    color: statusBar.tone; font.pixelSize: 12; font.bold: true
                    horizontalAlignment: Text.AlignRight; Layout.preferredWidth: 34 }
                Text { id: clock; color: theme.faint; font.pixelSize: 11
                    property string now: ""
                    text: statusBar.showBar ? win.fmtElapsed(win.elapsed) : now
                    Timer { interval: 1000; running: true; repeat: true; triggeredOnStart: true
                        onTriggered: clock.now = Qt.formatTime(new Date(), "HH:mm:ss") } }
            }
            // progress track along the bottom edge
            Rectangle {
                id: track
                x: 12; y: parent.height - 8; width: parent.width - 24; height: 4; radius: 2
                color: theme.inset; clip: true
                opacity: statusBar.showBar ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: win.motion } }
                readonly property bool indeterminate: statusBar.busy && win.runMode !== "search" && win.stageTotal === 0
                Rectangle {                       // determinate fill
                    visible: !track.indeterminate
                    height: parent.height; radius: 2; color: statusBar.tone
                    width: parent.width * (win.runResult === "ok" ? 1 : win.runProgress)
                    Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                    Behavior on color { ColorAnimation { duration: win.motion } }
                }
                Rectangle {                       // sweep: the whole bar when indeterminate, a sheen otherwise
                    id: sweep
                    visible: statusBar.busy
                    height: parent.height; radius: 2
                    width: track.indeterminate ? parent.width * 0.28 : 46
                    color: track.indeterminate ? statusBar.tone : "#ffffff"
                    opacity: track.indeterminate ? 1 : 0.35
                    NumberAnimation on x { running: statusBar.busy; loops: Animation.Infinite
                        from: -sweep.width; to: track.width; duration: 1500; easing.type: Easing.InOutSine }
                }
            }
        }
    }
}
