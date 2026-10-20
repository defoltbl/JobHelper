// OptionsDialog: one window of the JobHelper app, created once in Main.qml as `optDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Dialog {
    id: optDialog; objectName: "optDialog"
    modal: true; anchors.centerIn: parent
    closePolicy: Popup.NoAutoClose        // Esc goes through tryClose, so changes are never thrown away unasked
    Shortcut { sequence: "Escape"; enabled: win.onTop(optDialog); onActivated: optDialog.tryClose() }
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
    property string pendingRole: ""       // a role the app did not know, waiting for a second press on Add
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
        for (var i = 0; i < rolesModel.count; i++)
            if (rolesModel.get(i).text.toLowerCase() === t.toLowerCase()) { roleErr = "That role is already in the list."; return false; }
        // a role the app does not know is not wrong (the list of words it knows grew up with software jobs):
        // it is asked about once, so a typo is caught, and added on the second press
        if (!win.looksLikeRole(t) && !bridge.knownRole(t) && pendingRole.toLowerCase() !== t.toLowerCase()) {
            pendingRole = t;
            roleErr = "“" + t + "” is not a role the app knows. Check the spelling, then press Add again to search for it anyway.";
            return false;
        }
        pendingRole = "";
        rolesModel.append({ text: t });
        return true;
    }
    property string coErr: ""
    property string optErr: ""
    readonly property var sizes: win.limits.choices.text_sizes      // per cent: the whole window larger
    property int sizeAtOpen: 100
    function addCompany(name, ats, token) {
        var tok = (token || "").trim();
        coErr = "";
        if (win.hasNonLatin(name)) { coErr = "Write the company name in Latin letters."; return false; }
        if ((name || "").trim().length > win.limits.company_name) { coErr = "The company name is " + (name || "").trim().length + " characters long; the most is " + win.limits.company_name + "."; return false; }
        if (!tok) { coErr = "Enter the company's token (the slug in its career-site URL)."; return false; }
        if (!win.isSlug(tok)) { coErr = "Token looks wrong – use the URL slug only (letters, digits, - or _), no spaces or https://."; return false; }
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
        return m[(c || "").toLowerCase()] || c || "";
    }
    property string loaded: ""            // everything in the window as it was when it opened, to tell if it changed
    property bool confirmClose: false
    function collect() {                  // what Save would store, as plain values
        var qs = [];
        for (var i = 0; i < rolesModel.count; i++) qs.push("" + rolesModel.get(i).text);
        var cs = [];                      // plain objects: a ListModel row cannot cross the bridge
        for (var k = 0; k < companiesModel.count; k++) {
            var c = companiesModel.get(k);
            cs.push({ name: "" + c.name, ats: "" + c.ats, token: "" + c.token });
        }
        return { options: { where: cityCombo.editText, country: countryField.text.trim(), sources: pickedSources.slice(),
                            remote_where: remoteWhere, remote_countries: pickedRemote.slice(), all_languages: !engSw.checked,
                            full_time_only: fullSw.checked,
                            skip_words: skipTags.all(), keep_words: keepTags.all(),
                            level_words: levelTags.all(), max_years: yearsSpin.value,
                            wanted_roles: wantedTags.all(), unwanted_roles: unwantedTags.all(), my_fields: pickedFields.slice(),
                            max_age_days: ageSpin.value, per_query: pqSpin.value,
                            threshold: thrSpin.value, min_lead_score: minSpin.value,
                            followup_days: fuSpin.value, scan_days: scanSpin.value,
                            notifications: notifySw.checked, keep_backups: keepSpin.value,
                            text_size: optDialog.sizes[Math.max(0, sizeCombo.currentIndex)],
                            scan_all_folders: foldersSw.checked,
                            model: modelCombo.currentText, queries: qs },
                 companies: cs };
    }
    function changed() { return loaded !== "" && JSON.stringify(collect()) !== loaded; }
    // your profession for the free first look: read from the roles, or picked by hand here
    property var pickedFields: []
    // the kinds of job source ticked: keys of bridge.sourceKinds(), in its order
    readonly property var sourceKinds: bridge ? bridge.sourceKinds() : []
    property var pickedSources: []
    function toggleSource(key) {
        var on = pickedSources.indexOf(key) >= 0;
        pickedSources = sourceKinds.map(function (k) { return k.key; })
                                   .filter(function (k) { return k === key ? !on : pickedSources.indexOf(k) >= 0; });
    }
    // which remote jobs a search keeps (places.RemoteReach): open to your country and the ones added, or anywhere
    property string remoteWhere: "country"
    property var pickedRemote: []         // country keys, as bridge.countries() gives them
    property string notifyPermission: ""  // whether macOS shows the notifications (bridge.notificationPermission), read on opening
    property string notifyNote: ""        // what the Test button found
    property bool notifyBad: false
    // your country as the window shows it: the one typed, or the city's
    readonly property string homeName: bridge.countryOf(countryField.text.trim() !== "" ? countryField.text : cityCombo.editText)
    function dropRemote(key) { pickedRemote = pickedRemote.filter(function (k) { return k !== key; }); }
    function countryName(key) {
        var all = remoteDialog.all;
        for (var i = 0; i < all.length; i++) if (all[i].key === key) return all[i].name;
        return key;
    }
    function toggleField(name, all) {
        var on = pickedFields.indexOf(name) >= 0;
        pickedFields = (all || []).filter(function (f) { return f === name ? !on : pickedFields.indexOf(f) >= 0; });
    }
    // documents moved to the backup: how many there are, and removing the old ones (asked first, with the count)
    property var shelf: ({})
    property bool confirmTidy: false
    property string storageBusy: ""       // which backup action is running: "backup", "check", "export" or ""
    property string storageNote: ""
    property bool storageBad: false
    function storage(action, folder) {
        storageNote = ""; storageBad = false;
        if (win.appRunning) { storageBad = true; storageNote = "A search or scan is running. Do this when it has finished."; return; }
        if (storageBusy !== "") return;
        storageBusy = action;
        bridge.storage(action, folder);
    }
    Connections { target: bridge
        function onStorageDone(res) {
            optDialog.storageBusy = ""; optDialog.storageBad = !(res && res.ok);
            optDialog.storageNote = (res && res.msg) || (optDialog.storageBad ? "That did not work." : "Done.");
            if (res && res.ok) optDialog.readShelf();
        } }
    FolderDialog { id: exportDialog; title: "Choose an empty folder for the readable copy"
        onAccepted: optDialog.storage("export", "" + selectedFolder) }
    // what is wrong with a typed country ('' = nothing): its English name in letters, as postings write it
    function countryProblem(text) {
        var t = (text || "").trim();
        if (t === "") return "";
        if (win.hasNonLatin(t)) return "Write the country in English (Latin letters), e.g. Germany.";
        if (/[0-9]/.test(t)) return "A country's name has no digits. Write it in letters, e.g. Germany.";
        if (!/^[A-Za-z\u00C0-\u024F]+(?:[ '.\-]+[A-Za-z\u00C0-\u024F]+)*\.?$/.test(t)) return "Write only the country's name, e.g. Germany.";
        if (t.length >= 60) return "“Country” takes up to 60 characters.";
        return "";
    }
    property string backNote: ""          // what happened when "Scan now" was pressed
    property bool backBad: false
    function scanBack() {
        var r = win.startScanBack(backSpin.value);
        backBad = !(r && r.ok);
        backNote = backBad ? ((r && r.msg) || "The scan could not be started.")
                           : "Reading the last " + backSpin.value + " days. You can close Options; the result appears on the main screen.";
    }
    property string shelfNote: ""
    property bool shelfBad: false
    property bool shelfDone: false
    function megabytes(n) { return (n || 0) < 1048576 ? Math.max(1, Math.round((n || 0) / 1024)) + " KB" : ((n || 0) / 1048576).toFixed(1) + " MB"; }
    function readShelf() {
        if (!visible) return;
        var s = bridge.shelfStatus(shelfSpin.value);
        if (s && s.ok) { shelf = s; shelfBad = false; } else { shelf = ({}); shelfBad = true; shelfNote = (s && s.msg) || "The backup folder could not be read."; }
    }
    function shelfSummary() {
        if ((shelf.files || 0) === 0) return "No documents have been moved to the backup.";
        return shelf.files + (shelf.files === 1 ? " moved document is" : " moved documents are") + " in the backup (" + megabytes(shelf.bytes) + "). "
               + ((shelf.old || 0) === 0 ? "None is older than " + shelf.days + " days."
                  : shelf.old + (shelf.old === 1 ? " is" : " are") + " older than " + shelf.days + " days (" + megabytes(shelf.old_bytes) + ").");
    }
    function tidyShelf() {
        shelfDone = false;
        if (win.appRunning) { confirmTidy = false; shelfBad = true; shelfNote = "A search or scan is running. Remove old copies when it has finished."; return; }
        if (!confirmTidy) {
            readShelf();
            if (shelfBad || (shelf.old || 0) === 0) return;
            confirmTidy = true;
            shelfNote = "Move " + shelf.old + (shelf.old === 1 ? " document" : " documents") + " older than " + shelf.days
                        + " days (" + megabytes(shelf.old_bytes) + ") from the backup to the Trash? The app can then no longer put them back. "
                        + "Empty the Trash to free the space.";
            return;
        }
        confirmTidy = false;
        var r = bridge.tidyShelf(shelfSpin.value, shelf.old || 0);
        shelfBad = !(r && r.ok);
        if (r && r.ok) { shelfDone = true; shelfNote = "Moved " + r.removed + (r.removed === 1 ? " old copy" : " old copies") + " to the Trash (" + megabytes(r.bytes) + ")."; readShelf(); shelfBad = false; }
        else { shelfNote = (r && r.msg) || "The old copies could not be moved to the Trash."; var keep = shelfNote; readShelf(); shelfBad = true; shelfNote = keep;
               if (r && r.changed && (shelf.old || 0) > 0) confirmTidy = true; }
    }
    // Something typed into a box that has its own Add button, and not added: Save would leave it out without a word.
    function notAdded() {
        var boxes = [[roleField.text, "Search roles"], [skipTags.typed, skipTags.label], [keepTags.typed, keepTags.label],
                     [wantedTags.typed, wantedTags.label], [unwantedTags.typed, unwantedTags.label], [levelTags.typed, levelTags.label],
                     [coToken.text || coName.text, "Company career sites"]];
        for (var i = 0; i < boxes.length; i++) {
            var t = ("" + (boxes[i][0] || "")).trim();
            if (t !== "") return "“" + t.substring(0, 40) + "” is typed under “" + boxes[i][1].replace(/^…/, "") + "” but not added. Press Add next to it, or empty the box, then save.";
        }
        return "";
    }
    function tryClose() {                 // the ✕ and the Esc key: ask once before throwing changes away
        if (changed() && !confirmClose) {
            confirmClose = true;
            optErr = "You changed Options and did not save. Press Save, or close once more to discard the changes.";
            return;
        }
        close();
    }
    onClosed: { confirmClose = false; loaded = ""; confirmTidy = false; }
    function load() {
        var o = win.optsData;
        cityCombo.editText = cityDisplay(o.where);
        countryField.text = o.country || "";
        pickedSources = (o.sources || []).slice();
        remoteWhere = o.remote_where === "world" ? "world" : "country";
        notifyPermission = bridge.notificationPermission(); notifyNote = ""; notifyBad = false;
        pickedRemote = (o.remote_countries || []).slice();
        fullSw.checked = o.full_time_only !== false;
        skipTags.setAll(o.skip_words !== undefined ? o.skip_words : ["intern", "internship"]);
        keepTags.setAll(o.keep_words || []);
        levelTags.setAll(o.level_words || []);
        wantedTags.setAll(o.wanted_roles || []); unwantedTags.setAll(o.unwanted_roles || []);
        var known = bridge.professionFields([]).all || [];
        pickedFields = known.filter(function (name) { return (o.my_fields || []).indexOf(name) >= 0; });   // only names the app has, in its order
        yearsSpin.value = o.max_years !== undefined ? o.max_years : 4;
        engSw.checked = !(o.all_languages === true);
        ageSpin.value = o.max_age_days !== undefined ? o.max_age_days : 10;
        pqSpin.value = o.per_query || 15;
        thrSpin.value = o.threshold !== undefined ? o.threshold : 50;
        minSpin.value = o.min_lead_score || 0;
        fuSpin.value = o.followup_days !== undefined ? o.followup_days : 10;
        scanSpin.value = o.scan_days !== undefined ? o.scan_days : 30;
        notifySw.checked = o.notifications !== false;
        sizeCombo.currentIndex = Math.max(0, sizes.indexOf(o.text_size || 100)); sizeAtOpen = sizes[sizeCombo.currentIndex];
        foldersSw.checked = o.scan_all_folders === true;
        keepSpin.value = o.keep_backups !== undefined ? o.keep_backups : 10;
        modelCombo.currentIndex = Math.max(0, modelCombo.find(o.model));
        rolesModel.clear();
        var qs = o.queries || [];
        for (var i = 0; i < qs.length; i++) rolesModel.append({ text: qs[i] });
        companiesModel.clear();
        var cs = bridge.companies();
        for (var k = 0; k < cs.length; k++)
            companiesModel.append({ name: cs[k].name, ats: cs[k].ats, token: cs[k].token });
        coErr = ""; optErr = ""; roleErr = ""; confirmClose = false;
        roleField.text = ""; coName.text = ""; coToken.text = ""; pendingRole = "";      // nothing half-typed is left from the last time
        loaded = JSON.stringify(collect());
        optSink.forceActiveFocus();                    // no field is pre-selected when the window opens
        if (optScroll && optScroll.contentItem) {      // always open at the top
            optScroll.contentItem.cancelFlick(); optScroll.contentItem.contentY = 0;
        }
    }
    onAboutToShow: load()      // fill + reset BEFORE the window is visible (not after the animation)
    onOpened: { storageNote = ""; storageBad = false; backNote = ""; backBad = false; confirmTidy = false; shelfNote = ""; shelfBad = false; shelfDone = false; shelfSpin.value = 30; readShelf(); }
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
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: optDialog.tryClose() } } }
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
                        // which postings of a company's career site, and which remote jobs, count as "here"
                        SRow { label: "Country"; hint: "for career sites and remote jobs · empty = the city's country"
                            TextField { id: countryField; objectName: "countryField"; implicitWidth: 200; implicitHeight: 30
                                readonly property string guessed: bridge.countryOf(cityCombo.editText)
                                placeholderText: guessed !== "" ? guessed + " (from the city)" : "not known for this city: type it"
                                placeholderTextColor: guessed !== "" ? theme.faint : theme.warn
                                color: theme.ink; font.pixelSize: 12; selectByMouse: true; maximumLength: win.limits.options.country
                                onTextEdited: optDialog.optErr = optDialog.countryProblem(text)
                                background: Rectangle { radius: 8; color: theme.surface; border.width: 1
                                    border.color: countryField.activeFocus ? theme.accent
                                                  : optDialog.countryProblem(countryField.text) !== "" ? theme.crit : theme.line } } }
                        Sep {}
                        // which remote jobs a search keeps, from any source (places.RemoteReach)
                        SRow { label: "Remote jobs"; hint: "from any source · which places they must be open to" }
                        ColumnLayout { id: remoteBox; Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.bottomMargin: 12; spacing: 8
                            Flow { objectName: "remoteScope"; Layout.fillWidth: true; spacing: 6
                                Repeater { model: remoteDialog.choices.scopes || []
                                    Rectangle {
                                        readonly property bool picked: optDialog.remoteWhere === modelData.key
                                        objectName: "remote_" + modelData.key
                                        height: 28; radius: 14; width: rwT.implicitWidth + 24
                                        color: picked ? theme.accent : (rwMa.containsMouse ? theme.surface2 : theme.inset)
                                        border.width: 1; border.color: picked ? win.clearOf(theme.line) : theme.line
                                        Behavior on color { ColorAnimation { duration: 140 } }
                                        // "In my country" names the country when the window knows it
                                        Text { id: rwT; anchors.centerIn: parent
                                            text: (parent.picked ? "✓ " : "") + (modelData.key === "country" && optDialog.homeName !== ""
                                                                                  ? "In " + optDialog.homeName : modelData.name)
                                            font.pixelSize: 12; font.bold: parent.picked; color: parent.picked ? theme.accentInk : theme.soft }
                                        MouseArea { id: rwMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: optDialog.remoteWhere = modelData.key } } } }
                            // a job tied to one country is kept, in both choices, only for yours and the ones added here
                            Text { objectName: "remoteNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                text: (optDialog.remoteWhere === "world"
                                       ? "Kept: remote jobs open to anyone, or to any part of the world (APAC, Americas). "
                                       : "Kept: remote jobs open to anyone, to your country, or to a part of the world it is in. ")
                                      + (optDialog.pickedRemote.length === 0
                                         ? "A job tied to another country is skipped. Add countries where you may work to keep their jobs too."
                                         : "A job tied to another country is skipped, except for these:") }
                            Flow { objectName: "remoteCountries"; Layout.fillWidth: true; spacing: 6
                                Repeater { model: optDialog.pickedRemote
                                    Rectangle { objectName: "remoteCountry_" + modelData
                                        height: 26; radius: 13; width: rcT.implicitWidth + rcX.implicitWidth + 28
                                        color: theme.inset; border.width: 1; border.color: theme.line
                                        Text { id: rcT; anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter
                                            text: optDialog.countryName(modelData); color: theme.ink; font.pixelSize: 12 }
                                        Text { id: rcX; anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                                            text: "✕"; color: rcMa.containsMouse ? theme.crit : theme.faint; font.pixelSize: 10
                                            MouseArea { id: rcMa; anchors.fill: parent; anchors.margins: -6; hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor; onClicked: optDialog.dropRemote(modelData) } } } }
                                SmallButton { id: remoteAddBtn; objectName: "remoteAdd"; text: optDialog.pickedRemote.length === 0 ? "+ Add countries" : "Change"
                                    onClicked: remoteDialog.show(optDialog.pickedRemote, optDialog.homeName) } } }
                        Sep {}
                        // the kinds of job source a search reads, in any combination (job_sources.SourceChoice)
                        SRow { label: "Job sources"; hint: "pick one or more · a search reads every one you pick" }
                        ColumnLayout { id: sourcesBox; Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.bottomMargin: 12; spacing: 6
                            Flow { objectName: "sourceChips"; Layout.fillWidth: true; spacing: 6
                                Repeater { model: optDialog.sourceKinds
                                    Rectangle {
                                        readonly property bool picked: optDialog.pickedSources.indexOf(modelData.key) >= 0
                                        objectName: "source_" + modelData.key
                                        height: 28; radius: 14; width: scT.implicitWidth + 24
                                        color: picked ? theme.accent : (scMa.containsMouse ? theme.surface2 : theme.inset)
                                        border.width: 1; border.color: picked ? win.clearOf(theme.line) : theme.line
                                        Behavior on color { ColorAnimation { duration: 140 } }
                                        Text { id: scT; anchors.centerIn: parent; text: (parent.picked ? "✓ " : "") + modelData.name
                                            font.pixelSize: 12; font.bold: parent.picked; color: parent.picked ? theme.accentInk : theme.soft }
                                        MouseArea { id: scMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: optDialog.toggleSource(modelData.key) } } } }
                            Text { objectName: "sourcesErr"; visible: optDialog.pickedSources.length === 0; Layout.fillWidth: true; wrapMode: Text.WordWrap
                                color: theme.crit; font.pixelSize: 11; font.bold: true; text: "Choose at least one job source." } }
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
                        TagEditor { id: wantedTags; objectName: "wantedTags"; chipTone: theme.good
                            label: "Kinds of role you want"; hint: "the score measures fit for these · another field scores 40 at most"
                            placeholder: "e.g. backend developer" }
                        // which professions the free first look takes as yours: read from the roles above as you type them, or picked here
                        ColumnLayout { id: fieldsBox; Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.bottomMargin: 12; spacing: 8
                            property var read: { var n = wantedTags.tagCount; return optDialog.visible && bridge ? bridge.professionFields(wantedTags.all()) : ({ fields: [], all: [] }); }
                            readonly property bool byHand: optDialog.pickedFields.length > 0
                            Text { objectName: "fieldsNote"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.faint; font.pixelSize: 11
                                text: { var f = fieldsBox.read;
                                        var tail = " A title that is plainly another profession is skipped before scoring, at no cost to your Claude limit; you can still send it to scoring from the list.";
                                        if (fieldsBox.byHand) return "Your profession, as you picked it: " + optDialog.pickedFields.join(", ") + "." + tail;
                                        return (f.fields || []).length === 0
                                            ? "The app cannot tell your profession from these roles or your CV, so no job is skipped for its profession before scoring. Pick it below if you want that."
                                            : "Your profession, as the app reads it from " + (f.from_cv ? "your CV" : "these roles") + ": " + f.fields.join(", ")
                                              + "." + tail + " Pick below to set it yourself."; } }
                            Flow { objectName: "fieldChips"; Layout.fillWidth: true; spacing: 6
                                Repeater { model: fieldsBox.read.all || []
                                    Rectangle {
                                        readonly property bool picked: optDialog.pickedFields.indexOf(modelData) >= 0
                                        readonly property bool readOn: !fieldsBox.byHand && (fieldsBox.read.fields || []).indexOf(modelData) >= 0
                                        height: 24; radius: 12; width: fcT.implicitWidth + 18
                                        color: picked ? theme.accent : (fcMa.containsMouse ? theme.surface2 : theme.inset)
                                        border.width: 1; border.color: picked ? win.clearOf(theme.line) : readOn ? theme.accent : theme.line
                                        Behavior on color { ColorAnimation { duration: 140 } }
                                        Text { id: fcT; anchors.centerIn: parent; text: modelData; font.pixelSize: 11; font.bold: parent.picked || parent.readOn
                                            color: parent.picked ? theme.accentInk : parent.readOn ? theme.accent : theme.soft }
                                        MouseArea { id: fcMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: optDialog.toggleField(modelData, fieldsBox.read.all) } } }
                                SmallButton { objectName: "fieldsAuto"; visible: fieldsBox.byHand; implicitHeight: 24; text: "Let the app decide"
                                    onClicked: optDialog.pickedFields = [] } }
                        }
                        Sep {}
                        TagEditor { id: unwantedTags; objectName: "unwantedTags"; chipTone: theme.crit
                            label: "Kinds of role you do not want"; hint: "a title that names one is skipped before scoring · otherwise scored 20 at most"
                            placeholder: "e.g. economist" }
                        Sep {}
                        TagEditor { id: levelTags; objectName: "levelTags"; chipTone: theme.warn
                            label: "Skip levels above yours"; hint: "title words · empty the list if you are senior"
                            placeholder: "e.g. senior" }
                        Sep {}
                        SRow { label: "Skip jobs asking for"; hint: "years of experience or more · 0 = never"
                            ThemedSpin { id: yearsSpin; objectName: "yearsSpin"; from: win.limits.numbers.max_years[0]; to: win.limits.numbers.max_years[1]; value: 4 } }
                        Sep {}
                        SRow { label: "Full-time only"; hint: "hide part-time roles"
                            ThemedSwitch { id: fullSw; objectName: "fullSw" } }
                        Sep {}
                        SRow { label: "English only"; hint: "hide ads in another language, and roles that need one"
                            ThemedSwitch { id: engSw; objectName: "engSw" } }
                        Sep {}
                        SRow { label: "Max job age"; hint: "in days · 0 = any date"
                            ThemedSpin { id: ageSpin; from: win.limits.numbers.max_age_days[0]; to: win.limits.numbers.max_age_days[1]; value: 10 } }
                        Sep {}
                        SRow { label: "Results per query"
                            ThemedSpin { id: pqSpin; from: win.limits.numbers.per_query[0]; to: win.limits.numbers.per_query[1]; value: 15 } }
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
                                // a long company name wraps; it never runs under the ✕
                                Item { Layout.fillWidth: true; implicitHeight: Math.max(38, coLine.implicitHeight + 14)
                                    RowLayout { id: coLine; objectName: "companyLine"; spacing: 8
                                        anchors.left: parent.left; anchors.leftMargin: 14; anchors.right: parent.right; anchors.rightMargin: 40
                                        anchors.verticalCenter: parent.verticalCenter
                                        Text { objectName: "companyName"; text: model.name; color: theme.ink; font.pixelSize: 13; font.bold: true
                                            Layout.fillWidth: true; wrapMode: Text.Wrap }
                                        Rectangle { radius: 9; color: theme.inset; implicitHeight: Math.max(18, atp.implicitHeight + 6)
                                            implicitWidth: Math.min(atpWide.implicitWidth + 14, 220)
                                            Text { id: atpWide; visible: false; text: atp.text; font.pixelSize: 10 }      // how wide it would be on one line
                                            Text { id: atp; anchors.centerIn: parent; width: parent.width - 14; horizontalAlignment: Text.AlignHCenter
                                                wrapMode: Text.WrapAnywhere; text: model.ats + " / " + model.token; color: theme.soft; font.pixelSize: 10 } } }
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
                            TextField { id: coName; objectName: "coName"; Layout.fillWidth: true; placeholderText: "Company name"
                                color: theme.ink; font.pixelSize: 12; selectByMouse: true; maximumLength: win.limits.company_name
                                onTextEdited: optDialog.coErr = text.length >= maximumLength ? "The company name takes up to " + maximumLength + " characters." : ""
                                background: Rectangle { radius: 7; color: theme.surface; border.color: parent.activeFocus ? theme.accent : theme.line; border.width: 1 } }
                            ThemedCombo { id: coAts; implicitWidth: 128; plainText: true
                                model: win.limits.choices.ats }
                            TextField { id: coToken; Layout.preferredWidth: 110; placeholderText: "token"
                                color: theme.ink; font.pixelSize: 12; selectByMouse: true
                                background: Rectangle { radius: 7; color: theme.surface; border.width: 1
                                    border.color: (optDialog.coErr) ? theme.crit : (coToken.activeFocus ? theme.accent : theme.line) }
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
                        SRow { label: "Write letters above"; hint: "match score " + win.limits.numbers.threshold.join("–")
                            ThemedSpin { id: thrSpin; from: win.limits.numbers.threshold[0]; to: win.limits.numbers.threshold[1]; value: 50 } }
                        Sep {}
                        SRow { label: "Hide leads below"; hint: "0 = show all leads"
                            ThemedSpin { id: minSpin; from: win.limits.numbers.min_lead_score[0]; to: win.limits.numbers.min_lead_score[1]; value: 0 } }
                    }
                }

                // ── FOLLOW-UP ──
                ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                    GroupTitle { text: "Follow-up" }
                    Card {
                        SRow { label: "Remind me after"; hint: "days without a reply · 0 = never"
                            ThemedSpin { id: fuSpin; objectName: "fuSpin"; from: win.limits.numbers.followup_days[0]; to: win.limits.numbers.followup_days[1]; value: 10 } }
                    }
                }

                // ── ABOUT YOU: its own window now; a line here leads there ──
                ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                    GroupTitle { text: "About you" }
                    Card {
                        SRow { label: "Salary, right to work, start, your work"; hint: "in its own window, under Options"
                            SmallButton { objectName: "openAbout"; text: "Open About you"
                                onClicked: { if (optDialog.changed()) { optDialog.optErr = "Save or cancel the Options first, then open About you."; return; }
                                             optDialog.close(); aboutDialog.show(); } } }
                    }
                }

                // ── NOTIFICATIONS AND HOUSEKEEPING ──
                ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                    GroupTitle { text: "Notifications and storage" }
                    Card {
                        // everything in the window larger, for a large or very sharp screen
                        SRow { label: "Size of text and controls"
                            hint: sizeCombo.currentIndex >= 0 && optDialog.sizes[sizeCombo.currentIndex] !== optDialog.sizeAtOpen
                                  ? "saved with Save · used the next time you open the app" : "for a large screen · used the next time you open the app"
                            ThemedCombo { id: sizeCombo; objectName: "sizeCombo"; plainText: true; implicitWidth: 110
                                model: optDialog.sizes.map(function (n) { return n + "%"; }) } }
                        Sep {}
                        SRow { label: "Notifications"; hint: "run finished, paused on the limit, interview invitation"
                            RowLayout { spacing: 8
                                SmallButton { id: notifyTestBtn; objectName: "notifyTest"; text: "Test"
                                    onClicked: { var r = bridge.testNotification(); optDialog.notifyNote = r.msg || "";
                                                 optDialog.notifyBad = !(r && r.ok); optDialog.notifyPermission = bridge.notificationPermission(); } }
                                ThemedSwitch { id: notifySw; objectName: "notifySw" } } }
                        Text { objectName: "notifyNote"; visible: optDialog.notifyNote !== "" && !(notifySw.checked && optDialog.notifyPermission === "off")
                            Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.bottomMargin: 8; wrapMode: Text.WordWrap
                            font.pixelSize: 11; font.bold: optDialog.notifyBad; color: optDialog.notifyBad ? theme.crit : theme.good
                            text: optDialog.notifyNote }
                        // macOS decides whether they are shown: say so in red when it has them turned off
                        RowLayout { objectName: "notifyOffRow"; visible: notifySw.checked && optDialog.notifyPermission === "off"
                            Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.bottomMargin: 10; spacing: 8
                            Text { objectName: "notifyOff"; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: theme.crit
                                font.pixelSize: 11; font.bold: true
                                text: "macOS does not show JobHelper's notifications. Turn them on in System Settings → Notifications → JobHelper." }
                            SmallButton { objectName: "notifySettings"; text: "Open System Settings"
                                onClicked: bridge.openNotificationSettings() } }
                        Sep {}
                        SRow { label: "Keep backups"; hint: "newest ones kept, older deleted · 0 = keep all"
                            ThemedSpin { id: keepSpin; objectName: "keepSpin"; from: win.limits.numbers.keep_backups[0]; to: win.limits.numbers.keep_backups[1]; value: 10 } }
                        Sep {}
                        // letters and CVs moved out of the way because their job fell below your limit: only you remove them
                        SRow { label: "Moved documents older than"; hint: "days · moves those copies to the Trash"
                            RowLayout { spacing: 8
                                ThemedSpin { id: shelfSpin; objectName: "shelfSpin"; from: win.limits.shelf_days[0]; to: win.limits.shelf_days[1]; value: 30
                                    onValueChanged: { optDialog.confirmTidy = false; optDialog.shelfNote = ""; optDialog.readShelf(); } }
                                SmallButton { objectName: "tidyShelf"; primaryStyle: optDialog.confirmTidy
                                    enabled: (optDialog.shelf.old || 0) > 0 || optDialog.confirmTidy
                                    text: optDialog.confirmTidy ? "Yes, move " + optDialog.shelf.old + " to the Trash" : "Remove"
                                    onClicked: optDialog.tidyShelf() }
                                SmallButton { objectName: "tidyCancel"; visible: optDialog.confirmTidy; text: "Cancel"
                                    onClicked: { optDialog.confirmTidy = false; optDialog.shelfNote = ""; } } } }
                        Text { objectName: "shelfNote"; Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.bottomMargin: 12
                            wrapMode: Text.WordWrap; font.pixelSize: 11; font.bold: optDialog.shelfBad
                            color: optDialog.shelfBad ? theme.crit : optDialog.confirmTidy ? theme.warn : optDialog.shelfDone ? theme.good : theme.faint
                            text: optDialog.shelfNote !== "" ? optDialog.shelfNote : optDialog.shelfSummary() }
                        Sep {}
                        // everything in one encrypted backup, a proof that backups restore, and a readable copy to take away
                        SRow { label: "Back up everything"; hint: "data, CV, letters, documents, rules · encrypted"
                            RowLayout { spacing: 6
                                SmallButton { objectName: "backupNow"; enabled: optDialog.storageBusy === ""
                                    text: optDialog.storageBusy === "backup" ? "Backing up…" : "Back up now"; onClicked: optDialog.storage("backup", "") }
                                SmallButton { objectName: "backupCheck"; enabled: optDialog.storageBusy === ""
                                    text: optDialog.storageBusy === "check" ? "Checking…" : "Check backups"; onClicked: optDialog.storage("check", "") }
                                SmallButton { objectName: "backupExport"; enabled: optDialog.storageBusy === ""
                                    text: optDialog.storageBusy === "export" ? "Copying…" : "Save a readable copy…"; onClicked: exportDialog.open() } } }
                        Text { objectName: "storageNote"; visible: text !== ""
                            Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.bottomMargin: 12
                            wrapMode: Text.WordWrap; font.pixelSize: 11; font.bold: optDialog.storageBad
                            color: optDialog.storageBad ? theme.crit : theme.good; text: optDialog.storageNote }
                    }
                }

                // ── EMAIL SCAN ──
                ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                    GroupTitle { text: "Email scan" }
                    Card {
                        SRow { label: "Scan emails from the last"; hint: "days · emails already read are skipped"
                            ThemedSpin { id: scanSpin; objectName: "scanSpin"; from: win.limits.numbers.scan_days[0]; to: win.limits.numbers.scan_days[1]; value: 30 } }
                        Sep {}
                        SRow { label: "Also archived mail and spam"; hint: "not only the Inbox · never Sent or Drafts"
                            ThemedSwitch { id: foldersSw; objectName: "foldersSw" } }
                        Sep {}
                        // for once: after adding a mailbox, or when an old reply is missing. The setting above stays.
                        SRow { label: "Look further back once"; hint: "days · one scan now, the setting above stays"
                            RowLayout { spacing: 8
                                ThemedSpin { id: backSpin; objectName: "backSpin"; from: win.limits.look_back[0]; to: win.limits.look_back[1]; value: 90
                                    onValueChanged: optDialog.backNote = "" }
                                SmallButton { objectName: "backScan"; text: "Scan now"; onClicked: optDialog.scanBack() } } }
                        Text { objectName: "backNote"; visible: text !== ""
                            Layout.fillWidth: true; Layout.leftMargin: 14; Layout.rightMargin: 12; Layout.bottomMargin: 12
                            wrapMode: Text.WordWrap; font.pixelSize: 11; font.bold: optDialog.backBad
                            color: optDialog.backBad ? theme.crit : theme.good; text: optDialog.backNote }
                    }
                }

                // ── MODEL ──
                ColumnLayout { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; spacing: 6
                    GroupTitle { text: "Model" }
                    Card {
                        SRow { label: "Claude model"; hint: "uses your subscription"
                            ThemedCombo { id: modelCombo; implicitWidth: 140; plainText: true; model: win.limits.choices.models } }
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
            SmallButton { objectName: "optCancel"; text: optDialog.confirmClose ? "Discard changes" : "Cancel"; onClicked: optDialog.close() }
            PillButton { id: optSaveBtn; objectName: "optSave"; primaryStyle: true; text: "Save"
                onClicked: {
                    optSink.forceActiveFocus();        // finish any field that is still being edited
                    optDialog.optErr = ""; optDialog.confirmClose = false;
                    if ((cityCombo.editText || "").trim() === "") {
                        optDialog.optErr = "Enter a city (e.g. Prague) before saving."; return;
                    }
                    if (win.hasNonLatin(cityCombo.editText)) {
                        optDialog.optErr = "City must be in English (Latin letters), e.g. Prague."; return;
                    }
                    if (optDialog.countryProblem(countryField.text) !== "") { optDialog.optErr = optDialog.countryProblem(countryField.text); return; }
                    if (optDialog.pickedSources.length === 0) { optDialog.optErr = "Choose at least one job source."; return; }
                    var qs = [];
                    for (var i = 0; i < rolesModel.count; i++) qs.push("" + rolesModel.get(i).text);
                    var both = wantedTags.all().filter(function (w) { return unwantedTags.all().indexOf(w) >= 0; });
                    if (both.length > 0) {
                        optDialog.optErr = "“" + both[0] + "” is under both the roles you want and the roles you do not want. Remove it from one."; return;
                    }
                    var clash = optDialog.roleClash(qs, skipTags.all(), keepTags.all());
                    if (clash !== "") { optDialog.optErr = clash; return; }
                    var left = optDialog.notAdded();
                    if (left !== "") { optDialog.optErr = left; return; }
                    var all = optDialog.collect();
                    var saved = bridge.saveOptions(all.options);
                    if (!(saved && saved.ok)) { optDialog.optErr = (saved && saved.msg) || "The Options could not be saved."; return; }
                    bridge.saveCompanies(all.companies);
                    win.optsData = bridge.options();
                    win.countsData = bridge.counts();      // the follow-up count depends on the new setting
                    ticker.text = "✓ Options saved.";
                    optDialog.close();
                } } }
    }
}
