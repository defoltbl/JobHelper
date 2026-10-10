// AssistantBot: the assistant that stands at the end of the assembly line (StagePanel). It blinks,
// waves when the app opens or the pointer is over it, and opens its window when tapped.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Dialogs
import QtQuick.Effects

Item {
    id: root
    width: 84; height: 104
    property var theme
    property color ag: theme ? theme.a6 : "#06b6d4"
    property bool busy: false           // it is working on a request
    property bool greeting: false       // waving hello, with the bubble shown
    property bool hovered: false
    property real lid: 0                // 0 = eyes open, 1 = closed
    readonly property bool waving: greeting || hovered
    property string note: ""             // what it has to tell: the morning's briefing, or a form it noticed
    readonly property string says: busy ? "Working on it…" : (greeting ? (note !== "" ? note : "Hi! Tap me to fill in a form.") : "Assistant · tap to ask")
    // The bubble keeps the words it came up with while it fades out: changing them at that moment
    // (the greeting ending) made it change size and jump on its way out.
    readonly property bool talking: greeting || hovered || busy
    property string shown: ""
    onTalkingChanged: if (talking) shown = says
    onSaysChanged: if (talking) shown = says
    readonly property color agLight: Qt.lighter(ag, 1.25)
    readonly property color agDark: Qt.darker(ag, 1.3)
    readonly property color steelC: theme ? theme.steel : "#6b7787"
    readonly property color screenC: "#0d141c"
    property real lookX: 0              // where it looks: -1 (left) to 1 (right)
    property real lookY: 0              // -1 (up) to 1 (down)
    property real nodBy: 0              // the head going down and up: "done"
    property real shakeBy: 0            // the head going left and right: "that did not work"
    Behavior on lookX { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    Behavior on lookY { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    function lookAt(x, y) {             // a point in its parent's coordinates; far away counts as "that way"
        var dx = x - (root.x + 42), dy = y - (root.y + 36);
        lookX = Math.max(-1, Math.min(1, dx / 160)); lookY = Math.max(-1, Math.min(1, dy / 120));
    }
    function lookAhead() { lookX = 0; lookY = 0; }
    function nod() { shaking.stop(); shakeBy = 0; nodding.restart(); }
    function shake() { nodding.stop(); nodBy = 0; shaking.restart(); }
    SequentialAnimation { id: nodding
        NumberAnimation { target: root; property: "nodBy"; to: 5; duration: 130; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "nodBy"; to: 0; duration: 150; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "nodBy"; to: 5; duration: 130; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "nodBy"; to: 0; duration: 170; easing.type: Easing.InOutSine } }
    SequentialAnimation { id: shaking
        NumberAnimation { target: root; property: "shakeBy"; to: -5; duration: 90; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "shakeBy"; to: 5; duration: 150; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "shakeBy"; to: -5; duration: 150; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "shakeBy"; to: 0; duration: 110; easing.type: Easing.InOutSine } }
    signal tapped()
    function greet() { note = ""; greeting = true; greetEnd.restart(); }                      // a plain hello
    function tell(text) { note = text || ""; greeting = true; greetEnd.restart(); }           // hello, with something to say
    Timer { id: greetEnd; interval: root.note !== "" ? 9000 : 4200; onTriggered: root.greeting = false }

    // the eyes close and open by themselves every few seconds, twice now and then
    SequentialAnimation on lid {
        running: root.visible; loops: Animation.Infinite
        PauseAnimation { duration: 2600 }
        NumberAnimation { to: 1; duration: 70 } NumberAnimation { to: 0; duration: 120 }
        PauseAnimation { duration: 3400 }
        NumberAnimation { to: 1; duration: 70 } NumberAnimation { to: 0; duration: 110 }
        PauseAnimation { duration: 160 }
        NumberAnimation { to: 1; duration: 70 } NumberAnimation { to: 0; duration: 120 }
    }

    // shadow on the floor: smaller while the body is up
    Rectangle { x: 22 + body.lift; y: 96; width: 40 - 2 * body.lift; height: 6; radius: 3; color: "#000000"; opacity: 0.22 }

    Item {
        id: body
        property real lift: 0           // it hovers: up and down a little, faster while busy
        x: 12; y: 22 - lift; width: 60; height: 72
        SequentialAnimation on lift { running: root.visible; loops: Animation.Infinite
            NumberAnimation { to: 5; duration: root.busy ? 420 : 1300; easing.type: Easing.InOutSine }
            NumberAnimation { to: 0; duration: root.busy ? 420 : 1300; easing.type: Easing.InOutSine } }

        // the arm that waves (drawn behind the body, shoulder at its side)
        Item { id: wave; objectName: "assistantArm"; x: 50; y: 40; width: 8; height: 30
            transformOrigin: Item.Top; rotation: root.waving ? -150 : -18
            Behavior on rotation { enabled: !root.waving; NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
            Rectangle { x: 1.5; y: 0; width: 5; height: 24; radius: 2.5; color: root.steelC }
            Rectangle { x: -1; y: 20; width: 10; height: 10; radius: 5; color: root.agLight }
            SequentialAnimation on rotation { running: root.waving; loops: Animation.Infinite
                NumberAnimation { to: -165; duration: 230; easing.type: Easing.InOutSine }
                NumberAnimation { to: -125; duration: 230; easing.type: Easing.InOutSine } } }
        Item { x: 2; y: 40; width: 8; height: 30; transformOrigin: Item.Top; rotation: 16
            Rectangle { x: 1.5; y: 0; width: 5; height: 24; radius: 2.5; color: root.steelC }
            Rectangle { x: -1; y: 20; width: 10; height: 10; radius: 5; color: root.agLight } }

        // torso, with a small light that beats
        Rectangle { x: 14; y: 36; width: 32; height: 30; radius: 13
            gradient: Gradient { GradientStop { position: 0; color: root.ag } GradientStop { position: 1; color: root.agDark } }
            Rectangle { id: heart; anchors.horizontalCenter: parent.horizontalCenter; y: 10; width: 9; height: 9; radius: 4.5; color: root.agLight
                SequentialAnimation on opacity { running: root.visible; loops: Animation.Infinite
                    NumberAnimation { to: 0.35; duration: root.busy ? 260 : 900 } NumberAnimation { to: 1; duration: root.busy ? 260 : 900 } } } }
        // the jet it hovers on
        Rectangle { x: 23; y: 65; width: 14; height: 5; radius: 2.5; color: root.steelC }
        Rectangle { x: 26; y: 70; width: 8; height: 4 + body.lift * 0.6; radius: 3; color: root.agLight; opacity: 0.55 }

        // head
        Item { id: head; objectName: "assistantHead"; x: 5 + root.shakeBy; y: root.nodBy; width: 50; height: 38
            transformOrigin: Item.Bottom; rotation: root.waving ? 5 : 0
            Behavior on rotation { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            Rectangle { x: 24; y: -9; width: 2; height: 10; color: root.steelC }
            Rectangle { id: beacon; x: 21.5; y: -14; width: 7; height: 7; radius: 3.5; color: root.busy ? "#ffffff" : root.agLight
                SequentialAnimation on opacity { running: root.busy; loops: Animation.Infinite
                    NumberAnimation { to: 0.2; duration: 240 } NumberAnimation { to: 1; duration: 240 }
                    onStopped: beacon.opacity = 1 } }
            Rectangle { x: -4; y: 13; width: 6; height: 12; radius: 3; color: root.agDark }
            Rectangle { x: 48; y: 13; width: 6; height: 12; radius: 3; color: root.agDark }
            Rectangle { anchors.fill: parent; radius: 17
                gradient: Gradient { GradientStop { position: 0; color: root.agLight } GradientStop { position: 1; color: root.ag } } }
            Rectangle { x: 6; y: 8; width: 38; height: 22; radius: 11; color: root.screenC
                Row { id: eyes; objectName: "assistantEyes"; x: (parent.width - width) / 2 + root.lookX * 4; y: (parent.height - height) / 2 + root.lookY * 2.5; spacing: 9
                    Repeater { model: 2
                        Rectangle { objectName: "assistantEye" + index; width: 8; height: Math.max(1.4, 10 * (1 - root.lid)); radius: Math.min(4, height / 2)
                            anchors.verticalCenter: parent.verticalCenter; color: "#ffffff" } } }
                // a small smile while it greets
                Rectangle { visible: root.waving; anchors.horizontalCenter: parent.horizontalCenter; y: 17.5; width: 8; height: 2; radius: 1; color: root.agLight } } }
    }

    // what it says, to the left of it so that it never leaves the floor
    Rectangle {
        id: bubble; objectName: "assistantBubble"
        visible: opacity > 0; opacity: root.talking ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160 } }
        width: Math.min(root.note !== "" && root.greeting ? 300 : 200, bubbleText.implicitWidth + 22); height: bubbleText.implicitHeight + 14
        Behavior on width { enabled: bubble.opacity === 1; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        x: -width - 2; y: 52; radius: 10; z: 5
        color: root.theme ? root.theme.surface2 : "#1f2a37"; border.color: root.ag; border.width: 1
        Text { id: bubbleText; x: 11; y: 7; width: (root.note !== "" && root.greeting ? 300 : 200) - 22; wrapMode: Text.WordWrap; text: root.shown
            color: root.theme ? root.theme.ink : "#e7eef5"; font.pixelSize: 11; font.bold: true }
        Rectangle { width: 9; height: 9; rotation: 45; color: parent.color; border.color: root.ag; border.width: 1; x: parent.width - 5; y: parent.height / 2 - 4.5 }
        Rectangle { width: 6; height: 14; color: parent.color; x: parent.width - 7; y: parent.height / 2 - 7 }
    }

    MouseArea { objectName: "assistantTap"; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
        onEntered: root.hovered = true
        onExited: root.hovered = false
        onClicked: root.tapped() }
}
