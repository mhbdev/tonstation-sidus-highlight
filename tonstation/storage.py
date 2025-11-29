import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional


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

    def fetch_since_days(self, days: int) -> List[MessageRecord]:
        now = datetime.now(tz=timezone.utc)
        since = now - timedelta(days=days)
        return self.fetch_between(since, now)

    def fetch_between(self, start: datetime, end: datetime) -> List[MessageRecord]:
        start_ts = int(start.timestamp())
        end_ts = int(end.timestamp())
        with self.conn:
            rows = self.conn.execute(
                """
                SELECT message_id, chat_id, author, full_name, date_ts, text, views, forwards, replies
                FROM messages
                WHERE date_ts BETWEEN ? AND ?
                ORDER BY date_ts ASC
                """,
                (start_ts, end_ts),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

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
