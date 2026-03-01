# AIBar CodexBar-Style Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restyle AIBar's bar indicators and popup to match CodexBar's capsule progress bars, provider accent colors, rate windows with reset countdowns, and rich per-provider detail cards.

**Architecture:** Four-file edit. AIBar.qml service gets expanded parsing for new data fields (primary/secondary rate windows, color, plan) with backward compat. AIBarIndicator.qml replaces circular progress with horizontal capsule bar. AIBarPopup.qml gets full redesign with per-provider cards containing progress bars and reset timers. AIBarGroup.qml adjusts spacing.

**Tech Stack:** QML/Qt Quick, Quickshell framework, existing StyledProgressBar/StyledText/StyledPopup widgets.

---

### Task 1: Update AIBar.qml Service — Parse Expanded Data Model

**Files:**
- Modify: `~/.config/quickshell/ii/services/AIBar.qml`

**Step 1: Add helper functions for the new data model**

Add a `getRemainingPercent(id)` helper that reads from `primary.usedPercent` with fallback to `quotaUsed`, a `getColor(id)` helper, and a `formatResetTime(isoString)` helper. These support backward compat with old status.json format.

```qml
// Add after the existing getTool function (line ~22)

function getRemainingPercent(id) {
    const t = tools[id]
    if (!t) return 0
    if (t.primary && t.primary.usedPercent !== undefined)
        return Math.max(0, 100 - t.primary.usedPercent)
    return Math.max(0, (1 - (t.quotaUsed ?? 0)) * 100)
}

function getColor(id) {
    const t = tools[id]
    return (t && t.color) ? t.color : ""
}

function formatResetTime(isoString) {
    if (!isoString) return ""
    const now = new Date()
    const reset = new Date(isoString)
    const diffMs = reset.getTime() - now.getTime()
    if (diffMs <= 0) return "Resetting..."
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 60) return "Resets in " + diffMin + "m"
    const hours = Math.floor(diffMin / 60)
    const mins = diffMin % 60
    if (hours < 24) return "Resets in " + hours + "h " + mins + "m"
    const days = Math.floor(hours / 24)
    return "Resets in " + days + "d"
}
```

**Step 2: Verify the service loads without errors**

Run: `killall qs; sleep 1; nohup qs -c ii > /tmp/qs-t1.txt 2>&1 & sleep 3 && grep -i "error.*aibar\|AIBar.*error" /tmp/qs-t1.txt`
Expected: No AIBar-related errors.

**Step 3: Commit**

```bash
git add ~/.config/quickshell/ii/services/AIBar.qml
git commit -m "feat(aibar): add helper functions for expanded data model"
```

---

### Task 2: Rewrite AIBarIndicator.qml — Capsule Progress Bar

**Files:**
- Modify: `~/.config/quickshell/ii/modules/ii/bar/aibar/AIBarIndicator.qml`

**Step 1: Replace the entire AIBarIndicator with capsule bar layout**

Replace the full file content with a horizontal layout: letter label + capsule progress bar + percentage text.

```qml
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
    required property bool toolActive
    required property double costToday
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
```

**Step 2: Update AIBarGroup.qml to pass new properties**

Modify `~/.config/quickshell/ii/modules/ii/bar/aibar/AIBarGroup.qml` to pass `accentColor` and `primaryWindow` to the indicator, and adjust spacing.

Replace the Repeater's AIBarIndicator delegate:

```qml
        Repeater {
            model: AIBar.toolIds

            AIBarIndicator {
                required property string modelData
                required property int index
                property var tool: AIBar.getTool(modelData)
                toolLetter: tool?.letter ?? "?"
                quotaUsed: tool?.quotaUsed ?? 0
                status: tool?.status ?? "inactive"
                toolActive: tool?.active ?? false
                costToday: tool?.costToday ?? 0
                accentColor: tool?.color ?? ""
                primaryWindow: tool?.primary ?? null
                Layout.leftMargin: index > 0 ? 8 : 0
            }
        }
```

**Step 3: Verify visually — restart Quickshell**

Run: `killall qs; sleep 1; nohup qs -c ii > /tmp/qs-t2.txt 2>&1 & sleep 3 && grep -i "error.*aibar\|AIBar\|indicator" /tmp/qs-t2.txt`
Expected: No AIBar errors. Bar should show capsule progress bars with letters and percentages.

**Step 4: Commit**

```bash
git add ~/.config/quickshell/ii/modules/ii/bar/aibar/AIBarIndicator.qml ~/.config/quickshell/ii/modules/ii/bar/aibar/AIBarGroup.qml
git commit -m "feat(aibar): replace circular indicators with capsule progress bars"
```

---

### Task 3: Rewrite AIBarPopup.qml — Provider Cards with Rate Windows

**Files:**
- Modify: `~/.config/quickshell/ii/modules/ii/bar/aibar/AIBarPopup.qml`

**Step 1: Replace full popup content with CodexBar-style provider cards**

The popup shows per-provider sections with: status dot + name + running badge, plan info, progress bars for primary/secondary rate windows with reset countdowns, and a compact metrics row.

```qml
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

    function barColor(status, accentColor) {
        if (status === "limited") return Appearance.colors.colError
        if (status === "warning") return "#FFA500"
        if (accentColor) return accentColor
        return Appearance.colors.colPrimary
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

                // Primary rate window
                ColumnLayout {
                    visible: tool?.primary !== undefined && tool?.primary !== null
                    spacing: 2
                    Layout.fillWidth: true
                    Layout.leftMargin: 16

                    RowLayout {
                        Layout.fillWidth: true
                        StyledText {
                            text: tool?.primary?.label ?? "Session"
                            font.pixelSize: Appearance.font.pixelSize.smaller
                            color: Appearance.colors.colOnSurfaceVariant
                        }
                        Item { Layout.fillWidth: true }
                        StyledText {
                            text: {
                                const used = tool?.primary?.usedPercent ?? 0
                                return Math.round(Math.max(0, 100 - used)) + "% remaining"
                            }
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
                            width: parent.width * Math.min(1, Math.max(0, (100 - (tool?.primary?.usedPercent ?? 0)) / 100))
                            height: parent.height
                            radius: height / 2
                            color: root.barColor(toolStatus, accent)
                        }
                    }

                    StyledText {
                        text: AIBar.formatResetTime(tool?.primary?.resetsAt ?? "")
                        visible: text !== ""
                        font.pixelSize: Appearance.font.pixelSize.smaller
                        color: Appearance.colors.colOnSurfaceVariant
                    }
                }

                // Secondary rate window
                ColumnLayout {
                    visible: tool?.secondary !== undefined && tool?.secondary !== null
                    spacing: 2
                    Layout.fillWidth: true
                    Layout.leftMargin: 16

                    RowLayout {
                        Layout.fillWidth: true
                        StyledText {
                            text: tool?.secondary?.label ?? "Weekly"
                            font.pixelSize: Appearance.font.pixelSize.smaller
                            color: Appearance.colors.colOnSurfaceVariant
                        }
                        Item { Layout.fillWidth: true }
                        StyledText {
                            text: {
                                const used = tool?.secondary?.usedPercent ?? 0
                                return Math.round(Math.max(0, 100 - used)) + "% remaining"
                            }
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
                            width: parent.width * Math.min(1, Math.max(0, (100 - (tool?.secondary?.usedPercent ?? 0)) / 100))
                            height: parent.height
                            radius: height / 2
                            color: root.barColor(toolStatus, accent)
                        }
                    }

                    StyledText {
                        text: AIBar.formatResetTime(tool?.secondary?.resetsAt ?? "")
                        visible: text !== ""
                        font.pixelSize: Appearance.font.pixelSize.smaller
                        color: Appearance.colors.colOnSurfaceVariant
                    }
                }

                // Fallback: simple quota bar when no rate windows present
                ColumnLayout {
                    visible: (tool?.primary === undefined || tool?.primary === null) && (tool?.quotaUsed ?? 0) > 0
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
                            text: Math.round(Math.max(0, (1 - (tool?.quotaUsed ?? 0)) * 100)) + "% remaining"
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
                            width: parent.width * Math.min(1, Math.max(0, 1 - (tool?.quotaUsed ?? 0)))
                            height: parent.height
                            radius: height / 2
                            color: root.barColor(toolStatus, accent)
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
```

**Step 2: Verify — restart Quickshell and hover over AIBar**

Run: `killall qs; sleep 1; nohup qs -c ii > /tmp/qs-t3.txt 2>&1 & sleep 3 && grep -i "error.*aibar\|AIBar\|popup" /tmp/qs-t3.txt`
Expected: No errors. Hovering over the AIBar area should show the new popup with provider cards, progress bars, and metrics.

**Step 3: Commit**

```bash
git add ~/.config/quickshell/ii/modules/ii/bar/aibar/AIBarPopup.qml
git commit -m "feat(aibar): redesign popup with CodexBar-style provider cards and rate windows"
```

---

### Task 4: Update status.json with Expanded Data

**Files:**
- Modify: `~/.cache/aibar/status.json`

**Step 1: Update status.json with provider colors and rate windows for testing**

Write a test version of status.json that uses the expanded format so we can verify the full UI renders correctly.

```json
{
  "lastUpdate": "2026-02-28T23:00:00Z",
  "tools": {
    "claude": {
      "letter": "C",
      "name": "Claude Code",
      "color": "#D97757",
      "active": true,
      "status": "ok",
      "plan": "Max",
      "primary": { "usedPercent": 16.6, "windowMinutes": 300, "resetsAt": "2026-03-01T04:00:00Z", "label": "Session" },
      "secondary": { "usedPercent": 45.0, "windowMinutes": 10080, "resetsAt": "2026-03-03T00:00:00Z", "label": "Weekly" },
      "costToday": 33.19,
      "tokensIn": 366698,
      "tokensOut": 369527,
      "quotaUsed": 0.166
    },
    "codex": {
      "letter": "X",
      "name": "Codex CLI",
      "color": "#10A37F",
      "active": false,
      "status": "limited",
      "primary": { "usedPercent": 100.0, "windowMinutes": 300, "resetsAt": "2026-03-01T02:30:00Z", "label": "Session" },
      "secondary": { "usedPercent": 72.0, "windowMinutes": 10080, "resetsAt": "2026-03-03T00:00:00Z", "label": "Weekly" },
      "costToday": 0.0,
      "tokensIn": 0,
      "tokensOut": 0,
      "quotaUsed": 1.0
    },
    "gemini": {
      "letter": "G",
      "name": "Gemini CLI",
      "color": "#4285F4",
      "active": false,
      "status": "ok",
      "primary": { "usedPercent": 5.0, "windowMinutes": 300, "resetsAt": "2026-03-01T04:00:00Z", "label": "Session" },
      "costToday": 0.0,
      "tokensIn": 0,
      "tokensOut": 0,
      "quotaUsed": 0.05
    },
    "copilot": {
      "letter": "P",
      "name": "GitHub Copilot",
      "color": "#7C3AED",
      "active": false,
      "status": "ok",
      "costToday": 0.0,
      "tokensIn": 0,
      "tokensOut": 0,
      "quotaUsed": 0.0
    }
  }
}
```

**Step 2: Restart and visually verify the full experience**

Run: `killall qs; sleep 1; nohup qs -c ii > /tmp/qs-t4.txt 2>&1 & sleep 3 && grep -i "error" /tmp/qs-t4.txt | grep -iv "mapFromItem"`
Expected: No errors. Bar shows colored capsule bars. Popup shows rate windows with reset countdowns.

**Step 3: Do NOT commit status.json** — it's a cache file, not source code. This step is for testing only.

---

### Task 5: Final Verification and Cleanup

**Step 1: Verify backward compatibility**

Temporarily revert status.json to the old flat format (no `primary`, `secondary`, `color`, `plan`) and verify the UI still works with fallback behavior.

**Step 2: Restart and check**

Run: `killall qs; sleep 1; nohup qs -c ii > /tmp/qs-t5.txt 2>&1 & sleep 3 && grep -i "error" /tmp/qs-t5.txt | grep -iv "mapFromItem"`
Expected: No errors. Bar shows capsule bars using `quotaUsed` fallback. Popup shows simple quota bars without rate window sections.

**Step 3: Restore expanded status.json for full testing**

Put back the expanded format from Task 4.

**Step 4: Final commit if any cleanup needed**

```bash
git status
# If any remaining changes, commit them
```
