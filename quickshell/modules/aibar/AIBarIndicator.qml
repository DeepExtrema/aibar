import qs.modules.common
import qs.modules.common.widgets
import qs.modules.ii.bar
import qs.services
import QtQuick
import QtQuick.Layouts

Item {
    id: root
    required property string toolLetter
    required property double quotaUsed
    required property string status
    property bool toolActive: false
    property double costToday: 0
    property string accentColor: ""
    property var primaryWindow: null
    property int warningThreshold: 70
    property bool shown: true
    clip: true
    visible: width > 0 && height > 0
    implicitWidth: indicatorRow.x < 0 ? 0 : indicatorRow.implicitWidth
    implicitHeight: Appearance.sizes.barHeight

    property double remainingPercent: {
        if (primaryWindow && primaryWindow.usedPercent !== undefined)
            return Math.max(0, 100 - primaryWindow.usedPercent)
        return Math.max(0, (1 - quotaUsed) * 100)
    }
    property bool warning: (100 - remainingPercent) >= warningThreshold

    property color barColor: {
        if (status === "limited") return Appearance.colors.colError
        if (warning) return Appearance.colors.colError
        if (accentColor !== "") return accentColor
        return Appearance.colors.colPrimary
    }

    RowLayout {
        id: indicatorRow
        spacing: 4
        x: shown ? 0 : -indicatorRow.width
        anchors.verticalCenter: parent.verticalCenter

        StyledText {
            text: toolLetter
            font.weight: Font.DemiBold
            font.pixelSize: Appearance.font.pixelSize.smaller
            color: root.barColor
            Layout.alignment: Qt.AlignVCenter
        }

        Item {
            Layout.alignment: Qt.AlignVCenter
            implicitWidth: 50
            implicitHeight: 6

            Rectangle {
                id: track
                anchors.fill: parent
                radius: height / 2
                color: Appearance.m3colors.m3surfaceContainerHigh ?? "#2b2a2a"
            }

            Rectangle {
                id: fill
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width * Math.min(1, Math.max(0, root.remainingPercent / 100))
                height: parent.height
                radius: height / 2
                color: root.barColor

                Behavior on width {
                    NumberAnimation {
                        duration: Appearance.animation.elementMove.duration
                        easing.type: Appearance.animation.elementMove.type
                        easing.bezierCurve: Appearance.animation.elementMove.bezierCurve
                    }
                }
            }
        }

        StyledText {
            text: Math.round(root.remainingPercent) + "%"
            font.pixelSize: Appearance.font.pixelSize.smaller
            color: Appearance.colors.colOnLayer1
            Layout.alignment: Qt.AlignVCenter
        }

        Behavior on x {
            animation: Appearance.animation.elementMove.numberAnimation.createObject(this)
        }
    }

    Behavior on implicitWidth {
        NumberAnimation {
            duration: Appearance.animation.elementMove.duration
            easing.type: Appearance.animation.elementMove.type
            easing.bezierCurve: Appearance.animation.elementMove.bezierCurve
        }
    }
}
