# AIBar Collector — Hybrid Quota Scraping Design

## Goal

Upgrade the aibar-collector.py script to scrape real quota/usage data from Claude Code, Codex CLI, and GitHub Copilot APIs instead of relying on rough heuristics. Output the expanded status.json format with rate windows, provider colors, and reset times.

## Output Format

Expanded status.json with `primary`/`secondary` rate windows, `color`, and `plan` fields per tool. Backward-compatible with existing QML (which already handles both flat and expanded formats).

## Per-Provider Strategy

### Claude Code — Local files + Anthropic API

- **Local** (keep): Parse `~/.claude/backups/` for cost and token usage.
- **API** (new): Call Anthropic usage/billing endpoint for real session and weekly rate window data (usedPercent, resetsAt).
- **Auth**: `ANTHROPIC_API_KEY` from config or env var.
- **Fallback**: Cost-based heuristic (`cost / $200`) if API fails.

### Codex CLI — Local files + OpenAI API

- **Local** (keep): Parse `~/.codex/history.jsonl` for session counts.
- **API** (new): Call OpenAI API to check rate limit status via response headers.
- **Auth**: `OPENAI_API_KEY` from config or env var.
- **Fallback**: Session count heuristic (`sessions / 50`) if API fails.

### GitHub Copilot — GitHub API + VS Code storage

- **API** (new): Call GitHub REST API `/user/copilot/usage` for usage metrics.
- **Local** (new): Parse VS Code extension storage for session data.
- **Auth**: `GITHUB_TOKEN` from config or env var.
- **Fallback**: Default to inactive/0 if both fail.

## Config

API keys in `~/.config/aibar/config.json`:

```json
{
  "anthropic_api_key": "sk-ant-...",
  "openai_api_key": "sk-...",
  "github_token": "ghp_..."
}
```

Falls back to environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GITHUB_TOKEN`).

## Architecture

- Same single script: `~/.local/bin/aibar-collector.py`
- Same systemd timer: 30-second interval
- No new pip dependencies — use `urllib.request` from stdlib
- Each API call has a 10-second timeout and graceful fallback
- Provider colors hardcoded in TOOL_DEFS (e.g., Claude=#D97757, Codex=#10A37F, Copilot=#7C3AED)

## Constraints

- Script must complete within 30 seconds (timer interval)
- All API calls are best-effort with fallback to local data
- Atomic writes preserved (temp file + rename)
- No breaking changes to existing output — old fields still present alongside new ones
