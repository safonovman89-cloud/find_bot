from __future__ import annotations

import hashlib
import html
import json
import logging
import re
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
        "url_hints": {"files": ("рсэд", "тезис", "диадок")},
    },
    "esku": {
        "name": "ГИС ЕСКУ",
        "aliases": ("гис еску", "еску", "гис смета", "смета янао"),
        "sources": ("esku", "files"),
        "url_hints": {"files": ("еску", "гис смета")},
    },
    "rsud": {
        "name": "ГИС РСУД",
        "aliases": ("гис рсуд", "рсуд", "региональная система управления данными"),
        "sources": ("kb", "files"),
        "url_hints": {
            "kb": ("/books/regionalnaia-sistema-upravleniia-dannymi-rsud/", "/books/avtorizaciia-v-gis-rsud/"),
            "files": ("рсуд",),
        },
    },
    "r7": {
        "name": "Р7-Офис",
        "aliases": ("р7 офис", "р 7 офис", "р7-офис", "r7 офис", "r7-office"),
        "sources": ("kb", "files"),
        "url_hints": {"kb": ("/books/r7-ofis/",), "files": ("р7", "r7")},
    },
    "epd": {
        "name": "Единый почтовый домен",
        "aliases": ("единый почтовый домен", "епд"),
        "sources": ("kb", "files"),
        "url_hints": {"kb": ("/books/edinyi-poctovyi-domen-epd/",), "files": ("епд", "почтовый домен")},
    },
    "esv": {
        "name": "Единая система видеонаблюдения",
        "aliases": ("единая система видеонаблюдения", "есв"),
        "sources": ("kb", "files"),
        "url_hints": {"kb": ("/books/edinaia-sistema-videonabliudeniia-esv/",), "files": ("есв", "видеонаблюден")},
    },
    "bbb": {
        "name": "BigBlueButton",
        "aliases": ("bigbluebutton", "bbb", "веб конференция"),
        "sources": ("kb", "files"),
        "url_hints": {"kb": ("/books/bigbluebutton-bbb-veb-konferencii/",), "files": ("bigbluebutton", "bbb")},
    },
    "sreda": {
        "name": "Сервис «Среда»",
        "aliases": ("сервис среда", "коммуникационный сервис среда"),
        "sources": ("kb", "files"),
        "url_hints": {"kb": ("/books/kommunikacionnyi-servis-sreda/",), "files": ("среда",)},
    },
    "antivirus": {
        "name": "Единая антивирусная защита",
        "aliases": ("антивирусная защита", "антивирус", "касперский", "kaspersky"),
        "sources": ("kb", "files"),
        "url_hints": {"kb": ("/books/edinaia-antivirusnaia-zashhita-ianao/",), "files": ("антивирус", "касперск", "kaspersky")},
    },
}

HELP_TEXT = (
    "Как пользоваться ботом:\n\n"
    "1. Напишите систему и вопрос, например: «РСЭД — как подписать документ?».\n"
    "2. Откройте один из найденных результатов.\n"
    "3. Задавайте уточнения без повторения системы — я помню контекст.\n\n"
    "Примеры:\n"
    "• ГИС ЕСКУ — как создать обращение?\n"
    "• РСУД — как получить API-токен?\n"
    "• Как настроить Р7-Офис?\n\n"
    "/reset или «искать везде» — очистить контекст.\n"
    "/help — снова показать эту инструкцию."
)

BOT_COMMANDS = [
    {"name": "start", "description": "Начать новый поиск"},
    {"name": "help", "description": "Показать инструкцию"},
    {"name": "reset", "description": "Очистить историю и контекст"},
]

RSED_DOCUMENT_CREATION_QUERY = "создание карточки документа исходящего внутреннего"
RSED_DOCUMENT_CREATION_URL_HINT = (
    "/books/instrukciya-polzovatelya-gis-rsed/page/11-sozdanie-kartocki-dokumenta"
)
RSED_DOCUMENT_CREATION_STEPS = (
    "1. Откройте создание документа одним из способов: «Документы» → «Создать документ»; "
    "кнопка «Создать документ», «Создать исходящий документ» или «Создать внутренний документ»; "
    "либо кнопка «Создать» в списке документов.\n"
    "2. В открывшемся окне выберите канцелярский вид документа.\n"
    "3. Выберите вид документа или подходящий шаблон и подтвердите создание.\n"
    "4. В открывшейся карточке заполните основные сведения. Набор полей зависит от выбранного "
    "вида документа. [1]"
)


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


def _is_rsed_document_creation_request(text: str, context: str | None) -> bool:
    """Recognize requests for the canonical RSED document-creation procedure."""
    if context != "rsed":
        return False
    folded = text.lower().replace("ё", "е")
    has_document = re.search(r"\bдокумент\w*", folded) is not None
    has_creation = re.search(r"\b(?:созда\w*|завест\w*|оформить)\b", folded) is not None
    return has_document and has_creation


def _search_rsed_document_creation(storage: Storage):
    """Prefer the exact user-guide page over large manuals and release notes."""
    items = search(
        storage,
        "rsed",
        RSED_DOCUMENT_CREATION_QUERY,
        limit=1,
        url_hints=(RSED_DOCUMENT_CREATION_URL_HINT,),
    )
    if not items:
        items = search(
            storage,
            "rsed",
            RSED_DOCUMENT_CREATION_QUERY,
            limit=1,
            required_any=("создание карточки документа",),
        )
    return [(item.score, "rsed", item) for item in items]


def _search_all(storage: Storage, query: str, context: str | None = None, limit: int = 5):
    combined = []
    config = SYSTEMS.get(context or "")
    sources = config["sources"] if config else tuple(SOURCE_NAMES)
    for source in sources:
        boost = config["aliases"] if config else ()
        hints = config.get("url_hints", {}).get(source, ()) if config else ()
        items = search(storage, source, query, limit, boost_terms=boost, url_hints=hints)
        combined.extend((item.score, source, item) for item in items)
    combined.sort(key=lambda row: (-row[0], row[2].title.lower()))
    return combined[:limit]


def _format_results(
    query: str,
    results,
    context: str | None = None,
    summary: str | None = None,
    procedural: bool = False,
) -> tuple[str, list]:
    context_name = SYSTEMS.get(context or "", {}).get("name")
    if not results:
        scope = f" в контексте «{context_name}»" if context_name else ""
        return (
            f"По запросу «{html.escape(query)}»{html.escape(scope)} ничего не найдено. "
            "Попробуйте сократить запрос или напишите «искать везде» для сброса контекста.",
            [],
        )
    result_urls = {str(number): item.url for number, (_, _, item) in enumerate(results, 1)}

    def link_citations(text: str) -> str:
        escaped = html.escape(text)
        return re.sub(
            r"\[(\d+)\]",
            lambda match: (
                f'<a href="{html.escape(result_urls[match.group(1)], quote=True)}">'
                f'[{match.group(1)}]</a>'
                if match.group(1) in result_urls
                else match.group(0)
            ),
            escaped,
        )

    lines = []
    if context_name:
        lines.append(f"<b>Контекст поиска:</b> {html.escape(context_name)}")
    if summary:
        if lines:
            lines.append("")
        answer_title = "Пошаговая инструкция" if procedural else "Краткий ответ"
        lines.extend([f"<b>{answer_title}:</b>", link_citations(summary), "", "<b>Материалы:</b>"])
    elif not context_name:
        lines.append("<b>Нашёл во всех базах:</b>")
    buttons = []
    for number, (_, source, item) in enumerate(results, 1):
        safe_url = html.escape(item.url, quote=True)
        safe_title = html.escape(item.title[:220])
        item_text = (
            f'\n{number}. <a href="{safe_url}">{safe_title}</a>'
            f"\nИсточник: {html.escape(SOURCE_NAMES[source])}"
        )
        if not summary:
            item_text += f"\n{html.escape(item.snippet)}"
        lines.append(item_text)
        buttons.append([{"type": "link", "text": f"Открыть результат {number}", "url": item.url}])
    return "\n".join(lines), buttons


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
        await api.send(target.param, target.id, "Здравствуйте!\n\n" + HELP_TEXT)
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
        await api.send(target.param, target.id, HELP_TEXT)
        return
    if text.lower() in {"/help", "помощь", "как пользоваться", "инструкция"}:
        await api.send(target.param, target.id, HELP_TEXT)
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
    procedural = _is_rsed_document_creation_request(text, context)
    if procedural:
        query = RSED_DOCUMENT_CREATION_QUERY
    storage.add_history(target.key, "user", text)
    results = (
        _search_rsed_document_creation(storage)
        if procedural
        else _search_all(storage, query, context=context)
    )
    summary = RSED_DOCUMENT_CREATION_STEPS if procedural and results else None
    if ai and results and not procedural:
        evidence = [
            {
                "number": str(number),
                "title": item.title,
                "source": SOURCE_NAMES[source],
                "excerpt": item.snippet,
            }
            for number, (_, source, item) in enumerate(results[:4], 1)
        ]
        summary = await ai.summarize(
            question=text,
            context_name=SYSTEMS.get(context or "", {}).get("name"),
            evidence=evidence,
        )
    result_text, buttons = _format_results(
        text[:200],
        results,
        context=context,
        summary=summary,
        procedural=procedural,
    )
    storage.add_history(target.key, "assistant", " | ".join(item.title for _, _, item in results))
    await api.send(target.param, target.id, result_text, buttons, text_format="html")
