from __future__ import annotations

import sqlite3
from pathlib import Path


class Storage:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        return db

    def _init(self) -> None:
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS pages (
                    source TEXT NOT NULL,
                    url TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    fingerprint TEXT NOT NULL DEFAULT '',
                    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS pages_source ON pages(source);
                CREATE TABLE IF NOT EXISTS sessions (
                    target_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS processed_updates (
                    event_key TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS chat_context (
                    target_key TEXT PRIMARY KEY,
                    system_key TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_key TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS chat_history_target
                    ON chat_history(target_key, id DESC);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(pages)")}
            if "fingerprint" not in columns:
                db.execute("ALTER TABLE pages ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''")

    def replace_source(self, source: str, pages: list[dict[str, str]]) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM pages WHERE source = ?", (source,))
            db.executemany(
                "INSERT INTO pages(source, url, title, content, fingerprint) VALUES (?, ?, ?, ?, ?)",
                [(source, p["url"], p["title"], p["content"], p.get("fingerprint", "")) for p in pages],
            )

    def cached_pages(self, source: str) -> dict[str, sqlite3.Row]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT title, url, content, fingerprint FROM pages WHERE source = ?", (source,)
            ).fetchall()
        return {row["url"]: row for row in rows}

    def all_pages(self, source: str) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                "SELECT title, url, content FROM pages WHERE source = ?", (source,)
            ).fetchall()

    def counts(self) -> dict[str, int]:
        with self.connect() as db:
            rows = db.execute("SELECT source, count(*) count FROM pages GROUP BY source").fetchall()
        return {row["source"]: row["count"] for row in rows}

    def set_source(self, target_key: str, source: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO sessions(target_key, source) VALUES (?, ?) "
                "ON CONFLICT(target_key) DO UPDATE SET source=excluded.source, updated_at=CURRENT_TIMESTAMP",
                (target_key, source),
            )

    def get_source(self, target_key: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT source FROM sessions WHERE target_key = ?", (target_key,)).fetchone()
        return row["source"] if row else None

    def mark_once(self, event_key: str) -> bool:
        try:
            with self.connect() as db:
                db.execute("INSERT INTO processed_updates(event_key) VALUES (?)", (event_key,))
                db.execute("DELETE FROM processed_updates WHERE created_at < datetime('now', '-2 days')")
            return True
        except sqlite3.IntegrityError:
            return False

    def set_context(self, target_key: str, system_key: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO chat_context(target_key, system_key) VALUES (?, ?) "
                "ON CONFLICT(target_key) DO UPDATE SET "
                "system_key=excluded.system_key, updated_at=CURRENT_TIMESTAMP",
                (target_key, system_key),
            )

    def get_context(self, target_key: str) -> str | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT system_key FROM chat_context "
                "WHERE target_key = ? AND updated_at >= datetime('now', '-24 hours')",
                (target_key,),
            ).fetchone()
        return row["system_key"] if row else None

    def add_history(self, target_key: str, role: str, text: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO chat_history(target_key, role, text) VALUES (?, ?, ?)",
                (target_key, role, text[:1000]),
            )
            db.execute("DELETE FROM chat_history WHERE created_at < datetime('now', '-7 days')")
            db.execute(
                "DELETE FROM chat_history WHERE target_key = ? AND id NOT IN "
                "(SELECT id FROM chat_history WHERE target_key = ? ORDER BY id DESC LIMIT 40)",
                (target_key, target_key),
            )

    def recent_user_queries(self, target_key: str, limit: int = 3) -> list[str]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT text FROM chat_history WHERE target_key = ? AND role = 'user' "
                "ORDER BY id DESC LIMIT ?",
                (target_key, limit),
            ).fetchall()
        return [row["text"] for row in rows]

    def clear_conversation(self, target_key: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM chat_context WHERE target_key = ?", (target_key,))
            db.execute("DELETE FROM chat_history WHERE target_key = ?", (target_key,))
