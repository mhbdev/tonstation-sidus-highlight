import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from sensible locations (cwd, tonstation/, repo root)
def _load_env():
    module_dir = Path(__file__).resolve().parent
    candidates = [
        Path.cwd() / '.env',
        module_dir / '.env',
        module_dir.parent / '.env',
    ]
    for candidate in candidates:
        if candidate.exists():
            load_dotenv(dotenv_path=candidate)
            return candidate
    load_dotenv()
    return None


LOADED_DOTENV = _load_env()


def _get_env(name: str, default=None, required: bool = False, cast=None):
    val = os.getenv(name, default)
    if required and (val is None or str(val).strip() == ''):
        raise ValueError(f'Missing required env var: {name}')
    if cast and val is not None:
        try:
            return cast(val)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f'Invalid value for {name}: {val}') from exc
    return val


@dataclass
class Settings:
    bot_token: Optional[str]
    source_chat_id: Optional[str]
    deepseek_api_key: Optional[str]
    model_name: str
    target_chat_id: Optional[str]
    db_path: str
    window_days: int
    top_n_messages: int
    polling_timeout: int
    polling_interval: int
    tg_api_id: Optional[int]
    tg_api_hash: Optional[str]
    tg_session_path: str


def load_settings() -> Settings:
    return Settings(
        bot_token=_get_env('TG_BOT_TOKEN'),
        source_chat_id=_get_env('SOURCE_CHAT_ID'),
        deepseek_api_key=_get_env('DEEPSEEK_API_KEY'),
        model_name=_get_env('DEEPSEEK_MODEL', 'deepseek-chat'),
        target_chat_id=_get_env('HIGHLIGHT_TARGET_CHAT_ID'),
        db_path=_get_env('DB_PATH', 'tonstation/data/messages.db'),
        window_days=_get_env('WINDOW_DAYS', 7, cast=int),
        top_n_messages=_get_env('TOP_N_MESSAGES', 12, cast=int),
        polling_timeout=_get_env('POLLING_TIMEOUT', 30, cast=int),
        polling_interval=_get_env('POLLING_INTERVAL', 1, cast=int),
        tg_api_id=_get_env('TG_API_ID', cast=int),
        tg_api_hash=_get_env('TG_API_HASH'),
        tg_session_path=_get_env('TG_SESSION_PATH', 'tonstation/data/tg_session.session'),
    )


settings = load_settings()
