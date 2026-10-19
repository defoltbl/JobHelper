// AboutYouDialog: one window of the JobHelper app, created once in Main.qml as `aboutDialog`.
// The few facts about you that the app may state besides your CV: the salary you ask for, your right to work, when you
// can start, and what you really did in each job. What the app says about them (the date a form gets, the usual answers,
// its own salary estimate, a box for each job of My details) comes from the back end (about_you.AboutYou).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: aboutDialog; objectName: "aboutDialog"
    modal: true; anchors.centerIn: parent
    closePolicy: Popup.NoAutoClose        // Esc goes through tryClose, so changes are never thrown away unasked
    Shortcut { sequence: "Escape"; enabled: aboutDialog.visible; onActivated: aboutDialog.tryClose() }
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
    Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
    width: Math.min(580, win.width - 80)
    height: Math.min(780, win.height - 80)
    padding: 0

    property var info: ({})               // what the back end sends: values, right_choices, start, estimates, boxes, …
    property var myLetters: ({})
    property string err: ""
    property string payErr: ""
    property bool confirmClose: false
    property string loaded: ""            // what was there when the window opened, to know whether anything changed
    property var start: ({ ok: true, text: "" })
    readonly property int notesMax: info.max_notes || win.limits.experience_notes
    property int notesTick: 0             // a box's text changed: count again
    // how long the notes are as the app reads them, job names included: the back end counts (WorkNotes.size), so the
    // count here and the check when saving always agree
    readonly property int notesSize: { notesTick; boxModel.count; return bridge.workNotesSize(collect().about_jobs, generalField.text.trim()); }
    ListModel { id: payModel }            // a figure of its own for some kinds of role: { role, amount }
    ListModel { id: boxModel }            // a note for each job: { job, notes, earlier }

    function show() { open(); }
    function load() {
        info = bridge.aboutYou();
        myLetters = bridge.myLetters();
        salarySpin.value = info.salary_target || 0;
        var cur = info.currencies || ["CZK"];
        currencyCombo.model = cur;
        currencyCombo.currentIndex = Math.max(0, cur.indexOf(info.salary_currency || "CZK"));
        payModel.clear();
        (info.salary_by_role || []).forEach(function (e) { payModel.append({ role: String(e.role), amount: Number(e.amount) }); });
        payRole.text = ""; payAmount.value = 0;
        rightField.text = info.about_right_to_work || "";
        startField.text = info.about_start || "";
        start = info.start || ({ ok: true, text: "" });
        boxModel.clear();
        (info.boxes || []).forEach(function (b) { boxModel.append({ job: String(b.job), notes: String(b.notes || ""), earlier: b.earlier === true }); });
        generalField.text = info.general || "";
        err = ""; payErr = ""; confirmClose = false;
        loaded = JSON.stringify(collect());
        aboutSink.forceActiveFocus();
        if (aboutScroll && aboutScroll.contentItem) { aboutScroll.contentItem.cancelFlick(); aboutScroll.contentItem.contentY = 0; }
    }
    onAboutToShow: load()
    onClosed: { confirmClose = false; loaded = ""; }

    function collect() {                  // what Save stores: only the About you facts
        var pay = [], jobs = [];
        for (var i = 0; i < payModel.count; i++) pay.push({ role: payModel.get(i).role.trim(), amount: payModel.get(i).amount });
        for (var j = 0; j < boxModel.count; j++) {
            var b = boxModel.get(j), text = String(b.notes || "").trim();
            if (text !== "") jobs.push({ job: b.job, notes: text });
        }
        return { salary_target: salarySpin.value, salary_currency: currencyCombo.currentText, salary_by_role: pay,
                 about_right_to_work: rightField.text.trim(), about_start: startField.text.trim(),
                 about_experience: generalField.text.trim(), about_jobs: jobs };
    }
    function changed() { return loaded !== "" && JSON.stringify(collect()) !== loaded; }
    function tryClose() {                 // the ✕ and the Esc key: ask once before throwing changes away
        if (changed() && !confirmClose) {
            confirmClose = true;
            err = "You changed About you and did not save. Press Save, or close once more to discard the changes.";
            return;
        }
        close();
    }
    function payRoles(upTo) { var out = []; for (var i = 0; i < upTo; i++) out.push(payModel.get(i).role); return out; }
    function addPay() {                   // the back end's rule for one line (OptionsService.pay_problem), with its words
        var role = payRole.text.trim();
        payErr = bridge.payProblem(role, payAmount.value, payRoles(payModel.count));
        if (payErr !== "") return;
        payModel.append({ role: role, amount: payAmount.value });
        payRole.text = ""; payAmount.value = 0;
    }
    function problem() {                  // '' or what must be put right before saving, in the window's own words
        if (payRole.text.trim() !== "") return "“" + payRole.text.trim().substring(0, 40) + "” is typed under “A different figure for” but not added. Press Add, or empty the box.";
        for (var i = 0; i < payModel.count; i++) {      // each line by the same rule as Add
            var line = bridge.payProblem(payModel.get(i).role.trim(), payModel.get(i).amount, payRoles(i));
            if (line !== "") return "A different figure for: " + line;
        }
        if (win.hasNonLatin(rightField.text) || win.hasNonLatin(startField.text))
            return "Write the right to work and the start in English (Latin letters): they go into English letters and forms.";
        if (notesSize > notesMax) return "The notes about your work are " + (notesSize - notesMax) + " characters too long together. Shorten some, then save.";
        if (win.hasNonLatin(generalField.text)) return "Write the notes about your work in English (Latin letters): they are used for English interviews and forms.";
        for (var j = 0; j < boxModel.count; j++) if (win.hasNonLatin(boxModel.get(j).notes))
            return "Write the note on “" + boxModel.get(j).job + "” in English (Latin letters).";
        return "";
    }
    function save() {
        aboutSink.forceActiveFocus();     // finish any field that is still being edited
        err = ""; confirmClose = false;
        var p = problem();
        if (p !== "") { err = p; return; }
        var saved = bridge.saveAboutYou(collect());
        if (!(saved && saved.ok)) { err = (saved && saved.msg) || "About you could not be saved."; return; }
        win.optsData = bridge.options();
        ticker.text = "✓ About you saved.";
        close();
    }
    function money(n) { return Number(n).toLocaleString(Qt.locale("en_US"), "f", 0).replace(/,/g, " "); }

    background: Rectangle {
        radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
        FocusCatcher {}
    }
    Item { id: aboutSink }
    contentItem: ColumnLayout {
        spacing: 0
        RowLayout { Layout.fillWidth: true; Layout.margins: 16
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                Text { text: "About you"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                    text: "The only facts about you the app states besides your CV: in letters, form answers and interview preparation." } }
            Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                Layout.alignment: Qt.AlignTop
                Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: aboutDialog.tryClose() } } }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }

        ScrollView {
            id: aboutScroll; objectName: "aboutScroll"
            Layout.fillWidth: true; Layout.fillHeight: true
            contentWidth: availableWidth; clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Item {
                width: aboutDialog.width
                implicitHeight: aboutCol.implicitHeight
                FocusCatcher {}
            ColumnLayout {
                id: aboutCol
                anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
                spacing: 16
                Item { Layout.preferredHeight: 2 }

                // ── SALARY ──
                ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                    GroupTitle { text: "Salary" }
                    Card {
                        SRow { label: "Salary you ask for"; hint: "gross per month · 0 = none given"
                            RowLayout { spacing: 8
                                ThemedSpin { id: salarySpin; objectName: "salarySpin"; from: 0; to: win.limits.salary_max; stepSize: 1000; value: 0 }
                                ThemedCombo { id: currencyCombo; objectName: "currencyCombo"; implicitWidth: 84; plainText: true } } }
                        // with 0: what forms give instead, the app's own estimate for your kinds of role (or why there is none)
                        ColumnLayout { objectName: "salaryEstimates"; Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12
                            Layout.bottomMargin: 10; spacing: 4
                            Text { objectName: "salaryNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11; color: theme.faint
                                text: salarySpin.value > 0
                                      ? "Form answers give this as your expectation, and Insights compares what postings pay with it."
                                      : ((aboutDialog.info.estimates || {}).note || "") }
                            Repeater { model: salarySpin.value > 0 ? [] : ((aboutDialog.info.estimates || {}).rows || [])
                                RowLayout { Layout.fillWidth: true; spacing: 8
                                    Text { text: modelData.role; color: theme.soft; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                    Text { objectName: "estimate_" + index; text: "about " + modelData.text; color: theme.ink; font.pixelSize: 12; font.bold: true } } }
                        }
                        Sep {}
                        SRow { label: "A different figure for"; hint: "a kind of role, as in job titles · used instead of the one above"
                            RowLayout { spacing: 6
                                TextField { id: payRole; objectName: "payRole"; implicitWidth: 120; implicitHeight: 30; maximumLength: win.limits.pay_role
                                    placeholderText: "e.g. support"; placeholderTextColor: theme.faint; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                    background: Rectangle { radius: 8; color: theme.surface; border.width: 1
                                        border.color: payRole.activeFocus ? theme.accent : aboutDialog.payErr !== "" ? theme.crit : theme.line }
                                    onTextEdited: aboutDialog.payErr = ""; onAccepted: aboutDialog.addPay() }
                                ThemedSpin { id: payAmount; objectName: "payAmount"; from: 0; to: win.limits.salary_max; stepSize: 1000; value: 0 }
                                SmallButton { objectName: "payAdd"; text: "+ Add"; onClicked: aboutDialog.addPay() } } }
                        Text { objectName: "payErr"; visible: aboutDialog.payErr !== ""; Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12
                            wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11; font.bold: true; text: aboutDialog.payErr }
                        // the figures you gave: each can be changed where it stands, or removed
                        ColumnLayout { objectName: "payRows"; visible: payModel.count > 0; Layout.fillWidth: true; Layout.leftMargin: 14
                            Layout.rightMargin: 12; Layout.bottomMargin: 10; spacing: 6
                            Repeater { model: payModel
                                RowLayout { Layout.fillWidth: true; spacing: 6
                                    TextField { objectName: "payRowRole_" + index; Layout.fillWidth: true; implicitHeight: 30; text: model.role
                                        maximumLength: win.limits.pay_role; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                        background: Rectangle { radius: 8; color: theme.surface; border.width: 1
                                            border.color: parent.activeFocus ? theme.accent : theme.line }
                                        onTextEdited: payModel.setProperty(index, "role", text) }
                                    ThemedSpin { objectName: "payRowAmount_" + index; from: 0; to: win.limits.salary_max; stepSize: 1000; value: model.amount
                                        onValueChanged: if (value !== model.amount) payModel.setProperty(index, "amount", value) }
                                    Text { text: currencyCombo.currentText; color: theme.faint; font.pixelSize: 11 }
                                    SmallButton { objectName: "payRowRemove_" + index; text: "Remove"; onClicked: payModel.remove(index) } } }
                        }
                    }
                }

                // ── RIGHT TO WORK AND START ──
                ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                    GroupTitle { text: "Right to work and start" }
                    Card {
                        ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 14; Layout.topMargin: 10; Layout.bottomMargin: 10; spacing: 6
                            Text { text: "Right to work"; color: theme.ink; font.pixelSize: 13 }
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                text: "As letters and forms should say it · empty = not mentioned. Choose a usual answer, then change it if you need to." }
                            Flow { objectName: "rightChoices"; Layout.fillWidth: true; spacing: 6
                                Repeater { model: aboutDialog.info.right_choices || []
                                    Rectangle { objectName: "rightChoice_" + index; radius: 999; implicitHeight: 26; implicitWidth: choiceText.implicitWidth + 20
                                        color: rightField.text === modelData ? theme.accent : (choiceMa.containsMouse ? theme.surface2 : theme.inset)
                                        border.width: 1; border.color: rightField.text === modelData ? theme.accent : theme.line
                                        Text { id: choiceText; anchors.centerIn: parent; text: modelData; font.pixelSize: 11
                                            color: rightField.text === modelData ? theme.accentInk : theme.ink }
                                        MouseArea { id: choiceMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: { rightField.text = modelData; aboutDialog.err = ""; } } } } }
                            TextField { id: rightField; objectName: "rightField"; Layout.fillWidth: true; implicitHeight: 30
                                placeholderText: "e.g. EU citizen, no permit needed"; placeholderTextColor: theme.faint
                                color: theme.ink; font.pixelSize: 12; selectByMouse: true; maximumLength: win.limits.options.about_right_to_work
                                onTextEdited: aboutDialog.err = text.length >= maximumLength ? "“Right to work” takes up to " + maximumLength + " characters." : ""
                                background: Rectangle { radius: 8; color: theme.surface; border.width: 1
                                    border.color: rightField.activeFocus ? theme.accent : theme.line } }
                        }
                        Sep {}
                        ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 14; Layout.topMargin: 10; Layout.bottomMargin: 10; spacing: 6
                            Text { text: "You can start"; color: theme.ink; font.pixelSize: 13 }
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                text: "A date (2026-11-01) or a time from now (two weeks, one month) · empty = not mentioned. Letters say it as you write it; forms get a date." }
                            TextField { id: startField; objectName: "startField"; Layout.fillWidth: true; implicitHeight: 30
                                placeholderText: "e.g. within two weeks"; placeholderTextColor: theme.faint
                                color: theme.ink; font.pixelSize: 12; selectByMouse: true; maximumLength: win.limits.options.about_start
                                onTextEdited: {
                                    aboutDialog.err = text.length >= maximumLength ? "“You can start” takes up to " + maximumLength + " characters." : "";
                                    aboutDialog.start = bridge.startPreview(text);
                                }
                                background: Rectangle { radius: 8; color: theme.surface; border.width: 1
                                    border.color: (aboutDialog.start.ok === false) ? theme.crit : (startField.activeFocus ? theme.accent : theme.line) } }
                            Text { objectName: "startPreview"; visible: (aboutDialog.start.text || "") !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                                font.pixelSize: 11; font.bold: aboutDialog.start.ok === false
                                color: aboutDialog.start.ok === false ? theme.crit : theme.good; text: aboutDialog.start.text || "" }
                        }
                    }
                }

                // ── YOUR WORK ──
                ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                    GroupTitle { text: "More about your work" }
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                        text: "What you really did in each job beyond what the CV says: tasks, tools, team, results. In English. Interview preparation and form answers use it like your CV, so write only what is true." }
                    Card {
                        Text { objectName: "noJobs"; visible: boxModel.count === 0; Layout.fillWidth: true; Layout.margins: 14; wrapMode: Text.WordWrap
                            color: theme.soft; font.pixelSize: 12
                            text: "Add your jobs on the My details page of the assistant: each job then gets a box of its own here. Until then, write under Other work." }
                        Repeater { model: boxModel
                            ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 14; Layout.topMargin: 10; spacing: 5
                                RowLayout { Layout.fillWidth: true; spacing: 8
                                    Text { text: model.job; color: theme.ink; font.pixelSize: 13; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                    Text { visible: model.earlier; text: "no longer in My details"; color: theme.warn; font.pixelSize: 10; font.bold: true }
                                    SmallButton { objectName: "boxRemove_" + index; visible: model.earlier; text: "Remove"; onClicked: boxModel.remove(index) } }
                                Rectangle { Layout.fillWidth: true; radius: 8; color: theme.surface; border.width: 1
                                    border.color: boxEdit.activeFocus ? theme.accent : theme.line
                                    implicitHeight: Math.max(70, boxEdit.implicitHeight + 16)
                                    TextEdit { id: boxEdit; objectName: "boxNotes_" + index; x: 8; y: 8; width: parent.width - 16; wrapMode: TextEdit.Wrap
                                        selectByMouse: true; color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent; text: model.notes
                                        onTextChanged: if (text !== model.notes) { boxModel.setProperty(index, "notes", text); aboutDialog.err = ""; aboutDialog.notesTick++; }
                                        Text { visible: boxEdit.text === ""; width: parent.width; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 12
                                            text: "e.g. I was in a team of four. I wrote the import service in Python, added its tests, and fixed about thirty tickets." } } }
                            } }
                        ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 14; Layout.topMargin: 10; Layout.bottomMargin: 10; spacing: 5
                            Text { text: "Other work"; color: theme.ink; font.pixelSize: 13; font.bold: true }
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                text: "Projects, volunteering, anything that belongs to no job above." }
                            Rectangle { Layout.fillWidth: true; radius: 8; color: theme.surface; border.width: 1
                                border.color: generalField.activeFocus ? theme.accent : theme.line
                                implicitHeight: Math.max(70, generalField.implicitHeight + 16)
                                TextEdit { id: generalField; objectName: "generalField"; x: 8; y: 8; width: parent.width - 16; wrapMode: TextEdit.Wrap
                                    selectByMouse: true; color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                                    onTextChanged: { if (activeFocus) aboutDialog.err = ""; aboutDialog.notesTick++; } } }
                            Text { objectName: "notesCount"; Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; font.pixelSize: 11
                                color: aboutDialog.notesSize > aboutDialog.notesMax ? theme.crit : theme.faint
                                font.bold: aboutDialog.notesSize > aboutDialog.notesMax
                                text: aboutDialog.notesSize > aboutDialog.notesMax
                                      ? (aboutDialog.notesSize - aboutDialog.notesMax) + " characters too long together (the limit is " + aboutDialog.notesMax + ")"
                                      : aboutDialog.notesSize + " of " + aboutDialog.notesMax + " characters, all notes together" }
                        }
                    }
                }

                // ── YOUR OWN LETTERS ──
                ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                    GroupTitle { text: "Your own letters" }
                    Card {
                        SRow { label: "Letters you wrote yourself"
                            hint: (aboutDialog.myLetters.count || 0) + " in the " + (aboutDialog.myLetters.name || "my_letters")
                                  + " folder · never changed by the app"
                            SmallButton { objectName: "myLettersOpen"; text: "Open folder"
                                onClicked: { var r = bridge.openMyLetters();
                                    ticker.text = (r && r.ok) ? "Put letters you wrote yourself there, named like Name_CoverLetter_Company.docx."
                                                              : "Couldn't open the folder."; } } }
                    }
                }
                Item { Layout.preferredHeight: 4 }
            }
            }
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
        RowLayout { Layout.fillWidth: true; Layout.margins: 14
            Text { objectName: "aboutErr"; Layout.fillWidth: true; visible: aboutDialog.err !== ""; wrapMode: Text.WordWrap
                color: theme.crit; font.pixelSize: 12; font.bold: true; text: aboutDialog.err }
            Item { Layout.fillWidth: aboutDialog.err === "" }
            SmallButton { objectName: "aboutCancel"; text: aboutDialog.confirmClose ? "Discard changes" : "Cancel"; onClicked: aboutDialog.close() }
            PillButton { id: aboutSaveBtn; objectName: "aboutSave"; primaryStyle: true; text: "Save"; onClicked: aboutDialog.save() }
        }
    }
}
