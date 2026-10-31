// NavPanel: the left column: the lists, the account chip and what the search is set to.
// A part of the main window, created once in Main.qml. It uses names from Main.qml (theme, win, bridge,
// the dialogs) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Rectangle {
    id: navPanelRoot; objectName: "navPanel"
    Layout.preferredWidth: 238; Layout.fillHeight: true
    color: theme.surface
    Rectangle { anchors.right: parent.right; height: parent.height; width: 1; color: theme.line }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 16; spacing: 6
        Text { text: "VIEWS"; color: theme.faint; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.6 }
        Repeater {
            model: [
                { k: "new", label: "New Jobs", dot: theme.a2 },
                { k: "app", label: "Applications", dot: theme.a4 },
                { k: "resp", label: "Responses", dot: theme.a5 },
                { k: "ana", label: "Analytics", dot: theme.a1 },
                { k: "ins", label: "Insights", dot: theme.a3 }
            ]
            Rectangle {
                Layout.fillWidth: true; implicitHeight: Math.max(40, navCol.implicitHeight + 10); radius: 10
                objectName: "navRow_" + modelData.k
                color: navMouse.containsMouse ? theme.surface2 : win.clearOf(theme.surface2)
                Behavior on color { ColorAnimation { duration: 90 } }
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 11; anchors.rightMargin: 11; spacing: 10
                    Rectangle { implicitWidth: 9; implicitHeight: 9; radius: 3; color: modelData.dot }
                    ColumnLayout { id: navCol; Layout.fillWidth: true; spacing: 0
                        Text { text: modelData.label; color: theme.ink; font.pixelSize: 14
                            Layout.fillWidth: true; wrapMode: Text.Wrap }
                        Text { visible: modelData.k === "app" && (countsData.duplicates || 0) > 0
                            text: (countsData.duplicates || 0) + ((countsData.duplicates || 0) === 1 ? " possible duplicate" : " possible duplicates")
                            color: theme.steel; font.pixelSize: 10; font.bold: true
                            Layout.fillWidth: true; wrapMode: Text.Wrap }
                        Text { visible: modelData.k === "app" && (countsData.followups || 0) > 0
                            text: (countsData.followups || 0) + " to follow up"
                            color: theme.warn; font.pixelSize: 10; font.bold: true
                            Layout.fillWidth: true; wrapMode: Text.Wrap }
                    }
                    Item { objectName: "navTail_" + modelData.k; implicitWidth: 46; implicitHeight: 20
                    Rectangle {
                        visible: modelData.k !== "ana" && modelData.k !== "ins"; anchors.centerIn: parent
                        radius: 999; color: theme.inset; height: 20; width: Math.max(30, ctTxt.width + 16)
                        Text { id: ctTxt; anchors.centerIn: parent; font.pixelSize: 12; font.bold: true; color: theme.soft
                            text: modelData.k === "new" ? (countsData.leads !== undefined ? countsData.leads : "—")
                                : modelData.k === "app" ? (countsData.applications !== undefined ? countsData.applications : "—")
                                : (countsData.responses !== undefined ? countsData.responses : "—") }
                    }
                    // Analytics: a small bar chart, drawn (a font's symbol for it is not recognisable at this size)
                    Item { objectName: "navIcon_ana"; visible: modelData.k === "ana"; anchors.centerIn: parent; width: 17; height: 14
                        Repeater { model: [6, 10, 14]
                            Rectangle { x: index * 6; width: 4; height: modelData; y: parent.height - height; radius: 1
                                color: navMouse.containsMouse ? theme.ink : theme.soft } }
                    }
                    // Insights: a light bulb, for what the app noticed
                    Item { objectName: "navIcon_ins"; visible: modelData.k === "ins"; anchors.centerIn: parent; width: 12; height: 16
                        readonly property color ink: navMouse.containsMouse ? theme.ink : theme.soft
                        Rectangle { width: 12; height: 12; radius: 6; color: win.clearOf(parent.ink); border.color: parent.ink; border.width: 2 }
                        Rectangle { x: 4; y: 11; width: 4; height: 2; color: parent.ink }
                        Rectangle { x: 4; y: 14; width: 4; height: 2; radius: 1; color: parent.ink } }
                    }
                }
                MouseArea { id: navMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: win.openView(modelData.k) }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line; Layout.topMargin: 8; Layout.bottomMargin: 8 }
        Text { text: "ACCOUNT"; color: theme.faint; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.6 }
        Rectangle {
            id: chip; objectName: "accountChip"
            readonly property bool allOk: connData.claude === true && (connData.cv || "") !== "" && connData.paid_api !== true
                                          && welcome.protectedOk
            // the one fault is a sign-in check with no answer: amber, not red (a paid key, a missing CV, a locked or changed
            // data file stays red, and its own words are shown)
            readonly property bool unsureOnly: connData.claude_unsure === true && connData.paid_api !== true && (connData.cv || "") !== ""
                                               && welcome.protectedOk
            Layout.fillWidth: true; implicitHeight: Math.max(56, chipCol.implicitHeight + 18); radius: 13
            color: chipMa.containsMouse ? theme.surface2 : theme.inset
            border.color: chipMa.containsMouse ? theme.steel : theme.line; border.width: 1
            scale: chipMa.pressed ? 0.97 : 1
            Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
            Behavior on color { ColorAnimation { duration: 140 } }
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 10
                Item { implicitWidth: 34; implicitHeight: 34
                    Rectangle { anchors.fill: parent; radius: 17
                        gradient: Gradient { GradientStop { position: 0; color: theme.accent }
                                             GradientStop { position: 1; color: Qt.darker(theme.accent, 1.35) } }
                        Text { anchors.centerIn: parent; color: theme.accentInk; font.pixelSize: 15; font.bold: true
                            text: connData.claude === true && connData.claude_email ? connData.claude_email.charAt(0).toUpperCase() : "?" } }
                    Rectangle { objectName: "accountDot"; width: 12; height: 12; radius: 6; x: 24; y: 24
                        color: !win.connChecked ? theme.steel : (chip.allOk ? theme.good : chip.unsureOnly ? theme.warn : theme.crit)
                        border.color: theme.surface; border.width: 2 }
                }
                ColumnLayout { id: chipCol; Layout.fillWidth: true; spacing: 0
                    Text { objectName: "accountName"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.ink; font.pixelSize: 12; font.bold: true
                        text: !win.connChecked ? "Checking…"
                            : connData.claude === true ? (connData.claude_email || "Claude account")
                            : connData.claude_unsure === true ? "Sign-in not checked" : "Not signed in" }
                    Text { objectName: "accountNote"; Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 11
                        color: !win.connChecked || chip.allOk ? theme.faint : (chip.unsureOnly ? theme.warn : theme.crit)
                        text: !win.connChecked ? "connections"
                            : connData.paid_api === true ? "Paid API key is set"
                            : chip.unsureOnly ? "Claude did not answer"
                            : connData.claude !== true && connData.claude_unsure !== true ? "Sign in to Claude"
                            : (connData.cv || "") === "" ? "Add your master CV"
                            : connData.vault === "locked" ? "Encryption key missing"
                            : welcome.changedFiles.length > 0 ? "Files changed, review"
                            : ((connData.plan ? connData.plan.charAt(0).toUpperCase() + connData.plan.slice(1) + " plan" : "Subscription")
                               + (connData.email === true ? " · email on" : " · email off")) }
                }
                Text { text: "›"; color: theme.soft; font.pixelSize: 18 }
            }
            MouseArea { id: chipMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                onClicked: welcome.openCard() }
        }
        Row { spacing: 12; Layout.topMargin: 4; Layout.leftMargin: 2
            Repeater {
                model: [ { label: "Claude", ok: connData.claude === true },
                         { label: "Email", ok: connData.email === true },
                         { label: "CV", ok: (connData.cv || "") !== "" } ]
                Row { spacing: 5
                    Rectangle { width: 7; height: 7; radius: 3.5; anchors.verticalCenter: parent.verticalCenter
                        color: !win.connChecked ? theme.steel : (modelData.ok ? theme.good : theme.crit) }
                    Text { text: modelData.label; color: theme.soft; font.pixelSize: 11 } }
            }
        }
        Item { Layout.fillHeight: true }
        Text { text: "SEARCH"; color: theme.faint; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.6 }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Repeater {
                model: [ win.cityEN(optsData.where) || "No city yet",
                         (optsData.all_languages === true) ? "All languages" : "English only" ]
                       .concat(optsData.source_names || [])        // the sources a search reads (job_sources.SourceChoice)
                       .concat([
                         (optsData.full_time_only === false) ? "Part-time too" : "Full-time only",
                         (optsData.max_age_days && optsData.max_age_days > 0) ? ("≤ " + optsData.max_age_days + " days old") : "Any date",
                         "Letters from " + (optsData.threshold !== undefined ? optsData.threshold : 50) + "+"
                       ]).filter(function (t) { return t !== ""; })
                Rectangle {
                    height: 24; radius: 12; width: chipTxt.implicitWidth + 18
                    color: chipHover.hovered ? theme.surface2 : theme.inset
                    border.color: chipHover.hovered ? theme.steel : theme.line; border.width: 1
                    Behavior on color { ColorAnimation { duration: 140 } }
                    Text { id: chipTxt; anchors.centerIn: parent; text: modelData; color: theme.soft; font.pixelSize: 11 }
                    HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: optDialog.open() }
                }
            }
        }
    }
}
