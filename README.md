# Ton Station Highlight & Analytics

Telegram analytics toolkit that:
- Collects public channel posts **without adding a bot** (user session via Telethon).
- Manages a list of channels and tags/keywords to watch.
- Runs aggregated analytics per channel and per tag (counts, reach, direct links).
- Builds an LLM-powered digest of recent activity (optional; uses DeepSeek via SidusAI).

## Features
- Botless fetch (Telethon): read public channels with API ID/hash + user session.
- Channel & tag management: CLI to add/list/remove channels and tags.
- Date filters: analyze any interval via `--from/--to` or window-based `--days`.
- Aggregated analytics: per-channel/per-tag hit counts, reach (views), and direct links.
- Optional bot send: deliver analytics/digests to a Telegram chat or print locally.
- Legacy bot collector: still available for bot-present channels/groups.

## Project Layout
- `tonstation/config.py` — environment-driven settings.
- `tonstation/storage.py` — SQLite persistence for channels, tags, and messages.
- `tonstation/cli.py` — channel/tag management, botless fetch, analytics CLI.
- `tonstation/highlight_agent.py` — SidusAI + DeepSeek summarization agent.
- `tonstation/digest_builder.py` — digest generation and optional delivery.
- `tonstation/collector_service.py` — legacy bot-based collector.
- `tonstation/run_highlight.py` — one-shot helper to build/send/print the digest.
- `tonstation/.env.example` — sample environment configuration.

## Prerequisites
- Python 3.10+
- Telegram API ID & API hash (for botless fetch; create at my.telegram.org).
- Optional: Telegram bot token (`TG_BOT_TOKEN`) if sending analytics/digests.
- Optional: DeepSeek API key if you want the LLM digest.
- SQLite (bundled with Python).

## Setup
1) Install dependencies (repo root or `tonstation/`):
```bash
# from repo root
python -m pip install -r tonstation/requirements.txt
# or from tonstation/
cd tonstation && python -m pip install -r requirements.txt
```
2) Copy and fill env (loader checks repo root, tonstation/, cwd):
```bash
# from repo root
cp tonstation/.env.example .env
# or inside tonstation/
cd tonstation && cp .env.example .env
```
Key settings:
- `TG_API_ID`, `TG_API_HASH`, `TG_SESSION_PATH` — required for botless fetch.
- `TG_BOT_TOKEN`, `HIGHLIGHT_TARGET_CHAT_ID` — only if sending via bot.
- `DEEPSEEK_API_KEY` — only for LLM digest.
- `DB_PATH`, `WINDOW_DAYS`, `TOP_N_MESSAGES` — storage/digest tuning.

## Botless channel management & analytics (AG-1)
Run from repo root or `tonstation/`:
```bash
# Add channels (public @username or link)
python -m tonstation.cli channels add https://t.me/example_channel
python -m tonstation.cli channels list

# Manage tags
python -m tonstation.cli tags add airdrop
python -m tonstation.cli tags add TON
python -m tonstation.cli tags list

# Fetch posts (default WINDOW_DAYS)
python -m tonstation.cli fetch --days 7
# Custom interval
python -m tonstation.cli fetch --from 2025-01-01 --to 2025-01-31

# Analytics (prints by default)
python -m tonstation.cli analyze --days 7
# Send analytics to Telegram
python -m tonstation.cli analyze --days 7 --send --target -1001234567890
```
Analytics output covers:
- Which channels had keyword hits.
- Counts per tag and per channel.
- Reach (views) per tag and per channel.
- Direct links to matching posts.

## LLM Digest (optional)
Generate weekly digest (DeepSeek required):
```bash
# send to HIGHLIGHT_TARGET_CHAT_ID if set
python -m tonstation.digest_builder
# print only
python -m tonstation.digest_builder --no-send
# one-shot helper
python -m tonstation.run_highlight --target -1001234567890
```

## Legacy bot collector (optional)
```bash
python -m tonstation.collector_service
```
- Requires `TG_BOT_TOKEN` and `SOURCE_CHAT_ID` (bot must be in the channel/group).
- Use `/chatid` in the channel/group to discover its ID.

## Data & paths
- Database: `DB_PATH` (default `tonstation/data/messages.db`).
- Telethon session: `TG_SESSION_PATH` (default `tonstation/data/tg_session.session`).
- Both paths should be writable where the process runs.

## Testing
```bash
python -m pip install pytest pytest-cov
python -m pytest --maxfail=1 --disable-warnings --cov=tonstation --cov-report=term-missing
```
Tests stub external services; no network/Telegram calls are made during test runs.

## Production notes
- Schedule `fetch` and `analyze` (cron/systemd/GitHub Actions) as needed.
- Keep Telethon session and DB paths on persistent storage; secure secrets via env or a secret manager.
- Ensure outbound network for DeepSeek if using the digest.

## License
MIT
