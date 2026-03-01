# AIBar

A Quickshell status bar widget that monitors AI coding tool usage in real-time. Tracks quota limits, token consumption, and costs across multiple AI tools.

![License](https://img.shields.io/badge/license-MIT-blue)

## Features

- **Real-time quota tracking** for Claude Code, Codex CLI, and GitHub Copilot CLI
- **Claude Code** — Real usage data via Anthropic OAuth API (session, weekly all-models, weekly Sonnet-only windows with progress bars and reset countdowns)
- **Codex CLI** — Parses local session JSONL files for primary/secondary rate limit windows
- **GitHub Copilot CLI** — Tracks interactions from session event logs
- **OpenClaw** — Token usage monitoring (displayed in popup footer)
- **Per-model cost/token breakdown** for Claude Code (Opus, Sonnet, Haiku)
- **Single capsule indicator** on the bar showing average usage across all enabled tools
- **Rich popup** with per-provider cards, progress bars, reset countdowns, and cost metrics
- **Double-click to refresh** data immediately

## Architecture

```
aibar-collector.py (every 30s via systemd timer)
    |
    v
~/.cache/aibar/status.json
    |
    v
AIBar.qml (Quickshell service, reads JSON every 5s)
    |
    v
AIBarGroup.qml / AIBarIndicator.qml / AIBarPopup.qml
```

## Requirements

- [Quickshell](https://github.com/quickshell-mirror/quickshell) (QML-based shell)
- Python 3.10+
- systemd (user timer)
- One or more supported AI tools installed

## Installation

```bash
git clone https://github.com/DeepExtrema/aibar.git
cd aibar
./install.sh
```

Or manually:

```bash
# Collector script
cp collector/aibar-collector.py ~/.local/bin/
chmod +x ~/.local/bin/aibar-collector.py

# Systemd timer
cp systemd/aibar-collector.service ~/.config/systemd/user/
cp systemd/aibar-collector.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now aibar-collector.timer

# Quickshell modules (adjust paths to match your Quickshell config)
cp quickshell/services/AIBar.qml ~/.config/quickshell/<your-config>/services/
cp quickshell/modules/aibar/*.qml ~/.config/quickshell/<your-config>/modules/<your-bar>/aibar/
```

## Configuration

### Enabled Tools

Edit `AIBar.qml` to change which tools appear in the bar:

```qml
property var enabledTools: ["claude", "codex", "copilot"]
```

### Claude Code Real Usage

The collector automatically reads your OAuth token from `~/.claude/.credentials.json` to fetch real quota data from the Anthropic API. No manual configuration needed — just have Claude Code installed and authenticated.

### Supported Tools

| Tool | Key | Data Source |
|------|-----|-------------|
| Claude Code | `claude` | OAuth API + local backups/telemetry |
| Codex CLI | `codex` | Local session JSONL files |
| GitHub Copilot CLI | `copilot` | Local event logs |
| OpenClaw | `openclaw` | Local session files |
| Gemini CLI | `gemini` | Process detection only |
| Droid | `droid` | Process detection only |
| OpenCode | `opencode` | Process detection only |

## Output Format

The collector writes `~/.cache/aibar/status.json` every 30 seconds:

```json
{
  "lastUpdate": "2026-03-01T22:00:00Z",
  "tools": {
    "claude": {
      "letter": "C",
      "name": "Claude Code",
      "color": "#D97757",
      "active": true,
      "quotaUsed": 0.36,
      "status": "ok",
      "plan": "Max",
      "activeModel": "Opus",
      "rateWindows": [
        {"usedPercent": 36.0, "resetsAt": "2026-03-06T04:00:00Z", "label": "Weekly"},
        {"usedPercent": 32.0, "resetsAt": "2026-03-02T00:00:00Z", "label": "Session"},
        {"usedPercent": 6.0, "resetsAt": "2026-03-06T13:00:00Z", "label": "Sonnet only"}
      ],
      "models": [
        {"id": "claude-opus-4-6", "name": "Opus 4.6", "tokensIn": 20005, "tokensOut": 278437, "cost": 30.67}
      ],
      "costToday": 33.19,
      "tokensIn": 366698,
      "tokensOut": 369527
    }
  }
}
```

## License

MIT
