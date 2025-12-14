import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import telebot
from telethon import TelegramClient
from telethon.errors import RPCError

from tonstation.config import settings
from tonstation.digest_builder import send_digest
from tonstation.storage import (
    ChannelRecord,
    MessageRecord,
    MessageStore,
    TagRecord,
    build_message_link,
)

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ----------- Date helpers -----------
def _parse_date(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_range(args) -> Tuple[datetime, datetime]:
    if args.from_date or args.to_date:
        end = _parse_date(args.to_date) if args.to_date else datetime.now(tz=timezone.utc)
        start = _parse_date(args.from_date) if args.from_date else end - timedelta(days=settings.window_days)
        return start, end
    # default window
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=args.days or settings.window_days)
    return start, end


# ----------- Telegram client helpers -----------
def _require_api_credentials():
    if settings.tg_api_id is None or settings.tg_api_hash is None:
        raise ValueError('TG_API_ID and TG_API_HASH must be set to use the Telegram client.')


def _build_client() -> TelegramClient:
    _require_api_credentials()
    return TelegramClient(settings.tg_session_path, settings.tg_api_id, settings.tg_api_hash)


async def _resolve_channel(client: TelegramClient, identifier: str) -> ChannelRecord:
    entity = await client.get_entity(identifier)
    # Telethon returns positive ids; align with bot-style -100 prefix for channels
    chat_id = str(entity.id)
    if not chat_id.startswith('-100'):
        chat_id = f"-100{chat_id}"
    username = getattr(entity, 'username', None)
    link = f"https://t.me/{username}" if username else None
    title = getattr(entity, 'title', None)
    access_hash = getattr(entity, 'access_hash', None)
    return ChannelRecord(
        chat_id=chat_id,
        title=title,
        username=username,
        link=link,
        access_hash=access_hash,
    )


async def _iter_messages_for_channel(
    client: TelegramClient,
    channel: ChannelRecord,
    start: datetime,
    end: datetime,
    max_messages: Optional[int],
) -> Iterable[MessageRecord]:
    """
    Yield MessageRecords for a channel between start/end (UTC).
    """
    # Prefer resolving by username/link; fall back to numeric id
    identifier = channel.username or channel.link or int(channel.chat_id.replace('-100', ''))
    processed = 0
    async for msg in client.iter_messages(identifier, limit=max_messages):
        if msg is None:
            continue
        msg_dt = msg.date
        if msg_dt.tzinfo is None:
            msg_dt = msg_dt.replace(tzinfo=timezone.utc)
        msg_dt = msg_dt.astimezone(timezone.utc)
        if msg_dt > end:
            continue
        if msg_dt < start:
            break
        text = msg.message
        if text is None or str(text).strip() == '':
            continue
        author = None
        full_name = None
        try:
            sender = msg.sender
        except Exception:
            sender = None
        if sender:
            author = getattr(sender, 'username', None)
            first = getattr(sender, 'first_name', None)
            last = getattr(sender, 'last_name', None)
            full_name = ' '.join([p for p in [first, last] if p])
        if not author:
            author = getattr(msg, 'post_author', None)
        views = getattr(msg, 'views', None)
        forwards = getattr(msg, 'forwards', None)
        replies = None
        replies_obj = getattr(msg, 'replies', None)
        if replies_obj is not None:
            replies = getattr(replies_obj, 'replies', None)
        yield MessageRecord(
            message_id=msg.id,
            chat_id=channel.chat_id,
            author=author,
            full_name=full_name,
            date_ts=int(msg_dt.timestamp()),
            text=str(text).strip(),
            views=views,
            forwards=forwards,
            replies=replies,
        )
        processed += 1
        if max_messages and processed >= max_messages:
            break


# ----------- Analytics helpers -----------
def _detect_hits(
    records: Sequence[MessageRecord],
    tags: Sequence[TagRecord],
    channels_by_id: Dict[str, ChannelRecord],
):
    hits = []
    per_channel: Dict[str, Dict[str, int]] = {}
    per_tag: Dict[str, Dict[str, int]] = {}
    for rec in records:
        matched_tags = [tag.tag for tag in tags if rec.matches_tag(tag.tag)]
        if not matched_tags:
            continue
        channel = channels_by_id.get(rec.chat_id)
        for tag in matched_tags:
            bucket = per_tag.setdefault(tag, {'count': 0, 'views': 0})
            bucket['count'] += 1
            bucket['views'] += rec.views or 0
        chan_bucket = per_channel.setdefault(rec.chat_id, {'count': 0, 'views': 0})
        chan_bucket['count'] += 1
        chan_bucket['views'] += rec.views or 0
        hits.append((rec, matched_tags, channel))
    return hits, per_channel, per_tag


def _format_report(
    start: datetime,
    end: datetime,
    hits,
    per_channel: Dict[str, Dict[str, int]],
    per_tag: Dict[str, Dict[str, int]],
    channels_by_id: Dict[str, ChannelRecord],
) -> str:
    lines: List[str] = []
    lines.append(f"Analytics window: {start:%Y-%m-%d %H:%M} UTC -> {end:%Y-%m-%d %H:%M} UTC")
    lines.append(f"Total hits: {len(hits)} | Channels with hits: {len(per_channel)} | Tags matched: {len(per_tag)}")
    if per_channel:
        lines.append("\nPer channel:")
        for chat_id, stats in sorted(per_channel.items(), key=lambda kv: kv[1]['count'], reverse=True):
            channel = channels_by_id.get(chat_id)
            name = channel.title or channel.username or chat_id
            lines.append(f"- {name}: {stats['count']} posts, reach={stats['views']}")
    if per_tag:
        lines.append("\nPer tag:")
        for tag, stats in sorted(per_tag.items(), key=lambda kv: kv[1]['count'], reverse=True):
            lines.append(f"- {tag}: {stats['count']} posts, reach={stats['views']}")
    if hits:
        lines.append("\nMatched posts:")
        for rec, tags, channel in hits:
            ch_name = channel.title or channel.username or rec.chat_id if channel else rec.chat_id
            link = build_message_link(
                rec.chat_id,
                rec.message_id,
                channel_username=channel.username if channel else None,
                channel_link=channel.link if channel else None,
            )
            snippet = rec.text.replace('\n', ' ')
            if len(snippet) > 240:
                snippet = snippet[:240].rstrip() + "..."
            view_text = f"views={rec.views}" if rec.views is not None else "views=n/a"
            lines.append(
                f"- {ch_name} [{rec.date:%Y-%m-%d}] tags={', '.join(tags)} ({view_text}) -> {link}\n  {snippet}"
            )
    if not hits:
        lines.append("\nNo posts matched the current tag list in this window.")
    return "\n".join(lines)


# ----------- Command handlers -----------
async def _handle_channels_add(args, store: MessageStore):
    identifier = args.identifier
    async with _build_client() as client:
        record = await _resolve_channel(client, identifier)
        store.upsert_channel(record)
        logger.info("Added channel %s (%s)", record.chat_id, record.title or record.username)


def _handle_channels_remove(args, store: MessageStore):
    identifier = args.identifier
    channels = store.list_channels()
    to_remove = None
    ident_norm = identifier.replace('@', '')
    for ch in channels:
        if ch.chat_id == identifier or ch.username == ident_norm or ch.link == identifier:
            to_remove = ch.chat_id
            break
    if not to_remove:
        raise ValueError(f"Channel '{identifier}' not found in local list.")
    store.remove_channel(to_remove)
    logger.info("Removed channel %s", identifier)


def _handle_channels_list(args, store: MessageStore):
    channels = store.list_channels(active_only=args.active_only)
    if not channels:
        print("No channels stored.")
        return
    for ch in channels:
        status = "active" if ch.is_active else "inactive"
        name = ch.title or ch.username or ch.chat_id
        print(f"{name} ({ch.chat_id}) [{status}] link={ch.link or 'n/a'}")


def _handle_tags_add(args, store: MessageStore):
    record = store.add_tag(args.tag)
    logger.info("Added tag: %s", record.tag)


def _handle_tags_remove(args, store: MessageStore):
    store.remove_tag(args.tag)
    logger.info("Removed tag: %s", args.tag)


def _handle_tags_list(args, store: MessageStore):
    tags = store.list_tags()
    if not tags:
        print("No tags stored.")
        return
    for tag in tags:
        print(f"- {tag.tag}")


async def _handle_fetch(args, store: MessageStore):
    channels = store.list_channels(active_only=True)
    if not channels:
        raise ValueError("No channels configured. Add channels first via `channels add`.")
    start, end = _resolve_range(args)
    max_msgs = args.max_per_channel if args.max_per_channel and args.max_per_channel > 0 else None
    logger.info("Fetching messages between %s and %s UTC", start, end)
    async with _build_client() as client:
        for ch in channels:
            logger.info("Fetching %s", ch.title or ch.username or ch.chat_id)
            count = 0
            async for record in _iter_messages_for_channel(client, ch, start, end, max_msgs):
                store.upsert_message(record)
                count += 1
            logger.info("Stored %s messages for %s", count, ch.chat_id)


def _handle_analyze(args, store: MessageStore):
    channels = store.list_channels(active_only=True)
    if not channels:
        raise ValueError("No channels configured. Add channels first via `channels add`.")
    tags = store.list_tags()
    if not tags:
        raise ValueError("No tags configured. Add tags first via `tags add`.")
    start, end = _resolve_range(args)
    channel_ids = [ch.chat_id for ch in channels]
    records = store.fetch_between(start, end, chat_ids=channel_ids)
    channels_by_id = {c.chat_id: c for c in channels}
    hits, per_channel, per_tag = _detect_hits(records, tags, channels_by_id)
    report = _format_report(start, end, hits, per_channel, per_tag, channels_by_id)
    if args.send:
        if not settings.bot_token:
            raise ValueError("TG_BOT_TOKEN is required to send analytics to Telegram.")
        target = args.target or settings.target_chat_id
        if not target:
            raise ValueError("Target chat id is not set. Use --target or HIGHLIGHT_TARGET_CHAT_ID.")
        bot = telebot.TeleBot(settings.bot_token, parse_mode=None)
        send_digest(bot, target, report)
        logger.info("Analytics report sent to %s", target)
    else:
        print(report)


# ----------- CLI plumbing -----------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ton Station analytics and channel manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Channels
    chan = subparsers.add_parser("channels", help="Manage channels to analyze")
    chan_sub = chan.add_subparsers(dest="action", required=True)
    chan_add = chan_sub.add_parser("add", help="Add a channel by @username, link, or id")
    chan_add.add_argument("identifier", type=str, help="Channel username (@foo), link, or numeric id")
    chan_add.set_defaults(func=_handle_channels_add)

    chan_rm = chan_sub.add_parser("remove", help="Remove a stored channel")
    chan_rm.add_argument("identifier", type=str, help="Stored chat_id or username")
    chan_rm.set_defaults(func=_handle_channels_remove)

    chan_ls = chan_sub.add_parser("list", help="List stored channels")
    chan_ls.add_argument("--active-only", action="store_true", help="Show only active channels")
    chan_ls.set_defaults(func=_handle_channels_list)

    # Tags
    tags = subparsers.add_parser("tags", help="Manage tags/keywords")
    tags_sub = tags.add_subparsers(dest="action", required=True)

    tag_add = tags_sub.add_parser("add", help="Add a tag/keyword")
    tag_add.add_argument("tag", type=str)
    tag_add.set_defaults(func=_handle_tags_add)

    tag_rm = tags_sub.add_parser("remove", help="Remove a tag/keyword")
    tag_rm.add_argument("tag", type=str)
    tag_rm.set_defaults(func=_handle_tags_remove)

    tag_ls = tags_sub.add_parser("list", help="List stored tags")
    tag_ls.set_defaults(func=_handle_tags_list)

    # Fetch
    fetch = subparsers.add_parser("fetch", help="Fetch messages from configured channels (no bot needed)")
    fetch.add_argument("--from", dest="from_date", help="Start datetime (ISO, e.g., 2025-01-01 or 2025-01-01T12:00)")
    fetch.add_argument("--to", dest="to_date", help="End datetime (ISO). Defaults to now.")
    fetch.add_argument("--days", type=int, default=settings.window_days, help="Window size in days if no explicit dates are given")
    fetch.add_argument("--max-per-channel", type=int, default=None, help="Max messages per channel (0 for all)")
    fetch.set_defaults(func=_handle_fetch)

    # Analyze
    analyze = subparsers.add_parser("analyze", help="Run aggregated analytics over stored messages")
    analyze.add_argument("--from", dest="from_date", help="Start datetime (ISO, e.g., 2025-01-01)")
    analyze.add_argument("--to", dest="to_date", help="End datetime (ISO). Defaults to now.")
    analyze.add_argument("--days", type=int, default=settings.window_days, help="Window size in days if no explicit dates are given")
    analyze.add_argument("--send", action="store_true", help="Send analytics to Telegram instead of printing")
    analyze.add_argument("--target", type=str, default=None, help="Override target chat id for sending")
    analyze.set_defaults(func=_handle_analyze)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    store = MessageStore(settings.db_path)
    try:
        if asyncio.iscoroutinefunction(args.func):
            asyncio.run(args.func(args, store))
        else:
            args.func(args, store)
    finally:
        store.close()


if __name__ == "__main__":
    main()
