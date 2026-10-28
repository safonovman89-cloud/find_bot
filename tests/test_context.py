from pathlib import Path

from bot.search import SearchResult
from bot.service import (
    RSED_DOCUMENT_CREATION_STEPS,
    _detect_system,
    _format_results,
    _is_rsed_document_creation_request,
    _search_all,
    _search_rsed_document_creation,
)
from bot.storage import Storage


def test_detects_named_system():
    assert _detect_system("Как подписать документ в РСЭД?") == "rsed"
    assert _detect_system("Не открывается ГИС ЕСКУ") == "esku"
    assert _detect_system("Настройка Р7-Офис") == "r7"


def test_detects_rsed_document_creation_request():
    assert _is_rsed_document_creation_request("Как создать документ в РСЭД?", "rsed")
    assert _is_rsed_document_creation_request("Создание карточки документа", "rsed")
    assert not _is_rsed_document_creation_request("Как подписать документ?", "rsed")
    assert not _is_rsed_document_creation_request("Как создать документ?", "esku")


def test_context_filters_unrelated_results(tmp_path: Path):
    storage = Storage(str(tmp_path / "test.sqlite3"))
    storage.replace_source("rsed", [
        {"title": "Подписание документа", "url": "https://rsed/1", "content": "Как подписать документ"},
    ])
    storage.replace_source("esku", [
        {"title": "Подписание документа", "url": "https://esku/1", "content": "Как подписать документ"},
    ])
    storage.replace_source("files", [
        {"title": "Руководство РСЭД", "url": "https://files/РСЭД/1", "content": "РСЭД: как подписать документ"},
        {"title": "Руководство ЕСКУ", "url": "https://files/ЕСКУ/2", "content": "ГИС ЕСКУ: как подписать документ"},
    ])
    results = _search_all(storage, "как подписать", context="rsed", limit=10)
    urls = {item.url for _, _, item in results}
    assert "https://rsed/1" in urls
    assert "https://files/РСЭД/1" in urls
    assert "https://esku/1" not in urls
    assert "https://files/ЕСКУ/2" not in urls


def test_r7_context_rejects_incidental_mentions(tmp_path: Path):
    storage = Storage(str(tmp_path / "test.sqlite3"))
    storage.replace_source("kb", [
        {
            "title": "Регистрация и авторизация",
            "url": "https://kb.yanao.ru/books/r7-ofis/page/registraciia",
            "content": "Настройка и вход в Р7-Офис",
        },
    ])
    storage.replace_source("files", [
        {
            "title": "Руководство ТЕЗИС.pdf",
            "url": "https://files.yanao.ru/download?path=Материалы РСЭД Тезис",
            "content": "Система ТЕЗИС. Где-то внутри текста упомянут Р7-Офис.",
        },
    ])
    results = _search_all(storage, "как настроить р 7 офис", context="r7", limit=10)
    assert [item.url for _, _, item in results] == [
        "https://kb.yanao.ru/books/r7-ofis/page/registraciia"
    ]


def test_rsed_creation_uses_exact_user_guide_page(tmp_path: Path):
    storage = Storage(str(tmp_path / "test.sqlite3"))
    guide_url = (
        "https://instructions.yanao.ru/books/instrukciya-polzovatelya-gis-rsed/"
        "page/11-sozdanie-kartocki-dokumenta-isxodyashhego-vnutrennego"
    )
    storage.replace_source("rsed", [
        {
            "title": "1.1. Создание карточки документа (исходящего, внутреннего)",
            "url": guide_url,
            "content": "Для создания документа выберите способ, вид документа или шаблон.",
        },
        {
            "title": "Обновление РСЭД",
            "url": "https://instructions.yanao.ru/books/updates/page/latest",
            "content": "Создать документ в РСЭД. " * 20,
        },
    ])
    storage.replace_source("files", [
        {
            "title": "Большое руководство пользователя РСЭД.docx",
            "url": "https://files.example/manual.docx",
            "content": "Создать документ в РСЭД. " * 100,
        },
    ])

    results = _search_rsed_document_creation(storage)

    assert len(results) == 1
    assert results[0][1] == "rsed"
    assert results[0][2].url == guide_url


def test_rsed_creation_is_formatted_as_numbered_instruction():
    result = SearchResult(
        title="1.1. Создание карточки документа",
        url="https://instructions.example/rsed/create",
        snippet="Для создания документа откройте меню Документы.",
        score=20,
    )
    text, _ = _format_results(
        "как создать документ в РСЭД",
        [(20, "rsed", result)],
        context="rsed",
        summary=RSED_DOCUMENT_CREATION_STEPS,
        procedural=True,
    )

    assert "<b>Пошаговая инструкция:</b>" in text
    assert "1. Откройте создание документа" in text
    assert "4. В открывшейся карточке" in text
    assert '<a href="https://instructions.example/rsed/create">[1]</a>' in text


def test_history_and_context_can_be_cleared(tmp_path: Path):
    storage = Storage(str(tmp_path / "test.sqlite3"))
    storage.set_context("user_id:1", "rsed")
    storage.add_history("user_id:1", "user", "Как подписать?")
    assert storage.get_context("user_id:1") == "rsed"
    assert storage.recent_user_queries("user_id:1") == ["Как подписать?"]
    storage.clear_conversation("user_id:1")
    assert storage.get_context("user_id:1") is None
    assert storage.recent_user_queries("user_id:1") == []


def test_result_titles_and_citations_are_hyperlinks():
    result = SearchResult(
        title="Доступ к Р7-Офис",
        url="https://kb.example/r7?x=1&y=2",
        snippet="Инструкция по входу",
        score=10,
    )
    text, _ = _format_results(
        "как войти",
        [(10, "kb", result)],
        context="r7",
        summary="Откройте портал из инструкции [1].",
    )
    assert '<a href="https://kb.example/r7?x=1&amp;y=2">[1]</a>' in text
    assert '<a href="https://kb.example/r7?x=1&amp;y=2">Доступ к Р7-Офис</a>' in text
    assert "<b>Краткий ответ:</b>" in text


def test_legacy_apbook_links_use_public_domain():
    result = SearchResult(
        title="Создание обращения ГИС ЕСКУ",
        url="http://apbook.yanao.int/books/gis-esku/page/create?from=bot",
        snippet="Инструкция по созданию обращения",
        score=10,
    )
    text, buttons = _format_results(
        "как создать обращение",
        [(10, "esku", result)],
        context="esku",
        summary="Следуйте инструкции [1].",
    )

    public = "https://apbook.yanao.ru/books/gis-esku/page/create?from=bot"
    assert f'<a href="{public}">[1]</a>' in text
    assert f'<a href="{public}">Создание обращения ГИС ЕСКУ</a>' in text
    assert buttons[0][0]["url"] == public
