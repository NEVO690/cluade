"""CRUD operations for conversations and messages."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import ParamSpec, TypeVar

from app.storage.database import Database, StorageError

MODES = ("aven", "code")
DEFAULT_TITLE = "New conversation"
TITLE_MAX_LENGTH = 48

P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class Conversation:
    id: int
    title: str
    mode: str
    created_at: str
    updated_at: str


@dataclass
class Message:
    id: int
    conversation_id: int
    role: str
    content: str
    model: str | None
    status: str
    created_at: str


def _wrap_errors(func: Callable[P, R]) -> Callable[P, R]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except sqlite3.Error as exc:
            raise StorageError(f"Database error: {exc}") from exc

    return wrapper


def generate_title(text: str) -> str:
    """Build a short title from the first user message (no AI call involved)."""
    text = re.sub(r"```.*?(```|$)", " ", text, flags=re.S)  # drop code blocks
    text = re.sub(r"[`*_#>\[\]]", "", text)
    text = " ".join(text.split())
    if not text:
        return DEFAULT_TITLE
    if len(text) <= TITLE_MAX_LENGTH:
        return text
    cut = text[:TITLE_MAX_LENGTH]
    if " " in cut[TITLE_MAX_LENGTH // 2 :]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,.;:-") + "…"


class ConversationRepository:
    def __init__(self, db: Database) -> None:
        self.conn = db.conn

    # --- conversations ---------------------------------------------------------
    @_wrap_errors
    def create_conversation(self, mode: str = "aven", title: str = DEFAULT_TITLE) -> Conversation:
        if mode not in MODES:
            raise ValueError(f"Unknown mode: {mode}")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO conversations (title, mode) VALUES (?, ?)", (title.strip() or DEFAULT_TITLE, mode)
            )
        conversation = self.get_conversation(cur.lastrowid)
        assert conversation is not None
        return conversation

    @_wrap_errors
    def get_conversation(self, conversation_id: int) -> Conversation | None:
        row = self.conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return Conversation(**dict(row)) if row else None

    @_wrap_errors
    def list_conversations(self) -> list[Conversation]:
        rows = self.conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC, id DESC").fetchall()
        return [Conversation(**dict(r)) for r in rows]

    @_wrap_errors
    def rename_conversation(self, conversation_id: int, title: str) -> None:
        title = " ".join(title.split())[:120]
        if not title:
            raise ValueError("The title cannot be empty.")
        with self.conn:
            self.conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))

    @_wrap_errors
    def set_mode(self, conversation_id: int, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"Unknown mode: {mode}")
        with self.conn:
            self.conn.execute("UPDATE conversations SET mode = ? WHERE id = ?", (mode, conversation_id))

    @_wrap_errors
    def delete_conversation(self, conversation_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    @_wrap_errors
    def delete_all(self) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM messages")
            self.conn.execute("DELETE FROM conversations")
        self.conn.execute("VACUUM")

    # --- messages --------------------------------------------------------------
    @_wrap_errors
    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        model: str | None = None,
        status: str = "complete",
    ) -> Message:
        if role not in ("user", "assistant"):
            raise ValueError(f"Invalid role: {role}")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO messages (conversation_id, role, content, model, status) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, role, content, model, status),
            )
            self.conn.execute(
                "UPDATE conversations SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
                (conversation_id,),
            )
        row = self.conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        return Message(**dict(row))

    @_wrap_errors
    def list_messages(self, conversation_id: int) -> list[Message]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        ).fetchall()
        return [Message(**dict(r)) for r in rows]

    @_wrap_errors
    def delete_message(self, message_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))

    @_wrap_errors
    def count_messages(self, conversation_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()[0]
