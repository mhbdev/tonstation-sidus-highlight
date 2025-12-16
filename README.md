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

### Command examples (real output shapes)
`python -m tonstation.cli` accepts the commands below; outputs reflect the current implementation (logging format `[YYYY-MM-DD HH:MM:SS,mmm] LEVEL - message`).

Channels:
```bash
$ python -m tonstation.cli channels list
No channels stored.

$ python -m tonstation.cli channels add https://t.me/example_channel
[2025-02-01 12:00:00,000] INFO - Added channel -1001234567890 (Example Channel)

$ python -m tonstation.cli channels list --active-only
Example Channel (-1001234567890) [active] link=https://t.me/example_channel

$ python -m tonstation.cli channels remove https://t.me/example_channel
[2025-02-01 12:05:00,000] INFO - Removed channel https://t.me/example_channel
```

Tags:
```bash
$ python -m tonstation.cli tags list
No tags stored.

$ python -m tonstation.cli tags add airdrop
[2025-02-01 12:06:00,000] INFO - Added tag: airdrop
$ python -m tonstation.cli tags add ton
[2025-02-01 12:06:02,000] INFO - Added tag: ton
$ python -m tonstation.cli tags list
- airdrop
- ton

$ python -m tonstation.cli tags remove ton
[2025-02-01 12:06:05,000] INFO - Removed tag: ton
```

Fetch (botless Telethon client; stores matching window in SQLite):
```bash
$ python -m tonstation.cli fetch --days 1 --max-per-channel 10
[2025-02-01 12:10:00,000] INFO - Fetching messages between 2025-02-01 11:10 UTC and 2025-02-01 12:10 UTC
[2025-02-01 12:10:00,100] INFO - Fetching Example Channel
[2025-02-01 12:10:01,200] INFO - Stored 4 messages for -1001234567890
```

Analyze (prints by default; same data shape used when sending):
```bash
$ python -m tonstation.cli analyze --days 1
Analytics window: 2025-02-01 11:10 UTC -> 2025-02-01 12:10 UTC
Total hits: 2 | Channels with hits: 1 | Tags matched: 2

Per channel:
- Example Channel: 2 posts, reach=150

Per tag:
- ton: 2 posts, reach=150
- airdrop: 1 posts, reach=120

Matched posts:
- Example Channel [2025-02-01] tags=ton, airdrop (views=120) -> https://t.me/example_channel/10
  TON airdrop launching soon for early users.
- Example Channel [2025-02-01] tags=ton (views=30) -> https://t.me/example_channel/11
  TON dev update: new wallets released...
```

Analyze (send to Telegram; requires `TG_BOT_TOKEN` and target chat id):
```bash
$ python -m tonstation.cli analyze --days 1 --send --target -1009998887777
[2025-02-01 12:12:00,000] INFO - Analytics report sent to -1009998887777
```

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
Digest printing (content is whatever the model returns; structure follows the system prompt):
```bash
$ python -m tonstation.digest_builder --no-send
[2025-02-01 12:20:00,000] INFO - Loaded 42 messages for last 7 days
Weekly Highlight Digest

1) Quick stats
- Window: 2025-01-25 to 2025-02-01 UTC (7 days); Messages: 42; Unique authors: 18; Top sample size: 12

2) Top threads
- TON staking upgrade landed; validators outlining migration steps...

3) Emerging topics
- Wallet UX refresh; new TON DeFi farms with rising TVL...

4) Recommended pins/actions
- Pin the staking upgrade guide; prepare FAQ on DeFi risks.
```

`python -m tonstation.run_highlight --print-only` produces the same digest text locally; omitting `--print-only` and setting `--target` or `HIGHLIGHT_TARGET_CHAT_ID` sends it via the bot.

## Legacy bot collector (optional)
```bash
python -m tonstation.collector_service
```
- Requires `TG_BOT_TOKEN` and `SOURCE_CHAT_ID` (bot must be in the channel/group).
- Use `/chatid` in the channel/group to discover its ID.
- Typical runtime output:
```bash
$ python -m tonstation.collector_service
[2025-02-01 12:30:00,000] INFO - Starting collector for chat -1001234567890
[2025-02-01 12:30:05,000] INFO - Stored channel post 245
```

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
