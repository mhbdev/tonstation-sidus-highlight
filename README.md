# Ton Station Weekly Highlight Builder

Production-ready Telegram agent that collects Ton Station channel/group messages, curates weekly highlights with DeepSeek via SidusAI, and posts/prints a Markdown digest.

## Features
- Collect channel posts and group messages where the bot is present; store in SQLite.
- Summarize last N days (default 7) into a digest: quick stats, top threads, emerging topics, recommended pins/actions.
- Send digest to a target chat/channel or print locally.
- `/chatid` command to return the current chat ID (even before configuring `SOURCE_CHAT_ID`).
- Fault-tolerant polling with graceful Ctrl+C handling.

## Project Layout
- `tonstation/config.py` – environment-driven settings.
- `tonstation/storage.py` – SQLite persistence for Telegram messages.
- `tonstation/highlight_agent.py` – SidusAI + DeepSeek summarization agent.
- `tonstation/collector_service.py` – Telegram collector to ingest channel/group messages.
- `tonstation/digest_builder.py` – Digest generation and optional delivery.
- `tonstation/run_highlight.py` – One-shot CLI to build/send/print the digest.
- `tonstation/requirements.txt` – dependencies (installs local SidusAI in editable mode).
- `tonstation/.env.example` – sample environment configuration.
- `tonstation/.gitignore` – local ignores (env, db, pycache, editor files).

## Prerequisites
- Python 3.10+
- Telegram bot token; bot added to your channel/group (admin for channels to receive `channel_post`).
- DeepSeek API key and a valid model (default `deepseek-chat`).
- SQLite (bundled with Python).

## Setup
1) Install dependencies (run either from repo root or from `tonstation/`):
```bash
# from repo root
python -m pip install -r tonstation/requirements.txt
# or from tonstation/
cd tonstation && python -m pip install -r requirements.txt
```
2) Copy and fill env (can be placed in repo root or inside `tonstation/`; loader checks both):
```bash
# from repo root
cp tonstation/.env.example .env
# or inside tonstation/
cd tonstation && cp .env.example .env
```
Required:
- `TG_BOT_TOKEN` – Telegram bot token.
- `SOURCE_CHAT_ID` – channel/group id (e.g., `-1001234567890`).
- `DEEPSEEK_API_KEY` – DeepSeek API key.
Optional:
- `HIGHLIGHT_TARGET_CHAT_ID` – where to send digests; if empty, digest prints.
- `DEEPSEEK_MODEL`, `DB_PATH`, `WINDOW_DAYS`, `TOP_N_MESSAGES`, `POLLING_TIMEOUT`, `POLLING_INTERVAL`.

## Commands (run from repo root or from tonstation/)
- Run collector (ingest messages):
```bash
python -m tonstation.collector_service
```
  - Use `/chatid` in the channel/group to get its ID.
- Build and send digest (uses `HIGHLIGHT_TARGET_CHAT_ID` if set):
```bash
python -m tonstation.digest_builder
```
- Print-only:
```bash
python -m tonstation.digest_builder --no-send
```
- One-shot helper:
```bash
python -m tonstation.run_highlight              # send to HIGHLIGHT_TARGET_CHAT_ID
python -m tonstation.run_highlight --print-only # just print
python -m tonstation.run_highlight --target -1001234567890 # override target once
```

## Notes for production
- Keep the collector running as a service (systemd/Docker); schedule digest via cron/GitHub Actions.
- Ensure outbound network for DeepSeek API.
- SQLite file is created automatically at `DB_PATH`; back it up if needed.

## License
MIT
