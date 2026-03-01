import qs.modules.common
import qs.modules.common.widgets
import qs.modules.ii.bar
import qs.services
import QtQuick
import QtQuick.Layouts

StyledPopup {
    id: root

    function statusColor(status, accentColor) {
        if (status === "limited") return Appearance.colors.colError
        if (status === "warning") return "#FFA500"
        if (accentColor) return accentColor
        return Appearance.colors.colPrimary
    }

    function formatTokens(n) {
        if (n >= 1000000) return (n / 1000000).toFixed(1) + "M"
        if (n >= 1000) return (n / 1000).toFixed(1) + "K"
        return n.toString()
    }


    ColumnLayout {
        anchors.centerIn: parent
        spacing: 4
        implicitWidth: 280

        StyledPopupHeaderRow {
            icon: "smart_toy"
            label: "AI Tools"
        }

        Repeater {
            model: AIBar.toolIds

            ColumnLayout {
                required property string modelData
                required property int index
                property var tool: AIBar.getTool(modelData)
                property string toolStatus: tool?.status ?? "inactive"
                property string accent: tool?.color ?? ""
                spacing: 6
                Layout.fillWidth: true

                // Divider before each tool except the first
                Rectangle {
                    visible: index > 0
                    Layout.fillWidth: true
                    height: 1
                    color: Appearance.colors.colSurfaceBright ?? Appearance.m3colors.m3outlineVariant ?? "#3a3a3a"
                    Layout.topMargin: 4
                    Layout.bottomMargin: 4
                }

                // Header: status dot + name + running badge
                RowLayout {
                    spacing: 8
                    Layout.fillWidth: true

                    Rectangle {
                        width: 8
                        height: 8
                        radius: 4
                        color: root.statusColor(toolStatus, accent)
                    }

                    StyledText {
                        text: tool?.name ?? modelData
                        font.pixelSize: Appearance.font.pixelSize.normal
                        font.weight: Font.DemiBold
                        color: Appearance.colors.colOnSurface
                    }

                    Item { Layout.fillWidth: true }

                    StyledText {
                        visible: tool?.active ?? false
                        text: "running"
                        font.pixelSize: Appearance.font.pixelSize.smaller
                        color: root.statusColor(toolStatus, accent)
                    }
                }

                // Plan info
                StyledText {
                    visible: (tool?.plan ?? "") !== ""
                    text: "Plan: " + (tool?.plan ?? "")
                    font.pixelSize: Appearance.font.pixelSize.smaller
                    color: Appearance.colors.colOnSurfaceVariant
                    Layout.leftMargin: 16
                }

                // All rate windows — full progress bar for each
                // Uses rateWindows array (Claude API) or builds from primary/secondary (Codex)
                Repeater {
                    id: windowsRepeater
                    model: {
                        const rw = tool?.rateWindows
                        if (rw && rw.length > 0) return rw
                        // Build array from legacy primary/secondary
                        let legacy = []
                        if (tool?.primary) legacy.push(tool.primary)
                        if (tool?.secondary) legacy.push(tool.secondary)
                        return legacy.length > 0 ? legacy : []
                    }

                    ColumnLayout {
                        required property var modelData
                        spacing: 2
                        Layout.fillWidth: true
                        Layout.leftMargin: 16

                        RowLayout {
                            Layout.fillWidth: true
                            StyledText {
                                text: modelData.label ?? "Usage"
                                font.pixelSize: Appearance.font.pixelSize.smaller
                                color: Appearance.colors.colOnSurfaceVariant
                            }
                            Item { Layout.fillWidth: true }
                            StyledText {
                                text: Math.round(modelData.usedPercent ?? 0) + "% used"
                                font.pixelSize: Appearance.font.pixelSize.smaller
                                font.weight: Font.DemiBold
                                color: {
                                    const used = modelData.usedPercent ?? 0
                                    if (used >= 100) return Appearance.colors.colError
                                    if (used >= 70) return "#FFA500"
                                    return Appearance.colors.colOnSurface
                                }
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                            implicitHeight: 6

                            Rectangle {
                                anchors.fill: parent
                                radius: height / 2
                                color: Appearance.m3colors.m3surfaceContainerHigh ?? "#2b2a2a"
                            }
                            Rectangle {
                                anchors.left: parent.left
                                width: parent.width * Math.min(1, Math.max(0, (modelData.usedPercent ?? 0) / 100))
                                height: parent.height
                                radius: height / 2
                                color: root.statusColor(toolStatus, accent)
                            }
                        }

                        StyledText {
                            text: AIBar.formatResetTime(modelData.resetsAt ?? "")
                            visible: text !== ""
                            font.pixelSize: Appearance.font.pixelSize.smaller
                            color: Appearance.colors.colOnSurfaceVariant
                        }
                    }
                }

                // Fallback: simple quota bar when no rate windows present
                ColumnLayout {
                    visible: (tool?.rateWindows ?? []).length === 0 && !tool?.primary && (tool?.quotaUsed ?? 0) > 0
                    spacing: 2
                    Layout.fillWidth: true
                    Layout.leftMargin: 16

                    RowLayout {
                        Layout.fillWidth: true
                        StyledText {
                            text: "Quota"
                            font.pixelSize: Appearance.font.pixelSize.smaller
                            color: Appearance.colors.colOnSurfaceVariant
                        }
                        Item { Layout.fillWidth: true }
                        StyledText {
                            text: Math.round((tool?.quotaUsed ?? 0) * 100) + "% used"
                            font.pixelSize: Appearance.font.pixelSize.smaller
                            font.weight: Font.DemiBold
                            color: Appearance.colors.colOnSurface
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        implicitHeight: 6

                        Rectangle {
                            anchors.fill: parent
                            radius: height / 2
                            color: Appearance.m3colors.m3surfaceContainerHigh ?? "#2b2a2a"
                        }
                        Rectangle {
                            anchors.left: parent.left
                            width: parent.width * Math.min(1, Math.max(0, tool?.quotaUsed ?? 0))
                            height: parent.height
                            radius: height / 2
                            color: root.statusColor(toolStatus, accent)
                        }
                    }
                }

                // Metrics row: cost + tokens
                RowLayout {
                    spacing: 12
                    Layout.leftMargin: 16
                    visible: (tool?.costToday ?? 0) > 0 || (tool?.tokensIn ?? 0) > 0

                    StyledPopupValueRow {
                        visible: (tool?.costToday ?? 0) > 0
                        icon: "payments"
                        label: ""
                        value: "$" + (tool?.costToday ?? 0).toFixed(2)
                    }

                    StyledPopupValueRow {
                        visible: (tool?.tokensIn ?? 0) > 0
                        icon: "input"
                        label: ""
                        value: root.formatTokens(tool?.tokensIn ?? 0)
                    }

                    StyledPopupValueRow {
                        visible: (tool?.tokensOut ?? 0) > 0
                        icon: "output"
                        label: ""
                        value: root.formatTokens(tool?.tokensOut ?? 0)
                    }
                }

                // Per-model breakdown
                ColumnLayout {
                    visible: (tool?.models ?? []).length > 0
                    spacing: 2
                    Layout.fillWidth: true
                    Layout.leftMargin: 16

                    StyledText {
                        visible: (tool?.activeModel ?? "") !== ""
                        text: "Active: " + (tool?.activeModel ?? "")
                        font.pixelSize: Appearance.font.pixelSize.smaller
                        font.weight: Font.DemiBold
                        color: accent || Appearance.colors.colOnSurface
                    }

                    Repeater {
                        model: tool?.models ?? []

                        RowLayout {
                            required property var modelData
                            spacing: 8
                            Layout.fillWidth: true

                            StyledText {
                                text: modelData.name
                                font.pixelSize: Appearance.font.pixelSize.smaller
                                color: Appearance.colors.colOnSurfaceVariant
                                Layout.preferredWidth: 70
                            }

                            StyledText {
                                text: "$" + (modelData.cost ?? 0).toFixed(2)
                                font.pixelSize: Appearance.font.pixelSize.smaller
                                color: Appearance.colors.colOnSurface
                                Layout.preferredWidth: 50
                            }

                            StyledText {
                                text: root.formatTokens(modelData.tokensIn ?? 0) + " / " + root.formatTokens(modelData.tokensOut ?? 0)
                                font.pixelSize: Appearance.font.pixelSize.smaller
                                color: Appearance.colors.colOnSurfaceVariant
                            }
                        }
                    }
                }
            }
        }

        // Footer: last update time
        StyledText {
            Layout.alignment: Qt.AlignRight
            Layout.topMargin: 4
            font.pixelSize: Appearance.font.pixelSize.smaller
            color: Appearance.colors.colOnSurfaceVariant
            text: {
                if (!AIBar.lastUpdate) return ""
                const d = new Date(AIBar.lastUpdate)
                return "Updated " + d.toLocaleTimeString()
            }
        }
    }
}
