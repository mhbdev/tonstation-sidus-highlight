import argparse
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

import telebot

from tonstation.config import settings
from tonstation.highlight_agent import DEFAULT_SYSTEM_PROMPT, WeeklyHighlightAgent
from tonstation.storage import MessageRecord, MessageStore

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _score(record: MessageRecord) -> int:
    views = record.views or 0
    length_bonus = min(len(record.text) // 120, 5)
    return views * 2 + length_bonus


def pick_top(records: List[MessageRecord], limit: int) -> List[MessageRecord]:
    scored = sorted(records, key=_score, reverse=True)
    return scored[:limit]


def format_record(record: MessageRecord, idx: int) -> str:
    text = record.text.replace('\n', ' ')
    if len(text) > 320:
        text = text[:320].rstrip() + '...'
    author = record.author or record.full_name or 'anon'
    stats = []
    if record.views is not None:
        stats.append(f'views={record.views}')
    stamp = record.date.strftime('%Y-%m-%d')
    return f"{idx}. [{stamp}] @{author}: {text} ({', '.join(stats) if stats else 'stats=n/a'})"


def build_prompt(records: List[MessageRecord], window_days: int) -> str:
    if not records:
        return "No messages were captured in the selected window. Produce a short empty-state note."

    top_records = pick_top(records, settings.top_n_messages)
    authors = {r.author or r.full_name or 'anon' for r in records}
    start = records[0].date.strftime('%Y-%m-%d')
    end = records[-1].date.strftime('%Y-%m-%d')
    stats = (
        f"Window: {start} to {end} UTC ({window_days} days)\n"
        f"Messages: {len(records)} | Unique authors: {len(authors)} | "
        f"Top sample size: {len(top_records)}\n"
    )
    formatted = '\n'.join([format_record(r, idx + 1) for idx, r in enumerate(top_records)])
    instructions = (
        "Use ONLY the provided messages. Do not invent data. "
        "If metrics are missing, skip them. Keep Markdown concise."
    )
    return f"{stats}\nTop messages:\n{formatted}\n\n{instructions}"


def send_digest(bot: telebot.TeleBot, chat_id: str, text: str):
    """
    Send digest to Telegram, splitting if it exceeds Telegram's message limit.
    """
    chunk_size = 3900  # stay under 4096
    if len(text) <= chunk_size:
        bot.send_message(chat_id, text, disable_web_page_preview=True)
        return
    start = 0
    part = 1
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        bot.send_message(chat_id, f"Part {part}:\n{chunk}", disable_web_page_preview=True)
        start = end
        part += 1


def build_and_optionally_send(send: bool = True, target_chat_id: str | None = None) -> str:
    if not settings.deepseek_api_key:
        raise ValueError('DEEPSEEK_API_KEY must be set to build digests.')

    store = MessageStore(settings.db_path)
    try:
        records = store.fetch_since_days(settings.window_days)
        logger.info('Loaded %s messages for last %s days', len(records), settings.window_days)

        prompt = build_prompt(records, settings.window_days)
        agent = WeeklyHighlightAgent(
            api_key=settings.deepseek_api_key,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            model_name=settings.model_name,
        )
        digest_text = agent.build_digest_sync(prompt)

        target = target_chat_id or settings.target_chat_id
        if send and target:
            if not settings.bot_token:
                raise ValueError('TG_BOT_TOKEN is required to send the digest to Telegram.')
            bot = telebot.TeleBot(settings.bot_token, parse_mode=None)
            send_digest(bot, target, digest_text)
            logger.info('Digest sent to %s', target)
        elif send and not target:
            logger.warning('HIGHLIGHT_TARGET_CHAT_ID not set; printing digest locally.')
            print(digest_text)
        else:
            print(digest_text)
        return digest_text
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description='Ton Station weekly highlight builder')
    parser.add_argument('--no-send', action='store_true', help='Do not send to Telegram, just print')
    args = parser.parse_args()
    build_and_optionally_send(send=not args.no_send)


if __name__ == '__main__':
    main()
