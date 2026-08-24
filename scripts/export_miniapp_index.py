#!/usr/bin/env python3
"""Export the bot search corpus to a compact, public mini-app index."""

from __future__ import annotations

import json
import base64
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "bot.sqlite3"
OUTPUT = ROOT / "miniapp" / "public" / "search-index.json"
BLOOM_BITS = 8192
BLOOM_BYTES = BLOOM_BITS // 8
WORD_RE = re.compile(r"[a-zа-я0-9]{2,}", re.IGNORECASE)
SUFFIX_RE = re.compile(
    r"(иями|ями|ами|ого|ему|ому|ыми|ими|иях|ах|ях|ия|ие|ий|ый|ая|ое|ую|ей|ов|ам|ям|ом|ем|ить|ать|ять|ться|ть|ы|и|а|я|е|у|ю)$"
)


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\x00", " ")).strip()


def stem(value: str) -> str:
    word = value.lower().replace("ё", "е")
    return SUFFIX_RE.sub("", word) if len(word) >= 5 else word


def fnv1a(value: str, seed: int) -> int:
    result = seed
    for byte in value.encode("utf-8"):
        result ^= byte
        result = (result * 16777619) & 0xFFFFFFFF
    return result


def bloom_signature(value: str) -> str:
    signature = bytearray(BLOOM_BYTES)
    terms = {stem(word) for word in WORD_RE.findall(value) if len(stem(word)) >= 2}
    for term in terms:
        for seed in (2166136261, 519786371, 3144134277):
            position = fnv1a(term, seed) % BLOOM_BITS
            signature[position // 8] |= 1 << (position % 8)
    return base64.b64encode(signature).decode("ascii")


def main() -> None:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT source, title, url, content FROM pages ORDER BY source, title"
    ).fetchall()
    connection.close()

    documents = [
        {
            "source": row["source"],
            "title": compact_text(row["title"]),
            "url": row["url"],
            "bloom": bloom_signature(f'{row["title"]} {row["content"]} {row["url"]}'),
        }
        for row in rows
        if row["url"] and row["content"]
    ]

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": documents,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Exported {len(documents)} documents to {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
