# Claude Code Real Usage API — Design

## Goal

Replace the inaccurate cost-based quota heuristic for Claude Code with real rate limit data from the Anthropic OAuth usage API, matching the claude.ai usage page exactly.

## Data Source

**Endpoint:** `GET https://api.anthropic.com/api/oauth/usage`

**Auth:** OAuth token from `~/.claude/.credentials.json` → `claudeAiOauth.accessToken`

**Headers:** `Authorization: Bearer <token>`, `anthropic-beta: oauth-2025-04-20`

**Response:**
```json
{
  "five_hour": {"utilization": 16.0, "resets_at": "2026-03-02T00:00:00Z"},
  "seven_day": {"utilization": 35.0, "resets_at": "2026-03-06T04:00:00Z"},
  "seven_day_sonnet": {"utilization": 6.0, "resets_at": "2026-03-06T13:00:00Z"},
  "seven_day_opus": null,
  "extra_usage": {"is_enabled": false, ...}
}
```

## Mapping

| API field | Output field | Label |
|-----------|-------------|-------|
| `five_hour` | `rateWindows[N]` | "Session" |
| `seven_day` | `rateWindows[N]` | "Weekly" |
| `seven_day_sonnet` | `rateWindows[N]` | "Sonnet only" |
| `seven_day_opus` | `rateWindows[N]` | "Opus only" (if non-null) |

## Collector Output (Claude entry)

```json
{
  "primary": {"usedPercent": 35, "resetsAt": "...", "label": "Weekly"},
  "rateWindows": [
    {"usedPercent": 35, "resetsAt": "...", "label": "Weekly"},
    {"usedPercent": 16, "resetsAt": "...", "label": "Session"},
    {"usedPercent": 6, "resetsAt": "...", "label": "Sonnet only"}
  ],
  "quotaUsed": 0.35,
  "models": [...],
  "activeModel": "Opus",
  "plan": "Max"
}
```

- `primary` = worst window (highest utilization). Used by the bar indicator.
- `rateWindows` = all non-null windows, sorted worst-first. Used by the popup.
- `secondary` removed for Claude (replaced by `rateWindows` array).
- Fallback: if API call fails, keep cost heuristic.

## QML Popup Layout

```
Claude Code                    running
Plan: Max  |  Active: Opus

[====----------] 65% remaining
  Resets in 3h 13m

  Weekly      34% used   Resets Thu 11PM
  Session     13% used   Resets in 3h
  Sonnet       6% used   Resets Fri 8AM

  Opus 4.6  $30.67  20K / 278K
  Haiku 4.5  $2.52  346K / 91K
```

- Prominent progress bar for worst window (via existing `primary` rendering)
- Compact detail rows for all windows from `rateWindows` array
- Per-model cost/token rows (already implemented)

## Constraints

- 10-second timeout on API call
- Graceful fallback to cost heuristic on any failure
- No new pip dependencies (use `urllib.request`)
- Token refresh not implemented (Claude Code auto-refreshes; if token is expired, fallback kicks in)
- Undocumented endpoint — may break without notice
