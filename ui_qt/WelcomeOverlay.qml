// WelcomeOverlay: one window of the JobHelper app, created once in Main.qml as `welcome`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Item {
    id: welcome; objectName: "welcome"
    anchors.fill: parent; z: 50
    property bool shown: true
    property string phase: "splash"      // splash | card
    property bool first: true            // launch (Start) vs reopened (Done)
    property bool introDone: false
    property bool waitingLogin: false
    property bool editEmail: false
    property string hostDraft: ""         // the IMAP server, typed for a provider the app does not know
    // the server is asked for only when the address does not tell it (its own flag: a field's `visible` also depends on what is around it)
    readonly property bool needsServer: win.isEmail(emailDraft) && bridge.mailServer(emailDraft, "").known !== true
    property bool testBusy: false         // the saved mailboxes are being tried
    property int testLeft: 0
    property string testNote: ""
    property bool testBad: false
    function testMail() {
        if (testBusy) return;
        testNote = ""; testBad = false; testBusy = true; testLeft = connData.email2 === true ? 2 : 1;
        bridge.testMailbox(1);
        if (connData.email2 === true) bridge.testMailbox(2);
    }
    property var changes: []              // what changed in each watched file, while the person looks at it
    property string keyText: ""           // the recovery key while it is shown; cleared when hidden, on a timer, and when the card closes
    property string keyErr: ""
    property bool keyCopied: false
    property string restoreErr: ""
    function toggleKey() {
        keyErr = ""; keyCopied = false;
        if (keyText !== "") { keyText = ""; return; }
        var r = bridge.recoveryKey();
        if (r && r.ok) keyText = r.key; else keyErr = (r && r.msg) || "The recovery key could not be shown.";
    }
    function restoreKey() {
        var r = bridge.restoreKey(restoreField.text);
        restoreField.text = "";                                     // never left on screen
        if (r && r.ok) { restoreErr = ""; bridge.checkConnections(); win.reloadAll(); }
        else restoreErr = (r && r.msg) || "The key could not be used.";
    }
    onShownChanged: if (!shown) { testNote = ""; testBad = false; changes = []; keyText = ""; keyErr = ""; keyCopied = false; restoreErr = ""; }
    Timer { interval: 60000; running: welcome.keyText !== ""; onTriggered: { welcome.keyText = ""; welcome.keyCopied = false; } }
    property bool emailBusy: false        // the mailbox is being tried with the address and password just entered
    property string emailNote: ""         // saved, but something to know (the server could not be reached)
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
        if (editBox === 2 && emailDraft.trim().toLowerCase() === (connData.email_addr || "").toLowerCase()) {
            emailErr = "That is already your main job email. Enter a different address."; shake.restart(); return; }
        var server = bridge.mailServer(emailDraft, needsServer ? hostDraft : "");
        if (server.problem) { emailErr = server.problem; shake.restart(); return; }
        if (!server.host) { emailErr = "Enter this provider's IMAP server, for example imap." + emailDraft.trim().split("@").pop() + "."; shake.restart(); return; }
        if (pwDraft !== "" && server.gmail === true && !win.isAppPassword(pwDraft)) {
            emailErr = "A Google App Password is 16 letters (no digits). Check for typos."; shake.restart(); return; }
        if (pwDraft !== "" && win.hasNonLatin(pwDraft)) {
            emailErr = "A mail server takes only English letters, digits and symbols in a password here."; shake.restart(); return; }
        var known = editBox === 2 ? connData.email2 === true : connData.email === true;
        if (!known && pwDraft === "") { emailErr = "Enter the password for this mailbox."; shake.restart(); return; }
        if (emailBusy) return;
        emailBusy = true; emailNote = "";
        bridge.saveEmailChecked(editBox, emailDraft, pwDraft, needsServer ? hostDraft : "");       // tries the mailbox first; answers through onEmailSaved
    }
    onPhaseChanged: if (phase === "card") { emailDraft = connData.email_addr || ""; keySink.forceActiveFocus(); }
    Connections { target: win; function onConnCheckedChanged() { welcome.advance(); } }
    Connections { target: bridge
        function onConnectionsReady(info) { if (info.claude === true) welcome.waitingLogin = false; }
        function onEmailTested(r) {
            welcome.testLeft -= 1; welcome.testBad = welcome.testBad || !(r && r.ok);
            welcome.testNote = (welcome.testNote !== "" ? welcome.testNote + " " : "") + ((r && r.msg) || "");
            if (welcome.testLeft <= 0) welcome.testBusy = false;
        }
        function onEmailSaved(r) {
            welcome.emailBusy = false; welcome.pwDraft = "";
            if (r && r.ok) { welcome.editEmail = false; welcome.emailNote = r.note || ""; bridge.checkConnections(); }
            else { welcome.emailErr = (r && r.msg) ? r.msg : "Couldn't save the email."; shake.restart(); }
        } }
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
            Robot { id: logoBot; x: 60; theme: win.appTheme; ag: win.appTheme.accent; kind: "search"; interactive: false
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
                                                 : "Optional. Reads replies from your mailbox, never sends or deletes."
                    SmallButton { objectName: "mailTest"; visible: !welcome.editEmail && connData.email === true; enabled: !welcome.testBusy
                        text: welcome.testBusy ? "Testing…" : "Test"; onClicked: welcome.testMail() }
                    SmallButton { visible: !welcome.editEmail; text: connData.email === true ? "Change" : "Connect"
                        onClicked: { welcome.editBox = 1; welcome.emailDraft = connData.email_addr || ""; welcome.hostDraft = connData.email_host || "";
                                     welcome.pwDraft = ""; welcome.emailErr = "";
                                     welcome.editEmail = true; wEmail.forceActiveFocus(); } }
                }
                Text { objectName: "testNote"; visible: welcome.testNote !== "" && !welcome.editEmail
                    Layout.fillWidth: true; Layout.leftMargin: 38; wrapMode: Text.WordWrap; font.pixelSize: 11; font.bold: welcome.testBad
                    color: welcome.testBad ? theme.crit : theme.good; text: welcome.testNote }
                Text { objectName: "emailNote"; visible: welcome.emailNote !== "" && !welcome.editEmail
                    Layout.fillWidth: true; Layout.leftMargin: 38; wrapMode: Text.WordWrap
                    color: theme.warn; font.pixelSize: 11; font.bold: true; text: welcome.emailNote }
                // optional second mailbox (replies that go to another address)
                RowLayout { objectName: "secondMailRow"
                    visible: connData.email === true && !welcome.editEmail
                    Layout.fillWidth: true; Layout.leftMargin: 38; Layout.topMargin: 4; spacing: 6
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11
                        color: connData.email2 === true ? theme.soft : theme.faint
                        text: connData.email2 === true ? ("Second mailbox: " + (connData.email2_addr || "") + " · read-only")
                                                       : "Second mailbox (optional)" }
                    SmallButton { objectName: "secondMailAdd"; text: connData.email2 === true ? "Change" : "Add"
                        onClicked: { welcome.editBox = 2; welcome.emailDraft = connData.email2_addr || ""; welcome.hostDraft = connData.email2_host || "";
                                     welcome.pwDraft = "";
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
                                             ? "Password (leave blank to keep)" : "Password for this mailbox"
                            text: welcome.pwDraft; color: theme.ink; font.pixelSize: 12; selectByMouse: true
                            placeholderTextColor: theme.faint
                            background: Rectangle { radius: 8; color: theme.inset; border.width: 1
                                border.color: wPw.activeFocus ? theme.accent
                                    : (welcome.emailErr !== "" && win.isEmail(welcome.emailDraft) ? theme.crit : theme.line) }
                            onTextEdited: { welcome.pwDraft = text; welcome.emailErr = ""; }
                            onAccepted: welcome.saveEmail() }
                        // the server: asked for only when the address does not tell it
                        TextField { id: serverRow; objectName: "mailServerField"; Layout.fillWidth: true; Layout.leftMargin: 38
                            visible: welcome.needsServer
                            placeholderText: "IMAP server, e.g. imap." + (welcome.emailDraft.trim().split("@").pop() || "example.com")
                            text: welcome.hostDraft; color: theme.ink; font.pixelSize: 12; selectByMouse: true; maximumLength: 253
                            placeholderTextColor: theme.faint
                            background: Rectangle { radius: 8; color: theme.inset; border.width: 1
                                border.color: serverRow.activeFocus ? theme.accent : theme.line }
                            onTextEdited: { welcome.hostDraft = text; welcome.emailErr = ""; }
                            onAccepted: wPw.forceActiveFocus() }
                        Text { visible: welcome.emailErr !== ""; Layout.fillWidth: true; Layout.leftMargin: 38; wrapMode: Text.WordWrap
                            color: theme.crit; font.pixelSize: 11; font.bold: true; text: welcome.emailErr }
                        RowLayout { Layout.fillWidth: true; Layout.leftMargin: 38; spacing: 6
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                objectName: "mailHint"
                                readonly property var server: bridge.mailServer(welcome.emailDraft, welcome.needsServer ? welcome.hostDraft : "")
                                text: !win.isEmail(welcome.emailDraft) ? "Most providers want a separate app password for a program, not the one you sign in with."
                                      : server.problem ? server.problem : server.hint }
                            SmallButton { text: "Cancel"; enabled: !welcome.emailBusy
                                onClicked: { welcome.editEmail = false; welcome.emailErr = ""; keySink.forceActiveFocus(); } }
                            SmallButton { objectName: "emailSave"; primaryStyle: true; enabled: !welcome.emailBusy
                                text: welcome.emailBusy ? "Checking…" : "Save"; onClicked: welcome.saveEmail() } }
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
                            ? "Your data is encrypted but its key is not in the Keychain. Paste your recovery key below."
                       : welcome.changedFiles.length > 0
                            ? ("Changed outside the app: " + welcome.changedFiles.join(", ") + ". Check them, then approve.")
                       : connData.vault === "ok" ? "Encrypted on disk · key and mailbox password in your Keychain"
                       : "Off: no Keychain on this system, files are stored plain."
                    SmallButton { objectName: "seeChanges"; visible: welcome.changedFiles.length > 0 && connData.vault === "ok"
                        text: welcome.changes.length > 0 ? "Hide changes" : "See what changed"
                        onClicked: welcome.changes = welcome.changes.length > 0 ? [] : bridge.whatChanged() }
                    SmallButton { visible: welcome.changedFiles.length > 0 && connData.vault === "ok"; primaryStyle: true
                        text: "Approve"; onClicked: { bridge.approveChanges(); welcome.changes = []; bridge.checkConnections(); } }
                    SmallButton { objectName: "keyShow"; visible: connData.vault === "ok" && welcome.changedFiles.length === 0
                        text: welcome.keyText !== "" ? "Hide key" : "Recovery key"; onClicked: welcome.toggleKey() }
                }
                // what is different in each changed file, so that approving is not done blind
                ColumnLayout { objectName: "changesPanel"; visible: welcome.changes.length > 0 && welcome.changedFiles.length > 0
                    Layout.fillWidth: true; Layout.leftMargin: 38; spacing: 8
                    Repeater { model: welcome.changes
                        ColumnLayout { Layout.fillWidth: true; spacing: 2
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.ink; font.pixelSize: 12; font.bold: true
                                text: modelData.title + (modelData.file ? " · " + modelData.file : "") }
                            Text { visible: modelData.known !== true; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.warn; font.pixelSize: 11
                                text: "No earlier copy of this file was kept, so the difference cannot be shown. Open the file and read it before you approve. From the next approval on, the app keeps a copy." }
                            Text { visible: modelData.known === true && modelData.added.length === 0 && modelData.removed.length === 0
                                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.soft; font.pixelSize: 11
                                text: "The words are the same. Only the layout, the spacing or the file itself changed." }
                            Repeater { model: modelData.known === true ? modelData.removed : []
                                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.crit; font.pixelSize: 11; text: "− " + modelData } }
                            Repeater { model: modelData.known === true ? modelData.added : []
                                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; color: theme.good; font.pixelSize: 11; text: "+ " + modelData } }
                            Text { visible: (modelData.more || 0) > 0; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                text: "… and " + modelData.more + " more changed lines. Open the file to read all of it." } } }
                }
                // the recovery key, shown only when asked for, and put away again by itself
                ColumnLayout { objectName: "keyPanel"; visible: welcome.keyText !== "" || welcome.keyErr !== ""
                    Layout.fillWidth: true; Layout.leftMargin: 38; spacing: 6
                    Text { visible: welcome.keyText !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.warn; font.pixelSize: 11; font.bold: true
                        text: "Keep this somewhere safe and outside this Mac (a password manager). Anyone who has it can read your data. "
                              + "You need it on a new Mac or after the Keychain is reset." }
                    RowLayout { visible: welcome.keyText !== ""; Layout.fillWidth: true; spacing: 6
                        TextField { objectName: "keyField"; Layout.fillWidth: true; readOnly: true; selectByMouse: true
                            text: welcome.keyText; color: theme.ink; font.pixelSize: 11; font.family: "Menlo"
                            background: Rectangle { radius: 8; color: theme.inset; border.width: 1; border.color: theme.line } }
                        SmallButton { objectName: "keyCopy"; text: welcome.keyCopied ? "Copied" : "Copy"
                            onClicked: { welcome.keyCopied = bridge.copyText(welcome.keyText); } } }
                    Text { objectName: "keyErr"; visible: welcome.keyErr !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: theme.crit; font.pixelSize: 11; font.bold: true; text: welcome.keyErr }
                }
                // a new Mac, or the Keychain was reset: the saved key opens the data again
                ColumnLayout { objectName: "restorePanel"; visible: connData.vault === "locked"
                    Layout.fillWidth: true; Layout.leftMargin: 38; spacing: 6
                    RowLayout { Layout.fillWidth: true; spacing: 6
                        TextField { id: restoreField; objectName: "restoreField"; Layout.fillWidth: true; echoMode: TextInput.Password
                            placeholderText: "Your recovery key"; placeholderTextColor: theme.faint; maximumLength: 200
                            color: theme.ink; font.pixelSize: 12; selectByMouse: true
                            background: Rectangle { radius: 8; color: theme.inset; border.width: 1
                                border.color: restoreField.activeFocus ? theme.accent : welcome.restoreErr !== "" ? theme.crit : theme.line }
                            onTextEdited: welcome.restoreErr = ""
                            onAccepted: welcome.restoreKey() }
                        SmallButton { objectName: "restoreGo"; primaryStyle: true; text: "Open my data"; onClicked: welcome.restoreKey() } }
                    Text { objectName: "restoreErr"; visible: welcome.restoreErr !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: theme.crit; font.pixelSize: 11; font.bold: true; text: welcome.restoreErr }
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
