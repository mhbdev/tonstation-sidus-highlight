import argparse
import asyncio
import sys
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

import pytest

from tonstation import cli, config, storage


def test_parse_date_and_resolve_range():
    dt = cli._parse_date("2025-01-01")
    assert dt.tzinfo is not None

    args = SimpleNamespace(from_date="2025-01-01", to_date="2025-01-03")
    start, end = cli._resolve_range(args)
    assert start < end

    args2 = SimpleNamespace(from_date=None, to_date=None, days=2)
    start2, end2 = cli._resolve_range(args2)
    assert (end2 - start2).days == 2


def test_build_client(monkeypatch):
    cli.settings.tg_api_id = 1
    cli.settings.tg_api_hash = "hash"
    client = cli._build_client()
    assert isinstance(client, cli.TelegramClient)


def test_require_api_credentials(monkeypatch):
    monkeypatch.setattr(config.settings, "tg_api_id", None)
    monkeypatch.setattr(config.settings, "tg_api_hash", None)
    monkeypatch.setattr(cli.settings, "tg_api_id", None)
    monkeypatch.setattr(cli.settings, "tg_api_hash", None)
    with pytest.raises(ValueError):
        cli._require_api_credentials()

    config.settings.tg_api_id = 123
    config.settings.tg_api_hash = "hash"
    cli.settings.tg_api_id = 123
    cli.settings.tg_api_hash = "hash"
    cli._require_api_credentials()


def test_resolve_channel_and_iter_messages(monkeypatch):
    class _Client(cli.TelegramClient):
        async def get_entity(self, identifier):
            return SimpleNamespace(id=42, username="chan", title="Title", access_hash=99)

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.messages = []

    monkeypatch.setattr(cli, "TelegramClient", _Client)
    channel = asyncio.run(cli._resolve_channel(_Client("s", 1, "h"), "chan"))
    assert channel.chat_id.startswith("-100")
    assert channel.username == "chan"

    msg_time = datetime.now(timezone.utc)

    class _Msg:
        def __init__(self, idx, text):
            self.id = idx
            self.date = msg_time
            self.message = text
            self.sender = SimpleNamespace(username=f"user{idx}", first_name="U", last_name=str(idx))
            self.post_author = None
            self.views = idx
            self.forwards = idx + 1
            self.replies = SimpleNamespace(replies=idx + 2)

    client = _Client("sess", 1, "hash")
    client.messages = [_Msg(1, "hello world"), _Msg(2, "skip" * 100)]
    ch_record = storage.ChannelRecord(chat_id="-1001", title="T", username="chan", link=None)
    start = msg_time - timedelta(seconds=1)
    end = msg_time + timedelta(seconds=1)
    yielded = []
    async def _collect():
        async for rec in cli._iter_messages_for_channel(client, ch_record, start, end, max_messages=1):
            yielded.append(rec)
    asyncio.run(_collect())
    assert len(yielded) == 1
    assert yielded[0].author == "user1"


def test_iter_messages_branches(monkeypatch):
    msg_time = datetime.now(timezone.utc)

    class _Msg:
        def __init__(self, date, text, sender=None, post_author=None, sender_exception=False):
            self.id = 1
            self.date = date
            self.message = text
            self._sender = sender
            self.sender_exception = sender_exception
            self.post_author = post_author
            self.views = None
            self.forwards = None
            self.replies = None
        @property
        def sender(self):
            if self.sender_exception:
                raise RuntimeError("no sender")
            return self._sender

    messages = [
        None,
        _Msg((msg_time + timedelta(seconds=10)).replace(tzinfo=None), "late", sender=None),
        _Msg(msg_time, None),
        _Msg(msg_time, "with sender", post_author="fallback", sender_exception=True),
        _Msg(msg_time - timedelta(seconds=10), "too early"),
    ]

    class _Client:
        def __init__(self, messages):
            self.messages = messages

        async def iter_messages(self, identifier, limit=None):
            for m in self.messages:
                yield m

    start = msg_time - timedelta(seconds=5)
    end = msg_time + timedelta(seconds=5)
    ch_record = storage.ChannelRecord(chat_id="-1001", title="T", username="chan", link=None)
    collected = []

    async def _collect():
        async for rec in cli._iter_messages_for_channel(_Client(messages), ch_record, start, end, max_messages=None):
            collected.append(rec)

    asyncio.run(_collect())
    assert collected and collected[0].author == "fallback"


def test_detect_hits_and_format_report():
    rec1 = storage.MessageRecord(
        message_id=1,
        chat_id="-1001",
        author="a",
        full_name="A",
        date_ts=int(datetime.now(timezone.utc).timestamp()),
        text="ton airdrop " + ("x" * 300),
        views=5,
    )
    rec2 = storage.MessageRecord(
        message_id=2,
        chat_id="-1002",
        author="b",
        full_name="B",
        date_ts=int(datetime.now(timezone.utc).timestamp()),
        text="nothing here",
        views=2,
    )
    tags = [storage.TagRecord(id=1, tag="ton"), storage.TagRecord(id=2, tag="airdrop")]
    channels = {
        "-1001": storage.ChannelRecord(chat_id="-1001", title="Chan1", username="c1"),
        "-1002": storage.ChannelRecord(chat_id="-1002", title="Chan2", username="c2"),
    }
    hits, per_channel, per_tag = cli._detect_hits([rec1, rec2], tags, channels)
    assert len(hits) == 1
    report = cli._format_report(
        datetime.now(timezone.utc) - timedelta(days=1),
        datetime.now(timezone.utc),
        hits,
        per_channel,
        per_tag,
        channels,
    )
    assert "Per channel" in report
    # Empty hits message
    report2 = cli._format_report(datetime.now(timezone.utc), datetime.now(timezone.utc), [], {}, {}, {})
    assert "No posts matched" in report2


def test_channel_tag_handlers_and_list_output(tmp_path, capsys, monkeypatch):
    store = storage.MessageStore(str(tmp_path / "cli.db"))
    args_list = SimpleNamespace(active_only=False)
    cli._handle_tags_list(SimpleNamespace(), store)
    assert "No tags stored" in capsys.readouterr().out
    cli._handle_channels_list(args_list, store)
    out = capsys.readouterr().out
    assert "No channels stored" in out

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_entity(self, identifier):
            return SimpleNamespace(id=55, username="added", title="Added", access_hash=42)

    monkeypatch.setattr(cli, "_build_client", lambda: _FakeClient())
    add_args = SimpleNamespace(identifier="added")
    asyncio.run(cli._handle_channels_add(add_args, store))
    cli._handle_channels_list(args_list, store)
    assert "Added" in capsys.readouterr().out

    rem_args = SimpleNamespace(identifier="added")
    cli._handle_channels_remove(rem_args, store)
    with pytest.raises(ValueError):
        cli._handle_channels_remove(rem_args, store)

    tag_add_args = SimpleNamespace(tag="keyword")
    cli._handle_tags_add(tag_add_args, store)
    cli._handle_tags_list(SimpleNamespace(), store)
    assert "- keyword" in capsys.readouterr().out
    cli._handle_tags_remove(SimpleNamespace(tag="keyword"), store)
    assert store.list_tags() == []
    store.close()


def test_handle_fetch_and_analyze(tmp_path, monkeypatch, capsys):
    store = storage.MessageStore(str(tmp_path / "cli2.db"))
    fetch_args = SimpleNamespace(from_date=None, to_date=None, days=1, max_per_channel=None)
    with pytest.raises(ValueError):
        asyncio.run(cli._handle_fetch(fetch_args, store))

    ch = storage.ChannelRecord(chat_id="-1001", title="Ch", username="u")
    store.upsert_channel(ch)
    msg_time = datetime.now(timezone.utc)

    class _Msg:
        def __init__(self, idx):
            self.id = idx
            self.date = msg_time
            self.message = f"text {idx} keyword"
            self.sender = SimpleNamespace(username="sender", first_name="First", last_name="Last")
            self.post_author = None
            self.views = 3
            self.forwards = 0
            self.replies = SimpleNamespace(replies=0)

    class _FakeClient:
        def __init__(self):
            self.messages = [_Msg(1)]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_entity(self, identifier):
            return SimpleNamespace(id=1, username="u", title="Ch", access_hash=1)

        async def iter_messages(self, identifier, limit=None):
            for m in self.messages:
                yield m

    monkeypatch.setattr(cli, "_build_client", lambda: _FakeClient())
    asyncio.run(cli._handle_fetch(fetch_args, store))
    assert store.fetch_since_days(1)

    analyze_args = SimpleNamespace(
        from_date=None,
        to_date=None,
        days=1,
        send=False,
        target=None,
    )
    empty_store = storage.MessageStore(str(tmp_path / "empty.db"))
    with pytest.raises(ValueError):
        cli._handle_analyze(analyze_args, empty_store)
    empty_store.close()

    with pytest.raises(ValueError):
        cli._handle_analyze(analyze_args, store)

    store.add_tag("keyword")
    cli._handle_analyze(analyze_args, store)
    assert "Per channel" in capsys.readouterr().out

    send_calls = []

    def _fake_send(bot, chat_id, text):
        send_calls.append((chat_id, text))

    monkeypatch.setattr(cli, "send_digest", _fake_send)
    analyze_args.send = True
    analyze_args.target = "target"
    config.settings.bot_token = None
    cli.settings.bot_token = None
    with pytest.raises(ValueError):
        cli._handle_analyze(analyze_args, store)

    config.settings.bot_token = "bot-token"
    cli.settings.bot_token = "bot-token"
    analyze_args.target = None
    cli.settings.target_chat_id = None
    with pytest.raises(ValueError):
        cli._handle_analyze(analyze_args, store)

    analyze_args.target = "target"
    cli._handle_analyze(analyze_args, store)
    assert send_calls and send_calls[0][0] == "target"
    store.close()


def test_build_parser_and_main(monkeypatch, tmp_path):
    parser = cli.build_parser()
    args = parser.parse_args(["tags", "list"])
    assert args.command == "tags" and args.action == "list"

    config.settings.db_path = str(tmp_path / "cli_main.db")
    monkeypatch.setattr(sys, "argv", ["prog", "tags", "list"])
    monkeypatch.setattr(cli, "_handle_tags_list", lambda args, store: None)
    cli.main()

    async def _fake_add(args, store):
        return None

    monkeypatch.setattr(sys, "argv", ["prog", "channels", "add", "chan"])
    monkeypatch.setattr(cli, "_handle_channels_add", _fake_add)
    cli.main()


def test_cli_main_guard(monkeypatch, tmp_path):
    import runpy
    import sys as _sys

    monkeypatch.setattr(_sys, "argv", ["prog", "tags", "list"])
    monkeypatch.setenv("DB_PATH", str(tmp_path / "cli_guard.db"))
    runpy.run_module("tonstation.cli", run_name="__main__", alter_sys=True)
