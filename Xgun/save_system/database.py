"""SQLite persistence layer.

One database file holds every local account, wallet, inventory, progression
record and the metadata of the local social network.  Schema changes are
applied through ordered migrations recorded in ``schema_version`` so old
save files upgrade in place.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

MIGRATIONS: list[str] = [
    # 1 — accounts, economy, inventory, progression
    """
    CREATE TABLE accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        display_name TEXT NOT NULL,
        bio TEXT NOT NULL DEFAULT '',
        avatar_color TEXT NOT NULL DEFAULT '#7C4DFF',
        is_demo INTEGER NOT NULL DEFAULT 0,
        private_account INTEGER NOT NULL DEFAULT 0,
        allow_comments INTEGER NOT NULL DEFAULT 1,
        created_at REAL NOT NULL
    );
    CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE wallets (
        account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
        balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0)
    );
    CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        amount INTEGER NOT NULL,
        balance_after INTEGER NOT NULL,
        kind TEXT NOT NULL,
        reason TEXT NOT NULL,
        item_id TEXT,
        created_at REAL NOT NULL
    );
    CREATE TABLE owned_items (
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        item_id TEXT NOT NULL,
        source TEXT NOT NULL,
        acquired_at REAL NOT NULL,
        PRIMARY KEY (account_id, item_id)
    );
    CREATE TABLE loadout (
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        slot TEXT NOT NULL,
        item_id TEXT NOT NULL,
        PRIMARY KEY (account_id, slot)
    );
    CREATE TABLE stats (
        account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
        matches INTEGER NOT NULL DEFAULT 0,
        wins INTEGER NOT NULL DEFAULT 0,
        top10 INTEGER NOT NULL DEFAULT 0,
        eliminations INTEGER NOT NULL DEFAULT 0,
        damage_dealt INTEGER NOT NULL DEFAULT 0,
        chests_opened INTEGER NOT NULL DEFAULT 0,
        time_alive REAL NOT NULL DEFAULT 0,
        xp INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE match_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        placement INTEGER NOT NULL,
        players INTEGER NOT NULL,
        eliminations INTEGER NOT NULL,
        damage INTEGER NOT NULL,
        xon_earned INTEGER NOT NULL,
        xp_earned INTEGER NOT NULL,
        duration REAL NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE TABLE quest_progress (
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        quest_id TEXT NOT NULL,
        period TEXT NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0,
        claimed INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (account_id, quest_id, period)
    );
    CREATE TABLE reward_claims (
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        reward_key TEXT NOT NULL,
        claimed_at REAL NOT NULL,
        PRIMARY KEY (account_id, reward_key)
    );
    """,
    # 2 — friends
    """
    CREATE TABLE friend_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        to_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at REAL NOT NULL
    );
    CREATE TABLE friends (
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        friend_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (account_id, friend_id)
    );
    """,
    # 3 — social video network
    """
    CREATE TABLE videos (
        id TEXT PRIMARY KEY,
        owner_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        file_path TEXT NOT NULL,
        title TEXT NOT NULL,
        caption TEXT NOT NULL DEFAULT '',
        hashtags TEXT NOT NULL DEFAULT '',
        duration REAL NOT NULL DEFAULT 0,
        width INTEGER NOT NULL DEFAULT 0,
        height INTEGER NOT NULL DEFAULT 0,
        size_bytes INTEGER NOT NULL DEFAULT 0,
        visibility TEXT NOT NULL DEFAULT 'public',
        allow_comments INTEGER NOT NULL DEFAULT 1,
        views INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active',
        is_sample INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL
    );
    CREATE INDEX videos_owner ON videos(owner_id);
    CREATE TABLE video_likes (
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (account_id, video_id)
    );
    CREATE TABLE video_saves (
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (account_id, video_id)
    );
    CREATE TABLE video_views (
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        last_viewed REAL NOT NULL,
        PRIMARY KEY (account_id, video_id)
    );
    CREATE TABLE comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        text TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_at REAL NOT NULL
    );
    CREATE INDEX comments_video ON comments(video_id);
    CREATE TABLE follows (
        follower_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        followee_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (follower_id, followee_id)
    );
    CREATE TABLE blocks (
        blocker_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        blocked_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (blocker_id, blocked_id)
    );
    CREATE TABLE reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        created_at REAL NOT NULL,
        UNIQUE (reporter_id, target_type, target_id)
    );
    """,
]


class Database:
    """Thin, thread-safe wrapper around a single SQLite connection."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    # -- schema ---------------------------------------------------------
    def _migrate(self) -> None:
        with self._lock:
            self.conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self.conn.execute("SELECT version FROM schema_version").fetchone()
            current = row[0] if row else 0
            if row is None:
                self.conn.execute("INSERT INTO schema_version VALUES (0)")
            for index in range(current, len(MIGRATIONS)):
                # executescript commits implicitly, so the migration and its
                # version bump travel together inside one explicit transaction.
                script = (f"BEGIN; {MIGRATIONS[index]}\n"
                          f"UPDATE schema_version SET version = {index + 1}; COMMIT;")
                try:
                    self.conn.executescript(script)
                except sqlite3.Error:
                    if self.conn.in_transaction:
                        self.conn.execute("ROLLBACK")
                    raise

    @property
    def schema_version(self) -> int:
        return self.conn.execute("SELECT version FROM schema_version").fetchone()[0]

    # -- helpers --------------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Atomic block. Nested calls join the outer transaction."""
        with self._lock:
            if self.conn.in_transaction:
                yield self.conn
                return
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            else:
                self.conn.execute("COMMIT")

    @staticmethod
    def _params(params: Iterable[Any] | dict) -> tuple | dict:
        return params if isinstance(params, dict) else tuple(params)

    def execute(self, sql: str, params: Iterable[Any] | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, self._params(params))

    def one(self, sql: str, params: Iterable[Any] | dict = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, self._params(params)).fetchone()

    def all(self, sql: str, params: Iterable[Any] | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, self._params(params)).fetchall()

    def scalar(self, sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
        row = self.one(sql, params)
        return default if row is None or row[0] is None else row[0]

    def get_state(self, key: str, default: str | None = None) -> str | None:
        return self.scalar("SELECT value FROM app_state WHERE key = ?", (key,), default)

    def set_state(self, key: str, value: str) -> None:
        self.execute("INSERT INTO app_state(key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def close(self) -> None:
        with self._lock:
            self.conn.close()


def now() -> float:
    return time.time()
