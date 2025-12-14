from datetime import datetime, timedelta, timezone

import pytest

from tonstation import storage


def _ts(offset_seconds=0):
    return int((datetime.now(tz=timezone.utc) + timedelta(seconds=offset_seconds)).timestamp())


def test_message_store_crud(tmp_path):
    db_path = tmp_path / "messages.db"
    store = storage.MessageStore(str(db_path))

    # Empty text is ignored
    empty = storage.MessageRecord(
        message_id=1,
        chat_id="chat1",
        author=None,
        full_name=None,
        date_ts=_ts(),
        text="",
    )
    store.upsert_message(empty)
    assert store.fetch_since_days(1) == []

    now_ts = _ts()
    rec = storage.MessageRecord(
        message_id=2,
        chat_id="chat1",
        author="alice",
        full_name="Alice A",
        date_ts=now_ts,
        text="Hello TON world",
        views=10,
        forwards=1,
        replies=2,
    )
    store.upsert_message(rec)

    later = storage.MessageRecord(
        message_id=3,
        chat_id="chat2",
        author="bob",
        full_name="Bob B",
        date_ts=now_ts,
        text="Another message",
        views=5,
    )
    store.upsert_message(later)

    start = datetime.fromtimestamp(now_ts - 60, tz=timezone.utc)
    end = datetime.fromtimestamp(now_ts + 60, tz=timezone.utc)
    all_between = store.fetch_between(start, end)
    assert len(all_between) == 2

    chat1_only = store.fetch_between(start, end, chat_ids=["chat1"])
    assert len(chat1_only) == 1
    assert chat1_only[0].chat_id == "chat1"

    recent = store.fetch_since_days(1, chat_ids=["chat1", "chat2"])
    assert len(recent) == 2

    assert rec.matches_tag("ton")
    assert not rec.matches_tag("missing")

    # Channels
    channel = storage.ChannelRecord(
        chat_id="-1001",
        title="Test Channel",
        username="testchan",
        link="https://t.me/testchan",
        access_hash=123,
    )
    store.upsert_channel(channel)
    listed = store.list_channels()
    assert listed and listed[0].title == "Test Channel"
    assert store.get_channel("-1001").username == "testchan"
    store.remove_channel("-1001")
    assert store.get_channel("-1001") is None

    # Tags
    tag_record = store.add_tag("Airdrop")
    assert tag_record.tag == "airdrop"
    tags = store.list_tags()
    assert tags and tags[0].tag == "airdrop"
    store.remove_tag("airdrop")
    assert store.list_tags() == []

    store.close()


def test_build_message_link_variants():
    link = storage.build_message_link("-1001", 10, channel_username="chanuser")
    assert link == "https://t.me/chanuser/10"

    link2 = storage.build_message_link("-1001", 11, channel_link="https://t.me/custom")
    assert link2 == "https://t.me/custom/11"

    link3 = storage.build_message_link("-10012345", 12)
    assert link3 == "https://t.me/c/12345/12"


def test_message_from_telegram_builds_record():
    class _User:
        username = "user1"
        full_name = "User One"

    class _Msg:
        def __init__(self):
            self.message_id = 5
            self.text = "hi"
            self.caption = None
            self.from_user = _User()
            self.date = _ts()
            self.views = 7
            self.forward_date = 0

    msg = _Msg()
    rec = storage.message_from_telegram(msg, "-1001")
    assert rec.chat_id == "-1001"
    assert rec.author == "user1"
    assert rec.views == 7


def test_storage_edge_cases(tmp_path, monkeypatch):
    # Create store with missing parent directory to hit mkdir path
    db_path = tmp_path / "nested" / "db.sqlite"
    store = storage.MessageStore(str(db_path))
    assert db_path.exists()

    # matches_tag returns False on empty tag
    rec = storage.MessageRecord(
        message_id=1,
        chat_id="c",
        author=None,
        full_name=None,
        date_ts=int(storage.datetime.now(storage.timezone.utc).timestamp()),
        text="content",
    )
    assert rec.matches_tag("") is False

    with pytest.raises(ValueError):
        store.add_tag("   ")

    # close with failing connection
    store.conn.close()
    class _BrokenConn:
        def close(self):
            raise RuntimeError("fail")

    store.conn = _BrokenConn()
    store.close()  # should swallow exception

    # message_from_telegram returns None for missing inputs
    assert storage.message_from_telegram(None, "c") is None

    class _EmptyMsg:
        text = None
        caption = None

    assert storage.message_from_telegram(_EmptyMsg(), "c") is None
