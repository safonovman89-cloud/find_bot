from __future__ import annotations

import argparse
import asyncio
import json
import logging

from .ai import AIQueryAnalyzer
from .config import Settings
from .indexer import rebuild
from .max_api import MaxAPI
from .service import SYSTEMS, handle_update
from .storage import Storage


async def main() -> None:
    parser = argparse.ArgumentParser(description="Управление поисковым ботом MAX")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index", help="обновить локальный индекс инструкций")
    sub.add_parser("set-webhook", help="зарегистрировать MAX webhook")
    sub.add_parser("polling", help="запустить Long Polling для разработки")
    args = parser.parse_args()

    settings = Settings.from_env(require_token=args.command != "index")
    if args.command == "index":
        counts = await rebuild(Storage(settings.database_path))
        print(json.dumps(counts, ensure_ascii=False))
        return
    if args.command == "set-webhook" and not settings.webhook_url:
        raise RuntimeError("Не задана переменная MAX_WEBHOOK_URL")
    api = MaxAPI(settings.token, settings.api_base)
    try:
        if args.command == "set-webhook":
            result = await api.subscribe(settings.webhook_url, settings.webhook_secret)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        storage = Storage(settings.database_path)
        ai = AIQueryAnalyzer(
            settings.ai_api_key,
            settings.ai_base_url,
            settings.ai_model,
            {key: value["name"] for key, value in SYSTEMS.items()},
        )
        marker = None
        logging.basicConfig(level=logging.INFO)
        logging.info("Long Polling запущен. Для остановки нажмите Ctrl+C")
        while True:
            payload = await api.updates(marker=marker, timeout=30)
            for update in payload.get("updates", []):
                try:
                    await handle_update(update, storage, api, ai)
                except Exception:
                    logging.exception("Ошибка обработки события")
            if payload.get("marker") is not None:
                marker = payload["marker"]
    finally:
        if "ai" in locals():
            await ai.close()
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
