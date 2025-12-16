import importlib
from types import SimpleNamespace

import pytest

from tonstation import config, storage


def test_highlight_agent_build_digest_sync():
    from tonstation.highlight_agent import WeeklyHighlightAgent

    agent = WeeklyHighlightAgent(api_key="key", system_prompt="sys", model_name="model")
    result = agent.build_digest_sync("user prompt")
    assert "user prompt" in result


def test_highlight_agent_timeout(monkeypatch):
    from tonstation.highlight_agent import WeeklyHighlightAgent

    agent = WeeklyHighlightAgent(api_key="key", system_prompt="sys", model_name="model")
    agent.task_execute = lambda task: None  # do not trigger handler
    with pytest.raises(TimeoutError):
        agent.build_digest_sync("late", timeout=0)


def test_digest_prompt_scoring_and_sending(monkeypatch):
    from tonstation import digest_builder

    rec = storage.MessageRecord(
        message_id=1,
        chat_id="-1001",
        author="alice",
        full_name="Alice",
        date_ts=int(storage.datetime.now(storage.timezone.utc).timestamp()),
        text="A" * 500,
        views=10,
    )

    assert "No messages" in digest_builder.build_prompt([], 7)
    prompt = digest_builder.build_prompt([rec], 3)
    assert "Window:" in prompt and "Top messages:" in prompt

    bot = SimpleNamespace(sent=[])

    def _send_message(chat_id, text, **kwargs):
        bot.sent.append((chat_id, text))

    bot.send_message = _send_message
    digest_builder.send_digest(bot, "chat", "x" * 4001)
    assert len(bot.sent) == 2

    # Patch MessageStore to return a fixed set of records
    class _FakeStore:
        def __init__(self, *_a, **_k):
            self.closed = False

        def fetch_since_days(self, *_a, **_k):
            return [rec]

        def close(self):
            self.closed = True

    monkeypatch.setattr(digest_builder, "MessageStore", _FakeStore)
    monkeypatch.setattr(
        digest_builder.WeeklyHighlightAgent,
        "build_digest_sync",
        lambda self, prompt, timeout=120: "digest text",
    )
    # send=False prints path
    output = digest_builder.build_and_optionally_send(send=False)
    assert "digest text" in output

    # send=True with target uses bot send
    original_token = config.settings.bot_token
    config.settings.bot_token = "bot-token"
    digest_builder.settings.bot_token = "bot-token"
    digest_builder.settings.target_chat_id = "target-chat"
    sent_messages = []

    class _Bot:
        def __init__(self, *args, **kwargs):
            pass

        def send_message(self, chat_id, text, **kwargs):
            sent_messages.append((chat_id, text))

    monkeypatch.setattr(digest_builder.telebot, "TeleBot", lambda *a, **k: _Bot())
    result = digest_builder.build_and_optionally_send(send=True, target_chat_id="target")
    assert "digest text" in result
    assert sent_messages and sent_messages[0][0] == "target"

    # send=True but missing target falls back to print
    digest_builder.settings.target_chat_id = None
    result2 = digest_builder.build_and_optionally_send(send=True, target_chat_id=None)
    assert "digest text" in result2

    config.settings.bot_token = original_token
    digest_builder.settings.bot_token = original_token


def test_digest_builder_missing_key(monkeypatch):
    import tonstation.digest_builder as db
    original_key = config.settings.deepseek_api_key
    config.settings.deepseek_api_key = None
    db.settings.deepseek_api_key = None
    with pytest.raises(ValueError):
        db.build_and_optionally_send(send=False)
    config.settings.deepseek_api_key = original_key
    db.settings.deepseek_api_key = original_key


def test_digest_builder_errors_and_entry(monkeypatch):
    import tonstation.digest_builder as db
    monkeypatch.setattr(db, "settings", SimpleNamespace(
        deepseek_api_key="key",
        bot_token=None,
        target_chat_id=None,
        model_name="m",
        db_path=":memory:",
        window_days=1,
        top_n_messages=5,
    ))

    class _Store:
        def __init__(self, *_a, **_k):
            pass

        def fetch_since_days(self, *_a, **_k):
            return [storage.MessageRecord(
                message_id=1,
                chat_id="-1001",
                author="a",
                full_name="A",
                date_ts=int(storage.datetime.now(storage.timezone.utc).timestamp()),
                text="hello",
            )]

    monkeypatch.setattr(db, "MessageStore", _Store)
    monkeypatch.setattr(
        db.WeeklyHighlightAgent,
        "build_digest_sync",
        lambda self, prompt, timeout=120: "digest text",
    )
    with pytest.raises(ValueError):
        db.build_and_optionally_send(send=True, target_chat_id="target")

    calls = []
    monkeypatch.setattr(db, "build_and_optionally_send", lambda send=True, target_chat_id=None: calls.append((send, target_chat_id)))
    import sys
    monkeypatch.setattr(sys, "argv", ["prog", "--no-send"])
    db.main()
    assert calls and calls[0][0] is False

    import runpy
    monkeypatch.setattr(sys, "argv", ["prog", "--no-send"])
    monkeypatch.setattr(db, "MessageStore", _Store)
    runpy.run_module("tonstation.digest_builder", run_name="__main__", alter_sys=True)
