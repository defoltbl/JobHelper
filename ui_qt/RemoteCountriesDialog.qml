// RemoteCountriesDialog: one window of the JobHelper app, created once in Main.qml as `remoteDialog`.
// Opened from Options ("Remote jobs" → "Add countries"): the countries whose remote jobs a search also keeps,
// next to your own (places.RemoteReach). Done gives the choice back to Options; Options' Save stores it.
// It uses names from Main.qml (theme, win, bridge and optDialog) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: remoteDialog; objectName: "remoteDialog"
    modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(460, win.width - 80); height: Math.min(620, win.height - 80)
    padding: 0

    readonly property var all: bridge ? bridge.countries() : []        // [{key, name, area}], by name
    readonly property int most: 40                                     // places.RemoteReach.MAX_COUNTRIES
    // the parts of the world to filter by: places.AREA_OF's names
    readonly property var areas: [["", "All"], ["europe", "Europe"], ["asia", "Asia"], ["middle east", "Middle East"],
                                  ["africa", "Africa"], ["north america", "North America"], ["latin america", "Latin America"],
                                  ["oceania", "Oceania"]]
    property string home: ""            // your own country's key: always included, so it is not a choice here
    property var picked: []             // the keys ticked
    property string query: ""
    property string area: ""
    property string err: ""
    readonly property var shown: all.filter(function (c) {
        var q = query.trim().toLowerCase();
        return c.key !== home && (area === "" || c.area === area) && (q === "" || c.name.toLowerCase().indexOf(q) >= 0);
    })

    function show(keys, homeKey) {
        home = (homeKey || "").toLowerCase();
        picked = (keys || []).filter(function (k) { return k !== home; });
        query = ""; area = ""; err = ""; searchField.text = "";
        countryList.positionViewAtBeginning();
        open();
    }
    function toggle(key) {
        var on = picked.indexOf(key) >= 0;
        if (!on && picked.length >= most) { err = "You can add up to " + most + " countries."; return; }
        err = "";
        // kept in the order of the list, so the chips in Options read alphabetically
        picked = all.map(function (c) { return c.key; })
                    .filter(function (k) { return k === key ? !on : picked.indexOf(k) >= 0; });
    }
    function nameOf(key) {
        for (var i = 0; i < all.length; i++) if (all[i].key === key) return all[i].name;
        return key;
    }

    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
        FocusCatcher {} }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout { Layout.fillWidth: true; Layout.margins: 16
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                Text { text: "Countries for remote jobs"; color: theme.ink; font.pixelSize: 16; font.bold: true }
                Text { objectName: "remoteHomeNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 11
                    text: (remoteDialog.home !== "" ? remoteDialog.nameOf(remoteDialog.home) + " is always included. " : "")
                          + "A search also keeps remote jobs open to the countries you tick." } }
            Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: remoteDialog.close() } } }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }

        ColumnLayout { Layout.fillWidth: true; Layout.fillHeight: true; Layout.margins: 14; spacing: 10
            TextField { id: searchField; objectName: "countrySearch"; Layout.fillWidth: true; implicitHeight: 32
                placeholderText: "Search a country…"; placeholderTextColor: theme.faint
                color: theme.ink; font.pixelSize: 12; selectByMouse: true; leftPadding: 12; maximumLength: 60
                background: Rectangle { radius: 8; color: theme.inset; border.width: 1
                    border.color: searchField.activeFocus ? theme.accent : theme.line }
                onTextChanged: remoteDialog.query = text }
            Flow { objectName: "areaChips"; Layout.fillWidth: true; spacing: 6
                Repeater { model: remoteDialog.areas
                    Rectangle {
                        readonly property bool on: remoteDialog.area === modelData[0]
                        objectName: "area_" + (modelData[0] || "all")
                        height: 26; radius: 13; width: arT.implicitWidth + 20
                        color: on ? theme.accent : (arMa.containsMouse ? theme.surface2 : theme.inset)
                        border.width: 1; border.color: on ? win.clearOf(theme.line) : theme.line
                        Behavior on color { ColorAnimation { duration: 140 } }
                        Text { id: arT; anchors.centerIn: parent; text: modelData[1]; font.pixelSize: 11; font.bold: parent.on
                            color: parent.on ? theme.accentInk : theme.soft }
                        MouseArea { id: arMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: remoteDialog.area = modelData[0] } } } }
            Rectangle { Layout.fillWidth: true; Layout.fillHeight: true; radius: 10; color: theme.surface; border.color: theme.line; border.width: 1
                clip: true
                ListView {
                    id: countryList; objectName: "countryList"; anchors.fill: parent; anchors.margins: 1; clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    model: remoteDialog.shown
                    delegate: Rectangle {
                        id: row
                        readonly property bool ticked: remoteDialog.picked.indexOf(modelData.key) >= 0
                        objectName: "country_" + modelData.key
                        width: countryList.width; height: Math.max(36, countryName.implicitHeight + 16)     // a long name wraps
                        color: rowMa.containsMouse ? theme.inset : (index % 2 ? theme.surface2 : win.clearOf(theme.surface2))
                        Behavior on color { ColorAnimation { duration: 90 } }
                        RowLayout { anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 10
                            Rectangle { implicitWidth: 18; implicitHeight: 18; radius: 5
                                color: row.ticked ? theme.accent : theme.surface
                                border.width: 1; border.color: row.ticked ? theme.accent : theme.steel
                                Text { anchors.centerIn: parent; visible: row.ticked; text: "✓"
                                    color: theme.accentInk; font.pixelSize: 12; font.bold: true } }
                            Text { id: countryName; text: modelData.name; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true
                                wrapMode: Text.WordWrap } }
                        MouseArea { id: rowMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: remoteDialog.toggle(modelData.key) } }
                }
                Text { objectName: "noCountry"; anchors.centerIn: parent; visible: remoteDialog.shown.length === 0
                    text: "No country matches “" + remoteDialog.query.trim() + "”."; color: theme.faint; font.pixelSize: 12 } }
            Text { objectName: "remoteErr"; visible: remoteDialog.err !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                text: remoteDialog.err; color: theme.crit; font.pixelSize: 11; font.bold: true }
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        RowLayout { Layout.fillWidth: true; Layout.margins: 14; spacing: 8
            Text { objectName: "pickedCount"; Layout.fillWidth: true; color: theme.soft; font.pixelSize: 12
                text: remoteDialog.picked.length === 0 ? "No country added"
                      : remoteDialog.picked.length === 1 ? "1 country added" : remoteDialog.picked.length + " countries added" }
            SmallButton { objectName: "remoteClear"; text: "Clear"; visible: remoteDialog.picked.length > 0
                onClicked: { remoteDialog.picked = []; remoteDialog.err = ""; } }
            SmallButton { text: "Cancel"; onClicked: remoteDialog.close() }
            SmallButton { id: remoteDoneBtn; objectName: "remoteDone"; text: "Done"; primaryStyle: true
                onClicked: { optDialog.pickedRemote = remoteDialog.picked.slice(); remoteDialog.close(); } } }
    }
}
