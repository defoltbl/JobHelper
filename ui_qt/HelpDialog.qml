// HelpDialog: one window of the JobHelper app, created once in Main.qml as `helpDialog`.
// It uses names from Main.qml (theme, win, bridge, ticker and the other windows) through the QML context.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

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
            "<b>skipped</b>: the app saw from the title that it is another profession than the roles you look for, or a kind of role you listed as not wanted, and did not spend a Claude call on it. \"<b>Score it anyway</b>\" in the job window overrides that.",
            "<b>Options</b>, \"<b>Write letters above</b>\", sets from which <b>score</b> a CV and a letter are written.",
            "What counts as another profession follows the roles under \"<b>Kinds of role you want</b>\" in <b>Options</b>. The chips below them show what the app takes as your profession, and you can pick it yourself.",
            "\"<b>scored from the title only</b>\" or \"<b>from a short summary</b>\": the app could not read the whole posting. \"<b>Read it again</b>\" or \"<b>Paste the posting's text</b>\" in the job window fixes that, and the job is scored again by itself.",
            "\"<b>was 55</b>\" under a score is what the job scored before it was scored again. \"<b>no longer accepts applications</b>\": the posting closed after it was found." ] },
        { title: "The lists on the left", lines: [
            "<b>New Jobs</b>: jobs you have not applied to. <b>Applications</b>: jobs you applied to, with their status. <b>Responses</b>: every reply email. <b>Analytics</b>: the numbers. <b>Insights</b>: what works, how each <b>search</b> keyword performs, skills worth learning, and what the postings say they pay next to your target.",
            "In every list you can <b>search</b>, <b>filter</b> with the chips and <b>sort</b>. Click a row to open it.",
            "<b>Filtered out</b> in the <b>Last run</b> card lists every posting the last <b>search</b> removed before scoring, with the reason for each one. If a rule removes jobs you want, change it in <b>Options</b>.",
            "<b>Not interested</b> (in a job's window) removes a job for good; the \"<b>not interested</b>\" chip in <b>New Jobs</b> brings it back." ] },
        { title: "The job window", lines: [
            "It shows the description, why the job got its <b>score</b>, which keywords from the posting are in your CV and which are not, and buttons for the CV, the letter and their PDFs.",
            "\"<b>Move documents to backup</b>\" appears when a job has a letter and CV but now scores below your limit. They go to an encrypted backup, and \"<b>Put them back</b>\" returns them. <b>New Jobs</b> can do both for all such jobs at once. Old copies are removed in <b>Options</b>, to the <b>Trash</b>, never deleted.",
            "For an application you can change the status by hand (<b>Waiting</b>, <b>Interview</b>, <b>Offer</b>, <b>Rejected</b>), set the day you applied, prepare for an interview, and draft a follow-up email to copy.",
            "<b>Edit letter</b> lets you change a letter the app wrote, or have one paragraph rewritten. Your own letters are never changed by the app.",
            "For a job you applied to: <b>A date to remember</b>: put an interview, a deadline or a test task on a job. It appears under <b>Coming up</b> on the main screen, and you get a notification the day before and on the day.",
            "<b>Paste a reply</b>: an answer that came on LinkedIn or in a company portal can be pasted in, and it is filed like an email.",
            "<b>Notes</b> are kept for the company, not the job: who you spoke to, the salary mentioned, what they asked. They show again when you apply there later.",
            "<b>Compare CV</b> puts your <b>master CV</b> next to the adapted one and shows only the paragraphs that differ.",
            "<b>Add to calendar</b> opens a saved date in Calendar, so your phone reminds you too. From the day of an interview the window offers a <b>thank-you</b> draft.",
            "<b>Form answers</b>: paste the questions of that job's application form and Claude drafts the answers from your CV and the posting. They are kept with the job; anything it cannot know is marked for you to fill in.",
            "For a new job, <b>Before you apply</b> lists the steps in order and ticks off what you have done. <b>One PDF</b> joins the letter and the CV when a form takes a single file." ] },
        { title: "Your CV and letters", lines: [
            "The app <b>never invents experience</b>. An adapted CV changes only the Profile and Key Skills parts of your <b>master CV</b>, and a letter may only use what your CV shows.",
            "Change your <b>master CV</b> in the <b>Account card</b>. The rules the app follows are in two files in the data folder; if you edit them by hand, approve the change in the <b>Account</b> card." ] },
        { title: "Claude and the limit", lines: [
            "The app works through your Claude subscription, so a <b>search</b> costs you nothing extra. \"<b>Same work via API</b>\" on the Last run card shows what the last <b>search</b> or email scan alone would have cost with pay-per-use API billing.",
            "Your subscription has a <b>5-hour</b> and a <b>7-day</b> <b>limit</b> (<b>Usage left</b>, top right). The card shows when a nearly used one resets. When one is used up, the card says 0% left, the run pauses, saves, and shows a warning. <b>Resume</b> turns blue when the limit is back.",
            "To use less: fewer <b>search</b> roles, Czech boards instead of every source, a higher \"<b>Write letters above</b>\"." ] },
        { title: "Privacy and safety", lines: [
            "Everything stays on your Mac. Your job data and backups are <b>encrypted</b> on disk, and the Gmail app password and the data key are in the macOS <b>Keychain</b>.",
            "Save your <b>recovery key</b> once (python status.py security recovery-key) and keep it in a password manager: on a new Mac it is the only way to open your data.",
            "Only job postings, your CV text and the text of reply emails are sent to Claude, to <b>score</b> jobs and write documents." ] },
        { title: "If something looks wrong", lines: [
            "A robot or button does nothing: open the <b>Account</b> chip on the left and check the four rows are green.",
            "A rejection is missing: it probably did not arrive in the scanned mailbox. Mark it by hand in the job window, or add a <b>second mailbox</b> in the <b>Account card</b>.",
            "Too many poor jobs: add words to \"<b>Skip titles with</b>\" in <b>Options</b>, or remove a <b>search</b> role that <b>Insights</b> marks as weak.",
            "Good jobs are skipped: check the profession chips in <b>Options</b>, and send a single job to scoring with \"<b>Score it anyway</b>\".",
            "An error the app carried on after leaves one line in <b>data/app_trouble.log</b>.",
            "More detail on every command is in <b>COMMANDS.md</b>, and every screen is explained with pictures in <b>docs/GUIDE.md</b>, both in the app's folder." ] }
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
                            color: parent.on ? theme.accentInk : theme.soft }
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
