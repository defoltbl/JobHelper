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
    property var jobs: []                 // what the list shows: all open jobs, or those that match what was typed
    property var allJobs: []
    property string jobFindErr: ""
    readonly property int maxJobFind: 80
    // Typing part of a company or a title narrows the list; when one job is left, it is chosen and its full name shown.
    function findJob(typed) {
        var words = String(typed || "").toLowerCase().split(/\s+/).filter(function (w) { return w !== ""; }), kept = [], was = jobId;
        jobFindErr = "";
        if (String(typed || "").length > maxJobFind) { jobFindErr = "That is too long for a name: " + maxJobFind + " characters at most."; return; }
        for (var i = 1; i < allJobs.length; i++) {
            var label = allJobs[i].label.toLowerCase(), all = true;
            for (var w = 0; w < words.length; w++) if (label.indexOf(words[w]) < 0) { all = false; break; }
            if (all) kept.push(allJobs[i]);
        }
        jobs = [allJobs[0]].concat(kept);
        var at = 0;
        if (words.length > 0 && kept.length === 1) at = 1;
        else for (var k = 1; k < jobs.length; k++) if (jobs[k].id === was) at = k;
        jobBox.currentIndex = at; jobId = jobs[at].id;
        if (words.length > 0 && kept.length === 0)
            jobFindErr = "None of your open jobs has \"" + String(typed).trim() + "\" in its company or title. Check the spelling, or let me find the job from the page.";
    }
    function chooseJob(id) {              // by the app itself: the whole list again, and this job in it
        jobFind.text = ""; jobFindErr = ""; jobs = allJobs;
        for (var i = 0; i < jobs.length; i++) if (jobs[i].id === id) { jobBox.currentIndex = i; jobId = id; return true; }
        return false;
    }
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
    ListModel { id: noteModel }           // what it was told to remember: {text, when}
    property string doing: ""             // what is being done right now, said under the talk while it waits
    property bool canUndo: false          // the last yes can be taken back
    property string draftText: ""         // a reply drafted for you to copy
    property var browser: ({ key: "chrome", name: "Google Chrome", short: "Chrome", switch: "", all: [] })
    property var practiceLast: []         // how each question went the last time ("" = never practised)
    property var practiceNow: []          // how each went this time
    // an answer appears as if it were being written: quickly, and whole at once under test or when it is short
    property int typingIndex: -1
    property int typingShown: 0
    Timer { id: typist; interval: 16; repeat: true
        running: assistantDialog.typingIndex >= 0 && assistantDialog.visible
        onTriggered: {
            if (assistantDialog.typingIndex >= talk.count) { assistantDialog.typingIndex = -1; return; }
            var whole = talk.get(assistantDialog.typingIndex).text.length;
            assistantDialog.typingShown += Math.max(10, Math.ceil(whole / 24));
            if (assistantDialog.typingShown >= whole) assistantDialog.typingIndex = -1;
            talkFlick.contentY = Math.max(0, talkFlick.contentHeight - talkFlick.height);
        } }
    function write(text) {                // an answer from Claude, written out
        say("bot", text, false);
        if (text.length > 60) { typingIndex = talk.count - 1; typingShown = 0; }
    }
    function loadNotes() {
        var d = bridge.assistantNotes(), notes = (d && d.notes) || [];
        noteModel.clear();
        for (var i = 0; i < notes.length; i++) noteModel.append({ text: notes[i].text, when: notes[i].when || "" });
    }
    function forgetNote(index) {
        var r = bridge.forgetNote(index + 1);
        if (!(r && r.ok)) { problem = { field: "", msg: (r && r.msg) || "That note could not be removed." }; return; }
        loadNotes(); detailsNote = "Forgotten.";
    }
    function setBrowser(key) {
        var r = bridge.setAssistantBrowser(key);
        if (!(r && r.ok)) {              // Firefox, for one: said, and the list goes back to the browser in use
            problem = { field: "", msg: (r && r.msg) || "That browser could not be chosen." }; detailsNote = "";
            browser = ({}); browser = bridge.assistantBrowser(); return;
        }
        problem = ({});
        browser = r; watchProblem = "";
        detailsNote = "I now work in " + r.name + ". Its switch: " + r.switch + ".";
    }
    ListModel { id: rowModel }            // jobs an answer is about: {id, label, sub}
    ListModel { id: problemModel }        // what a review found: {field, problem}
    ListModel { id: nudgeModel }          // things to look at today: {text, job_id, kind}
    // an action that changes your data waits here for your yes
    property var pending: null
    property string pendingAsk: ""
    property string pendingPreview: ""
    // practising an interview: one question at a time
    property bool practising: false
    property string practiceJob: ""
    property string practiceName: ""
    property var practiceQuestions: []
    property int practiceIndex: 0
    // noticing a form in Chrome by itself: off until you turn it on
    property bool watching: false
    property string watchProblem: ""
    property string noticedJob: ""
    function contextJob() { return detailDialog.visible && detailDialog.job && detailDialog.job.id ? detailDialog.job.id : ""; }
    function setWatch(on) {
        var r = bridge.setAssistantWatch(on);
        if (!(r && r.ok)) { askErr = (r && r.msg) || "That could not be changed."; watching = bridge.assistantWatching(); return; }
        watching = on; watchProblem = "";
    }
    function yes() {                      // your yes to what the assistant asked about
        if (busy || pending === null) return;
        var what = JSON.stringify(pending);
        pending = null; pendingAsk = ""; pendingPreview = "";
        say("you", "Yes", false);
        busy = true; bridge.assistantDo("confirm", what, "");
    }
    function no() {
        if (pending === null) return;
        pending = null; pendingAsk = ""; pendingPreview = "";
        say("you", "No", false); say("bot", "Left as it was.", false);
    }
    function openThing(id, what) {
        if (what === "posting") { var r = bridge.openUrl(id); if (!(r && r.ok)) say("bot", "There is no link saved for this job.", true); return; }
        if (what === "cv" || what === "letter") {
            var d = bridge.jobDetail(id), name = d ? d[what] : "";
            if (!name) { say("bot", "This job has no " + (what === "cv" ? "CV" : "letter") + " from the app.", true); return; }
            bridge.openDoc(d[what + "_pdf"] === true ? what + "_pdf" : what, name); return;
        }
        detailDialog.show(id);
    }
    function practiceSummary() {
        var n = { good: 0, ok: 0, weak: 0 };
        for (var i = 0; i < practiceNow.length; i++) n[practiceNow[i]] = (n[practiceNow[i]] || 0) + 1;
        if (practiceNow.length === 0) return "No answer was given this time.";
        return "This time: " + n.good + " good, " + n.ok + " fair, " + n.weak + " weak."
               + (n.weak > 0 ? " The weak ones come first next time." : "");
    }
    function endPractice(words) {
        if (!practising) return;
        practising = false;
        say("bot", words || ("Practice ended. " + practiceSummary()), false);
    }
    function askQuestion() {
        var before = practiceLast[practiceIndex] || "";
        say("bot", "Question " + (practiceIndex + 1) + " of " + practiceQuestions.length + (before === "weak" ? " (it went badly last time)" : before === "good" ? " (it went well last time)" : "")
                   + ": " + practiceQuestions[practiceIndex], false);
    }
    function dropNudge(index) {
        var n = nudgeModel.get(index);
        bridge.nudgeDone(n.job_id, n.kind); nudgeModel.remove(index);
    }
    ListModel { id: fieldModel }          // {key, label, most, value, fromCv}
    ListModel { id: jobModel }            // {employer, title, start, end, current}
    ListModel { id: schoolModel }         // {school, degree, field, start, end}
    ListModel { id: fileModel }           // {label, path, name}
    ListModel { id: answerModel }         // {question, answer, was, check, dirty, err}
    property string salaryAmount: ""      // digits, "" = no figure
    property string salaryCurrency: "CZK"
    property string salaryPeriod: "month"
    property var currencies: ["CZK"]
    property int maxRows: 15
    property bool confirmCv: false        // "Read from my CV" was pressed once and would replace rows
    property var starters: []             // questions most forms ask, not answered yet
    property string answersNote: ""
    property string answersErr: ""
    readonly property var jobCols: [{ key: "employer", label: "Employer", most: 100 }, { key: "title", label: "Job title", most: 100 },
                                    { key: "start", label: "From", most: 10, hint: "03/2023" }, { key: "end", label: "To", most: 10, hint: "2024" }]
    readonly property var schoolCols: [{ key: "school", label: "University or school", most: 120 }, { key: "degree", label: "Degree", most: 120 },
                                       { key: "field", label: "Field of study", most: 120 }, { key: "start", label: "From", most: 10, hint: "2019" },
                                       { key: "end", label: "To", most: 10, hint: "2023" }]

    function say(who, text, bad) {
        talk.append({ who: who, text: text, bad: bad === true });
        Qt.callLater(function () { talkFlick.contentY = Math.max(0, talkFlick.contentHeight - talkFlick.height); });
    }
    function show() {
        askErr = ""; confirmClose = false; busy = false;
        allJobs = [{ id: "", label: "Find the job from the page" }].concat(bridge.assistantJobs());
        jobs = allJobs; jobFind.text = ""; jobFindErr = "";
        jobBox.currentIndex = 0; jobId = "";
        loadDetails(); loadAnswers();
        remembered = bridge.assistantMemory().count || 0; confirmForget = false;
        watching = bridge.assistantWatching(); browser = bridge.assistantBrowser(); loadNotes();
        doing = ""; typingIndex = -1;
        nudgeModel.clear();
        var today = bridge.assistantBriefing(), nudges = (today && today.nudges) || [];
        for (var n = 0; n < nudges.length; n++) nudgeModel.append({ text: nudges[n].text, job_id: nudges[n].job_id, kind: nudges[n].kind });
        if (talk.count === 0 && today && (today.lines || []).length > 0)
            say("bot", "Today: " + today.lines.join("; ") + ".", false);
        if (talk.count === 0)
            say("bot", detailsSaved ? "Hi! Open an application form in Chrome, bring its tab to the front, then ask me to fill it in."
                                    : "Hi! First tell me your details on the My details page. Then open an application form in Chrome and ask me to fill it in.");
        page = detailsSaved ? "ask" : "details";
        if (noticedJob !== "") {              // it noticed a form by itself: the answers are for that job
            chooseJob(noticedJob);
            noticedJob = "";
        }
        open();
    }
    function forJob(id) {                 // opened from a job's window: the answers are for that job
        show();
        chooseJob(id);
        if (jobId !== id) askErr = "That application is closed, so it is not in the list. Choose a job, or let me find it from the page.";
    }
    function ask(text) {
        confirmClose = false;
        if (busy) { askErr = "I am still working on the last request. Wait for the answer."; return; }
        var words = (text || "").trim();
        if (words === "") { askErr = "Write what you need, or press Fill in the form in Chrome."; return; }
        if (words.length > maxRequest) { askErr = "That is longer than " + maxRequest + " characters. Say it in a sentence."; return; }
        if (dirty) { askErr = "You changed your details and did not save them. Save them on the My details page first."; return; }
        if (pending !== null) { askErr = "First answer the question above: Yes, do it or No."; return; }
        askErr = ""; askBox.text = "";
        if (practising) {                     // an answer to the question that was asked
            if (/^(stop|end|quit|enough|finish)\b/i.test(words)) { say("you", words, false); endPractice(""); return; }
            say("you", words, false);
            busy = true;
            bridge.assistantDo("practice_answer", JSON.stringify({ question: practiceQuestions[practiceIndex], answer: words }), practiceJob);
            return;
        }
        filledModel.clear(); leftModel.clear(); rowModel.clear(); problemModel.clear();
        last = ({}); nextPage = false; watchSign = ""; appliedNow = false; canUndo = false; draftText = ""; doing = "";
        say("you", words, false);
        busy = true;
        bridge.askAssistant(words, contextJob(), jobId);
    }
    function act(what, arg, words) {      // one of the buttons under an answer
        if (busy) { askErr = "I am still working on the last request. Wait for the answer."; return; }
        if (what === "review") problemModel.clear();
        if (what === "judge") { rowModel.clear(); canUndo = false; draftText = ""; }
        doing = what === "judge" ? "Reading the page and scoring it…" : "";
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
        if (unsavedAnswers() > 0 && !confirmClose) {
            confirmClose = true; page = "answers"; answersNote = "";
            answersErr = unsavedAnswers() + (unsavedAnswers() === 1 ? " answer is" : " answers are") + " not saved. Press Save on each, or Close once more to discard the changes.";
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
        fillRows(jobModel, (d && d.experience) || [], jobCols, true);
        fillRows(schoolModel, (d && d.education) || [], schoolCols, false);
        fileModel.clear();
        var files = (d && d.files) || [];
        for (var f = 0; f < files.length; f++) fileModel.append({ label: files[f].label, path: files[f].path, name: files[f].name });
        salaryAmount = d && d.salary_amount > 0 ? "" + d.salary_amount : "";
        salaryCurrency = (d && d.salary_currency) || "CZK"; salaryPeriod = (d && d.salary_period) || "month";
        currencies = (d && d.currencies) || ["CZK"]; maxRows = (d && d.max_rows) || 15;
        detailsSaved = !!(d && d.saved); offered = fromCv.length;
        dirty = false; problem = ({}); detailsNote = ""; confirmClose = false; confirmCv = false;
    }
    function fillRows(model, rows, cols, withCurrent) {
        model.clear();
        for (var i = 0; i < rows.length; i++) {
            var row = {};
            for (var c = 0; c < cols.length; c++) row[cols[c].key] = rows[i][cols[c].key] || "";
            if (withCurrent) row.current = rows[i].current === true;
            model.append(row);
        }
    }
    function rowsOf(model, cols, withCurrent) {
        var out = [];
        for (var i = 0; i < model.count; i++) {
            var row = {}, kept = model.get(i);
            for (var c = 0; c < cols.length; c++) row[cols[c].key] = kept[cols[c].key];
            if (withCurrent) row.current = kept.current === true;
            out.push(row);
        }
        return out;
    }
    function values() {
        var out = {};
        for (var i = 0; i < fieldModel.count; i++) out[fieldModel.get(i).key] = fieldModel.get(i).value;
        out.experience = rowsOf(jobModel, jobCols, true);
        out.education = rowsOf(schoolModel, schoolCols, false);
        out.files = [];
        for (var f = 0; f < fileModel.count; f++) out.files.push({ label: fileModel.get(f).label, path: fileModel.get(f).path });
        out.salary_amount = salaryAmount.trim() === "" ? 0 : salaryAmount;
        out.salary_currency = salaryCurrency; out.salary_period = salaryPeriod;
        return out;
    }
    function touched() {                  // something on the page changed: check it all again
        dirty = true; detailsNote = ""; confirmClose = false; confirmCv = false;
        problem = bridge.checkMyDetails(JSON.stringify(values()));
    }
    function addRow(model, cols, withCurrent) {
        if (model.count >= maxRows) { problem = { field: "", msg: "That is the most rows this list takes (" + maxRows + "). Remove an old one first." }; return; }
        var row = {};
        for (var c = 0; c < cols.length; c++) row[cols[c].key] = "";
        if (withCurrent) row.current = false;
        model.append(row); dirty = true; detailsNote = "";
    }
    function setRow(model, index, key, value) { model.setProperty(index, key, value); touched(); }
    function setSalary(amount, currency, period) { salaryAmount = "" + amount; salaryCurrency = currency; salaryPeriod = period; touched(); }
    function addFile(url) {
        var path = bridge.localFile(url);
        if (path === "") { problem = { field: "files", msg: "That is not a file on this Mac. Choose a file, such as a PDF of a certificate." }; return; }
        for (var i = 0; i < fileModel.count; i++)
            if (fileModel.get(i).path === path) { problem = { field: "files." + i, msg: "That file is in the list already." }; return; }
        var name = path.split("/").pop();
        fileModel.append({ label: name.replace(/\.[^.]+$/, ""), path: path, name: name });
        touched();
    }
    function readCv() {                   // jobs and degrees, copied from the CV by Claude; never over rows without asking
        if (busy) return;
        if ((jobModel.count > 0 || schoolModel.count > 0) && !confirmCv) {
            confirmCv = true; detailsNote = "";
            problem = { field: "", msg: "Reading from your CV replaces the jobs and degrees listed here. Press Read from my CV once more to go on." };
            return;
        }
        confirmCv = false; problem = ({});
        say("you", "Read my jobs and degrees from my CV", false);
        busy = true; bridge.assistantDo("cv_lists", "", "");
    }
    // ── My answers ──
    function loadAnswers() {
        var d = bridge.myAnswers();
        answerModel.clear();
        var items = (d && d.items) || [];
        for (var i = 0; i < items.length; i++)
            answerModel.append({ question: items[i].question, answer: items[i].answer, was: items[i].question, check: "", dirty: false, err: "" });
        starters = (d && d.starters) || [];
        answersNote = ""; answersErr = "";
    }
    function addAnswer(question) {
        for (var i = 0; i < answerModel.count; i++)
            if (answerModel.get(i).question.trim().toLowerCase() === (question || "").trim().toLowerCase() && question !== "") { answersErr = "That question is in the list already."; return; }
        answerModel.insert(0, { question: question || "", answer: "", was: "", check: "", dirty: true, err: "" });
        answersErr = ""; answersNote = "";
        var left = [];
        for (var s = 0; s < starters.length; s++) if (starters[s] !== question) left.push(starters[s]);
        starters = left;
        answersFlick.contentY = 0;
    }
    function setAnswer(index, key, value) {
        answerModel.setProperty(index, key, value); answerModel.setProperty(index, "dirty", true); answerModel.setProperty(index, "err", "");
        answersNote = ""; answersErr = "";
    }
    function unsavedAnswers() { var n = 0; for (var i = 0; i < answerModel.count; i++) if (answerModel.get(i).dirty) n++; return n; }
    function saveAnswer(index) {
        var row = answerModel.get(index);
        var r = bridge.saveMyAnswer(row.question, row.answer, row.was);
        if (!(r && r.ok)) { answerModel.setProperty(index, "err", (r && r.msg) || "That answer could not be kept."); return; }
        answerModel.setProperty(index, "was", row.question.trim()); answerModel.setProperty(index, "dirty", false);
        answerModel.setProperty(index, "err", ""); answerModel.setProperty(index, "check", "");
        remembered = bridge.assistantMemory().count || 0;
        answersNote = "Kept. The next form that asks this gets your wording, with no Claude call.";
    }
    function removeAnswer(index) {
        var row = answerModel.get(index);
        if (row.was !== "") bridge.deleteMyAnswer(row.was);
        answerModel.remove(index);
        remembered = bridge.assistantMemory().count || 0;
        answersNote = "Removed."; answersErr = "";
    }
    function draftAnswer(index) {
        if (busy) { answerModel.setProperty(index, "err", "I am still working on the last request. Wait for the answer."); return; }
        var row = answerModel.get(index);
        if (row.question.trim() === "") { answerModel.setProperty(index, "err", "Write the question first."); return; }
        if (row.answer.trim() !== "" && row.check !== "replace") {
            answerModel.setProperty(index, "check", "replace");
            answerModel.setProperty(index, "err", "A draft replaces what is written here. Press Draft with Claude once more to go on."); return;
        }
        answerModel.setProperty(index, "err", ""); answerModel.setProperty(index, "check", "");
        say("you", "Draft an answer: " + row.question, false);
        busy = true; bridge.assistantDo("draft", row.question, "");
    }
    function setField(key, value) {       // what typing in a field does
        for (var i = 0; i < fieldModel.count; i++) if (fieldModel.get(i).key === key) fieldModel.setProperty(i, "value", value);
        touched();
    }
    function saveDetails() {
        confirmClose = false; detailsNote = "";
        var empty = jobModel.count === 0 && schoolModel.count === 0 && fileModel.count === 0, all = values();
        for (var i = 0; i < fieldModel.count; i++) if (String(fieldModel.get(i).value).trim() !== "") empty = false;
        if (empty && !detailsSaved) { problem = { field: "first_name", msg: "Every field is empty. Fill in at least your name and email, then save." }; return; }
        var r = bridge.saveMyDetails(JSON.stringify(all));
        if (!(r && r.ok)) { problem = { field: (r && r.field) || "", msg: (r && r.msg) || "Your details could not be saved." }; return; }
        loadDetails();
        detailsNote = "Saved, encrypted on this Mac. Forms are filled in with exactly this.";
    }
    FileDialog { id: filePick; title: "Choose a file a form may ask for"
        onAccepted: assistantDialog.addFile("" + selectedFile) }
    Connections { target: bridge
        function onFormWatched(res) {
            if (!res.ok || assistantDialog.busy || assistantDialog.watchSign === "" || assistantDialog.nextPage) return;
            if (assistantDialog.watchSign === "pending") { assistantDialog.watchSign = res.url + " " + res.sign; return; }
            if (res.url + " " + res.sign === assistantDialog.watchSign || res.empty < 1) return;
            assistantDialog.nextPage = true;
            assistantDialog.say("bot", "The form in Chrome shows other fields now. Shall I fill in this page too?", false);
        }
        function onAssistantProgress(res) { if (assistantDialog.busy) assistantDialog.doing = res.text || ""; }
        function onAssistantReady(res) {
            if (!assistantDialog.busy) return;
            assistantDialog.busy = false; assistantDialog.doing = "";
            var also = res.also || [];                    // what was said or done before this, in the same request
            for (var s = 0; s < also.length; s++) assistantDialog.say("bot", also[s], false);
            var then = res.then || [];
            for (var o = 0; o < then.length; o++) {
                if (then[o].action === "open") assistantDialog.openThing(then[o].job_id, then[o].what);
                if (then[o].action === "page") assistantDialog.page = then[o].page;
            }
            if (res.notes_changed) assistantDialog.loadNotes();
            if (res.can_undo !== undefined) assistantDialog.canUndo = res.can_undo === true;
            if (res.action === "details") assistantDialog.page = "details";
            if (res.action === "fill") assistantDialog.last = res;
            if (res.action === "learn" || res.action === "forget") { assistantDialog.remembered = bridge.assistantMemory().count || 0; assistantDialog.loadAnswers(); }
            if (res.action === "cv_lists") {              // offered in the page, not saved
                if (res.ok) {
                    assistantDialog.fillRows(jobModel, res.experience || [], assistantDialog.jobCols, true);
                    assistantDialog.fillRows(schoolModel, res.education || [], assistantDialog.schoolCols, false);
                    assistantDialog.touched();
                    assistantDialog.detailsNote = "Read from your CV, not saved yet: check every line, then save.";
                } else assistantDialog.problem = { field: "", msg: res.msg || "That did not work." };
            }
            if (res.action === "draft") {
                for (var a = 0; a < answerModel.count; a++) {
                    if (answerModel.get(a).question.trim() !== (res.question || answerModel.get(a).question).trim() && res.ok) continue;
                    if (res.ok) { answerModel.setProperty(a, "answer", res.answer); answerModel.setProperty(a, "dirty", true);
                                  answerModel.setProperty(a, "check", res.check || ""); answerModel.setProperty(a, "err", ""); assistantDialog.answersNote = res.say || ""; }
                    else if (answerModel.get(a).dirty || answerModel.count === 1) { answerModel.setProperty(a, "err", res.msg || "That did not work."); break; }
                }
                if (!res.ok) assistantDialog.answersErr = res.msg || "That did not work.";
            }
            if (res.action === "practice_feedback" && !res.ok && assistantDialog.practising) {     // the answer was not taken: the same question stays
                assistantDialog.askErr = res.msg || "That did not work."; return;
            }
            if (!res.ok) { stagePanel.assistant.shake(); assistantDialog.say("bot", res.msg || "That did not work.", true); return; }
            stagePanel.assistant.nod();
            if (res.action === "confirm") {             // something of yours would change: asked first, in the app's own words
                assistantDialog.pending = res.pending; assistantDialog.pendingAsk = res.ask || ""; assistantDialog.pendingPreview = res.preview || "";
                assistantDialog.say("bot", res.ask || "Shall I?", false); return;
            }
            if (res.action === "say" || res.action === "review") assistantDialog.write(res.say || "Done.");
            else assistantDialog.say("bot", res.say || "Done.", false);
            if (res.action === "draft") assistantDialog.draftText = res.copy || "";
            var rows = res.rows || [];
            rowModel.clear();
            for (var r = 0; r < rows.length; r++) rowModel.append({ id: rows[r].id, label: rows[r].label, sub: rows[r].sub || "" });
            if (res.action === "page") assistantDialog.page = res.page;
            if (res.action === "open") assistantDialog.openThing(res.job_id, res.what);
            if (res.action === "done") { win.reloadAll(); detailDialog.refresh(); }
            if (res.action === "review") {
                problemModel.clear();
                var found = res.problems || [];
                for (var p = 0; p < found.length; p++) problemModel.append({ field: found[p].field, problem: found[p].problem });
            }
            if (res.action === "practice") {
                assistantDialog.practising = true; assistantDialog.practiceJob = res.job_id; assistantDialog.practiceName = res.job || "";
                assistantDialog.practiceQuestions = res.questions || []; assistantDialog.practiceIndex = 0;
                assistantDialog.practiceLast = res.last || []; assistantDialog.practiceNow = [];
                assistantDialog.askQuestion();
            }
            if (res.action === "practice_feedback" && assistantDialog.practising) {
                var went = assistantDialog.practiceNow.slice(); went.push(res.rating || "ok"); assistantDialog.practiceNow = went;
                if (assistantDialog.practiceIndex + 1 >= assistantDialog.practiceQuestions.length)
                    assistantDialog.endPractice("That was the last question. " + assistantDialog.practiceSummary());
                else { assistantDialog.practiceIndex++; assistantDialog.askQuestion(); }
            }
            if (res.action === "fill") { assistantDialog.watchSign = "pending"; assistantDialog.watched = 0; bridge.watchForm(); }
            var filled = res.filled || [], left = res.left || [];
            for (var i = 0; i < filled.length; i++)
                filledModel.append({ label: filled[i].label, value: filled[i].value, kind: filled[i].kind, check: filled[i].check || "" });
            for (var j = 0; j < left.length; j++) leftModel.append({ label: left[j].label, why: left[j].why });
            if (res.job_id) detailDialog.refresh();
        } }

    background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
        FocusCatcher {} }
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
                    text: "Fills in application forms in your browser, answers questions about your search, and does things in the app after your yes." } }
            Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                Layout.alignment: Qt.AlignTop
                Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: assistantDialog.tryClose() } }
        }
        RowLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 10; spacing: 6
            SmallButton { objectName: "asPageAsk"; text: "Ask"; primaryStyle: assistantDialog.page === "ask"; onClicked: assistantDialog.page = "ask" }
            SmallButton { objectName: "asPageDetails"; text: assistantDialog.dirty ? "My details •" : "My details"
                primaryStyle: assistantDialog.page === "details"; onClicked: assistantDialog.page = "details" }
            SmallButton { objectName: "asPageAnswers"; text: "My answers" + (answerModel.count > 0 ? " (" + answerModel.count + ")" : "")
                primaryStyle: assistantDialog.page === "answers"; onClicked: assistantDialog.page = "answers" }
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
                FocusCatcher {}                // a press on empty space in the scroll area
                ColumnLayout {
                    id: talkCol
                    x: 16; y: 14; width: talkFlick.width - 32; spacing: 10
                    DetailCard { objectName: "asNudges"; visible: nudgeModel.count > 0; heading: "For you today (" + nudgeModel.count + ")"
                        Repeater { model: nudgeModel
                            RowLayout { Layout.fillWidth: true; spacing: 6
                                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.ink; font.pixelSize: 12; text: model.text }
                                SmallButton { text: "Open"; onClicked: detailDialog.show(model.job_id) }
                                SmallButton { text: "Do not remind me"; onClicked: assistantDialog.dropNudge(index) } } } }
                    Repeater {
                        model: talk
                        Rectangle {
                            Layout.maximumWidth: talkCol.width * 0.86; Layout.preferredWidth: Math.min(talkCol.width * 0.86, line.implicitWidth + 24)
                            Layout.alignment: model.who === "you" ? Qt.AlignRight : Qt.AlignLeft
                            implicitHeight: line.implicitHeight + 18; radius: 12
                            color: model.who === "you" ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.16) : (model.bad ? theme.critbg : theme.surface2)
                            border.width: 1; border.color: model.who === "you" ? theme.accent : (model.bad ? theme.crit : theme.line)
                            Text { id: line; x: 12; y: 9; width: Math.min(implicitWidth, talkCol.width * 0.86 - 24); wrapMode: Text.Wrap
                                text: index === assistantDialog.typingIndex ? ("" + (model.text || "")).substring(0, assistantDialog.typingShown) : (model.text || "")
                                color: model.bad ? theme.crit : theme.ink; font.pixelSize: 13; font.bold: model.bad }
                        }
                    }
                    // what waits for your yes
                    ColumnLayout { objectName: "asConfirm"; visible: assistantDialog.pending !== null && !assistantDialog.busy; Layout.fillWidth: true; spacing: 6
                        Rectangle { visible: assistantDialog.pendingPreview !== ""; Layout.fillWidth: true; radius: 10; color: theme.inset; border.color: theme.line; border.width: 1
                            implicitHeight: previewText.implicitHeight + 18
                            Text { id: previewText; x: 10; y: 9; width: parent.width - 20; wrapMode: Text.Wrap; color: theme.ink; font.pixelSize: 12
                                text: assistantDialog.pendingPreview } }
                        RowLayout { spacing: 6
                            PillButton { objectName: "asYes"; primaryStyle: true; text: "Yes, do it"; onClicked: assistantDialog.yes() }
                            SmallButton { objectName: "asNo"; implicitHeight: 34; text: "No"; onClicked: assistantDialog.no() } } }
                    Row { visible: assistantDialog.busy; spacing: 8
                        BusyIndicator { running: assistantDialog.busy; width: 20; height: 20; palette.dark: theme.a6 }
                        Text { anchors.verticalCenter: parent.verticalCenter; color: theme.soft; font.pixelSize: 12
                            text: assistantDialog.doing !== "" ? assistantDialog.doing : "Working on it…" } }
                    // a reply drafted for you: to copy, never sent
                    ColumnLayout { objectName: "asDraft"; visible: assistantDialog.draftText !== "" && !assistantDialog.busy; Layout.fillWidth: true; spacing: 6
                        Rectangle { Layout.fillWidth: true; radius: 10; color: theme.inset; border.color: theme.line; border.width: 1
                            implicitHeight: draftBody.implicitHeight + 18
                            TextEdit { id: draftBody; x: 10; y: 9; width: parent.width - 20; wrapMode: TextEdit.Wrap; readOnly: true; selectByMouse: true
                                color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent; text: assistantDialog.draftText } }
                        RowLayout { spacing: 6
                            SmallButton { objectName: "asCopy"; primaryStyle: true; text: "Copy"
                                onClicked: { bridge.copyText(assistantDialog.draftText); assistantDialog.say("bot", "Copied. Paste it into your mail and send it yourself.", false); } } } }
                    DetailCard { objectName: "asRows"; visible: rowModel.count > 0; heading: "Jobs (" + rowModel.count + ")"
                        Repeater { model: rowModel
                            Rectangle { Layout.fillWidth: true; radius: 8; color: rowMa.containsMouse ? theme.inset : "transparent"; implicitHeight: rowCol.implicitHeight + 10
                                ColumnLayout { id: rowCol; x: 6; y: 5; width: parent.width - 12; spacing: 0
                                    Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.ink; font.pixelSize: 12; font.bold: true; text: model.label }
                                    Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.soft; font.pixelSize: 11; text: model.sub } }
                                MouseArea { id: rowMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onClicked: detailDialog.show(model.id) } } } }
                    DetailCard { objectName: "asProblems"; visible: problemModel.count > 0; heading: "Look at these before you send (" + problemModel.count + ")"
                        Repeater { model: problemModel
                            ColumnLayout { Layout.fillWidth: true; spacing: 1
                                RowLayout { Layout.fillWidth: true; spacing: 6
                                    Rectangle { implicitWidth: 8; implicitHeight: 8; radius: 4; color: theme.warn }
                                    Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.ink; font.pixelSize: 12; font.bold: true; text: model.field } }
                                Text { Layout.fillWidth: true; Layout.leftMargin: 14; wrapMode: Text.Wrap; color: theme.soft; font.pixelSize: 12; text: model.problem } } } }
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
                        visible: assistantDialog.canOpenForm || assistantDialog.canShowFiles || assistantDialog.canLearn || assistantDialog.canApply || (assistantDialog.canUndo && !assistantDialog.busy)
                                 || (assistantDialog.last.ok === true && !assistantDialog.busy) || (assistantDialog.nextPage && !assistantDialog.busy)
                        SmallButton { objectName: "asNextPage"; visible: assistantDialog.nextPage && !assistantDialog.busy; primaryStyle: true; text: "Fill in this page too"
                            onClicked: assistantDialog.ask("Fill in the form in Chrome") }
                        SmallButton { objectName: "asOpenForm"; visible: assistantDialog.canOpenForm; primaryStyle: true; text: "Open the form in its own tab"
                            onClicked: assistantDialog.act("open_form", assistantDialog.last.frame, "Open the form in its own tab") }
                        SmallButton { objectName: "asUndo"; visible: assistantDialog.canUndo && !assistantDialog.busy; text: "Undo"
                            onClicked: assistantDialog.act("undo", "", "Undo that") }
                        SmallButton { objectName: "asReview"; visible: assistantDialog.last.ok === true && !assistantDialog.busy; text: "Review before I send"
                            onClicked: assistantDialog.act("review", "", "Review the form before I send it") }
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
                RowLayout { objectName: "asPractice"; visible: assistantDialog.practising; Layout.fillWidth: true; spacing: 8
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.a6; font.pixelSize: 12; font.bold: true
                        text: "Practising for " + assistantDialog.practiceName + " · question " + (assistantDialog.practiceIndex + 1) + " of " + assistantDialog.practiceQuestions.length }
                    SmallButton { text: "Stop practising"; enabled: !assistantDialog.busy; onClicked: assistantDialog.endPractice("") } }
                Flow { objectName: "asStarters"; Layout.fillWidth: true; spacing: 6; visible: !assistantDialog.practising && !assistantDialog.busy && assistantDialog.pending === null
                    SmallButton { text: "What needs my attention?"; onClicked: assistantDialog.ask("What needs my attention today?") }
                    SmallButton { objectName: "asJudge"; text: "Is the posting in my browser worth applying to?"
                        onClicked: assistantDialog.act("judge", "", "Is the job posting open in my browser worth applying to?") }
                    SmallButton { text: "New talk"; visible: talk.count > 2
                        onClicked: { bridge.newTalk(); talk.clear(); rowModel.clear(); problemModel.clear(); filledModel.clear(); leftModel.clear();
                                     assistantDialog.last = ({}); assistantDialog.canUndo = false; assistantDialog.draftText = "";
                                     assistantDialog.say("bot", "A new talk: I have put the earlier one away.", false); } } }
                RowLayout { Layout.fillWidth: true; spacing: 8
                    Text { text: "Answers are for"; color: theme.soft; font.pixelSize: 12 }
                    TextField { id: jobFind; objectName: "asJobFind"; Layout.preferredWidth: 190; implicitHeight: 32
                        placeholderText: "Type a company or a title"; placeholderTextColor: theme.faint
                        color: theme.ink; font.pixelSize: 12; selectByMouse: true; enabled: !assistantDialog.busy
                        Accessible.name: "Find one of your jobs by typing part of its company or title"
                        background: Rectangle { radius: 7; color: theme.surface; border.width: 1
                            border.color: assistantDialog.jobFindErr !== "" ? theme.crit : (jobFind.activeFocus ? theme.accent : theme.line) }
                        onTextEdited: assistantDialog.findJob(text)
                        Keys.onEscapePressed: { text = ""; assistantDialog.findJob("") } }
                    ThemedCombo { id: jobBox; objectName: "asJob"; Layout.fillWidth: true; enabled: !assistantDialog.busy
                        model: assistantDialog.jobs; textRole: "label"
                        onActivated: assistantDialog.jobId = assistantDialog.jobs[currentIndex] ? assistantDialog.jobs[currentIndex].id : "" } }
                Text { objectName: "asJobFindErr"; visible: assistantDialog.jobFindErr !== ""; text: assistantDialog.jobFindErr
                    Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.crit; font.pixelSize: 12 }
                RowLayout { Layout.fillWidth: true; spacing: 8
                    TextField { id: askBox; objectName: "asBox"; Layout.fillWidth: true; implicitHeight: 34
                        placeholderText: assistantDialog.practising ? "Your answer, as you would say it (or: stop)" : "Ask me: fill in the form · why did this score 62? · mark it applied"
                    placeholderTextColor: theme.faint
                        color: theme.ink; font.pixelSize: 13; selectByMouse: true; enabled: !assistantDialog.busy
                        background: Rectangle { radius: 9; color: theme.surface; border.width: 1
                            border.color: assistantDialog.askErr !== "" || askBox.text.length > assistantDialog.maxRequest ? theme.crit : (askBox.activeFocus ? theme.accent : theme.line) }
                        onTextEdited: assistantDialog.askErr = ""
                        Keys.onReturnPressed: assistantDialog.ask(text)
                        Keys.onEnterPressed: assistantDialog.ask(text) }
                    SmallButton { objectName: "asSend"; implicitHeight: 34; text: "Ask"; enabled: !assistantDialog.busy; onClicked: assistantDialog.ask(askBox.text) }
                    PillButton { objectName: "asFill"; primaryStyle: true; enabled: !assistantDialog.busy
                        text: assistantDialog.busy ? "Working…" : "Fill in the form"
                        onClicked: assistantDialog.ask("Fill in the form") } }
                Text { objectName: "asErr"; Layout.fillWidth: true; wrapMode: Text.WordWrap
                    font.pixelSize: assistantDialog.askErr !== "" ? 12 : 11; font.bold: assistantDialog.askErr !== ""
                    color: assistantDialog.askErr !== "" || askBox.text.length > assistantDialog.maxRequest ? theme.crit : theme.faint
                    text: assistantDialog.askErr !== "" ? assistantDialog.askErr
                        : askBox.text.length > assistantDialog.maxRequest ? (askBox.text.length - assistantDialog.maxRequest) + " characters too long (the limit is " + assistantDialog.maxRequest + ")"
                        : "I fill in the form that is open in " + assistantDialog.browser.name + " (change the browser on My details). Filling costs nothing; anything else you ask is one Claude call. I ask before I change anything of yours, and I never send a form." }
            }
        }

        // ── My answers ──
        ColumnLayout { visible: assistantDialog.page === "answers"; Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            Flickable {
                id: answersFlick
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                contentHeight: answersCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                FocusCatcher {}                // a press on empty space in the scroll area
                ColumnLayout {
                    id: answersCol
                    x: 16; y: 14; width: answersFlick.width - 32; spacing: 10
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                        text: "Questions that forms ask whatever the company, answered once in your own words. Claude can draft an answer from your CV; it counts as yours once you read it and save it. A question about one company (“Why do you want to work here?”) is drafted for each job when its form is filled in." }
                    RowLayout { Layout.fillWidth: true; spacing: 6
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 12; font.bold: true
                            text: answerModel.count === 0 ? "No answers of your own yet." : answerModel.count + (answerModel.count === 1 ? " answer" : " answers") }
                        SmallButton { objectName: "asAddAnswer"; text: "Add a question"; onClicked: assistantDialog.addAnswer("") } }
                    Flow { Layout.fillWidth: true; spacing: 6; visible: assistantDialog.starters.length > 0
                        Repeater { model: assistantDialog.starters
                            SmallButton { text: "+ " + modelData; onClicked: assistantDialog.addAnswer(modelData) } } }
                    Repeater {
                        model: answerModel
                        Rectangle { Layout.fillWidth: true; radius: 12; color: theme.surface2; border.width: 1
                            border.color: model.err !== "" ? theme.crit : (model.dirty ? theme.warn : theme.line)
                            implicitHeight: ansItem.implicitHeight + 24
                            ColumnLayout { id: ansItem; x: 12; y: 12; width: parent.width - 24; spacing: 6
                                TextField { id: qBox; Layout.fillWidth: true; implicitHeight: 32; color: theme.ink; font.pixelSize: 13; font.bold: true; selectByMouse: true
                                    placeholderText: "The question, as a form asks it"; placeholderTextColor: theme.faint
                                    Component.onCompleted: text = model.question
                                    background: Rectangle { radius: 7; color: theme.surface; border.width: 1; border.color: qBox.activeFocus ? theme.accent : theme.line }
                                    onTextEdited: assistantDialog.setAnswer(index, "question", text) }
                                Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1
                                    border.color: aBox.text.length > 3000 ? theme.crit : (aBox.activeFocus ? theme.accent : theme.line)
                                    implicitHeight: Math.max(64, aBox.implicitHeight + 16)
                                    TextEdit { id: aBox; x: 8; y: 8; width: parent.width - 16; wrapMode: TextEdit.Wrap; selectByMouse: true
                                        color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                                        text: model.answer
                                        onTextChanged: if (activeFocus) assistantDialog.setAnswer(index, "answer", text)
                                        Text { visible: aBox.text === ""; text: "Your answer"; color: theme.faint; font.pixelSize: 12 } } }
                                Text { visible: model.err !== "" || (model.check !== "" && model.check !== "replace"); Layout.fillWidth: true; wrapMode: Text.WordWrap
                                    color: model.err !== "" ? theme.crit : theme.warn; font.pixelSize: 11; font.bold: true
                                    text: model.err !== "" ? model.err : "Check: " + model.check }
                                RowLayout { Layout.fillWidth: true; spacing: 6
                                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                        text: model.dirty ? "Not saved yet." : "Kept: used when a form asks this." }
                                    SmallButton { enabled: !assistantDialog.busy; text: assistantDialog.busy ? "Asking Claude…" : "Draft with Claude"
                                        onClicked: assistantDialog.draftAnswer(index) }
                                    SmallButton { text: "Remove"; onClicked: assistantDialog.removeAnswer(index) }
                                    SmallButton { primaryStyle: true; visible: model.dirty; text: "Save"; onClicked: assistantDialog.saveAnswer(index) } }
                            }
                        }
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
                Text { objectName: "asAnswersNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap
                    font.pixelSize: assistantDialog.answersErr !== "" ? 12 : 11; font.bold: assistantDialog.answersErr !== ""
                    color: assistantDialog.answersErr !== "" ? theme.crit : (assistantDialog.answersNote !== "" ? theme.good : theme.faint)
                    text: assistantDialog.answersErr !== "" ? assistantDialog.answersErr
                        : assistantDialog.answersNote !== "" ? assistantDialog.answersNote
                        : "Kept encrypted on this Mac. Each one is marked for checking when it is used in a form." }
                SmallButton { text: "Close"; onClicked: assistantDialog.tryClose() }
            }
        }

        // ── My details ──
        ColumnLayout { visible: assistantDialog.page === "details"; Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            Flickable {
                id: detailsFlick
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                contentHeight: detailsCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                FocusCatcher {}                // a press on empty space in the scroll area
                ColumnLayout {
                    id: detailsCol
                    x: 16; y: 14; width: detailsFlick.width - 32; spacing: 10
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                        text: "What application forms are filled in with. Typed once, kept encrypted on this Mac. A field you leave empty is left empty in the form too."
                              + (assistantDialog.offered > 0 ? " Fields marked “from your CV” were read from your CV and are not saved yet: check them, then save." : "") }
                    // ── how the assistant works: which browser, and whether it looks by itself ──
                    GroupTitle { text: "How I work" }
                    RowLayout { Layout.fillWidth: true; spacing: 8
                        Text { text: "Browser"; color: theme.ink; font.pixelSize: 12; font.bold: true }
                        ThemedCombo { objectName: "asBrowser"; Layout.preferredWidth: 190; model: assistantDialog.browser.all || []; textRole: "name"
                            currentIndex: { var all = assistantDialog.browser.all || []; for (var i = 0; i < all.length; i++) if (all[i].key === assistantDialog.browser.key) return i; return 0; }
                            onActivated: assistantDialog.setBrowser(assistantDialog.browser.all[currentIndex].key) }
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 11
                            text: "Its switch, once: " + (assistantDialog.browser.switch || "") } }
                    RowLayout { Layout.fillWidth: true; spacing: 8
                        ThemedSwitch { objectName: "asWatch"; checked: assistantDialog.watching; onToggled: assistantDialog.setWatch(checked) }
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                            color: assistantDialog.watchProblem !== "" ? theme.crit : theme.soft; font.bold: assistantDialog.watchProblem !== ""
                            text: assistantDialog.watchProblem !== "" ? assistantDialog.watchProblem
                                : assistantDialog.watching ? "Noticing forms: while the app is open I look at the address of the tab in front in " + assistantDialog.browser.short + " every 20 seconds and tell you when it is the form of a job you track."
                                : "Notice application forms in " + assistantDialog.browser.short + " by myself (off: I look at the browser only when you ask)." } }
                    ColumnLayout { objectName: "asNotes"; Layout.fillWidth: true; spacing: 4; visible: noteModel.count > 0
                        Text { text: "What you asked me to remember"; color: theme.ink; font.pixelSize: 12; font.bold: true }
                        Repeater { model: noteModel
                            RowLayout { Layout.fillWidth: true; spacing: 8
                                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12; text: (index + 1) + ". " + model.text }
                                SmallButton { text: "Forget"; onClicked: assistantDialog.forgetNote(index) } } } }
                    GroupTitle { text: "My details"; Layout.topMargin: 6 }
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

                    // ── the jobs you have had ──
                    RowLayout { Layout.fillWidth: true; Layout.topMargin: 8; spacing: 6
                        GroupTitle { text: "Work experience"; Layout.fillWidth: true }
                        SmallButton { objectName: "asReadCv"; enabled: !assistantDialog.busy
                            text: assistantDialog.busy ? "Reading…" : "Read from my CV"; onClicked: assistantDialog.readCv() }
                        SmallButton { objectName: "asAddJob"; text: "Add a job"; onClicked: assistantDialog.addRow(jobModel, assistantDialog.jobCols, true) } }
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                        text: jobModel.count === 0 ? "No jobs listed. Forms that ask for your employer and job title are filled in from this list; several jobs may be current at once."
                              : "A form with several “Company” fields gets these in order: the current jobs first, then the others as listed here." }
                    RowsEditor { objectName: "asJobs"; Layout.fillWidth: true; store: jobModel; cols: assistantDialog.jobCols; listName: "experience"; withCurrent: true
                        problem: assistantDialog.problem; onChanged: assistantDialog.touched() }

                    // ── degrees ──
                    RowLayout { Layout.fillWidth: true; Layout.topMargin: 8; spacing: 6
                        GroupTitle { text: "Education"; Layout.fillWidth: true }
                        SmallButton { objectName: "asAddSchool"; text: "Add a degree"; onClicked: assistantDialog.addRow(schoolModel, assistantDialog.schoolCols, false) } }
                    Text { visible: schoolModel.count === 0; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                        text: "No degrees listed. Add each one: the highest first, as forms ask for them." }
                    RowsEditor { objectName: "asSchools"; Layout.fillWidth: true; store: schoolModel; cols: assistantDialog.schoolCols; listName: "education"
                        problem: assistantDialog.problem; onChanged: assistantDialog.touched() }

                    // ── the salary you ask for ──
                    GroupTitle { text: "Salary expectation"; Layout.topMargin: 8 }
                    RowLayout { Layout.fillWidth: true; spacing: 8
                        TextField { id: payBox; objectName: "asSalary"; Layout.preferredWidth: 150; implicitHeight: 32; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                            placeholderText: "60000"; placeholderTextColor: theme.faint
                            text: assistantDialog.salaryAmount
                            background: Rectangle { radius: 7; color: theme.surface; border.width: 1
                                border.color: assistantDialog.problem.field === "salary" ? theme.crit : (payBox.activeFocus ? theme.accent : theme.line) }
                            onTextEdited: { assistantDialog.salaryAmount = text; assistantDialog.touched(); } }
                        ThemedCombo { objectName: "asCurrency"; plainText: true; Layout.preferredWidth: 96; model: assistantDialog.currencies
                            currentIndex: Math.max(0, assistantDialog.currencies.indexOf(assistantDialog.salaryCurrency))
                            onActivated: { assistantDialog.salaryCurrency = assistantDialog.currencies[currentIndex]; assistantDialog.touched(); } }
                        ThemedCombo { objectName: "asPeriod"; plainText: true; Layout.preferredWidth: 130; model: ["per month", "per year"]
                            currentIndex: assistantDialog.salaryPeriod === "year" ? 1 : 0
                            onActivated: { assistantDialog.salaryPeriod = currentIndex === 1 ? "year" : "month"; assistantDialog.touched(); } }
                        Item { Layout.fillWidth: true } }
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                        color: assistantDialog.problem.field === "salary" ? theme.crit : theme.faint; font.bold: assistantDialog.problem.field === "salary"
                        text: assistantDialog.problem.field === "salary" ? (assistantDialog.problem.msg || "")
                            : assistantDialog.salaryAmount.trim() === "" ? "Gross, as a whole number. Left empty, a form that asks is answered from the figure in Options, or left to you."
                            : "A form that asks gets: " + assistantDialog.salaryAmount.trim().replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " " + assistantDialog.salaryCurrency + " gross per " + assistantDialog.salaryPeriod + "." }

                    // ── files a form may ask for besides the CV ──
                    RowLayout { Layout.fillWidth: true; Layout.topMargin: 8; spacing: 6
                        GroupTitle { text: "Files for forms"; Layout.fillWidth: true }
                        SmallButton { objectName: "asAddFile"; text: "Add a file…"; onClicked: filePick.open() } }
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                        text: "Certificates, diplomas, references. The assistant attaches the CV and the letter of the job by itself; these are shown in Finder after a fill, for you to drag onto the form." }
                    Repeater {
                        model: fileModel
                        ColumnLayout { id: fileRow; Layout.fillWidth: true; spacing: 2
                            readonly property bool wrong: assistantDialog.problem.field === "files." + index
                            RowLayout { Layout.fillWidth: true; spacing: 8
                                TextField { id: fileBox; Layout.preferredWidth: 220; implicitHeight: 30; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                    Component.onCompleted: text = model.label
                                    background: Rectangle { radius: 7; color: theme.surface; border.width: 1
                                        border.color: fileRow.wrong ? theme.crit : (fileBox.activeFocus ? theme.accent : theme.line) }
                                    onTextEdited: { fileModel.setProperty(index, "label", text); assistantDialog.touched(); } }
                                Text { Layout.fillWidth: true; wrapMode: Text.WrapAnywhere; color: theme.soft; font.pixelSize: 12; text: model.name }
                                SmallButton { text: "Remove"; onClicked: { fileModel.remove(index); assistantDialog.touched(); } } }
                            Text { visible: fileRow.wrong; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11; font.bold: true
                                text: assistantDialog.problem.msg || "" } } }
                    Text { visible: assistantDialog.problem.field === "files"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11; font.bold: true
                        text: assistantDialog.problem.msg || "" }
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
