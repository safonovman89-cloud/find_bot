from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

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


def search(
    storage: Storage,
    source: str,
    query: str,
    limit: int = 5,
    required_any: tuple[str, ...] = (),
    boost_terms: tuple[str, ...] = (),
    url_hints: tuple[str, ...] = (),
) -> list[SearchResult]:
    terms = list(dict.fromkeys(words(query)))[:12]
    required = list(dict.fromkeys(value.lower().replace("ё", "е") for value in required_any))
    boosts = list(dict.fromkeys(word for value in boost_terms for word in words(value)))
    hints = list(dict.fromkeys(value.lower().replace("ё", "е") for value in url_hints))
    if not terms:
        return []
    ranked: list[SearchResult] = []
    for page in storage.all_pages(source):
        title = page["title"].lower().replace("ё", "е")
        content = page["content"].lower().replace("ё", "е")
        decoded_url = unquote(page["url"]).lower().replace("ё", "е")
        if hints and not any(hint in decoded_url for hint in hints):
            continue
        if required and not any(term in title or term in content for term in required):
            continue
        matched = sum(term in title or term in content for term in terms)
        if not matched:
            continue
        score = matched / len(terms) * 10
        score += sum(5 for term in terms if term in title)
        score += sum(min(content.count(term), 8) * 0.15 for term in terms)
        if all(term in title or term in content for term in terms):
            score += 4
        score += sum(2.5 for term in boosts if term in title)
        score += sum(0.4 for term in boosts if term in content)
        ranked.append(SearchResult(page["title"], page["url"], _snippet(page["content"], terms), score))
    ranked.sort(key=lambda item: (-item.score, item.title.lower()))
    return ranked[:limit]
