pragma Singleton
pragma ComponentBehavior: Bound

import qs.modules.common
import qs.modules.common.functions
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property var tools: ({})
    property var enabledTools: ["claude", "codex", "copilot"]
    property var toolIds: Object.keys(tools).filter(id => enabledTools.indexOf(id) !== -1)
    property string lastUpdate: ""
    property int toolCount: toolIds.length
    property double avgRemainingPercent: {
        if (toolIds.length === 0) return 100
        let total = 0
        for (const id of toolIds) {
            total += getRemainingPercent(id)
        }
        return total / toolIds.length
    }

    function getTool(id) {
        return tools[id] ?? null
    }

    function getRemainingPercent(id) {
        const t = tools[id]
        if (!t) return 0
        // Use rateWindows if available (worst window is first)
        const windows = t.rateWindows
        if (windows && windows.length > 0) {
            for (const w of windows) {
                if (w.usedPercent >= 100) return 0
            }
            return Math.max(0, 100 - windows[0].usedPercent)
        }
        // Fallback: use primary/secondary (Codex)
        if (t.secondary && t.secondary.usedPercent >= 100) return 0
        if (t.primary && t.primary.usedPercent >= 100) return 0
        if (t.primary && t.primary.usedPercent !== undefined) {
            let remaining = 100 - t.primary.usedPercent
            if (t.secondary && t.secondary.usedPercent !== undefined)
                remaining = Math.min(remaining, 100 - t.secondary.usedPercent)
            return Math.max(0, remaining)
        }
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

    function worstStatus() {
        if (toolIds.length === 0) return "inactive"
        let worst = "ok"
        for (const id of toolIds) {
            const s = tools[id]?.status
            if (s === "limited") return "limited"
            if (s === "warning") worst = "warning"
        }
        return worst
    }

    function refresh() {
        statusFile.reload()
        try {
            const data = JSON.parse(statusFile.text())
            root.tools = data.tools ?? {}
            root.lastUpdate = data.lastUpdate ?? ""
        } catch (e) {}
    }

    FileView {
        id: statusFile
        path: FileUtils.trimFileProtocol(Directories.home) + "/.cache/aibar/status.json"
    }

    Component.onCompleted: refresh()

    Timer {
        interval: 5000
        running: true
        repeat: true
        onTriggered: root.refresh()
    }
}
