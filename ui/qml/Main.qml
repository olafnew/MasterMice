import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import "Theme.js" as Theme

ApplicationWindow {
    id: root
    visible: true
    width: 1060
    height: 700
    minimumWidth: 920
    minimumHeight: 620
    title: {
        var base = "MasterMice"
        if (backend && backend.appVersion) base += " v" + backend.appVersion
        if (backend && backend.mouseModelName) base += " — " + backend.mouseModelName
        return base
    }

    property string appearanceMode: uiState ? uiState.appearanceMode : "system"
    readonly property bool darkMode: appearanceMode === "dark"
                                    || (appearanceMode === "system"
                                        && (uiState ? uiState.systemDarkMode : false))
    readonly property var theme: Theme.palette(darkMode)
    readonly property string fontFamily: uiState ? uiState.fontFamily : "Segoe UI"
    property int currentPage: 0
    property Item hoveredNavItem: null
    property string hoveredNavText: ""
    property real hoveredNavCenterX: 0
    property real hoveredNavCenterY: 0

    color: theme.bg

    Material.theme: darkMode ? Material.Dark : Material.Light
    Material.accent: theme.accent
    Material.background: theme.bg
    Material.foreground: theme.textPrimary

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: sidebar
            Layout.preferredWidth: 72
            Layout.fillHeight: true
            color: root.theme.bgSidebar

            // ── Top: logo + nav items ──────────────────────
            Column {
                id: topNavCol
                anchors {
                    left: parent.left
                    right: parent.right
                    top: parent.top
                    topMargin: 20
                }
                spacing: 6

                Rectangle {
                    width: 44
                    height: 44
                    radius: 14
                    color: root.theme.accent
                    anchors.horizontalCenter: parent.horizontalCenter

                    Image {
                        anchors.centerIn: parent
                        width: 28; height: 28
                        source: applicationDirUrl + "/images/icons/icon.png"
                        sourceSize: Qt.size(28, 28)
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                    }
                }

                Item { width: 1; height: 18 }

                Repeater {
                    model: [
                        { icon: "mouse-simple", tip: "Mouse & Profiles", page: 0 },
                        { icon: "sliders-horizontal", tip: "Point & Scroll", page: 1 }
                    ]

                    delegate: FocusScope {
                        id: navItem
                        width: sidebar.width
                        height: 56
                        activeFocusOnTab: true

                        Accessible.role: Accessible.Button
                        Accessible.name: modelData.tip
                        Accessible.description: "Open " + modelData.tip

                        Keys.onReturnPressed: root.currentPage = modelData.page
                        Keys.onEnterPressed: root.currentPage = modelData.page
                        Keys.onSpacePressed: root.currentPage = modelData.page

                        Rectangle {
                            anchors.centerIn: parent
                            width: 46
                            height: 46
                            radius: 14
                            color: root.currentPage === modelData.page
                                   ? Qt.rgba(0, 0.83, 0.67, root.darkMode ? 0.14 : 0.16)
                                   : navMouse.containsMouse || navItem.activeFocus
                                     ? Qt.rgba(1, 1, 1, root.darkMode ? 0.06 : 0.22)
                                     : "transparent"

                            border.width: navItem.activeFocus ? 1 : 0
                            border.color: root.theme.accent

                            Behavior on color { ColorAnimation { duration: 150 } }

                            AppIcon {
                                anchors.centerIn: parent
                                width: 22
                                height: 22
                                name: modelData.icon
                                iconColor: root.currentPage === modelData.page
                                           ? root.theme.accent
                                           : navMouse.containsMouse || navItem.activeFocus
                                             ? root.theme.textPrimary
                                             : root.theme.textSecondary
                            }
                        }

                        Rectangle {
                            width: 3
                            height: 24
                            radius: 2
                            color: root.theme.accent
                            anchors {
                                left: parent.left
                                verticalCenter: parent.verticalCenter
                            }
                            visible: root.currentPage === modelData.page
                        }

                        MouseArea {
                            id: navMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.currentPage = modelData.page
                            onContainsMouseChanged: {
                                if (containsMouse) {
                                    var p = navItem.mapToItem(overlayLayer, navItem.width, navItem.height / 2)
                                    root.hoveredNavItem = navItem
                                    root.hoveredNavText = modelData.tip
                                    root.hoveredNavCenterX = p.x
                                    root.hoveredNavCenterY = p.y
                                } else if (root.hoveredNavItem === navItem) {
                                    root.hoveredNavItem = null
                                    root.hoveredNavText = ""
                                }
                            }
                        }
                    }
                }
            }

            // ── Bottom: settings gear ──────────────────────
            FocusScope {
                id: settingsNav
                width: sidebar.width
                height: 56
                anchors {
                    bottom: parent.bottom
                    bottomMargin: 12
                }
                activeFocusOnTab: true

                Accessible.role: Accessible.Button
                Accessible.name: "Settings"

                Keys.onReturnPressed: root.currentPage = 2
                Keys.onEnterPressed: root.currentPage = 2
                Keys.onSpacePressed: root.currentPage = 2

                Rectangle {
                    anchors.centerIn: parent
                    width: 46
                    height: 46
                    radius: 14
                    color: root.currentPage === 2
                           ? Qt.rgba(0, 0.83, 0.67, root.darkMode ? 0.14 : 0.16)
                           : settingsMouse.containsMouse || settingsNav.activeFocus
                             ? Qt.rgba(1, 1, 1, root.darkMode ? 0.06 : 0.22)
                             : "transparent"

                    border.width: settingsNav.activeFocus ? 1 : 0
                    border.color: root.theme.accent

                    Behavior on color { ColorAnimation { duration: 150 } }

                    AppIcon {
                        anchors.centerIn: parent
                        width: 22
                        height: 22
                        name: "gear"
                        iconColor: root.currentPage === 2
                                   ? root.theme.accent
                                   : settingsMouse.containsMouse || settingsNav.activeFocus
                                     ? root.theme.textPrimary
                                     : root.theme.textSecondary
                    }
                }

                Rectangle {
                    width: 3
                    height: 24
                    radius: 2
                    color: root.theme.accent
                    anchors {
                        left: parent.left
                        verticalCenter: parent.verticalCenter
                    }
                    visible: root.currentPage === 2
                }

                MouseArea {
                    id: settingsMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.currentPage = 2
                    onContainsMouseChanged: {
                        if (containsMouse) {
                            var p = settingsNav.mapToItem(overlayLayer, settingsNav.width, settingsNav.height / 2)
                            root.hoveredNavItem = settingsNav
                            root.hoveredNavText = "Settings"
                            root.hoveredNavCenterX = p.x
                            root.hoveredNavCenterY = p.y
                        } else if (root.hoveredNavItem === settingsNav) {
                            root.hoveredNavItem = null
                            root.hoveredNavText = ""
                        }
                    }
                }
            }
        }

        StackLayout {
            id: contentStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.currentPage

            MousePage {}
            Loader {
                active: true    // pre-load for instant tab switching
                source: "ScrollPage.qml"
            }
            Loader {
                active: true
                source: "SettingsPage.qml"
            }
        }
    }

    Item {
        id: overlayLayer
        anchors.fill: parent
        z: 999

        Rectangle {
            id: navTooltip
            x: root.hoveredNavCenterX + 10
            y: Math.max(8, Math.min(root.height - height - 8, root.hoveredNavCenterY - height / 2))
            visible: root.hoveredNavItem !== null
            opacity: visible ? 1 : 0
            radius: 10
            color: root.theme.tooltipBg
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, root.darkMode ? 0.06 : 0.12)
            width: navTooltipText.implicitWidth + 22
            height: navTooltipText.implicitHeight + 14

            Behavior on opacity { NumberAnimation { duration: 120 } }

            Text {
                id: navTooltipText
                anchors.centerIn: parent
                text: root.hoveredNavText
                font {
                    family: root.fontFamily
                    pixelSize: 12
                }
                color: root.theme.tooltipText
            }
        }
    }

    Rectangle {
        id: toast
        anchors {
            bottom: parent.bottom
            horizontalCenter: parent.horizontalCenter
            bottomMargin: 24
        }
        width: toastText.implicitWidth + 32
        height: 38
        radius: 19
        color: root.theme.accent
        opacity: 0
        visible: opacity > 0

        Text {
            id: toastText
            anchors.centerIn: parent
            font {
                family: root.fontFamily
                pixelSize: 12
                bold: true
            }
            color: root.theme.bgSidebar
        }

        Behavior on opacity { NumberAnimation { duration: 200 } }

        function show(msg) {
            toastText.text = msg
            toast.opacity = 1
            toastTimer.restart()
        }

        Timer {
            id: toastTimer
            interval: 2000
            onTriggered: toast.opacity = 0
        }
    }

    // ── Logitech software check on startup ─────────────────────
    Timer {
        interval: 1500; running: true; repeat: false
        onTriggered: {
            if (!backend) return
            var warning = backend.checkLogiSoftware()
            if (warning) {
                logiWarningText.text = warning
                logiWarningBar.visible = true
            }
        }
    }

    Rectangle {
        id: logiWarningBar
        visible: false
        anchors {
            top: parent.top; left: parent.left; right: parent.right
            topMargin: 0
        }
        height: visible ? logiWarningText.implicitHeight + 20 : 0
        color: "#E65100"
        z: 200

        Text {
            id: logiWarningText
            anchors {
                centerIn: parent
                leftMargin: 20; rightMargin: 20
            }
            width: parent.width - 80
            wrapMode: Text.WordWrap
            font { family: root.fontFamily; pixelSize: 12 }
            color: "white"
            horizontalAlignment: Text.AlignHCenter
        }

        Text {
            anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
            text: "✕"
            font.pixelSize: 16; color: "white"
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: logiWarningBar.visible = false
            }
        }
    }

    // ── First-run device selector overlay ─────────────────────
    // Shows briefly on first launch until auto-detection sets the model.
    // Falls back to manual selection if no device is detected.
    Rectangle {
        id: deviceOverlay
        anchors.fill: parent
        z: 10000
        visible: !backend || backend.mouseModel === ""
        color: Qt.rgba(0, 0, 0, 0.7)

        // Eat all clicks so nothing underneath is reachable
        MouseArea { anchors.fill: parent; hoverEnabled: true }

        Rectangle {
            anchors.centerIn: parent
            width: 440
            height: deviceOverlayCol.implicitHeight + 64
            radius: 20
            color: root.theme.bgCard
            border.width: 1
            border.color: root.theme.border

            Column {
                id: deviceOverlayCol
                anchors {
                    left: parent.left; right: parent.right
                    top: parent.top; margins: 32
                }
                spacing: 20

                Text {
                    text: "Welcome to MasterMice"
                    font { family: root.fontFamily; pixelSize: 22; bold: true }
                    color: root.theme.textPrimary
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Text {
                    text: backend && backend.mouseConnected
                          ? "Detecting your mouse..."
                          : "Connect your Logitech mouse, or select manually"
                    font { family: root.fontFamily; pixelSize: 13 }
                    color: root.theme.textSecondary
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                // Spinner shown while connected but not yet detected
                BusyIndicator {
                    visible: backend && backend.mouseConnected
                    anchors.horizontalCenter: parent.horizontalCenter
                    running: visible
                    Material.accent: root.theme.accent
                }

                // Manual fallback selector
                Column {
                    visible: !backend || !backend.mouseConnected
                    spacing: 10
                    anchors.horizontalCenter: parent.horizontalCenter

                    Repeater {
                        model: [
                            { id: "mx_master_3s", label: "MX Master 3/3S",
                              desc: "6 programmable buttons: middle click, gesture button, back, forward, and horizontal scroll wheel." },
                            { id: "mx_master_4",  label: "MX Master 4",
                              desc: "7 programmable buttons: same as 3/3S plus the Actions Ring (haptic touch panel)." }
                        ]

                        delegate: Rectangle {
                            width: 370
                            height: 72
                            radius: 12
                            color: devOverlayMa.containsMouse
                                   ? root.theme.bgCardHover
                                   : root.theme.bgSubtle
                            border.width: 1
                            border.color: devOverlayMa.containsMouse
                                          ? root.theme.accent
                                          : root.theme.border
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Behavior on border.color { ColorAnimation { duration: 120 } }

                            Column {
                                anchors {
                                    left: parent.left; right: parent.right
                                    verticalCenter: parent.verticalCenter
                                    margins: 16
                                }
                                spacing: 4

                                Text {
                                    text: modelData.label
                                    font { family: root.fontFamily; pixelSize: 15; bold: true }
                                    color: root.theme.textPrimary
                                }
                                Text {
                                    text: modelData.desc
                                    font { family: root.fontFamily; pixelSize: 11 }
                                    color: root.theme.textSecondary
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                }
                            }

                            MouseArea {
                                id: devOverlayMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: backend.setMouseModel(modelData.id)
                            }
                        }
                    }
                }
            }
        }
    }

    onClosing: function(close) {
        close.accepted = false
        root.hide()
    }

    Connections {
        target: backend
        function onStatusMessage(msg) { toast.show(msg) }
    }
}
