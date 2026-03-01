# AIBar Collector — Real Quota Scraping Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade aibar-collector.py to output real rate window data (primary/secondary with usedPercent, resetsAt) and provider colors by parsing locally-cached data from Claude Code and Codex CLI, plus improved heuristics for GitHub Copilot.

**Architecture:** Enhance the existing Python script. Codex CLI already caches structured rate limit data in session JSONL files — parse the latest `token_count` event for exact used_percent, window_minutes, and resets_at. Claude Code stores subscription tier in telemetry — use that to improve the quota heuristic. Add provider colors and plan info to output. No external API calls needed.

**Tech Stack:** Python 3, stdlib only (json, pathlib, datetime, glob). No pip dependencies.

---

### Task 1: Add Provider Colors and Plan to TOOL_DEFS

**Files:**
- Modify: `~/.local/bin/aibar-collector.py:21-64`

**Step 1: Add `color` and default `plan` to each tool definition**

Replace the TOOL_DEFS dict with:

```python
TOOL_DEFS = {
    "claude": {
        "letter": "C",
        "name": "Claude Code",
        "color": "#D97757",
        "process_names": ["claude"],
        "data_dir": Path.home() / ".claude",
    },
    "codex": {
        "letter": "X",
        "name": "Codex CLI",
        "color": "#10A37F",
        "process_names": ["codex"],
        "data_dir": Path.home() / ".codex",
    },
    "openclaw": {
        "letter": "O",
        "name": "OpenClaw",
        "color": "#FF6B35",
        "process_names": ["openclaw"],
        "data_dir": Path.home() / ".openclaw",
    },
    "gemini": {
        "letter": "G",
        "name": "Gemini CLI",
        "color": "#4285F4",
        "process_names": ["gemini"],
        "data_dir": Path.home() / ".config" / "gemini",
    },
    "droid": {
        "letter": "D",
        "name": "Droid",
        "color": "#00C853",
        "process_names": ["droid"],
        "data_dir": Path.home() / ".config" / "droid",
    },
    "opencode": {
        "letter": "N",
        "name": "OpenCode",
        "color": "#FF9800",
        "process_names": ["opencode"],
        "data_dir": Path.home() / ".opencode",
    },
    "copilot": {
        "letter": "P",
        "name": "GitHub Copilot",
        "color": "#7C3AED",
        "process_names": ["github-copilot-cli"],
        "data_dir": Path.home() / ".config" / "Code" / "User" / "globalStorage" / "github.copilot-chat",
    },
}
```

**Step 2: Update `collect_tool_status` to include `color` in output**

Add `"color": tool_def["color"]` to the return dict at line ~235-244.

**Step 3: Test**

Run: `~/.local/bin/aibar-collector.py`
Expected: Output JSON now includes `"color": "#D97757"` etc. for each tool.

---

### Task 2: Parse Codex CLI Rate Limit Data from Session Files

**Files:**
- Modify: `~/.local/bin/aibar-collector.py` — replace `parse_codex` function

**Step 1: Write the new `parse_codex` function**

Codex CLI stores structured rate limit data in session JSONL files at `~/.codex/sessions/YYYY/MM/DD/*.jsonl`. Each file contains `token_count` events with `rate_limits.primary` and `rate_limits.secondary` windows.

Replace the existing `parse_codex` function:

```python
def parse_codex(data_dir: Path) -> dict:
    """Parse Codex CLI session files for real rate limit data."""
    result = {
        "costToday": 0.0, "tokensIn": 0, "tokensOut": 0, "quotaUsed": 0.0,
        "primary": None, "secondary": None,
    }

    sessions_dir = data_dir / "sessions"
    if not sessions_dir.is_dir():
        return result

    # Find the most recent session file
    session_files = sorted(sessions_dir.glob("**/*.jsonl"))
    if not session_files:
        return result

    latest_session = session_files[-1]
    latest_rate_limits = None

    try:
        with open(latest_session, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    payload = entry.get("payload", {})
                    if payload.get("type") == "token_count" and payload.get("rate_limits"):
                        latest_rate_limits = payload["rate_limits"]
                except json.JSONDecodeError:
                    continue
    except OSError:
        return result

    if not latest_rate_limits:
        return result

    # Parse primary window (5-hour session)
    pri = latest_rate_limits.get("primary")
    if pri and pri.get("used_percent") is not None:
        resets_at = pri.get("resets_at")
        result["primary"] = {
            "usedPercent": pri["used_percent"],
            "windowMinutes": pri.get("window_minutes", 300),
            "resetsAt": datetime.fromtimestamp(resets_at, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ) if resets_at else None,
            "label": "Session",
        }
        result["quotaUsed"] = round(pri["used_percent"] / 100.0, 4)

    # Parse secondary window (weekly)
    sec = latest_rate_limits.get("secondary")
    if sec and sec.get("used_percent") is not None:
        resets_at = sec.get("resets_at")
        result["secondary"] = {
            "usedPercent": sec["used_percent"],
            "windowMinutes": sec.get("window_minutes", 10080),
            "resetsAt": datetime.fromtimestamp(resets_at, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ) if resets_at else None,
            "label": "Weekly",
        }
        # Use the worse of primary/secondary for quotaUsed
        result["quotaUsed"] = round(
            max(result["quotaUsed"], sec["used_percent"] / 100.0), 4
        )

    return result
```

**Step 2: Test**

Run: `~/.local/bin/aibar-collector.py | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['tools']['codex'], indent=2))"`
Expected: Codex output now has `"primary": {...}` and `"secondary": {...}` with real usedPercent and resetsAt values from the latest session.

---

### Task 3: Improve Claude Code Quota Parsing

**Files:**
- Modify: `~/.local/bin/aibar-collector.py` — enhance `parse_claude` function

**Step 1: Extract subscription tier from telemetry for plan info**

Claude Code stores `subscriptionType` and `rateLimitTier` in telemetry files at `~/.claude/telemetry/`. Parse these to get the plan name and use tier-appropriate quota heuristic.

Replace the existing `parse_claude` function:

```python
def parse_claude(data_dir: Path) -> dict:
    """Parse Claude Code backup and telemetry data for cost, tokens, and plan."""
    result = {
        "costToday": 0.0, "tokensIn": 0, "tokensOut": 0, "quotaUsed": 0.0,
        "plan": None,
    }

    # --- Extract plan info from telemetry ---
    telemetry_dir = data_dir / "telemetry"
    if telemetry_dir.is_dir():
        for tf in sorted(telemetry_dir.glob("1p_failed_events.*.json"), reverse=True):
            try:
                with open(tf, "r") as f:
                    tdata = json.load(f)
                events = tdata if isinstance(tdata, list) else [tdata]
                for ev in events:
                    attrs = ev.get("user_attributes", {})
                    sub_type = attrs.get("subscriptionType")
                    if sub_type:
                        result["plan"] = sub_type.capitalize()
                        break
            except (json.JSONDecodeError, OSError):
                continue
            if result["plan"]:
                break

    # --- Parse cost and tokens from backups ---
    backups_dir = data_dir / "backups"
    if not backups_dir.is_dir():
        return result

    backup_files = sorted(backups_dir.glob(".claude.json.backup.*"))
    if not backup_files:
        return result

    latest = backup_files[-1]
    try:
        with open(latest, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return result

    projects = data.get("projects", {})
    if not isinstance(projects, dict):
        return result

    total_cost = 0.0
    total_in = 0
    total_out = 0

    for proj_data in projects.values():
        if not isinstance(proj_data, dict):
            continue
        total_cost += proj_data.get("lastCost", 0) or 0
        total_in += proj_data.get("lastTotalInputTokens", 0) or 0
        total_out += proj_data.get("lastTotalOutputTokens", 0) or 0

    result["costToday"] = round(total_cost, 4)
    result["tokensIn"] = total_in
    result["tokensOut"] = total_out

    # Estimate quota based on plan tier
    # Max plan: ~$200/day equivalent, Pro: ~$20/day
    plan_budget = 200.0 if (result["plan"] or "").lower() == "max" else 20.0
    if total_cost > 0:
        result["quotaUsed"] = round(min(total_cost / plan_budget, 1.0), 4)

    return result
```

**Step 2: Test**

Run: `~/.local/bin/aibar-collector.py | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['tools']['claude'], indent=2))"`
Expected: Claude output now has `"plan": "Max"` (or "Pro" etc.) based on telemetry data.

---

### Task 4: Update `collect_tool_status` for Expanded Output

**Files:**
- Modify: `~/.local/bin/aibar-collector.py` — update `collect_tool_status` function

**Step 1: Include new fields in the output dict**

Replace `collect_tool_status`:

```python
def collect_tool_status(key: str, tool_def: dict) -> dict:
    """Collect full status for a single tool."""
    active = is_process_active(tool_def["process_names"])

    parser = PARSERS.get(key)
    if parser and tool_def["data_dir"].is_dir():
        parsed = parser(tool_def["data_dir"])
    else:
        parsed = {"costToday": 0.0, "tokensIn": 0, "tokensOut": 0, "quotaUsed": 0.0}

    quota = parsed.get("quotaUsed", 0.0)

    result = {
        "letter": tool_def["letter"],
        "name": tool_def["name"],
        "color": tool_def["color"],
        "active": active,
        "quotaUsed": quota,
        "costToday": parsed.get("costToday", 0.0),
        "tokensIn": parsed.get("tokensIn", 0),
        "tokensOut": parsed.get("tokensOut", 0),
        "status": quota_status(quota),
    }

    # Add optional expanded fields
    if parsed.get("plan"):
        result["plan"] = parsed["plan"]
    if parsed.get("primary"):
        result["primary"] = parsed["primary"]
    if parsed.get("secondary"):
        result["secondary"] = parsed["secondary"]

    return result
```

**Step 2: Test full output**

Run: `~/.local/bin/aibar-collector.py`
Expected: Full JSON with `color`, `plan`, `primary`, `secondary` fields where available. Codex should have primary/secondary rate windows. Claude should have plan info.

**Step 3: Verify QML picks it up**

Wait ~5 seconds for the QML timer to poll, then hover over the AIBar. The popup should now show real rate window data for Codex (Session/Weekly with actual percentages and reset times).

---

### Task 5: Verify End-to-End and Clean Up

**Step 1: Run the collector manually and verify output format**

Run: `~/.local/bin/aibar-collector.py | python3 -m json.tool`
Expected: Valid JSON with all tools, colors, and expanded fields.

**Step 2: Restart the systemd timer**

Run: `systemctl --user restart aibar-collector.timer && systemctl --user status aibar-collector.timer`
Expected: Timer active, next trigger in ~30 seconds.

**Step 3: Verify Quickshell displays real data**

Run: `killall qs; sleep 1; nohup qs -c ii > /tmp/qs-final.txt 2>&1 & sleep 5 && grep -i "error" /tmp/qs-final.txt | grep -iv "mapFromItem\|brightness"`
Expected: No errors. Bar shows capsule with average remaining. Popup shows real rate windows for Codex with reset countdowns.

**Step 4: Verify backward compatibility**

The old flat fields (`quotaUsed`, `costToday`, `tokensIn`, `tokensOut`, `status`) are still present alongside new fields. QML handles both formats.
