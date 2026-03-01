#!/usr/bin/env python3
"""
AIBar Collector - Aggregates AI tool usage data into a JSON status file.

Called every 30s by a systemd user timer. Reads local data from Claude Code,
Codex CLI, OpenClaw, and others, detects active processes, and writes
aggregated JSON to ~/.cache/aibar/status.json using atomic writes.
"""

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

CACHE_DIR = Path.home() / ".cache" / "aibar"
STATUS_FILE = CACHE_DIR / "status.json"

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
        "data_dir": Path.home() / ".local" / "state" / ".copilot",
    },
}


def is_process_active(process_names: list[str]) -> bool:
    """Check if any of the given process names are running via pgrep."""
    for name in process_names:
        try:
            result = subprocess.run(
                ["pgrep", "-f", name],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return False


def quota_status(quota_used: float) -> str:
    """Return status string based on quota usage fraction."""
    if quota_used >= 1.0:
        return "limited"
    if quota_used >= 0.7:
        return "warning"
    return "ok"


CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

def fetch_claude_usage(data_dir: Path) -> dict | None:
    """Fetch real rate limit data from Anthropic OAuth usage API."""
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

    windows.sort(key=lambda w: w["usedPercent"], reverse=True)

    return {
        "rateWindows": windows,
        "primary": windows[0],
        "quotaUsed": round(windows[0]["usedPercent"] / 100.0, 4),
    }


def parse_claude(data_dir: Path) -> dict:
    """Parse Claude Code backup and telemetry data for cost, token usage, and plan."""
    result = {"costToday": 0.0, "tokensIn": 0, "tokensOut": 0, "quotaUsed": 0.0}

    # --- Try real API data first ---
    api_data = fetch_claude_usage(data_dir)
    if api_data:
        result["rateWindows"] = api_data["rateWindows"]
        result["primary"] = api_data["primary"]
        result["quotaUsed"] = api_data["quotaUsed"]

    # --- Detect plan from telemetry ---
    # Telemetry files are JSONL (one JSON object per line).
    # subscriptionType lives at: event_data.user_attributes (stringified JSON) -> subscriptionType
    plan = None
    budget = 200.0  # default Max budget
    telemetry_dir = data_dir / "telemetry"
    if telemetry_dir.is_dir():
        telem_files = sorted(telemetry_dir.glob("1p_failed_events.*.json"))
        for tfile in reversed(telem_files):
            try:
                with open(tfile, "r") as f:
                    for line in reversed(f.readlines()):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        # user_attributes may be at top level or inside event_data
                        attrs_raw = event.get("user_attributes")
                        if not attrs_raw:
                            event_data = event.get("event_data", {})
                            if isinstance(event_data, dict):
                                attrs_raw = event_data.get("user_attributes")
                        if not attrs_raw:
                            continue
                        # user_attributes may be a JSON string that needs parsing
                        if isinstance(attrs_raw, str):
                            try:
                                attrs_raw = json.loads(attrs_raw)
                            except json.JSONDecodeError:
                                continue
                        if isinstance(attrs_raw, dict):
                            sub_type = attrs_raw.get("subscriptionType")
                            if sub_type:
                                plan = sub_type.capitalize()
                                break
            except OSError:
                continue
            if plan:
                break

    if plan:
        result["plan"] = plan
        if plan.lower() == "pro":
            budget = 20.0
        else:
            budget = 200.0

    # --- Parse backup data for cost/tokens ---
    backups_dir = data_dir / "backups"
    if not backups_dir.is_dir():
        return result

    # Find the most recent backup file
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

    # --- Aggregate per-model usage from lastModelUsage ---
    MODEL_FRIENDLY = {
        "claude-opus-4-6": "Opus 4.6",
        "claude-sonnet-4-6": "Sonnet 4.6",
        "claude-haiku-4-5-20251001": "Haiku 4.5",
    }
    model_totals: dict[str, dict] = {}
    for proj_data in projects.values():
        if not isinstance(proj_data, dict):
            continue
        lmu = proj_data.get("lastModelUsage")
        if not isinstance(lmu, dict):
            continue
        for model_id, usage in lmu.items():
            if not isinstance(usage, dict):
                continue
            if model_id not in model_totals:
                model_totals[model_id] = {"tokensIn": 0, "tokensOut": 0, "cost": 0.0}
            model_totals[model_id]["tokensIn"] += usage.get("inputTokens", 0) or 0
            model_totals[model_id]["tokensOut"] += usage.get("outputTokens", 0) or 0
            model_totals[model_id]["cost"] += usage.get("costUSD", 0) or 0

    if model_totals:
        models = []
        for mid, mt in sorted(model_totals.items(), key=lambda x: x[1]["cost"], reverse=True):
            models.append({
                "id": mid,
                "name": MODEL_FRIENDLY.get(mid, mid),
                "tokensIn": mt["tokensIn"],
                "tokensOut": mt["tokensOut"],
                "cost": round(mt["cost"], 4),
            })
        result["models"] = models

    # --- Read active model from settings.json ---
    settings_file = data_dir / "settings.json"
    try:
        with open(settings_file, "r") as f:
            settings = json.load(f)
        model_val = settings.get("model")
        if model_val and isinstance(model_val, str):
            result["activeModel"] = model_val.capitalize()
    except (json.JSONDecodeError, OSError):
        pass

    # Estimate quota using plan-appropriate budget
    if "quotaUsed" not in result and total_cost > 0:
        result["quotaUsed"] = round(min(total_cost / budget, 1.0), 4)

    return result


def parse_codex(data_dir: Path) -> dict:
    """Parse Codex CLI session JSONL files for rate limit data."""
    result = {"costToday": 0.0, "tokensIn": 0, "tokensOut": 0, "quotaUsed": 0.0}

    sessions_dir = data_dir / "sessions"
    if not sessions_dir.is_dir():
        return result

    # Find the most recent session file by walking year/month/day dirs
    latest_file = None
    latest_mtime = 0.0
    for jsonl_file in sessions_dir.glob("*/*/*/*.jsonl"):
        try:
            mtime = jsonl_file.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = jsonl_file
        except OSError:
            continue

    if latest_file is None:
        return result

    # Scan for the last token_count event with rate_limits
    last_rate_limits = None
    try:
        with open(latest_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    payload = entry.get("payload", {})
                    if (
                        isinstance(payload, dict)
                        and payload.get("type") == "token_count"
                        and "rate_limits" in payload
                    ):
                        last_rate_limits = payload["rate_limits"]
                except json.JSONDecodeError:
                    continue
    except OSError:
        return result

    if last_rate_limits is None:
        return result

    primary_raw = last_rate_limits.get("primary", {})
    secondary_raw = last_rate_limits.get("secondary", {})

    def _build_limit(raw: dict, label: str) -> dict:
        resets_ts = raw.get("resets_at", 0)
        resets_iso = datetime.fromtimestamp(
            resets_ts, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ") if resets_ts else ""
        return {
            "usedPercent": raw.get("used_percent", 0.0),
            "windowMinutes": raw.get("window_minutes", 0),
            "resetsAt": resets_iso,
            "label": label,
        }

    primary = _build_limit(primary_raw, "Session")
    secondary = _build_limit(secondary_raw, "Weekly")

    result["primary"] = primary
    result["secondary"] = secondary

    # quotaUsed is the worse (higher) of the two, converted to 0-1 fraction
    worse_pct = max(primary["usedPercent"], secondary["usedPercent"])
    result["quotaUsed"] = round(min(worse_pct / 100.0, 1.0), 4)

    return result


def parse_openclaw(data_dir: Path) -> dict:
    """Parse OpenClaw session files for today's usage."""
    result = {"costToday": 0.0, "tokensIn": 0, "tokensOut": 0, "quotaUsed": 0.0}

    agents_dir = data_dir / "agents"
    if not agents_dir.is_dir():
        return result

    today_start = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()

    session_count = 0
    for session_file in agents_dir.glob("*/sessions/*.jsonl"):
        try:
            mtime = session_file.stat().st_mtime
            if mtime >= today_start:
                session_count += 1
        except OSError:
            continue

    # Estimate quota: ~20 sessions/day
    result["quotaUsed"] = round(min(session_count / 20.0, 1.0), 4)

    return result


def parse_copilot(data_dir: Path) -> dict:
    """Parse Copilot CLI session data for interaction counts."""
    result = {"costToday": 0.0, "tokensIn": 0, "tokensOut": 0, "quotaUsed": 0.0}

    session_state_dir = data_dir / "session-state"
    if not session_state_dir.is_dir():
        return result

    # Find the most recently modified session (by events.jsonl mtime)
    latest_events = None
    latest_mtime = 0.0
    for session_dir in session_state_dir.iterdir():
        if not session_dir.is_dir():
            continue
        events_file = session_dir / "events.jsonl"
        if not events_file.is_file():
            continue
        try:
            mtime = events_file.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_events = events_file
        except OSError:
            continue

    if latest_events is None:
        return result

    # Count event types as interaction proxies
    user_messages = 0
    assistant_messages = 0
    tool_completions = 0
    try:
        with open(latest_events, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = event.get("type", "")
                if etype == "user.message":
                    user_messages += 1
                elif etype == "assistant.message":
                    assistant_messages += 1
                elif etype == "tool.execution_complete":
                    tool_completions += 1
    except OSError:
        return result

    result["tokensIn"] = user_messages
    result["tokensOut"] = assistant_messages + tool_completions

    # Optionally read session summary from workspace.yaml
    workspace_file = latest_events.parent / "workspace.yaml"
    try:
        with open(workspace_file, "r") as f:
            for line in f:
                if line.startswith("summary:"):
                    summary = line[len("summary:"):].strip()
                    if summary:
                        result["sessionSummary"] = summary
                    break
    except OSError:
        pass

    return result


# Map tool keys to their parser functions
PARSERS = {
    "claude": parse_claude,
    "codex": parse_codex,
    "openclaw": parse_openclaw,
    "copilot": parse_copilot,
}


def collect_tool_status(key: str, tool_def: dict) -> dict:
    """Collect full status for a single tool."""
    active = is_process_active(tool_def["process_names"])

    # Run parser if one exists, otherwise use defaults
    parser = PARSERS.get(key)
    if parser and tool_def["data_dir"].is_dir():
        parsed = parser(tool_def["data_dir"])
    else:
        parsed = {"costToday": 0.0, "tokensIn": 0, "tokensOut": 0, "quotaUsed": 0.0}

    quota = parsed.get("quotaUsed", 0.0)

    entry = {
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

    # Conditionally include expanded fields when present
    if "plan" in parsed:
        entry["plan"] = parsed["plan"]
    if "primary" in parsed:
        entry["primary"] = parsed["primary"]
    if "secondary" in parsed:
        entry["secondary"] = parsed["secondary"]
    if "models" in parsed:
        entry["models"] = parsed["models"]
    if "activeModel" in parsed:
        entry["activeModel"] = parsed["activeModel"]
    if "sessionSummary" in parsed:
        entry["sessionSummary"] = parsed["sessionSummary"]
    if "rateWindows" in parsed:
        entry["rateWindows"] = parsed["rateWindows"]

    return entry


def write_atomic(path: Path, data: str) -> None:
    """Write data to a file atomically via tmp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
        os.rename(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main() -> None:
    tools = {}
    for key, tool_def in TOOL_DEFS.items():
        tools[key] = collect_tool_status(key, tool_def)

    output = {
        "lastUpdate": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tools": tools,
    }

    json_str = json.dumps(output, indent=2) + "\n"
    write_atomic(STATUS_FILE, json_str)

    # Also print to stdout for debugging
    print(json_str, end="")


if __name__ == "__main__":
    main()
