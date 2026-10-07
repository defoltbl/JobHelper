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
    Timer { interval: 3600 * 1000; repeat: true; running: true; onTriggered: { bridge.remind(); win.upcomingData = bridge.upcoming(); } }
    Timer { interval: 4000; running: true; onTriggered: bridge.remind() }
    property bool appRunning: false   // mirror of bridge.running (avoids teardown binding churn)
    property bool usageBusy: false
    property var schedData: ({})
    property bool connChecked: false  // first connection check has come back
    property var healthData: ({ ok: true, checks: [], problems: 0, message: "" })   // the start-up self-check
    property bool healthHidden: false
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
        if (runMode === "scan") {                 // one stage: emails read so far
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
    readonly property bool dialogOpen: tableDialog.visible || optDialog.visible || schedDialog.visible || detailDialog.visible || limitDialog.visible || responseDialog.visible || letterDialog.visible || prepDialog.visible || helpDialog.visible || compareDialog.visible || answersDialog.visible
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
        return m[(c || "").toLowerCase()] || c || "Prague";
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
        if (r && r.fix) welcome.openCard();   // jump to the fix
    }
    function noScore(v) { return v === null || v === undefined; }
    function daysText(n) { return n + (n === 1 ? " day" : " days"); }
    function stopRun() { if (win.appRunning && !win.stopping && bridge.stopRun()) win.stopping = true; }
    function startRun() { if (win.appRunning) return; handleStart(bridge.runSearch(optsData), "Starting…", "search"); }
    function startScan() { if (win.appRunning) return; handleStart(bridge.scanEmail(), "Reading inbox…", "scan"); }

    Timer { interval: 60; running: true; repeat: false
        onTriggered: { win.reloadAll(); win.usageBusy = true; bridge.refreshUsage(); } }
    Connections {
        target: bridge
        function onAgentChanged(key, status, info) { win.setAgent(key, status, info); }
        function onLogChanged(t) { ticker.text = t; }
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
            if (!win.connChecked || !win.healthData.ok) win.healthData = bridge.selfCheck(info.claude === true);   // at start, and again until it is clean
            win.connChecked = true;
        }
        function onUsageReady() { win.usageData = bridge.usageInfo(); win.usageBusy = false; }
    }

    // ── palette ──
    QtObject {
        id: theme
        property color winbg: win.dark ? "#121922" : "#f3f6f9"
        property color surface: win.dark ? "#19222d" : "#ffffff"
        property color surface2: win.dark ? "#1f2a37" : "#f5f8fb"
        property color inset: win.dark ? "#141c25" : "#eceff3"
        property color ink: win.dark ? "#e7eef5" : "#182230"
        property color soft: win.dark ? "#9fb0c1" : "#5a6675"
        property color faint: win.dark ? "#6f7f90" : "#8b97a5"
        property color line: win.dark ? "#2a3644" : "#d6dde5"
        property color accent: win.dark ? "#f0a84a" : "#e5891f"
        property color belt: win.dark ? "#2a3643" : "#c6cfd9"
        property color beltDark: win.dark ? "#1d2731" : "#aeb9c6"
        property color steel: win.dark ? "#8695a6" : "#6b7787"
        property color good: win.dark ? "#4ade80" : "#15944b"
        property color goodbg: win.dark ? "#12301f" : "#e4f4ea"
        property color warnbg: win.dark ? "#2e2410" : "#f8eed8"
        property color warn: win.dark ? "#f0b84a" : "#b5720a"
        property color crit: win.dark ? "#f87171" : "#cf3030"
        property color critbg: win.dark ? "#331717" : "#f8e3e3"
        property color infobg: win.dark ? "#142338" : "#e5eefc"
        property color a1: "#3b82f6"; property color a2: "#10b981"
        property color a3: "#8b5cf6"; property color a4: "#fb923c"; property color a5: "#f43f5e"
    }

    // ── reusable buttons ──
    component PillButton: Button {
        id: pb
        property color bg: theme.surface
        property bool primaryStyle: false
        property color tint: "transparent"   // tinted secondary style when set
        readonly property bool tinted: tint != Qt.rgba(0, 0, 0, 0)
        implicitHeight: 34
        leftPadding: 14; rightPadding: 14
        font.pixelSize: 13; font.bold: true
        HoverHandler { cursorShape: Qt.PointingHandCursor; enabled: pb.enabled }
        scale: pb.down ? 0.96 : 1
        Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        background: Rectangle {
            radius: 10
            color: pb.primaryStyle ? (pb.hovered ? Qt.lighter(theme.accent, 1.08) : theme.accent)
                 : pb.tinted ? Qt.rgba(pb.tint.r, pb.tint.g, pb.tint.b, pb.hovered ? 0.28 : 0.16)
                 : (pb.hovered ? theme.surface2 : pb.bg)
            border.color: pb.primaryStyle ? "transparent"
                        : pb.tinted ? Qt.rgba(pb.tint.r, pb.tint.g, pb.tint.b, 0.55)
                        : (pb.hovered ? theme.steel : theme.line)
            border.width: pb.tinted ? 1.5 : 1
            opacity: pb.enabled ? 1 : 0.5
        }
        property string glyph: ""            // "mail" draws an envelope before the label
        readonly property color fg: primaryStyle ? "#ffffff" : (tinted ? tint : theme.ink)
        contentItem: Item {
            implicitWidth: btnRow.implicitWidth; implicitHeight: btnRow.implicitHeight
            Row {
                id: btnRow; anchors.centerIn: parent; spacing: 8
                Item {                           // envelope icon, drawn so it is crisp at any size
                    visible: pb.glyph === "mail"; width: 18; height: 13
                    anchors.verticalCenter: parent.verticalCenter
                    Rectangle { anchors.fill: parent; radius: 3; color: "transparent"; border.color: pb.fg; border.width: 1.6 }
                    Shape {
                        anchors.fill: parent
                        ShapePath { strokeColor: pb.fg; strokeWidth: 1.6; fillColor: "transparent"
                            capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                            startX: 2.5; startY: 3
                            PathLine { x: 9; y: 8 } PathLine { x: 15.5; y: 3 } }
                    }
                }
                Rectangle {                      // help icon: a ring with a question mark
                    visible: pb.glyph === "help"; width: 16; height: 16; radius: 8
                    anchors.verticalCenter: parent.verticalCenter
                    color: "transparent"; border.color: pb.fg; border.width: 1.6
                    Text { anchors.centerIn: parent; text: "?"; color: pb.fg; font.pixelSize: 11; font.bold: true }
                }
                Item {                           // gear icon: a ring with eight teeth
                    visible: pb.glyph === "gear"; width: 16; height: 16
                    anchors.verticalCenter: parent.verticalCenter
                    Repeater { model: 4
                        Rectangle { x: 6.5; y: 0; width: 3; height: 16; radius: 1.2; color: pb.fg
                            rotation: index * 45; antialiasing: true } }
                    Rectangle { x: 2.5; y: 2.5; width: 11; height: 11; radius: 5.5; color: pb.fg }
                    Rectangle { x: 5.5; y: 5.5; width: 5; height: 5; radius: 2.5
                        color: pb.hovered ? theme.surface2 : pb.bg }
                }
                Text { text: pb.text; font: pb.font; color: pb.fg; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }
    component SmallButton: Button {
        id: sb
        property bool primaryStyle: false
        implicitHeight: 26
        leftPadding: 9; rightPadding: 9
        font.pixelSize: 11; font.bold: true
        HoverHandler { cursorShape: Qt.PointingHandCursor; enabled: sb.enabled }
        scale: sb.down ? 0.95 : 1
        Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        background: Rectangle { radius: 7
            color: sb.primaryStyle ? (sb.hovered ? Qt.lighter(theme.accent, 1.08) : theme.accent)
                                        : (sb.hovered ? Qt.lighter(theme.surface2, 1.25) : theme.surface2)
            border.color: sb.primaryStyle ? "transparent" : (sb.hovered ? theme.steel : theme.line); border.width: 1 }
        contentItem: Text { text: sb.text; font: sb.font
            color: sb.primaryStyle ? "#ffffff" : theme.ink
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
    }

    // ── macOS-System-Settings-style building blocks ──
    component GroupTitle: Text {
        Layout.leftMargin: 6; Layout.topMargin: 4; Layout.bottomMargin: 2
        color: theme.faint; font.pixelSize: 11; font.bold: true; font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
    }
    component Card: Rectangle {
        default property alias items: col.data
        Layout.fillWidth: true
        radius: 11; color: theme.surface2; border.color: theme.line; border.width: 1
        implicitHeight: col.implicitHeight + 2
        ColumnLayout { id: col; y: 1
            anchors.left: parent.left; anchors.right: parent.right
            anchors.leftMargin: 1; anchors.rightMargin: 1; spacing: 0 }
    }
    component SRow: Item {
        property string label: ""
        property string hint: ""
        default property alias ctl: slot.data
        Layout.fillWidth: true
        implicitHeight: hint !== "" ? 56 : 48
        ColumnLayout {
            anchors.left: parent.left; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter
            anchors.right: slot.left; anchors.rightMargin: 10; spacing: 1
            Text { text: label; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
            Text { visible: hint !== ""; text: hint; color: theme.faint; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
        }
        Item { id: slot; anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
            width: childrenRect.width; height: childrenRect.height }
    }
    component Sep: Rectangle {
        Layout.fillWidth: true; Layout.preferredHeight: 1; Layout.leftMargin: 14; color: theme.line; opacity: 0.6
    }
    // dropdown (optionally type-to-complete via `editable`)
    component ThemedCombo: ComboBox {
        id: cb
        property bool plainText: false   // true = string model (no textRole)
        implicitHeight: 32; font.pixelSize: 12
        palette.text: theme.ink; palette.highlightedText: theme.ink
        palette.buttonText: theme.ink; palette.windowText: theme.ink; palette.base: theme.surface
        background: Rectangle { radius: 7; color: theme.surface
            border.color: cb.activeFocus ? theme.accent : theme.line; border.width: 1 }
        delegate: ItemDelegate {
            width: cb.width; height: 30
            contentItem: Text {
                text: cb.plainText ? modelData : (cb.textRole ? (modelData[cb.textRole] !== undefined ? modelData[cb.textRole] : model[cb.textRole]) : modelData)
                color: theme.ink; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; leftPadding: 8; elide: Text.ElideRight }
            background: Rectangle { color: (cb.highlightedIndex === index) ? theme.surface2 : "transparent" }
            highlighted: cb.highlightedIndex === index
        }
        popup: Popup {
            y: cb.height + 2; width: cb.width; padding: 1
            implicitHeight: Math.min(lv.contentHeight + 2, 240)
            background: Rectangle { radius: 8; color: theme.surface; border.color: theme.line; border.width: 1 }
            contentItem: ListView { id: lv; clip: true; implicitHeight: contentHeight
                model: cb.popup.visible ? cb.delegateModel : null; currentIndex: cb.highlightedIndex
                ScrollBar.vertical: ScrollBar {} }
        }
        // editable field: text colour follows the theme (also after switching it),
        // and the text can be selected with the mouse
        Binding { target: cb.contentItem; property: "color"; value: theme.ink; when: cb.editable }
        Component.onCompleted: if (editable && contentItem) {
            try { contentItem.selectByMouse = true } catch (e) {}
        }
    }
    // free-text field with a case-insensitive suggestion dropdown; Enter / a click
    // adds the value. Used for adding search roles.
    component AutoField: Item {
        id: af
        property var suggestions: []
        property string placeholder: ""
        property alias text: tf.text
        signal add(string value)
        signal edited()
        implicitHeight: 32; implicitWidth: 180
        TextField {
            id: tf; anchors.fill: parent
            placeholderText: af.placeholder; color: theme.ink; font.pixelSize: 12; selectByMouse: true
            background: Rectangle { radius: 7; color: theme.surface; border.width: 1
                border.color: tf.activeFocus ? theme.accent : theme.line }
            onTextEdited: { af.edited(); sugPop.refresh(); }
            onActiveFocusChanged: if (!activeFocus) sugPop.close()
            Keys.onReturnPressed: { af.add(tf.text); sugPop.close(); }
            Keys.onEnterPressed: { af.add(tf.text); sugPop.close(); }
            Keys.onDownPressed: if (sugPop.opened) sugList.incrementCurrentIndex()
        }
        Popup {
            id: sugPop
            y: tf.height + 3; x: 0; width: Math.max(tf.width, 220); padding: 1
            closePolicy: Popup.NoAutoClose
            implicitHeight: Math.min(sugList.contentHeight + 2, 190)
            background: Rectangle { radius: 8; color: theme.surface; border.color: theme.line; border.width: 1 }
            ListModel { id: sugModel }
            function refresh() {
                var q = tf.text.toLowerCase().trim();   // case-insensitive
                sugModel.clear();
                if (q.length < 1) { close(); return; }
                var n = 0;
                for (var i = 0; i < af.suggestions.length && n < 8; i++) {
                    var s = af.suggestions[i];
                    if (s.toLowerCase().indexOf(q) !== -1) { sugModel.append({ t: s }); n++; }
                }
                if (n > 0) open(); else close();
            }
            contentItem: ListView {
                id: sugList; clip: true; implicitHeight: contentHeight; model: sugModel
                delegate: ItemDelegate {
                    width: sugList.width; height: 30
                    contentItem: Text { text: t; color: theme.ink; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; leftPadding: 8 }
                    background: Rectangle { color: hovered ? theme.surface2 : "transparent" }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    onClicked: { af.add(t); sugPop.close(); }
                }
            }
        }
    }
    // on/off switch that follows the theme: accent track when on, clear knob travel
    component ThemedSwitch: Switch {
        id: sw
        implicitWidth: 42; implicitHeight: 24; padding: 0
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        indicator: Rectangle {
            width: 42; height: 24; radius: 12
            color: sw.checked ? theme.accent : theme.inset
            border.color: sw.checked ? theme.accent : theme.line; border.width: 1
            Behavior on color { ColorAnimation { duration: 120 } }
            Rectangle {
                width: 18; height: 18; radius: 9; y: 3
                x: sw.checked ? parent.width - width - 3 : 3
                color: "#ffffff"; border.color: theme.line; border.width: sw.checked ? 0 : 1
                Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
            }
        }
        contentItem: Item {}
    }
    // modern number stepper: rounded, −/+ with hover + pointer cursor, subtle
    // accent focus (no harsh blue), editable text you can select and type into.
    component ThemedSpin: SpinBox {
        id: sp
        editable: true
        wheelEnabled: false          // scrolling the page must never change a number
        implicitHeight: 32; implicitWidth: 120
        font.pixelSize: 12
        palette.text: theme.ink; palette.highlightedText: "#ffffff"
        leftPadding: 36; rightPadding: 36; topPadding: 0; bottomPadding: 0
        background: Rectangle { radius: 8; color: theme.surface
            border.color: sp.activeFocus ? theme.accent : theme.line; border.width: 1 }
        contentItem: TextInput {
            id: spIn
            text: sp.displayText; font: sp.font; color: theme.ink
            selectByMouse: true; cursorVisible: sp.activeFocus
            horizontalAlignment: Qt.AlignHCenter; verticalAlignment: Qt.AlignVCenter
            readOnly: !sp.editable
            validator: IntValidator { bottom: sp.from; top: sp.to }   // can't type out of range
            inputMethodHints: Qt.ImhDigitsOnly
            // What is typed becomes the value at once, so Save never stores the old
            // number because the field still had the cursor in it.
            onTextEdited: if (acceptableInput) sp.value = sp.valueFromText(text, sp.locale)
            // clamp + re-sync the text to the valid value when editing ends
            onEditingFinished: { sp.value = sp.valueFromText(text, sp.locale); text = sp.displayText; }
        }
        down.indicator: Rectangle {
            x: 1; y: 1; width: 34; height: sp.height - 2
            radius: 7; color: sp.down.pressed ? theme.inset : (sp.down.hovered ? theme.surface2 : "transparent")
            Text { anchors.centerIn: parent; text: "−"; color: theme.ink; font.pixelSize: 16 }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
        }
        up.indicator: Rectangle {
            x: sp.width - 35; y: 1; width: 34; height: sp.height - 2
            radius: 7; color: sp.up.pressed ? theme.inset : (sp.up.hovered ? theme.surface2 : "transparent")
            Text { anchors.centerIn: parent; text: "+"; color: theme.ink; font.pixelSize: 15 }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
        }
    }
    // zero-padded time field (HH / MM). Unlike a SpinBox it KEEPS an out-of-range
    // value visible, turns the border red, and sets `valid=false` so Save can be
    // blocked with an explicit error (instead of silently clamping).
    component TimeField: Item {
        id: tfr
        property int value: 0
        property int maxv: 23
        property bool _typing: false
        readonly property bool valid: value >= 0 && value <= maxv
        signal edited()
        implicitWidth: 112; implicitHeight: 32
        function _fmt(v) { return (v < 10 ? "0" : "") + v; }
        onValueChanged: if (!_typing) ti.text = _fmt(value)   // don't reformat mid-type
        Rectangle {
            anchors.fill: parent; radius: 8; color: theme.surface; border.width: 1.5
            border.color: !tfr.valid ? theme.crit : (ti.activeFocus ? theme.accent : theme.line)
        }
        Rectangle {
            x: 1; y: 1; width: 32; height: parent.height - 2; radius: 7
            color: dPress.pressed ? theme.inset : (dMa.hovered ? theme.surface2 : "transparent")
            Text { anchors.centerIn: parent; text: "−"; color: theme.ink; font.pixelSize: 16 }
            HoverHandler { id: dMa; cursorShape: Qt.PointingHandCursor }
            MouseArea { id: dPress; anchors.fill: parent
                onClicked: { tfr._typing = false; if (tfr.value > 0) tfr.value--; else ti.text = tfr._fmt(tfr.value); tfr.edited(); } }
        }
        Rectangle {
            x: parent.width - 33; y: 1; width: 32; height: parent.height - 2; radius: 7
            color: uPress.pressed ? theme.inset : (uMa.hovered ? theme.surface2 : "transparent")
            Text { anchors.centerIn: parent; text: "+"; color: theme.ink; font.pixelSize: 15 }
            HoverHandler { id: uMa; cursorShape: Qt.PointingHandCursor }
            MouseArea { id: uPress; anchors.fill: parent
                onClicked: { tfr._typing = false; if (tfr.value < tfr.maxv) tfr.value++; else ti.text = tfr._fmt(tfr.value); tfr.edited(); } }
        }
        TextInput {
            id: ti; anchors.centerIn: parent; width: parent.width - 72
            color: theme.ink; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter
            selectByMouse: true; inputMethodHints: Qt.ImhDigitsOnly
            validator: IntValidator { bottom: 0; top: 99 }   // allow typing 24/25/60… so we can flag them
            Component.onCompleted: text = tfr._fmt(tfr.value)
            // commit the value LIVE while typing so Save always sees the current
            // number (and the red error appears immediately), without reformatting
            onTextEdited: { tfr._typing = true; var v = parseInt(text, 10); tfr.value = isNaN(v) ? 0 : v; tfr.edited(); }
            onEditingFinished: { tfr._typing = false; var v = parseInt(text, 10); tfr.value = isNaN(v) ? 0 : v; ti.text = tfr._fmt(tfr.value); tfr.edited(); }
        }
    }

    // A short list of words the user edits as chips (skip words, exceptions).
    component TagEditor: ColumnLayout {
        id: te
        property string label: ""
        property string hint: ""
        property string placeholder: ""
        property string err: ""
        property color chipTone: theme.ink
        ListModel { id: teModel }
        function setAll(arr) { teModel.clear(); for (var i = 0; i < (arr || []).length; i++) teModel.append({ text: "" + arr[i] }); err = ""; }
        function all() { var out = []; for (var i = 0; i < teModel.count; i++) out.push("" + teModel.get(i).text); return out; }
        function add(txt) {
            var t = (txt || "").trim().toLowerCase();
            err = "";
            if (!t) return false;
            if (win.hasNonLatin(t)) { err = "Use Latin letters, as job titles are written."; return false; }
            if (!/[a-z]/.test(t) || t.length < 2) { err = "Enter a word from a job title, for example: intern."; return false; }
            if (t.length > 40) { err = "That is too long. Use one word or a short phrase."; return false; }
            for (var i = 0; i < teModel.count; i++)
                if (teModel.get(i).text === t) { err = "That word is already in the list."; return false; }
            teModel.append({ text: t });
            return true;
        }
        Layout.fillWidth: true; spacing: 0
        SRow { label: te.label; hint: te.hint
            RowLayout { spacing: 6
                TextField { id: teField; implicitWidth: 180; implicitHeight: 30; placeholderText: te.placeholder
                    placeholderTextColor: theme.faint; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                    background: Rectangle { radius: 8; color: theme.surface; border.width: 1
                        border.color: teField.activeFocus ? theme.accent : (te.err !== "" ? theme.crit : theme.line) }
                    onTextEdited: te.err = ""
                    onAccepted: if (te.add(text)) text = "" }
                SmallButton { text: "+ Add"; primaryStyle: true; onClicked: { if (te.add(teField.text)) teField.text = ""; } } } }
        Text { visible: te.err !== ""; Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.topMargin: 2
            wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11; font.bold: true; text: te.err }
        Flow {
            Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.bottomMargin: 12
            spacing: 6; visible: teModel.count > 0
            Repeater { model: teModel
                Rectangle {
                    radius: 999; color: theme.inset; border.color: theme.line; border.width: 1
                    implicitHeight: 24; implicitWidth: teChip.width + 16
                    Row { id: teChip; anchors.centerIn: parent; spacing: 5
                        Text { text: model.text; color: te.chipTone; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: "✕"; color: theme.faint; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter
                            MouseArea { anchors.fill: parent; anchors.margins: -4; cursorShape: Qt.PointingHandCursor
                                onClicked: teModel.remove(index) } } }
                } }
        }
    }

    // A factory gate straddling the belt: an inverted-U portal the belt runs
    // through. Jobs come out of the input gate and go into the output gate; the
    // lamp on the beam blinks while the line runs and the opening lights up each
    // time a package passes. The belt line sits at local y = 64.
    component Gate: Item {
        id: g
        property color ag: theme.steel
        property string kind: "in"            // in: a document | out: a box
        property string gtitle: "Gate"
        property string caption: ""
        property string badge: ""             // small counter on the beam
        property bool running: false
        property real flash: 0                // 0..1, a package is passing
        width: 94; height: 128
        // glow in the opening when a package passes
        Rectangle { x: 17; y: 18; width: 60; height: 68; radius: 4
            color: g.ag; opacity: 0.10 + 0.45 * g.flash; visible: g.running }
        // portal frame
        Rectangle { x: 4; y: 6; width: 86; height: 12; radius: 5; color: theme.beltDark }   // top beam
        Rectangle { x: 4; y: 6; width: 13; height: 80; radius: 5; color: theme.beltDark }    // left post
        Rectangle { x: 77; y: 6; width: 13; height: 80; radius: 5; color: theme.beltDark }   // right post
        Rectangle { x: 4; y: 6; width: 86; height: 4; radius: 2; color: g.ag }               // accent beam cap
        // light strips down the inside of both posts
        Repeater { model: [19, 72]
            Rectangle { x: modelData; y: 20; width: 3; height: 62; radius: 1.5; color: g.ag
                opacity: g.running ? 0.35 + 0.65 * g.flash : 0.18 } }
        // feet
        Rectangle { x: 1; y: 82; width: 19; height: 5; radius: 2; color: theme.steel; opacity: 0.7 }
        Rectangle { x: 74; y: 82; width: 19; height: 5; radius: 2; color: theme.steel; opacity: 0.7 }
        // beacon lamp on the beam
        Rectangle { id: lamp; x: 10; y: 11; width: 6; height: 6; radius: 3
            color: g.running ? g.ag : theme.steel
            SequentialAnimation on opacity { running: g.running; loops: Animation.Infinite
                NumberAnimation { to: 0.25; duration: 450 } NumberAnimation { to: 1; duration: 450 }
                onStopped: lamp.opacity = 1 } }
        // counter on the beam
        Rectangle { visible: g.badge !== ""; x: 90 - width - 3; y: -3; height: 17; width: Math.max(20, bTxt.implicitWidth + 10)
            radius: 8.5; color: g.ag; border.color: theme.surface; border.width: 1.5
            Text { id: bTxt; anchors.centerIn: parent; text: g.badge; color: "#ffffff"; font.pixelSize: 10; font.bold: true } }
        // icon plate in the opening, sitting on the belt
        Rectangle { x: 26; y: 24; width: 42; height: 40; radius: 10
            color: theme.surface2; border.color: g.ag; border.width: 1.5
            scale: 1 + 0.07 * g.flash
            // document
            Item { visible: g.kind === "in"; anchors.centerIn: parent; width: 18; height: 22
                Rectangle { anchors.fill: parent; radius: 3; color: "transparent"; border.color: g.ag; border.width: 1.6 }
                Column { x: 4; y: 5; spacing: 3
                    Repeater { model: [10, 7, 10, 5]
                        Rectangle { width: modelData; height: 1.8; radius: 0.9; color: g.ag } } } }
            // box
            Item { visible: g.kind === "out"; anchors.centerIn: parent; width: 22; height: 20
                Rectangle { x: 0; y: 5; width: 22; height: 15; radius: 2.5; color: "transparent"; border.color: g.ag; border.width: 1.6 }
                Rectangle { x: -1; y: 1; width: 24; height: 6; radius: 2; color: theme.surface2; border.color: g.ag; border.width: 1.6 }
                Rectangle { x: 9; y: 9; width: 4; height: 4; radius: 1; color: g.ag } }
        }
        // labels
        Text { anchors.horizontalCenter: parent.horizontalCenter; y: 92
            text: g.gtitle; color: theme.ink; font.pixelSize: 12; font.bold: true }
        Text { anchors.horizontalCenter: parent.horizontalCenter; y: 108
            text: g.caption; color: g.ag; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1 }
    }

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
                            color: navMouse.containsMouse ? theme.surface2 : "transparent"
                            Behavior on color { ColorAnimation { duration: 140 } }
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
                                    Text { anchors.centerIn: parent; color: "#ffffff"; font.pixelSize: 15; font.bold: true
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
                            model: [ win.cityEN(optsData.where),
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
                            border.width: 1; border.color: win.canResume ? "transparent" : theme.line
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
                    PillButton { objectName: "answersButton"; Layout.fillWidth: true; text: "Answers"; onClicked: answersDialog.show("") }
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
                         secondary: (j.posted || "") + (j.desired ? "   " + Number(j.desired).toLocaleString() + " CZK/mo" : ""),
                         badge: j.tier || "", value: win.noScore(j.score) ? "–" : "" + j.score, actions: acts,
                         id: j.id, flag: "",
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
                            border.width: 1; border.color: on ? "transparent" : theme.line
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
                    color: heading ? theme.inset : rowMa.containsMouse && openable ? theme.inset : (index % 2 ? theme.surface2 : "transparent")
                    Behavior on color { ColorAnimation { duration: 120 } }
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

    // ───────────────────────── one job in full ─────────────────────────
    component ChipFlow: Flow {
        id: cf
        property var items: []
        property color tone: theme.soft
        property color fill: theme.inset
        Layout.fillWidth: true; spacing: 6
        Repeater { model: cf.items
            Rectangle { height: 24; radius: 12; width: cfT.implicitWidth + 18; color: cf.fill
                border.color: Qt.rgba(cf.tone.r, cf.tone.g, cf.tone.b, 0.45); border.width: 1
                Text { id: cfT; anchors.centerIn: parent; text: modelData; color: cf.tone; font.pixelSize: 11; font.bold: true } } }
    }
    component DetailCard: Rectangle {
        default property alias body: dcCol.data
        property string heading: ""
        Layout.fillWidth: true; radius: 12; color: theme.surface2; border.color: theme.line; border.width: 1
        implicitHeight: dcCol.implicitHeight + 24
        ColumnLayout { id: dcCol; x: 14; y: 12; width: parent.width - 28; spacing: 8
            Text { text: parent.parent.heading; visible: text !== ""; color: theme.faint; font.pixelSize: 10; font.bold: true
                font.letterSpacing: 1.4; font.capitalization: Font.AllUppercase } }
    }
    Dialog {
        id: detailDialog; objectName: "detailDialog"
        modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
        enter: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
        exit: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
            NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
        Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
        width: Math.min(760, win.width - 80); height: Math.min(700, win.height - 70)
        padding: 0
        property var job: ({})
        property var draft: ({})
        property string note: ""
        property string dateErr: ""
        property bool prepBusy: false
        property string prepErr: ""
        property string prepJob: ""
        property string eventErr: ""
        property string eventKind: "interview"
        property string notesInfo: ""
        property bool replyOpen: false
        property bool replyBusy: false
        property string replyInfo: ""
        property string replyErr: ""
        property string replyJob: ""
        property var thanks: ({})
        property string thanksNote: ""
        function saveEvent() {
            eventErr = "";
            var r = bridge.setEvent(job.id, evDate.text, evTime.text, eventKind, evNote.text);
            if (r && r.ok) { refresh(); win.upcomingData = bridge.upcoming(); ticker.text = "Date saved. You will be reminded the day before."; }
            else eventErr = (r && r.msg) ? r.msg : "Couldn't save that date.";
        }
        function saveNotes() {
            var r = bridge.saveCompanyNotes(job.company || "", { contact: cnContact.text, salary: cnSalary.text, asked: cnAsked.text, notes: cnNotes.text });
            notesInfo = (r && r.ok) ? "Saved for " + (job.company || "this company") + "." : ((r && r.msg) || "Couldn't save the notes.");
            if (r && r.ok) refresh();
        }
        function fileReply() {
            replyErr = ""; replyInfo = "";
            if (replyText.text.trim().length < 20) { replyErr = "Paste the whole message: that is too short to read."; return; }
            replyBusy = true; replyJob = job.id;
            bridge.addReply(job.id, replyText.text);
        }
        Connections { target: bridge
            function onReplyReady(res) {
                if (res.job_id !== detailDialog.replyJob) return;
                detailDialog.replyBusy = false;
                if (res.job_id !== detailDialog.job.id) {           // another job is open now: only refresh the lists
                    if (res.ok) { win.reloadAll(); win.refreshOpenView(); ticker.text = "The pasted reply was filed as: " + res.stage + "."; }
                    else ticker.text = res.msg || "The pasted reply could not be filed.";
                    return;
                }
                if (res.ok) {
                    detailDialog.replyInfo = "Filed as: " + res.stage + (res.by_rules ? " (read by the app's rules, not by Claude)" : "") + ".";
                    replyText.text = ""; detailDialog.replyOpen = false;
                    detailDialog.refresh(); win.reloadAll(); win.refreshOpenView();
                } else detailDialog.replyErr = res.msg || "The message could not be filed.";
            } }
        Connections { target: bridge
            function onPrepReady(res) {
                if (res.job_id !== detailDialog.prepJob) return;
                detailDialog.prepBusy = false;
                if (res.ok) { ticker.text = "Interview preparation is ready.";
                              if (detailDialog.visible && detailDialog.job.id === res.job_id) { detailDialog.refresh(); prepDialog.show(res.job_id); } }
                else { detailDialog.prepErr = "Not prepared: " + (res.msg || "unknown reason"); ticker.text = detailDialog.prepErr; }
            } }
        readonly property var fu: job.followup || ({})
        function setStatus(s) {
            var r = bridge.setStatus(job.id, s);
            if (r && r.ok) { refresh(); win.countsData = bridge.counts(); win.refreshOpenView();
                             ticker.text = "Marked " + s.replace("_", " ") + "."; }
            else ticker.text = (r && r.msg) ? r.msg : "Couldn't change the status.";
        }
        function saveDate() {
            dateErr = "";
            var r = bridge.setApplyDate(job.id, dateField.text);
            if (r && r.ok) { refresh(); win.countsData = bridge.counts(); win.refreshOpenView(); ticker.text = "Apply date saved."; }
            else dateErr = (r && r.msg) ? r.msg : "Couldn't save that date.";
        }
        onJobChanged: {
            dateField.text = job.applied || "";
            var e = job.event || {};
            evDate.text = e.date || ""; evTime.text = e.time || ""; evNote.text = e.note || ""; eventKind = e.kind || "interview";
            var n = job.company_notes || {};
            cnContact.text = n.contact || ""; cnSalary.text = n.salary || ""; cnAsked.text = n.asked || ""; cnNotes.text = n.notes || "";
        }
        readonly property bool hasWords: (job.matched || []).length + (job.missing || []).length > 0
        function show(jobId) {
            var d = bridge.jobDetail(jobId);
            if (!d || !d.id) { ticker.text = "That job could not be opened."; return; }
            job = d; draft = ({}); note = ""; dateErr = ""; if (!prepBusy) prepErr = "";
            eventErr = ""; notesInfo = ""; replyErr = ""; replyInfo = ""; replyOpen = false; thanks = ({}); thanksNote = "";
            detailFlick.contentY = 0;
            open();
        }
        function refresh() { var d = bridge.jobDetail(job.id); if (d && d.id) job = d; }
        background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 0
            // header
            RowLayout {
                Layout.fillWidth: true; Layout.margins: 16; spacing: 12
                Rectangle { visible: detailDialog.job.score !== undefined && detailDialog.job.score !== null
                    implicitWidth: 46; implicitHeight: 46; radius: 12
                    color: win.badgeBg(detailDialog.job.tier || ""); border.width: 1
                    border.color: win.badgeColor(detailDialog.job.tier || "")
                    Text { anchors.centerIn: parent; text: "" + detailDialog.job.score
                        color: win.badgeColor(detailDialog.job.tier || ""); font.pixelSize: 17; font.bold: true } }
                ColumnLayout { Layout.fillWidth: true; spacing: 2
                    Text { objectName: "detailTitle"; text: detailDialog.job.title || ""; color: theme.ink; font.pixelSize: 17; font.bold: true
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight }
                    Text { color: theme.soft; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight
                        text: (detailDialog.job.company || "") + (detailDialog.job.location ? "  ·  " + detailDialog.job.location : "") } }
                Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                    Layout.alignment: Qt.AlignTop
                    Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: detailDialog.close() } }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }

            Flickable {
                id: detailFlick
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                contentHeight: detailCol.implicitHeight + 28
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                ColumnLayout {
                    id: detailCol
                    x: 16; y: 14; width: detailFlick.width - 32; spacing: 12

                    ChipFlow {
                        items: [ detailDialog.job.status ? ("" + detailDialog.job.status).replace("_", " ") : "",
                                 detailDialog.job.tier ? detailDialog.job.tier + " match" : "",
                                 detailDialog.job.posted ? "posted " + detailDialog.job.posted : "",
                                 detailDialog.job.applied ? (detailDialog.job.applied_from_email ? "first email " : "applied ") + detailDialog.job.applied : "",
                                 detailDialog.job.source || "",
                                 detailDialog.job.desired ? Number(detailDialog.job.desired).toLocaleString() + " CZK/mo target" : "",
                                 (detailDialog.job.pay && detailDialog.job.pay.low)
                                    ? ("posting says " + (detailDialog.job.pay.low === detailDialog.job.pay.high
                                          ? Math.round(detailDialog.job.pay.low / 1000) + "k"
                                          : Math.round(detailDialog.job.pay.low / 1000) + "–" + Math.round(detailDialog.job.pay.high / 1000) + "k") + " CZK/mo") : "",
                                 detailDialog.job.letter_old_format === true ? "letter: older format, open in Word" : ""
                               ].filter(function (t) { return t !== ""; })
                    }

                    DetailCard { heading: "Why this score"
                        RowLayout { visible: !!detailDialog.job.prefilter; Layout.fillWidth: true; spacing: 10
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                                text: "Not scored, to save a Claude call. " + (detailDialog.job.prefilter || "") }
                            SmallButton { objectName: "scoreAnyway"; text: "Score it anyway"
                                onClicked: { bridge.scoreAnyway(detailDialog.job.id); detailDialog.refresh(); win.refreshOpenView();
                                             ticker.text = "It will be scored on the next Run search."; } } }
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                            visible: !detailDialog.job.prefilter
                            text: detailDialog.job.score_queued ? "You asked for this one to be scored. It is scored on the next Run search."
                                : detailDialog.job.reason ? detailDialog.job.reason
                                : (detailDialog.job.score === undefined || detailDialog.job.score === null)
                                    ? (detailDialog.job.is_application ? "This application came from your emails or your letters folder, so it was never scored."
                                                                       : "This job has not been scored yet. It is scored on the next Run search.")
                                    : "No explanation was saved with this score." } }

                    DetailCard { heading: "Keywords in the posting"
                        Text { visible: !detailDialog.hasWords; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                            text: detailDialog.job.description ? "No known technologies were found in this posting."
                                                               : "No description is saved for this job, so keywords cannot be compared." }
                        Text { visible: (detailDialog.job.matched || []).length > 0; text: "In your CV"; color: theme.good; font.pixelSize: 12; font.bold: true }
                        ChipFlow { objectName: "matchedChips"; visible: (detailDialog.job.matched || []).length > 0
                            items: detailDialog.job.matched || []; tone: theme.good; fill: theme.goodbg }
                        Text { visible: (detailDialog.job.missing || []).length > 0; text: "Not in your CV"; color: theme.warn; font.pixelSize: 12; font.bold: true
                            Layout.topMargin: 2 }
                        ChipFlow { objectName: "missingChips"; visible: (detailDialog.job.missing || []).length > 0
                            items: detailDialog.job.missing || []; tone: theme.warn; fill: theme.warnbg }
                        Text { visible: (detailDialog.job.missing || []).length > 0; Layout.fillWidth: true; wrapMode: Text.WordWrap
                            color: theme.faint; font.pixelSize: 11
                            text: "Shown for your information only. A keyword that is not in your master CV is never added to an adapted CV." }
                    }

                    DetailCard { heading: "Same application twice?"; visible: !!(detailDialog.job.duplicate && detailDialog.job.duplicate.id)
                        border.color: theme.steel
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                            text: detailDialog.job.duplicate && detailDialog.job.duplicate.id
                                ? ("This looks like the same application as \"" + detailDialog.job.duplicate.company + " · "
                                   + detailDialog.job.duplicate.title + "\" (" + detailDialog.job.duplicate.status + "). "
                                   + "Merging keeps one row with both histories, letters and emails.") : "" }
                        RowLayout { Layout.fillWidth: true; spacing: 6
                            Item { Layout.fillWidth: true }
                            SmallButton { text: "They are different"
                                onClicked: { bridge.keepSeparate(detailDialog.job.id, detailDialog.job.duplicate.id);
                                             detailDialog.refresh(); win.countsData = bridge.counts(); win.refreshOpenView(); } }
                            SmallButton { objectName: "mergeButton"; primaryStyle: true; text: "Merge into one"
                                onClicked: { var d = detailDialog.job.duplicate;
                                             var r = bridge.mergeJobs(d.keep, d.drop);
                                             if (r && r.ok) { ticker.text = "Merged into one application.";
                                                 win.countsData = bridge.counts(); win.refreshOpenView(); detailDialog.show(d.keep); } } }
                        }
                    }

                    DetailCard { heading: "Your application"; visible: detailDialog.job.is_application === true
                        RowLayout { Layout.fillWidth: true; spacing: 6
                            Text { text: "Status"; color: theme.soft; font.pixelSize: 12; Layout.preferredWidth: 78 }
                            Repeater {
                                model: [ { s: "waiting", label: "Waiting" }, { s: "interview", label: "Interview" },
                                         { s: "offer", label: "Offer" }, { s: "rejected", label: "Rejected" } ]
                                Rectangle {
                                    objectName: "status_" + modelData.s
                                    readonly property bool current: detailDialog.job.status === modelData.s
                                    implicitHeight: 26; implicitWidth: stT.implicitWidth + 20; radius: 13
                                    color: current ? win.badgeBg(modelData.s) : (stMa.containsMouse ? theme.inset : "transparent")
                                    border.width: 1; border.color: current ? win.badgeColor(modelData.s) : theme.line
                                    Behavior on color { ColorAnimation { duration: 140 } }
                                    Text { id: stT; anchors.centerIn: parent; text: modelData.label; font.pixelSize: 11; font.bold: true
                                        color: parent.current ? win.badgeColor(modelData.s) : theme.soft }
                                    MouseArea { id: stMa; anchors.fill: parent; hoverEnabled: true
                                        cursorShape: parent.current ? Qt.ArrowCursor : Qt.PointingHandCursor
                                        onClicked: if (!parent.current) detailDialog.setStatus(modelData.s) }
                                }
                            }
                            Item { Layout.fillWidth: true }
                        }
                        RowLayout { Layout.fillWidth: true; spacing: 6
                            Text { text: "Applied on"; color: theme.soft; font.pixelSize: 12; Layout.preferredWidth: 78 }
                            TextField { id: dateField; objectName: "dateField"; implicitWidth: 130; implicitHeight: 28
                                placeholderText: "YYYY-MM-DD"; placeholderTextColor: theme.faint
                                color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                inputMethodHints: Qt.ImhDate
                                background: Rectangle { radius: 7; color: theme.inset; border.width: 1
                                    border.color: dateField.activeFocus ? theme.accent : (detailDialog.dateErr !== "" ? theme.crit : theme.line) }
                                onTextEdited: detailDialog.dateErr = ""
                                onAccepted: detailDialog.saveDate() }
                            SmallButton { objectName: "dateSave"; text: "Save date"; onClicked: detailDialog.saveDate() }
                            Text { Layout.fillWidth: true; elide: Text.ElideRight; color: theme.faint; font.pixelSize: 11
                                text: detailDialog.job.applied_from_email ? "taken from the first email" : "" }
                        }
                        Text { objectName: "dateErr"; visible: detailDialog.dateErr !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                            color: theme.crit; font.pixelSize: 11; font.bold: true; text: detailDialog.dateErr }
                    }

                    DetailCard { heading: "A date to remember"; objectName: "eventCard"
                        visible: detailDialog.job.is_application === true
                        border.color: (detailDialog.job.event && detailDialog.job.event.date) ? theme.a2 : theme.line
                        Flow { Layout.fillWidth: true; spacing: 6
                            Repeater { model: ["interview", "deadline", "test task", "call", "other"]
                                Rectangle {
                                    readonly property bool on: detailDialog.eventKind === modelData
                                    height: 24; radius: 12; width: ekT.implicitWidth + 18
                                    color: on ? theme.accent : (ekMa.containsMouse ? theme.inset : "transparent")
                                    border.width: 1; border.color: on ? "transparent" : theme.line
                                    Text { id: ekT; anchors.centerIn: parent; text: modelData; font.pixelSize: 11; font.bold: parent.on
                                        color: parent.on ? "#ffffff" : theme.soft }
                                    MouseArea { id: ekMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        onClicked: detailDialog.eventKind = modelData } } } }
                        RowLayout { Layout.fillWidth: true; spacing: 6
                            TextField { id: evDate; objectName: "evDate"; implicitWidth: 118; implicitHeight: 28; placeholderText: "YYYY-MM-DD"
                                placeholderTextColor: theme.faint; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                background: Rectangle { radius: 7; color: theme.inset; border.width: 1
                                    border.color: evDate.activeFocus ? theme.accent : (detailDialog.eventErr !== "" ? theme.crit : theme.line) }
                                onTextEdited: detailDialog.eventErr = "" }
                            TextField { id: evTime; objectName: "evTime"; implicitWidth: 70; implicitHeight: 28; placeholderText: "HH:MM"
                                placeholderTextColor: theme.faint; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                background: Rectangle { radius: 7; color: theme.inset; border.width: 1
                                    border.color: evTime.activeFocus ? theme.accent : theme.line }
                                onTextEdited: detailDialog.eventErr = "" }
                            TextField { id: evNote; objectName: "evNote"; Layout.fillWidth: true; implicitHeight: 28; placeholderText: "note, e.g. Teams call with the team lead"
                                placeholderTextColor: theme.faint; color: theme.ink; font.pixelSize: 12; selectByMouse: true; maximumLength: 200
                                background: Rectangle { radius: 7; color: theme.inset; border.width: 1
                                    border.color: evNote.activeFocus ? theme.accent : theme.line } }
                            SmallButton { objectName: "evSave"; primaryStyle: true; text: "Save"; onClicked: detailDialog.saveEvent() }
                            SmallButton { objectName: "evCalendar"; visible: !!(detailDialog.job.event && detailDialog.job.event.date)
                                text: "Add to calendar"
                                onClicked: { var c = bridge.exportEvent(detailDialog.job.id);
                                    if (c && c.ok) ticker.text = "Opened a calendar file. Confirm it in Calendar and it syncs to your phone.";
                                    else detailDialog.eventErr = (c && c.msg) || "Couldn't make the calendar file."; } }
                            SmallButton { visible: !!(detailDialog.job.event && detailDialog.job.event.date); text: "Clear"
                                onClicked: { bridge.clearEvent(detailDialog.job.id); detailDialog.refresh(); win.upcomingData = bridge.upcoming(); } }
                        }
                        Text { objectName: "eventErr"; visible: detailDialog.eventErr !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                            color: theme.crit; font.pixelSize: 11; font.bold: true; text: detailDialog.eventErr }
                        Text { visible: detailDialog.eventErr === ""; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                            text: "Shown on the main screen. A notification comes the day before and on the day." }
                    }

                    DetailCard { heading: "After the " + ((detailDialog.job.event && detailDialog.job.event.kind) || "interview"); objectName: "thanksCard"
                        visible: detailDialog.job.thanks_due === true
                        border.color: theme.a2
                        RowLayout { Layout.fillWidth: true; spacing: 10
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 13; color: theme.ink
                                text: "A short thank-you note the same or the next day is a good habit. Here is a draft to adjust and send yourself." }
                            SmallButton { objectName: "thanksToggle"; text: detailDialog.thanks.body ? "Hide draft" : "Draft thank-you"
                                onClicked: { detailDialog.thanksNote = "";
                                    detailDialog.thanks = detailDialog.thanks.body ? ({}) : bridge.thanksDraft(detailDialog.job.id); } }
                        }
                        ColumnLayout { visible: !!detailDialog.thanks.body; Layout.fillWidth: true; spacing: 6
                            TextEdit { Layout.fillWidth: true; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                                text: "Subject: " + (detailDialog.thanks.subject || ""); color: theme.ink; font.pixelSize: 12; font.bold: true
                                selectionColor: theme.accent }
                            Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.color: theme.line; border.width: 1
                                implicitHeight: thanksBody.implicitHeight + 20
                                TextEdit { id: thanksBody; objectName: "thanksBody"; x: 10; y: 10; width: parent.width - 20
                                    readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                                    text: detailDialog.thanks.body || ""; color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent } }
                            RowLayout { Layout.fillWidth: true; spacing: 6
                                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                                    color: detailDialog.thanksNote !== "" ? theme.good : theme.faint
                                    text: detailDialog.thanksNote !== "" ? detailDialog.thanksNote
                                        : "The app never sends email. Add one thing you really talked about before you send it." }
                                SmallButton { text: "Copy"
                                    onClicked: { bridge.copyText((detailDialog.thanks.subject || "") + "\n\n" + (detailDialog.thanks.body || ""));
                                                 detailDialog.thanksNote = "Copied. Paste it into your mail app."; } }
                                SmallButton { objectName: "thanksDone"; primaryStyle: true; text: "Mark as sent"
                                    onClicked: { if (bridge.markThanked(detailDialog.job.id)) {
                                                     detailDialog.refresh(); ticker.text = "Thank-you noted."; } } }
                            }
                        }
                    }

                    DetailCard { heading: "A reply that is not in your mailbox"; objectName: "replyCard"
                        visible: detailDialog.job.is_application === true
                        RowLayout { Layout.fillWidth: true; spacing: 10
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 13
                                color: detailDialog.replyErr !== "" ? theme.crit : (detailDialog.replyInfo !== "" ? theme.good : theme.ink)
                                text: detailDialog.replyBusy ? "Reading the message…"
                                    : detailDialog.replyErr !== "" ? detailDialog.replyErr
                                    : detailDialog.replyInfo !== "" ? detailDialog.replyInfo
                                    : "Got an answer on LinkedIn or in a company portal? Paste it here and it is filed like an email." }
                            SmallButton { objectName: "replyToggle"; visible: !detailDialog.replyBusy
                                text: detailDialog.replyOpen ? "Cancel" : "Paste a reply"
                                onClicked: { detailDialog.replyOpen = !detailDialog.replyOpen; detailDialog.replyErr = ""; } }
                        }
                        ColumnLayout { visible: detailDialog.replyOpen; Layout.fillWidth: true; spacing: 6
                            Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1
                                border.color: replyText.activeFocus ? theme.accent : theme.line; implicitHeight: 110; clip: true
                                Flickable { anchors.fill: parent; anchors.margins: 8; contentHeight: replyText.implicitHeight; clip: true
                                    TextEdit { id: replyText; objectName: "replyText"; width: parent.width; wrapMode: TextEdit.Wrap; selectByMouse: true
                                        color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                                        Text { visible: replyText.text === ""; text: "Paste the message text here"; color: theme.faint; font.pixelSize: 12 } } } }
                            RowLayout { Layout.fillWidth: true
                                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                    text: "Claude reads it (one call). If the limit is used up, the app's own rules decide." }
                                SmallButton { objectName: "replyFile"; primaryStyle: true; enabled: !detailDialog.replyBusy
                                    text: detailDialog.replyBusy ? "Reading…" : "File it"; onClicked: detailDialog.fileReply() } }
                        }
                    }

                    DetailCard { heading: "Notes about " + (detailDialog.job.company || "this company")
                        objectName: "notesCard"
                        // for a job you have not applied to, only when you already keep notes on that company
                        visible: !!detailDialog.job.company && detailDialog.job.company !== "unknown"
                                 && (detailDialog.job.is_application === true
                                     || !!(detailDialog.job.company_notes && detailDialog.job.company_notes.updated))
                        GridLayout { Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 6
                            Text { text: "Who you spoke to"; color: theme.soft; font.pixelSize: 12 }
                            TextField { id: cnContact; objectName: "cnContact"; Layout.fillWidth: true; implicitHeight: 28; color: theme.ink; font.pixelSize: 12
                                selectByMouse: true; maximumLength: 200; placeholderText: "name, role"; placeholderTextColor: theme.faint
                                background: Rectangle { radius: 7; color: theme.inset; border.width: 1; border.color: cnContact.activeFocus ? theme.accent : theme.line }
                                onTextEdited: detailDialog.notesInfo = "" }
                            Text { text: "Salary mentioned"; color: theme.soft; font.pixelSize: 12 }
                            TextField { id: cnSalary; objectName: "cnSalary"; Layout.fillWidth: true; implicitHeight: 28; color: theme.ink; font.pixelSize: 12
                                selectByMouse: true; maximumLength: 200; placeholderText: "what they said, what you said"; placeholderTextColor: theme.faint
                                background: Rectangle { radius: 7; color: theme.inset; border.width: 1; border.color: cnSalary.activeFocus ? theme.accent : theme.line }
                                onTextEdited: detailDialog.notesInfo = "" }
                            Text { text: "What they asked"; color: theme.soft; font.pixelSize: 12 }
                            TextField { id: cnAsked; objectName: "cnAsked"; Layout.fillWidth: true; implicitHeight: 28; color: theme.ink; font.pixelSize: 12
                                selectByMouse: true; maximumLength: 400; placeholderText: "questions, tasks"; placeholderTextColor: theme.faint
                                background: Rectangle { radius: 7; color: theme.inset; border.width: 1; border.color: cnAsked.activeFocus ? theme.accent : theme.line }
                                onTextEdited: detailDialog.notesInfo = "" }
                        }
                        Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1
                            border.color: cnNotes.activeFocus ? theme.accent : theme.line; implicitHeight: Math.max(54, cnNotes.implicitHeight + 16)
                            TextEdit { id: cnNotes; objectName: "cnNotes"; x: 8; y: 8; width: parent.width - 16; wrapMode: TextEdit.Wrap; selectByMouse: true
                                color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                                onTextChanged: if (activeFocus) detailDialog.notesInfo = ""
                                Text { visible: cnNotes.text === ""; text: "Anything else worth remembering"; color: theme.faint; font.pixelSize: 12 } } }
                        RowLayout { Layout.fillWidth: true; spacing: 6
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                                color: detailDialog.notesInfo !== "" ? theme.good : theme.faint
                                text: detailDialog.notesInfo !== "" ? detailDialog.notesInfo
                                    : "Kept for the company, so they show again on every job there"
                                      + ((detailDialog.job.company_notes && detailDialog.job.company_notes.updated) ? " · last changed " + detailDialog.job.company_notes.updated : "") + "." }
                            SmallButton { objectName: "notesSave"; text: "Save notes"; onClicked: detailDialog.saveNotes() }
                        }
                    }

                    DetailCard { heading: "Interview preparation"; visible: detailDialog.job.is_application === true
                        border.color: detailDialog.job.status === "interview" ? theme.good : theme.line
                        RowLayout { Layout.fillWidth: true; spacing: 10
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                                text: detailDialog.prepBusy ? "Preparing questions and answers from your CV… this takes about a minute."
                                    : detailDialog.prepErr !== "" ? detailDialog.prepErr
                                    : detailDialog.job.has_prep ? ("Questions and answers are ready (made " + detailDialog.job.prep_made + ").")
                                    : detailDialog.job.status === "interview" ? "You have an interview here. Get likely questions with answers built from your CV."
                                    : "Likely questions for this role, with answers built from your CV." 
                                Binding on color { when: detailDialog.prepErr !== "" && !detailDialog.prepBusy; value: theme.crit } }
                            SmallButton { visible: detailDialog.job.has_prep === true && !detailDialog.prepBusy; text: "Open"
                                primaryStyle: true; objectName: "prepOpen"; onClicked: prepDialog.show(detailDialog.job.id) }
                            SmallButton { objectName: "prepMake"; enabled: !detailDialog.prepBusy
                                text: detailDialog.prepBusy ? "Preparing…" : (detailDialog.job.has_prep ? "Make again" : "Prepare")
                                onClicked: { detailDialog.prepErr = ""; detailDialog.prepBusy = true; detailDialog.prepJob = detailDialog.job.id;
                                             bridge.prepareInterview(detailDialog.job.id); } }
                        }
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                            text: "Asks Claude once or twice (uses your limit). Answers use only what your CV shows." }
                    }

                    DetailCard { heading: "Follow-up"; visible: detailDialog.job.status === "waiting"
                        border.color: detailDialog.fu.due ? theme.warn : theme.line
                        RowLayout { Layout.fillWidth: true; spacing: 10
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 13
                                color: detailDialog.fu.due ? theme.warn : theme.ink
                                text: !detailDialog.fu.since ? "The app does not know when you applied, so it will not remind you about this one."
                                    : detailDialog.fu.stale ? ("Silent for " + win.daysText(detailDialog.fu.days_waiting) + ". This one has most likely gone quiet; no reminder.")
                                    : detailDialog.fu.due ? ((detailDialog.fu.had_reply ? "Only a confirmation so far, no decision for " : "No reply for ")
                                                             + win.daysText(detailDialog.fu.days_waiting) + ". A short follow-up is reasonable now.")
                                    : (detailDialog.fu.days_waiting === 0 ? "Last activity today"
                                       : "Last activity " + win.daysText(detailDialog.fu.days_waiting) + " ago")
                                      + (
                                         detailDialog.fu.followed_up ? " (you followed up on " + detailDialog.fu.followed_up + ")." : ".") }
                            SmallButton { text: detailDialog.draft.body ? "Hide draft" : "Draft follow-up"
                                onClicked: { detailDialog.note = "";
                                    detailDialog.draft = detailDialog.draft.body ? ({}) : bridge.followupDraft(detailDialog.job.id); } }
                        }
                        ColumnLayout { visible: !!detailDialog.draft.body; Layout.fillWidth: true; spacing: 6
                            TextEdit { Layout.fillWidth: true; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                                text: "Subject: " + (detailDialog.draft.subject || ""); color: theme.ink; font.pixelSize: 12; font.bold: true
                                selectionColor: theme.accent }
                            Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.color: theme.line; border.width: 1
                                implicitHeight: draftBody.implicitHeight + 20
                                TextEdit { id: draftBody; objectName: "draftBody"; x: 10; y: 10; width: parent.width - 20
                                    readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                                    text: detailDialog.draft.body || ""; color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent } }
                            RowLayout { Layout.fillWidth: true; spacing: 6
                                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                                    color: detailDialog.note !== "" ? theme.good : theme.faint
                                    text: detailDialog.note !== "" ? detailDialog.note
                                        : "The app never sends email. Copy the text and send it from your own mail." }
                                SmallButton { text: "Copy"
                                    onClicked: { bridge.copyText((detailDialog.draft.subject || "") + "\n\n" + (detailDialog.draft.body || ""));
                                                 detailDialog.note = "Copied. Paste it into your mail app."; } }
                                SmallButton { primaryStyle: true; text: "Mark as followed up"
                                    onClicked: { if (bridge.markFollowedUp(detailDialog.job.id)) {
                                                     detailDialog.draft = ({}); detailDialog.refresh(); win.countsData = bridge.counts();
                                                     ticker.text = "Follow-up noted. The reminder starts counting again."; } } }
                            }
                        }
                    }

                    DetailCard { heading: "Notes"; visible: !!detailDialog.job.notes || !!detailDialog.job.next_step
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 12; lineHeight: 1.25
                            text: (detailDialog.job.next_step ? "Next step: " + detailDialog.job.next_step + "\n" : "") + (detailDialog.job.notes || "") } }

                    DetailCard { heading: "Description"; visible: !!detailDialog.job.description
                        TextEdit { Layout.fillWidth: true; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                            text: detailDialog.job.description || ""; color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent } }
                }
            }

            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            RowLayout { objectName: "detailFooter"; Layout.fillWidth: true; Layout.margins: 12; spacing: 6
                Flow { objectName: "detailDocs"; Layout.fillWidth: true; Layout.minimumWidth: 120; spacing: 6
                SmallButton { visible: !!detailDialog.job.url; text: "Open posting ↗"
                    onClicked: { var r = bridge.openUrl(detailDialog.job.id);
                                 ticker.text = (r && r.ok) ? "Opened the job posting in your browser." : "No link for this job."; } }
                SmallButton { visible: !!detailDialog.job.cv; text: "CV"; onClicked: bridge.openDoc("cv", detailDialog.job.cv) }
                SmallButton { visible: detailDialog.job.cv_pdf === true; text: "CV PDF"; onClicked: bridge.openDoc("cv_pdf", detailDialog.job.cv) }
                SmallButton { visible: !!detailDialog.job.letter; text: "Letter"; onClicked: bridge.openDoc("letter", detailDialog.job.letter) }
                SmallButton { visible: detailDialog.job.letter_pdf === true; text: "Letter PDF"; onClicked: bridge.openDoc("letter_pdf", detailDialog.job.letter) }
                SmallButton { objectName: "compareCv"; visible: detailDialog.job.can_compare === true; text: "Compare CV"
                    onClicked: compareDialog.show(detailDialog.job.id) }
                SmallButton { objectName: "editLetter"; visible: detailDialog.job.letter_editable === true; text: "Edit letter"
                    onClicked: letterDialog.show(detailDialog.job.id) }
                }
                SmallButton { objectName: "answersOpen"; text: "Answers"; onClicked: answersDialog.show(detailDialog.job.id) }
                SmallButton { objectName: "notInterested"; visible: detailDialog.job.is_lead === true; text: "Not interested"
                    onClicked: { var r = bridge.dismissJob(detailDialog.job.id);
                                 if (r && r.ok) { ticker.text = "Removed. It will not come back in later searches (see the “not interested” filter to undo).";
                                     detailDialog.close(); win.countsData = bridge.counts(); win.refreshOpenView(); }
                                 else ticker.text = (r && r.msg) ? r.msg : "Couldn't remove that job."; } }
                SmallButton { visible: detailDialog.job.is_dismissed === true; primaryStyle: true; text: "Restore to New Jobs"
                    onClicked: { bridge.restoreJob(detailDialog.job.id); detailDialog.refresh();
                                 win.countsData = bridge.counts(); win.refreshOpenView(); ticker.text = "Back in New Jobs."; } }
                PillButton { visible: detailDialog.job.is_lead === true; primaryStyle: true; text: "Mark applied"
                    onClicked: { bridge.applyJob(detailDialog.job.id); ticker.text = "Moved to Applications (waiting).";
                                 detailDialog.close(); tableDialog.close(); win.reloadAll(); } }
            }
        }
    }

    // ───────────────────────── master CV next to the adapted one ─────────────────────────
    Dialog {
        id: compareDialog; objectName: "compareDialog"
        modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
        enter: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
        exit: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
            NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
        Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
        width: Math.min(980, win.width - 40); height: Math.min(760, win.height - 50)
        padding: 0
        property var data: ({})
        function show(jobId) {
            var d = bridge.cvCompare(jobId);
            if (!d || !d.ok) { ticker.text = (d && d.msg) ? d.msg : "These CVs cannot be compared."; return; }
            data = d; cmpFlick.contentY = 0; open();
        }
        background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 0
            RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
                ColumnLayout { Layout.fillWidth: true; spacing: 2
                    Text { text: "Your CV, before and after"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                    Text { objectName: "compareSummary"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                        text: (compareDialog.data.company || "") + "  ·  " + (compareDialog.data.changed || 0) + (compareDialog.data.changed === 1 ? " paragraph changed" : " paragraphs changed")
                              + ((compareDialog.data.added || 0) > 0 ? ", " + compareDialog.data.added + " added" : "")
                              + ((compareDialog.data.removed || 0) > 0 ? ", " + compareDialog.data.removed + " removed" : "")
                              + "  ·  " + (compareDialog.data.same || 0) + " identical (not shown)" } }
                Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                    Layout.alignment: Qt.AlignTop
                    Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: compareDialog.close() } }
            }
            RowLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 8; spacing: 12
                Text { Layout.fillWidth: true; Layout.preferredWidth: 1; text: "MASTER CV"; color: theme.faint; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.4 }
                Text { Layout.fillWidth: true; Layout.preferredWidth: 1; text: "ADAPTED FOR THIS JOB"; color: theme.accent; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.4 }
            }
            Rectangle { objectName: "olderMaster"; visible: compareDialog.data.older_master === true
                Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 8
                radius: 8; color: theme.inset; border.color: theme.warn; border.width: 1; implicitHeight: omT.implicitHeight + 14
                Text { id: omT; x: 10; y: 7; width: parent.width - 20; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 12
                    text: "This CV was adapted before you last changed your master CV. Differences outside the profile and the skills come from that older master, not from the adaptation." } }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            Flickable {
                id: cmpFlick
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                contentHeight: cmpCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                ColumnLayout {
                    id: cmpCol
                    x: 16; y: 14; width: cmpFlick.width - 32; spacing: 10
                    Text { visible: (compareDialog.data.rows || []).length === 0; Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: theme.soft; font.pixelSize: 13; text: "The adapted CV is identical to your master CV." }
                    Repeater {
                        model: compareDialog.data.rows || []
                        ColumnLayout { Layout.fillWidth: true; spacing: 4
                            Text { visible: index === 0 || compareDialog.data.rows[index - 1].section !== modelData.section
                                text: modelData.section || "Start of the CV"; color: theme.faint; font.pixelSize: 10; font.bold: true
                                font.letterSpacing: 1.2; font.capitalization: Font.AllUppercase; Layout.topMargin: index === 0 ? 0 : 6 }
                            RowLayout { Layout.fillWidth: true; spacing: 12
                                Rectangle { Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.alignment: Qt.AlignTop
                                    radius: 9; color: theme.surface2; border.color: theme.line; border.width: 1
                                    implicitHeight: lT.implicitHeight + 18
                                    Text { id: lT; x: 10; y: 9; width: parent.width - 20; wrapMode: Text.WordWrap; textFormat: Text.StyledText
                                        color: theme.soft; font.pixelSize: 12; lineHeight: 1.25
                                        text: modelData.master !== "" ? modelData.master : "<i>not in the master CV</i>" } }
                                Rectangle { Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.alignment: Qt.AlignTop
                                    radius: 9; color: theme.surface2; border.width: 1
                                    border.color: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.6)
                                    implicitHeight: rT.implicitHeight + 18
                                    Text { id: rT; x: 10; y: 9; width: parent.width - 20; wrapMode: Text.WordWrap; textFormat: Text.StyledText
                                        color: theme.ink; font.pixelSize: 12; lineHeight: 1.25
                                        text: modelData.adapted !== "" ? modelData.adapted : "<i>removed in the adapted CV</i>" } }
                            }
                        }
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                    text: "Left: words that were replaced are struck through. Right: new words are bold." }
                SmallButton { text: "Open the adapted CV"; onClicked: bridge.openDoc("cv", compareDialog.data.file || "") }
                PillButton { primaryStyle: true; text: "Close"; onClicked: compareDialog.close() }
            }
        }
    }

    // ───────────────────────── answers to repeated form questions ─────────────────────────
    Dialog {
        id: answersDialog; objectName: "answersDialog"
        modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
        enter: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
        exit: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
            NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
        Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
        width: Math.min(720, win.width - 60); height: Math.min(740, win.height - 50)
        padding: 0
        property string jobId: ""             // the job whose company and role fill {company} and {role}
        property string info: ""
        property bool dirty: false
        ListModel { id: answersModel }
        function show(job) {
            jobId = job || ""; info = ""; dirty = false;
            answersModel.clear();
            var list = bridge.answers();
            for (var i = 0; i < list.length; i++) answersModel.append({ question: list[i].question, answer: list[i].answer });
            ansFlick.contentY = 0; open();
        }
        function all() {
            var out = [];
            for (var i = 0; i < answersModel.count; i++) out.push({ question: answersModel.get(i).question, answer: answersModel.get(i).answer });
            return out;
        }
        function save() {
            var r = bridge.saveAnswers(all());
            if (r && r.ok) { dirty = false; info = "Saved."; show(jobId); info = "Saved."; }
            else info = "Couldn't save the answers.";
        }
        function copy(i) {
            var text = answersModel.get(i).answer;
            if (text.trim() === "") { info = "That answer is still empty."; return; }
            bridge.copyAnswer(text, jobId);
            info = "Copied" + (jobId !== "" && /\{(company|role)\}/.test(text) ? ", with this job's company and role filled in." : ".");
        }
        background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 0
            RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
                ColumnLayout { Layout.fillWidth: true; spacing: 2
                    Text { text: "Your answers"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 12
                        text: "Write each answer once, then copy it into application forms. {company} and {role} are replaced with the job's when you open this from a job window." } }
                Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                    Layout.alignment: Qt.AlignTop
                    Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: answersDialog.close() } }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            Flickable {
                id: ansFlick
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                contentHeight: ansCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                ColumnLayout {
                    id: ansCol
                    x: 16; y: 14; width: ansFlick.width - 32; spacing: 12
                    Repeater {
                        model: answersModel
                        Rectangle { Layout.fillWidth: true; radius: 12; color: theme.surface2; border.color: theme.line; border.width: 1
                            implicitHeight: ansItem.implicitHeight + 24
                            ColumnLayout { id: ansItem; x: 12; y: 12; width: parent.width - 24; spacing: 6
                                RowLayout { Layout.fillWidth: true; spacing: 6
                                    TextField { Layout.fillWidth: true; implicitHeight: 28; text: model.question; color: theme.ink
                                        font.pixelSize: 13; font.bold: true; selectByMouse: true; maximumLength: 200
                                        placeholderText: "The question"; placeholderTextColor: theme.faint
                                        background: Rectangle { radius: 7; color: theme.inset; border.width: 1
                                            border.color: parent.activeFocus ? theme.accent : theme.line }
                                        onTextEdited: { answersModel.setProperty(index, "question", text); answersDialog.dirty = true; answersDialog.info = ""; } }
                                    SmallButton { text: "Copy"; onClicked: answersDialog.copy(index) }
                                    SmallButton { text: "Remove"
                                        onClicked: { answersModel.remove(index); answersDialog.dirty = true; answersDialog.info = ""; } }
                                }
                                Rectangle { Layout.fillWidth: true; radius: 8; color: theme.inset; border.width: 1
                                    border.color: ansEdit.activeFocus ? theme.accent : theme.line
                                    implicitHeight: Math.max(56, ansEdit.implicitHeight + 16)
                                    TextEdit { id: ansEdit; x: 8; y: 8; width: parent.width - 16; wrapMode: TextEdit.Wrap; selectByMouse: true
                                        color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                                        Component.onCompleted: text = model.answer
                                        onTextChanged: if (activeFocus) { answersModel.setProperty(index, "answer", text); answersDialog.dirty = true; answersDialog.info = ""; }
                                        Text { visible: ansEdit.text === ""; text: "Your answer"; color: theme.faint; font.pixelSize: 12 } } }
                            }
                        }
                    }
                    SmallButton { objectName: "answersAdd"; text: "+ Add a question"
                        onClicked: { answersModel.append({ question: "", answer: "" }); answersDialog.dirty = true; answersDialog.info = ""; } }
                }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
                Text { objectName: "answersInfo"; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                    color: answersDialog.info !== "" ? theme.good : theme.faint
                    text: answersDialog.info !== "" ? answersDialog.info
                        : answersDialog.dirty ? "Not saved yet." : "Kept encrypted on this Mac. A question with no text is dropped when you save." }
                SmallButton { text: "Close"; onClicked: answersDialog.close() }
                PillButton { objectName: "answersSave"; primaryStyle: true; text: "Save"; onClicked: answersDialog.save() }
            }
        }
    }

    // ───────────────────────── help ─────────────────────────
    Dialog {
        id: helpDialog; objectName: "helpDialog"
        modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
        enter: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
        exit: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
            NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
        Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
        width: Math.min(720, win.width - 60); height: Math.min(760, win.height - 50)
        padding: 0
        property string tab: "how"            // how: how the app works | new: what changed
        property var changes: []
        onAboutToShow: { helpFlick.contentY = 0; changes = bridge.changelog(); }
        onTabChanged: helpFlick.contentY = 0
        // Each topic: a title and short lines. Kept here so the help always matches this window.
        readonly property var topics: [
            { title: "What JobHelper does", lines: [
                "It finds jobs that fit your CV, writes an adapted CV and a cover letter for the good ones, and keeps track of what you applied to and what the companies answered.",
                "Five robots do the work, in this order: <b>Profiler</b> reads your CV, <b>Scout</b> searches the job boards, <b>Scribe</b> scores each job and writes the documents, <b>Tracker</b> builds the Excel files, <b>Postman</b> reads the replies in your inbox." ] },
            { title: "A normal week", lines: [
                "1. Press <b>Run search</b>. New jobs appear in <b>New Jobs</b>, best <b>score</b> first.",
                "2. Open a job (click its row) and read why it got its <b>score</b>. Open the CV and the letter, check them, and apply on the company's site.",
                "3. Press <b>Mark applied</b>. The job moves to <b>Applications</b>.",
                "4. Press <b>Scan email</b> now and then. Replies update your applications by themselves.",
                "The <b>Weekly run</b> card can do steps 1 and 4 for you once a week." ] },
            { title: "The buttons at the top", lines: [
                "<b>Run search</b>: runs <b>Profiler</b>, <b>Scout</b>, <b>Scribe</b> and <b>Tracker</b>. While it runs the button becomes <b>Stop</b>; everything finished before you stop is saved.",
                "<b>Scan email</b>: <b>Postman</b> reads your inbox. It only reads. It <b>never sends</b>, deletes or marks an email.",
                "The status bar under the line shows the step, the progress and the time." ] },
            { title: "Scores and labels", lines: [
                "Each job gets a <b>score</b> from 0 to 100 for how well it fits your CV.",
                "<b>strong</b>: 60 or more. <b>moderate</b>: 50 to 59. <b>stretch</b>: below 50 but above your own <b>limit</b>; read \"<b>Why this score</b>\" before applying.",
                "<b>skipped</b>: the app saw from the title that it is another profession and did not spend a Claude call on it. \"<b>Score it anyway</b>\" in the job window overrides that.",
                "<b>Options</b>, \"<b>Write letters above</b>\", sets from which <b>score</b> a CV and a letter are written." ] },
            { title: "The lists on the left", lines: [
                "<b>New Jobs</b>: jobs you have not applied to. <b>Applications</b>: jobs you applied to, with their status. <b>Responses</b>: every reply email. <b>Analytics</b>: the numbers. <b>Insights</b>: what works, how each <b>search</b> keyword performs, skills worth learning, and what the postings say they pay next to your target.",
                "In every list you can <b>search</b>, <b>filter</b> with the chips and <b>sort</b>. Click a row to open it.",
                "<b>Filtered out</b> in the <b>Last run</b> card lists every posting the last <b>search</b> removed before scoring, with the reason for each one. If a rule removes jobs you want, change it in <b>Options</b>.",
                "<b>Not interested</b> (in a job's window) removes a job for good; the \"<b>not interested</b>\" chip in <b>New Jobs</b> brings it back." ] },
            { title: "The job window", lines: [
                "It shows the description, why the job got its <b>score</b>, which keywords from the posting are in your CV and which are not, and buttons for the CV, the letter and their PDFs.",
                "For an application you can change the status by hand (<b>Waiting</b>, <b>Interview</b>, <b>Offer</b>, <b>Rejected</b>), set the day you applied, prepare for an interview, and draft a follow-up email to copy.",
                "<b>Edit letter</b> lets you change a letter the app wrote, or have one paragraph rewritten. Your own letters are never changed by the app.",
                "For a job you applied to: <b>A date to remember</b>: put an interview, a deadline or a test task on a job. It appears under <b>Coming up</b> on the main screen, and you get a notification the day before and on the day.",
                "<b>Paste a reply</b>: an answer that came on LinkedIn or in a company portal can be pasted in, and it is filed like an email.",
                "<b>Notes</b> are kept for the company, not the job: who you spoke to, the salary mentioned, what they asked. They show again when you apply there later.",
                "<b>Compare CV</b> puts your <b>master CV</b> next to the adapted one and shows only the paragraphs that differ.",
                "<b>Add to calendar</b> opens a saved date in Calendar, so your phone reminds you too. From the day of an interview the window offers a <b>thank-you</b> draft.",
                "<b>Answers</b> keeps your replies to questions forms repeat (salary, start date, why this company) ready to copy." ] },
            { title: "Your CV and letters", lines: [
                "The app <b>never invents experience</b>. An adapted CV changes only the Profile and Key Skills parts of your <b>master CV</b>, and a letter may only use what your CV shows.",
                "Change your <b>master CV</b> in the <b>Account card</b>. The rules the app follows are in two files in the data folder; if you edit them by hand, approve the change in the <b>Account</b> card." ] },
            { title: "Claude and the limit", lines: [
                "The app works through your Claude subscription, so a <b>search</b> costs you nothing extra. \"<b>Same work via API</b>\" on the Last run card shows what the same work would have cost with pay-per-use API billing.",
                "Your subscription has a <b>5-hour</b> and a <b>7-day</b> <b>limit</b> (<b>Usage left</b>, top right). When one is used up, the run pauses, saves, and shows a warning. <b>Resume</b> turns blue when the limit is back.",
                "To use less: fewer <b>search</b> roles, Czech boards instead of every source, a higher \"<b>Write letters above</b>\"." ] },
            { title: "Privacy and safety", lines: [
                "Everything stays on your Mac. Your job data and backups are <b>encrypted</b> on disk, and the Gmail app password and the data key are in the macOS <b>Keychain</b>.",
                "Save your <b>recovery key</b> once (python status.py security recovery-key) and keep it in a password manager: on a new Mac it is the only way to open your data.",
                "Only job postings, your CV text and the text of reply emails are sent to Claude, to <b>score</b> jobs and write documents." ] },
            { title: "If something looks wrong", lines: [
                "A robot or button does nothing: open the <b>Account</b> chip on the left and check the four rows are green.",
                "A rejection is missing: it probably did not arrive in the scanned mailbox. Mark it by hand in the job window, or add a <b>second mailbox</b> in the <b>Account card</b>.",
                "Too many poor jobs: add words to \"<b>Skip titles with</b>\" in <b>Options</b>, or remove a <b>search</b> role that <b>Insights</b> marks as weak.",
                "More detail on every command is in the file <b>COMMANDS.md</b> in the app's folder." ] }
        ]
        background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 0
            RowLayout { Layout.fillWidth: true; Layout.margins: 16
                Text { text: "Help"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                Row { Layout.leftMargin: 14; spacing: 6
                    Repeater { model: [["how", "How it works"], ["new", "What changed"]]
                        Rectangle {
                            readonly property bool on: helpDialog.tab === modelData[0]
                            objectName: "helpTab_" + modelData[0]
                            height: 26; radius: 13; width: htT.implicitWidth + 22
                            color: on ? theme.accent : (htMa.containsMouse ? theme.inset : "transparent")
                            border.width: 1; border.color: on ? "transparent" : theme.line
                            Text { id: htT; anchors.centerIn: parent; text: modelData[1]; font.pixelSize: 12; font.bold: parent.on
                                color: parent.on ? "#ffffff" : theme.soft }
                            MouseArea { id: htMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: helpDialog.tab = modelData[0] } } } }
                Item { Layout.fillWidth: true }
                Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                    Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: helpDialog.close() } }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            Flickable {
                id: helpFlick
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                contentHeight: helpCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                ColumnLayout {
                    id: helpCol
                    x: 16; y: 14; width: helpFlick.width - 32; spacing: 12
                    Text { visible: helpDialog.tab === "new" && helpDialog.changes.length === 0; Layout.fillWidth: true
                        wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 13
                        text: "The list of changes (CHANGELOG.md in the app's folder) could not be read." }
                    Repeater {
                        model: helpDialog.tab === "new" ? helpDialog.changes : []
                        DetailCard { heading: modelData.date
                            Repeater { model: modelData.items
                                RowLayout { Layout.fillWidth: true; spacing: 8
                                    Text { text: "•"; color: theme.accent; font.pixelSize: 13; Layout.alignment: Qt.AlignTop }
                                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.3
                                        textFormat: Text.StyledText; text: modelData } } } }
                    }
                    Repeater {
                        model: helpDialog.tab === "how" ? helpDialog.topics : []
                        DetailCard { heading: modelData.title
                            Repeater { model: modelData.lines
                                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.3
                                    textFormat: Text.StyledText        // key words are in <b>bold</b>
                                    text: modelData } } }
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            RowLayout { Layout.fillWidth: true; Layout.margins: 12
                Item { Layout.fillWidth: true }
                PillButton { primaryStyle: true; text: "Close"; implicitWidth: 120; onClicked: helpDialog.close() } }
        }
    }

    // ───────────────────────── interview preparation ─────────────────────────
    Dialog {
        id: prepDialog; objectName: "prepDialog"
        modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
        enter: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
        exit: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
            NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
        Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
        width: Math.min(760, win.width - 60); height: Math.min(780, win.height - 50)
        padding: 0
        property var prep: ({})
        property string note: ""
        function show(jobId) {
            var d = bridge.interviewPrep(jobId);
            if (!d || !d.id) { ticker.text = "No interview preparation is saved for this job yet."; return; }
            prep = d; note = ""; prepFlick.contentY = 0; open();
        }
        background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 0
            RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
                ColumnLayout { Layout.fillWidth: true; spacing: 2
                    Text { text: "Interview preparation"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                    Text { objectName: "prepFor"; Layout.fillWidth: true; elide: Text.ElideRight; color: theme.soft; font.pixelSize: 12
                        text: (prepDialog.prep.company || "") + "  ·  " + (prepDialog.prep.title || "") } }
                Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                    Layout.alignment: Qt.AlignTop
                    Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: prepDialog.close() } }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            Flickable {
                id: prepFlick
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                contentHeight: prepCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                ColumnLayout {
                    id: prepCol
                    x: 16; y: 14; width: prepFlick.width - 32; spacing: 12
                    DetailCard { heading: "What to expect"; visible: !!prepDialog.prep.summary
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                            text: prepDialog.prep.summary || "" } }
                    Repeater {
                        model: prepDialog.prep.questions || []
                        ColumnLayout { Layout.fillWidth: true; spacing: 6
                            Text { visible: index === 0 || (prepDialog.prep.questions[index - 1].kind !== modelData.kind)
                                text: modelData.kind; color: theme.accent; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.4
                                font.capitalization: Font.AllUppercase; Layout.topMargin: index === 0 ? 0 : 6 }
                            Rectangle { Layout.fillWidth: true; radius: 12; color: theme.surface2; border.width: 1
                                border.color: modelData.check ? theme.warn : theme.line
                                implicitHeight: qaCol.implicitHeight + 24
                                ColumnLayout { id: qaCol; x: 14; y: 12; width: parent.width - 28; spacing: 6
                                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 14; font.bold: true
                                        text: (index + 1) + ".  " + modelData.question }
                                    Text { visible: !!modelData.why; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                        text: "Why they ask: " + (modelData.why || "") }
                                    TextEdit { Layout.fillWidth: true; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                                        text: modelData.answer; color: theme.ink; font.pixelSize: 13; selectionColor: theme.accent }
                                    Text { visible: !!modelData.check; Layout.fillWidth: true; wrapMode: Text.WordWrap
                                        color: theme.warn; font.pixelSize: 11; font.bold: true
                                        text: "Check this answer: it talks about " + (modelData.check || "") + ", which is not in your CV. Say only what is true." }
                                }
                            }
                        }
                    }
                    DetailCard { heading: "Questions to ask them"; visible: (prepDialog.prep.ask_them || []).length > 0
                        Repeater { model: prepDialog.prep.ask_them || []
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; text: "•  " + modelData } } }
                    DetailCard { heading: "Revise before the interview"; visible: (prepDialog.prep.revise || []).length > 0
                        Repeater { model: prepDialog.prep.revise || []
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; text: "•  " + modelData } } }
                }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                    color: prepDialog.note !== "" ? theme.good : theme.faint
                    text: prepDialog.note !== "" ? prepDialog.note
                        : "Answers are a starting point built from your CV. Say them in your own words." }
                SmallButton { objectName: "prepCopy"; text: "Copy all"
                    onClicked: { bridge.copyText(bridge.prepText(prepDialog.prep.id)); prepDialog.note = "Copied. Paste it into Notes or a document."; } }
                PillButton { primaryStyle: true; text: "Close"; onClicked: prepDialog.close() }
            }
        }
    }

    // ───────────────────────── edit a letter the app wrote ─────────────────────────
    Dialog {
        id: letterDialog; objectName: "letterDialog"
        modal: true; anchors.centerIn: parent; closePolicy: Popup.NoAutoClose
        enter: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
        exit: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
            NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
        Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
        width: Math.min(760, win.width - 60); height: Math.min(760, win.height - 50)
        padding: 0
        property var meta: ({})
        property var texts: []                // the five paragraphs as edited
        property var original: []
        property int busyIndex: -1            // paragraph Claude is rewriting, -1 = none
        property string err: ""
        property var warnings: []
        property string info: ""
        readonly property bool dirty: JSON.stringify(texts) !== JSON.stringify(original)
        readonly property int words: texts.join(" ").split(/\s+/).filter(function (w) { return w !== ""; }).length
        ListModel { id: paraModel }
        function show(jobId) {
            var d = bridge.letterForEdit(jobId);
            if (!d || !d.ok) { ticker.text = (d && d.msg) ? d.msg : "This letter cannot be edited here."; return; }
            meta = d; original = d.paragraphs.slice(); texts = d.paragraphs.slice();
            paraModel.clear();
            for (var i = 0; i < texts.length; i++) paraModel.append({ body: texts[i] });
            busyIndex = -1; err = ""; warnings = []; info = ""; hintField.text = "";
            letterFlick.contentY = 0;
            open();
        }
        function setText(i, t) { var c = texts.slice(); c[i] = t; texts = c; }
        function rewrite(i) {
            if (busyIndex >= 0) return;
            err = ""; info = ""; busyIndex = i;
            bridge.rewriteParagraph(meta.id, texts, i, hintField.text);
        }
        function save() {
            err = ""; info = "";
            var r = bridge.saveLetter(meta.id, texts);
            if (!r || !r.ok) { err = (r && r.msg) ? r.msg : "The letter could not be saved."; return; }
            original = texts.slice(); warnings = r.warnings || [];
            info = warnings.length === 0 ? "Saved. The Word file and the PDF are updated."
                                         : "Saved, with the notes below. The Word file and the PDF are updated.";
            detailDialog.refresh();
        }
        Connections { target: bridge
            function onParagraphReady(res) {
                if (!letterDialog.visible || res.job_id !== letterDialog.meta.id) return;
                letterDialog.busyIndex = -1;
                if (res.ok) { paraModel.setProperty(res.index, "body", res.paragraph); letterDialog.setText(res.index, res.paragraph);
                              letterDialog.info = "Paragraph " + (res.index + 1) + " was rewritten. Read it, then Save or change it back."; }
                else letterDialog.err = "Paragraph " + (res.index + 1) + " was not rewritten: " + (res.msg || "unknown reason");
            } }
        background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 0
            RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
                ColumnLayout { Layout.fillWidth: true; spacing: 2
                    Text { text: "Cover letter"; color: theme.ink; font.pixelSize: 17; font.bold: true }
                    Text { Layout.fillWidth: true; elide: Text.ElideRight; color: theme.soft; font.pixelSize: 12
                        text: (letterDialog.meta.company || "") + "  ·  " + (letterDialog.meta.title_line || letterDialog.meta.title || "") } }
                Text { objectName: "letterWords"; font.pixelSize: 12; font.bold: true
                    color: (letterDialog.words < (letterDialog.meta.min_words || 0) || letterDialog.words > (letterDialog.meta.max_words || 9999)) ? theme.warn : theme.soft
                    text: letterDialog.words + " words" }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            Flickable {
                id: letterFlick
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                contentHeight: letterCol.implicitHeight + 28; boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                ColumnLayout {
                    id: letterCol
                    x: 16; y: 14; width: letterFlick.width - 32; spacing: 12
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                        text: "Only the five paragraphs are edited. The head, date, greeting, signature, fonts and layout stay as they are." }
                    Repeater {
                        model: paraModel
                        ColumnLayout { Layout.fillWidth: true; spacing: 4
                            RowLayout { Layout.fillWidth: true; spacing: 8
                                Text { text: "Paragraph " + (index + 1) + "  ·  " + ["hook", "strongest evidence", "second theme", "learning and fit", "close"][index]
                                    color: theme.faint; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.0; font.capitalization: Font.AllUppercase
                                    Layout.fillWidth: true }
                                Text { color: theme.faint; font.pixelSize: 11
                                    text: (letterDialog.texts[index] || "").split(/\s+/).filter(function (w) { return w !== ""; }).length + " words" }
                                SmallButton { objectName: "rewrite" + index
                                    text: letterDialog.busyIndex === index ? "Rewriting…" : "Rewrite this paragraph"
                                    enabled: letterDialog.busyIndex < 0; onClicked: letterDialog.rewrite(index) }
                            }
                            Rectangle { Layout.fillWidth: true; radius: 9; color: theme.inset; border.width: 1
                                border.color: pEdit.activeFocus ? theme.accent : theme.line
                                implicitHeight: pEdit.implicitHeight + 20
                                opacity: letterDialog.busyIndex === index ? 0.5 : 1
                                TextEdit { id: pEdit; x: 10; y: 10; width: parent.width - 20
                                    text: model.body; wrapMode: TextEdit.Wrap; selectByMouse: true
                                    readOnly: letterDialog.busyIndex === index
                                    color: theme.ink; font.pixelSize: 13; selectionColor: theme.accent
                                    onTextChanged: if (text !== letterDialog.texts[index]) letterDialog.setText(index, text) }
                            }
                        }
                    }
                    RowLayout { Layout.fillWidth: true; spacing: 8
                        Text { text: "For a rewrite"; color: theme.soft; font.pixelSize: 12 }
                        TextField { id: hintField; objectName: "hintField"; Layout.fillWidth: true; implicitHeight: 30
                            placeholderText: "Optional: what should change? e.g. shorter, more about my main project"
                            placeholderTextColor: theme.faint; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                            background: Rectangle { radius: 8; color: theme.inset; border.width: 1
                                border.color: hintField.activeFocus ? theme.accent : theme.line } }
                    }
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                        text: "A rewrite asks Claude once or twice and uses your limit. It follows your letter rules and your CV; nothing is saved until you press Save." }
                    Text { objectName: "letterErr"; visible: letterDialog.err !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: theme.crit; font.pixelSize: 12; font.bold: true; text: letterDialog.err }
                    Text { objectName: "letterInfo"; visible: letterDialog.info !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: theme.good; font.pixelSize: 12; font.bold: true; text: letterDialog.info }
                    Repeater { model: letterDialog.warnings
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.warn; font.pixelSize: 12; text: "• " + modelData } }
                }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
                SmallButton { text: "Open in Word"; onClicked: bridge.openDoc("letter", detailDialog.job.letter || "") }
                SmallButton { text: "Undo my changes"; enabled: letterDialog.dirty && letterDialog.busyIndex < 0
                    onClicked: { letterDialog.texts = letterDialog.original.slice();
                                 for (var i = 0; i < letterDialog.original.length; i++) paraModel.setProperty(i, "body", letterDialog.original[i]);
                                 letterDialog.err = ""; letterDialog.info = ""; } }
                Item { Layout.fillWidth: true }
                Text { visible: letterDialog.dirty; text: "not saved"; color: theme.warn; font.pixelSize: 11; font.bold: true }
                SmallButton { text: "Close"; onClicked: letterDialog.close() }
                PillButton { objectName: "letterSave"; primaryStyle: true; text: "Save"
                    enabled: letterDialog.dirty && letterDialog.busyIndex < 0; onClicked: letterDialog.save() }
            }
        }
    }

    // ───────────────────────── one reply in full ─────────────────────────
    Dialog {
        id: responseDialog; objectName: "responseDialog"
        modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
        enter: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
        exit: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
            NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
        Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
        width: Math.min(620, win.width - 80); padding: 0
        property var r: ({})
        function show(msgId) {
            var d = bridge.responseDetail(msgId);
            if (!d || !d.id) { ticker.text = "That reply could not be opened."; return; }
            r = d; open();
        }
        background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 0
            RowLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
                ColumnLayout { Layout.fillWidth: true; spacing: 2
                    Text { objectName: "responseTitle"; text: responseDialog.r.company || ""; color: theme.ink; font.pixelSize: 17; font.bold: true
                        Layout.fillWidth: true; elide: Text.ElideRight }
                    Text { text: responseDialog.r.role || ""; visible: text !== ""; color: theme.soft; font.pixelSize: 12
                        Layout.fillWidth: true; wrapMode: Text.WordWrap } }
                Rectangle { visible: !!responseDialog.r.stage; radius: 999; implicitHeight: 22; implicitWidth: rsT.width + 18
                    Layout.alignment: Qt.AlignTop; color: win.badgeBg(responseDialog.r.stage || "")
                    Text { id: rsT; anchors.centerIn: parent; text: responseDialog.r.stage || ""; font.pixelSize: 11; font.bold: true
                        color: win.badgeColor(responseDialog.r.stage || "") } }
                Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                    Layout.alignment: Qt.AlignTop
                    Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: responseDialog.close() } }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            ColumnLayout { Layout.fillWidth: true; Layout.margins: 16; spacing: 12
                DetailCard { heading: "What it says"
                    Text { objectName: "responseSummary"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                        text: responseDialog.r.summary || "No summary was saved for this email." } }
                DetailCard { heading: "Rejection"; visible: responseDialog.r.stage === "rejection"
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; lineHeight: 1.25
                        text: (responseDialog.r.category ? "Reason given: " + responseDialog.r.category + "." : "No reason was given.")
                              + (responseDialog.r.reason ? "\n" + responseDialog.r.reason : "") } }
                DetailCard { heading: "Next step"; visible: !!responseDialog.r.next_step
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 13; text: responseDialog.r.next_step || "" } }
                DetailCard { heading: "The email"
                    TextEdit { Layout.fillWidth: true; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                        color: theme.ink; font.pixelSize: 12; selectionColor: theme.accent
                        text: "Subject: " + (responseDialog.r.subject || "—") + "\nFrom: " + (responseDialog.r.sender || "—")
                              + "\nReceived: " + (responseDialog.r.date || "—") } }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            RowLayout { Layout.fillWidth: true; Layout.margins: 12; spacing: 6
                Text { Layout.fillWidth: true; elide: Text.ElideRight; color: theme.faint; font.pixelSize: 11
                    text: responseDialog.r.job_id ? ("Belongs to: " + responseDialog.r.job_company + " · " + responseDialog.r.job_title
                                                     + " (" + responseDialog.r.job_status + ")")
                                                  : "Not linked to an application in your list." }
                SmallButton { objectName: "openApplication"; visible: !!responseDialog.r.job_id; text: "Open the application"
                    onClicked: { var id = responseDialog.r.job_id; responseDialog.close(); detailDialog.show(id); } }
            }
        }
    }

    // ───────────────────────── limit warning ─────────────────────────
    Dialog {
        id: limitDialog; objectName: "limitDialog"
        modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
        enter: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
        exit: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
            NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
        Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
        width: Math.min(440, win.width - 80); padding: 0
        background: Rectangle { radius: 18; color: theme.winbg; border.color: theme.warn; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 0
            Item { Layout.preferredHeight: 26 }
            // warning triangle with an exclamation mark
            Item {
                Layout.alignment: Qt.AlignHCenter; implicitWidth: 96; implicitHeight: 84
                Shape {
                    anchors.fill: parent
                    ShapePath { strokeColor: theme.warn; strokeWidth: 4; fillColor: theme.warnbg
                        joinStyle: ShapePath.RoundJoin; capStyle: ShapePath.RoundCap
                        startX: 48; startY: 6
                        PathLine { x: 92; y: 78 } PathLine { x: 4; y: 78 } PathLine { x: 48; y: 6 } }
                }
                Rectangle { x: 45; y: 30; width: 6; height: 26; radius: 3; color: theme.warn }
                Rectangle { x: 44.5; y: 62; width: 7; height: 7; radius: 3.5; color: theme.warn }
                SequentialAnimation on scale { running: limitDialog.visible; loops: 2
                    NumberAnimation { to: 1.08; duration: 260; easing.type: Easing.OutCubic }
                    NumberAnimation { to: 1.0; duration: 260; easing.type: Easing.InOutSine } }
            }
            Text { Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 10
                text: "WARNING"; color: theme.warn; font.pixelSize: 13; font.bold: true; font.letterSpacing: 3 }
            Text { objectName: "limitText"
                Layout.fillWidth: true; Layout.leftMargin: 30; Layout.rightMargin: 30; Layout.topMargin: 12
                horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 14; lineHeight: 1.3
                text: "Claude's " + (limitData.window || "usage") + " limit is used up"
                      + (limitData.used ? " (" + limitData.used + "%)" : "") + ".\n"
                      + "The run is paused and everything done so far is saved.\n"
                      + (limitData.resets_at ? "It resets at " + limitData.resets_at
                            + (limitData.resets_day ? " on " + limitData.resets_day : "") + ". " : "")
                      + "The Resume button turns blue when you can continue." }
            Item { Layout.preferredHeight: 22 }
            PillButton { objectName: "limitClose"; Layout.alignment: Qt.AlignHCenter; implicitWidth: 150
                primaryStyle: true; text: "Close"; onClicked: limitDialog.close() }
            Item { Layout.preferredHeight: 24 }
        }
    }

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
    component StepDot: Item {
        id: sd
        property bool ok: false
        property bool busy: false
        property string label: "1"
        implicitWidth: 26; implicitHeight: 26
        Rectangle { anchors.fill: parent; radius: 13
            color: sd.ok ? theme.goodbg : theme.inset
            border.color: sd.ok ? theme.good : theme.line; border.width: 1.5
            Behavior on color { ColorAnimation { duration: win.motion } } }
        Text { anchors.centerIn: parent; text: sd.label; visible: !sd.ok && !sd.busy
            color: theme.soft; font.pixelSize: 12; font.bold: true }
        Item { anchors.fill: parent; visible: sd.busy && !sd.ok
            RotationAnimation on rotation { running: sd.busy && !sd.ok; from: 0; to: 360; duration: 900; loops: Animation.Infinite }
            Rectangle { x: 11.5; y: 3; width: 3; height: 7; radius: 1.5; color: theme.accent } }
        Item {                                  // clip grows left→right so the tick is "drawn"
            x: 6; y: 6; height: 14; clip: true
            width: sd.ok ? 14 : 0
            Behavior on width { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
            Shape { width: 14; height: 14; visible: sd.ok
                ShapePath { strokeColor: theme.good; strokeWidth: 2.2; fillColor: "transparent"
                    capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                    startX: 2; startY: 7.5
                    PathLine { x: 5.8; y: 11 } PathLine { x: 12; y: 3.5 } } }
        }
    }
    component StepRow: RowLayout {
        id: sr
        property alias ok: dot.ok
        property alias busy: dot.busy
        property alias label: dot.label
        property string title: ""
        property string sub: ""
        property color subColor: theme.soft
        property int order: 0
        default property alias actions: act.data
        Layout.fillWidth: true; spacing: 12
        opacity: Math.max(0, Math.min(1, card.appear * 2.2 - order * 0.35))
        transform: Translate { y: (1 - sr.opacity) * 10 }
        StepDot { id: dot }
        ColumnLayout { Layout.fillWidth: true; spacing: 1
            Text { text: sr.title; color: theme.ink; font.pixelSize: 14; font.bold: true }
            Text { text: sr.sub; color: sr.subColor; font.pixelSize: 12; Layout.fillWidth: true
                maximumLineCount: 3; elide: Text.ElideRight; wrapMode: Text.WordWrap } }
        Row { id: act; spacing: 6; Layout.alignment: Qt.AlignVCenter }
    }

    Item {
        id: welcome; objectName: "welcome"
        anchors.fill: parent; z: 50
        property bool shown: true
        property string phase: "splash"      // splash | card
        property bool first: true            // launch (Start) vs reopened (Done)
        property bool introDone: false
        property bool waitingLogin: false
        property bool editEmail: false
        property int editBox: 1               // which mailbox the editor is for: 1 main, 2 the optional second one
        property string emailDraft: ""
        property string pwDraft: ""
        property string emailErr: ""
        property string cvErr: ""
        property real cover: shown ? 1 : 0
        readonly property bool hasCv: (connData.cv || "") !== ""
        readonly property var changedFiles: connData.changed_files || []
        readonly property bool protectedOk: connData.vault !== "locked" && changedFiles.length === 0
        readonly property bool ready: connData.claude === true && hasCv && connData.paid_api !== true && protectedOk
        Behavior on cover { NumberAnimation { duration: 460; easing.type: Easing.InOutCubic } }
        visible: cover > 0.001

        function advance() { if (phase === "splash" && introDone && win.connChecked) phase = "card"; }
        function openCard() {
            first = false; phase = "card"; editEmail = false; emailErr = ""; cvErr = ""; waitingLogin = false;
            emailDraft = connData.email_addr || ""; pwDraft = "";
            shown = true; bridge.checkConnections(); keySink.forceActiveFocus();
        }
        function finish() { shown = false; waitingLogin = false; editEmail = false; }
        function saveEmail() {
            emailErr = "";
            if (!win.isEmail(emailDraft)) { emailErr = "Enter a valid email address (e.g. you@gmail.com)."; shake.restart(); return; }
            if (pwDraft !== "" && !win.isAppPassword(pwDraft)) {
                emailErr = "A Gmail App Password is 16 letters (no spaces). Check for typos."; shake.restart(); return; }
            var known = editBox === 2 ? connData.email2 === true : connData.email === true;
            if (!known && pwDraft === "") { emailErr = "Enter the Gmail App Password for this mailbox."; shake.restart(); return; }
            if (editBox === 2 && emailDraft.trim().toLowerCase() === (connData.email_addr || "").toLowerCase()) {
                emailErr = "That is already your main job email. Enter a different address."; shake.restart(); return; }
            var r = editBox === 2 ? bridge.saveEmail2(emailDraft, pwDraft) : bridge.saveEmail(emailDraft, pwDraft);
            pwDraft = "";
            if (r && r.ok) { editEmail = false; bridge.checkConnections(); }
            else { emailErr = (r && r.msg) ? r.msg : "Couldn't save the email."; shake.restart(); }
        }
        onPhaseChanged: if (phase === "card") { emailDraft = connData.email_addr || ""; keySink.forceActiveFocus(); }
        Connections { target: win; function onConnCheckedChanged() { welcome.advance(); } }
        Connections { target: bridge
            function onConnectionsReady(info) { if (info.claude === true) welcome.waitingLogin = false; } }
        Timer { interval: 2500; repeat: true; running: welcome.shown && welcome.waitingLogin
            onTriggered: bridge.checkConnections() }
        Timer { interval: 6000; running: welcome.phase === "splash"      // never get stuck on the splash
            onTriggered: { win.connChecked = true; welcome.introDone = true; welcome.advance(); } }

        // backdrop: solid for the launch splash, frosted over the live app afterwards
        Rectangle { anchors.fill: parent; color: theme.winbg
            opacity: welcome.cover * (welcome.phase === "splash" ? 1 : (win.dark ? 0.62 : 0.55))
            Behavior on opacity { NumberAnimation { duration: 520; easing.type: Easing.InOutCubic } } }
        MouseArea { anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.AllButtons
            onWheel: function (w) { w.accepted = true; }
            onPressed: keySink.forceActiveFocus() }
        Item { id: keySink; focus: welcome.shown
            Keys.onReturnPressed: if (welcome.phase === "card" && (welcome.ready || !welcome.first)) welcome.finish()
            Keys.onEnterPressed: if (welcome.phase === "card" && (welcome.ready || !welcome.first)) welcome.finish()
            Keys.onEscapePressed: if (welcome.phase === "card" && !welcome.first) welcome.finish() }

        Item {
            id: wstage
            anchors.fill: parent
            opacity: welcome.cover
            scale: 1 + 0.05 * (1 - welcome.cover)

            // the logo: a robot on a piece of belt. Large in the splash, then it
            // travels up to sit on top of the card.
            Item {
                id: logo
                width: 240; height: 112
                x: (parent.width - width) / 2
                y: welcome.phase === "splash" ? (parent.height - height) / 2 - 30 : card.y - 104
                scale: welcome.phase === "splash" ? 1.7 : 0.9
                opacity: 0
                property real beltW: 0
                Behavior on y { NumberAnimation { duration: 560; easing.type: Easing.OutBack; easing.overshoot: 0.7 } }
                Behavior on scale { NumberAnimation { duration: 560; easing.type: Easing.OutBack; easing.overshoot: 0.7 } }
                Rectangle { x: (logo.width - width) / 2; y: 68; width: logo.beltW; height: 40; radius: 20; color: theme.beltDark }
                Rectangle { x: (logo.width - width) / 2; y: 73; width: Math.max(0, logo.beltW - 10); height: 30; radius: 15; color: theme.belt }
                Robot { id: logoBot; x: 60; theme: theme; ag: theme.accent; kind: "search"; interactive: false
                    done: welcome.phase === "card" && welcome.ready }
                SequentialAnimation {
                    id: intro; running: true
                    PauseAnimation { duration: 120 }
                    ParallelAnimation {
                        NumberAnimation { target: logo; property: "opacity"; to: 1; duration: 320; easing.type: Easing.OutCubic }
                        NumberAnimation { target: logo; property: "beltW"; to: 240; duration: 620; easing.type: Easing.OutCubic }
                    }
                    ScriptAction { script: logoBot.active = true }
                    PauseAnimation { duration: 700 }
                    ScriptAction { script: { logoBot.active = false; welcome.introDone = true; welcome.advance(); } }
                }
            }
            Column {
                anchors.horizontalCenter: parent.horizontalCenter
                y: parent.height / 2 + 92
                spacing: 6
                opacity: welcome.phase === "splash" ? logo.opacity : 0
                Behavior on opacity { NumberAnimation { duration: 200 } }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "JobHelper"
                    color: theme.ink; font.pixelSize: 26; font.bold: true; font.letterSpacing: -0.3 }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Checking your connections…"
                    color: theme.faint; font.pixelSize: 12 }
            }

            // the card
            Rectangle {
                id: card
                width: Math.min(470, parent.width - 60)
                height: cardCol.implicitHeight + 44
                x: (parent.width - width) / 2 + shakeX
                y: Math.max(108, (parent.height - height) / 2 + 40) + (1 - appear) * 18
                radius: 20
                color: Qt.rgba(theme.surface.r, theme.surface.g, theme.surface.b, win.dark ? 0.90 : 0.94)
                border.width: 1
                border.color: drop.containsDrag ? theme.accent : Qt.rgba(theme.steel.r, theme.steel.g, theme.steel.b, 0.35)
                property real shakeX: 0
                property real appear: welcome.phase === "card" ? 1 : 0
                Behavior on appear { NumberAnimation { duration: 620; easing.type: Easing.OutCubic } }
                Behavior on height { NumberAnimation { duration: win.motion; easing.type: Easing.OutCubic } }
                opacity: Math.min(1, appear * 2.5)
                scale: 0.94 + 0.06 * appear
                visible: appear > 0.001
                SequentialAnimation { id: shake
                    NumberAnimation { target: card; property: "shakeX"; to: -9; duration: 50 }
                    NumberAnimation { target: card; property: "shakeX"; to: 8; duration: 70 }
                    NumberAnimation { target: card; property: "shakeX"; to: -5; duration: 70 }
                    NumberAnimation { target: card; property: "shakeX"; to: 0; duration: 80; easing.type: Easing.OutCubic } }
                // soft shadow
                Repeater { model: 4
                    Rectangle { z: -1; anchors.fill: parent; anchors.margins: -3 * (index + 1); radius: 20 + 3 * (index + 1)
                        color: "#000000"; opacity: win.dark ? 0.07 : 0.022 } }
                DropArea { id: drop; anchors.fill: parent
                    onDropped: function (d) { if (d.hasUrls && d.urls.length) win.applyCv(d.urls[0].toString()); } }

                ColumnLayout {
                    id: cardCol
                    x: 24; y: 22; width: parent.width - 48; spacing: 16

                    ColumnLayout { Layout.fillWidth: true; spacing: 3
                        Text { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter
                            color: theme.ink; font.pixelSize: 21; font.bold: true; font.letterSpacing: -0.2
                            text: !welcome.first ? "Account & connections" : (welcome.ready ? "Welcome back" : "Let's get you set up") }
                        Text { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                            color: theme.soft; font.pixelSize: 12
                            text: welcome.ready ? "Everything is connected. Your assembly line is ready."
                                : !welcome.protectedOk ? "Your data protection needs a look before the line can run."
                                : "Two things are needed before the line can run." }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line; opacity: 0.7 }

                    // 1 · Claude
                    StepRow {
                        order: 0; label: "1"; title: "Claude account"
                        ok: connData.claude === true && connData.paid_api !== true
                        busy: welcome.waitingLogin || !win.connChecked
                        subColor: connData.paid_api === true ? theme.crit : theme.soft
                        sub: connData.paid_api === true ? "A paid API key is set. Unset ANTHROPIC_API_KEY to use your subscription."
                           : connData.claude === true ? ((connData.claude_email || "Signed in") + (connData.plan ? " · " + connData.plan.charAt(0).toUpperCase() + connData.plan.slice(1) + " plan" : ""))
                           : welcome.waitingLogin ? "Finish signing in in the Terminal window that opened. This updates by itself."
                           : "Runs on your subscription, never the paid API."
                        SmallButton { visible: connData.claude === true; text: "Switch"
                            onClicked: { bridge.claudeLogin(); } }
                        PillButton { visible: connData.claude !== true; primaryStyle: true
                            text: welcome.waitingLogin ? "Waiting…" : "Sign in with Claude"; enabled: !welcome.waitingLogin
                            onClicked: { var r = bridge.claudeLogin(); if (r && r.ok) welcome.waitingLogin = true; } }
                    }

                    // 2 · Job email (the editor unfolds under the row)
                    ColumnLayout { Layout.fillWidth: true; spacing: 0
                    StepRow {
                        order: 1; label: "2"; title: "Job email"
                        ok: connData.email === true
                        sub: connData.email === true ? ((connData.email_addr || "") + " · read-only")
                                                     : "Optional. Reads replies from Gmail, never sends or deletes."
                        SmallButton { visible: !welcome.editEmail; text: connData.email === true ? "Change" : "Connect"
                            onClicked: { welcome.editBox = 1; welcome.emailDraft = connData.email_addr || ""; welcome.pwDraft = ""; welcome.emailErr = "";
                                         welcome.editEmail = true; wEmail.forceActiveFocus(); } }
                    }
                    // optional second mailbox (replies that go to another address)
                    RowLayout { objectName: "secondMailRow"
                        visible: connData.email === true && !welcome.editEmail
                        Layout.fillWidth: true; Layout.leftMargin: 38; Layout.topMargin: 4; spacing: 6
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                            color: connData.email2 === true ? theme.soft : theme.faint
                            text: connData.email2 === true ? ("Second mailbox: " + (connData.email2_addr || "") + " · read-only")
                                                           : "Second mailbox (optional)" }
                        SmallButton { objectName: "secondMailAdd"; text: connData.email2 === true ? "Change" : "Add"
                            onClicked: { welcome.editBox = 2; welcome.emailDraft = connData.email2_addr || ""; welcome.pwDraft = "";
                                         welcome.emailErr = ""; welcome.editEmail = true; wEmail.forceActiveFocus(); } }
                        SmallButton { visible: connData.email2 === true; text: "Remove"
                            onClicked: { bridge.removeEmail2(); bridge.checkConnections(); } }
                    }
                    Item {
                        Layout.fillWidth: true; clip: true
                        Layout.preferredHeight: welcome.editEmail ? emailCol.implicitHeight + 10 : 0
                        opacity: welcome.editEmail ? 1 : 0
                        Behavior on Layout.preferredHeight { NumberAnimation { duration: win.motion; easing.type: Easing.OutCubic } }
                        Behavior on opacity { NumberAnimation { duration: win.motion } }
                        ColumnLayout { id: emailCol; y: 10; width: parent.width; spacing: 8
                            Text { visible: welcome.editBox === 2; Layout.leftMargin: 38; text: "Second mailbox (optional)"
                                color: theme.soft; font.pixelSize: 11; font.bold: true }
                            TextField { id: wEmail; Layout.fillWidth: true; Layout.leftMargin: 38; placeholderText: "you@gmail.com"
                                text: welcome.emailDraft; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                placeholderTextColor: theme.faint
                                background: Rectangle { radius: 8; color: theme.inset; border.width: 1
                                    border.color: wEmail.activeFocus ? theme.accent
                                        : (welcome.emailErr !== "" && !win.isEmail(welcome.emailDraft) ? theme.crit : theme.line) }
                                onTextEdited: { welcome.emailDraft = text; welcome.emailErr = ""; }
                                onAccepted: wPw.forceActiveFocus() }
                            TextField { id: wPw; Layout.fillWidth: true; Layout.leftMargin: 38; echoMode: TextInput.Password
                                placeholderText: (welcome.editBox === 2 ? connData.email2 === true : connData.email === true)
                                                 ? "App password (leave blank to keep)" : "Gmail App Password (16 letters)"
                                text: welcome.pwDraft; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                placeholderTextColor: theme.faint
                                background: Rectangle { radius: 8; color: theme.inset; border.width: 1
                                    border.color: wPw.activeFocus ? theme.accent
                                        : (welcome.emailErr !== "" && win.isEmail(welcome.emailDraft) ? theme.crit : theme.line) }
                                onTextEdited: { welcome.pwDraft = text; welcome.emailErr = ""; }
                                onAccepted: welcome.saveEmail() }
                            Text { visible: welcome.emailErr !== ""; Layout.fillWidth: true; Layout.leftMargin: 38; wrapMode: Text.WordWrap
                                color: theme.crit; font.pixelSize: 11; font.bold: true; text: welcome.emailErr }
                            RowLayout { Layout.fillWidth: true; Layout.leftMargin: 38; spacing: 6
                                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                    text: "Use a Google App Password, not your normal password." }
                                SmallButton { text: "Cancel"; onClicked: { welcome.editEmail = false; welcome.emailErr = ""; keySink.forceActiveFocus(); } }
                                SmallButton { primaryStyle: true; text: "Save"; onClicked: welcome.saveEmail() } }
                        }
                    }
                    }

                    // 3 · Master CV
                    StepRow {
                        order: 2; label: "3"; title: "Master CV"
                        ok: welcome.hasCv
                        subColor: welcome.cvErr !== "" ? theme.crit : theme.soft
                        sub: welcome.cvErr !== "" ? welcome.cvErr
                           : drop.containsDrag ? "Drop it to use this file."
                           : welcome.hasCv ? connData.cv : "Drop a .docx or .pdf here, or choose a file."
                        SmallButton { text: welcome.hasCv ? "Change…" : "Choose…"; onClicked: cvDialog.open() }
                    }

                    // 4 · Data protection (encryption + tamper check)
                    StepRow {
                        order: 3; label: "4"; title: "Data protection"
                        ok: connData.vault === "ok" && welcome.changedFiles.length === 0
                        subColor: welcome.protectedOk ? theme.soft : theme.crit
                        sub: connData.vault === "locked"
                                ? "Your data is encrypted but its key is not in the Keychain. Run: python status.py security restore-key"
                           : welcome.changedFiles.length > 0
                                ? ("Changed outside the app: " + welcome.changedFiles.join(", ") + ". Check them, then approve.")
                           : connData.vault === "ok" ? "Encrypted on disk · key and Gmail password in your Keychain"
                           : "Off: no Keychain on this system, files are stored plain."
                        SmallButton { visible: welcome.changedFiles.length > 0 && connData.vault === "ok"; primaryStyle: true
                            text: "Approve"; onClicked: { bridge.approveChanges(); bridge.checkConnections(); } }
                    }

                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line; opacity: 0.7 }
                    RowLayout { Layout.fillWidth: true; spacing: 10
                        opacity: Math.max(0, Math.min(1, card.appear * 2.2 - 1.05))
                        Text { Layout.fillWidth: true; color: theme.faint; font.pixelSize: 11; wrapMode: Text.WordWrap
                            visible: welcome.first && !welcome.ready
                            text: "Continue without setup"; font.underline: skipMa.containsMouse
                            MouseArea { id: skipMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: welcome.finish() } }
                        Item { Layout.fillWidth: true; visible: !(welcome.first && !welcome.ready) }
                        SmallButton { text: "Recheck"; visible: !welcome.first; onClicked: bridge.checkConnections() }
                        PillButton { objectName: "welcomeStart"; primaryStyle: true; implicitWidth: 120
                            text: welcome.first ? "Start" : "Done"
                            enabled: welcome.ready || !welcome.first
                            onClicked: welcome.finish() }
                    }
                }
            }
        }
    }

    // ───────────────────────── options (macOS-style) ─────────────────────────
    Dialog {
        id: optDialog; objectName: "optDialog"
        modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
        enter: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
        exit: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
            NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
        Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
        width: Math.min(540, win.width - 80)
        height: Math.min(700, win.height - 80)
        padding: 0
        ListModel { id: rolesModel }
        ListModel { id: companiesModel }
        property string roleErr: ""
        // "software engineering intern" as a search role while "intern" is skipped would
        // search for jobs only to throw them all away.
        function roleClash(roles, skips, keeps) {
            function has(text, word) {
                var w = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
                return new RegExp("(^|[^a-z0-9])" + w + "s?([^a-z0-9]|$)", "i").test(text);
            }
            for (var i = 0; i < roles.length; i++) {
                var kept = false;
                for (var k = 0; k < keeps.length; k++) if (has(roles[i], keeps[k])) kept = true;
                if (kept) continue;
                for (var j = 0; j < skips.length; j++)
                    if (has(roles[i], skips[j]))
                        return "The search role “" + roles[i] + "” contains “" + skips[j] + "”, which you skip. Remove one of them.";
            }
            return "";
        }
        function addRole(txt) {
            var t = (txt || "").trim();
            roleErr = "";
            if (!t) return false;
            if (win.hasNonLatin(t)) { roleErr = "Use English (Latin letters) for search roles."; return false; }
            if (!/[a-zA-Z]/.test(t) || t.length < 2) { roleErr = "Enter a real role, e.g. 'junior data analyst'."; return false; }
            if (!win.looksLikeRole(t)) { roleErr = "“" + t + "” doesn't look like a job role — check spelling or try e.g. 'backend developer'."; return false; }
            for (var i = 0; i < rolesModel.count; i++)
                if (rolesModel.get(i).text.toLowerCase() === t.toLowerCase()) { roleErr = "That role is already in the list."; return false; }
            rolesModel.append({ text: t });
            return true;
        }
        property string coErr: ""
        property string optErr: ""
        function addCompany(name, ats, token) {
            var tok = (token || "").trim();
            coErr = "";
            if (!tok) { coErr = "Enter the company's token (the slug in its career-site URL)."; return false; }
            if (!win.isSlug(tok)) { coErr = "Token looks wrong — use the URL slug only (letters, digits, - or _), no spaces or https://."; return false; }
            for (var i = 0; i < companiesModel.count; i++)
                if (companiesModel.get(i).token.toLowerCase() === tok.toLowerCase()
                    && companiesModel.get(i).ats === ats) { coErr = "That company is already in the list."; return false; }
            companiesModel.append({ name: (name || "").trim() || tok, ats: ats, token: tok });
            return true;
        }
        // show the city in English even if it was saved in its native form
        function cityDisplay(c) {
            var m = { "praha": "Prague", "plzeň": "Pilsen", "plzen": "Pilsen",
                      "české budějovice": "Budweis", "wien": "Vienna", "münchen": "Munich",
                      "köln": "Cologne", "warszawa": "Warsaw", "kraków": "Kraków" };
            return m[(c || "").toLowerCase()] || c || "Prague";
        }
        function load() {
            var o = win.optsData;
            cityCombo.editText = cityDisplay(o.where);
            srcCombo.currentIndex = Math.max(0, srcCombo.indexOfValue(o.source || "czech"));
            remoteSw.checked = o.include_remote === true;
            fullSw.checked = o.full_time_only !== false;
            skipTags.setAll(o.skip_words !== undefined ? o.skip_words : ["intern", "internship"]);
            keepTags.setAll(o.keep_words || []);
            levelTags.setAll(o.level_words || []);
            yearsSpin.value = o.max_years !== undefined ? o.max_years : 4;
            engSw.checked = !(o.all_languages === true);
            ageSpin.value = o.max_age_days !== undefined ? o.max_age_days : 10;
            pqSpin.value = o.per_query || 15;
            thrSpin.value = o.threshold !== undefined ? o.threshold : 50;
            minSpin.value = o.min_lead_score || 0;
            fuSpin.value = o.followup_days !== undefined ? o.followup_days : 10;
            scanSpin.value = o.scan_days !== undefined ? o.scan_days : 30;
            rightField.text = o.about_right_to_work || ""; startField.text = o.about_start || "";
            notifySw.checked = o.notifications !== false;
            foldersSw.checked = o.scan_all_folders === true;
            keepSpin.value = o.keep_backups !== undefined ? o.keep_backups : 10;
            modelCombo.currentIndex = Math.max(0, modelCombo.find(o.model || "sonnet"));
            rolesModel.clear();
            var qs = o.queries || [];
            for (var i = 0; i < qs.length; i++) rolesModel.append({ text: qs[i] });
            companiesModel.clear();
            var cs = bridge.companies();
            for (var k = 0; k < cs.length; k++)
                companiesModel.append({ name: cs[k].name, ats: cs[k].ats, token: cs[k].token });
            coErr = ""; optErr = ""; roleErr = "";
            optSink.forceActiveFocus();                    // no field is pre-selected when the window opens
            if (optScroll && optScroll.contentItem) {      // always open at the top
                optScroll.contentItem.cancelFlick(); optScroll.contentItem.contentY = 0;
            }
        }
        onAboutToShow: load()      // fill + reset BEFORE the window is visible (not after the animation)
        background: Rectangle {
            radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
            MouseArea { anchors.fill: parent; onPressed: function (m) { optSink.forceActiveFocus(); m.accepted = false; } }
        }
        Item { id: optSink }
        contentItem: ColumnLayout {
            spacing: 0
            RowLayout { Layout.fillWidth: true; Layout.margins: 16
                Text { text: "Options"; color: theme.ink; font.pixelSize: 17; font.bold: true; Layout.fillWidth: true }
                Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                    Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: optDialog.close() } } }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }

            ScrollView {
                id: optScroll; objectName: "optScroll"
                Layout.fillWidth: true; Layout.fillHeight: true
                contentWidth: availableWidth; clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                Item {
                    width: optDialog.width
                    implicitHeight: scrollCol.implicitHeight
                    // clicking empty space (even inside the scroll area) drops the
                    // spin-box / field focus so its accent outline clears
                    MouseArea { anchors.fill: parent; onPressed: function (m) { optSink.forceActiveFocus(); m.accepted = false; } }
                ColumnLayout {
                    id: scrollCol
                    anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
                    spacing: 16
                    // outer padding
                    Item { Layout.preferredHeight: 2 }

                    // ── SEARCH ──
                    ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                        GroupTitle { text: "Search" }
                        Card {
                            SRow { label: "City"
                                ThemedCombo { id: cityCombo; objectName: "cityCombo"; editable: true; plainText: true
                                    implicitWidth: 200; model: win.euCities } }
                            Sep {}
                            SRow { label: "Job source"
                                ThemedCombo { id: srcCombo; implicitWidth: 210; textRole: "text"; valueRole: "value"
                                    model: [
                                        { text: "Czech boards, LinkedIn & careers", value: "czech" },
                                        { text: "LinkedIn only", value: "linkedin" },
                                        { text: "Company career sites only", value: "careers" },
                                        { text: "All sources (+ remote)", value: "all" } ] } }
                            Sep {}
                            // search roles: autocomplete field + add, chips below
                            SRow { label: "Search roles"; hint: "in English"
                                RowLayout { spacing: 6
                                    AutoField { id: roleField; objectName: "roleField"; implicitWidth: 180
                                        placeholder: "e.g. junior data scientist"; suggestions: win.roleSuggestions
                                        onEdited: optDialog.roleErr = ""
                                        onAdd: function (v) { if (optDialog.addRole(v)) roleField.text = ""; } }
                                    SmallButton { text: "+ Add"; primaryStyle: true
                                        onClicked: { if (optDialog.addRole(roleField.text)) roleField.text = ""; } } } }
                            Text { visible: optDialog.roleErr !== ""; Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.topMargin: 2
                                wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11; font.bold: true; text: optDialog.roleErr }
                            // chips
                            Flow {
                                Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.bottomMargin: 12
                                spacing: 6; visible: rolesModel.count > 0
                                Repeater { model: rolesModel
                                    Rectangle {
                                        radius: 999; color: theme.inset; border.color: theme.line; border.width: 1
                                        implicitHeight: 24; implicitWidth: chipRow.width + 16
                                        Row { id: chipRow; anchors.centerIn: parent; spacing: 5
                                            Text { text: model.text; color: theme.ink; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                                            Text { text: "✕"; color: theme.faint; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter
                                                MouseArea { anchors.fill: parent; anchors.margins: -4; cursorShape: Qt.PointingHandCursor
                                                    onClicked: rolesModel.remove(index) } } }
                                    } }
                            }
                            Sep {}
                            TagEditor { id: skipTags; objectName: "skipTags"; chipTone: theme.crit
                                label: "Skip titles with"; hint: "these jobs are left out"
                                placeholder: "e.g. intern" }
                            Sep {}
                            TagEditor { id: keepTags; objectName: "keepTags"; chipTone: theme.good
                                label: "…but keep titles with"; hint: "exceptions: these words beat a skip word"
                                placeholder: "e.g. graduate program" }
                            Sep {}
                            TagEditor { id: levelTags; objectName: "levelTags"; chipTone: theme.warn
                                label: "Skip levels above yours"; hint: "title words · empty the list if you are senior"
                                placeholder: "e.g. senior" }
                            Sep {}
                            SRow { label: "Skip jobs asking for"; hint: "years of experience or more · 0 = never"
                                ThemedSpin { id: yearsSpin; objectName: "yearsSpin"; from: 0; to: 30; value: 4 } }
                            Sep {}
                            SRow { label: "Include remote jobs"
                                ThemedSwitch { id: remoteSw; objectName: "remoteSw" } }
                            Sep {}
                            SRow { label: "Full-time only"; hint: "hide part-time roles"
                                ThemedSwitch { id: fullSw; objectName: "fullSw" } }
                            Sep {}
                            SRow { label: "English only"; hint: "hide Czech-language ads"
                                ThemedSwitch { id: engSw; objectName: "engSw" } }
                            Sep {}
                            SRow { label: "Max job age"; hint: "in days · 0 = any date"
                                ThemedSpin { id: ageSpin; from: 0; to: 90; value: 10 } }
                            Sep {}
                            SRow { label: "Results per query"
                                ThemedSpin { id: pqSpin; from: 1; to: 100; value: 15 } }
                        }
                    }

                    // ── CAREER SITES ──
                    ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                        GroupTitle { text: "Company career sites" }
                        Card {
                            // header
                            Item { Layout.fillWidth: true; implicitHeight: 42
                                ColumnLayout { anchors.left: parent.left; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 1
                                    Text { text: "Pull roles straight from companies' career sites"; color: theme.ink; font.pixelSize: 13 }
                                    Text { text: "token = the slug in the career URL (e.g. boards.greenhouse.io/gitlab → gitlab)"; color: theme.faint; font.pixelSize: 11 } } }
                            Sep {}
                            // existing companies
                            Repeater { model: companiesModel
                                ColumnLayout { Layout.fillWidth: true; spacing: 0
                                    Item { Layout.fillWidth: true; implicitHeight: 38
                                        Row { anchors.left: parent.left; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                                            Text { text: model.name; color: theme.ink; font.pixelSize: 13; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
                                            Rectangle { radius: 999; color: theme.inset; implicitHeight: 18; implicitWidth: atp.width + 14; anchors.verticalCenter: parent.verticalCenter
                                                Text { id: atp; anchors.centerIn: parent; text: model.ats + " / " + model.token; color: theme.soft; font.pixelSize: 10 } } }
                                        Text { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                                            text: "✕"; color: theme.faint; font.pixelSize: 13
                                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                                            MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor; onClicked: companiesModel.remove(index) } } }
                                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; Layout.leftMargin: 14; color: theme.line; opacity: 0.6 }
                                }
                            }
                            Text { visible: companiesModel.count === 0; Layout.fillWidth: true; Layout.margins: 12
                                text: "No companies yet. Add one below."; color: theme.faint; font.pixelSize: 12 }
                            // add form
                            RowLayout { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; Layout.topMargin: 12; spacing: 6
                                TextField { id: coName; Layout.fillWidth: true; placeholderText: "Company name"
                                    color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                    background: Rectangle { radius: 7; color: theme.surface; border.color: parent.activeFocus ? theme.accent : theme.line; border.width: 1 } }
                                ThemedCombo { id: coAts; implicitWidth: 128; plainText: true
                                    model: ["greenhouse", "lever", "smartrecruiters", "recruitee"] }
                                TextField { id: coToken; Layout.preferredWidth: 110; placeholderText: "token"
                                    color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                    background: Rectangle { radius: 7; color: theme.surface; border.width: 1
                                        border.color: coToken.activeFocus ? theme.accent : (optDialog.coErr ? theme.crit : theme.line) }
                                    onTextChanged: optDialog.coErr = ""
                                    onAccepted: { if (optDialog.addCompany(coName.text, coAts.currentText, coToken.text)) { coName.text = ""; coToken.text = ""; } } }
                                SmallButton { text: "+ Add"; primaryStyle: true
                                    onClicked: { if (optDialog.addCompany(coName.text, coAts.currentText, coToken.text)) { coName.text = ""; coToken.text = ""; } } }
                            }
                            Text { visible: optDialog.coErr !== ""; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; Layout.bottomMargin: 10
                                wrapMode: Text.WordWrap; color: theme.crit; font.pixelSize: 11; font.bold: true; text: optDialog.coErr }
                            Item { visible: optDialog.coErr === ""; Layout.preferredHeight: 10 }
                        }
                    }

                    // ── MATCHING ──
                    ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                        GroupTitle { text: "Matching" }
                        Card {
                            SRow { label: "Write letters above"; hint: "match score 0–100"
                                ThemedSpin { id: thrSpin; from: 0; to: 100; value: 50 } }
                            Sep {}
                            SRow { label: "Hide leads below"; hint: "0 = show all leads"
                                ThemedSpin { id: minSpin; from: 0; to: 100; value: 0 } }
                        }
                    }

                    // ── FOLLOW-UP ──
                    ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                        GroupTitle { text: "Follow-up" }
                        Card {
                            SRow { label: "Remind me after"; hint: "days without a reply · 0 = never"
                                ThemedSpin { id: fuSpin; objectName: "fuSpin"; from: 0; to: 90; value: 10 } }
                        }
                    }

                    // ── ABOUT YOU (the only personal facts the app states besides your CV) ──
                    ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                        GroupTitle { text: "About you" }
                        Card {
                            SRow { label: "Right to work"; hint: "as letters should say it · empty = not mentioned"
                                TextField { id: rightField; objectName: "rightField"; implicitWidth: 250; implicitHeight: 30
                                    placeholderText: "e.g. full right to work in the Czech Republic"; placeholderTextColor: theme.faint
                                    color: theme.ink; font.pixelSize: 12; selectByMouse: true; maximumLength: 90
                                    background: Rectangle { radius: 8; color: theme.surface; border.width: 1
                                        border.color: rightField.activeFocus ? theme.accent : theme.line } } }
                            Sep {}
                            SRow { label: "You can start"; hint: "empty = not mentioned"
                                TextField { id: startField; objectName: "startField"; implicitWidth: 250; implicitHeight: 30
                                    placeholderText: "e.g. within two weeks"; placeholderTextColor: theme.faint
                                    color: theme.ink; font.pixelSize: 12; selectByMouse: true; maximumLength: 60
                                    background: Rectangle { radius: 8; color: theme.surface; border.width: 1
                                        border.color: startField.activeFocus ? theme.accent : theme.line } } }
                        }
                    }

                    // ── NOTIFICATIONS AND HOUSEKEEPING ──
                    ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                        GroupTitle { text: "Notifications and storage" }
                        Card {
                            SRow { label: "Notifications"; hint: "run finished, paused on the limit, interview invitation"
                                ThemedSwitch { id: notifySw; objectName: "notifySw" } }
                            Sep {}
                            SRow { label: "Keep backups"; hint: "newest ones kept, older deleted · 0 = keep all"
                                ThemedSpin { id: keepSpin; objectName: "keepSpin"; from: 0; to: 200; value: 10 } }
                        }
                    }

                    // ── EMAIL SCAN ──
                    ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                        GroupTitle { text: "Email scan" }
                        Card {
                            SRow { label: "Scan emails from the last"; hint: "days · emails already read are skipped"
                                ThemedSpin { id: scanSpin; objectName: "scanSpin"; from: 1; to: 365; value: 30 } }
                            Sep {}
                            SRow { label: "Also archived mail and spam"; hint: "not only the Inbox · never Sent or Drafts"
                                ThemedSwitch { id: foldersSw; objectName: "foldersSw" } }
                        }
                    }

                    // ── MODEL ──
                    ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                        GroupTitle { text: "Model" }
                        Card {
                            SRow { label: "Claude model"; hint: "uses your subscription"
                                ThemedCombo { id: modelCombo; implicitWidth: 140; plainText: true; model: ["sonnet", "opus", "haiku"] } }
                        }
                    }
                    Item { Layout.preferredHeight: 4 }
                }
                }
            }

            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            RowLayout { Layout.fillWidth: true; Layout.margins: 14
                Text { Layout.fillWidth: true; visible: optDialog.optErr !== ""; wrapMode: Text.WordWrap
                    color: theme.crit; font.pixelSize: 12; font.bold: true; text: optDialog.optErr }
                Item { Layout.fillWidth: optDialog.optErr === "" }
                SmallButton { text: "Cancel"; onClicked: optDialog.close() }
                PillButton { primaryStyle: true; text: "Save"
                    onClicked: {
                        optSink.forceActiveFocus();        // finish any field that is still being edited
                        optDialog.optErr = "";
                        if ((cityCombo.editText || "").trim() === "") {
                            optDialog.optErr = "Enter a city (e.g. Prague) before saving."; return;
                        }
                        if (win.hasNonLatin(cityCombo.editText)) {
                            optDialog.optErr = "City must be in English (Latin letters), e.g. Prague."; return;
                        }
                        var qs = [];
                        for (var i = 0; i < rolesModel.count; i++) qs.push("" + rolesModel.get(i).text);
                        if (win.hasNonLatin(rightField.text) || win.hasNonLatin(startField.text)) {
                            optDialog.optErr = "Write “About you” in English (Latin letters): it goes into English letters."; return;
                        }
                        var clash = optDialog.roleClash(qs, skipTags.all(), keepTags.all());
                        if (clash !== "") { optDialog.optErr = clash; return; }
                        var out = { where: cityCombo.editText, source: srcCombo.currentValue,
                            include_remote: remoteSw.checked, all_languages: !engSw.checked,
                            full_time_only: fullSw.checked,
                            skip_words: skipTags.all(), keep_words: keepTags.all(),
                            level_words: levelTags.all(), max_years: yearsSpin.value,
                            max_age_days: ageSpin.value, per_query: pqSpin.value,
                            threshold: thrSpin.value, min_lead_score: minSpin.value,
                            followup_days: fuSpin.value, scan_days: scanSpin.value,
                            about_right_to_work: rightField.text.trim(), about_start: startField.text.trim(),
                            notifications: notifySw.checked, keep_backups: keepSpin.value,
                            scan_all_folders: foldersSw.checked,
                            model: modelCombo.currentText, queries: qs };
                        bridge.saveOptions(out);
                        // build PLAIN objects (ListModel.get() returns a QObject that
                        // can't cross the bridge directly)
                        var cs = [];
                        for (var k = 0; k < companiesModel.count; k++) {
                            var c = companiesModel.get(k);
                            cs.push({ name: "" + c.name, ats: "" + c.ats, token: "" + c.token });
                        }
                        bridge.saveCompanies(cs);
                        win.optsData = bridge.options();
                        win.countsData = bridge.counts();      // the follow-up count depends on the new setting
                        ticker.text = "✓ Options saved.";
                        optDialog.close();
                    } } }
        }
    }

    // ───────────────────────── weekly schedule ─────────────────────────
    Dialog {
        id: schedDialog; objectName: "schedDialog"
        modal: true; anchors.centerIn: parent; closePolicy: Popup.CloseOnEscape
        enter: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.92; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 0.7 } } }
        exit: Transition { ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 170; easing.type: Easing.InCubic }
            NumberAnimation { property: "scale"; from: 1; to: 0.96; duration: 170; easing.type: Easing.InCubic } } }
        Overlay.modal: Rectangle { color: win.dimColor; Behavior on opacity { NumberAnimation { duration: 200 } } }
        width: Math.min(440, win.width - 80); padding: 0
        property bool en: true
        property int wd: 1
        property int hh: 9
        property int mm: 0
        property string schedErr: ""
        // combo index 0..6 -> Mon..Sun ; launchd weekday Sun = 0
        readonly property var wdVals: [1, 2, 3, 4, 5, 6, 0]
        // live time-range error (empty when both fields are valid)
        readonly property string timeErr: !hourField.valid ? "Hour must be between 0 and 23."
                                        : (!minField.valid ? "Minute must be between 0 and 59." : "")
        function load() {
            en = win.schedData.enabled === true;
            hh = win.schedData.hour !== undefined ? win.schedData.hour : 9;
            mm = win.schedData.minute !== undefined ? win.schedData.minute : 0;
            wd = win.schedData.weekday !== undefined ? win.schedData.weekday : 1;
            dayCombo.currentIndex = Math.max(0, wdVals.indexOf(wd));
            hourField.value = hh; minField.value = mm;
            schedErr = "";
        }
        onAboutToShow: load()      // fill + reset BEFORE the window is visible (not after the animation)
        background: Rectangle { radius: 16; color: theme.winbg; border.color: theme.line; border.width: 1
            MouseArea { anchors.fill: parent; onPressed: function (m) { schedSink.forceActiveFocus(); m.accepted = false; } } }
        Item { id: schedSink }
        contentItem: ColumnLayout {
            spacing: 0
            RowLayout { Layout.fillWidth: true; Layout.margins: 16
                Text { text: "🗓️  Weekly run"; color: theme.ink; font.pixelSize: 16; font.bold: true; Layout.fillWidth: true }
                Rectangle { implicitWidth: 28; implicitHeight: 28; radius: 8; color: theme.surface2; border.color: theme.line; border.width: 1
                    Text { anchors.centerIn: parent; text: "✕"; color: theme.soft; font.pixelSize: 13 }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: schedDialog.close() } } }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            ColumnLayout {
                Layout.fillWidth: true; Layout.margins: 18; spacing: 14
                Text { text: "Automatically search jobs + scan email on a schedule (macOS)."
                    color: theme.soft; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                RowLayout { Layout.fillWidth: true
                    Text { text: "Enabled"; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true }
                    ThemedSwitch { checked: schedDialog.en; onToggled: schedDialog.en = checked } }
                RowLayout { Layout.fillWidth: true; enabled: schedDialog.en; opacity: schedDialog.en ? 1 : 0.4
                    Text { text: "Day"; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true }
                    ThemedCombo { id: dayCombo; objectName: "dayCombo"; Layout.preferredWidth: 150; plainText: true
                        model: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                        onActivated: schedDialog.wd = schedDialog.wdVals[currentIndex] } }
                RowLayout { Layout.fillWidth: true; enabled: schedDialog.en; opacity: schedDialog.en ? 1 : 0.4
                    Text { text: "Time"; color: theme.ink; font.pixelSize: 13; Layout.fillWidth: true }
                    TimeField { id: hourField; objectName: "hourField"; maxv: 23; onEdited: schedDialog.schedErr = "" }
                    Text { text: ":"; color: theme.ink; font.pixelSize: 15; font.bold: true }
                    TimeField { id: minField; objectName: "minField"; maxv: 59; onEdited: schedDialog.schedErr = "" } }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }
            RowLayout { Layout.fillWidth: true; Layout.margins: 14
                Text { Layout.fillWidth: true; visible: (schedDialog.timeErr || schedDialog.schedErr) !== ""; wrapMode: Text.WordWrap
                    color: theme.crit; font.pixelSize: 12; font.bold: true; text: schedDialog.timeErr || schedDialog.schedErr }
                Item { Layout.fillWidth: (schedDialog.timeErr || schedDialog.schedErr) === "" }
                SmallButton { text: "Cancel"; onClicked: schedDialog.close() }
                PillButton { objectName: "schedSave"; primaryStyle: true; text: "Save"
                    onClicked: {
                        schedDialog.schedErr = "";
                        if (!hourField.valid || !minField.valid) return;   // red error already shown; don't save
                        var r = bridge.setWeeklySchedule(schedDialog.en, schedDialog.wd, hourField.value, minField.value);
                        win.schedData = bridge.weeklySchedule();
                        if (r && r.ok) {
                            ticker.text = schedDialog.en ? ("✓ Weekly run set for " + (win.schedData.label || "")) : "✓ Weekly run turned off.";
                            schedDialog.close();
                        } else {
                            schedDialog.schedErr = (r && r.msg) ? r.msg : "Couldn't update the schedule.";
                        }
                    } } }
        }
    }
}
