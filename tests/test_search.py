from pathlib import Path

from bot.search import search
from bot.storage import Storage


def test_search_prefers_title(tmp_path: Path):
    storage = Storage(str(tmp_path / "test.sqlite3"))
    storage.replace_source("rsed", [
        {"title": "Создание документа", "url": "https://example/1", "content": "Как создать карточку документа"},
        {"title": "Общие сведения", "url": "https://example/2", "content": "Документ можно создать из меню"},
    ])
    results = search(storage, "rsed", "создание документа")
    assert results[0].url == "https://example/1"


def test_search_handles_yo(tmp_path: Path):
    storage = Storage(str(tmp_path / "test.sqlite3"))
    storage.replace_source("esku", [
        {"title": "Отчётность", "url": "https://example/1", "content": "Формирование отчёта"},
    ])
    assert search(storage, "esku", "отчет")

