// StatusPanel: the right column: Claude usage, the last run, dates coming up, the weekly run, Options, About you and Help.
// A part of the main window, created once in Main.qml. It uses names from Main.qml (theme, win, bridge,
// the dialogs) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Rectangle {
    id: statusPanelRoot; objectName: "statusPanel"
    Layout.preferredWidth: 236; Layout.fillHeight: true
    color: theme.surface
    Rectangle { anchors.left: parent.left; height: parent.height; width: 1; color: theme.line }
    // In a short window the column scrolls, so no button at its foot is ever cut off; when it fits, nothing moves.
    Flickable {
        id: statusScroll; objectName: "statusScroll"
        anchors.fill: parent; clip: true; boundsBehavior: Flickable.StopAtBounds
        contentWidth: width; contentHeight: statusCol.height + 32
        interactive: contentHeight > height + 1
        ScrollBar.vertical: ScrollBar { policy: statusScroll.interactive ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
    ColumnLayout {
        id: statusCol
        x: 16; y: 16; width: statusScroll.width - 32
        height: Math.max(statusScroll.height - 32, implicitHeight); spacing: 12
        RowLayout { spacing: 9
            Rectangle { implicitWidth: 34; implicitHeight: 34; radius: 9; color: theme.infobg
                Text { anchors.centerIn: parent; text: "✶"; color: theme.a1; font.pixelSize: 16 } }
            ColumnLayout { spacing: 0
                Text { text: "Claude · " + (usageData.model || ""); color: theme.ink; font.pixelSize: 14; font.bold: true }
                Text { text: connData.paid_api ? "PAID API – unset the key" : "subscription · not paid API"
                    color: theme.faint; font.pixelSize: 11 } }
        }
        RowLayout {
            Layout.fillWidth: true
            Text { text: "USAGE LEFT"; color: theme.faint; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.6 }
            Item { Layout.fillWidth: true }
            Text {
                text: win.usageBusy ? "↻ checking…" : "↻ refresh"
                color: win.usageBusy ? theme.faint : theme.accent; font.pixelSize: 11; font.bold: true
                MouseArea { anchors.fill: parent; enabled: !win.usageBusy; cursorShape: Qt.PointingHandCursor
                    onClicked: { win.usageBusy = true; bridge.refreshUsage(); } }
            }
        }
        Repeater {
            model: [
                { key: "five_hour", label: "5-hour", used: usageData.five_hour_used, resets: usageData.five_hour_resets, asOf: usageData.five_hour_as_of,
                  resetPassed: usageData.five_hour_reset_passed, low: usageData.five_hour_low === true, c1: theme.a2, c2: theme.accent },
                { key: "seven_day", label: "7-day", used: usageData.seven_day_used, resets: usageData.seven_day_resets, asOf: usageData.seven_day_as_of,
                  resetPassed: usageData.seven_day_reset_passed, low: usageData.seven_day_low === true, c1: theme.a1, c2: theme.a3 }
            ]
            ColumnLayout { Layout.fillWidth: true; spacing: 5
                RowLayout { Layout.fillWidth: true
                    Text { text: modelData.label + " window"; color: theme.soft; font.pixelSize: 12 }
                    Item { Layout.fillWidth: true }
                    Text { objectName: "usageLeft_" + modelData.key; font.pixelSize: 11
                        color: modelData.used >= 100 ? theme.crit : theme.soft; font.bold: modelData.used >= 100
                        text: modelData.used === undefined || modelData.used === null ? "—" : Math.max(0, 100 - modelData.used) + "% left" } }
                // the bar is what is LEFT, as the card's title says: full when nothing is used, empty when it is used up
                Rectangle { Layout.fillWidth: true; implicitHeight: 8; radius: 4; color: theme.inset
                    Rectangle { id: bar; objectName: "usageBar_" + modelData.key; height: parent.height; radius: 4
                        visible: modelData.used !== undefined && modelData.used !== null      // not known: no fill, never "used up"
                        readonly property real share: modelData.used === undefined || modelData.used === null ? 0 : Math.max(0, 100 - modelData.used)
                        width: parent.width * Math.min(1, share / 100)
                        gradient: Gradient { orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: modelData.low ? theme.crit : modelData.c1 }      // usage.LOW_LEFT, from the back end
                            GradientStop { position: 1; color: modelData.low ? theme.warn : modelData.c2 } } } }
                // when little is left: the time it comes back, on its own line so the card keeps its width;
                // else, for a number Claude reported long ago, when that was (it reports only with an answer)
                Text { objectName: "usageResets_" + modelData.key; visible: text !== ""
                    readonly property bool resetLine: !!modelData.resets && modelData.low
                    Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; wrapMode: Text.Wrap
                    color: resetLine && modelData.used >= 100 ? theme.crit : theme.soft; font.pixelSize: 10
                    text: resetLine ? "resets " + modelData.resets
                          : modelData.resetPassed ? "reset at " + modelData.resetPassed + " · not read since"
                          : (modelData.asOf ? "as of " + modelData.asOf : "") }
            }
        }
        // last run card
        Rectangle { Layout.fillWidth: true; radius: 12; color: theme.surface2; border.color: theme.line; border.width: 1
            implicitHeight: lrCol.implicitHeight + 26
            ColumnLayout { id: lrCol; anchors.fill: parent; anchors.margins: 13; spacing: 6
                Text { text: "LAST RUN"; color: theme.faint; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.4 }
                Repeater {
                    model: [ { k: "When", v: lastRunData.when || "—" },
                             { k: "Found", v: lastRunData.found || "—" },
                             { k: "Filtered out", v: lastRunData.filtered !== undefined ? lastRunData.filtered + " · see why ›" : "after next search",
                               view: lastRunData.filtered !== undefined ? "skip" : "" },
                             { k: "Letters", v: lastRunData.letters !== undefined ? "" + lastRunData.letters : "—" },
                             { k: "CVs", v: lastRunData.cvs !== undefined ? "" + lastRunData.cvs : "—" },
                             { k: "Email scan", v: lastRunData.scan || "—" },
                             // how much mail that scan went through and how little of it was worth a question
                             { k: "Emails read", v: lastRunData.scan_detail || "", hide: !lastRunData.scan_detail },
                             { k: "You paid", v: connData.paid_api === true ? "API billing" : "subscription only" },
                             // of the last run alone (a search or an email scan, named in the label), not of everything so far
                             { k: lastRunData.cost === undefined ? "Same work via API"
                                  : (lastRunData.cost_of === "email scan" ? "Same scan via API" : "Same search via API"),
                               v: lastRunData.cost !== undefined ? "≈ $" + Number(lastRunData.cost).toFixed(2) : "after next run" } ].filter(function (row) { return !row.hide; })
                    // the value takes the space that is left and shortens itself, so a
                    // long value can never run out of the card
                    RowLayout { Layout.fillWidth: true; spacing: 8
                        Text { text: modelData.k; color: theme.soft; font.pixelSize: 12 }
                        Text { objectName: "lastRunValue"; text: modelData.v; font.pixelSize: 12; font.bold: true
                            color: modelData.view ? theme.accent : theme.ink
                            Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; wrapMode: Text.Wrap }
                        TapHandler { enabled: !!modelData.view; onTapped: win.openView(modelData.view) }
                        HoverHandler { enabled: !!modelData.view; cursorShape: Qt.PointingHandCursor } }
                }
            }
        }
        // upcoming dates (interviews, deadlines); click one to open its job
        Rectangle { objectName: "upcomingCard"; visible: win.upcomingData.length > 0
            Layout.fillWidth: true; radius: 12; color: theme.surface2; border.color: theme.a2; border.width: 1
            implicitHeight: upCol.implicitHeight + 26
            ColumnLayout { id: upCol; anchors.fill: parent; anchors.margins: 13; spacing: 7
                Text { text: "COMING UP"; color: theme.faint; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.4 }
                Repeater {
                    model: win.upcomingData
                    ColumnLayout { Layout.fillWidth: true; spacing: 0
                        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 12; font.bold: true
                            color: modelData.days <= 1 ? theme.warn : theme.ink
                            text: modelData.label.charAt(0).toUpperCase() + modelData.label.slice(1)
                                  + (modelData.time ? " · " + modelData.time : "") + " · " + modelData.kind }
                        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.soft; font.pixelSize: 11
                            text: (modelData.company || modelData.title) + "  ·  " + modelData.date }
                        TapHandler { onTapped: detailDialog.show(modelData.id) }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                    }
                }
            }
        }
        // weekly card (click to change the schedule)
        Rectangle { Layout.fillWidth: true; radius: 12; color: theme.surface2
            border.color: wkMouse.containsMouse ? theme.steel : theme.line; border.width: 1
            implicitHeight: wkCol.implicitHeight + 26
            ColumnLayout { id: wkCol; anchors.fill: parent; anchors.margins: 13; spacing: 8
                RowLayout { Layout.fillWidth: true
                    Text { text: "🗓️ Weekly run"; color: theme.ink; font.pixelSize: 12 }
                    Item { Layout.fillWidth: true }
                    Rectangle { radius: 999; implicitHeight: 22; implicitWidth: wkt.width + 16
                        color: schedData.enabled ? theme.goodbg : theme.inset
                        Text { id: wkt; anchors.centerIn: parent
                            text: schedData.label || "Off"
                            color: schedData.enabled ? theme.good : theme.faint; font.pixelSize: 11; font.bold: true } } }
                RowLayout { Layout.fillWidth: true
                    Text { text: "Model"; color: theme.soft; font.pixelSize: 12 }
                    Item { Layout.fillWidth: true }
                    Text { text: usageData.model || "—"; color: theme.ink; font.pixelSize: 12; font.bold: true } }
                Text { text: "click to change →"; color: theme.accent; font.pixelSize: 10; font.bold: true }
            }
            MouseArea { id: wkMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                onClicked: schedDialog.open() }
        }
        Item { Layout.fillHeight: true }
        PillButton { Layout.fillWidth: true; text: "Options"; glyph: "gear"; onClicked: optDialog.open() }
        PillButton { objectName: "aboutButton"; Layout.fillWidth: true; text: "About you"; glyph: "person"; onClicked: aboutDialog.show() }
        PillButton { objectName: "helpButton"; Layout.fillWidth: true; text: "Help"; glyph: "help"; onClicked: helpDialog.open() }
    }
    }
}
