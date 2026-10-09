// StatusPanel: the right column: Claude usage, the last run, dates coming up, the weekly run, Options and Help.
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
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 16; spacing: 16
        RowLayout { spacing: 9
            Rectangle { implicitWidth: 34; implicitHeight: 34; radius: 9; color: theme.infobg
                Text { anchors.centerIn: parent; text: "✶"; color: theme.a1; font.pixelSize: 16 } }
            ColumnLayout { spacing: 0
                Text { text: "Claude · " + (usageData.model || ""); color: theme.ink; font.pixelSize: 14; font.bold: true }
                Text { text: connData.paid_api ? "PAID API — unset the key" : "subscription · not paid API"
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
                { key: "five_hour", label: "5-hour", used: usageData.five_hour_used, resets: usageData.five_hour_resets, c1: theme.a2, c2: theme.accent },
                { key: "seven_day", label: "7-day", used: usageData.seven_day_used, resets: usageData.seven_day_resets, c1: theme.a1, c2: theme.a3 }
            ]
            ColumnLayout { Layout.fillWidth: true; spacing: 5
                RowLayout { Layout.fillWidth: true
                    Text { text: modelData.label + " window"; color: theme.soft; font.pixelSize: 12 }
                    Item { Layout.fillWidth: true }
                    Text { objectName: "usageLeft_" + modelData.key; font.pixelSize: 11
                        color: modelData.used >= 100 ? theme.crit : theme.soft; font.bold: modelData.used >= 100
                        text: modelData.used === undefined || modelData.used === null ? "—"
                              : (100 - modelData.used) + "% left" + (modelData.resets && modelData.used >= 80 ? " · resets " + modelData.resets : "") } }
                Rectangle { Layout.fillWidth: true; implicitHeight: 8; radius: 4; color: theme.inset
                    Rectangle { height: parent.height; radius: 4
                        width: parent.width * ((modelData.used === undefined || modelData.used === null ? 0 : modelData.used) / 100)
                        gradient: Gradient { orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: modelData.c1 } GradientStop { position: 1; color: modelData.c2 } } } }
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
                             { k: "You paid", v: connData.paid_api === true ? "API billing" : "your subscription only" },
                             // of the last run alone (a search or an email scan), not of everything so far
                             { k: "Same work via API", v: lastRunData.cost !== undefined
                                 ? "≈ $" + Number(lastRunData.cost).toFixed(2) + (lastRunData.cost_of ? " · " + lastRunData.cost_of : "")
                                 : "after next run" } ]
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
        PillButton { objectName: "helpButton"; Layout.fillWidth: true; text: "Help"; glyph: "help"; onClicked: helpDialog.open() }
    }
}
