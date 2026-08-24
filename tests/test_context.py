from pathlib import Path

from bot.service import _detect_system, _search_all
from bot.storage import Storage


def test_detects_named_system():
    assert _detect_system("Как подписать документ в РСЭД?") == "rsed"
    assert _detect_system("Не открывается ГИС ЕСКУ") == "esku"
    assert _detect_system("Настройка Р7-Офис") == "r7"


def test_context_filters_unrelated_results(tmp_path: Path):
    storage = Storage(str(tmp_path / "test.sqlite3"))
    storage.replace_source("rsed", [
        {"title": "Подписание документа", "url": "https://rsed/1", "content": "Как подписать документ"},
    ])
    storage.replace_source("esku", [
        {"title": "Подписание документа", "url": "https://esku/1", "content": "Как подписать документ"},
    ])
    storage.replace_source("files", [
        {"title": "Руководство РСЭД", "url": "https://files/1", "content": "РСЭД: как подписать документ"},
        {"title": "Руководство ЕСКУ", "url": "https://files/2", "content": "ГИС ЕСКУ: как подписать документ"},
    ])
    results = _search_all(storage, "как подписать", context="rsed", limit=10)
    urls = {item.url for _, _, item in results}
    assert "https://rsed/1" in urls
    assert "https://files/1" in urls
    assert "https://esku/1" not in urls
    assert "https://files/2" not in urls


def test_history_and_context_can_be_cleared(tmp_path: Path):
    storage = Storage(str(tmp_path / "test.sqlite3"))
    storage.set_context("user_id:1", "rsed")
    storage.add_history("user_id:1", "user", "Как подписать?")
    assert storage.get_context("user_id:1") == "rsed"
    assert storage.recent_user_queries("user_id:1") == ["Как подписать?"]
    storage.clear_conversation("user_id:1")
    assert storage.get_context("user_id:1") is None
    assert storage.recent_user_queries("user_id:1") == []
