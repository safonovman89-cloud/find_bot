from __future__ import annotations

import re
from dataclasses import dataclass

from .storage import Storage

WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float


def words(text: str) -> list[str]:
    return [w.lower().replace("ё", "е") for w in WORD_RE.findall(text)]


def _snippet(content: str, terms: list[str], size: int = 230) -> str:
    folded = content.lower().replace("ё", "е")
    positions = [folded.find(term) for term in terms if folded.find(term) >= 0]
    start = max(0, (min(positions) if positions else 0) - 60)
    end = min(len(content), start + size)
    text = re.sub(r"\s+", " ", content[start:end]).strip()
    return ("…" if start else "") + text + ("…" if end < len(content) else "")


def search(storage: Storage, source: str, query: str, limit: int = 5) -> list[SearchResult]:
    terms = list(dict.fromkeys(words(query)))[:12]
    if not terms:
        return []
    ranked: list[SearchResult] = []
    for page in storage.all_pages(source):
        title = page["title"].lower().replace("ё", "е")
        content = page["content"].lower().replace("ё", "е")
        matched = sum(term in title or term in content for term in terms)
        if not matched:
            continue
        score = matched / len(terms) * 10
        score += sum(5 for term in terms if term in title)
        score += sum(min(content.count(term), 8) * 0.15 for term in terms)
        if all(term in title or term in content for term in terms):
            score += 4
        ranked.append(SearchResult(page["title"], page["url"], _snippet(page["content"], terms), score))
    ranked.sort(key=lambda item: (-item.score, item.title.lower()))
    return ranked[:limit]

