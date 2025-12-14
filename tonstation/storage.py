import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


@dataclass
class MessageRecord:
    message_id: int
    chat_id: str
    author: Optional[str]
    full_name: Optional[str]
    date_ts: int
    text: str
    views: Optional[int] = None
    forwards: Optional[int] = None
    replies: Optional[int] = None

    @property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.date_ts, tz=timezone.utc)

    def matches_tag(self, tag: str) -> bool:
        """
        Case-insensitive substring check for a tag/keyword.
        """
        if not tag:
            return False
        return tag.lower() in (self.text or '').lower()


@dataclass
class ChannelRecord:
    chat_id: str
    title: Optional[str] = None
    username: Optional[str] = None
    link: Optional[str] = None
    access_hash: Optional[int] = None
    added_at: Optional[int] = None
    is_active: bool = True


@dataclass
class TagRecord:
    id: int
    tag: str


class MessageStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        if self.db_path.parent and not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self):
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL,
                    chat_id TEXT NOT NULL,
                    author TEXT,
                    full_name TEXT,
                    date_ts INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    views INTEGER,
                    forwards INTEGER,
                    replies INTEGER,
                    UNIQUE(chat_id, message_id)
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    chat_id TEXT PRIMARY KEY,
                    title TEXT,
                    username TEXT,
                    link TEXT,
                    access_hash INTEGER,
                    added_at INTEGER,
                    is_active INTEGER DEFAULT 1
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag TEXT NOT NULL UNIQUE
                )
                """
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date_ts)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)"
            )

    def upsert_message(self, record: MessageRecord):
        if record.text is None or str(record.text).strip() == '':
            return
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO messages
                (message_id, chat_id, author, full_name, date_ts, text, views, forwards, replies)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.message_id,
                    record.chat_id,
                    record.author,
                    record.full_name,
                    record.date_ts,
                    record.text,
                    record.views,
                    record.forwards,
                    record.replies,
                ),
            )

    def fetch_since_days(self, days: int, chat_ids: Optional[Sequence[str]] = None) -> List[MessageRecord]:
        now = datetime.now(tz=timezone.utc)
        since = now - timedelta(days=days)
        return self.fetch_between(since, now, chat_ids=chat_ids)

    def fetch_between(
        self,
        start: datetime,
        end: datetime,
        chat_ids: Optional[Sequence[str]] = None,
    ) -> List[MessageRecord]:
        start_ts = int(start.timestamp())
        end_ts = int(end.timestamp())
        params = [start_ts, end_ts]
        channel_clause = ""
        if chat_ids:
            placeholders = ",".join("?" for _ in chat_ids)
            channel_clause = f" AND chat_id IN ({placeholders})"
            params.extend(list(chat_ids))
        with self.conn:
            rows = self.conn.execute(
                """
                SELECT message_id, chat_id, author, full_name, date_ts, text, views, forwards, replies
                FROM messages
                WHERE date_ts BETWEEN ? AND ?
                """
                + channel_clause
                + """
                ORDER BY date_ts ASC
                """,
                params,
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def upsert_channel(self, record: ChannelRecord):
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO channels (chat_id, title, username, link, access_hash, added_at, is_active)
                VALUES (:chat_id, :title, :username, :link, :access_hash, :added_at, :is_active)
                ON CONFLICT(chat_id) DO UPDATE SET
                    title=excluded.title,
                    username=excluded.username,
                    link=excluded.link,
                    access_hash=excluded.access_hash,
                    is_active=excluded.is_active
                """,
                {
                    "chat_id": record.chat_id,
                    "title": record.title,
                    "username": record.username,
                    "link": record.link,
                    "access_hash": record.access_hash,
                    "added_at": record.added_at or int(datetime.now(tz=timezone.utc).timestamp()),
                    "is_active": 1 if record.is_active else 0,
                },
            )

    def remove_channel(self, chat_id: str):
        with self.conn:
            self.conn.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))

    def list_channels(self, active_only: bool = False) -> List[ChannelRecord]:
        clause = "WHERE is_active = 1" if active_only else ""
        with self.conn:
            rows = self.conn.execute(
                f"SELECT chat_id, title, username, link, access_hash, added_at, is_active FROM channels {clause} ORDER BY added_at DESC"
            ).fetchall()
        return [self._row_to_channel(row) for row in rows]

    def get_channel(self, chat_id: str) -> Optional[ChannelRecord]:
        with self.conn:
            row = self.conn.execute(
                "SELECT chat_id, title, username, link, access_hash, added_at, is_active FROM channels WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return self._row_to_channel(row) if row else None

    def add_tag(self, tag: str) -> TagRecord:
        tag_norm = tag.strip().lower()
        if not tag_norm:
            raise ValueError("Tag cannot be empty")
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO tags (tag) VALUES (?)",
                (tag_norm,),
            )
            row = self.conn.execute(
                "SELECT id, tag FROM tags WHERE tag = ?", (tag_norm,)
            ).fetchone()
        return self._row_to_tag(row)

    def remove_tag(self, tag: str):
        with self.conn:
            self.conn.execute("DELETE FROM tags WHERE tag = ?", (tag.strip().lower(),))

    def list_tags(self) -> List[TagRecord]:
        with self.conn:
            rows = self.conn.execute("SELECT id, tag FROM tags ORDER BY tag ASC").fetchall()
        return [self._row_to_tag(row) for row in rows]

    def _row_to_channel(self, row: sqlite3.Row) -> ChannelRecord:
        return ChannelRecord(
            chat_id=row["chat_id"],
            title=row["title"],
            username=row["username"],
            link=row["link"],
            access_hash=row["access_hash"],
            added_at=row["added_at"],
            is_active=bool(row["is_active"]),
        )

    def _row_to_tag(self, row: sqlite3.Row) -> TagRecord:
        return TagRecord(id=row["id"], tag=row["tag"])

    def _row_to_record(self, row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(
            message_id=row['message_id'],
            chat_id=row['chat_id'],
            author=row['author'],
            full_name=row['full_name'],
            date_ts=row['date_ts'],
            text=row['text'],
            views=row['views'],
            forwards=row['forwards'],
            replies=row['replies'],
        )

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


def message_from_telegram(msg, chat_id: str) -> Optional[MessageRecord]:
    """
    Build a MessageRecord from a TeleBot message.
    """
    if msg is None:
        return None
    text = msg.text or msg.caption
    if text is None:
        return None
    username = None
    full_name = None
    if getattr(msg, 'from_user', None):
        username = msg.from_user.username
        full_name = msg.from_user.full_name
    views = getattr(msg, 'views', None)
    forwards = getattr(msg, 'forward_date', None)
    replies = 0  # Telegram Bot API does not expose reply count for posts; keep placeholder
    return MessageRecord(
        message_id=msg.message_id,
        chat_id=str(chat_id),
        author=username,
        full_name=full_name,
        date_ts=msg.date,
        text=str(text).strip(),
        views=views,
        forwards=forwards,
        replies=replies,
    )


def build_message_link(chat_id: str, message_id: int, channel_username: Optional[str] = None, channel_link: Optional[str] = None) -> str:
    """
    Build a direct link to a Telegram post. Prefers public username link if available.
    """
    if channel_link:
        base = channel_link.rstrip("/")
        return f"{base}/{message_id}"
    if channel_username:
        return f"https://t.me/{channel_username}/{message_id}"
    # Fallback to internal channel id link (works for members)
    trimmed = str(chat_id).removeprefix("-100")
    return f"https://t.me/c/{trimmed}/{message_id}"
