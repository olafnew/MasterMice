import QtQuick
import "Theme.js" as Theme

/*  A single clickable hotspot dot placed over the mouse image.
    Position is given as normalised coordinates (0-1) within the
    source image, so it adapts when the image is scaled.

    Label is positioned via targetLabelFraction (0-1 of container
    height) for evenly-spaced right-aligned callouts.              */

Item {
    id: hotspot
    opacity: isDimmed ? 0.3 : 1.0
    Behavior on opacity { NumberAnimation { duration: 200 } }
    readonly property var theme: Theme.palette(uiState.darkMode)

    // ── Properties ───────────────────────────────────────────
    property Item imgItem                 // the Image element
    property real normX: 0               // 0-1 x in source image
    property real normY: 0               // 0-1 y in source image
    property string buttonKey: ""        // config key (e.g. "middle")
    property bool isHScroll: false

    property string label: ""
    property string sublabel: ""
    property string labelSide: "right"
    property real labelOffX: 120
    property real labelOffY: -30

    // Fraction-based label Y (0-1 of container height for label center).
    // When >= 0, overrides labelOffX/labelOffY and right-aligns the label.
    property real targetLabelFraction: -1

    // ── Computed centre ───────────────────────────────────────
    property real cx: imgItem ? imgItem.x + imgItem.offX + normX * imgItem.paintedWidth : 0
    property real cy: imgItem ? imgItem.y + imgItem.offY + normY * imgItem.paintedHeight : 0

    property bool isSelected: mousePage.selectedButton === buttonKey
    property bool isDimmed: mousePage.selectedButton !== "" && !isSelected
    property bool isHovered: dotMa.containsMouse

    // ── Label geometry ───────────────────────────────────────
    property real labelWidth: 190
    property real labelHeight: 48

    property real labelX: {
        if (targetLabelFraction >= 0)
            return width - labelWidth - 16
        return Math.max(8, Math.min(width - labelWidth - 8, cx + labelOffX + 6))
    }
    property real labelY: {
        if (targetLabelFraction >= 0) {
            var raw = targetLabelFraction * height - labelHeight / 2
            return Math.max(4, Math.min(height - labelHeight - 4, raw))
        }
        return Math.max(8, Math.min(height - labelHeight - 8, cy + labelOffY - 8))
    }

    property real lineEndX: labelX + 2
    property real lineEndY: labelY + labelHeight / 2

    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: label

    function triggerSelection() {
        mousePage.selectButton(buttonKey)
    }

    Keys.onReturnPressed: triggerSelection()
    Keys.onEnterPressed: triggerSelection()
    Keys.onSpacePressed: triggerSelection()

    // ── Glow ring ─────────────────────────────────────────────
    Rectangle {
        id: glow
        x: cx - width / 2
        y: cy - height / 2
        width: 30; height: 30; radius: 15
        color: "transparent"
        border.width: isSelected || hotspot.activeFocus ? 2 : 1
        border.color: isSelected || hotspot.activeFocus
                      ? theme.accent
                      : Qt.rgba(0, 0.83, 0.67, 0.3)
        opacity: isSelected || isHovered || hotspot.activeFocus ? 1 : 0.6

        Behavior on opacity { NumberAnimation { duration: 200 } }
        Behavior on border.width { NumberAnimation { duration: 150 } }

        SequentialAnimation on scale {
            loops: Animation.Infinite
            running: isSelected
            NumberAnimation { from: 1.0; to: 1.25; duration: 800; easing.type: Easing.InOutQuad }
            NumberAnimation { from: 1.25; to: 1.0; duration: 800; easing.type: Easing.InOutQuad }
        }
    }

    // ── Dot ───────────────────────────────────────────────────
    Rectangle {
        id: dot
        x: cx - width / 2
        y: cy - height / 2
        width: 16; height: 16; radius: 8
        color: isSelected ? theme.accentHover : theme.accent
        border.width: 2
        border.color: hotspot.activeFocus ? theme.textPrimary : Qt.rgba(0, 0, 0, 0.3)

        scale: isHovered ? 1.2 : 1.0
        Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutQuad } }
        Behavior on color { ColorAnimation { duration: 150 } }
    }

    // ── Click area ───────────────────────────────────────────
    MouseArea {
        id: dotMa
        x: cx - 18
        y: cy - 18
        width: 36; height: 36
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: hotspot.triggerSelection()
    }

    // ── Connecting line ───────────────────────────────────────
    Canvas {
        id: lineCanvas
        anchors.fill: parent
        z: 0
        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.strokeStyle = isSelected ? theme.accent : Qt.rgba(0, 0.83, 0.67, 0.35)
            ctx.lineWidth = 1
            ctx.setLineDash([4, 3])
            ctx.beginPath()
            ctx.moveTo(cx, cy)
            ctx.lineTo(lineEndX, lineEndY)
            ctx.stroke()
        }

        Connections {
            target: hotspot
            function onCxChanged() { lineCanvas.requestPaint() }
            function onCyChanged() { lineCanvas.requestPaint() }
            function onIsSelectedChanged() { lineCanvas.requestPaint() }
            function onLabelXChanged() { lineCanvas.requestPaint() }
            function onLabelYChanged() { lineCanvas.requestPaint() }
        }
        Component.onCompleted: requestPaint()
    }

    // ── Annotation label ──────────────────────────────────────
    Rectangle {
        id: labelBg
        z: 2
        x: labelX
        y: labelY
        width: labelWidth
        height: labelHeight
        radius: 10
        color: isSelected
               ? (uiState.darkMode
                  ? Qt.rgba(0, 0.83, 0.67, 0.18)
                  : Qt.rgba(0.82, 0.97, 0.93, 0.9))
               : uiState.darkMode ? "#1e293b" : Qt.rgba(1, 1, 1, 0.92)
        border.width: 1
        border.color: uiState.darkMode ? "#334155" : Qt.rgba(0, 0.83, 0.67, 0.3)

        Behavior on color { ColorAnimation { duration: 200 } }

        Item {
            id: labelCol
            anchors.centerIn: parent
            width: 166
            height: titleText.height + (sublabelText.visible ? sublabelText.height + 2 : 0)

            Text {
                id: titleText
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top
                text: hotspot.label
                font { family: uiState.fontFamily; pixelSize: 13; bold: true }
                color: isSelected ? theme.accent : theme.textPrimary
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }

            Text {
                id: sublabelText
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: titleText.bottom
                anchors.topMargin: 2
                text: hotspot.sublabel
                font { family: uiState.fontFamily; pixelSize: 11 }
                color: theme.textSecondary
                visible: text !== ""
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: hotspot.triggerSelection()
        }
    }

    // ── Small dot at the line endpoint ────────────────────────
    Rectangle {
        z: 1
        x: lineEndX - 3
        y: lineEndY - 3
        width: 6; height: 6; radius: 3
        color: isSelected ? theme.accent : Qt.rgba(0, 0.83, 0.67, 0.5)
    }
}
