from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    token: str
    webhook_secret: str
    webhook_url: str
    database_path: str
    ai_api_key: str = ""
    ai_base_url: str = "https://ai-gw.yanao.ru/v1"
    ai_model: str = "yanao/large"
    api_base: str = "https://platform-api2.max.ru"

    @classmethod
    def from_env(cls, require_token: bool = True) -> "Settings":
        token = os.getenv("MAX_BOT_TOKEN", "").strip()
        if require_token and not token:
            raise RuntimeError("Не задана переменная MAX_BOT_TOKEN")
        return cls(
            token=token,
            webhook_secret=os.getenv("MAX_WEBHOOK_SECRET", "").strip(),
            webhook_url=os.getenv("MAX_WEBHOOK_URL", "").strip(),
            database_path=os.getenv("DATABASE_PATH", "data/bot.sqlite3"),
            ai_api_key=os.getenv("AI_GATEWAY_API_KEY", "").strip(),
            ai_base_url=os.getenv("AI_GATEWAY_BASE_URL", "https://ai-gw.yanao.ru/v1").rstrip("/"),
            ai_model=os.getenv("AI_GATEWAY_MODEL", "yanao/large").strip(),
        )
