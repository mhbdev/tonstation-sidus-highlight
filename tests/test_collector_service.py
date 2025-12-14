import threading

import pytest

from tonstation import collector_service
from tonstation import storage


@pytest.fixture(autouse=True)
def cleanup_store():
    yield
    try:
        collector_service.store.close()
    except Exception:
        pass


class _StubChat:
    def __init__(self, chat_id):
        self.id = chat_id


class _StubMessage:
    def __init__(self, chat_id, text, msg_id=1):
        self.chat = _StubChat(chat_id)
        self.text = text
        self.caption = None
        self.message_id = msg_id
        self.date = int(storage.datetime.now(storage.timezone.utc).timestamp())
        self.views = 1
        self.forward_date = 0


def test_handlers_store_messages(tmp_path, monkeypatch):
    try:
        collector_service.store.close()
    except Exception:
        pass
    collector_service.store = storage.MessageStore(str(tmp_path / "collector.db"))
    collector_service.settings.source_chat_id = "-1001234567890"

    assert collector_service._is_source_chat(_StubMessage("other", "x")) is False
    class _NoChat:
        text = "hello"
        caption = None
    assert collector_service._is_source_chat(_NoChat()) is False

    other_msg = _StubMessage("other", "ignored")
    collector_service.handle_channel_post(other_msg)
    collector_service.handle_text(other_msg)

    chatid_msg = _StubMessage("-1001234567890", "/chatid")
    collector_service.handle_channel_post(chatid_msg)
    collector_service.handle_text(chatid_msg)

    normal_msg = _StubMessage("-1001234567890", "hello there", msg_id=2)
    collector_service.handle_channel_post(normal_msg)
    normal_msg2 = _StubMessage("-1001234567890", "another", msg_id=3)
    collector_service.handle_text(normal_msg2)

    rows = collector_service.store.fetch_since_days(1)
    assert len(rows) == 2
    collector_service.store.close()


def test_collector_service_error_import(monkeypatch):
    import importlib
    monkeypatch.setattr(collector_service.settings, "bot_token", None)
    monkeypatch.setattr(collector_service.settings, "source_chat_id", None)
    import tonstation.config as config_mod
    monkeypatch.setattr(config_mod.settings, "bot_token", None)
    monkeypatch.setattr(config_mod.settings, "source_chat_id", None)
    with pytest.raises(ValueError):
        importlib.reload(collector_service)
    # restore valid settings
    collector_service.settings.bot_token = "test-bot-token"
    collector_service.settings.source_chat_id = "-1001234567890"
    importlib.reload(collector_service)


def test_run_collector_exits_fast(monkeypatch, tmp_path):
    try:
        collector_service.store.close()
    except Exception:
        pass
    collector_service.store = storage.MessageStore(str(tmp_path / "collector2.db"))
    collector_service.stop_event = threading.Event()

    state = {"count": 0}

    def _fake_polling(**kwargs):
        state["count"] += 1
        if state["count"] == 1:
            raise RuntimeError("fail once")
        if state["count"] == 2:
            return None  # triggers else branch
        collector_service.stop_event.set()
        raise RuntimeError("stop now")

    collector_service.bot.infinity_polling = _fake_polling
    collector_service.bot.stop_polling = lambda: None
    monkeypatch.setattr(collector_service.signal, "signal", lambda *a, **k: None)
    monkeypatch.setattr(collector_service.time, "sleep", lambda *a, **k: None)
    collector_service.run_collector()


def test_run_collector_keyboardinterrupt(monkeypatch, tmp_path):
    try:
        collector_service.store.close()
    except Exception:
        pass
    collector_service.store = storage.MessageStore(str(tmp_path / "collector3.db"))
    collector_service.stop_event = threading.Event()

    class _FakeThread:
        def __init__(self, *args, **kwargs):
            self.join_calls = 0

        def start(self):
            return None

        def is_alive(self):
            return True

        def join(self, timeout=None):
            self.join_calls += 1
            if self.join_calls == 1:
                raise KeyboardInterrupt()
            return None

    monkeypatch.setattr(collector_service.threading, "Thread", lambda *a, **k: _FakeThread())
    collector_service.bot.infinity_polling = lambda **kwargs: None
    collector_service.bot.stop_polling = lambda: (_ for _ in ()).throw(RuntimeError("stop"))
    monkeypatch.setattr(collector_service.signal, "signal", lambda *a, **k: None)
    monkeypatch.setattr(collector_service.time, "sleep", lambda *a, **k: None)
    collector_service.run_collector()
    collector_service.store.close()


def test_collector_service_main_guard(monkeypatch, tmp_path):
    import runpy
    import threading as real_threading

    class _FakeThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            return None

        def is_alive(self):
            return False

        def join(self, timeout=None):
            return None

    monkeypatch.setenv("DB_PATH", str(tmp_path / "collector_guard.db"))
    monkeypatch.setattr(real_threading, "Thread", lambda *a, **k: _FakeThread())
    monkeypatch.setattr(collector_service.signal, "signal", lambda *a, **k: None)
    monkeypatch.setattr(collector_service.time, "sleep", lambda *a, **k: None)
    runpy.run_module("tonstation.collector_service", run_name="__main__", alter_sys=True)
