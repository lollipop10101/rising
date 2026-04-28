from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvSettings(BaseSettings):
    telegram_api_id: int | None = Field(default=None, alias="TELEGRAM_API_ID")
    telegram_api_hash: str | None = Field(default=None, alias="TELEGRAM_API_HASH")
    telegram_session: str = Field(default="rising_session", alias="TELEGRAM_SESSION")
    telegram_source_chat: str | int | None = Field(default=None, alias="TELEGRAM_SOURCE_CHAT")
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_report_chat_id: str | int | None = Field(default=None, alias="TELEGRAM_REPORT_CHAT_ID")
    helius_api_key: str | None = Field(default=None, alias="HELIUS_API_KEY")
    database_url: str = Field(default="sqlite:///data/rising.db", alias="DATABASE_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def load_yaml_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def nested_get(config: dict[str, Any], path: str, default: Any) -> Any:
    cur: Any = config
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
