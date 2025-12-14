import os
import sys
import types
from pathlib import Path

# --- Environment defaults for tests ---
repo_root = Path(__file__).resolve().parent.parent
data_dir = repo_root / "tonstation" / "data"
data_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TG_BOT_TOKEN", "test-bot-token")
os.environ.setdefault("SOURCE_CHAT_ID", "-1001234567890")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-key")
os.environ.setdefault("TG_API_ID", "123456")
os.environ.setdefault("TG_API_HASH", "test-api-hash")
os.environ.setdefault("TG_SESSION_PATH", str(data_dir / "test_session.session"))
os.environ.setdefault("DB_PATH", str(data_dir / "test_messages.db"))

# --- Stub telebot module ---


class _DummyTeleBot:
    def __init__(self, *args, **kwargs):
        self.sent = []
        self.handlers = {}
        self.stopped = False

    def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))

    def channel_post_handler(self, *args, **kwargs):
        def decorator(fn):
            self.handlers["channel_post"] = fn
            return fn

        return decorator

    def message_handler(self, *args, **kwargs):
        def decorator(fn):
            self.handlers["message"] = fn
            return fn

        return decorator

    def infinity_polling(self, **kwargs):
        return None

    def stop_polling(self):
        self.stopped = True


telebot_module = types.ModuleType("telebot")
telebot_module.TeleBot = _DummyTeleBot
sys.modules["telebot"] = telebot_module

# --- Stub telethon module ---


class _DummyEntity:
    def __init__(self, identifier):
        self.id = 999
        self.username = "dummyuser"
        self.title = f"title-{identifier}"
        self.access_hash = 111


class _DummyTelegramClient:
    def __init__(self, session, api_id, api_hash):
        self.session = session
        self.api_id = api_id
        self.api_hash = api_hash
        self.messages = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get_entity(self, identifier):
        return _DummyEntity(identifier)

    async def iter_messages(self, identifier, limit=None):
        count = 0
        for msg in self.messages:
            if limit and count >= limit:
                break
            count += 1
            yield msg


telethon_module = types.ModuleType("telethon")
telethon_module.TelegramClient = _DummyTelegramClient
telethon_errors = types.ModuleType("telethon.errors")


class _DummyRPCError(Exception):
    pass


telethon_errors.RPCError = _DummyRPCError
telethon_module.errors = telethon_errors
sys.modules["telethon"] = telethon_module
sys.modules["telethon.errors"] = telethon_errors

# --- Stub sidusai module for highlight agent ---
sidusai_module = types.ModuleType("sidusai")


class _DummyChatAgentValue(list):
    def append_system(self, content):
        self.append(("system", content))

    def append_user(self, content):
        self.append(("user", content))

    def last_content(self):
        return self[-1][1] if self else None


class _DummyCompletedAgentTask:
    def __init__(self, agent):
        self.agent = agent
        self._chat = None
        self._then = None

    def data(self, chat):
        self._chat = chat
        return self

    def then(self, callback):
        self._then = callback
        return self


class _DummyAgent:
    def __init__(self, name):
        self.name = name
        self.is_builded = False

    def application_build(self):
        self.is_builded = True

    def task_registration(self, *args, **kwargs):
        return None

    def task_execute(self, task):
        if getattr(task, "_then", None):
            task._then(task._chat)


def _dummy_build_and_register_task_skill_names(skills, agent):
    return ["dummy-skill"]


sidusai_core_plugin = types.ModuleType("sidusai.core.plugin")
sidusai_core_plugin.build_and_register_task_skill_names = _dummy_build_and_register_task_skill_names
sidusai_core = types.ModuleType("sidusai.core")
sidusai_core.plugin = sidusai_core_plugin


class _DummyDeepSeekPlugin:
    def __init__(self, api_key, model_name=None):
        self.api_key = api_key
        self.model_name = model_name

    def apply_plugin(self, agent):
        agent.plugin_applied = True


sidusai_deepseek = types.ModuleType("sidusai.plugins.deepseek")
sidusai_deepseek.DeepSeekPlugin = _DummyDeepSeekPlugin
sidusai_deepseek.skills = types.SimpleNamespace(ds_chat_transform_skill=lambda *_a, **_k: "skill")
sidusai_plugins = types.ModuleType("sidusai.plugins")
sidusai_plugins.deepseek = sidusai_deepseek

sidusai_module.CompletedAgentTask = _DummyCompletedAgentTask
sidusai_module.Agent = _DummyAgent
sidusai_module.ChatAgentValue = _DummyChatAgentValue
sidusai_module.core = types.ModuleType("sidusai.core")
sidusai_module.core.plugin = sidusai_core_plugin
sidusai_module.plugins = sidusai_plugins

sys.modules["sidusai"] = sidusai_module
sys.modules["sidusai.core"] = sidusai_module.core
sys.modules["sidusai.core.plugin"] = sidusai_core_plugin
sys.modules["sidusai.plugins"] = sidusai_plugins
sys.modules["sidusai.plugins.deepseek"] = sidusai_deepseek

# Ensure tonstation package is importable with stubs in place
sys.path.append(str(repo_root))

# --- Reset config per test to keep env consistent ---
import pytest
import importlib


@pytest.fixture(autouse=True)
def reload_config_module():
    import tonstation.config as config_mod

    importlib.reload(config_mod)
    yield
    importlib.reload(config_mod)
