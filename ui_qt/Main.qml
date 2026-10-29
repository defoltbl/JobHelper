import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects
import "views.js" as Views

ApplicationWindow {
    id: win
    visible: true
    width: 1200; height: 800
    minimumWidth: 940; minimumHeight: 620
    title: "JobHelper"
    color: theme.winbg

    property bool dark: true
    // how long what you type may be: from the back end, which checks the same numbers (the window keeps no copy)
    readonly property var limits: bridge.limits()
    property string beltPath: "M70,200 H840 Q915,200 915,315 Q915,430 840,430 H150"

    // autocomplete suggestion pools
    readonly property var euCities: [
        "Prague", "Brno", "Ostrava", "Plzeň", "Olomouc", "Liberec", "Bratislava", "Košice",
        "Vienna", "Graz", "Linz", "Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne",
        "Warsaw", "Kraków", "Wrocław", "Gdańsk", "Poznań", "Budapest", "Bucharest", "Sofia",
        "Amsterdam", "Rotterdam", "The Hague", "Brussels", "Luxembourg", "Dublin", "Paris",
        "Lyon", "Madrid", "Barcelona", "Lisbon", "Porto", "Milan", "Rome", "Zurich", "Geneva",
        "Copenhagen", "Stockholm", "Gothenburg", "Helsinki", "Oslo", "Tallinn", "Riga", "Vilnius",
        "Ljubljana", "Zagreb", "Athens", "Remote"
    ]
    readonly property var roleSuggestions: [
        "junior", "medior", "middle", "senior", "entry level", "graduate", "intern", "trainee",
        "software developer", "software engineer", "backend developer", "frontend developer",
        "full stack developer", "python developer", "java developer", "javascript developer",
        "c# developer", "golang developer", "web developer", "mobile developer", "android developer",
        "ios developer", "data scientist", "data analyst", "data engineer", "machine learning engineer",
        "ai engineer", "qa engineer", "test engineer", "automation engineer", "devops engineer",
        "site reliability engineer", "cloud engineer", "it support", "help desk", "service desk",
        "system administrator", "business analyst", "product manager", "ux designer"
    ]

    // ── live data (reassigned wholesale so bindings refresh) ──
    property var connData: ({})
    property var countsData: ({})
    property var usageData: ({})
    property var optsData: ({})
    property var lastRunData: ({})    // what the last search / scan did; kept between app starts
    property var upcomingData: []     // the next dated events (interviews, deadlines)
    // dates that are tomorrow or today are announced once a day, at start and every hour after
    // every five minutes, so a date with a time can also be announced about three hours and one hour before
    Timer { interval: 300 * 1000; repeat: true; running: true; onTriggered: { bridge.remind(); win.upcomingData = bridge.upcoming(); } }
    Timer { interval: 4000; running: true; onTriggered: bridge.remind() }
    Timer { interval: 300 * 1000; repeat: true; running: true; onTriggered: bridge.refreshWidget() }   // usage and "in 2 days" change
    property bool appRunning: false   // mirror of bridge.running (avoids teardown binding churn)
    property bool usageBusy: false
    property var schedData: ({})
    // parts that live in their own files but are reached by name from everywhere (the status line, the robots)
    property alias ticker: stagePanel.ticker
    readonly property Item a1: stagePanel.botA1
    readonly property Item a2: stagePanel.botA2
    readonly property Item a3: stagePanel.botA3
    readonly property Item a4: stagePanel.botA4
    readonly property Item a5: stagePanel.botA5
    readonly property QtObject appTheme: theme   // for the split files, where a robot's own `theme` property hides this id
    property bool connChecked: false  // first connection check has come back
    property var healthData: ({ ok: true, checks: [], problems: 0, message: "" })   // the start-up self-check
    property bool healthHidden: false
    property string healthNote: ""         // what the start-up check's button did (or why it did not)
    property bool healthNoteOk: false
    function fixHealth() {
        var r = bridge.fixProblem(healthData.action || "");
        healthNote = r.msg || ""; healthNoteOk = r.ok === true;
        if (r.ok === true) { healthHidden = false; reloadAll(); }     // the check runs again with the connections
    }
    property bool healthRan: false
    function showHealth() {
        var rows = (healthData.checks || []).map(function (c) {
            return { primary: c.name, secondary: c.ok ? "fine" : c.problem, badge: c.ok ? "" : "weak", value: c.ok ? "✓" : "!", actions: [],
                     group: c.ok ? "fine" : "needs attention" }; });
        tableDialog.show("Start-up check", rows, "", []);
    }

    // ── run progress (drives the status bar, the stepper and the gates) ──
    property string runMode: ""          // "search" | "scan" | "" (idle)
    property string stageKey: ""         // agent working right now
    property int stageDone: 0
    property int stageTotal: 0
    property real runProgress: 0         // 0..1 over the whole run
    property int elapsed: 0              // seconds since the run started
    property string runResult: ""        // "" | "ok" | "error" (shown briefly after a run)
    readonly property var stageOrder: ["a1", "a2", "a3", "a4"]
    readonly property var stageWeight: [0.04, 0.24, 0.68, 0.04]
    readonly property var agentInfo: ({
        a1: { name: "Profiler", color: theme.a1 }, a2: { name: "Scout", color: theme.a2 },
        a3: { name: "Scribe", color: theme.a3 }, a4: { name: "Tracker", color: theme.a4 },
        a5: { name: "Postman", color: theme.a5 } })
    readonly property color stageColor: stageKey !== "" ? agentInfo[stageKey].color : theme.steel
    function updateProgress() {
        if (runMode === "scan" || runMode === "rescore") {   // one stage: emails read, or jobs scored again, so far
            if (stageTotal > 0) runProgress = Math.max(runProgress, Math.min(1, stageDone / stageTotal));
            return;
        }
        var i = stageOrder.indexOf(stageKey);
        if (runMode !== "search" || i < 0) return;
        var base = 0;
        for (var k = 0; k < i; k++) base += stageWeight[k];
        var frac = stageTotal > 0 ? Math.min(1, stageDone / stageTotal) : 0;
        runProgress = Math.max(runProgress, base + stageWeight[i] * frac);
    }
    function fmtElapsed(sec) {
        var m = Math.floor(sec / 60), s2 = sec % 60;
        return (m < 10 ? "0" : "") + m + ":" + (s2 < 10 ? "0" : "") + s2;
    }
    Timer { interval: 1000; repeat: true; running: win.working; onTriggered: win.elapsed++ }
    Timer { id: resultFade; interval: 3200; onTriggered: { win.runResult = ""; win.runMode = ""; win.runProgress = 0; } }

    // ── shared motion (same feel in the welcome screen, dialogs and buttons) ──
    readonly property int motion: 260
    readonly property color dimColor: Qt.rgba(0, 0, 0, dark ? 0.42 : 0.22)
    readonly property bool dialogOpen: tableDialog.visible || optDialog.visible || schedDialog.visible || detailDialog.visible || limitDialog.visible || responseDialog.visible || letterDialog.visible || prepDialog.visible || helpDialog.visible || compareDialog.visible || formDialog.visible || prepEditDialog.visible || assistantDialog.visible || aboutDialog.visible
    property bool stopping: false        // Stop was pressed; waiting for the current step to end
    property bool paused: false          // the run waits because Claude's limit is used up
    property bool canResume: false       // ...and the limit has reset, so Resume works
    property var limitData: ({})
    readonly property bool working: appRunning && !paused     // agents are really doing something
    readonly property string limitWhy: !paused ? ""
        : canResume ? "The limit is back. Press to continue where the run stopped."
        : ("Can't resume yet: Claude's " + (limitData.window || "usage") + " limit is used up"
           + (limitData.used ? " (" + limitData.used + "%)" : "") + "."
           + (limitData.resets_at ? " It resets at " + limitData.resets_at + (limitData.resets_day ? " on " + limitData.resets_day : "") + "." : "")
           + " This button turns blue when you can continue.")
    property real backBlur: welcome.cover > 0 ? welcome.cover : (dialogOpen ? 0.45 : 0)
    Behavior on backBlur { enabled: welcome.cover === 0 || welcome.cover === 1
        NumberAnimation { duration: win.motion; easing.type: Easing.OutCubic } }

    function reloadAll() {
        countsData = bridge.counts();
        usageData = bridge.usageInfo();
        optsData = bridge.options();
        schedData = bridge.weeklySchedule();
        lastRunData = bridge.lastRun();
        upcomingData = bridge.upcoming();
        bridge.checkConnections();          // answers through onConnectionsReady
        bridge.refreshWidget();             // the macOS widget shows what the window shows
        if (!welcome.shown) bridge.warmUp();   // in the background: makes the first Insights view open at once
    }
    // Not while the welcome screen is up: preparing Insights is heavy enough to make its animation stutter.
    Timer { id: warmLater; interval: 900; onTriggered: bridge.warmUp() }
    Connections { target: welcome
        function onShownChanged() { if (!welcome.shown) warmLater.restart(); else warmLater.stop(); } }
    // ── input validation helpers ──
    // Find-as-you-type: does what was typed start one of the words of these names? "ge" finds Georgia and Germany, not
    // Algeria or Nigeria; "zealand" finds New Zealand; accents and case do not matter. The one rule for every list that
    // narrows as you type (the country picker, the suggestion fields).
    function plainWords(s) {
        return " " + String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9+#.]+/g, " ").trim();
    }
    function matchesStart(names, typed) {
        var q = plainWords(typed);
        if (q === " ") return true;
        var all = Array.isArray(names) ? names : [names];
        for (var i = 0; i < all.length; i++) if (plainWords(all[i]).indexOf(q) >= 0) return true;
        return false;
    }
    function hasNonLatin(s) {
        return /[぀-ヿ㐀-鿿가-힯Ѐ-ӿͰ-Ͽ؀-ۿ֐-׿฀-๿ऀ-ॿ]/.test(s || "");
    }
    // known job-role / tech vocabulary — an added role must share a word with it,
    // which rejects gibberish ("апаввар", "asdfgh") and most typos.
    readonly property var roleVocab: {
        var v = {};
        function add(arr) {
            for (var i = 0; i < arr.length; i++) {
                var ws = ("" + arr[i]).toLowerCase().split(/[^a-z0-9+#]+/);
                for (var j = 0; j < ws.length; j++) if (ws[j]) v[ws[j]] = true;
            }
        }
        add(roleSuggestions);
        add(["react", "node", "typescript", "php", "ruby", "rust", "kotlin", "swift", "sql", "database", "db",
             "security", "network", "networking", "infrastructure", "platform", "sre", "scrum", "project", "program",
             "manager", "consultant", "specialist", "architect", "lead", "apprentice", "helpdesk", "admin", "administrator",
             "fullstack", "ml", "llm", "nlp", "genai", "api", "rest", "microservices", "embedded", "firmware", "hardware",
             "linux", "windows", "aws", "azure", "gcp", "kubernetes", "docker", "spring", "django", "flask", "fastapi",
             "analytics", "analyst", "bi", "etl", "warehouse", "quant", "developer", "engineer", "programmer", "coder",
             "tester", "sdet", "support", "desk", "service", "it", "ai", "qa", "qe", "ux", "ui", "web", "mobile", "cloud", "data",
             "prague", "praha", "czech", "czechia", "republic", "english", "speaking", "remote", "hybrid", "onsite",
             "junior", "senior", "medior", "middle", "entry", "graduate", "intern", "trainee", "level", "scientist",
             "machine", "learning", "frontend", "backend", "software", "android", "ios", "golang", "go", "java", "javascript",
             "python", "csharp", "automation", "devops", "reliability", "designer", "business", "product", "system", "systems"]);
        return v;
    }
    function looksLikeRole(s) {
        var words = ("" + s).toLowerCase().split(/[^a-z0-9+#]+/).filter(function (w) { return w.length > 0; });
        return words.some(function (w) { return roleVocab[w] === true; });
    }
    function isEmail(s) { return /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test((s || "").trim()); }
    function cleanPw(s) { return (s || "").replace(/\s+/g, ""); }
    function isAppPassword(s) { return /^[a-z]{16}$/i.test(cleanPw(s)); }   // Gmail app password = 16 letters
    function isSlug(s) { return /^[a-z0-9][a-z0-9._-]{0,60}$/i.test((s || "").trim()); }
    function cityEN(c) {
        var m = { "praha": "Prague", "plzeň": "Pilsen", "plzen": "Pilsen", "wien": "Vienna",
                  "münchen": "Munich", "köln": "Cologne", "warszawa": "Warsaw" };
        return m[(c || "").toLowerCase()] || c || "";
    }
    function resetRobots() { [a1, a2, a3, a4, a5].forEach(function (r) { r.active = false; r.done = false; r.count = ""; }); }
    function setAgent(key, status, info) {
        var m = { a1: a1, a2: a2, a3: a3, a4: a4, a5: a5 };
        var r = m[key]; if (!r) return;
        if (status === "running") { r.active = true; r.done = false;
            stageKey = key; stageDone = 0; stageTotal = 0; updateProgress(); }
        else if (status === "done") { r.active = false; r.done = true; if (info) r.count = info; }
    }
    function handleStart(r, okMsg, mode) {
        if (r && r.ok) {
            resetRobots(); ticker.text = okMsg;
            resultFade.stop(); runMode = mode; runResult = ""; runProgress = 0; elapsed = 0; stageKey = ""; stopping = false;
            paused = false; canResume = false;
            return;
        }
        ticker.text = (r && r.msg) ? r.msg : "Couldn't start.";
        if (r && r.fix === "city") { optsData = bridge.options(); optDialog.open(); }     // straight to where the city is set
        if (r && r.fix) welcome.openCard();   // jump to the fix
    }
    function noScore(v) { return v === null || v === undefined; }
    // The status line is behind any open window, so a message written there while a window is
    // open is also shown on top of it for a few seconds: red when it says something went wrong.
    property bool quietTicker: false
    property string toastText: ""
    property bool toastBad: false
    function looksBad(t) {
        return /^(Couldn't|Could not|No |Not |Nothing |That |Choose |Paste |Enter |Unset |Log in |Add your )|could not|cannot|can't|isn't|not in the list|is missing|failed|still empty/i.test(t || "");
    }
    function showToast(t) { toastText = t; toastBad = looksBad(t); toastTimer.restart(); }
    // The same colour, fully see-through. A colour that fades to plain "transparent" fades
    // through black on the way, which leaves a dark shadow behind on a quick mouse move.
    function clearOf(c) { return Qt.rgba(c.r, c.g, c.b, 0); }
    // text from Claude or the user shown in a StyledText line: its own < and & are letters, not marks
    function escapeHtml(t) { return ("" + (t || "")).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
    function daysText(n) { return n + (n === 1 ? " day" : " days"); }
    function stopRun() { if (win.appRunning && !win.stopping && bridge.stopRun()) win.stopping = true; }
    function startRun() { if (win.appRunning) return; handleStart(bridge.runSearch(optsData), "Starting…", "search"); }
    function startScan() { if (win.appRunning) return; handleStart(bridge.scanEmail(), "Reading inbox…", "scan"); }
    // one scan over a longer period (from Options); the answer says why when it could not start
    function startScanBack(days) {
        if (win.appRunning) return { ok: false, msg: "A search or scan is running. Start this one when it has finished." };
        var r = bridge.scanEmailBack(days);
        if (r && r.ok) handleStart(r, "Reading inbox, last " + days + " days…", "scan");
        return r || { ok: false, msg: "The scan could not be started." };
    }
    function startRescore() { if (win.appRunning) return false; var r = bridge.rescoreAll(); handleStart(r, "Scoring again…", "rescore"); return !!(r && r.ok); }

    Timer { id: startUp; objectName: "startUp"; interval: 60; running: true; repeat: false
        onTriggered: { win.reloadAll(); win.refreshUsageNow(); } }
    Connections {
        target: bridge
        function onAgentChanged(key, status, info) { win.setAgent(key, status, info); }
        function onLogChanged(t) { win.quietTicker = true; ticker.text = t; win.quietTicker = false; }     // a run's own progress: no pop-up
        function onRunningChanged(r) { win.appRunning = r; if (!r) win.refreshIfDue(); }   // a reset during the run: asked about once it stops
        function onRunFinished(mode, summary) {
            ticker.text = summary; win.reloadAll();
            var bad = /^(Error|Couldn't|Email scan failed|Stopped)/.test(summary);
            win.runResult = bad ? "error" : "ok"; win.stageKey = ""; win.stopping = false;
            win.paused = false; win.canResume = false;
            [a1, a2, a3, a4, a5].forEach(function (r) { r.active = false; });   // nobody keeps working after a stop or an error
            if (!bad) win.runProgress = 1;
            resultFade.restart();
        }
        function onLimitChanged(info) {
            var was = win.paused;
            win.limitData = info; win.paused = info.paused === true; win.canResume = info.can_resume === true;
            var bots = { a1: a1, a2: a2, a3: a3, a4: a4, a5: a5 };
            if (win.paused && !was) {                       // just paused: robots rest, warn once, with sound
                [a1, a2, a3, a4, a5].forEach(function (r) { r.active = false; });
                limitDialog.open();
                bridge.playAlert();
            } else if (!win.paused && was && win.appRunning && bots[win.stageKey]) {
                bots[win.stageKey].active = true;           // resumed: the same agent picks up again
            }
        }
        function onProgressChanged(key, done, total) {
            if (key !== win.stageKey) return;
            win.stageDone = done; win.stageTotal = total; win.updateProgress();
        }
        function onConnectionsReady(info) {
            win.connData = info;
            // once per launch, and again until it is clean. Its own flag: the splash stops waiting after
            // 6 seconds and sets connChecked itself, and a slow sign-in check must not skip this.
            if (!win.healthRan || !win.healthData.ok) { win.healthData = info.health ? JSON.parse(info.health) : bridge.selfCheck(info.claude === true); win.healthRan = true; }
            win.connChecked = true;
        }
        function onUsageReady() { win.usageData = bridge.usageInfo(); win.usageBusy = false; bridge.refreshWidget(); }   // the widget too, at once
    }
    // When a limit's reset time passes, the card asks again (one small question to Claude): what is used after a reset is
    // not known, because Claude Code shares the subscription. While the app window is shown it looks every minute and
    // asks when the numbers are older than usage.REFRESH_AFTER (usageInfo's should_refresh); also when the app window
    // comes to the front. Never during a run, which brings its own numbers.
    function refreshUsageNow() { if (!win.usageBusy && !win.appRunning) { win.usageBusy = true; bridge.refreshUsage(); } }
    // the figures read again first (an old flag is out of date), then one question only when the back end says it is due
    function refreshIfDue() { win.usageData = bridge.usageInfo(); if (win.usageData.should_refresh === true) win.refreshUsageNow(); }
    Timer { id: usageTick; objectName: "usageTick"; interval: 60000; repeat: true      // looks only; the back end decides
        running: win.visible && win.visibility !== Window.Minimized
        onTriggered: win.refreshIfDue() }
    onActiveChanged: if (active) win.refreshIfDue()
    Timer { id: usageReset; objectName: "usageReset"
        interval: Math.max(1000, Math.min((win.usageData.next_reset_in || 0), 2000000) * 1000 + 1500)
        running: (win.usageData.next_reset_in || 0) > 0
        onTriggered: win.refreshIfDue() }

    // ── palette ──
    // Both sets of values are chosen so that small text reads against its surfaces (contrast 4.5:1 or more
    // for ink, soft, faint, steel, accent, good, warn, crit and the assistant's a6, on every surface and the inset,
    // and for a label on the accent); see tests/test_window_scores.py.
    QtObject {
        id: theme
        readonly property real disabledOpacity: 0.5     // a control that cannot be used now: one paleness for every button
        property color winbg: win.dark ? "#121922" : "#f3f6f9"
        property color surface: win.dark ? "#19222d" : "#ffffff"
        property color surface2: win.dark ? "#1f2a37" : "#f5f8fb"
        property color inset: win.dark ? "#141c25" : "#eceff3"
        property color ink: win.dark ? "#e7eef5" : "#182230"
        property color soft: win.dark ? "#9fb0c1" : "#5a6675"
        property color faint: win.dark ? "#8493a3" : "#606c7b"
        property color line: win.dark ? "#2a3644" : "#d6dde5"
        property color accent: win.dark ? "#f0a84a" : "#a35605"
        // a label on the accent (a main button, a picked chip) or on the green tick: the dark theme's
        // orange and green are light colours, so the label on them is dark there
        property color accentInk: win.dark ? "#1b1305" : "#ffffff"
        property color belt: win.dark ? "#2a3643" : "#c6cfd9"
        property color beltDark: win.dark ? "#1d2731" : "#aeb9c6"
        property color steel: win.dark ? "#8695a6" : "#616c7a"
        property color good: win.dark ? "#4ade80" : "#0f7a3d"
        property color goodbg: win.dark ? "#12301f" : "#e4f4ea"
        property color warnbg: win.dark ? "#2e2410" : "#f8eed8"
        property color warn: win.dark ? "#f0b84a" : "#96600a"
        property color crit: win.dark ? "#f87171" : "#c02626"
        property color critbg: win.dark ? "#331717" : "#f8e3e3"
        property color infobg: win.dark ? "#142338" : "#e5eefc"
        property color a1: "#3b82f6"; property color a2: "#10b981"
        property color a3: "#8b5cf6"; property color a4: "#fb923c"; property color a5: "#f43f5e"
        property color a6: win.dark ? "#22d3ee" : "#067590"       // the assistant
        property color night: "#0d141c"                             // the robots' face screens, and the dark label on a bright badge
        property color resume: "#2563eb"                            // Resume: a darker blue than the robots', so its white label reads
        property color paper: win.dark ? "#eef2f7" : "#ffffff"      // the sheets that travel on the belt
        property color paperLine: "#8b97a5"                         // the lines of writing on a sheet
        // the label on a coloured badge: white or near-black, whichever reads better on that colour
        function labelOn(c) {
            if (typeof c === "string") c = Qt.color(c);        // a colour given as "#rrggbb" text, too
            function lin(v) { return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
            function lum(k) { return 0.2126 * lin(k.r) + 0.7152 * lin(k.g) + 0.0722 * lin(k.b); }
            var dark = night, l = lum(c);
            return (1.05 / (l + 0.05)) >= ((l + 0.05) / (lum(dark) + 0.05)) ? "#ffffff" : "" + dark;
        }
    }

    // The building blocks (buttons, fields, the dialog shell, the gates) are each in their own file in ui_qt/.

    // ── layout ──
    ColumnLayout {
        id: mainUi
        anchors.fill: parent
        spacing: 0
        // recedes and blurs behind the welcome screen and (lighter) behind dialogs
        scale: 1 - 0.035 * welcome.cover
        layer.enabled: win.backBlur > 0.004
        layer.effect: MultiEffect { blurEnabled: true; blur: win.backBlur; blurMax: 40; autoPaddingEnabled: false }

        // body
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0

            NavPanel { id: navPanel }

            StagePanel { id: stagePanel }

            StatusPanel { id: statusPanel }
        }

        PipelineBar { id: pipelineBar }
    }

    // ───────────────────────── view data table ─────────────────────────
    function badgeColor(kind) {
        return kind === "strong" || kind === "interview" || kind === "offer" || kind === "working" ? theme.good
             : kind === "rejected" || kind === "rejection" || kind === "not working" || kind === "drop?" ? theme.crit
             : kind === "moderate" || kind === "waiting" || kind === "on_hold" || kind === "not yet" || kind === "weak" ? theme.warn
             : kind === "stretch" || kind === "skipped" ? theme.steel : theme.a1;
    }
    function badgeBg(kind) {
        return kind === "strong" || kind === "interview" || kind === "offer" || kind === "working" ? theme.goodbg
             : kind === "rejected" || kind === "rejection" || kind === "not working" || kind === "drop?" ? theme.critbg
             : kind === "moderate" || kind === "waiting" || kind === "on_hold" || kind === "not yet" || kind === "weak" ? theme.warnbg : theme.infobg;
    }
    property string lastView: ""
    function refreshOpenView() { if (tableDialog.visible && lastView !== "") openView(lastView); }

    // ── which window is on top: the Esc key belongs to it alone ──
    // Each window is numbered when it opens; of the windows still shown, the one opened last is on top. A window
    // asks onTop(itself) before it takes Esc, so two windows never both take it, and the one in front always does.
    property int openSeq: 0
    property var openedAt: ({})
    readonly property var windows: [tableDialog, detailDialog, compareDialog, formDialog, assistantDialog, prepEditDialog, helpDialog, prepDialog, letterDialog, responseDialog, limitDialog, optDialog, aboutDialog, remoteDialog, schedDialog]
    Component.onCompleted: {
        for (var i = 0; i < windows.length; i++) {
            (function (w) { w.aboutToShow.connect(function () { win.openedAt[w.objectName] = ++win.openSeq; }); })(windows[i]);
        }
    }
    function onTop(w) {
        var mine = win.openSeq >= 0 ? (win.openedAt[w.objectName] || 0) : 0;      // reading openSeq keeps a binding up to date
        for (var i = 0; i < windows.length; i++) {
            var other = windows[i];
            if (other !== w && other.visible && (win.openedAt[other.objectName] || 0) > mine) return false;
        }
        return w.visible;
    }
    function openView(k) { Views.open(k); }       // the lists themselves are in views.js

    TableDialog { id: tableDialog }

    // ───────────────────────── one job in full ─────────────────────────
    DetailDialog { id: detailDialog }

    // ───────────────────────── master CV next to the adapted one ─────────────────────────
    CompareDialog { id: compareDialog }

    // ───────────────────────── answers to repeated form questions ─────────────────────────
    FormAnswersDialog { id: formDialog }
    AssistantDialog { id: assistantDialog }
    PrepEditDialog { id: prepEditDialog }

    // ───────────────────────── a message on top of an open window ─────────────────────────
    Connections { target: ticker
        function onTextChanged() { if (win.dialogOpen && !win.quietTicker && ticker.text !== "") win.showToast(ticker.text); } }
    Timer { id: toastTimer; interval: 4200; onTriggered: win.toastText = "" }
    // it belongs to the windows it was shown over: when the last one closes it ends, so it never comes back on the next
    // window (the status line keeps the words)
    onDialogOpenChanged: if (!dialogOpen) { toastTimer.stop(); toastText = ""; }
    // It keeps clear of the note and buttons of the window in front: above that window's footer when the window
    // reaches down to the bottom of the screen (a small screen), else at the bottom as before.
    function footerOf(item, depth) {            // the shown DialogFooter in a window (in an open tab, for the assistant)
        if (!item || !item.visible || depth > 4) return null;
        if (item.dialogFooter === true) return item;
        for (var i = 0; i < item.children.length; i++) { var f = footerOf(item.children[i], depth + 1); if (f) return f; }
        return null;
    }
    function toastBottom(tall) {
        var lowest = win.height - 26;
        var shown = win.toastText;                          // reading the text measures again for each new message
        for (var i = 0; i < windows.length; i++) {
            var w = windows[i];
            if (!onTop(w)) continue;
            if (w.y + w.height + 8 <= lowest - tall) return lowest;          // room below the window
            var foot = footerOf(w.contentItem, 0);
            return foot ? Math.min(lowest, foot.mapToItem(null, 0, 0).y - 8) : lowest;
        }
        return lowest;
    }
    Rectangle {
        id: toast; objectName: "toast"
        parent: Overlay.overlay; z: 10000
        visible: opacity > 0; opacity: win.toastText !== "" && win.dialogOpen ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160 } }
        width: Math.min(620, win.width - 80); height: toastT.implicitHeight + 22
        x: (win.width - width) / 2; y: win.toastBottom(height) - height
        radius: 11; color: win.toastBad ? theme.critbg : theme.surface2
        border.width: 1; border.color: win.toastBad ? theme.crit : theme.steel
        Text { id: toastT; objectName: "toastText"; x: 14; y: 11; width: parent.width - 28; wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter; color: theme.ink; font.pixelSize: 12; font.bold: win.toastBad
            text: win.toastText }
        TapHandler { onTapped: win.toastText = "" }
    }

    // ───────────────────────── help ─────────────────────────
    HelpDialog { id: helpDialog }

    // ───────────────────────── interview preparation ─────────────────────────
    PrepDialog { id: prepDialog }

    // ───────────────────────── edit a letter the app wrote ─────────────────────────
    LetterDialog { id: letterDialog }

    // ───────────────────────── one reply in full ─────────────────────────
    ResponseDialog { id: responseDialog }

    // ───────────────────────── limit warning ─────────────────────────
    LimitDialog { id: limitDialog }

    // ───────────────────────── welcome / account ─────────────────────────
    // Covers the app at launch (splash → card) and reopens from the account
    // chip. Sign-in itself belongs to the Claude CLI; this only starts it and
    // reacts when the connection checks turn green.
    function applyCv(url) {
        var r = bridge.setMasterCV(url);
        welcome.cvErr = (r && r.ok) ? "" : (r && r.msg ? r.msg : "Couldn't set that file as your CV.");
        ticker.text = (r && r.ok) ? ("✓ Master CV updated – " + r.name) : welcome.cvErr;
        bridge.checkConnections();
    }
    FileDialog {
        id: cvDialog
        title: "Choose your master CV"
        nameFilters: ["CV documents (*.docx *.pdf *.txt)"]
        onAccepted: win.applyCv(selectedFile.toString())
    }

    // status dot: number → spinner → check that draws itself

    WelcomeOverlay { id: welcome }

    // ───────────────────────── options (macOS-style) ─────────────────────────
    OptionsDialog { id: optDialog }
    AboutYouDialog { id: aboutDialog }
    RemoteCountriesDialog { id: remoteDialog }      // opened from Options: countries for remote jobs

    // ───────────────────────── weekly schedule ─────────────────────────
    ScheduleDialog { id: schedDialog }
}
