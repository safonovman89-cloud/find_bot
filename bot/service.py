from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

from .ai import AIQueryAnalyzer
from .max_api import MaxAPI
from .search import search, words
from .storage import Storage

log = logging.getLogger(__name__)
SOURCE_NAMES = {
    "rsed": "РСЭД",
    "esku": "ГИС ЕСКУ",
    "kb": "База знаний ЯНАО",
    "files": "Документы ЯНАО",
}

SYSTEMS = {
    "rsed": {
        "name": "РСЭД",
        "aliases": ("рсэд", "тезис", "диадок", "мэдо"),
        "sources": ("rsed", "files"),
    },
    "esku": {
        "name": "ГИС ЕСКУ",
        "aliases": ("гис еску", "еску", "гис смета", "смета янао"),
        "sources": ("esku", "files"),
    },
    "rsud": {
        "name": "ГИС РСУД",
        "aliases": ("гис рсуд", "рсуд", "региональная система управления данными"),
        "sources": ("kb", "files"),
    },
    "r7": {
        "name": "Р7-Офис",
        "aliases": ("р7 офис", "р7-офис", "r7 офис", "r7-office"),
        "sources": ("kb", "files"),
    },
    "epd": {
        "name": "Единый почтовый домен",
        "aliases": ("единый почтовый домен", "епд"),
        "sources": ("kb", "files"),
    },
    "esv": {
        "name": "Единая система видеонаблюдения",
        "aliases": ("единая система видеонаблюдения", "есв"),
        "sources": ("kb", "files"),
    },
    "bbb": {
        "name": "BigBlueButton",
        "aliases": ("bigbluebutton", "bbb", "веб конференция"),
        "sources": ("kb", "files"),
    },
    "sreda": {
        "name": "Сервис «Среда»",
        "aliases": ("сервис среда", "коммуникационный сервис среда"),
        "sources": ("kb", "files"),
    },
    "antivirus": {
        "name": "Единая антивирусная защита",
        "aliases": ("антивирусная защита", "антивирус", "касперский", "kaspersky"),
        "sources": ("kb", "files"),
    },
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


def _detect_system(text: str) -> str | None:
    folded = text.lower().replace("ё", "е")
    matches = []
    for key, config in SYSTEMS.items():
        for alias in config["aliases"]:
            normalized = alias.lower().replace("ё", "е")
            if normalized in folded:
                matches.append((len(normalized), key))
    return max(matches)[1] if matches else None


def _search_all(storage: Storage, query: str, context: str | None = None, limit: int = 5):
    combined = []
    config = SYSTEMS.get(context or "")
    sources = config["sources"] if config else tuple(SOURCE_NAMES)
    for source in sources:
        required = config["aliases"] if config and source in {"files", "kb"} else ()
        boost = config["aliases"] if config else ()
        items = search(storage, source, query, limit, required_any=required, boost_terms=boost)
        combined.extend((item.score, source, item) for item in items)
    combined.sort(key=lambda row: (-row[0], row[2].title.lower()))
    return combined[:limit]


def _format_results(query: str, results, context: str | None = None) -> tuple[str, list]:
    context_name = SYSTEMS.get(context or "", {}).get("name")
    if not results:
        scope = f" в контексте «{context_name}»" if context_name else ""
        return (
            f"По запросу «{query}»{scope} ничего не найдено. "
            "Попробуйте сократить запрос или напишите «искать везде» для сброса контекста.",
            [],
        )
    lines = [f"Контекст поиска: {context_name}" if context_name else "Нашёл во всех базах:"]
    buttons = []
    for number, (_, source, item) in enumerate(results, 1):
        lines.append(f"\n{number}. {item.title}\nИсточник: {SOURCE_NAMES[source]}\n{item.snippet}")
        buttons.append([{"type": "link", "text": f"Открыть результат {number}", "url": item.url}])
    return "\n".join(lines)[:3990], buttons


async def handle_update(
    update: dict,
    storage: Storage,
    api: MaxAPI,
    ai: AIQueryAnalyzer | None = None,
) -> None:
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
            "Здравствуйте! Напишите систему и вопрос, например: «РСЭД — как подписать документ?». "
            "Я запомню систему для следующих уточнений. Команда /reset сбрасывает контекст.",
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
    if text.lower() in {"/start", "старт"}:
        storage.clear_conversation(target.key)
        await api.send(target.param, target.id, "Напишите систему и вопрос. Я сохраню контекст диалога на 24 часа.")
        return
    if text.lower() in {"/reset", "сброс", "сбросить контекст", "искать везде", "меню"}:
        storage.clear_conversation(target.key)
        await api.send(target.param, target.id, "Контекст и история очищены. Следующий запрос будет искаться по всем базам.")
        return
    if len(text) < 2:
        await api.send(target.param, target.id, "Введите хотя бы два символа для поиска.")
        return
    previous_queries = storage.recent_user_queries(target.key, limit=3)
    explicit_context = _detect_system(text)
    saved_context = storage.get_context(target.key)
    understanding = None
    if ai:
        understanding = await ai.understand(
            text=text,
            history=list(reversed(previous_queries)),
            current_context=explicit_context or saved_context,
        )
    context = explicit_context or (understanding.system if understanding else None) or saved_context
    if context and (explicit_context or (understanding and understanding.system)):
        storage.set_context(target.key, context)
    query = text
    if understanding:
        query = understanding.search_query
    is_followup = len(words(text)) <= 3 or text.lower().startswith(
        ("а ", "и ", "как ", "где ", "что ", "почему ", "можно ")
    )
    if not understanding and context and is_followup and previous_queries:
        query = f"{text} {previous_queries[0]}"
    storage.add_history(target.key, "user", text)
    results = _search_all(storage, query, context=context)
    result_text, buttons = _format_results(text[:200], results, context=context)
    storage.add_history(target.key, "assistant", " | ".join(item.title for _, _, item in results))
    await api.send(target.param, target.id, result_text, buttons)
