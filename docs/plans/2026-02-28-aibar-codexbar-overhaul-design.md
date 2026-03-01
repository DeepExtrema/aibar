# AIBar CodexBar-Style Overhaul Design

## Goal

Restyle AIBar to match [CodexBar](https://github.com/steipete/CodexBar) as closely as possible within Quickshell's QML framework. CodexBar is a macOS menu bar app that monitors AI tool quotas with capsule progress bars, rate windows, and provider-specific accent colors.

## Data Model (status.json)

Expand the flat format to support rate windows. Backward-compatible with existing `quotaUsed` field.

```json
{
  "lastUpdate": "2026-02-28T22:43:40Z",
  "tools": {
    "claude": {
      "letter": "C",
      "name": "Claude Code",
      "color": "#D97757",
      "active": true,
      "status": "ok",
      "primary": {
        "usedPercent": 16.6,
        "windowMinutes": 300,
        "resetsAt": "2026-02-28T23:00:00Z",
        "label": "Session"
      },
      "secondary": {
        "usedPercent": 45.0,
        "windowMinutes": 10080,
        "resetsAt": "2026-03-03T00:00:00Z",
        "label": "Weekly"
      },
      "costToday": 33.19,
      "tokensIn": 366698,
      "tokensOut": 369527,
      "plan": "Max",
      "quotaUsed": 0.166
    }
  }
}
```

New fields per tool:
- `color` (string): Hex accent color for progress bars
- `primary` (object|null): Primary rate window (session)
- `secondary` (object|null): Secondary rate window (weekly)
- `plan` (string|null): Plan name

Rate window object:
- `usedPercent` (number): 0-100
- `windowMinutes` (int|null): Window duration
- `resetsAt` (string|null): ISO 8601 reset time
- `label` (string): Display label ("Session", "Weekly")

## Bar Indicators (AIBarIndicator.qml)

Replace circular progress rings with horizontal capsule progress bars.

Layout per indicator:
```
 C [████████░░░░] 83%
```

- Letter: small DemiBold text, provider-colored
- Capsule bar: ~50px wide, 6px tall, rounded ends (radius: height/2)
  - Track: `Appearance.m3colors.m3surfaceContainerHigh`
  - Fill: provider's `color` field (fallback to `Appearance.colors.colPrimary`)
  - Value: remaining percent from primary rate window, or `(1 - quotaUsed) * 100` fallback
- Percentage: small text, right-aligned
- Warning: fill turns error color when used > threshold (70%)

## Popup (AIBarPopup.qml)

Per-provider card sections with dividers.

Per provider section:
1. Header row: status dot (provider-colored) + tool name (bold) + "running" badge
2. Plan info (if available)
3. Per rate window (primary, then secondary if present):
   - Label + "XX% remaining" right-aligned
   - Capsule progress bar (provider-colored, full width)
   - Reset countdown text ("Resets in Xh Ym" or "Resets Mar 3")
4. Metrics row: cost, tokens in, tokens out (compact, icon + value)
5. Divider between providers

Footer: "Updated HH:MM:SS" right-aligned.

## Files Changed

| File | Change |
|------|--------|
| `services/AIBar.qml` | Parse new fields (primary, secondary, color, plan), backward compat |
| `modules/ii/bar/aibar/AIBarIndicator.qml` | Replace CircularProgress with capsule bar layout |
| `modules/ii/bar/aibar/AIBarGroup.qml` | Adjust spacing for wider indicators |
| `modules/ii/bar/aibar/AIBarPopup.qml` | Full redesign with provider cards and progress bars |

No new files needed. Uses existing `StyledProgressBar` or inline Rectangle-based capsule bars.

## Backward Compatibility

- If `primary` is absent, fall back to `quotaUsed` (multiply by 100 for percent)
- If `color` is absent, use `Appearance.colors.colPrimary`
- If `secondary` is absent, only show one progress bar
- Existing status.json format continues to work
