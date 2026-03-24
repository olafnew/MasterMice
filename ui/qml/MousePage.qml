import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import "Theme.js" as Theme
import "DeviceModels.js" as DeviceModels

/*  Unified Mouse + Profiles page.
    Left panel  — profile list with add/delete.
    Right panel — interactive mouse image with hotspot overlay & action picker.
    Selecting a profile switches which mappings are shown / edited.            */

Item {
    id: mousePage
    readonly property var theme: Theme.palette(uiState ? uiState.darkMode : false)

    // ── Profile state ─────────────────────────────────────────
    property string selectedProfile: backend ? backend.activeProfile : "default"
    property string selectedProfileLabel: ""
    property var    selectedProfileApps: []

    Component.onCompleted: selectProfile(backend ? backend.activeProfile : "default")

    function selectProfile(name) {
        selectedProfile = name
        var profs = backend ? backend.profiles : []
        for (var i = 0; i < profs.length; i++) {
            if (profs[i].name === name) {
                selectedProfileLabel = profs[i].label
                selectedProfileApps  = profs[i].apps
                break
            }
        }
        // Clear hotspot selection when switching profiles
        selectedButton = ""
        selectedButtonName = ""
        selectedActionId = ""
    }

    Connections {
        target: backend
        function onProfilesChanged() {
            // Refresh label/apps if current profile still exists
            var profs = backend.profiles
            for (var i = 0; i < profs.length; i++) {
                if (profs[i].name === selectedProfile) {
                    selectedProfileLabel = profs[i].label
                    selectedProfileApps  = profs[i].apps
                    return
                }
            }
            // Profile deleted — fall back to active
            selectProfile(backend.activeProfile)
        }
        function onActiveProfileChanged() {
            // Auto-select when engine switches profile
            selectProfile(backend.activeProfile)
        }
    }

    // ── Device model ──────────────────────────────────────────
    property var deviceModel: backend ? DeviceModels.get(backend.mouseModel) : null
    onDeviceModelChanged: {
        selectedButton = ""
        selectedButtonName = ""
        selectedActionId = ""
    }

    // ── Button / hotspot state ────────────────────────────────
    property string selectedButton: ""
    property string selectedButtonName: ""
    property string selectedActionId: ""

    function selectButton(key) {
        if (selectedButton === key) {
            selectedButton = ""
            selectedButtonName = ""
            selectedActionId = ""
            return
        }
        var btns = backend.getProfileMappings(selectedProfile)
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].key === key) {
                selectedButton = key
                selectedButtonName = btns[i].name
                selectedActionId = btns[i].actionId
                return
            }
        }
    }

    Connections {
        id: mappingsConn
        target: backend
        function onMappingsChanged() {
            if (selectedButton === "") return
            var btns = backend.getProfileMappings(selectedProfile)
            for (var i = 0; i < btns.length; i++) {
                if (btns[i].key === selectedButton) {
                    selectedActionId = btns[i].actionId
                    break
                }
            }
        }
    }

    function actionFor(key) {
        var btns = backend.getProfileMappings(selectedProfile)
        for (var i = 0; i < btns.length; i++)
            if (btns[i].key === key) return btns[i].actionLabel
        return "Do Nothing"
    }

    function actionFor_id(key) {
        var btns = backend.getProfileMappings(selectedProfile)
        for (var i = 0; i < btns.length; i++)
            if (btns[i].key === key) return btns[i].actionId
        return "none"
    }

    // ── Main two-column layout ────────────────────────────────
    Row {
        anchors.fill: parent
        spacing: 0

        // ══════════════════════════════════════════════════════
        // ── Left panel: profile list ─────────────────────────
        // ══════════════════════════════════════════════════════
        Rectangle {
            id: leftPanel
            width: 220
            height: parent.height
            color: mousePage.theme.bgCard
            border.width: 1; border.color: mousePage.theme.border

            Column {
                anchors.fill: parent
                spacing: 0

                // Title bar
                Item {
                    width: parent.width; height: 52

                    Text {
                        anchors {
                            left: parent.left; leftMargin: 16
                            verticalCenter: parent.verticalCenter
                        }
                        text: "Profiles"
                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 14; bold: true }
                        color: mousePage.theme.textPrimary
                    }
                }

                Rectangle { width: parent.width; height: 1; color: mousePage.theme.border }

                // Profile items
                ListView {
                    id: profileList
                    width: parent.width
                    height: parent.height - 110
                    model: backend ? backend.profiles : []
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds

                    delegate: Rectangle {
                        width: profileList.width
                        height: 58
                        color: selectedProfile === modelData.name
                               ? Qt.rgba(0, 0.83, 0.67, 0.08)
                               : profItemMa.containsMouse
                                 ? Qt.rgba(1, 1, 1, 0.03)
                                 : "transparent"
                        Behavior on color { ColorAnimation { duration: 120 } }

                        Row {
                            anchors {
                                fill: parent
                                leftMargin: 6; rightMargin: 10
                            }
                            spacing: 8

                            // Active indicator
                            Rectangle {
                                width: 3; height: 28; radius: 2
                                color: modelData.isActive
                                       ? mousePage.theme.accent : "transparent"
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            // App icons
                            Row {
                                spacing: -4
                                anchors.verticalCenter: parent.verticalCenter
                                visible: modelData.appIcons !== undefined
                                         && modelData.appIcons.length > 0

                                Repeater {
                                    model: modelData.appIcons
                                    delegate: Image {
                                        source: modelData
                                                ? applicationDirUrl
                                                  + "/images/" + modelData
                                                : ""
                                        width: 24; height: 24
                                        sourceSize { width: 24; height: 24 }
                                        fillMode: Image.PreserveAspectFit
                                        visible: modelData !== ""
                                        smooth: true; mipmap: true
                                        asynchronous: true
                                        cache: true
                                    }
                                }
                            }

                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2

                                Text {
                                    text: modelData.label
                                    font {
                                        family: uiState ? uiState.fontFamily : "Segoe UI"
                                        pixelSize: 12; bold: true
                                    }
                                    color: selectedProfile === modelData.name
                                           ? mousePage.theme.accent : mousePage.theme.textPrimary
                                    elide: Text.ElideRight
                                    width: leftPanel.width - 70
                                }
                                Text {
                                    text: modelData.apps.length
                                          ? modelData.apps.join(", ")
                                          : "All applications"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 9 }
                                    color: mousePage.theme.textSecondary
                                    elide: Text.ElideRight
                                    width: leftPanel.width - 70
                                }
                            }
                        }

                        MouseArea {
                            id: profItemMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: selectProfile(modelData.name)
                        }
                    }
                }

                Rectangle { width: parent.width; height: 1; color: mousePage.theme.border }

                // Add profile controls
                Item {
                    width: parent.width; height: 52

                    RowLayout {
                        anchors {
                            fill: parent
                            leftMargin: 8; rightMargin: 8
                        }
                        spacing: 4

                        ComboBox {
                            id: addCombo
                            Layout.fillWidth: true
                            model: {
                                var apps = backend ? backend.knownApps : []
                                var labels = []
                                for (var i = 0; i < apps.length; i++)
                                    labels.push(apps[i].label)
                                return labels
                            }
                            Material.accent: mousePage.theme.accent
                            font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10 }
                        }

                        Rectangle {
                            width: 42; height: 28; radius: 8
                            color: addBtnMa.containsMouse
                                   ? mousePage.theme.accentHover : mousePage.theme.accent

                            Text {
                                anchors.centerIn: parent
                                text: "+"
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 16; bold: true }
                                color: mousePage.theme.bgSidebar
                            }

                            MouseArea {
                                id: addBtnMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (addCombo.currentText)
                                        backend.addProfile(addCombo.currentText)
                                }
                            }
                        }
                    }
                }
            }
        }

        // ══════════════════════════════════════════════════════
        // ── Right panel: mouse image + hotspots + picker ─────
        // ══════════════════════════════════════════════════════
        Flickable {
            width: parent.width - leftPanel.width
            height: parent.height
            contentWidth: width
            contentHeight: rightCol.implicitHeight + 32
            boundsBehavior: Flickable.StopAtBounds
            clip: true

                Column {
                    id: rightCol
                    width: parent.width
                    spacing: 0

                    // ── Header ────────────────────────────────
                    Item {
                        width: parent.width; height: 70

                        Row {
                            anchors {
                                left: parent.left; leftMargin: 28
                                verticalCenter: parent.verticalCenter
                            }
                            spacing: 12

                            Column {
                                spacing: 3
                                anchors.verticalCenter: parent.verticalCenter

                                Row {
                                    spacing: 8

                                    Text {
                                        text: backend ? backend.mouseModelName : ""
                                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 20; bold: true }
                                        color: mousePage.theme.textPrimary
                                    }

                                    // Profile badge
                                    Rectangle {
                                        visible: selectedProfileLabel !== ""
                                        width: profBadgeText.implicitWidth + 16
                                        height: 22; radius: 11
                                        color: Qt.rgba(0, 0.83, 0.67, 0.12)
                                        anchors.verticalCenter: parent.verticalCenter

                                        Text {
                                            id: profBadgeText
                                            anchors.centerIn: parent
                                            text: selectedProfileLabel
                                            font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                                            color: mousePage.theme.accent
                                        }
                                    }
                                }

                                Text {
                                    text: "Click a dot to configure its action"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12 }
                                    color: mousePage.theme.textSecondary
                                }
                            }
                        }

                        // Right-side status row: delete button + battery + connection
                        Row {
                            anchors {
                                right: parent.right; rightMargin: 28
                                verticalCenter: parent.verticalCenter
                            }
                            spacing: 8

                            // Delete profile button (not for default)
                            Rectangle {
                                visible: selectedProfile !== ""
                                         && selectedProfile !== "default"
                                width: delText.implicitWidth + 20
                                height: 24; radius: 8
                                color: delMa.containsMouse ? "#aa3333" : "#662222"
                                Behavior on color { ColorAnimation { duration: 120 } }
                                anchors.verticalCenter: parent.verticalCenter

                                Text {
                                    id: delText
                                    anchors.centerIn: parent
                                    text: "Delete Profile"
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10; bold: true }
                                    color: mousePage.theme.textPrimary
                                }

                                MouseArea {
                                    id: delMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        backend.deleteProfile(selectedProfile)
                                        selectProfile(backend.activeProfile)
                                    }
                                }
                            }

                            // Battery indicator (Windows-style)
                            Row {
                                visible: backend ? backend.batteryLevel >= 0 : false
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 6

                                // Battery icon body
                                Item {
                                    width: 28; height: 14
                                    anchors.verticalCenter: parent.verticalCenter

                                    // Outer shell
                                    Rectangle {
                                        id: battShell
                                        width: 24; height: 14; radius: 3
                                        color: "transparent"
                                        border.width: 1.5
                                        border.color: {
                                            var lvl = backend ? backend.batteryLevel : -1
                                            if (lvl < 20) return "#e05555"
                                            if (lvl <= 40) return "#e0b840"
                                            return mousePage.theme.textSecondary
                                        }

                                        // Fill bar
                                        Rectangle {
                                            x: 2; y: 2
                                            width: Math.max(1, (parent.width - 4) * Math.min(100, Math.max(0, backend ? backend.batteryLevel : 0)) / 100)
                                            height: parent.height - 4
                                            radius: 1.5
                                            color: {
                                                var lvl = backend ? backend.batteryLevel : 0
                                                var charging = backend ? backend.batteryCharging : false
                                                if (charging) return "#4CAF50"
                                                if (lvl < 20) return "#e05555"
                                                if (lvl <= 40) return "#e0b840"
                                                return mousePage.theme.accent
                                            }
                                        }

                                        // Charging bolt overlay
                                        Text {
                                            anchors.centerIn: parent
                                            text: "\u26A1"
                                            font.pixelSize: 8
                                            color: "#FFFFFF"
                                            visible: backend ? backend.batteryCharging : false
                                        }
                                    }

                                    // Positive terminal nub
                                    Rectangle {
                                        x: 24; y: 4
                                        width: 3; height: 6; radius: 1
                                        color: battShell.border.color
                                    }
                                }

                                // Percentage text
                                Text {
                                    text: {
                                        var lvl = backend ? backend.batteryLevel : -1
                                        var chg = backend ? backend.batteryCharging : false
                                        if (chg && lvl <= 0) return "Chg"
                                        return lvl + "%"
                                    }
                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11; bold: true }
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: {
                                        var lvl = backend ? backend.batteryLevel : -1
                                        var charging = backend ? backend.batteryCharging : false
                                        if (charging) return "#4CAF50"
                                        if (lvl < 20) return "#e05555"
                                        if (lvl <= 40) return "#e0b840"
                                        return mousePage.theme.textSecondary
                                    }
                                }
                            }

                            // Connection type + status badge
                            Row {
                                spacing: 6
                                anchors.verticalCenter: parent.verticalCenter

                                // Connection type icon
                                Rectangle {
                                    visible: backend && backend.mouseConnected
                                    width: connTypeRow.implicitWidth + 12
                                    height: 24; radius: 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: Qt.rgba(0.4, 0.6, 0.9, 0.15)

                                    Row {
                                        id: connTypeRow
                                        anchors.centerIn: parent
                                        spacing: 4

                                        Image {
                                            width: 16; height: 16
                                            anchors.verticalCenter: parent.verticalCenter
                                            source: {
                                                var ct = backend ? backend.connectionType : ""
                                                if (ct === "bluetooth") return applicationDirUrl + "/images/icons/bluetooth.png"
                                                if (ct === "bolt") return applicationDirUrl + "/images/icons/bolt.png"
                                                return applicationDirUrl + "/images/icons/unifying.png"
                                            }
                                            sourceSize: Qt.size(16, 16)
                                            fillMode: Image.PreserveAspectFit
                                            smooth: true
                                        }
                                        Text {
                                            text: {
                                                var ct = backend ? backend.connectionType : "unknown"
                                                if (ct === "bluetooth") return "Bluetooth"
                                                if (ct === "bolt") return "Bolt"
                                                if (ct === "unifying") return "Unifying"
                                                return ""
                                            }
                                            font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10 }
                                            color: mousePage.theme.textSecondary
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                    }
                                }

                                // Connection status badge
                                Rectangle {
                                    width: statusRow.implicitWidth + 16
                                    height: 24; radius: 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: backend && backend.mouseConnected
                                           ? Qt.rgba(0, 0.83, 0.67, 0.12)
                                           : Qt.rgba(0.9, 0.3, 0.3, 0.15)

                                    Row {
                                        id: statusRow
                                        anchors.centerIn: parent
                                        spacing: 5

                                        Rectangle {
                                            width: 7; height: 7; radius: 4
                                            color: backend && backend.mouseConnected
                                                   ? mousePage.theme.accent : "#e05555"
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                        Text {
                                            text: backend && backend.mouseConnected
                                                  ? "Connected" : "Not Connected"
                                            font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                                            color: backend && backend.mouseConnected
                                                   ? mousePage.theme.accent : "#e05555"
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        width: parent.width - 56; height: 1
                        color: mousePage.theme.border
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    // ── Mouse image with hotspots ─────────────
                    Item {
                        id: mouseImageArea
                        width: parent.width
                        // Fill remaining viewport height below header (70) + separator (1)
                        height: Math.max(400, mousePage.height - 71)

                        // Image centered in the viewport left of labels
                        Image {
                            id: mouseImg
                            source: mousePage.deviceModel
                                    ? "image://mouseimage/" + encodeURIComponent(mousePage.deviceModel.image)
                                      + "?dark=" + (uiState ? uiState.darkMode : false ? "true" : "false")
                                    : ""
                            cache: false
                            fillMode: Image.PreserveAspectFit
                            width: Math.min(440, mouseImageArea.width - 230)
                            height: Math.min(400, mouseImageArea.height - 40)
                            x: (mouseImageArea.width - 210 - width) / 2
                            y: (mouseImageArea.height - height) / 2
                            smooth: true
                            mipmap: true
                            asynchronous: true

                            property real offX: (width - paintedWidth) / 2
                            property real offY: (height - paintedHeight) / 2
                        }

                        // Missing-image fallback
                        Rectangle {
                            x: (mouseImageArea.width - 210 - width) / 2
                            y: (mouseImageArea.height - height) / 2
                            width: 220; height: 64; radius: 10
                            color: Qt.rgba(0.9, 0.3, 0.3, 0.08)
                            visible: mouseImg.status === Image.Error
                            Text {
                                anchors.centerIn: parent
                                text: "Mouse image not available"
                                font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 13 }
                                color: mousePage.theme.textSecondary
                            }
                        }

                        // Hotspot dots + labels
                        Repeater {
                            id: hotspotRepeater
                            model: mousePage.deviceModel ? mousePage.deviceModel.hotspots : []
                            delegate: HotspotDot {
                                anchors.fill: mouseImageArea
                                imgItem:   mouseImg
                                normX:     modelData.normX
                                normY:     modelData.normY
                                buttonKey: modelData.buttonKey
                                label:     modelData.label
                                sublabel:  modelData.placeholder
                                           ? "Not yet supported"
                                           : actionFor(modelData.buttonKey)
                                isHScroll: false
                                // Fixed 10px gap between 48px labels, centered vertically
                                targetLabelFraction: {
                                    var labelH = 48
                                    var gap = 10
                                    var n = hotspotRepeater.count
                                    var totalH = n * labelH + (n - 1) * gap
                                    var startY = (mouseImageArea.height - totalH) / 2
                                    return (startY + index * (labelH + gap) + labelH / 2) / mouseImageArea.height
                                }
                            }
                        }
                    }

                    Item { width: 1; height: 24 }
                }

                // ── Action picker overlay ────────────────
                // Positioned over the mouse image, inside the Flickable
                // but OUTSIDE the Column (so it can float with z-order)
                Rectangle {
                    id: pickerOverlay
                    visible: selectedButton !== ""
                    z: 100
                    x: 20
                    y: 80
                    width: Math.min(parent.width - 250, 600)
                    height: visible ? Math.min(pickerScrollContent.implicitHeight + 40,
                                               mousePage.height - 120) : 0
                    radius: 14
                    color: mousePage.theme.bgCard
                    border.width: 1
                    border.color: mousePage.theme.accent

                        Flickable {
                            id: pickerFlick
                            anchors {
                                fill: parent
                                margins: 20
                            }
                            contentHeight: pickerScrollContent.implicitHeight
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds

                            Column {
                                id: pickerScrollContent
                                width: pickerFlick.width
                                spacing: 14

                                // Title row
                                Row {
                                    spacing: 10
                                    width: parent.width

                                    Rectangle {
                                        width: 5; height: pickerTitleCol.height
                                        radius: 3; color: mousePage.theme.accent
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    Column {
                                        id: pickerTitleCol
                                        spacing: 2
                                        width: parent.width - 50

                                        Text {
                                            text: selectedButtonName
                                                  ? selectedButtonName + " — Choose Action"
                                                  : ""
                                            font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 15; bold: true }
                                            color: mousePage.theme.textPrimary
                                        }
                                        Text {
                                            text: "Select what happens when you use this button"
                                            font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 11 }
                                            color: mousePage.theme.textSecondary
                                        }
                                    }

                                    // Close button
                                    Rectangle {
                                        width: 28; height: 28; radius: 14
                                        color: closeMa.containsMouse ? mousePage.theme.bgSubtle : "transparent"
                                        anchors.verticalCenter: parent.verticalCenter
                                        Text {
                                            anchors.centerIn: parent
                                            text: "\u2715"
                                            font.pixelSize: 14
                                            color: mousePage.theme.textSecondary
                                        }
                                        MouseArea {
                                            id: closeMa
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                selectedButton = ""
                                                selectedButtonName = ""
                                                selectedActionId = ""
                                            }
                                        }
                                    }
                                }

                                // Action categories
                                Repeater {
                                    model: backend ? backend.actionCategories : []
                                    delegate: Column {
                                        width: parent.width
                                        spacing: 6

                                        Text {
                                            text: modelData.category
                                            font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10;
                                                   capitalization: Font.AllUppercase;
                                                   letterSpacing: 1 }
                                            color: mousePage.theme.textDim
                                        }

                                        Flow {
                                            width: parent.width; spacing: 6
                                            Repeater {
                                                model: modelData.actions
                                                delegate: ActionChip {
                                                    actionId: modelData.id
                                                    actionLabel: modelData.label
                                                    isCurrent: modelData.id === selectedActionId
                                                    onPicked: function(aid) {
                                                        backend.setProfileMapping(
                                                            selectedProfile,
                                                            selectedButton, aid)
                                                        selectedActionId = aid
                                                        backend.statusMessage("Saved")
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }

                                // ── Sensitivity presets (only for haptic_panel) ──
                                Column {
                                    width: parent.width
                                    spacing: 6
                                    visible: selectedButton === "haptic_panel" && backend && backend.mouseConnected

                                    Rectangle {
                                        width: parent.width; height: 1
                                        color: mousePage.theme.border
                                        opacity: 0.5
                                    }

                                    Text {
                                        text: "CLICK SENSITIVITY"
                                        font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 10
                                               capitalization: Font.AllUppercase
                                               letterSpacing: 1 }
                                        color: mousePage.theme.textDim
                                    }

                                    property string currentSens: backend ? backend.getButtonSensitivity() : "unknown"

                                    Flow {
                                        width: parent.width; spacing: 6
                                        Repeater {
                                            model: [
                                                { label: "Light", value: "light" },
                                                { label: "Medium", value: "medium" },
                                                { label: "Hard", value: "hard" },
                                                { label: "Firm", value: "firm" }
                                            ]
                                            delegate: Rectangle {
                                                required property var modelData
                                                property bool active: parent.parent.parent.currentSens === modelData.value
                                                width: sensLbl.implicitWidth + 20; height: 32; radius: 8
                                                color: active ? mousePage.theme.accent
                                                       : sensMa.containsMouse ? mousePage.theme.bgCardHover
                                                       : mousePage.theme.bgSubtle
                                                border.width: 1
                                                border.color: active ? mousePage.theme.accent : mousePage.theme.border
                                                Behavior on color { ColorAnimation { duration: 120 } }
                                                Text {
                                                    id: sensLbl
                                                    anchors.centerIn: parent
                                                    text: modelData.label
                                                    font { family: uiState ? uiState.fontFamily : "Segoe UI"; pixelSize: 12; bold: active }
                                                    color: active ? "#000" : mousePage.theme.textPrimary
                                                }
                                                MouseArea {
                                                    id: sensMa
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: {
                                                        backend.setButtonSensitivity(modelData.value)
                                                        parent.parent.parent.parent.currentSens = modelData.value
                                                        backend.statusMessage("Saved")
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
        }
    }

