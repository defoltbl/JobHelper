import QtQuick

// One agent as a workstation on the conveyor: a platform clamped to the belt's
// edge, a robot standing on it whose arms reach down onto the belt, a lit work
// zone on the belt itself and a small console showing what the agent is doing.
// No labels underneath - name / role / agent / state / result show in a tooltip
// ABOVE the robot while the cursor is over it.
//
// Local geometry: the belt's centre line runs through y = 88 (edges 68..108).
Item {
    id: root
    property color ag: "#3b82f6"
    property string title: "Agent"
    property string role: ""
    property string agent: "AGENT"
    property string count: ""
    property string kind: "cv"          // cv | search | write | table | mail
    property bool active: false
    property bool done: false
    property bool showInfo: false
    property bool interactive: true     // false: no hover tooltip (used as the app logo)
    property var theme

    readonly property color agLight: Qt.lighter(ag, 1.22)
    readonly property color agDark: Qt.darker(ag, 1.28)
    readonly property color steelC: theme ? theme.steel : "#6b7787"
    readonly property color frameC: theme ? theme.beltDark : "#aeb9c6"
    readonly property color goodC: theme ? theme.good : "#15944b"
    readonly property color screenC: "#0d141c"
    readonly property string stateText: active ? "Working…" : (done ? "Done" : "Idle")
    readonly property color stateColor: active ? ag : (done ? goodC : steelC)

    width: 120
    height: 112

    // settle arms back to rest when work stops
    onActiveChanged: if (!active) { lArm.rotation = 7; rArm.rotation = -7; }

    // ── work zone painted on the belt under the station ──
    Rectangle {
        id: zone
        x: 12; y: 69; width: 96; height: 38; radius: 7
        color: Qt.rgba(root.ag.r, root.ag.g, root.ag.b, root.active ? 0.30 : (root.showInfo ? 0.20 : 0.10))
        border.color: Qt.rgba(root.ag.r, root.ag.g, root.ag.b, root.active || root.showInfo ? 0.95 : 0.50)
        border.width: 1.5
        Behavior on color { ColorAnimation { duration: 180 } }
        SequentialAnimation on opacity {
            running: root.active; loops: Animation.Infinite
            NumberAnimation { to: 0.55; duration: 600; easing.type: Easing.InOutSine }
            NumberAnimation { to: 1.0; duration: 600; easing.type: Easing.InOutSine }
            onStopped: zone.opacity = 1
        }
        // corner ticks, like floor markings
        Repeater {
            model: [{ x: 5, y: 5 }, { x: 83, y: 5 }, { x: 5, y: 30 }, { x: 83, y: 30 }]
            Rectangle { x: modelData.x; y: modelData.y; width: 8; height: 3; radius: 1.5; color: root.ag; opacity: 0.8 }
        }
    }

    // the job card being worked on (only while this agent works)
    Rectangle {
        id: card
        x: 51; y: 77; width: 18; height: 22; radius: 3
        visible: opacity > 0
        opacity: root.active ? 1 : 0
        color: "#f7f9fc"; border.color: root.agDark; border.width: 1
        Behavior on opacity { NumberAnimation { duration: 180 } }
        Column {
            x: 3; y: 4; spacing: 3
            Repeater { model: [12, 9, 12, 6]
                Rectangle { width: modelData; height: 2; radius: 1; color: root.ag; opacity: 0.75 } }
        }
        SequentialAnimation on scale {
            running: root.active; loops: Animation.Infinite
            NumberAnimation { to: 1.08; duration: 280; easing.type: Easing.InOutSine }
            NumberAnimation { to: 1.0; duration: 280; easing.type: Easing.InOutSine }
        }
    }
    // sparks where the hands meet the card
    Repeater {
        model: [{ x: 44, y: 74, d: 0 }, { x: 73, y: 80, d: 190 }, { x: 47, y: 96, d: 380 }]
        Rectangle {
            x: modelData.x; y: modelData.y; width: 4; height: 4; radius: 2
            color: root.agLight; opacity: 0; visible: root.active
            SequentialAnimation on opacity {
                running: root.active; loops: Animation.Infinite
                PauseAnimation { duration: modelData.d }
                NumberAnimation { to: 1; duration: 90 }
                NumberAnimation { to: 0; duration: 220 }
                PauseAnimation { duration: 570 - modelData.d }
            }
        }
    }

    // ── station hardware: platform on the belt's edge + clamps onto the belt ──
    Rectangle { x: 24; y: 62; width: 7; height: 12; radius: 2; color: root.steelC }      // left clamp
    Rectangle { x: 89; y: 62; width: 7; height: 12; radius: 2; color: root.steelC }      // right clamp
    Rectangle {
        x: 18; y: 55; width: 84; height: 13; radius: 4
        color: root.frameC
        Rectangle { x: 0; y: 0; width: parent.width; height: 3; radius: 1.5; color: root.ag }
        Row { anchors.horizontalCenter: parent.horizontalCenter; y: 6; spacing: 5
            Repeater { model: 5
                Rectangle { width: 6; height: 3; radius: 1.5; color: root.steelC; opacity: 0.55 } } }
    }

    // ── console: what this agent is doing ──
    Rectangle { x: 104; y: 40; width: 3; height: 17; color: root.steelC }                // console post
    Rectangle {
        id: screen
        x: 91; y: 12; width: 30; height: 28; radius: 5
        color: root.screenC
        border.color: root.active ? root.ag : (root.done ? root.goodC : root.steelC); border.width: 1.5
        clip: true
        readonly property real dim: root.active ? 1 : 0.45

        // done: check mark
        Text { anchors.centerIn: parent; visible: root.done && !root.active
            text: "✓"; color: root.goodC; font.pixelSize: 16; font.bold: true }

        Item {
            anchors.fill: parent; anchors.margins: 5
            visible: !(root.done && !root.active); opacity: screen.dim

            // Profiler: a page being scanned
            Item { anchors.fill: parent; visible: root.kind === "cv"
                Column { anchors.centerIn: parent; spacing: 3
                    Repeater { model: [16, 12, 16, 9]
                        Rectangle { width: modelData; height: 2; radius: 1; color: root.agLight; opacity: 0.8 } } }
                Rectangle { id: scan; width: parent.width; height: 2; color: "#ffffff"; y: 0; visible: root.active
                    SequentialAnimation on y { running: root.active && root.kind === "cv"; loops: Animation.Infinite
                        NumberAnimation { from: 0; to: 16; duration: 700; easing.type: Easing.InOutSine }
                        NumberAnimation { from: 16; to: 0; duration: 700; easing.type: Easing.InOutSine } } }
            }
            // Scout: radar sweep
            Item { anchors.fill: parent; visible: root.kind === "search"
                Rectangle { anchors.centerIn: parent; width: 18; height: 18; radius: 9
                    color: "transparent"; border.color: root.agLight; border.width: 1.5 }
                Rectangle { anchors.centerIn: parent; width: 8; height: 8; radius: 4
                    color: "transparent"; border.color: root.agLight; border.width: 1; opacity: 0.6 }
                Item { anchors.centerIn: parent; width: 18; height: 18
                    Rectangle { x: 8; y: 0; width: 2; height: 9; radius: 1; color: "#ffffff" }
                    RotationAnimation on rotation { running: root.active && root.kind === "search"
                        from: 0; to: 360; duration: 1400; loops: Animation.Infinite } }
                Rectangle { x: 13; y: 4; width: 3; height: 3; radius: 1.5; color: "#ffffff"; visible: root.active
                    SequentialAnimation on opacity { running: root.active && root.kind === "search"; loops: Animation.Infinite
                        NumberAnimation { to: 0; duration: 700 } NumberAnimation { to: 1; duration: 700 } } }
            }
            // Scribe: lines being written
            Item { anchors.fill: parent; visible: root.kind === "write"
                property real t: 1
                id: wr
                NumberAnimation on t { running: root.active && root.kind === "write"
                    from: 0; to: 1; duration: 1500; loops: Animation.Infinite; onStopped: wr.t = 1 }
                Column { y: 1; spacing: 3
                    Repeater { model: 4
                        Rectangle { height: 2; radius: 1; color: root.agLight
                            width: 20 * Math.max(0, Math.min(1, wr.t * 4 - index)) * (index === 3 ? 0.55 : 1) } } }
            }
            // Tracker: table cells filling in
            Item { anchors.fill: parent; visible: root.kind === "table"
                property int n: 9
                id: tb
                NumberAnimation on n { running: root.active && root.kind === "table"
                    from: 0; to: 10; duration: 1600; loops: Animation.Infinite; onStopped: tb.n = 9 }
                Grid { anchors.centerIn: parent; columns: 3; spacing: 2
                    Repeater { model: 9
                        Rectangle { width: 5; height: 4; radius: 1
                            color: index < 3 ? "#ffffff" : root.agLight
                            opacity: index < tb.n ? (index < 3 ? 0.9 : 0.8) : 0.18 } } }
            }
            // Postman: an envelope arriving
            Item { anchors.fill: parent; visible: root.kind === "mail"
                Item { id: env; width: 18; height: 13; x: 1; y: 3
                    Rectangle { anchors.fill: parent; radius: 2; color: "transparent"; border.color: root.agLight; border.width: 1.5 }
                    Rectangle { x: 2; y: 4; width: 9; height: 1.5; color: root.agLight; rotation: 32; transformOrigin: Item.Left; antialiasing: true }
                    Rectangle { x: 7; y: 4; width: 9; height: 1.5; color: root.agLight; rotation: -32; transformOrigin: Item.Right; antialiasing: true }
                    SequentialAnimation on y { running: root.active && root.kind === "mail"; loops: Animation.Infinite
                        NumberAnimation { from: -14; to: 3; duration: 420; easing.type: Easing.OutBack }
                        PauseAnimation { duration: 520 }
                        NumberAnimation { to: 22; duration: 260; easing.type: Easing.InQuad }
                        onStopped: env.y = 3 }
                }
            }
        }
    }

    // ── the robot ──
    Item {
        id: bot
        x: 30; y: root.active ? 2 : 0
        width: 60; height: 60
        Behavior on y { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

        // legs down to the platform
        Rectangle { x: 20; y: 50; width: 6; height: 8; radius: 2; color: root.steelC }
        Rectangle { x: 34; y: 50; width: 6; height: 8; radius: 2; color: root.steelC }

        // torso
        Rectangle {
            x: 13; y: 30; width: 34; height: 23; radius: 8
            gradient: Gradient {
                GradientStop { position: 0; color: root.ag }
                GradientStop { position: 1; color: root.agDark }
            }
            // chest display
            Rectangle { anchors.horizontalCenter: parent.horizontalCenter; y: 6; width: 20; height: 10; radius: 3; color: root.screenC
                Row { anchors.centerIn: parent; spacing: 3
                    Repeater { model: 3
                        Rectangle { width: 3; height: 4; radius: 1
                            color: root.done && !root.active ? root.goodC : root.agLight
                            opacity: root.active || root.done ? 1 : 0.4
                            SequentialAnimation on opacity { running: root.active; loops: Animation.Infinite
                                PauseAnimation { duration: index * 140 }
                                NumberAnimation { to: 0.2; duration: 200 }
                                NumberAnimation { to: 1; duration: 200 }
                                PauseAnimation { duration: 280 - index * 140 } } } } }
            }
        }
        // neck
        Rectangle { x: 25; y: 26; width: 10; height: 6; color: root.steelC }

        // arms: shoulder at the torso, hand down on the belt
        Item {
            id: lArm
            x: 9; y: 33; width: 7; height: 42
            transformOrigin: Item.Top; rotation: 7
            Behavior on rotation { enabled: !root.active; NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
            Rectangle { x: 1; y: 0; width: 5; height: 36; radius: 2.5; color: root.steelC }
            Rectangle { x: -1; y: -3; width: 9; height: 9; radius: 4.5; color: root.agDark }          // shoulder
            Rectangle { x: 0; y: 16; width: 7; height: 7; radius: 3.5; color: root.ag }               // elbow
            Rectangle { x: -2; y: 33; width: 11; height: 6; radius: 2; color: root.ag }               // wrist
            Rectangle { x: -2; y: 37; width: 3; height: 7; radius: 1.5; color: root.agLight }         // gripper
            Rectangle { x: 6; y: 37; width: 3; height: 7; radius: 1.5; color: root.agLight }
            SequentialAnimation on rotation {
                running: root.active; loops: Animation.Infinite
                NumberAnimation { to: -24; duration: 300; easing.type: Easing.InOutSine }
                NumberAnimation { to: -10; duration: 220; easing.type: Easing.InOutSine }
                NumberAnimation { to: -24; duration: 220; easing.type: Easing.InOutSine }
                NumberAnimation { to: 4; duration: 320; easing.type: Easing.InOutSine }
            }
        }
        Item {
            id: rArm
            x: 44; y: 33; width: 7; height: 42
            transformOrigin: Item.Top; rotation: -7
            Behavior on rotation { enabled: !root.active; NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
            Rectangle { x: 1; y: 0; width: 5; height: 36; radius: 2.5; color: root.steelC }
            Rectangle { x: -1; y: -3; width: 9; height: 9; radius: 4.5; color: root.agDark }
            Rectangle { x: 0; y: 16; width: 7; height: 7; radius: 3.5; color: root.ag }
            Rectangle { x: -2; y: 33; width: 11; height: 6; radius: 2; color: root.ag }
            Rectangle { x: -2; y: 37; width: 3; height: 7; radius: 1.5; color: root.agLight }
            Rectangle { x: 6; y: 37; width: 3; height: 7; radius: 1.5; color: root.agLight }
            SequentialAnimation on rotation {
                running: root.active; loops: Animation.Infinite
                NumberAnimation { to: -4; duration: 320; easing.type: Easing.InOutSine }
                NumberAnimation { to: 24; duration: 300; easing.type: Easing.InOutSine }
                NumberAnimation { to: 10; duration: 220; easing.type: Easing.InOutSine }
                NumberAnimation { to: 24; duration: 220; easing.type: Easing.InOutSine }
            }
        }

        // head (looks down at the belt while working)
        Item {
            id: head
            x: 8; y: 0; width: 44; height: 28
            transformOrigin: Item.Bottom
            rotation: 0
            SequentialAnimation on rotation {
                running: root.active; loops: Animation.Infinite
                NumberAnimation { to: -4; duration: 520; easing.type: Easing.InOutSine }
                NumberAnimation { to: 4; duration: 520; easing.type: Easing.InOutSine }
                onStopped: head.rotation = 0
            }
            // antenna + beacon
            Rectangle { x: 21; y: -9; width: 2; height: 10; color: root.steelC }
            Rectangle { id: beacon; x: 18.5; y: -14; width: 7; height: 7; radius: 3.5
                color: root.done && !root.active ? root.goodC : root.ag
                SequentialAnimation on opacity { running: root.active; loops: Animation.Infinite
                    NumberAnimation { to: 0.25; duration: 420 } NumberAnimation { to: 1.0; duration: 420 }
                    onStopped: beacon.opacity = 1 } }
            // ears
            Rectangle { x: -4; y: 9; width: 6; height: 11; radius: 3; color: root.agDark }
            Rectangle { x: 42; y: 9; width: 6; height: 11; radius: 3; color: root.agDark }
            // skull
            Rectangle { anchors.fill: parent; radius: 10
                gradient: Gradient {
                    GradientStop { position: 0; color: root.agLight }
                    GradientStop { position: 1; color: root.ag }
                } }
            // visor + eyes
            Rectangle {
                x: 5; y: 7; width: 34; height: 14; radius: 7; color: root.screenC
                Row {
                    id: eyes
                    anchors.verticalCenter: parent.verticalCenter
                    x: 9; spacing: 8
                    SequentialAnimation on x { running: root.active; loops: Animation.Infinite
                        NumberAnimation { to: 5; duration: 420; easing.type: Easing.InOutSine }
                        NumberAnimation { to: 13; duration: 420; easing.type: Easing.InOutSine }
                        onStopped: eyes.x = 9 }
                    Repeater { model: 2
                        Rectangle { width: 6; height: root.active ? 7 : 5; radius: 3
                            anchors.verticalCenter: parent.verticalCenter
                            color: root.done && !root.active ? root.goodC : (root.active ? "#ffffff" : root.agLight)
                            Behavior on height { NumberAnimation { duration: 150 } } } }
                }
            }
        }
    }

    // hover target: robot + console + its zone on the belt
    MouseArea {
        x: 8; y: -14; width: 116; height: 124
        enabled: root.interactive; visible: root.interactive
        hoverEnabled: true
        onEntered: root.showInfo = true
        onExited: root.showInfo = false
    }

    // ── tooltip ABOVE the robot (name / role / agent / state / result) ──
    Rectangle {
        id: tip
        visible: opacity > 0
        opacity: root.showInfo ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 120 } }
        z: 60
        width: tcol.implicitWidth + 26
        height: tcol.implicitHeight + 16
        x: (root.width - width) / 2
        y: -height - 20 + (root.showInfo ? 0 : 4)
        Behavior on y { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        radius: 10
        color: root.theme ? root.theme.surface2 : "#1f2a37"
        border.color: root.ag; border.width: 1
        Column {
            id: tcol
            anchors.centerIn: parent; spacing: 2
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.title
                color: root.theme ? root.theme.ink : "#e7eef5"; font.bold: true; font.pixelSize: 13 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.role
                color: root.theme ? root.theme.soft : "#9fb0c1"; font.pixelSize: 11 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.agent
                color: root.theme ? root.theme.faint : "#6f7f90"; font.pixelSize: 8; font.letterSpacing: 1.2 }
            Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 5; topPadding: 2
                Rectangle { width: 7; height: 7; radius: 3.5; color: root.stateColor; anchors.verticalCenter: parent.verticalCenter }
                Text { text: root.stateText + (root.count !== "" ? " · " + root.count : "")
                    color: root.stateColor; font.pixelSize: 11; font.bold: true }
            }
        }
        // little downward pointer
        Rectangle {
            width: 10; height: 10; rotation: 45
            color: parent.color; border.color: root.ag; border.width: 1
            x: parent.width / 2 - 5; y: parent.height - 5
        }
        Rectangle { // mask the pointer's top border seam
            width: 14; height: 6; color: parent.color
            x: parent.width / 2 - 7; y: parent.height - 7
        }
    }
}
