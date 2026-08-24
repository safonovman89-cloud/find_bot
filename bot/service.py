from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

from .max_api import MaxAPI
from .search import search
from .storage import Storage

log = logging.getLogger(__name__)
SOURCE_NAMES = {
    "rsed": "РСЭД",
    "esku": "ГИС ЕСКУ",
    "kb": "База знаний ЯНАО",
    "files": "Документы ЯНАО",
}


@dataclass(frozen=True)
class Target:
    param: str
    id: int

    @property
    def key(self) -> str:
        return f"{self.param}:{self.id}"


def menu_buttons():
    return []


def _target(update: dict) -> Target | None:
    chat_id = update.get("chat_id")
    if chat_id is not None:
        return Target("chat_id", int(chat_id))
    message = update.get("message") or (update.get("callback") or {}).get("message") or {}
    recipient = message.get("recipient") or {}
    if recipient.get("chat_id") is not None:
        return Target("chat_id", int(recipient["chat_id"]))
    sender = message.get("sender") or update.get("user") or (update.get("callback") or {}).get("user") or {}
    user_id = sender.get("user_id")
    return Target("user_id", int(user_id)) if user_id is not None else None


def _event_key(update: dict) -> str:
    callback_id = (update.get("callback") or {}).get("callback_id")
    if callback_id:
        return f"callback:{callback_id}"
    message = update.get("message") or {}
    message_id = (message.get("body") or {}).get("mid")
    if message_id:
        return f"message:{message_id}"
    raw = json.dumps(update, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def _search_all(storage: Storage, query: str, limit: int = 5):
    combined = []
    for source in SOURCE_NAMES:
        combined.extend((item.score, source, item) for item in search(storage, source, query, limit))
    combined.sort(key=lambda row: (-row[0], row[2].title.lower()))
    return combined[:limit]


def _format_results(query: str, results) -> tuple[str, list]:
    if not results:
        return (
            f"По запросу «{query}» ничего не найдено. "
            "Попробуйте сократить запрос или заменить окончание слова.",
            [],
        )
    lines = ["Нашёл во всех базах:"]
    buttons = []
    for number, (_, source, item) in enumerate(results, 1):
        lines.append(f"\n{number}. {item.title}\nИсточник: {SOURCE_NAMES[source]}\n{item.snippet}")
        buttons.append([{"type": "link", "text": f"Открыть результат {number}", "url": item.url}])
    return "\n".join(lines)[:3990], buttons


async def handle_update(update: dict, storage: Storage, api: MaxAPI) -> None:
    target = _target(update)
    if not target:
        log.warning("В событии нет адресата: %s", update.get("update_type"))
        return
    if not storage.mark_once(_event_key(update)):
        return

    update_type = update.get("update_type")
    if update_type == "bot_started":
        await api.send(
            target.param,
            target.id,
            "Здравствуйте! Напишите ключевые слова — я выполню поиск сразу по всем базам.",
        )
        return

    if update_type == "message_callback":
        callback = update.get("callback") or {}
        payload = callback.get("payload", "")
        callback_id = callback.get("callback_id")
        if callback_id:
            await api.answer_callback(callback_id)
        if payload.startswith("source:") and payload[7:] in SOURCE_NAMES:
            await api.send(target.param, target.id, "Выбор базы больше не требуется. Напишите ключевые слова — поиск выполняется везде.")
        return

    if update_type != "message_created":
        return
    message = update.get("message") or {}
    sender = message.get("sender") or {}
    if sender.get("is_bot"):
        return
    text = ((message.get("body") or {}).get("text") or "").strip()
    if text.lower() in {"/start", "старт", "меню"}:
        await api.send(target.param, target.id, "Напишите ключевые слова — поиск выполняется сразу по всем базам.")
        return
    if len(text) < 2:
        await api.send(target.param, target.id, "Введите хотя бы два символа для поиска.")
        return
    result_text, buttons = _format_results(text[:200], _search_all(storage, text))
    await api.send(target.param, target.id, result_text, buttons)
