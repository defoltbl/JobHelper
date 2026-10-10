// AssistantDialog: the assistant's window, created once in Main.qml as `assistantDialog`.
// Two pages: "Ask" (fill in the form that is open in Chrome) and "My details" (what the forms are filled with).
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: assistantDialog; objectName: "assistantDialog"
    modal: true; anchors.centerIn: parent
    closePolicy: (dirty || busy) ? Popup.NoAutoClose : Popup.CloseOnEscape      // Esc must not throw away edits
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(700, win.width - 60); height: Math.min(760, win.height - 50)
    padding: 0

    property string page: "ask"           // ask | details
    property bool busy: false             // a request is being worked on (Chrome, perhaps Claude)
    property string askErr: ""            // what is wrong with the request, in red under the box
    property string jobId: ""             // the job the answers are for ("" = find it from the page)
    property var jobs: []
    readonly property int maxRequest: 300
    // My details
    property bool dirty: false            // a detail was changed and not saved
    property bool confirmClose: false
    property bool detailsSaved: false     // something is saved already
    property var problem: ({})            // {field, msg} of the first thing wrong, as you type
    property string detailsNote: ""
    property int offered: 0               // fields filled from the CV and not saved yet
    // what the last answer offers to do next
    property var last: ({})               // the assistant's last answer to a fill
    property bool nextPage: false         // the form in Chrome moved on to other fields since the last fill
    property string watchSign: ""         // what the form looked like right after the fill
    property int watched: 0               // how many times it was looked at since (it stops by itself)
    property int remembered: 0            // answers of your own that are kept
    property bool confirmForget: false
    readonly property bool canOpenForm: !busy && !!last.frame
    readonly property bool canShowFiles: !busy && last.ok === true && last.wants_file === true && last.has_files === true
    readonly property bool canLearn: !busy && last.ok === true && last.can_learn === true
    property bool appliedNow: false       // Mark applied was pressed for the job of the last answer
    readonly property bool canApply: !busy && !appliedNow && last.ok === true && last.is_lead === true && (last.filled || []).length > 0

    ListModel { id: talk }                // {who: "bot" | "you", text, bad}
    ListModel { id: filledModel }         // {label, value, kind, check}
    ListModel { id: leftModel }           // {label, why}
    ListModel { id: fieldModel }          // {key, label, most, value, fromCv}

    function say(who, text, bad) {
        talk.append({ who: who, text: text, bad: bad === true });
        Qt.callLater(function () { talkFlick.contentY = Math.max(0, talkFlick.contentHeight - talkFlick.height); });
    }
    function show() {
        askErr = ""; confirmClose = false; busy = false;
        jobs = [{ id: "", label: "Find the job from the page" }].concat(bridge.assistantJobs());
        jobBox.currentIndex = 0; jobId = "";
        loadDetails();
        remembered = bridge.assistantMemory().count || 0; confirmForget = false;
        if (talk.count === 0)
            say("bot", detailsSaved ? "Hi! Open an application form in Chrome, bring its tab to the front, then ask me to fill it in."
                                    : "Hi! First tell me your details on the My details page. Then open an application form in Chrome and ask me to fill it in.");
        page = detailsSaved ? "ask" : "details";
        open();
    }
    function forJob(id) {                 // opened from a job's window: the answers are for that job
        show();
        for (var i = 0; i < jobs.length; i++) if (jobs[i].id === id) { jobBox.currentIndex = i; jobId = id; }
        if (jobId !== id) askErr = "That application is closed, so it is not in the list. Choose a job, or let me find it from the page.";
    }
    function ask(text) {
        confirmClose = false;
        if (busy) { askErr = "I am still working on the last request. Wait for the answer."; return; }
        var words = (text || "").trim();
        if (words === "") { askErr = "Write what you need, or press Fill in the form in Chrome."; return; }
        if (words.length > maxRequest) { askErr = "That is longer than " + maxRequest + " characters. Say it in a sentence."; return; }
        if (dirty) { askErr = "You changed your details and did not save them. Save them on the My details page first."; return; }
        askErr = ""; askBox.text = "";
        filledModel.clear(); leftModel.clear(); last = ({}); nextPage = false; watchSign = ""; appliedNow = false;
        say("you", words, false);
        busy = true;
        bridge.askAssistant(words, jobId);
    }
    function act(what, arg, words) {      // one of the buttons under an answer
        if (busy) { askErr = "I am still working on the last request. Wait for the answer."; return; }
        askErr = ""; confirmClose = false;
        say("you", words, false);
        busy = true;
        bridge.assistantDo(what, arg || "", last.job_id || jobId);
    }
    function markApplied() {
        if (busy || !last.job_id) return;
        var id = last.job_id, name = last.job || "this job";
        if (!bridge.applyJob(id)) { say("bot", "That job could not be moved. It may have been removed from the list.", true); return; }
        appliedNow = true;
        say("you", "Mark applied", false);
        say("bot", "Moved " + name + " to Applications, as waiting. Replies will be filed to it when you scan your email.", false);
        ticker.text = "Moved to Applications (waiting)."; win.reloadAll(); detailDialog.refresh();
    }
    function forget() {
        if (!confirmForget) { confirmForget = true; detailsNote = ""; return; }
        confirmForget = false; page = "ask";
        act("forget", "", "Forget my remembered answers");
    }
    // After a fill the form is looked at every few seconds: when it shows other fields (the next step
    // of a form with several pages), the assistant offers to fill those too. It stops after five minutes.
    Timer { id: watcher; interval: 4000; repeat: true
        running: assistantDialog.visible && !assistantDialog.busy && assistantDialog.watchSign !== "" && !assistantDialog.nextPage && assistantDialog.watched < 75
        onTriggered: { assistantDialog.watched++; bridge.watchForm(); } }
    function tryClose() {
        if (busy) { askErr = "I am still working. Wait for the answer, then close."; page = "ask"; return; }
        if (dirty && !confirmClose) {
            confirmClose = true; page = "details"; detailsNote = "";
            problem = { field: "", msg: "You changed your details and did not save them. Press Save, or Close once more to discard the change." };
            return;
        }
        dirty = false; close();
    }
    // ── My details ──
    function loadDetails() {
        var d = bridge.myDetails();
        fieldModel.clear();
        var fields = (d && d.fields) || [], shown = (d && d.details) || {}, fromCv = (d && d.from_cv) || [];
        for (var i = 0; i < fields.length; i++)
            fieldModel.append({ key: fields[i].key, label: fields[i].label, most: fields[i].most,
                                value: shown[fields[i].key] || "", fromCv: fromCv.indexOf(fields[i].key) >= 0 });
        detailsSaved = !!(d && d.saved); offered = fromCv.length;
        dirty = false; problem = ({}); detailsNote = ""; confirmClose = false;
    }
    function values() {
        var out = {};
        for (var i = 0; i < fieldModel.count; i++) out[fieldModel.get(i).key] = fieldModel.get(i).value;
        return out;
    }
    function setField(key, value) {       // what typing in a field does
        for (var i = 0; i < fieldModel.count; i++) if (fieldModel.get(i).key === key) fieldModel.setProperty(i, "value", value);
        dirty = true; detailsNote = ""; confirmClose = false;
        problem = bridge.checkMyDetails(values());
    }
    function saveDetails() {
        confirmClose = false; detailsNote = "";
        var empty = true, all = values();
        for (var k in all) if (String(all[k]).trim() !== "") empty = false;
        if (empty && !detailsSaved) { problem = { field: "first_name", msg: "Every field is empty. Fill in at least your name and email, then save." }; return; }
        var r = bridge.saveMyDetails(all);
        if (!(r && r.ok)) { problem = { field: (r && r.field) || "", msg: (r && r.msg) || "Your details could not be saved." }; return; }
        loadDetails();
        detailsNote = "Saved, encrypted on this Mac. Forms are filled in with exactly this.";
    }
    Connections { target: bridge
        function onFormWatched(res) {
            if (!res.ok || assistantDialog.busy || assistantDialog.watchSign === "" || assistantDialog.nextPage) return;
            if (assistantDialog.watchSign === "pending") { assistantDialog.watchSign = res.url + " " + res.sign; return; }
            if (res.url + " " + res.sign === assistantDialog.watchSign || res.empty < 1) return;
            assistantDialog.nextPage = true;
            assistantDialog.say("bot", "The form in Chrome shows other fields now. Shall I fill in this page too?", false);
        }
        function onAssistantReady(res) {
            if (!assistantDialog.busy) return;
            assistantDialog.busy = false;
            if (res.action === "details") assistantDialog.page = "details";
            if (res.action === "fill") assistantDialog.last = res;
            if (res.action === "learn" || res.action === "forget") assistantDialog.remembered = bridge.assistantMemory().count || 0;
            if (!res.ok) { stagePanel.assistant.shake(); assistantDialog.say("bot", res.msg || "That did not work.", true); return; }
            stagePanel.assistant.nod();
            assistantDialog.say("bot", res.say || "Done.", false);
            if (res.action === "fill") { assistantDialog.watchSign = "pending"; assistantDialog.watched = 0; bridge.watchForm(); }
            var filled = res.filled || [], left = res.left || [];
            for (var i = 0; i < filled.length; i++)
                filledModel.append({ label: filled[i].label, value: filled[i].value, kind: filled[i].kind, check: filled[i].check || "" });
            for (var j = 0; j < left.length; j++) leftModel.append({ label: left[j].label, why: left[j].why });
            if (res.job_id) detailDialog.refresh();
        } }

    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
            Rectangle { implicitWidth: 38; implicitHeight: 38; radius: 19; color: Qt.rgba(theme.a6.r, theme.a6.g, theme.a6.b, 0.18); border.color: theme.a6; border.width: 1
                Rectangle { anchors.centerIn: parent; width: 24; height: 14; radius: 7; color: "#0d141c"
                    Row { anchors.centerIn: parent; spacing: 5
                        Repeater { model: 2; Rectangle { width: 5; height: 6; radius: 2.5; color: "#ffffff" } } } } }
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                Text { text: "Assistant"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                    text: "Fills in the application form that is open in Google Chrome. You read it and send it." } }
            Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                Layout.alignment: Qt.AlignTop
                Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: assistantDialog.tryClose() } }
        }
        RowLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 10; spacing: 6
            SmallButton { objectName: "asPageAsk"; text: "Ask"; primaryStyle: assistantDialog.page === "ask"; onClicked: assistantDialog.page = "ask" }
            SmallButton { objectName: "asPageDetails"; text: assistantDialog.dirty ? "My details •" : "My details"
                primaryStyle: assistantDialog.page === "details"; onClicked: assistantDialog.page = "details" }
            Item { Layout.fillWidth: true }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }

        // ── Ask ──
        ColumnLayout { visible: assistantDialog.page === "ask"; Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            Flickable {
                id: talkFlick
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                contentHeight: talkCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                ColumnLayout {
                    id: talkCol
                    x: 16; y: 14; width: talkFlick.width - 32; spacing: 10
                    Repeater {
                        model: talk
                        Rectangle {
                            Layout.maximumWidth: talkCol.width * 0.86; Layout.preferredWidth: Math.min(talkCol.width * 0.86, line.implicitWidth + 24)
                            Layout.alignment: model.who === "you" ? Qt.AlignRight : Qt.AlignLeft
                            implicitHeight: line.implicitHeight + 18; radius: 12
                            color: model.who === "you" ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.16) : (model.bad ? theme.critbg : theme.surface2)
                            border.width: 1; border.color: model.who === "you" ? theme.accent : (model.bad ? theme.crit : theme.line)
                            Text { id: line; x: 12; y: 9; width: Math.min(implicitWidth, talkCol.width * 0.86 - 24); wrapMode: Text.Wrap
                                text: model.text; color: model.bad ? theme.crit : theme.ink; font.pixelSize: 13; font.bold: model.bad }
                        }
                    }
                    Row { visible: assistantDialog.busy; spacing: 8
                        BusyIndicator { running: assistantDialog.busy; width: 20; height: 20; palette.dark: theme.a6 }
                        Text { anchors.verticalCenter: parent.verticalCenter; color: theme.soft; font.pixelSize: 12
                            text: "Working on it…" } }
                    DetailCard { visible: filledModel.count > 0; heading: "Filled in (" + filledModel.count + ")"
                        Repeater { model: filledModel
                            ColumnLayout { Layout.fillWidth: true; spacing: 1
                                RowLayout { Layout.fillWidth: true; spacing: 6
                                    Rectangle { implicitWidth: 8; implicitHeight: 8; radius: 4; color: model.check !== "" ? theme.warn : theme.good }
                                    Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.ink; font.pixelSize: 12; font.bold: true; text: model.label } }
                                Text { Layout.fillWidth: true; Layout.leftMargin: 14; wrapMode: Text.Wrap; color: theme.soft; font.pixelSize: 12; text: model.value }
                                Text { visible: model.check !== ""; Layout.fillWidth: true; Layout.leftMargin: 14; wrapMode: Text.Wrap
                                    color: theme.warn; font.pixelSize: 11; font.bold: true; text: "Check: " + model.check } } } }
                    DetailCard { visible: leftModel.count > 0; heading: "Left for you (" + leftModel.count + ")"
                        Repeater { model: leftModel
                            ColumnLayout { Layout.fillWidth: true; spacing: 1
                                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.ink; font.pixelSize: 12; font.bold: true; text: model.label }
                                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.soft; font.pixelSize: 12; text: model.why } } } }
                    // what can be done next, offered only when it applies
                    Flow { objectName: "asNext"; Layout.fillWidth: true; spacing: 6
                        visible: assistantDialog.canOpenForm || assistantDialog.canShowFiles || assistantDialog.canLearn || assistantDialog.canApply || (assistantDialog.nextPage && !assistantDialog.busy)
                        SmallButton { objectName: "asNextPage"; visible: assistantDialog.nextPage && !assistantDialog.busy; primaryStyle: true; text: "Fill in this page too"
                            onClicked: assistantDialog.ask("Fill in the form in Chrome") }
                        SmallButton { objectName: "asOpenForm"; visible: assistantDialog.canOpenForm; primaryStyle: true; text: "Open the form in its own tab"
                            onClicked: assistantDialog.act("open_form", assistantDialog.last.frame, "Open the form in its own tab") }
                        SmallButton { objectName: "asFiles"; visible: assistantDialog.canShowFiles; text: "Show my CV and letter in Finder"
                            onClicked: assistantDialog.act("files", "", "Show my CV and letter in Finder") }
                        SmallButton { objectName: "asLearn"; visible: assistantDialog.canLearn; text: "Remember what I changed on the page"
                            onClicked: assistantDialog.act("learn", "", "Remember what I changed on the page") }
                        SmallButton { objectName: "asApply"; visible: assistantDialog.canApply; text: "Mark applied"
                            onClicked: assistantDialog.markApplied() }
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            ColumnLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 8
                RowLayout { Layout.fillWidth: true; spacing: 8
                    Text { text: "Answers are for"; color: theme.soft; font.pixelSize: 12 }
                    ThemedCombo { id: jobBox; objectName: "asJob"; Layout.fillWidth: true; enabled: !assistantDialog.busy
                        model: assistantDialog.jobs; textRole: "label"
                        onActivated: assistantDialog.jobId = assistantDialog.jobs[currentIndex] ? assistantDialog.jobs[currentIndex].id : "" } }
                RowLayout { Layout.fillWidth: true; spacing: 8
                    TextField { id: askBox; objectName: "asBox"; Layout.fillWidth: true; implicitHeight: 34
                        placeholderText: "Ask me: fill in the form in Chrome · why did this score 62?"; placeholderTextColor: theme.faint
                        color: theme.ink; font.pixelSize: 13; selectByMouse: true; enabled: !assistantDialog.busy
                        background: Rectangle { radius: 9; color: theme.surface; border.width: 1
                            border.color: assistantDialog.askErr !== "" || askBox.text.length > assistantDialog.maxRequest ? theme.crit : (askBox.activeFocus ? theme.accent : theme.line) }
                        onTextEdited: assistantDialog.askErr = ""
                        Keys.onReturnPressed: assistantDialog.ask(text)
                        Keys.onEnterPressed: assistantDialog.ask(text) }
                    SmallButton { objectName: "asSend"; implicitHeight: 34; text: "Ask"; enabled: !assistantDialog.busy; onClicked: assistantDialog.ask(askBox.text) }
                    PillButton { objectName: "asFill"; primaryStyle: true; enabled: !assistantDialog.busy
                        text: assistantDialog.busy ? "Working…" : "Fill in the form in Chrome"
                        onClicked: assistantDialog.ask("Fill in the form in Chrome") } }
                Text { objectName: "asErr"; Layout.fillWidth: true; wrapMode: Text.WordWrap
                    font.pixelSize: assistantDialog.askErr !== "" ? 12 : 11; font.bold: assistantDialog.askErr !== ""
                    color: assistantDialog.askErr !== "" || askBox.text.length > assistantDialog.maxRequest ? theme.crit : theme.faint
                    text: assistantDialog.askErr !== "" ? assistantDialog.askErr
                        : askBox.text.length > assistantDialog.maxRequest ? (askBox.text.length - assistantDialog.maxRequest) + " characters too long (the limit is " + assistantDialog.maxRequest + ")"
                        : "Only empty fields are filled, and the form is never sent: you read it and press Submit yourself. A question about a job or the app is answered by Claude." }
            }
        }

        // ── My details ──
        ColumnLayout { visible: assistantDialog.page === "details"; Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            Flickable {
                id: detailsFlick
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                contentHeight: detailsCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                ColumnLayout {
                    id: detailsCol
                    x: 16; y: 14; width: detailsFlick.width - 32; spacing: 10
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                        text: "What application forms are filled in with. Typed once, kept encrypted on this Mac. A field you leave empty is left empty in the form too."
                              + (assistantDialog.offered > 0 ? " Fields marked “from your CV” were read from your CV and are not saved yet: check them, then save." : "") }
                    RowLayout { Layout.fillWidth: true; spacing: 8; visible: assistantDialog.remembered > 0
                        Text { objectName: "asMemory"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 12
                            color: assistantDialog.confirmForget ? theme.crit : theme.soft; font.bold: assistantDialog.confirmForget
                            text: assistantDialog.confirmForget
                                ? "Forgetting removes " + assistantDialog.remembered + (assistantDialog.remembered === 1 ? " answer" : " answers") + " you wrote yourself. Press Forget them once more to go on."
                                : assistantDialog.remembered + (assistantDialog.remembered === 1 ? " answer of your own is" : " answers of your own are")
                                  + " remembered and used when another form asks the same question." }
                        SmallButton { objectName: "asForget"; text: "Forget them"; onClicked: assistantDialog.forget() } }
                    GridLayout { Layout.fillWidth: true; columns: width > 520 ? 2 : 1; columnSpacing: 12; rowSpacing: 10
                        Repeater {
                            model: fieldModel
                            ColumnLayout { id: cell; Layout.fillWidth: true; Layout.preferredWidth: 100; spacing: 3
                                readonly property bool wrong: assistantDialog.problem.field === model.key
                                RowLayout { Layout.fillWidth: true; spacing: 6
                                    Text { text: model.label; color: theme.ink; font.pixelSize: 12; font.bold: true }
                                    Text { visible: model.fromCv; text: "from your CV"; color: theme.a6; font.pixelSize: 10; font.bold: true }
                                    Item { Layout.fillWidth: true } }
                                TextField { id: box; Layout.fillWidth: true; implicitHeight: 32; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                    Component.onCompleted: text = model.value
                                    background: Rectangle { radius: 7; color: theme.surface; border.width: 1
                                        border.color: cell.wrong || box.text.length > model.most ? theme.crit : (box.activeFocus ? theme.accent : theme.line) }
                                    onTextEdited: assistantDialog.setField(model.key, text) }
                                Text { visible: cell.wrong; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11; font.bold: true
                                    text: assistantDialog.problem.msg || "" }
                            }
                        }
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
                Text { objectName: "asDetailsNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap
                    readonly property bool bad: !!assistantDialog.problem.msg
                    font.pixelSize: bad ? 12 : 11; font.bold: bad
                    color: bad ? theme.crit : (assistantDialog.detailsNote !== "" ? theme.good : theme.faint)
                    text: bad ? assistantDialog.problem.msg
                        : assistantDialog.detailsNote !== "" ? assistantDialog.detailsNote
                        : assistantDialog.dirty ? "Changed, not saved yet."
                        : assistantDialog.detailsSaved ? "Saved. The right to work and your start date are under Options > About you."
                        : "Nothing is saved yet." }
                SmallButton { objectName: "asClose"; text: "Close"; onClicked: assistantDialog.tryClose() }
                PillButton { objectName: "asSave"; primaryStyle: true; text: "Save"; onClicked: assistantDialog.saveDetails() }
            }
        }
    }
}
