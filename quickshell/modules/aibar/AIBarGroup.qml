import qs.modules.common
import qs.modules.common.widgets
import qs.modules.ii.bar
import qs.services
import QtQuick
import QtQuick.Layouts

MouseArea {
    id: root
    implicitWidth: rowLayout.implicitWidth + rowLayout.anchors.leftMargin + rowLayout.anchors.rightMargin
    implicitHeight: Appearance.sizes.barHeight
    hoverEnabled: !Config.options.bar.tooltips.clickToShow
    onDoubleClicked: AIBar.refresh()

    RowLayout {
        id: rowLayout
        spacing: 4
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8

        AIBarIndicator {
            toolLetter: "AI"
            quotaUsed: 1 - (AIBar.avgRemainingPercent / 100)
            status: AIBar.worstStatus()
        }
    }

    AIBarPopup {
        hoverTarget: root
    }
}
