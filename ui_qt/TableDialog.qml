// TableDialog: one window of the JobHelper app, created once in Main.qml as `tableDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: tableDialog; objectName: "tableDialog"
    modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(700, win.width - 80); height: Math.min(640, win.height - 80)
    padding: 0
    property string excelKey: ""
    property string baseTitle: ""
    property var allRows: []
    property var sorts: []                // [[key, label], ...]; empty = a plain list without the toolbar
    property var groups: []               // [{key, n}] in the order they first appear
    property string query: ""
    property string groupFilter: ""       // "" = everything (except hidden groups)
    property string sortKey: ""
    function show(title, rows, excel, sortOptions) {
        var sameView = visible && baseTitle === title;      // a refresh keeps what you were filtering
        baseTitle = title; excelKey = excel; sorts = sortOptions || [];
        for (var i = 0; i < rows.length; i++) rows[i].order = i;
        allRows = rows;
        var seen = {}, list = [];
        rows.forEach(function (r) {
            if (r.group === undefined || r.group === "") return;
            if (seen[r.group] === undefined) { seen[r.group] = list.length; list.push({ key: r.group, n: 0, hidden: r.hidden === true }); }
            list[seen[r.group]].n++;
        });
        groups = list;
        if (!sameView) { query = ""; groupFilter = ""; sortKey = ""; searchField.text = ""; sortCombo.currentIndex = 0; }
        else if (groupFilter !== "" && seen[groupFilter] === undefined) groupFilter = "";
        apply();
        if (!sameView) listView.positionViewAtBeginning();      // never reopen mid-list
        open();
    }
    function apply() {
        var q = query.trim().toLowerCase(), g = groupFilter, words = q.split(/\s+/).filter(function (w) { return w !== ""; });
        var out = allRows.filter(function (r) {
            if (g === "" ? r.hidden === true : r.group !== g) return false;
            for (var i = 0; i < words.length; i++) if ((r.hay || (r.primary + "").toLowerCase()).indexOf(words[i]) < 0) return false;
            return true;
        });
        if (sortKey === "company")
            out.sort(function (a, b) { return (a.company || "").localeCompare(b.company || "") || a.order - b.order; });
        else if (sortKey === "date")
            out.sort(function (a, b) { return (b.date || "").localeCompare(a.date || "") || a.order - b.order; });
        else out.sort(function (a, b) { return a.order - b.order; });
        listView.model = out;
        var total = allRows.filter(function (r) { return r.hidden !== true; }).length;
        titleTxt.text = sorts.length === 0 ? baseTitle
                      : (out.length === total && g === "" && q === "") ? (baseTitle + " — " + total)
                      : (baseTitle + " — " + out.length + " of " + total);
    }
    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout {
            Layout.fillWidth: true; Layout.margins: 16
            Text { id: titleTxt; color: theme.ink; font.pixelSize: 16; font.bold: true; Layout.fillWidth: true }
            SmallButton { text: "open Excel"; visible: tableDialog.excelKey !== ""; onClicked: bridge.openExcel(tableDialog.excelKey) }
            Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: tableDialog.close() } }
        }
        // search · filter · sort
        ColumnLayout {
            visible: tableDialog.sorts.length > 0
            Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 12; spacing: 8
            RowLayout { Layout.fillWidth: true; spacing: 8
                TextField { id: searchField; objectName: "searchField"; Layout.fillWidth: true; implicitHeight: 32
                    placeholderText: "Search company, role, place…"; placeholderTextColor: theme.faint
                    color: theme.ink; font.pixelSize: 12; selectByMouse: true; leftPadding: 12
                    background: Rectangle { radius: 8; color: theme.inset; border.width: 1
                        border.color: searchField.activeFocus ? theme.accent : theme.line }
                    onTextChanged: { tableDialog.query = text; tableDialog.apply(); } }
                ThemedCombo { id: sortCombo; objectName: "sortCombo"; implicitWidth: 190; plainText: true
                    model: tableDialog.sorts.map(function (o) { return o[1]; })
                    onActivated: function (i) { tableDialog.sortKey = tableDialog.sorts[i][0]; tableDialog.apply(); } }
            }
            Flow { Layout.fillWidth: true; spacing: 6; visible: tableDialog.groups.length > 1
                Repeater {
                    model: [{ key: "", n: tableDialog.allRows.filter(function (r) { return r.hidden !== true; }).length, all: true }]
                           .concat(tableDialog.groups)
                    Rectangle {
                        readonly property bool on: tableDialog.groupFilter === modelData.key
                        height: 24; radius: 12; width: gT.implicitWidth + 18
                        color: on ? theme.accent : (gMa.containsMouse ? theme.surface2 : theme.inset)
                        border.width: 1; border.color: on ? win.clearOf(theme.line) : theme.line
                        Behavior on color { ColorAnimation { duration: 140 } }
                        Text { id: gT; anchors.centerIn: parent; font.pixelSize: 11; font.bold: parent.on
                            color: parent.on ? "#ffffff" : theme.soft
                            text: (modelData.all ? "all" : modelData.key.replace(/_/g, " ")) + "  " + modelData.n }
                        MouseArea { id: gMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: { tableDialog.groupFilter = modelData.key; tableDialog.apply(); listView.positionViewAtBeginning(); } }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        ListView {
            id: listView; objectName: "listView"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            delegate: Rectangle {
                width: listView.width; implicitHeight: 54
                readonly property bool openable: !!modelData.id || !!modelData.rid
                readonly property bool heading: modelData.heading === true
                color: heading ? theme.inset : rowMa.containsMouse && openable ? theme.inset : (index % 2 ? theme.surface2 : win.clearOf(theme.surface2))
                Behavior on color { ColorAnimation { duration: 90 } }
                MouseArea { id: rowMa; anchors.fill: parent; hoverEnabled: true; enabled: parent.openable
                    cursorShape: parent.openable ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: modelData.rid ? responseDialog.show(modelData.rid) : detailDialog.show(modelData.id) }
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 10
                    Text { visible: modelData.value !== ""; text: modelData.value; color: theme.ink; font.pixelSize: 14; font.bold: true
                        Layout.preferredWidth: 28 }
                    ColumnLayout { spacing: 1; Layout.fillWidth: true
                        Text { text: modelData.primary; color: modelData.heading === true ? theme.accent : theme.ink
                            font.pixelSize: 13; font.bold: modelData.heading === true; Layout.fillWidth: true; elide: Text.ElideRight }
                        Text { visible: modelData.secondary !== ""; text: modelData.secondary; color: theme.faint; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight } }
                    Rectangle { visible: !!modelData.flag; radius: 999; implicitHeight: 20; implicitWidth: flT.width + 16
                        color: theme.warnbg
                        Text { id: flT; anchors.centerIn: parent; text: modelData.flag || ""; color: theme.warn; font.pixelSize: 11; font.bold: true } }
                    Rectangle { visible: modelData.badge !== ""; radius: 999; implicitHeight: 20; implicitWidth: bt.width + 16
                        color: win.badgeBg(modelData.badge)
                        Text { id: bt; anchors.centerIn: parent; text: modelData.badge; color: win.badgeColor(modelData.badge); font.pixelSize: 11; font.bold: true } }
                    Repeater {
                        model: modelData.actions
                        SmallButton {
                            text: modelData.label
                            primaryStyle: modelData.kind === "apply"
                            onClicked: {
                                if (modelData.kind === "apply") {
                                    bridge.applyJob(modelData.arg);
                                    ticker.text = "Moved to Applications (waiting).";
                                    tableDialog.close(); win.reloadAll();
                                } else if (modelData.kind === "restore") {
                                    var back = bridge.restoreJob(modelData.arg);
                                    ticker.text = (back && back.ok) ? "Back in New Jobs." : "Couldn't restore that job.";
                                    win.countsData = bridge.counts(); win.refreshOpenView();
                                } else if (modelData.kind === "bringback") {
                                    var bb = bridge.bringBack(modelData.arg);
                                    ticker.text = (bb && bb.ok) ? "Added to New Jobs. The next search run will score it."
                                                                : ((bb && bb.msg) || "Couldn't bring that posting back.");
                                    if (bb && bb.ok) { win.countsData = bridge.counts(); win.refreshOpenView(); }
                                } else if (modelData.kind === "skiplink") {
                                    var o = bridge.openFiltered(modelData.arg);
                                    ticker.text = (o && o.ok) ? "Opened the job posting in your browser." : "No link for this posting.";
                                } else if (modelData.kind === "url") {
                                    var r = bridge.openUrl(modelData.arg);
                                    ticker.text = (r && r.ok) ? "Opened the job posting in your browser." : "No link for this job.";
                                } else {
                                    bridge.openDoc(modelData.kind, modelData.arg);
                                }
                            }
                        }
                    }
                }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.line; opacity: 0.5 }
            }
            footer: Text { visible: listView.count > 0 && (!!listView.model[0].id || !!listView.model[0].rid)
                width: listView.width; height: 34
                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                text: listView.count > 0 && listView.model[0].rid ? "Click a row to read the whole reply."
                                                                  : "Click a row for the description, score explanation and keywords."
                color: theme.faint; font.pixelSize: 11 }
            Text { anchors.centerIn: parent; visible: listView.count === 0
                text: tableDialog.allRows.length > 0 ? "Nothing matches. Clear the search or pick another filter." : "Nothing here yet."; color: theme.faint; font.pixelSize: 13 }
        }
    }
}
