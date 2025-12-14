import importlib
import os

import pytest

from tonstation import config


def test_get_env_required_and_cast_errors(monkeypatch):
    with pytest.raises(ValueError):
        config._get_env("MISSING_REQUIRED", required=True)

    monkeypatch.setenv("CAST_BAD", "abc")
    with pytest.raises(ValueError):
        config._get_env("CAST_BAD", cast=int)


def test_load_settings_respects_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TG_BOT_TOKEN", "bot-token-x")
    monkeypatch.setenv("SOURCE_CHAT_ID", "-10042")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key-x")
    monkeypatch.setenv("TG_API_ID", "9876")
    monkeypatch.setenv("TG_API_HASH", "hash9876")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite"))
    reloaded = importlib.reload(config)
    settings = reloaded.load_settings()
    assert settings.bot_token == "bot-token-x"
    assert settings.source_chat_id == "-10042"
    assert settings.deepseek_api_key == "deepseek-key-x"
    assert settings.tg_api_id == 9876
    assert settings.tg_api_hash == "hash9876"
    assert settings.db_path.endswith("db.sqlite")


def test_load_env_picks_up_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DOTENV_TEST_VAR=hello\n")
    monkeypatch.chdir(tmp_path)
    reloaded = importlib.reload(config)
    assert reloaded.LOADED_DOTENV == env_file
    assert os.getenv("DOTENV_TEST_VAR") == "hello"
