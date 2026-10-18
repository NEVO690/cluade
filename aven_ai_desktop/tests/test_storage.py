from __future__ import annotations

import sqlite3
import time

import pytest

from app.storage.conversation_repository import DEFAULT_TITLE, ConversationRepository, generate_title
from app.storage.database import SCHEMA_VERSION, Database, StorageError


@pytest.fixture
def repo(tmp_path) -> ConversationRepository:
    return ConversationRepository(Database(tmp_path / "test.db"))


def test_create_and_list_conversations_most_recent_first(repo) -> None:
    first = repo.create_conversation("aven", "First")
    time.sleep(0.01)
    second = repo.create_conversation("code", "Second")
    assert [c.id for c in repo.list_conversations()] == [second.id, first.id]
    assert second.mode == "code"

    time.sleep(0.01)
    repo.add_message(first.id, "user", "bump")
    assert repo.list_conversations()[0].id == first.id  # activity moves it to the top


def test_messages_are_saved_in_order(repo) -> None:
    conversation = repo.create_conversation()
    repo.add_message(conversation.id, "user", "Hello")
    repo.add_message(conversation.id, "assistant", "Hi!", model="m-1", status="stopped")
    messages = repo.list_messages(conversation.id)
    assert [(m.role, m.content) for m in messages] == [("user", "Hello"), ("assistant", "Hi!")]
    assert messages[1].model == "m-1"
    assert messages[1].status == "stopped"
    assert repo.count_messages(conversation.id) == 2


def test_rename_set_mode_and_delete(repo) -> None:
    conversation = repo.create_conversation()
    repo.add_message(conversation.id, "user", "text")
    repo.rename_conversation(conversation.id, "  New   title ")
    repo.set_mode(conversation.id, "code")
    updated = repo.get_conversation(conversation.id)
    assert updated.title == "New title"
    assert updated.mode == "code"

    with pytest.raises(ValueError):
        repo.rename_conversation(conversation.id, "   ")

    repo.delete_conversation(conversation.id)
    assert repo.get_conversation(conversation.id) is None
    assert repo.list_messages(conversation.id) == []  # cascaded


def test_delete_single_message_and_all(repo) -> None:
    conversation = repo.create_conversation()
    message = repo.add_message(conversation.id, "assistant", "x")
    repo.delete_message(message.id)
    assert repo.list_messages(conversation.id) == []
    repo.create_conversation()
    repo.delete_all()
    assert repo.list_conversations() == []


def test_invalid_role_and_mode_rejected(repo) -> None:
    conversation = repo.create_conversation()
    with pytest.raises(ValueError):
        repo.add_message(conversation.id, "system", "nope")
    with pytest.raises(ValueError):
        repo.create_conversation(mode="other")


def test_persistence_across_connections(tmp_path) -> None:
    path = tmp_path / "persist.db"
    db = Database(path)
    conversation = ConversationRepository(db).create_conversation("code", "Kept")
    ConversationRepository(db).add_message(conversation.id, "user", "survives restarts")
    db.close()

    reopened = ConversationRepository(Database(path))
    assert reopened.list_conversations()[0].title == "Kept"
    assert reopened.list_messages(conversation.id)[0].content == "survives restarts"


def test_database_from_newer_version_is_refused(tmp_path) -> None:
    path = tmp_path / "future.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    conn.close()
    with pytest.raises(StorageError):
        Database(path)


def test_sqlite_errors_are_wrapped(repo) -> None:
    repo.conn.close()
    with pytest.raises(StorageError):
        repo.list_conversations()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("How do I center a div?", "How do I center a div?"),
        ("   ", DEFAULT_TITLE),
        ("```python\nprint(1)\n```", DEFAULT_TITLE),
        ("**Bold** _question_ here", "Bold question here"),
    ],
)
def test_generate_title(text: str, expected: str) -> None:
    assert generate_title(text) == expected


def test_generate_title_truncates_at_word_boundary() -> None:
    title = generate_title("Explain the difference between processes and threads in operating systems please")
    assert len(title) <= 49
    assert title.endswith("…")
    assert not title[:-1].endswith(" ")
