"""SQLite connection management and schema migrations."""

from __future__ import annotations

import contextlib
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)


class StorageError(Exception):
    """Raised when the local database cannot complete an operation."""


# Each entry migrates the schema from version N to N+1.
_MIGRATIONS: list[str] = [
    """
    CREATE TABLE conversations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT    NOT NULL,
        mode        TEXT    NOT NULL DEFAULT 'aven',
        created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );
    CREATE TABLE messages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role            TEXT    NOT NULL CHECK (role IN ('user', 'assistant')),
        content         TEXT    NOT NULL,
        model           TEXT,
        status          TEXT    NOT NULL DEFAULT 'complete',
        created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );
    CREATE INDEX idx_messages_conversation ON messages(conversation_id, id);
    CREATE INDEX idx_conversations_updated ON conversations(updated_at DESC);
    """,
]

SCHEMA_VERSION = len(_MIGRATIONS)


class Database:
    """Owns a single SQLite connection. Use from the GUI thread only."""

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        try:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.path, timeout=10)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            if self.path != ":memory:":
                self.conn.execute("PRAGMA journal_mode = WAL")
            self._migrate()
        except sqlite3.Error as exc:
            raise StorageError(f"Could not open the conversation database: {exc}") from exc

    def _migrate(self) -> None:
        current = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if current > SCHEMA_VERSION:
            raise StorageError(
                "The conversation database was created by a newer version of AVEN AI. Please update the application."
            )
        for version in range(current, SCHEMA_VERSION):
            log.info("Migrating database schema to version %d", version + 1)
            with self.conn:
                self.conn.executescript(_MIGRATIONS[version])
                self.conn.execute(f"PRAGMA user_version = {version + 1}")

    def close(self) -> None:
        with contextlib.suppress(sqlite3.Error):
            self.conn.close()
