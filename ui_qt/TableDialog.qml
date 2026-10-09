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
    property bool confirmRescore: false
    property int rescoreJobs: 0
    onClosed: { confirmRescore = false; confirmStale = false; staleNote = ""; staleFailed = []; }
    // New Jobs only: jobs that still have a letter or CV from a score that is now below the limit
    property var staleRows: []
    property bool confirmStale: false
    property string staleNote: ""
    property bool staleBad: false
    property var staleFailed: []          // jobs the last move or put-back could not handle: [{title, company, why}], one line each
    property bool anyWas: false           // some row shows its earlier score: every row keeps room for it
    property var lastShelved: ({})        // the last batch moved to the backup, while it can still be put back
    readonly property int shelvedCount: (lastShelved.jobs || []).length
    function dayTime(iso) { return (iso || "").replace("T", " ").slice(0, 16); }
    function putBack() {
        confirmStale = false;
        if (win.appRunning) { staleBad = true; staleNote = "A search or scan is running. Put the documents back when it has finished."; return; }
        var r = bridge.unshelveLast(lastShelved.batch || "");
        var failed = (r && r.failed) || [];
        if (r && r.ok) {
            var msg = "Documents of " + staleWord(r.jobs) + " are back in place (" + r.files + (r.files === 1 ? " file" : " files") + ").";
            ticker.text = msg + (failed.length ? " " + staleWord(failed.length) + " could not be put back." : "");
            win.countsData = bridge.counts(); win.refreshOpenView();
            staleBad = failed.length > 0; staleNote = staleBad ? msg + " Not put back:" : "";
        } else {
            staleBad = true; staleNote = ((r && r.msg) || "Couldn't put the documents back.") + (failed.length ? " The reason for each job:" : "");
            lastShelved = bridge.lastShelved();
        }
        staleFailed = failed;
    }
    function staleWord(n) { return n + (n === 1 ? " job" : " jobs"); }
    function shelveAll() {
        if (win.appRunning) { staleBad = true; staleNote = "A search or scan is running. Move the documents when it has finished."; return; }
        if (!confirmStale) {
            staleRows = bridge.staleDocs();          // the names asked about are the ones on disk right now
            if (staleRows.length === 0) { win.refreshOpenView(); return; }
            confirmStale = true; staleNote = ""; staleBad = false; staleFailed = [];
            return;
        }
        var r = bridge.shelveAllDocs(staleRows.length);
        confirmStale = false;
        var failed = (r && r.failed) || [];
        staleFailed = failed;
        if (r && r.ok) {
            var msg = "Documents of " + staleWord(r.jobs) + " moved to the backup (" + r.files + (r.files === 1 ? " file" : " files") + ").";
            ticker.text = msg + (failed.length ? " " + staleWord(failed.length) + " could not be moved." : "");
            win.countsData = bridge.counts(); win.refreshOpenView();
            staleBad = failed.length > 0; staleNote = staleBad ? msg + " Not moved:" : "";
        } else {
            staleBad = true; staleNote = ((r && r.msg) || "Couldn't move the documents.") + (failed.length ? " The reason for each job:" : "");
            staleRows = bridge.staleDocs();
            if (r && r.changed && staleRows.length > 0) confirmStale = true;     // new names: asked again, with the new list
        }
    }
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
        anyWas = rows.some(function (r) { return !!r.was; });
        staleRows = excel === "leads" ? bridge.staleDocs() : [];
        lastShelved = excel === "leads" ? bridge.lastShelved() : ({});
        if (staleRows.length === 0) confirmStale = false;
        if (!sameView) { confirmStale = false; staleNote = ""; staleBad = false; staleFailed = []; }
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
            // New Jobs only: score every scored job again with the rules as they are now. Asked twice, it uses the limit.
            SmallButton { objectName: "rescoreAll"; visible: tableDialog.excelKey === "leads" && !win.appRunning
                text: tableDialog.confirmRescore ? "Yes, score " + tableDialog.rescoreJobs + " again" : "Score all again"
                primaryStyle: tableDialog.confirmRescore
                onClicked: {
                    if (!tableDialog.confirmRescore) {
                        var plan = bridge.rescorePlan();
                        if ((plan.jobs || 0) === 0) { ticker.text = "There are no scored new jobs to score again."; return; }
                        tableDialog.rescoreJobs = plan.jobs; tableDialog.confirmRescore = true;
                        ticker.text = "This asks Claude about " + plan.jobs + " jobs, in about " + plan.calls + (plan.calls === 1 ? " call" : " calls")
                                      + ". Only scores change; no letter is written or removed. Press again to start.";
                        return;
                    }
                    tableDialog.confirmRescore = false;
                    if (win.startRescore()) tableDialog.close();
                } }
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
                            color: parent.on ? theme.accentInk : theme.soft
                            text: (modelData.all ? "all" : modelData.key.replace(/_/g, " ")) + "  " + modelData.n }
                        MouseArea { id: gMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: { tableDialog.groupFilter = modelData.key; tableDialog.apply(); listView.positionViewAtBeginning(); } }
                    }
                }
            }
        }
        // documents left from a higher score, for all such jobs at once: asked once, with the names
        ColumnLayout {
            objectName: "staleBar"
            visible: tableDialog.excelKey === "leads" && (tableDialog.staleRows.length > 0 || tableDialog.staleNote !== "" || tableDialog.shelvedCount > 0)
            Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 12; spacing: 6
            RowLayout { Layout.fillWidth: true; spacing: 8; visible: tableDialog.staleRows.length > 0
                Text { objectName: "staleBarText"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.warn; font.pixelSize: 12
                    text: tableDialog.confirmStale
                          ? "Move the letter and CV the app wrote for " + (tableDialog.staleRows.length === 1 ? "this job" : "these " + tableDialog.staleRows.length + " jobs")
                            + " to an encrypted backup? The jobs stay in the list. A letter of your own is never moved."
                          : tableDialog.staleWord(tableDialog.staleRows.length) + (tableDialog.staleRows.length === 1 ? " has" : " have")
                            + " documents from a score that is now below your limit." }
                SmallButton { objectName: "shelveAll"; primaryStyle: tableDialog.confirmStale
                    text: tableDialog.confirmStale ? "Yes, move documents of " + tableDialog.staleWord(tableDialog.staleRows.length) : "Move them to backup"
                    onClicked: tableDialog.shelveAll() }
                SmallButton { objectName: "shelveAllCancel"; visible: tableDialog.confirmStale; text: "Cancel"
                    onClicked: { tableDialog.confirmStale = false; tableDialog.staleNote = ""; } }
            }
            Flickable { visible: tableDialog.confirmStale && tableDialog.staleRows.length > 0
                Layout.fillWidth: true; implicitHeight: Math.min(staleNames.implicitHeight, 112); contentHeight: staleNames.implicitHeight
                clip: true; boundsBehavior: Flickable.StopAtBounds; ScrollBar.vertical: ScrollBar {}
                Text { id: staleNames; objectName: "staleNames"; textFormat: Text.PlainText; width: parent.width - 12; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12; lineHeight: 1.25
                    text: tableDialog.staleRows.map(function (r) { return r.score + "   " + r.title + "  ·  " + r.company; }).join("\n") } }
            // the last batch moved to the backup can be put back for a week
            RowLayout { objectName: "undoRow"; Layout.fillWidth: true; spacing: 8; visible: tableDialog.shelvedCount > 0 && !tableDialog.confirmStale
                Text { objectName: "undoText"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                    text: "Documents of " + tableDialog.staleWord(tableDialog.shelvedCount) + " were moved to the backup on "
                          + tableDialog.dayTime(tableDialog.lastShelved.when) + "." }
                SmallButton { objectName: "putBack"; text: "Put them back"; onClicked: tableDialog.putBack() } }
            Text { objectName: "staleNote"; visible: tableDialog.staleNote !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                font.pixelSize: 12; font.bold: tableDialog.staleBad; color: tableDialog.staleBad ? theme.crit : theme.good; text: tableDialog.staleNote }
            // what could not be done, job by job, each with its own reason
            Flickable { visible: tableDialog.staleFailed.length > 0 && tableDialog.staleNote !== ""
                Layout.fillWidth: true; implicitHeight: Math.min(failedList.implicitHeight, 112); contentHeight: failedList.implicitHeight
                clip: true; boundsBehavior: Flickable.StopAtBounds; ScrollBar.vertical: ScrollBar {}
                Text { id: failedList; objectName: "staleFailed"; textFormat: Text.PlainText; width: parent.width - 12; wrapMode: Text.WordWrap
                    color: theme.crit; font.pixelSize: 12; lineHeight: 1.25
                    text: tableDialog.staleFailed.map(function (f) { return f.title + "  ·  " + f.company + ": " + f.why; }).join("\n") } }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        ListView {
            id: listView; objectName: "listView"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            delegate: Rectangle {
                width: listView.width; implicitHeight: Math.max(54, rowWords.implicitHeight + 18)     // a long title makes the row taller, it is not cut
                readonly property bool openable: !!modelData.id || !!modelData.rid
                readonly property bool heading: modelData.heading === true
                color: heading ? theme.inset : rowMa.containsMouse && openable ? theme.inset : (index % 2 ? theme.surface2 : win.clearOf(theme.surface2))
                Behavior on color { ColorAnimation { duration: 90 } }
                MouseArea { id: rowMa; anchors.fill: parent; hoverEnabled: true; enabled: parent.openable
                    cursorShape: parent.openable ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: modelData.rid ? responseDialog.show(modelData.rid) : detailDialog.show(modelData.id) }
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 10
                    ColumnLayout { visible: modelData.value !== ""; spacing: 0; Layout.preferredWidth: tableDialog.anyWas ? 42 : 28
                        Text { text: modelData.value; color: theme.ink; font.pixelSize: 14; font.bold: true }
                        // the score it had before it was scored again
                        Text { visible: !!modelData.was; text: modelData.was || ""; color: theme.faint; font.pixelSize: 10 } }
                    ColumnLayout { id: rowWords; spacing: 1; Layout.fillWidth: true
                        Text { text: modelData.primary; color: modelData.heading === true ? theme.accent : theme.ink
                            font.pixelSize: 13; font.bold: modelData.heading === true; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        Text { visible: modelData.secondary !== ""; text: modelData.secondary; color: theme.faint; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap } }
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
