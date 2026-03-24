import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import "Theme.js" as Theme

Item {
    id: scrollPage
    readonly property var theme: Theme.palette(uiState ? uiState.darkMode : false)

    Flickable {
        id: pageScroll
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: mainCol.implicitHeight + 32
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: mainCol
            width: pageScroll.width
            spacing: 0

            Item {
                width: parent.width
                height: 96

                Column {
                    anchors {
                        left: parent.left
                        leftMargin: 36
                        verticalCenter: parent.verticalCenter
                    }
                    spacing: 4

                    Text {
                        text: "Point & Scroll"
                        font {
                            family: uiState ? uiState.fontFamily : "Segoe UI"
                            pixelSize: 24
                            bold: true
                        }
                        color: scrollPage.theme.textPrimary
                    }

                    Text {
                        text: "Adjust pointer speed and scroll behaviour"
                        font {
                            family: uiState ? uiState.fontFamily : "Segoe UI"
                            pixelSize: 13
                        }
                        color: scrollPage.theme.textSecondary
                    }
                }
            }

            Rectangle {
                width: parent.width - 72
                height: 1
                color: scrollPage.theme.border
                anchors.horizontalCenter: parent.horizontalCenter
            }

            Item { width: 1; height: 24 }

            // ── Pointer Speed card (DPI + Windows Cursor Speed) ────
            Rectangle {
                id: dpiCard
                width: parent.width - 72
                anchors.horizontalCenter: parent.horizontalCenter
                height: pointerSpeedCol.implicitHeight + 40
                radius: Theme.radius
                color: scrollPage.theme.bgCard
                border.width: 1
                border.color: scrollPage.theme.border

                Column {
                    id: pointerSpeedCol
                    anchors {
                        left: parent.left; right: parent.right
                        top: parent.top; margins: 20
                    }
                    spacing: 12

                    Text {
                        text: "Pointer Speed"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 18; bold: true }
                        color: scrollPage.theme.textPrimary
                    }
                    Text {
                        text: "Sensor DPI and Windows cursor speed"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12 }
                        color: scrollPage.theme.textSecondary
                    }

                    // ── DPI sub-block ──
                    Rectangle {
                        width: parent.width; height: dpiSubCol.implicitHeight + 20; radius: 10
                        color: scrollPage.theme.bgSubtle

                        Column {
                            id: dpiSubCol
                            anchors {
                                left: parent.left; right: parent.right; top: parent.top
                                leftMargin: 16; rightMargin: 16; topMargin: 10
                            }
                            spacing: 8

                            Text {
                                text: "DPI (Sensor Speed)"
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: true }
                                color: scrollPage.theme.textPrimary
                            }
                            Text {
                                text: "Higher = faster tracking. Step: 50 DPI."
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10 }
                                color: scrollPage.theme.textDim
                            }

                            RowLayout {
                                width: parent.width
                                spacing: 10
                                Text {
                                    text: "200"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                                    color: scrollPage.theme.textDim
                                }
                                Slider {
                                    id: dpiSlider
                                    Layout.fillWidth: true
                                    from: 200
                                    to: backend ? backend.maxDpi : 4000
                                    stepSize: 50
                                    value: backend ? backend.dpi : 1000
                                    Material.accent: scrollPage.theme.accent
                                    onMoved: { dpiLabel.text = Math.round(value) + " DPI"; dpiDebounce.restart() }
                                    onPressedChanged: { if (!pressed) { dpiDebounce.stop(); dpiLabel.text = Math.round(value) + " DPI"; backend.setDpi(Math.round(value)) } }
                                }
                                Text {
                                    text: backend ? backend.maxDpi : "4000"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                                    color: scrollPage.theme.textDim
                                }
                                Rectangle {
                                    width: 90; height: 32; radius: 8
                                    color: scrollPage.theme.accentDim
                                    Text {
                                        id: dpiLabel
                                        anchors.centerIn: parent
                                        text: (backend ? backend.dpi : 1000) + " DPI"
                                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: true }
                                        color: scrollPage.theme.accent
                                    }
                                }
                            }

                            Timer { id: dpiDebounce; interval: 400; onTriggered: { backend.setDpi(Math.round(dpiSlider.value)); backend.statusMessage("Saved") } }

                            Flow {
                                width: parent.width
                                spacing: 8
                                Text {
                                    text: "Presets:"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                                    color: scrollPage.theme.textDim
                                }
                                Repeater {
                                    model: [400, 800, 1000, 1600, 2400, 4000, 6000, 8000]
                                    delegate: Rectangle {
                                        visible: modelData <= (backend ? backend.maxDpi : 8000)
                                        width: visible ? pText.implicitWidth + 20 : 0
                                        height: visible ? 28 : 0
                                        radius: 8
                                        color: dpiSlider.value === modelData ? scrollPage.theme.accent : pMa.containsMouse ? scrollPage.theme.bgCardHover : scrollPage.theme.bgSubtle
                                        border.width: 1
                                        border.color: scrollPage.theme.border
                                        Behavior on color { ColorAnimation { duration: 120 } }
                                        Text {
                                            id: pText
                                            anchors.centerIn: parent
                                            text: modelData
                                            font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12 }
                                            color: dpiSlider.value === modelData ? scrollPage.theme.bgSidebar : scrollPage.theme.textPrimary
                                        }
                                        MouseArea {
                                            id: pMa
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: { dpiSlider.value = modelData; dpiLabel.text = modelData + " DPI"; backend.setDpi(modelData) }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ── Windows Cursor Speed sub-block ──
                    Rectangle {
                        width: parent.width
                        height: winSpeedSubCol.implicitHeight + 20
                        radius: 10
                        color: scrollPage.theme.bgSubtle

                        Column {
                            id: winSpeedSubCol
                            anchors {
                                left: parent.left; right: parent.right; top: parent.top
                                leftMargin: 16; rightMargin: 16; topMargin: 10
                            }
                            spacing: 6

                            Text {
                                text: "Windows Cursor Speed"
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: true }
                                color: scrollPage.theme.textPrimary
                            }
                            Text {
                                text: "System-wide pointer speed (1-20). Affects all mice."
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10 }
                                color: scrollPage.theme.textDim
                            }
                            Row {
                                width: parent.width
                                spacing: 10
                                Text {
                                    text: "1"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                                    color: scrollPage.theme.textDim
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Slider {
                                    id: mouseSpeedSlider
                                    width: parent.width - 90
                                    from: 1; to: 20; stepSize: 1
                                    value: backend ? backend.mouseSpeed : 10
                                    Material.accent: scrollPage.theme.accent
                                    anchors.verticalCenter: parent.verticalCenter
                                    onPressedChanged: { if (!pressed) backend.setMouseSpeed(Math.round(value)) }
                                }
                                Text {
                                    text: "20"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                                    color: scrollPage.theme.textDim
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Rectangle {
                                    width: 42; height: 28; radius: 6
                                    color: scrollPage.theme.accent
                                    anchors.verticalCenter: parent.verticalCenter
                                    Text {
                                        anchors.centerIn: parent
                                        text: Math.round(mouseSpeedSlider.value)
                                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12; bold: true }
                                        color: scrollPage.theme.bgSidebar
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item { width: 1; height: 16 }

            // ── Scroll Wheel card ─────────────────────────
            Rectangle {
                width: parent.width - 72
                anchors.horizontalCenter: parent.horizontalCenter
                height: wheelContent.implicitHeight + 40
                radius: Theme.radius
                color: scrollPage.theme.bgCard
                border.width: 1
                border.color: scrollPage.theme.border

                Column {
                    id: wheelContent
                    anchors {
                        left: parent.left; right: parent.right
                        top: parent.top; margins: 20
                    }
                    spacing: 12

                    Text {
                        text: "Scroll Wheel"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 16; bold: true }
                        color: scrollPage.theme.textPrimary
                    }

                    Text {
                        text: "SmartShift and scroll settings (applied directly to the device)"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12 }
                        color: scrollPage.theme.textSecondary
                    }

                    // Scrolling force (MX4 SmartShift v2 only)
                    Rectangle {
                        visible: backend && backend.mouseConnected ? backend.getSmartShiftVersion() === 2 : false
                        width: parent.width; height: visible ? 62 : 0; radius: 10
                        color: scrollPage.theme.bgSubtle

                        RowLayout {
                            anchors {
                                fill: parent
                                leftMargin: 16; rightMargin: 16
                            }

                            Column {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: "Scrolling Force"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13 }
                                    color: scrollPage.theme.textPrimary
                                }
                            }

                            Slider {
                                id: forceSlider
                                Layout.preferredWidth: 180
                                from: 1; to: 100; stepSize: 1
                                value: 50
                                Material.accent: scrollPage.theme.accent
                                Component.onCompleted: {
                                    var v = backend ? backend.getScrollForce() : -1
                                    if (v > 0) value = v
                                }
                                onMoved: forceDebounce.restart()
                            }

                            Text {
                                text: Math.round(forceSlider.value) + "%"
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: true }
                                color: scrollPage.theme.accent
                                Layout.preferredWidth: 40
                            }

                            Timer {
                                id: forceDebounce
                                interval: 400
                                onTriggered: backend.setScrollForce(Math.round(forceSlider.value))
                            }
                        }
                    }

                    // Smooth scrolling toggle
                    Rectangle {
                        visible: backend && backend.mouseConnected ? backend.hasSmoothScrolling() : false
                        width: parent.width; height: visible ? 62 : 0; radius: 10
                        color: scrollPage.theme.bgSubtle

                        RowLayout {
                            anchors {
                                fill: parent
                                leftMargin: 16; rightMargin: 16
                            }

                            Column {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: "Smooth Scrolling"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13 }
                                    color: scrollPage.theme.textPrimary
                                }
                                Text {
                                    text: "Web pages glide across your screen smoothly"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10 }
                                    color: scrollPage.theme.textDim
                                }
                            }

                            Switch {
                                id: smoothSwitch
                                Material.accent: scrollPage.theme.accent
                                Component.onCompleted: {
                                    checked = backend ? backend.getSmoothScrolling() : false
                                }
                                onToggled: { backend.setSmoothScrolling(checked); backend.statusMessage("Saved") }
                            }
                        }
                    }

                    // SmartShift toggle + sensitivity
                    Rectangle {
                        width: parent.width; height: ssCol.implicitHeight + 20; radius: 10
                        color: scrollPage.theme.bgSubtle

                        Column {
                            id: ssCol
                            anchors {
                                left: parent.left; right: parent.right
                                top: parent.top
                                leftMargin: 16; rightMargin: 16; topMargin: 10
                            }
                            spacing: 8

                            RowLayout {
                                width: parent.width

                                Column {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text {
                                        text: "SmartShift"
                                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13 }
                                        color: scrollPage.theme.textPrimary
                                    }
                                    Text {
                                        text: "Automatically switches to hyper-fast scrolling when you scroll faster"
                                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10 }
                                        color: scrollPage.theme.textDim
                                        width: parent.width
                                        wrapMode: Text.WordWrap
                                    }
                                }

                                Switch {
                                    id: ssEnabledSwitch
                                    Material.accent: scrollPage.theme.accent
                                    Component.onCompleted: {
                                        checked = backend ? backend.getSmartShiftEnabled() : true
                                    }
                                    onToggled: { backend.setSmartShiftEnabled(checked); backend.statusMessage("Saved") }
                                }
                            }

                            // Sensitivity slider (visible when SmartShift is on)
                            RowLayout {
                                visible: ssEnabledSwitch.checked
                                width: parent.width
                                spacing: 8

                                Text {
                                    text: "Sensitivity"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12 }
                                    color: scrollPage.theme.textDim
                                }

                                Slider {
                                    id: ssSlider
                                    Layout.fillWidth: true
                                    from: 1; to: 50; stepSize: 1
                                    value: 10
                                    Material.accent: scrollPage.theme.accent
                                    Component.onCompleted: {
                                        var v = backend ? backend.getSmartShiftThreshold() : -1
                                        if (v > 0) value = v
                                    }
                                    onMoved: ssDebounce.restart()
                                }

                                Text {
                                    text: Math.round(ssSlider.value / 50 * 100) + "%"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: true }
                                    color: scrollPage.theme.accent
                                    Layout.preferredWidth: 40
                                }

                                Timer {
                                    id: ssDebounce
                                    interval: 400
                                    onTriggered: backend.setSmartShiftThreshold(Math.round(ssSlider.value))
                                }
                            }
                        }
                    }

                    // Hi-Res scroll toggle (MX3/3S only — hidden on MX4)
                    Rectangle {
                        visible: backend && backend.mouseConnected ? backend.hasHiResWheel() : false
                        width: parent.width; height: visible ? 52 : 0; radius: 10
                        color: scrollPage.theme.bgSubtle

                        RowLayout {
                            anchors {
                                fill: parent
                                leftMargin: 16; rightMargin: 16
                            }

                            Column {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: "Hi-Res Scrolling"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13 }
                                    color: scrollPage.theme.textPrimary
                                }
                                Text {
                                    text: "Smoother, higher-resolution scroll. Use the speed slider below to tune."
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10 }
                                    color: scrollPage.theme.textDim
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                }
                            }

                            Switch {
                                id: hiresSwitch
                                Material.accent: scrollPage.theme.accent
                                Component.onCompleted: {
                                    checked = backend ? backend.getHiResScroll() : false
                                }
                                onToggled: { backend.setHiResScroll(checked); backend.statusMessage("Saved") }
                            }
                        }
                    }

                    // Hi-Res scroll speed slider (visible only when HiRes is ON)
                    Rectangle {
                        visible: hiresSwitch.checked
                        width: parent.width; height: visible ? hiresSpeedCol.implicitHeight + 20 : 0; radius: 10
                        color: scrollPage.theme.bgSubtle

                        Column {
                            id: hiresSpeedCol
                            anchors {
                                left: parent.left; right: parent.right; top: parent.top
                                leftMargin: 16; rightMargin: 16; topMargin: 10
                            }
                            spacing: 6

                            Text {
                                text: "Hi-Res Scroll Speed"
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: true }
                                color: scrollPage.theme.textPrimary
                            }
                            Text {
                                text: "Scales the high-resolution scroll events. Default (15) = normal speed."
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10 }
                                color: scrollPage.theme.textDim
                            }

                            Row {
                                width: parent.width; spacing: 8
                                Text {
                                    text: "Slower"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10 }
                                    color: scrollPage.theme.textDim
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Slider {
                                    id: hiresSpeedSlider
                                    width: parent.width - 130
                                    from: 1; to: 30; stepSize: 1
                                    value: backend ? backend.hiResScrollDivider : 15
                                    Material.accent: scrollPage.theme.accent
                                    anchors.verticalCenter: parent.verticalCenter
                                    onPressedChanged: {
                                        if (!pressed) backend.setHiResScrollDivider(Math.round(value))
                                    }
                                }
                                Text {
                                    text: "Faster"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10 }
                                    color: scrollPage.theme.textDim
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Rectangle {
                                    width: 36; height: 26; radius: 6; color: scrollPage.theme.accent; anchors.verticalCenter: parent.verticalCenter
                                    Text {
                                        anchors.centerIn: parent
                                        text: Math.round(hiresSpeedSlider.value)
                                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11; bold: true }
                                        color: scrollPage.theme.bgSidebar
                                    }
                                }
                            }
                        }
                    }

                    // Scroll speed slider (Windows scroll lines)
                    Rectangle {
                        width: parent.width; height: scrollSpeedCol.implicitHeight + 20; radius: 10
                        color: scrollPage.theme.bgSubtle

                        Column {
                            id: scrollSpeedCol
                            anchors {
                                left: parent.left; right: parent.right
                                top: parent.top
                                leftMargin: 16; rightMargin: 16; topMargin: 10
                            }
                            spacing: 6

                            Text {
                                text: "Scroll Speed (Lines per notch)"
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13 }
                                color: scrollPage.theme.textPrimary
                            }
                            Text {
                                text: "System-wide setting. Lower values = slower scroll."
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10 }
                                color: scrollPage.theme.textDim
                            }

                            Row {
                                width: parent.width
                                spacing: 10

                                Text {
                                    text: "1"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                                    color: scrollPage.theme.textDim
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Slider {
                                    id: scrollSpeedSlider
                                    width: parent.width - 90
                                    from: 1; to: 20; stepSize: 1
                                    value: backend ? backend.scrollLines : 3
                                    Material.accent: scrollPage.theme.accent
                                    anchors.verticalCenter: parent.verticalCenter
                                    onPressedChanged: {
                                        if (!pressed) {
                                            backend.setScrollLines(Math.round(value))
                                        }
                                    }
                                }
                                Text {
                                    text: "20"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                                    color: scrollPage.theme.textDim
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Rectangle {
                                    width: 36; height: 26; radius: 6
                                    color: scrollPage.theme.accent
                                    anchors.verticalCenter: parent.verticalCenter
                                    Text {
                                        anchors.centerIn: parent
                                        text: Math.round(scrollSpeedSlider.value)
                                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12; bold: true }
                                        color: scrollPage.theme.bgSidebar
                                    }
                                }
                            }
                        }
                    }

                    // ── Scroll Direction sub-block (moved inside Scroll Wheel) ──
                    Rectangle {
                        width: parent.width
                        height: scrollDirCol.implicitHeight + 20
                        radius: 10
                        color: scrollPage.theme.bgSubtle

                        Column {
                            id: scrollDirCol
                            anchors {
                                left: parent.left; right: parent.right; top: parent.top
                                leftMargin: 16; rightMargin: 16; topMargin: 10
                            }
                            spacing: 6

                            Text {
                                text: "Scroll Direction"
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: true }
                                color: scrollPage.theme.textPrimary
                            }

                            RowLayout {
                                width: parent.width
                                Text {
                                    text: "Invert vertical scroll"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12 }
                                    color: scrollPage.theme.textPrimary
                                    Layout.fillWidth: true
                                }
                                Switch {
                                    id: vscrollSwitch
                                    checked: backend ? backend.invertVScroll : false
                                    Material.accent: scrollPage.theme.accent
                                    onToggled: {
                                        backend.setInvertVScroll(checked)
                                        backend.statusMessage("Saved")
                                    }
                                }
                            }

                            RowLayout {
                                width: parent.width
                                Text {
                                    text: "Invert horizontal scroll"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12 }
                                    color: scrollPage.theme.textPrimary
                                    Layout.fillWidth: true
                                }
                                Switch {
                                    id: hscrollSwitch
                                    checked: backend ? backend.invertHScroll : false
                                    Material.accent: scrollPage.theme.accent
                                    onToggled: {
                                        backend.setInvertHScroll(checked)
                                        backend.statusMessage("Saved")
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item { width: 1; height: 16 }

            // ── Haptic Feedback card (MX4 only) ──────────────
            Rectangle {
                visible: backend && backend.mouseConnected ? backend.hasHapticFeedback() : false
                width: parent.width - 72
                anchors.horizontalCenter: parent.horizontalCenter
                height: hapticContent.implicitHeight + 40
                radius: Theme.radius
                color: scrollPage.theme.bgCard
                border.width: 1
                border.color: scrollPage.theme.border

                Column {
                    id: hapticContent
                    anchors {
                        left: parent.left; right: parent.right
                        top: parent.top; margins: 20
                    }
                    spacing: 12

                    Text {
                        text: "Haptic Feedback"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 16; bold: true }
                        color: scrollPage.theme.textPrimary
                    }

                    Text {
                        text: "Tactile vibration feedback from the Actions Ring and scroll wheel"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12 }
                        color: scrollPage.theme.textSecondary
                    }

                    // Haptic on/off toggle
                    Rectangle {
                        width: parent.width; height: 52; radius: 10
                        color: scrollPage.theme.bgSubtle

                        RowLayout {
                            anchors {
                                fill: parent
                                leftMargin: 16; rightMargin: 16
                            }

                            Text {
                                text: "Enable Haptics"
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13 }
                                color: scrollPage.theme.textPrimary
                                Layout.fillWidth: true
                            }

                            Switch {
                                id: hapticSwitch
                                Material.accent: scrollPage.theme.accent
                                Component.onCompleted: {
                                    checked = backend ? backend.getHapticEnabled() : false
                                }
                                onToggled: { backend.setHapticEnabled(checked); backend.statusMessage("Saved") }
                            }
                        }
                    }

                    // Haptic intensity slider (visible when enabled)
                    Rectangle {
                        visible: hapticSwitch.checked
                        width: parent.width; height: visible ? 62 : 0; radius: 10
                        color: scrollPage.theme.bgSubtle

                        RowLayout {
                            anchors {
                                fill: parent
                                leftMargin: 16; rightMargin: 16
                            }

                            Column {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: "Intensity"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13 }
                                    color: scrollPage.theme.textPrimary
                                }
                            }

                            Slider {
                                id: hapticSlider
                                Layout.preferredWidth: 180
                                from: 1; to: 100; stepSize: 1
                                value: 60
                                Material.accent: scrollPage.theme.accent
                                Component.onCompleted: {
                                    var v = backend ? backend.getHapticIntensity() : 60
                                    if (v > 0) value = v
                                }
                                onMoved: hapticDebounce.restart()
                            }

                            Text {
                                text: Math.round(hapticSlider.value) + "%"
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: true }
                                color: scrollPage.theme.accent
                                Layout.preferredWidth: 40
                            }

                            Timer {
                                id: hapticDebounce
                                interval: 400
                                onTriggered: backend.setHapticIntensity(Math.round(hapticSlider.value))
                            }
                        }
                    }

                    // ── Pulse Pattern Test Grid ──
                    Text {
                        text: "Test Pulses"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: true }
                        color: scrollPage.theme.textPrimary
                    }
                    Text {
                        text: "Tap a button to feel the haptic pattern"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                        color: scrollPage.theme.textSecondary
                    }
                    // Row 1: Single pulses
                    Row {
                        spacing: 8
                        Repeater {
                            model: [
                                { label: "Nudge",  code: 0x01 },
                                { label: "Light",  code: 0x02 },
                                { label: "Tick",   code: 0x04 },
                                { label: "Strong", code: 0x08 }
                            ]
                            delegate: Rectangle {
                                required property var modelData
                                width: 90; height: 36; radius: 8
                                color: hapBtnMa1.containsMouse ? scrollPage.theme.accentDim : scrollPage.theme.bgSubtle
                                border.width: 1
                                border.color: scrollPage.theme.accent
                                Behavior on color { ColorAnimation { duration: 120 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12; bold: true }
                                    color: scrollPage.theme.accent
                                }
                                MouseArea {
                                    id: hapBtnMa1
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.testHapticPulse(modelData.code)
                                }
                            }
                        }
                    }
                    // Row 2: Combo pulses
                    Row {
                        spacing: 8
                        Repeater {
                            model: [
                                { label: "Buzz",      code: 0x06 },
                                { label: "Burst",     code: 0x0A },
                                { label: "Triple",    code: 0x0C },
                                { label: "Dbl Buzz",  code: 0x0E }
                            ]
                            delegate: Rectangle {
                                required property var modelData
                                width: 90; height: 36; radius: 8
                                color: hapBtnMa2.containsMouse ? scrollPage.theme.accentDim : scrollPage.theme.bgSubtle
                                border.width: 1
                                border.color: scrollPage.theme.border
                                Behavior on color { ColorAnimation { duration: 120 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12 }
                                    color: scrollPage.theme.textPrimary
                                }
                                MouseArea {
                                    id: hapBtnMa2
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.testHapticPulse(modelData.code)
                                }
                            }
                        }
                    }
                    // ── Custom Mix (bit toggle) ──
                    Item { width: parent.width; height: 12 }
                    Rectangle { width: parent.width; height: 1; color: scrollPage.theme.border; opacity: 0.3 }
                    Item { width: parent.width; height: 8 }

                    Text {
                        text: "Custom Mix"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: true }
                        color: scrollPage.theme.textPrimary
                    }
                    Text {
                        text: "Toggle bits to create a custom pulse — then hit Play"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                        color: scrollPage.theme.textSecondary
                    }

                    property int mixBits: 0
                    Row {
                        spacing: 8
                        Repeater {
                            model: [
                                { label: "Nudge",  bit: 0x01 },
                                { label: "Light",  bit: 0x02 },
                                { label: "Tick",   bit: 0x04 },
                                { label: "Strong", bit: 0x08 }
                            ]
                            delegate: Rectangle {
                                required property var modelData
                                property bool active: (hapticContent.mixBits & modelData.bit) !== 0
                                width: 80; height: 34; radius: 8
                                color: active ? scrollPage.theme.accent : (mixMa.containsMouse ? scrollPage.theme.bgSubtle : "transparent")
                                border.width: 1
                                border.color: active ? scrollPage.theme.accent : scrollPage.theme.border
                                Behavior on color { ColorAnimation { duration: 150 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12; bold: active }
                                    color: active ? "#000" : scrollPage.theme.textSecondary
                                }
                                MouseArea {
                                    id: mixMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: hapticContent.mixBits = hapticContent.mixBits ^ modelData.bit
                                }
                            }
                        }
                        // Play button
                        Rectangle {
                            width: 70; height: 34; radius: 8
                            color: hapticContent.mixBits > 0 ? (playMixMa.containsMouse ? Qt.lighter(scrollPage.theme.accent, 1.2) : scrollPage.theme.accent) : scrollPage.theme.bgSubtle
                            opacity: hapticContent.mixBits > 0 ? 1.0 : 0.4
                            Text {
                                anchors.centerIn: parent
                                text: "Play"
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12; bold: true }
                                color: hapticContent.mixBits > 0 ? "#000" : scrollPage.theme.textSecondary
                            }
                            MouseArea {
                                id: playMixMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: hapticContent.mixBits > 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: {
                                    if (hapticContent.mixBits > 0)
                                        backend.testHapticPulse(hapticContent.mixBits)
                                }
                            }
                        }
                        // Show hex code
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: hapticContent.mixBits > 0 ? "0x" + hapticContent.mixBits.toString(16).toUpperCase().padStart(2, "0") : ""
                            font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                            color: scrollPage.theme.textSecondary
                        }
                    }

                    // ── Sequence Builder ──
                    Item { width: parent.width; height: 12 }
                    Rectangle { width: parent.width; height: 1; color: scrollPage.theme.border; opacity: 0.3 }
                    Item { width: parent.width; height: 8 }

                    Text {
                        text: "Sequence Builder"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: true }
                        color: scrollPage.theme.textPrimary
                    }
                    Text {
                        text: "Chain pulses with delays to create custom patterns"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                        color: scrollPage.theme.textSecondary
                    }

                    // Preset sequences
                    Row {
                        spacing: 8
                        Repeater {
                            model: [
                                { label: "Heartbeat", seq: '{"steps":[{"pulse":8,"delay":80},{"pulse":4,"delay":300},{"pulse":8,"delay":80},{"pulse":4,"delay":600}], "repeat":3}' },
                                { label: "Alert",     seq: '{"steps":[{"pulse":4,"delay":60},{"pulse":4,"delay":60},{"pulse":4,"delay":200}], "repeat":3}' },
                                { label: "Buzz 0.5s", seq: '{"steps":[{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25},{"pulse":2,"delay":25}], "repeat":1}' },
                                { label: "SOS",       seq: '{"steps":[{"pulse":2,"delay":100},{"pulse":2,"delay":100},{"pulse":2,"delay":250},{"pulse":8,"delay":100},{"pulse":8,"delay":100},{"pulse":8,"delay":250},{"pulse":2,"delay":100},{"pulse":2,"delay":100},{"pulse":2,"delay":0}], "repeat":1}' },
                                { label: "Ramp Up",   seq: '{"steps":[{"pulse":1,"delay":80},{"pulse":2,"delay":80},{"pulse":4,"delay":80},{"pulse":8,"delay":80},{"pulse":12,"delay":0}], "repeat":1}' }
                            ]
                            delegate: Rectangle {
                                required property var modelData
                                width: seqLabel.implicitWidth + 20; height: 32; radius: 8
                                color: seqMa.containsMouse ? scrollPage.theme.accentDim : scrollPage.theme.bgSubtle
                                border.width: 1
                                border.color: scrollPage.theme.border
                                Behavior on color { ColorAnimation { duration: 120 } }
                                Text {
                                    id: seqLabel
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                                    color: scrollPage.theme.textPrimary
                                }
                                MouseArea {
                                    id: seqMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.playHapticSequence(modelData.seq)
                                }
                            }
                        }
                    }
                }
            }

            Item { width: 1; height: 16 }

            // ── Button Sensitivity card (MX4 only) ─────────────
            Rectangle {
                visible: backend && backend.mouseConnected ? backend.hasButtonSensitivity() : false
                width: parent.width - 72
                anchors.horizontalCenter: parent.horizontalCenter
                height: btnSensContent.implicitHeight + 40
                radius: Theme.radius
                color: scrollPage.theme.bgCard
                border.width: 1
                border.color: scrollPage.theme.border

                Column {
                    id: btnSensContent
                    anchors {
                        left: parent.left; right: parent.right
                        top: parent.top; margins: 20
                    }
                    spacing: 12

                    Text {
                        text: "Haptic Sense Panel"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 16; bold: true }
                        color: scrollPage.theme.textPrimary
                    }
                    Text {
                        text: "Adjust click sensitivity for the haptic sense panel (MX Master 4)"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12 }
                        color: scrollPage.theme.textSecondary
                    }

                    property string currentPreset: backend && backend.mouseConnected ? backend.getButtonSensitivity() : "unknown"

                    Row {
                        spacing: 10
                        Repeater {
                            model: [
                                { label: "Light", value: "light" },
                                { label: "Medium", value: "medium" },
                                { label: "Hard", value: "hard" },
                                { label: "Firm", value: "firm" }
                            ]
                            delegate: Rectangle {
                                required property var modelData
                                property bool active: btnSensContent.currentPreset === modelData.value
                                width: 90; height: 38; radius: 8
                                color: active ? scrollPage.theme.accent : (bsMa.containsMouse ? scrollPage.theme.bgSubtle : "transparent")
                                border.width: 1
                                border.color: active ? scrollPage.theme.accent : scrollPage.theme.border
                                Behavior on color { ColorAnimation { duration: 150 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13; bold: active }
                                    color: active ? "#000" : scrollPage.theme.textPrimary
                                }
                                MouseArea {
                                    id: bsMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        backend.setButtonSensitivity(modelData.value)
                                        btnSensContent.currentPreset = modelData.value
                                        backend.statusMessage("Saved")
                                    }
                                }
                            }
                        }
                    }

                    // ── Click test area ──
                    Rectangle {
                        width: parent.width; height: 56; radius: 10
                        color: sensTestMa.pressed ? scrollPage.theme.accent : scrollPage.theme.bgSubtle
                        border.width: 2
                        border.color: sensTestMa.pressed ? scrollPage.theme.accent : scrollPage.theme.border
                        Behavior on color { ColorAnimation { duration: 60 } }

                        Row {
                            anchors.centerIn: parent
                            spacing: 10
                            Rectangle {
                                width: 16; height: 16; radius: 8
                                anchors.verticalCenter: parent.verticalCenter
                                color: sensTestMa.pressed ? "#000" : scrollPage.theme.border
                                scale: sensTestMa.pressed ? 1.4 : 1.0
                                Behavior on scale { NumberAnimation { duration: 60 } }
                                Behavior on color { ColorAnimation { duration: 60 } }
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: sensTestMa.pressed ? "Click detected!" : "Click anywhere here to test sensitivity"
                                font {
                                    family: uiState ? uiState.fontFamily : "Segoe UI"
                                    pixelSize: 13
                                    bold: sensTestMa.pressed
                                }
                                color: sensTestMa.pressed ? "#000" : scrollPage.theme.textSecondary
                            }
                        }

                        MouseArea {
                            id: sensTestMa
                            anchors.fill: parent
                            acceptedButtons: Qt.AllButtons
                        }
                    }
                }
            }

            Item { width: 1; height: 16 }

            Rectangle {
                width: parent.width - 72
                anchors.horizontalCenter: parent.horizontalCenter
                height: noteRow.implicitHeight + 28
                radius: Theme.radius
                color: scrollPage.theme.bgCard
                border.width: 1
                border.color: scrollPage.theme.border

                Row {
                    id: noteRow
                    anchors {
                        fill: parent
                        margins: 14
                    }
                    spacing: 10

                    AppIcon {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 18
                        height: 18
                        name: "warning"
                        iconColor: scrollPage.theme.warning
                    }

                    Text {
                        width: parent.width - 28
                        text: "All settings require HID++ communication and will take effect after a short delay."
                        font {
                            family: uiState ? uiState.fontFamily : "Segoe UI"
                            pixelSize: 12
                        }
                        color: scrollPage.theme.textDim
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Item { width: 1; height: 24 }
        }
    }

    Connections {
        target: backend
        function onDpiFromDevice(dpi) {
            if (!dpiSlider.pressed) {
                dpiSlider.value = dpi
                dpiLabel.text = dpi + " DPI"
            }
        }
        function onSettingsChanged() {
            if (!dpiSlider.pressed) {
                dpiSlider.to = backend.maxDpi
                dpiSlider.value = backend.dpi
                dpiLabel.text = backend.dpi + " DPI"
            }
            vscrollSwitch.checked = backend.invertVScroll
            hscrollSwitch.checked = backend.invertHScroll
        }
        function onMouseConnectedChanged() {
            if (!backend.mouseConnected) return
            // Refresh all device-dependent control values
            var ss = backend.getSmartShiftThreshold()
            if (ss > 0) ssSlider.value = ss
            ssEnabledSwitch.checked = backend.getSmartShiftEnabled()
            var f = backend.getScrollForce()
            if (f > 0) forceSlider.value = f
            smoothSwitch.checked = backend.getSmoothScrolling()
            hiresSwitch.checked = backend.getHiResScroll()
            hapticSwitch.checked = backend.getHapticEnabled()
            var hi = backend.getHapticIntensity()
            if (hi > 0) hapticSlider.value = hi
        }
    }
}
