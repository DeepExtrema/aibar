# Claude Code Real Usage API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Claude Code's cost-based quota heuristic with real rate limit data from the Anthropic OAuth usage API, showing session, weekly, and sonnet-only windows with accurate percentages and reset times.

**Architecture:** Add a `fetch_claude_usage()` function to the collector that reads the OAuth token from `~/.claude/.credentials.json` and calls `GET https://api.anthropic.com/api/oauth/usage`. Map the three API windows (five_hour, seven_day, seven_day_sonnet) into a `rateWindows` array sorted by worst-first, and set `primary` to the worst window. Fall back to the existing cost heuristic on any failure. Update the QML popup to render the `rateWindows` array as compact detail rows below the primary progress bar.

**Tech Stack:** Python 3 stdlib (json, urllib.request), QML/Quickshell.

---

### Task 1: Add `fetch_claude_usage()` to the Collector

**Files:**
- Modify: `~/.local/bin/aibar-collector.py` — add new function + import

**Step 1: Add `urllib.request` import**

At line 16 (after `from pathlib import Path`), add:

```python
from urllib.request import Request, urlopen
from urllib.error import URLError
```

**Step 2: Write `fetch_claude_usage` function**

Add this function before `parse_claude` (before line 99):

```python
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

def fetch_claude_usage(data_dir: Path) -> dict | None:
    """Fetch real rate limit data from Anthropic OAuth usage API.

    Returns dict with 'rateWindows' list and 'primary' (worst window),
    or None if the API call fails for any reason.
    """
    creds_file = data_dir / ".credentials.json"
    if not creds_file.is_file():
        return None

    try:
        with open(creds_file, "r") as f:
            creds = json.load(f)
        token = creds["claudeAiOauth"]["accessToken"]
    except (json.JSONDecodeError, KeyError, OSError):
        return None

    req = Request(CLAUDE_USAGE_URL)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("anthropic-beta", "oauth-2025-04-20")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (URLError, json.JSONDecodeError, OSError, TimeoutError):
        return None

    # Map API fields to rate windows
    WINDOW_MAP = {
        "five_hour": "Session",
        "seven_day": "Weekly",
        "seven_day_sonnet": "Sonnet only",
        "seven_day_opus": "Opus only",
    }

    windows = []
    for api_key, label in WINDOW_MAP.items():
        raw = data.get(api_key)
        if not isinstance(raw, dict):
            continue
        util = raw.get("utilization")
        if util is None:
            continue
        resets_at = raw.get("resets_at", "")
        # Normalize resets_at to simple ISO format (strip fractional seconds + tz offset)
        if resets_at and "+" in resets_at:
            try:
                dt = datetime.fromisoformat(resets_at)
                resets_at = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                pass
        windows.append({
            "usedPercent": float(util),
            "resetsAt": resets_at,
            "label": label,
        })

    if not windows:
        return None

    # Sort worst-first (highest utilization)
    windows.sort(key=lambda w: w["usedPercent"], reverse=True)

    return {
        "rateWindows": windows,
        "primary": windows[0],
        "quotaUsed": round(windows[0]["usedPercent"] / 100.0, 4),
    }
```

**Step 3: Test the function standalone**

Run: `python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, str(Path.home() / '.local/bin'))
from importlib import import_module
# Quick inline test
import json
from urllib.request import Request, urlopen
creds = json.load(open(Path.home() / '.claude/.credentials.json'))
token = creds['claudeAiOauth']['accessToken']
req = Request('https://api.anthropic.com/api/oauth/usage')
req.add_header('Authorization', f'Bearer {token}')
req.add_header('anthropic-beta', 'oauth-2025-04-20')
with urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read())
print(json.dumps(data, indent=2))
"`

Expected: JSON with `five_hour`, `seven_day`, `seven_day_sonnet` objects containing `utilization` and `resets_at`.

---

### Task 2: Integrate API Data into `parse_claude`

**Files:**
- Modify: `~/.local/bin/aibar-collector.py:99-238` — update `parse_claude` function

**Step 1: Call `fetch_claude_usage` at the start of `parse_claude`**

At the beginning of `parse_claude`, right after the `result` dict initialization (line 101), add:

```python
    # --- Try real API data first ---
    api_data = fetch_claude_usage(data_dir)
    if api_data:
        result["rateWindows"] = api_data["rateWindows"]
        result["primary"] = api_data["primary"]
        result["quotaUsed"] = api_data["quotaUsed"]
```

**Step 2: Remove the old `secondary` field and cost-based `quotaUsed`**

At the end of `parse_claude`, the cost-based heuristic (lines 234-236) should only run when API data wasn't available. Wrap it:

```python
    # Estimate quota using plan-appropriate budget (fallback when API unavailable)
    if "quotaUsed" not in result and total_cost > 0:
        result["quotaUsed"] = round(min(total_cost / budget, 1.0), 4)
```

Change the condition from `if total_cost > 0` to `if "quotaUsed" not in result and total_cost > 0` — this way the API-provided `quotaUsed` takes precedence.

**Step 3: Test**

Run: `~/.local/bin/aibar-collector.py | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d['tools']['claude']
print('primary:', json.dumps(c.get('primary'), indent=2))
print('rateWindows:', json.dumps(c.get('rateWindows'), indent=2))
print('quotaUsed:', c.get('quotaUsed'))
print('plan:', c.get('plan'))
print('models:', [m['name'] for m in c.get('models', [])])
"`

Expected: `primary` shows the worst window (highest utilization). `rateWindows` has 3 entries (Session, Weekly, Sonnet only) with real percentages matching the claude.ai usage page. `quotaUsed` matches worst window. `plan` and `models` still present (those come from local data, not the API).

---

### Task 3: Pass `rateWindows` Through `collect_tool_status`

**Files:**
- Modify: `~/.local/bin/aibar-collector.py:449-462` — update `collect_tool_status`

**Step 1: Add `rateWindows` passthrough**

After the existing optional field passthrough block, add:

```python
    if "rateWindows" in parsed:
        entry["rateWindows"] = parsed["rateWindows"]
```

This goes alongside the existing `if "primary" in parsed:` block (line 452).

**Step 2: Test full output**

Run: `~/.local/bin/aibar-collector.py | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d['tools']['claude']
assert 'rateWindows' in c, 'Missing rateWindows'
assert len(c['rateWindows']) >= 2, 'Expected at least 2 windows'
for w in c['rateWindows']:
    assert 'usedPercent' in w and 'resetsAt' in w and 'label' in w
    print(f\"  {w['label']}: {w['usedPercent']}% used, resets {w['resetsAt']}\")
print('All checks passed')
"`

Expected: All 3 windows printed with real data, all checks pass.

---

### Task 4: Update QML Popup for `rateWindows` Display

**Files:**
- Modify: `~/.config/quickshell/ii/modules/ii/bar/aibar/AIBarPopup.qml:95-197`
- Modify: `~/.config/quickshell/ii/services/AIBar.qml:31-45`

**Step 1: Update `getRemainingPercent` in AIBar.qml to use `rateWindows`**

Replace the current `getRemainingPercent` function (lines 31-45) with:

```javascript
    function getRemainingPercent(id) {
        const t = tools[id]
        if (!t) return 0
        // Use rateWindows if available (worst window is first)
        const windows = t.rateWindows
        if (windows && windows.length > 0) {
            // If any window is fully exhausted, treat as 0%
            for (const w of windows) {
                if (w.usedPercent >= 100) return 0
            }
            return Math.max(0, 100 - windows[0].usedPercent)
        }
        // Fallback: use primary/secondary
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
```

**Step 2: Replace the primary+secondary sections in AIBarPopup.qml with a rateWindows Repeater**

Replace the two large blocks — "Primary rate window" (lines 95-145) and "Secondary rate window" (lines 147-197) — with a single block that handles both `rateWindows` (Claude API) and the legacy `primary`/`secondary` (Codex):

```qml
                // Rate windows — rateWindows array (Claude API) or primary/secondary (Codex)
                // Prominent bar for worst window (first in rateWindows, or primary)
                ColumnLayout {
                    id: worstWindowSection
                    property var worstWindow: {
                        const rw = tool?.rateWindows
                        if (rw && rw.length > 0) return rw[0]
                        if (tool?.primary) return tool.primary
                        return null
                    }
                    visible: worstWindow !== null
                    spacing: 2
                    Layout.fillWidth: true
                    Layout.leftMargin: 16

                    RowLayout {
                        Layout.fillWidth: true
                        StyledText {
                            text: worstWindowSection.worstWindow?.label ?? "Usage"
                            font.pixelSize: Appearance.font.pixelSize.smaller
                            color: Appearance.colors.colOnSurfaceVariant
                        }
                        Item { Layout.fillWidth: true }
                        StyledText {
                            text: {
                                const used = worstWindowSection.worstWindow?.usedPercent ?? 0
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
                            width: parent.width * Math.min(1, Math.max(0, (100 - (worstWindowSection.worstWindow?.usedPercent ?? 0)) / 100))
                            height: parent.height
                            radius: height / 2
                            color: root.statusColor(toolStatus, accent)
                        }
                    }

                    StyledText {
                        text: AIBar.formatResetTime(worstWindowSection.worstWindow?.resetsAt ?? "")
                        visible: text !== ""
                        font.pixelSize: Appearance.font.pixelSize.smaller
                        color: Appearance.colors.colOnSurfaceVariant
                    }
                }

                // Compact detail rows for all rate windows
                ColumnLayout {
                    visible: (tool?.rateWindows ?? []).length > 1
                    spacing: 1
                    Layout.fillWidth: true
                    Layout.leftMargin: 16
                    Layout.topMargin: 2

                    Repeater {
                        model: tool?.rateWindows ?? []

                        RowLayout {
                            required property var modelData
                            spacing: 6
                            Layout.fillWidth: true

                            StyledText {
                                text: modelData.label
                                font.pixelSize: Appearance.font.pixelSize.smaller
                                color: Appearance.colors.colOnSurfaceVariant
                                Layout.preferredWidth: 75
                            }

                            StyledText {
                                text: Math.round(modelData.usedPercent) + "% used"
                                font.pixelSize: Appearance.font.pixelSize.smaller
                                font.weight: Font.DemiBold
                                color: {
                                    if (modelData.usedPercent >= 100) return Appearance.colors.colError
                                    if (modelData.usedPercent >= 70) return "#FFA500"
                                    return Appearance.colors.colOnSurface
                                }
                                Layout.preferredWidth: 60
                            }

                            StyledText {
                                text: AIBar.formatResetTime(modelData.resetsAt ?? "")
                                font.pixelSize: Appearance.font.pixelSize.smaller
                                color: Appearance.colors.colOnSurfaceVariant
                            }
                        }
                    }
                }

                // Legacy secondary window (Codex — only shown when no rateWindows)
                ColumnLayout {
                    visible: (tool?.rateWindows ?? []).length === 0 && tool?.secondary !== undefined && tool?.secondary !== null
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
                            color: root.statusColor(toolStatus, accent)
                        }
                    }

                    StyledText {
                        text: AIBar.formatResetTime(tool?.secondary?.resetsAt ?? "")
                        visible: text !== ""
                        font.pixelSize: Appearance.font.pixelSize.smaller
                        color: Appearance.colors.colOnSurfaceVariant
                    }
                }
```

**Step 3: Test**

Run: `killall qs; sleep 1; nohup qs -c ii > /tmp/qs-ratewin.txt 2>&1 & sleep 4 && grep -i "error" /tmp/qs-ratewin.txt | grep -iv "mapFromItem\|brightness\|QFont"`

Expected: No QML errors. Popup shows Claude Code with:
- Prominent progress bar for the worst window
- Compact detail rows: "Weekly  35% used  Resets Thu 11PM" / "Session  16% used  Resets in 3h" / "Sonnet only  6% used  Resets Fri 8AM"
- Codex still shows its primary/secondary windows as before (it has no rateWindows).

---

### Task 5: Verify End-to-End

**Step 1: Validate collector JSON**

Run: `~/.local/bin/aibar-collector.py | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d['tools']['claude']
x = d['tools']['codex']
# Claude should have rateWindows from API
assert 'rateWindows' in c, 'Claude missing rateWindows'
assert len(c['rateWindows']) >= 2
assert c['primary']['label'] in [w['label'] for w in c['rateWindows']]
# Codex should still have primary/secondary (no rateWindows)
assert 'primary' in x
assert 'secondary' in x
assert 'rateWindows' not in x
# Backward compat
for k in ['quotaUsed','costToday','tokensIn','tokensOut','status','color','plan','models']:
    assert k in c, f'Claude missing {k}'
print('Claude windows:', [(w['label'], w['usedPercent']) for w in c['rateWindows']])
print('Codex primary:', x['primary']['usedPercent'], '% session')
print('All checks passed')
"`

Expected: All assertions pass. Claude shows 3 real rate windows. Codex still shows primary/secondary.

**Step 2: Restart systemd timer**

Run: `systemctl --user restart aibar-collector.timer && systemctl --user status aibar-collector.timer --no-pager | head -6`

Expected: Timer active.

**Step 3: Visual verification**

Restart Quickshell and hover over AIBar. Verify:
- Claude Code popup matches the claude.ai usage page numbers
- Worst window gets the prominent progress bar
- All 3 windows shown as compact rows
- Codex still shows its 2 windows normally
- Bar indicator reflects the worst window across all tools
