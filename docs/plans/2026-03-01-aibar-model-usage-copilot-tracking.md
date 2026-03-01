# AIBar — Per-Model Usage Display & Copilot CLI Tracking

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show per-model token/cost breakdowns in the AIBar popup for Claude Code (not hardcoded to one model), and add real session tracking for GitHub Copilot CLI.

**Architecture:** Extend `parse_claude` in the collector to extract `lastModelUsage` from backup files — this gives per-model token counts and costs across all projects. For Copilot CLI, parse `~/.local/state/.copilot/session-state/*/events.jsonl` to count interactions and detect activity. Update the popup QML to render per-model rows under each provider.

**Tech Stack:** Python 3 stdlib (json, pathlib, datetime). QML/Quickshell for UI.

---

### Task 1: Extract Per-Model Usage from Claude Code Backups

**Files:**
- Modify: `~/.local/bin/aibar-collector.py:99-193` — `parse_claude` function

**Step 1: Add model usage extraction to `parse_claude`**

After the existing cost/token loop (which sums `lastCost`, `lastTotalInputTokens`, `lastTotalOutputTokens`), aggregate `lastModelUsage` across all projects. The backup JSON structure is:

```json
{
  "projects": {
    "/path/to/project": {
      "lastModelUsage": {
        "claude-opus-4-6": {
          "inputTokens": 8994,
          "outputTokens": 38937,
          "cacheReadInputTokens": 2981879,
          "cacheCreationInputTokens": 181582,
          "costUSD": 3.84
        },
        "claude-haiku-4-5-20251001": {
          "inputTokens": 55801,
          "outputTokens": 16687,
          "costUSD": 0.44
        }
      }
    }
  }
}
```

Add this code after the existing `for proj_data in projects.values():` loop, inside `parse_claude`:

```python
    # --- Aggregate per-model usage across all projects ---
    model_totals = {}  # model_id -> {inputTokens, outputTokens, costUSD}
    for proj_data in projects.values():
        if not isinstance(proj_data, dict):
            continue
        model_usage = proj_data.get("lastModelUsage", {})
        if not isinstance(model_usage, dict):
            continue
        for model_id, usage in model_usage.items():
            if not isinstance(usage, dict):
                continue
            if model_id not in model_totals:
                model_totals[model_id] = {"inputTokens": 0, "outputTokens": 0, "costUSD": 0.0}
            model_totals[model_id]["inputTokens"] += usage.get("inputTokens", 0) or 0
            model_totals[model_id]["outputTokens"] += usage.get("outputTokens", 0) or 0
            model_totals[model_id]["costUSD"] += usage.get("costUSD", 0) or 0

    if model_totals:
        # Build a sorted list (highest cost first) with friendly names
        models = []
        for model_id, totals in sorted(model_totals.items(), key=lambda x: x[1]["costUSD"], reverse=True):
            name = model_id
            # Friendly names: "claude-opus-4-6" -> "Opus 4.6", "claude-haiku-4-5-20251001" -> "Haiku 4.5"
            if "opus" in model_id:
                name = "Opus " + model_id.split("opus-")[1].replace("-", ".") if "opus-" in model_id else "Opus"
            elif "sonnet" in model_id:
                name = "Sonnet " + model_id.split("sonnet-")[1].split("-")[0].replace("-", ".") if "sonnet-" in model_id else "Sonnet"
            elif "haiku" in model_id:
                name = "Haiku " + model_id.split("haiku-")[1].split("-")[0].replace("-", ".") if "haiku-" in model_id else "Haiku"
            models.append({
                "id": model_id,
                "name": name,
                "tokensIn": totals["inputTokens"],
                "tokensOut": totals["outputTokens"],
                "cost": round(totals["costUSD"], 4),
            })
        result["models"] = models
```

**Step 2: Also extract active model from settings.json**

Add before the `return result` at the end of `parse_claude`:

```python
    # --- Read active model from settings ---
    settings_file = data_dir / "settings.json"
    if settings_file.is_file():
        try:
            with open(settings_file, "r") as f:
                settings = json.load(f)
            active_model = settings.get("model", "")
            if active_model:
                result["activeModel"] = active_model.capitalize()
        except (json.JSONDecodeError, OSError):
            pass
```

**Step 3: Test**

Run: `~/.local/bin/aibar-collector.py | python3 -c "import sys,json; d=json.load(sys.stdin); c=d['tools']['claude']; print(json.dumps({'models': c.get('models'), 'activeModel': c.get('activeModel'), 'plan': c.get('plan')}, indent=2))"`

Expected: Output shows `"models": [{"id": "claude-opus-4-6", "name": "Opus 4.6", ...}, ...]` sorted by cost descending, and `"activeModel": "Opus"`.

---

### Task 2: Add Copilot CLI Session Tracking

**Files:**
- Modify: `~/.local/bin/aibar-collector.py` — add `parse_copilot` function and register it in `PARSERS`

**Step 1: Update TOOL_DEFS for Copilot**

The current `copilot` entry in `TOOL_DEFS` points to VS Code's globalStorage which isn't useful. Change it:

```python
    "copilot": {
        "letter": "P",
        "name": "GitHub Copilot",
        "color": "#7C3AED",
        "process_names": ["copilot"],
        "data_dir": Path.home() / ".local" / "state" / ".copilot",
    },
```

**Step 2: Write `parse_copilot` function**

Copilot CLI stores session data at `~/.local/state/.copilot/session-state/<session-id>/`. Each session dir has:
- `workspace.yaml` with session metadata (created_at, updated_at, summary)
- `events.jsonl` with interaction events (user.message, assistant.message, tool.execution_*)

Parse the most recent session's events to count interactions and detect activity:

```python
def parse_copilot(data_dir: Path) -> dict:
    """Parse Copilot CLI session state for interaction counts."""
    result = {"costToday": 0.0, "tokensIn": 0, "tokensOut": 0, "quotaUsed": 0.0}

    sessions_dir = data_dir / "session-state"
    if not sessions_dir.is_dir():
        return result

    # Find the most recently modified session directory
    latest_session = None
    latest_mtime = 0.0
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        events_file = session_dir / "events.jsonl"
        if not events_file.is_file():
            continue
        try:
            mtime = events_file.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_session = session_dir
        except OSError:
            continue

    if latest_session is None:
        return result

    # Count user messages (interactions) in the latest session
    events_file = latest_session / "events.jsonl"
    user_messages = 0
    assistant_messages = 0
    tool_calls = 0

    try:
        with open(events_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    event_type = event.get("type", "")
                    if event_type == "user.message":
                        user_messages += 1
                    elif event_type == "assistant.message":
                        assistant_messages += 1
                    elif event_type == "tool.execution_complete":
                        tool_calls += 1
                except json.JSONDecodeError:
                    continue
    except OSError:
        return result

    # Store interaction counts as token proxies
    result["tokensIn"] = user_messages
    result["tokensOut"] = assistant_messages + tool_calls

    # Read session summary from workspace.yaml (plain text parsing, no yaml dep)
    workspace_file = latest_session / "workspace.yaml"
    if workspace_file.is_file():
        try:
            text = workspace_file.read_text()
            for wline in text.splitlines():
                wline = wline.strip()
                if wline.startswith("summary:"):
                    summary = wline.split(":", 1)[1].strip()
                    if summary:
                        result["sessionSummary"] = summary
                    break
        except OSError:
            pass

    return result
```

**Step 3: Register the parser**

Add to the `PARSERS` dict:

```python
PARSERS = {
    "claude": parse_claude,
    "codex": parse_codex,
    "openclaw": parse_openclaw,
    "copilot": parse_copilot,
}
```

**Step 4: Test**

Run: `~/.local/bin/aibar-collector.py | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['tools']['copilot'], indent=2))"`

Expected: Copilot output has `"tokensIn": <user_message_count>`, `"tokensOut": <assistant_messages + tool_calls>`, and optionally `"sessionSummary": "Run Tests"`.

---

### Task 3: Display Per-Model Rows in AIBarPopup

**Files:**
- Modify: `~/.config/quickshell/ii/modules/ii/bar/aibar/AIBarPopup.qml`

**Step 1: Add a models section under each provider card**

After the metrics row (cost + tokens, lines ~242-267), add a per-model breakdown section. Only shown when the tool has a `models` array:

```qml
                // Per-model breakdown
                ColumnLayout {
                    visible: (tool?.models ?? []).length > 0
                    spacing: 2
                    Layout.fillWidth: true
                    Layout.leftMargin: 16

                    // Active model header
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
```

Place this block right after the closing `}` of the metrics RowLayout (line ~267) and before the closing `}` of the ColumnLayout for each tool (line ~268).

**Step 2: Test**

Run: `killall qs; sleep 1; nohup qs -c ii > /tmp/qs-models.txt 2>&1 & sleep 3 && grep -i "error" /tmp/qs-models.txt | grep -iv "mapFromItem\|brightness\|QFont"`

Expected: No QML errors. Hovering over AIBar popup shows Claude Code section with "Active: Opus" and per-model rows like:
```
Opus 4.6     $30.67    1.2M / 315.3K
Haiku 4.5    $2.52     346.7K / 81.3K
```

---

### Task 4: Update `collect_tool_status` for New Fields

**Files:**
- Modify: `~/.local/bin/aibar-collector.py:287-320` — `collect_tool_status` function

**Step 1: Pass through new optional fields**

Add after the existing optional field passthrough (plan, primary, secondary):

```python
    if "models" in parsed:
        entry["models"] = parsed["models"]
    if "activeModel" in parsed:
        entry["activeModel"] = parsed["activeModel"]
    if "sessionSummary" in parsed:
        entry["sessionSummary"] = parsed["sessionSummary"]
```

**Step 2: Test full output**

Run: `~/.local/bin/aibar-collector.py | python3 -m json.tool | head -80`

Expected: Claude entry has `models` array and `activeModel`. Copilot entry has `tokensIn`/`tokensOut` counts and optionally `sessionSummary`.

---

### Task 5: Verify End-to-End

**Step 1: Run collector and validate JSON schema**

Run: `~/.local/bin/aibar-collector.py | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d['tools']['claude']
assert 'models' in c, 'Missing models'
assert 'activeModel' in c, 'Missing activeModel'
assert len(c['models']) > 0, 'Empty models array'
assert c['models'][0]['name'] != c['models'][0]['id'], 'Friendly name not applied'
p = d['tools']['copilot']
print('Claude models:', [m['name'] for m in c['models']])
print('Claude active:', c.get('activeModel'))
print('Copilot interactions:', p.get('tokensIn', 0), 'in /', p.get('tokensOut', 0), 'out')
print('All checks passed')
"`

Expected: `All checks passed` with model names like `['Opus 4.6', 'Haiku 4.5']`.

**Step 2: Restart Quickshell and verify**

Run: `killall qs; sleep 1; nohup qs -c ii > /tmp/qs-final.txt 2>&1 & sleep 4 && grep -i "error" /tmp/qs-final.txt | grep -iv "mapFromItem\|brightness\|QFont"`

Expected: No errors. AIBar popup shows per-model rows under Claude Code section.

**Step 3: Verify backward compatibility**

Old fields (`quotaUsed`, `costToday`, `tokensIn`, `tokensOut`, `status`, `plan`, `color`) still present alongside new `models`, `activeModel`, `sessionSummary` fields.
