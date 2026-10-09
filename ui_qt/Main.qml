import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

ApplicationWindow {
    id: win
    visible: true
    width: 1200; height: 800
    minimumWidth: 940; minimumHeight: 620
    title: "JobHelper"
    color: theme.winbg

    property bool dark: true
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
    property bool appRunning: false   // mirror of bridge.running (avoids teardown binding churn)
    property bool usageBusy: false
    property var schedData: ({})
    readonly property QtObject appTheme: theme   // for the split files, where a robot's own `theme` property hides this id
    property bool connChecked: false  // first connection check has come back
    property var healthData: ({ ok: true, checks: [], problems: 0, message: "" })   // the start-up self-check
    property bool healthHidden: false
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
    readonly property bool dialogOpen: tableDialog.visible || optDialog.visible || schedDialog.visible || detailDialog.visible || limitDialog.visible || responseDialog.visible || letterDialog.visible || prepDialog.visible || helpDialog.visible || compareDialog.visible || formDialog.visible || prepEditDialog.visible
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
        bridge.warmUp();                    // in the background: makes the first Insights view open at once
    }
    // ── input validation helpers ──
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
    function daysText(n) { return n + (n === 1 ? " day" : " days"); }
    function stopRun() { if (win.appRunning && !win.stopping && bridge.stopRun()) win.stopping = true; }
    function startRun() { if (win.appRunning) return; handleStart(bridge.runSearch(optsData), "Starting…", "search"); }
    function startScan() { if (win.appRunning) return; handleStart(bridge.scanEmail(), "Reading inbox…", "scan"); }
    function startRescore() { if (win.appRunning) return false; var r = bridge.rescoreAll(); handleStart(r, "Scoring again…", "rescore"); return !!(r && r.ok); }

    Timer { interval: 60; running: true; repeat: false
        onTriggered: { win.reloadAll(); win.usageBusy = true; bridge.refreshUsage(); } }
    Connections {
        target: bridge
        function onAgentChanged(key, status, info) { win.setAgent(key, status, info); }
        function onLogChanged(t) { win.quietTicker = true; ticker.text = t; win.quietTicker = false; }     // a run's own progress: no pop-up
        function onRunningChanged(r) { win.appRunning = r; }
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
            if (!win.healthRan || !win.healthData.ok) { win.healthData = bridge.selfCheck(info.claude === true); win.healthRan = true; }
            win.connChecked = true;
        }
        function onUsageReady() { win.usageData = bridge.usageInfo(); win.usageBusy = false; }
    }

    // ── palette ──
    // Both sets of values are chosen so that small text reads against its surfaces (contrast 4.5:1 or more
    // for ink, soft, faint, good, warn and crit, and for a label on the accent); see tests/test_ui_qml.py.
    QtObject {
        id: theme
        property color winbg: win.dark ? "#121922" : "#f3f6f9"
        property color surface: win.dark ? "#19222d" : "#ffffff"
        property color surface2: win.dark ? "#1f2a37" : "#f5f8fb"
        property color inset: win.dark ? "#141c25" : "#eceff3"
        property color ink: win.dark ? "#e7eef5" : "#182230"
        property color soft: win.dark ? "#9fb0c1" : "#5a6675"
        property color faint: win.dark ? "#8493a3" : "#657181"
        property color line: win.dark ? "#2a3644" : "#d6dde5"
        property color accent: win.dark ? "#f0a84a" : "#b45f06"
        // a label on the accent (a main button, a picked chip) or on the green tick: the dark theme's
        // orange and green are light colours, so the label on them is dark there
        property color accentInk: win.dark ? "#1b1305" : "#ffffff"
        property color belt: win.dark ? "#2a3643" : "#c6cfd9"
        property color beltDark: win.dark ? "#1d2731" : "#aeb9c6"
        property color steel: win.dark ? "#8695a6" : "#6b7787"
        property color good: win.dark ? "#4ade80" : "#0f7a3d"
        property color goodbg: win.dark ? "#12301f" : "#e4f4ea"
        property color warnbg: win.dark ? "#2e2410" : "#f8eed8"
        property color warn: win.dark ? "#f0b84a" : "#96600a"
        property color crit: win.dark ? "#f87171" : "#c02626"
        property color critbg: win.dark ? "#331717" : "#f8e3e3"
        property color infobg: win.dark ? "#142338" : "#e5eefc"
        property color a1: "#3b82f6"; property color a2: "#10b981"
        property color a3: "#8b5cf6"; property color a4: "#fb923c"; property color a5: "#f43f5e"
    }

    // ── reusable buttons ──

    // ── macOS-System-Settings-style building blocks ──
    // dropdown (optionally type-to-complete via `editable`)
    // free-text field with a case-insensitive suggestion dropdown; Enter / a click
    // adds the value. Used for adding search roles.
    // on/off switch that follows the theme: accent track when on, clear knob travel
    // modern number stepper: rounded, −/+ with hover + pointer cursor, subtle
    // accent focus (no harsh blue), editable text you can select and type into.
    // zero-padded time field (HH / MM). Unlike a SpinBox it KEEPS an out-of-range
    // value visible, turns the border red, and sets `valid=false` so Save can be
    // blocked with an explicit error (instead of silently clamping).

    // A short list of words the user edits as chips (skip words, exceptions).

    // A factory gate straddling the belt: an inverted-U portal the belt runs
    // through. Jobs come out of the input gate and go into the output gate; the
    // lamp on the beam blinks while the line runs and the opening lights up each
    // time a package passes. The belt line sits at local y = 64.

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

            // ── NAV ──
            Rectangle {
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
                            Layout.fillWidth: true; implicitHeight: 40; radius: 10
                            objectName: "navRow_" + modelData.k
                            color: navMouse.containsMouse ? theme.surface2 : win.clearOf(theme.surface2)
                            Behavior on color { ColorAnimation { duration: 90 } }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 11; anchors.rightMargin: 11; spacing: 10
                                Rectangle { implicitWidth: 9; implicitHeight: 9; radius: 3; color: modelData.dot }
                                ColumnLayout { Layout.fillWidth: true; spacing: 0
                                    Text { text: modelData.label; color: theme.ink; font.pixelSize: 14
                                        Layout.fillWidth: true; elide: Text.ElideRight }
                                    Text { visible: modelData.k === "app" && (countsData.duplicates || 0) > 0
                                        text: (countsData.duplicates || 0) + ((countsData.duplicates || 0) === 1 ? " possible duplicate" : " possible duplicates")
                                        color: theme.steel; font.pixelSize: 10; font.bold: true
                                        Layout.fillWidth: true; elide: Text.ElideRight }
                                    Text { visible: modelData.k === "app" && (countsData.followups || 0) > 0
                                        text: (countsData.followups || 0) + " to follow up"
                                        color: theme.warn; font.pixelSize: 10; font.bold: true
                                        Layout.fillWidth: true; elide: Text.ElideRight }
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
                                Text { visible: modelData.k === "ana" || modelData.k === "ins"; anchors.centerIn: parent
                                    text: modelData.k === "ana" ? "▦" : "✦"; color: theme.soft; font.pixelSize: 13 }
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
                        Layout.fillWidth: true; implicitHeight: 56; radius: 13
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
                                Rectangle { width: 12; height: 12; radius: 6; x: 24; y: 24
                                    color: !win.connChecked ? theme.steel : (chip.allOk ? theme.good : theme.crit)
                                    border.color: theme.surface; border.width: 2 }
                            }
                            ColumnLayout { Layout.fillWidth: true; spacing: 0
                                Text { Layout.fillWidth: true; elide: Text.ElideMiddle; color: theme.ink; font.pixelSize: 12; font.bold: true
                                    text: !win.connChecked ? "Checking…"
                                        : connData.claude === true ? (connData.claude_email || "Claude account") : "Not signed in" }
                                Text { Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: 11
                                    color: !win.connChecked || chip.allOk ? theme.faint : theme.crit
                                    text: !win.connChecked ? "connections"
                                        : connData.paid_api === true ? "Paid API key is set"
                                        : connData.claude !== true ? "Sign in to Claude"
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
                                     (optsData.all_languages === true) ? "All languages" : "English only",
                                     (optsData.include_remote === true) ? "+ Remote" : "",
                                     (optsData.full_time_only === false) ? "Part-time too" : "Full-time only",
                                     (optsData.max_age_days && optsData.max_age_days > 0) ? ("≤ " + optsData.max_age_days + " days old") : "Any date",
                                     "Letters from " + (optsData.threshold !== undefined ? optsData.threshold : 50) + "+"
                                   ].filter(function (t) { return t !== ""; })
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

            // ── STAGE ──
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: theme.inset
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 16; spacing: 14
                    // one clear line when the start-up check found something; nothing when all is well
                    Rectangle { objectName: "healthBanner"; visible: win.healthData.ok === false && !win.healthHidden
                        Layout.fillWidth: true; radius: 10; color: theme.critbg; border.color: theme.crit; border.width: 1
                        implicitHeight: hbRow.implicitHeight + 16
                        RowLayout { id: hbRow; x: 12; y: 8; width: parent.width - 24; spacing: 10
                            Text { objectName: "healthText"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 12
                                text: win.healthData.message || "" }
                            SmallButton { visible: (win.healthData.problems || 0) > 1; text: "Show all"; onClicked: win.showHealth() }
                            SmallButton { text: "Hide"; onClicked: win.healthHidden = true }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 10
                        Text { text: "Assembly line"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                        Rectangle {
                            visible: connData.paid_api === true
                            radius: 999; color: theme.critbg; implicitHeight: 24; implicitWidth: paidTxt.width + 18
                            Text { id: paidTxt; anchors.centerIn: parent; text: "Paid API key set"; color: theme.crit; font.pixelSize: 11; font.bold: true }
                        }
                        Item { Layout.fillWidth: true }
                        // paused on Claude's limit: Resume replaces Stop. Grey (with the reason on
                        // hover) until the limit resets, then blue and clickable.
                        Rectangle {
                            id: resumeBtn; objectName: "resumeButton"
                            visible: win.paused
                            implicitHeight: 34; implicitWidth: resumeRow.implicitWidth + 28; radius: 10
                            color: win.canResume ? (resumeMa.containsMouse ? Qt.lighter(theme.a1, 1.1) : theme.a1) : theme.inset
                            border.width: 1; border.color: win.canResume ? win.clearOf(theme.line) : theme.line
                            scale: resumeMa.pressed && win.canResume ? 0.96 : 1
                            Behavior on color { ColorAnimation { duration: win.motion } }
                            Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                            readonly property string text: "▶ Resume"
                            Row { id: resumeRow; anchors.centerIn: parent; spacing: 6
                                Text { text: resumeBtn.text; font.pixelSize: 13; font.bold: true
                                    color: win.canResume ? "#ffffff" : theme.faint } }
                            MouseArea { id: resumeMa; anchors.fill: parent; hoverEnabled: true
                                cursorShape: win.canResume ? Qt.PointingHandCursor : Qt.ForbiddenCursor
                                onClicked: if (win.canResume) bridge.resumeRun() }
                            ToolTip {
                                id: resumeTip; objectName: "resumeTip"
                                visible: resumeMa.containsMouse; delay: 120; timeout: -1
                                y: resumeBtn.height + 8; x: Math.round((resumeBtn.width - width) / 2)
                                text: win.limitWhy
                                contentItem: Text { text: resumeTip.text; color: theme.ink; font.pixelSize: 12; wrapMode: Text.WordWrap
                                    width: Math.min(300, implicitWidth) }
                                background: Rectangle { radius: 9; color: theme.surface2
                                    border.width: 1; border.color: win.canResume ? theme.a1 : theme.warn }
                            }
                        }
                        SmallButton { objectName: "stopWhilePaused"; visible: win.paused; text: win.stopping ? "Stopping…" : "■ Stop"
                            enabled: !win.stopping; implicitHeight: 34; onClicked: win.stopRun() }
                        PillButton { objectName: "runButton"; primaryStyle: !win.appRunning; visible: !win.paused
                            tint: win.appRunning ? theme.crit : "transparent"; enabled: !win.stopping
                            text: win.stopping ? "Stopping…" : (win.appRunning ? "■ Stop" : "▶ Run search")
                            onClicked: win.appRunning ? win.stopRun() : win.startRun() }
                        PillButton { text: "Scan email"; glyph: "mail"; tint: theme.a1; enabled: !win.appRunning; onClicked: win.startScan() }
                        Rectangle {
                            implicitWidth: 34; implicitHeight: 34; radius: 9; color: theme.surface2; border.color: theme.line; border.width: 1
                            Text { anchors.centerIn: parent; text: win.dark ? "☀" : "☾"; color: theme.soft; font.pixelSize: 15 }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: win.dark = !win.dark }
                        }
                    }

                    // factory floor
                    Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        radius: 14; color: theme.surface; border.color: theme.line; border.width: 1; clip: true

                        Item {
                            id: design
                            width: 1000; height: 500
                            anchors.centerIn: parent
                            property real beltT: 0
                            scale: Math.min((parent.width - 28) / 1000, (parent.height - 28) / 500, 1.6)

                            NumberAnimation on beltT { running: win.working; from: 0; to: 1; duration: 7000; loops: Animation.Infinite }

                            Shape {
                                anchors.fill: parent
                                ShapePath { strokeColor: theme.beltDark; strokeWidth: 40; fillColor: "transparent"
                                    capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin; PathSvg { path: win.beltPath } }
                                ShapePath { strokeColor: theme.belt; strokeWidth: 30; fillColor: "transparent"
                                    capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin; PathSvg { path: win.beltPath } }
                                ShapePath { strokeColor: theme.steel; strokeWidth: 30; fillColor: "transparent"
                                    capStyle: ShapePath.FlatCap; strokeStyle: ShapePath.DashLine; dashPattern: [0.4, 2.0]
                                    property real doff: 0; dashOffset: doff
                                    PathSvg { path: win.beltPath }
                                    NumberAnimation on doff { running: win.working; from: 0; to: 4.8; duration: 550; loops: Animation.Infinite } }
                            }

                            // packages riding the belt
                            PathInterpolator { id: pi0; progress: (design.beltT + 0.0) % 1; path: Path { PathSvg { path: win.beltPath } } }
                            PathInterpolator { id: pi1; progress: (design.beltT + 0.25) % 1; path: Path { PathSvg { path: win.beltPath } } }
                            PathInterpolator { id: pi2; progress: (design.beltT + 0.5) % 1; path: Path { PathSvg { path: win.beltPath } } }
                            PathInterpolator { id: pi3; progress: (design.beltT + 0.75) % 1; path: Path { PathSvg { path: win.beltPath } } }
                            // each package starts plain at the input gate and takes the colour
                            // of the last station it passed; it fades in/out inside the gates
                            Repeater {
                                model: [pi0, pi1, pi2, pi3]
                                Rectangle {
                                    readonly property real p: modelData.progress
                                    readonly property color tone: p > 0.88 ? theme.a5 : p > 0.744 ? theme.a4
                                        : p > 0.352 ? theme.a3 : p > 0.227 ? theme.a2 : p > 0.10 ? theme.a1 : theme.accent
                                    visible: win.appRunning; width: 20; height: 22; radius: 4
                                    opacity: Math.max(0, Math.min(1, p * 28, (1 - p) * 28))
                                    color: win.dark ? "#eef2f7" : "#ffffff"
                                    border.color: tone; border.width: 1.6
                                    x: modelData.x - 10; y: modelData.y - 11
                                    Behavior on border.color { ColorAnimation { duration: 220 } }
                                    Rectangle { x: 0; y: 0; width: parent.width; height: 5; radius: 2; color: parent.tone
                                        Behavior on color { ColorAnimation { duration: 220 } } }
                                    Column { x: 4; y: 8; spacing: 2.5
                                        Repeater { model: [12, 8, 11]
                                            Rectangle { width: modelData; height: 1.8; radius: 0.9; color: "#8b97a5" } } }
                                }
                            }

                            // gates at the two ends of the line (belt runs through them)
                            Gate { x: 48; y: 136; ag: theme.a2; kind: "in"; gtitle: "Your CV"; caption: "INPUT"
                                running: win.working
                                flash: Math.max(0, 1 - ((design.beltT * 4) % 1) * 6) }
                            Gate { x: 103; y: 366; ag: theme.a4; kind: "out"; gtitle: "Applications"; caption: "OUTPUT"
                                running: win.working
                                badge: countsData.applications !== undefined ? "" + countsData.applications : ""
                                flash: Math.max(0, (((design.beltT * 4) % 1) - 0.84) * 6) }

                            // robots (hover one for its name / role / result)
                            Robot { id: a1; objectName: "a1"; kind: "cv"; theme: theme; ag: theme.a1; title: "Profiler"; role: "reads your CV"; agent: "AGENT 1"; x: 190; y: 112 }
                            Robot { id: a2; objectName: "a2"; kind: "search"; theme: theme; ag: theme.a2; title: "Scout"; role: "searches jobs"; agent: "AGENT 2"; x: 410; y: 112 }
                            Robot { id: a3; objectName: "a3"; kind: "write"; theme: theme; ag: theme.a3; title: "Scribe"; role: "letters & CVs"; agent: "AGENT 3"; x: 630; y: 112 }
                            Robot { id: a5; objectName: "a5"; kind: "mail"; theme: theme; ag: theme.a5; title: "Postman"; role: "reads replies"; agent: "AGENT 5"; x: 300; y: 342 }
                            Robot { id: a4; objectName: "a4"; kind: "table"; theme: theme; ag: theme.a4; title: "Tracker"; role: "builds tables"; agent: "AGENT 4"; x: 540; y: 342 }
                        }
                    }

                    // status bar: what is happening, which step, how far, how long
                    Rectangle {
                        id: statusBar
                        readonly property bool busy: win.working
                        readonly property bool showBar: win.appRunning || win.runResult !== ""
                        readonly property color tone: win.runResult === "ok" ? theme.good
                            : win.runResult === "error" ? theme.crit
                            : win.paused ? theme.warn : (busy ? win.stageColor : theme.steel)
                        Layout.fillWidth: true; implicitHeight: 46; radius: 12
                        color: theme.surface; border.width: 1
                        border.color: (busy || win.paused) ? Qt.rgba(tone.r, tone.g, tone.b, 0.55) : theme.line
                        Behavior on border.color { ColorAnimation { duration: win.motion } }
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 10
                            anchors.bottomMargin: statusBar.showBar ? 5 : 0
                            Behavior on anchors.bottomMargin { NumberAnimation { duration: win.motion; easing.type: Easing.OutCubic } }
                            // step pill
                            Rectangle {
                                implicitHeight: 24; radius: 12; implicitWidth: pillRow.implicitWidth + 18
                                color: Qt.rgba(statusBar.tone.r, statusBar.tone.g, statusBar.tone.b, 0.16)
                                Behavior on color { ColorAnimation { duration: win.motion } }
                                Behavior on implicitWidth { NumberAnimation { duration: win.motion; easing.type: Easing.OutCubic } }
                                Row { id: pillRow; anchors.centerIn: parent; spacing: 6
                                    Rectangle { id: pillDot; width: 8; height: 8; radius: 4; color: statusBar.tone; anchors.verticalCenter: parent.verticalCenter
                                        SequentialAnimation on opacity { running: statusBar.busy; loops: Animation.Infinite
                                            NumberAnimation { to: 0.3; duration: 600 } NumberAnimation { to: 1; duration: 600 }
                                            onStopped: pillDot.opacity = 1 } }
                                    Text { color: statusBar.tone; font.pixelSize: 11; font.bold: true
                                        text: win.runResult === "ok" ? "Done" : win.runResult === "error" ? "Stopped"
                                            : win.paused ? (win.canResume ? "Paused · ready to resume" : "Paused · limit reached")
                                            : !statusBar.busy ? "Idle"
                                            : win.stopping ? "Stopping"
                                        : win.stageKey === "" ? "Starting"
                                            : win.runMode === "search"
                                                ? ("Step " + (win.stageOrder.indexOf(win.stageKey) + 1) + " of 4 · " + win.agentInfo[win.stageKey].name)
                                                : win.agentInfo[win.stageKey].name }
                                }
                            }
                            Text { id: ticker; text: "Line idle. Press Run search to start the pipeline."
                                color: theme.soft; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
                            Text { visible: statusBar.showBar && (win.runMode === "search" || win.runProgress > 0)
                                text: Math.round(win.runProgress * 100) + "%"
                                color: statusBar.tone; font.pixelSize: 12; font.bold: true
                                horizontalAlignment: Text.AlignRight; Layout.preferredWidth: 34 }
                            Text { id: clock; color: theme.faint; font.pixelSize: 11
                                property string now: ""
                                text: statusBar.showBar ? win.fmtElapsed(win.elapsed) : now
                                Timer { interval: 1000; running: true; repeat: true; triggeredOnStart: true
                                    onTriggered: clock.now = Qt.formatTime(new Date(), "HH:mm:ss") } }
                        }
                        // progress track along the bottom edge
                        Rectangle {
                            id: track
                            x: 12; y: parent.height - 8; width: parent.width - 24; height: 4; radius: 2
                            color: theme.inset; clip: true
                            opacity: statusBar.showBar ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: win.motion } }
                            readonly property bool indeterminate: statusBar.busy && win.runMode !== "search" && win.stageTotal === 0
                            Rectangle {                       // determinate fill
                                visible: !track.indeterminate
                                height: parent.height; radius: 2; color: statusBar.tone
                                width: parent.width * (win.runResult === "ok" ? 1 : win.runProgress)
                                Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                                Behavior on color { ColorAnimation { duration: win.motion } }
                            }
                            Rectangle {                       // sweep: the whole bar when indeterminate, a sheen otherwise
                                id: sweep
                                visible: statusBar.busy
                                height: parent.height; radius: 2
                                width: track.indeterminate ? parent.width * 0.28 : 46
                                color: track.indeterminate ? statusBar.tone : "#ffffff"
                                opacity: track.indeterminate ? 1 : 0.35
                                NumberAnimation on x { running: statusBar.busy; loops: Animation.Infinite
                                    from: -sweep.width; to: track.width; duration: 1500; easing.type: Easing.InOutSine }
                            }
                        }
                    }
                }
            }

            // ── STATUS ──
            Rectangle {
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
                            { label: "5-hour", used: usageData.five_hour_used, c1: theme.a2, c2: theme.accent },
                            { label: "7-day", used: usageData.seven_day_used, c1: theme.a1, c2: theme.a3 }
                        ]
                        ColumnLayout { Layout.fillWidth: true; spacing: 5
                            RowLayout { Layout.fillWidth: true
                                Text { text: modelData.label + " window"; color: theme.soft; font.pixelSize: 12 }
                                Item { Layout.fillWidth: true }
                                Text { color: theme.soft; font.pixelSize: 11
                                    text: modelData.used === undefined || modelData.used === null ? "—" : (100 - modelData.used) + "% left" } }
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
                                         { k: "You paid", v: connData.paid_api === true ? "API billing" : "$0 · subscription" },
                                         { k: "Same work via API", v: "≈ $" + (usageData.cost !== undefined ? usageData.cost.toFixed(2) : "0.00") } ]
                                // the value takes the space that is left and shortens itself, so a
                                // long value can never run out of the card
                                RowLayout { Layout.fillWidth: true; spacing: 8
                                    Text { text: modelData.k; color: theme.soft; font.pixelSize: 12 }
                                    Text { objectName: "lastRunValue"; text: modelData.v; font.pixelSize: 12; font.bold: true
                                        color: modelData.view ? theme.accent : theme.ink
                                        Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight }
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
                                    Text { Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: 12; font.bold: true
                                        color: modelData.days <= 1 ? theme.warn : theme.ink
                                        text: modelData.label.charAt(0).toUpperCase() + modelData.label.slice(1)
                                              + (modelData.time ? " · " + modelData.time : "") + " · " + modelData.kind }
                                    Text { Layout.fillWidth: true; elide: Text.ElideRight; color: theme.soft; font.pixelSize: 11
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
        }

        // bottom bar: the pipeline as a stepper that follows the run
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 44; color: theme.surface
            Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: theme.line }
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 6
                Repeater {
                    model: [ { bot: a1, name: "Profiler" }, { bot: a2, name: "Scout" }, { bot: a3, name: "Scribe" },
                             { bot: a4, name: "Tracker" }, { bot: a5, name: "Postman" } ]
                    Row {
                        id: stepItem
                        spacing: 6
                        readonly property var bot: modelData.bot
                        Rectangle {                      // link from the previous step, fills when that step is done
                            visible: index > 0; width: 22; height: 2; radius: 1; anchors.verticalCenter: parent.verticalCenter
                            color: theme.line
                            Rectangle { height: 2; radius: 1; color: stepItem.bot.ag
                                width: (stepItem.bot.active || stepItem.bot.done) ? 22 : 0
                                Behavior on width { NumberAnimation { duration: 360; easing.type: Easing.OutCubic } } }
                        }
                        Rectangle {
                            height: 26; radius: 13; width: stepRow.implicitWidth + 20
                            anchors.verticalCenter: parent.verticalCenter
                            color: stepItem.bot.active ? Qt.rgba(stepItem.bot.ag.r, stepItem.bot.ag.g, stepItem.bot.ag.b, 0.20) : "transparent"
                            border.width: 1
                            border.color: stepItem.bot.active ? stepItem.bot.ag
                                        : stepItem.bot.done ? Qt.rgba(stepItem.bot.ag.r, stepItem.bot.ag.g, stepItem.bot.ag.b, 0.5) : theme.line
                            Behavior on color { ColorAnimation { duration: win.motion } }
                            Behavior on border.color { ColorAnimation { duration: win.motion } }
                            Row { id: stepRow; anchors.centerIn: parent; spacing: 6
                                Rectangle { id: stepDot; width: 8; height: 8; radius: 4; anchors.verticalCenter: parent.verticalCenter
                                    color: stepItem.bot.active || stepItem.bot.done ? stepItem.bot.ag : theme.steel
                                    opacity: stepItem.bot.active || stepItem.bot.done ? 1 : 0.55
                                    SequentialAnimation on scale { running: stepItem.bot.active; loops: Animation.Infinite
                                        NumberAnimation { to: 1.5; duration: 500 } NumberAnimation { to: 1; duration: 500 }
                                        onStopped: stepDot.scale = 1 } }
                                Text { text: modelData.name; font.pixelSize: 12
                                    font.bold: stepItem.bot.active
                                    color: stepItem.bot.active ? theme.ink : (stepItem.bot.done ? theme.soft : theme.faint) }
                                Text {
                                    visible: stepItem.bot.done && !stepItem.bot.active; text: "✓"; color: stepItem.bot.ag; font.pixelSize: 11; font.bold: true }
                            }
                        }
                    }
                }
                Item { Layout.fillWidth: true }
                Text { color: theme.faint; font.pixelSize: 11; elide: Text.ElideRight
                    Layout.maximumWidth: 360; horizontalAlignment: Text.AlignRight
                    text: "Applied jobs move to Applications automatically" }
            }
        }
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
    function openView(k) {
        lastView = k;
        if (k === "skip") {
            var fo = bridge.filteredOut();
            var skipped = (fo.rows || []).map(function (r, i) {
                return { primary: r.title + "  ·  " + (r.company || "unknown company"), badge: "", value: "", id: "", flag: "",
                         secondary: r.reason + (r.source ? "   ·  " + r.source : ""),
                         actions: (r.url ? [{ label: "open ↗", kind: "skiplink", arg: i }] : [])
                                  .concat(r.can_return ? [{ label: "bring back", kind: "bringback", arg: i }] : []),
                         group: r.group, company: r.company || "", score: 0, date: "",
                         hay: (r.title + " " + r.company + " " + r.reason + " " + (r.location || "")).toLowerCase() };
            });
            tableDialog.show("Filtered out by the last search" + (fo.when ? " (" + fo.when + ")" : "")
                             + ((fo.total || 0) > skipped.length ? ", first " + skipped.length + " of " + fo.total : ""),
                             skipped, "", [["", "Order of filtering"], ["company", "Company A–Z"]]);
        } else if (k === "new") {
            var rows = bridge.leads().map(function (j) {
                var acts = [];
                if (j.url) acts.push({ label: "open ↗", kind: "url", arg: j.id });
                if (j.letter) acts.push({ label: "letter", kind: "letter", arg: j.letter });
                if (j.cv) acts.push({ label: "CV", kind: "cv", arg: j.cv });
                acts.push({ label: "mark applied", kind: "apply", arg: j.id });
                return { primary: j.title + "  ·  " + j.company,
                         // what the score rests on, and documents left from a higher score: said in the row itself
                         secondary: [[j.posted || "", j.desired ? Number(j.desired).toLocaleString() + " CZK/mo" : ""]
                                         .filter(function (part) { return part !== ""; }).join("   "),
                                     j.basis === "title" ? "scored from the title only" : j.basis === "summary" ? "scored from a short summary" : "",
                                     j.stale_docs === true ? "documents from a higher score" : ""]
                                    .filter(function (part) { return part !== ""; }).join("   ·   "),
                         badge: j.tier || "", value: win.noScore(j.score) ? "–" : "" + j.score, actions: acts,
                         id: j.id, flag: "", was: win.noScore(j.before) ? "" : "was " + j.before, stale: j.stale_docs === true,
                         group: j.tier || (win.noScore(j.score) ? "not scored" : "no documents"),
                         company: j.company || "", score: win.noScore(j.score) ? -1 : j.score, date: j.posted || "",
                         hay: (j.title + " " + j.company + " " + (j.location || "") + " " + (j.source || "")).toLowerCase() };
            });
            // jobs you marked "not interested": only shown when you pick that filter
            bridge.dismissedLeads().forEach(function (j) {
                rows.push({ primary: j.title + "  ·  " + j.company, secondary: j.posted || "", badge: "", flag: "",
                            value: win.noScore(j.score) ? "–" : "" + j.score, id: j.id,
                            actions: [{ label: "restore", kind: "restore", arg: j.id }],
                            group: "not interested", hidden: true, company: j.company || "",
                            score: win.noScore(j.score) ? -1 : j.score, date: j.posted || "",
                            hay: (j.title + " " + j.company + " " + (j.location || "")).toLowerCase() });
            });
            tableDialog.show("New Jobs", rows, "leads",
                             [["", "Best score first"], ["date", "Newest posting first"], ["company", "Company A–Z"]]);
        } else if (k === "app") {
            var rows2 = bridge.applications().map(function (j) {
                var acts = [];
                if (j.letter) acts.push({ label: "letter", kind: "letter", arg: j.letter });
                if (j.cv) acts.push({ label: "CV", kind: "cv", arg: j.cv });
                return { primary: j.company + "  ·  " + j.title,
                         secondary: (j.followup ? (j.had_reply ? "No decision for " : "No reply for ") + win.daysText(j.days_waiting) + "   " : "")
                                    + (j.stages || "") + (j.next_step ? "   → " + j.next_step : ""),
                         badge: j.status || "", value: "", actions: acts,
                         id: j.id, flag: j.followup ? "follow up" : (j.duplicate ? "duplicate?" : ""),
                         group: j.status || "", company: j.company || "", score: -1, date: j.applied || j.updated || "",
                         hay: (j.company + " " + j.title + " " + (j.stages || "") + " " + (j.next_step || "")).toLowerCase() };
            });
            tableDialog.show("Applications", rows2, "apps",
                             [["", "By status"], ["date", "Newest applied first"], ["company", "Company A–Z"]]);
        } else if (k === "resp") {
            var rows3 = bridge.responses().map(function (r) {
                return { primary: r.company + (r.summary ? "  —  " + r.summary : ""),
                         secondary: r.date, badge: r.stage || "", value: "", actions: [], rid: r.id,
                         group: r.stage || "", company: r.company || "", score: -1, date: r.date || "",
                         hay: (r.company + " " + (r.summary || "")).toLowerCase() };
            });
            tableDialog.show("Responses", rows3, "report",
                             [["", "By kind"], ["date", "Newest first"], ["company", "Company A–Z"]]);
        } else if (k === "ins") {
            var ins = bridge.insights(), out = [];
            function head(text, note) { out.push({ primary: text, secondary: note || "", badge: "", value: "", actions: [], heading: true }); }
            function row(text, value, note, badge) { out.push({ primary: text, secondary: note || "", badge: badge || "", value: "" + value, actions: [] }); }
            function mark(v) { return v.indexOf("working") === 0 ? "working" : v.indexOf("not working") === 0 ? "not working"
                                    : v.indexOf("consider") === 0 ? "drop?" : v.indexOf("weak") === 0 ? "weak"
                                    : (v.indexOf("too few") === 0 || v.indexOf("no jobs") === 0) ? "" : "not yet"; }
            var works = ins.works || {};
            head("What is working: kinds of role", "from your " + (works.applications || 0) + " applications · the number is how many you sent");
            (works.by_role || []).forEach(function (r) {
                row(r.name, r.applications, r.verdict + "  ·  " + r.replied + " replied, " + r.rejected + " rejected, " + r.waiting + " waiting", mark(r.verdict)); });
            head("What is working: where the job came from", "");
            (works.by_source || []).forEach(function (r) {
                row(r.name, r.applications, r.verdict + "  ·  " + r.rejected + " rejected, " + r.waiting + " waiting", mark(r.verdict)); });
            head("Week by week", "the number is how many applications you sent that week · weeks start on Monday");
            (ins.trends || []).forEach(function (t) {
                row("Week of " + t.week + (t.current ? " (this week)" : ""), t.applications,
                    t.replies + (t.replies === 1 ? " reply" : " replies") + "  ·  " + t.invitations
                    + (t.invitations === 1 ? " invitation" : " invitations") + ", " + t.rejections + (t.rejections === 1 ? " rejection" : " rejections")); });
            var rt = ins.reply_times || {};
            head("How long companies take to decide", (rt.decisions || 0) === 0 ? "no decisions with a known apply date yet"
                 : "days from applying to the first rejection or invitation · from " + rt.decisions + " decisions");
            if ((rt.decisions || 0) > 0) {
                row("Middle value", rt.middle + " d", "half of the decisions came sooner than this");
                row("4 of 5 decisions came within", rt.most_within + " d", "the slowest took " + rt.slowest + " days");
                (rt.by_role || []).forEach(function (r) {
                    row("↳ " + r.name, r.middle + " d", "middle value from " + r.decisions + " decisions  ·  between " + r.fastest + " and " + r.slowest + " days"); });
                row("Waiting longer than that", rt.waiting_late, "of " + rt.waiting + " waiting applications · after " + rt.most_within
                    + " days of silence a decision is unlikely, though the slowest took " + rt.slowest, rt.waiting_late > 0 ? "weak" : "");
                (rt.late || []).forEach(function (l) {
                    out.push({ primary: "↳ " + l.company + "  ·  " + l.title, secondary: "no decision for " + l.days + " days",
                               badge: "", value: l.days + " d", actions: [], id: l.id }); });
            }
            head("Search keywords", "the number is how many jobs the keyword found · score " + (ins.threshold || 30) + "+ gets a CV and letter");
            (ins.keywords || []).forEach(function (r) {
                row(r.keyword, r.leads, r.verdict + (r.average !== null && r.average !== undefined ? "  ·  average score " + r.average : "")
                    + (r.guessed > 0 ? "  ·  matched by title" : ""), mark(r.verdict)); });
            var gaps = ins.gaps || {};
            head("Skills to learn", "asked for in the " + (gaps.postings || 0) + " postings with a description, but not in your CV · never added to a CV");
            (gaps.skills || []).forEach(function (r) {
                row(r.skill, r.postings, "in " + r.share + "% of postings  ·  " + r.relevant + " of them close to your profile"); });
            if ((gaps.languages || []).length > 0)
                row("Languages asked for", gaps.languages.map(function (l) { return l.postings; }).reduce(function (a, b) { return a + b; }, 0),
                    gaps.languages.map(function (l) { return l.language + " in " + l.postings; }).join("  ·  "));
            var lows = ins.low_scores || {};
            head("Why jobs score low", (lows.jobs || 0) + " jobs scored below " + (lows.threshold || 30)
                 + " · read from the explanation of each score · one job can count under several reasons");
            (lows.rows || []).forEach(function (r) { row(r.reason, r.jobs, "in " + r.share + "% of the low-scoring jobs"); });
            if ((lows.technologies || []).length > 0)
                row("Named most often as missing", lows.technologies.length,
                    lows.technologies.map(function (t) { return t.skill + " in " + t.jobs; }).join("  ·  "));
            var pay = ins.salaries || {};
            head("What the postings pay", (pay.stated || 0) + " of " + (pay.postings || 0) + " postings state it · gross CZK per month · the number is the top of the range"
                 + (pay.median ? " · middle value " + Math.round(pay.median / 1000) + "k" : ""));
            (pay.rows || []).forEach(function (r) {
                out.push({ primary: r.title + "  ·  " + r.company, badge: "", actions: [], id: r.id,
                           value: Math.round(r.high / 1000) + "k",
                           secondary: (r.low === r.high ? Math.round(r.low / 1000) + "k" : Math.round(r.low / 1000) + "–" + Math.round(r.high / 1000) + "k")
                                      + " CZK  ·  written as \"" + r.text + "\""
                                      + (r.target ? "  ·  your target " + Math.round(r.target / 1000) + "k: " + r.verdict : "") }); });
            tableDialog.show("Insights — what works, keywords, skills to learn", out, "", []);
        } else {
            var an = bridge.analytics();
            var st = an.applications_by_status || {}, em = an.by_stage || {};
            function line(label, value, note) { return { primary: label, secondary: note || "", badge: "", value: "" + value, actions: [] }; }
            var wk = bridge.weekSummary();
            var rows4 = [{ primary: "The last 7 days", secondary: (wk.from || "") + " to " + (wk.to || ""), heading: true, badge: "", value: "", actions: [] }];
            (wk.lines || []).forEach(function (r) { rows4.push(line(r.label, r.value, r.note)); });
            rows4.push({ primary: "All time", secondary: "every application and reply the app knows", heading: true, badge: "", value: "", actions: [] });
            rows4 = rows4.concat([
                line("Applications", an.applications_tracked || 0, "the four rows below add up to this"),
                line("↳ waiting for an answer", st.waiting || 0),
                line("↳ in interviews now", st.interview || 0),
                line("↳ offers", st.offer || 0),
                line("↳ rejected", (st.rejected || 0) + (st.on_hold || 0),
                     (an.rejected_by_hand || 0) > 0 ? ((an.rejected_by_hand) + " of them you marked yourself (no email in the mailbox)") : ""),
                line("Companies that replied", an.companies_replied || 0, "at least one email from them"),
                line("Applications that reached an interview", an.applications_with_interview || 0, "at any point, including ones rejected later"),
                line("Reply emails", an.response_emails || 0, "every email counted once; the five rows below add up to this"),
                line("↳ confirmations", em.acknowledged || 0, "\"we received your application\""),
                line("↳ interview emails", em.interview || 0, "invitations, scheduling, reminders"),
                line("↳ tests and tasks", em.assessment || 0),
                line("↳ rejections", em.rejection || 0),
                line("↳ other", em.other || 0, "feedback requests, account messages"),
                line("Why the rejection emails said no", em.rejection || 0, "the rows below add up to this")
            ]);
            var rr = an.rejection_reasons || {};
            for (var key in rr) rows4.push(line("↳ " + key.replace(/_/g, " "), rr[key]));
            tableDialog.show("Analytics — outcomes & rejection reasons", rows4, "", []);
        }
    }

    TableDialog { id: tableDialog }

    // ───────────────────────── one job in full ─────────────────────────
    DetailDialog { id: detailDialog }

    // ───────────────────────── master CV next to the adapted one ─────────────────────────
    CompareDialog { id: compareDialog }

    // ───────────────────────── answers to repeated form questions ─────────────────────────
    FormAnswersDialog { id: formDialog }
    PrepEditDialog { id: prepEditDialog }

    // ───────────────────────── a message on top of an open window ─────────────────────────
    Connections { target: ticker
        function onTextChanged() { if (win.dialogOpen && !win.quietTicker && ticker.text !== "") win.showToast(ticker.text); } }
    Timer { id: toastTimer; interval: 4200; onTriggered: win.toastText = "" }
    Rectangle {
        id: toast; objectName: "toast"
        parent: Overlay.overlay; z: 10000
        visible: opacity > 0; opacity: win.toastText !== "" && win.dialogOpen ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160 } }
        width: Math.min(620, win.width - 80); height: toastT.implicitHeight + 22
        x: (win.width - width) / 2; y: win.height - height - 26
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
        ticker.text = (r && r.ok) ? ("✓ Master CV updated — " + r.name) : welcome.cvErr;
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

    // ───────────────────────── weekly schedule ─────────────────────────
    ScheduleDialog { id: schedDialog }
}
