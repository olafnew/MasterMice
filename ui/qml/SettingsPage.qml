import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import "Theme.js" as Theme

Item {
    id: settingsPage
    readonly property var theme: Theme.palette(uiState.darkMode)
    property bool diagRunning: false

    Timer {
        id: diagTimer
        interval: 50  // let UI repaint before blocking call
        repeat: false
        onTriggered: {
            var result = backend.runDiagnostics()
            logViewer.text = result + "\n\n" + backend.refreshLogContent()
            diagRunning = false
            diagLabel.text = "Run Diagnostics"
        }
    }

    Flickable {
        id: settingsScroll
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: settingsCol.implicitHeight + 32
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: settingsCol
            width: settingsScroll.width
            spacing: 0

            // ── Header ─────────────────────────────────────────
            Item {
                width: parent.width; height: 96

                Column {
                    anchors {
                        left: parent.left; leftMargin: 36
                        verticalCenter: parent.verticalCenter
                    }
                    spacing: 4

                    Row {
                        spacing: 10
                        Text {
                            text: "Settings"
                            font { family: uiState.fontFamily; pixelSize: 24; bold: true }
                            color: settingsPage.theme.textPrimary
                        }
                        Rectangle {
                            width: verText.implicitWidth + 12
                            height: 20; radius: 10
                            color: settingsPage.theme.accentDim
                            anchors.verticalCenter: parent.verticalCenter
                            Text {
                                id: verText
                                anchors.centerIn: parent
                                text: "v" + (backend ? backend.appVersion : "")
                                font { family: uiState.fontFamily; pixelSize: 11 }
                                color: settingsPage.theme.accent
                            }
                        }
                    }
                    Text {
                        text: "Configure MasterMice preferences"
                        font { family: uiState.fontFamily; pixelSize: 13 }
                        color: settingsPage.theme.textSecondary
                    }
                }
            }

            Rectangle {
                width: parent.width - 72; height: 1
                color: settingsPage.theme.border
                anchors.horizontalCenter: parent.horizontalCenter
            }

            Item { width: 1; height: 24 }

            // ── Mouse type card ────────────────────────────────
            Rectangle {
                width: parent.width - 72
                anchors.horizontalCenter: parent.horizontalCenter
                height: mouseTypeContent.implicitHeight + 40
                radius: Theme.radius
                color: settingsPage.theme.bgCard
                border.width: 1
                border.color: settingsPage.theme.border

                Column {
                    id: mouseTypeContent
                    anchors {
                        left: parent.left; right: parent.right
                        top: parent.top; margins: 20
                    }
                    spacing: 12

                    Text {
                        text: "Mouse Type"
                        font { family: uiState.fontFamily; pixelSize: 16; bold: true }
                        color: settingsPage.theme.textPrimary
                    }

                    Text {
                        text: "Select which Logitech mouse you are using"
                        font { family: uiState.fontFamily; pixelSize: 12 }
                        color: settingsPage.theme.textSecondary
                    }

                    Row {
                        spacing: 8

                        Repeater {
                            model: [
                                { id: "mx_master_3s", label: "MX Master 3/3S" },
                                { id: "mx_master_4",  label: "MX Master 4"  }
                            ]

                            delegate: Rectangle {
                                width: mtLabel.implicitWidth + 24
                                height: 34; radius: 8
                                color: backend && backend.mouseModel === modelData.id
                                       ? settingsPage.theme.accent
                                       : mtMa.containsMouse
                                         ? settingsPage.theme.bgCardHover
                                         : settingsPage.theme.bgSubtle
                                border.width: 1
                                border.color: settingsPage.theme.border
                                Behavior on color { ColorAnimation { duration: 120 } }

                                Text {
                                    id: mtLabel
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    font { family: uiState.fontFamily; pixelSize: 13 }
                                    color: backend && backend.mouseModel === modelData.id
                                           ? settingsPage.theme.bgSidebar
                                           : settingsPage.theme.textPrimary
                                }

                                MouseArea {
                                    id: mtMa
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

            Item { width: 1; height: 16 }

            // ── Appearance mode card ───────────────────────────
            Rectangle {
                width: parent.width - 72
                anchors.horizontalCenter: parent.horizontalCenter
                height: appearanceContent.implicitHeight + 40
                radius: Theme.radius
                color: settingsPage.theme.bgCard
                border.width: 1
                border.color: settingsPage.theme.border

                Column {
                    id: appearanceContent
                    anchors {
                        left: parent.left; right: parent.right
                        top: parent.top; margins: 20
                    }
                    spacing: 12

                    Text {
                        text: "Appearance"
                        font { family: uiState.fontFamily; pixelSize: 16; bold: true }
                        color: settingsPage.theme.textPrimary
                    }

                    Text {
                        text: "Choose light or dark mode for the interface"
                        font { family: uiState.fontFamily; pixelSize: 12 }
                        color: settingsPage.theme.textSecondary
                    }

                    Row {
                        spacing: 8

                        Repeater {
                            model: [
                                { id: "system", label: "System" },
                                { id: "light",  label: "Light"  },
                                { id: "dark",   label: "Dark"   }
                            ]

                            delegate: Rectangle {
                                width: amLabel.implicitWidth + 24
                                height: 34; radius: 8
                                color: uiState.appearanceMode === modelData.id
                                       ? settingsPage.theme.accent
                                       : amMa.containsMouse
                                         ? settingsPage.theme.bgCardHover
                                         : settingsPage.theme.bgSubtle
                                border.width: 1
                                border.color: settingsPage.theme.border
                                Behavior on color { ColorAnimation { duration: 120 } }

                                Text {
                                    id: amLabel
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    font { family: uiState.fontFamily; pixelSize: 13 }
                                    color: uiState.appearanceMode === modelData.id
                                           ? settingsPage.theme.bgSidebar
                                           : settingsPage.theme.textPrimary
                                }

                                MouseArea {
                                    id: amMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: uiState.appearanceMode = modelData.id
                                }
                            }
                        }
                    }
                }
            }

            Item { width: 1; height: 16 }

            // ── Run on startup card (greyed out) ───────────────
            Rectangle {
                width: parent.width - 72
                anchors.horizontalCenter: parent.horizontalCenter
                height: startupContent.implicitHeight + 40
                radius: Theme.radius
                color: settingsPage.theme.bgCard
                border.width: 1
                border.color: settingsPage.theme.border
                opacity: 0.5

                Column {
                    id: startupContent
                    anchors {
                        left: parent.left; right: parent.right
                        top: parent.top; margins: 20
                    }
                    spacing: 12

                    Row {
                        spacing: 8

                        Text {
                            text: "Run on Startup"
                            font { family: uiState.fontFamily; pixelSize: 16; bold: true }
                            color: settingsPage.theme.textPrimary
                        }

                        Rectangle {
                            width: csText.implicitWidth + 12
                            height: 18; radius: 9
                            color: settingsPage.theme.border
                            anchors.verticalCenter: parent.verticalCenter

                            Text {
                                id: csText
                                anchors.centerIn: parent
                                text: "Coming soon"
                                font { family: uiState.fontFamily; pixelSize: 9 }
                                color: settingsPage.theme.textDim
                            }
                        }
                    }

                    Text {
                        text: "Launch MasterMice automatically as a background service when Windows starts"
                        font { family: uiState.fontFamily; pixelSize: 12 }
                        color: settingsPage.theme.textSecondary
                    }

                    Rectangle {
                        width: parent.width; height: 52; radius: 10
                        color: settingsPage.theme.bgSubtle

                        RowLayout {
                            anchors {
                                fill: parent
                                leftMargin: 16; rightMargin: 16
                            }

                            Text {
                                text: "Start as Windows service"
                                font { family: uiState.fontFamily; pixelSize: 13 }
                                color: settingsPage.theme.textDim
                                Layout.fillWidth: true
                            }

                            Switch {
                                enabled: false
                                Material.accent: settingsPage.theme.accent
                            }
                        }
                    }
                }
            }

            Item { width: 1; height: 16 }

            // ── Logging card ───────────────────────────────────
            Rectangle {
                width: parent.width - 72
                anchors.horizontalCenter: parent.horizontalCenter
                height: logContent.implicitHeight + 40
                radius: Theme.radius
                color: settingsPage.theme.bgCard
                border.width: 1
                border.color: settingsPage.theme.border

                Column {
                    id: logContent
                    anchors {
                        left: parent.left; right: parent.right
                        top: parent.top; margins: 20
                    }
                    spacing: 12

                    Text {
                        text: "Logging"
                        font { family: uiState.fontFamily; pixelSize: 16; bold: true }
                        color: settingsPage.theme.textPrimary
                    }

                    Text {
                        text: "Control log verbosity and view application logs"
                        font { family: uiState.fontFamily; pixelSize: 12 }
                        color: settingsPage.theme.textSecondary
                    }

                    Row {
                        spacing: 8

                        Repeater {
                            model: [
                                { id: "disabled", label: "Disabled" },
                                { id: "errors",   label: "Errors Only" },
                                { id: "verbose",  label: "Verbose" }
                            ]

                            delegate: Rectangle {
                                width: llLabel.implicitWidth + 24
                                height: 34; radius: 8
                                color: backend && backend.logLevel === modelData.id
                                       ? settingsPage.theme.accent
                                       : llMa.containsMouse
                                         ? settingsPage.theme.bgCardHover
                                         : settingsPage.theme.bgSubtle
                                border.width: 1
                                border.color: settingsPage.theme.border
                                Behavior on color { ColorAnimation { duration: 120 } }

                                Text {
                                    id: llLabel
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    font { family: uiState.fontFamily; pixelSize: 13 }
                                    color: backend && backend.logLevel === modelData.id
                                           ? settingsPage.theme.bgSidebar
                                           : settingsPage.theme.textPrimary
                                }

                                MouseArea {
                                    id: llMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.setLogLevel(modelData.id)
                                }
                            }
                        }
                    }

                    // Max file size
                    Row {
                        spacing: 12
                        width: parent.width

                        Text {
                            text: "Max log size:"
                            font { family: uiState.fontFamily; pixelSize: 13 }
                            color: settingsPage.theme.textPrimary
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Slider {
                            id: logSizeSlider
                            width: 200
                            from: 64; to: 4096; stepSize: 64
                            value: backend ? backend.logMaxKb : 1024
                            Material.accent: settingsPage.theme.accent
                            onMoved: logSizeDebounce.restart()
                        }

                        Text {
                            text: Math.round(logSizeSlider.value) + " KB"
                            font { family: uiState.fontFamily; pixelSize: 13; bold: true }
                            color: settingsPage.theme.accent
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Timer {
                            id: logSizeDebounce
                            interval: 500
                            onTriggered: backend.setLogMaxKb(Math.round(logSizeSlider.value))
                        }
                    }

                    // Progress bar (visible during diagnostics)
                    ProgressBar {
                        width: parent.width
                        indeterminate: true
                        visible: diagRunning
                        height: diagRunning ? 4 : 0
                        Material.accent: settingsPage.theme.accent
                    }

                    // Log viewer
                    Rectangle {
                        width: parent.width
                        height: 220
                        radius: 8
                        color: settingsPage.theme.bgSubtle
                        border.width: 1
                        border.color: settingsPage.theme.border
                        clip: true

                        ScrollView {
                            anchors.fill: parent
                            anchors.margins: 8

                            TextArea {
                                id: logViewer
                                readOnly: true
                                wrapMode: TextEdit.WrapAnywhere
                                text: backend ? backend.refreshLogContent() : ""
                                font.family: "Consolas"
                                font.pixelSize: 11
                                color: settingsPage.theme.textSecondary
                                background: null
                                Component.onCompleted: text = backend ? backend.refreshLogContent() : ""
                            }
                        }
                    }

                    // Action buttons row
                    Row {
                        spacing: 8

                        Rectangle {
                            width: diagLabel.implicitWidth + 24
                            height: 34; radius: 8
                            color: diagMa.containsMouse
                                   ? settingsPage.theme.accent
                                   : settingsPage.theme.accentDim
                            border.width: 1
                            border.color: settingsPage.theme.accent

                            Text {
                                id: diagLabel
                                anchors.centerIn: parent
                                text: "Run Diagnostics"
                                font { family: uiState.fontFamily; pixelSize: 13; bold: true }
                                color: diagMa.containsMouse
                                       ? settingsPage.theme.bgSidebar
                                       : settingsPage.theme.accent
                            }

                            MouseArea {
                                id: diagMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    diagRunning = true
                                    diagLabel.text = "Running..."
                                    // Use a timer to let the UI update before blocking call
                                    diagTimer.start()
                                }
                            }
                        }

                        Rectangle {
                            width: clearLabel.implicitWidth + 24
                            height: 34; radius: 8
                            color: clearMa.containsMouse
                                   ? settingsPage.theme.bgCardHover
                                   : settingsPage.theme.bgSubtle
                            border.width: 1
                            border.color: settingsPage.theme.border

                            Text {
                                id: clearLabel
                                anchors.centerIn: parent
                                text: "Clear Log"
                                font { family: uiState.fontFamily; pixelSize: 13 }
                                color: settingsPage.theme.textPrimary
                            }

                            MouseArea {
                                id: clearMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    backend.clearLog()
                                    logViewer.text = "(log cleared)"
                                }
                            }
                        }

                        Rectangle {
                            width: refreshLabel.implicitWidth + 24
                            height: 34; radius: 8
                            color: refreshMa.containsMouse
                                   ? settingsPage.theme.bgCardHover
                                   : settingsPage.theme.bgSubtle
                            border.width: 1
                            border.color: settingsPage.theme.border

                            Text {
                                id: refreshLabel
                                anchors.centerIn: parent
                                text: "Refresh Log"
                                font { family: uiState.fontFamily; pixelSize: 13 }
                                color: settingsPage.theme.textPrimary
                            }

                            MouseArea {
                                id: refreshMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: logViewer.text = backend.refreshLogContent()
                            }
                        }

                        Rectangle {
                            width: openLabel.implicitWidth + 24
                            height: 34; radius: 8
                            color: openMa.containsMouse
                                   ? settingsPage.theme.bgCardHover
                                   : settingsPage.theme.bgSubtle
                            border.width: 1
                            border.color: settingsPage.theme.border

                            Text {
                                id: openLabel
                                anchors.centerIn: parent
                                text: "Open in Explorer"
                                font { family: uiState.fontFamily; pixelSize: 13 }
                                color: settingsPage.theme.textPrimary
                            }

                            MouseArea {
                                id: openMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: backend.openLogInExplorer()
                            }
                        }
                    }
                }
            }

            Item { width: 1; height: 24 }
        }
    }
}
