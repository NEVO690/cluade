from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from app.ai import errors
from app.ai.chat_service import ChatService
from app.config.secrets import CredentialStore
from app.config.settings import AppSettings, SettingsStore
from app.storage.conversation_repository import ConversationRepository
from app.storage.database import Database
from app.ui.main_window import MainWindow
from app.ui.message_widget import AssistantMessageWidget, CodeBlockWidget, ErrorWidget, UserMessageWidget
from app.ui.settings_dialog import SettingsDialog
from app.ui.theme_manager import ThemeManager
from tests.conftest import FakeProvider


@pytest.fixture
def make_window(qtbot, qapp, tmp_path):
    def factory(provider=None, configured: bool = True):
        credentials = CredentialStore(use_keyring=False)
        if configured:
            credentials.save_key("anthropic", "sk-test-key-123456")
        settings = AppSettings(theme="dark")
        theme = ThemeManager(qapp)
        theme.apply("dark")
        repo = ConversationRepository(Database(tmp_path / "ui.db"))
        holder = {"provider": provider or FakeProvider()}
        service = ChatService(settings, credentials, provider_factory=lambda *a, **k: holder["provider"])
        window = MainWindow(settings, SettingsStore(tmp_path / "settings.json"), credentials, repo, theme, service)
        qtbot.addWidget(window)
        window.resize(1100, 760)
        window.show()
        return window, repo, holder

    return factory


def widgets_of(window, cls):
    return [w for w in window.chat.message_widgets() if isinstance(w, cls)]


def test_window_initializes_with_welcome_screen(make_window) -> None:
    window, _repo, _ = make_window()
    assert window.windowTitle() == "AVEN AI Desktop"
    assert window.chat.stack.currentIndex() == 0
    assert "claude-opus-5-5" in window.chat.model_label.text()
    assert window.chat.setup_card.isHidden()


def test_unconfigured_state_shows_setup_and_never_calls_provider(make_window, monkeypatch) -> None:
    provider = FakeProvider()
    window, repo, _ = make_window(provider, configured=False)
    assert not window.chat.setup_card.isHidden()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    window.send_message("hello")
    assert provider.requests == []
    assert repo.list_conversations() == []


def test_send_streams_response_and_persists(make_window, qtbot) -> None:
    reply = "Sure!\n\n```python\nprint('hi')\n```\n\nDone."
    window, repo, _ = make_window(FakeProvider(reply=reply))
    window.chat.input.setPlainText("Write hello world")
    qtbot.keyClick(window.chat.input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.generation is None, timeout=5000)

    conversation = repo.list_conversations()[0]
    assert conversation.title == "Write hello world"
    messages = repo.list_messages(conversation.id)
    assert [(m.role, m.content) for m in messages] == [("user", "Write hello world"), ("assistant", reply)]
    assert messages[1].model == "claude-opus-5-5"
    assistant = widgets_of(window, AssistantMessageWidget)[0]
    codes = [w for w in assistant.findChildren(CodeBlockWidget)]
    assert len(codes) == 1 and codes[0]._code == "print('hi')"
    assert window.chat.input.toPlainText() == ""
    assert window.chat.send_button.text() == "Send"


def test_shift_enter_inserts_newline(make_window, qtbot) -> None:
    window, repo, _ = make_window()
    window.chat.input.setPlainText("line one")
    window.chat.input.moveCursor(window.chat.input.textCursor().MoveOperation.End)
    qtbot.keyClick(window.chat.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert window.chat.input.toPlainText() == "line one\n"
    assert repo.list_conversations() == []


def test_duplicate_submission_is_ignored(make_window, qtbot) -> None:
    provider = FakeProvider(reply="x" * 200, delay=0.02, chunk=2)
    window, repo, _ = make_window(provider)
    window.send_message("first")
    window.send_message("second")  # ignored while generating
    assert window.chat.busy
    qtbot.waitUntil(lambda: window.generation is None, timeout=10000)
    messages = repo.list_messages(repo.list_conversations()[0].id)
    assert [m.content for m in messages if m.role == "user"] == ["first"]
    assert len(provider.requests) == 1


def test_stop_generation_keeps_partial_response(make_window, qtbot) -> None:
    provider = FakeProvider(reply="word " * 400, delay=0.01, chunk=3)
    window, repo, _ = make_window(provider)
    window.send_message("long please")
    qtbot.waitUntil(lambda: window.generation is not None and len(window.generation.text) > 10, timeout=5000)
    window.stop_generation()
    assert window.generation is None
    assert not window.chat.busy
    messages = repo.list_messages(repo.list_conversations()[0].id)
    assert messages[-1].role == "assistant"
    assert messages[-1].status == "stopped"
    assert 0 < len(messages[-1].content) < len("word " * 400)


def test_error_shows_card_and_retry_succeeds(make_window, qtbot) -> None:
    window, repo, holder = make_window(FakeProvider(error=errors.RateLimitedError("Slow down.")))
    window.send_message("hello")
    qtbot.waitUntil(lambda: window.generation is None, timeout=5000)
    cards = widgets_of(window, ErrorWidget)
    assert len(cards) == 1
    assert widgets_of(window, AssistantMessageWidget) == []
    conversation_id = repo.list_conversations()[0].id
    assert [m.role for m in repo.list_messages(conversation_id)] == ["user"]

    holder["provider"] = FakeProvider(reply="Recovered.")
    qtbot.mouseClick(cards[0].retry_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: window.generation is None and bool(widgets_of(window, AssistantMessageWidget)), timeout=5000
    )
    assert [m.role for m in repo.list_messages(conversation_id)] == ["user", "assistant"]


def test_regenerate_replaces_last_answer(make_window, qtbot) -> None:
    window, repo, holder = make_window(FakeProvider(reply="First answer."))
    window.send_message("question")
    qtbot.waitUntil(lambda: window.generation is None, timeout=5000)
    holder["provider"] = FakeProvider(reply="Second answer.")
    window.regenerate()
    qtbot.waitUntil(lambda: window.generation is None, timeout=5000)
    messages = repo.list_messages(repo.list_conversations()[0].id)
    assert [m.content for m in messages] == ["question", "Second answer."]


def test_mode_switch_is_saved_and_changes_prompt(make_window, qtbot) -> None:
    provider = FakeProvider(reply="ok")
    window, repo, _ = make_window(provider)
    qtbot.mouseClick(window.chat.mode_buttons["code"], Qt.MouseButton.LeftButton)
    assert window.mode == "code"
    window.send_message("fix my code")
    qtbot.waitUntil(lambda: window.generation is None, timeout=5000)
    assert repo.list_conversations()[0].mode == "code"
    assert "AVEN CODE" in provider.requests[0].system_prompt


def test_open_rename_and_delete_conversations(make_window, monkeypatch) -> None:
    window, repo, _ = make_window()
    conversation = repo.create_conversation("aven", "Saved chat")
    repo.add_message(conversation.id, "user", "old question")
    repo.add_message(conversation.id, "assistant", "old answer")
    window.refresh_sidebar()

    window.open_conversation(conversation.id)
    assert window.chat.title_label.text() == "Saved chat"
    assert len(widgets_of(window, UserMessageWidget)) == 1
    assert len(widgets_of(window, AssistantMessageWidget)) == 1

    monkeypatch.setattr("app.ui.main_window.QInputDialog.getText", lambda *a, **k: ("Renamed", True))
    window.rename_conversation(conversation.id)
    assert repo.get_conversation(conversation.id).title == "Renamed"
    assert window.chat.title_label.text() == "Renamed"

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.delete_conversation(conversation.id)
    assert repo.list_conversations() == []
    assert window.current is None
    assert window.chat.stack.currentIndex() == 0


def test_long_conversations_load_in_pages(make_window) -> None:
    window, repo, _ = make_window()
    conversation = repo.create_conversation()
    for i in range(150):
        repo.add_message(conversation.id, "user" if i % 2 == 0 else "assistant", f"message {i}")
    window.open_conversation(conversation.id)
    assert len(window.chat.message_widgets()) == 60
    assert window.chat.load_earlier_button.isVisible()
    window.load_earlier()
    window.load_earlier()
    assert len(window.chat.message_widgets()) == 150
    assert not window.chat.load_earlier_button.isVisible()
    first = window.chat.message_widgets()[0]
    assert isinstance(first, UserMessageWidget) and first.content == "message 0"


def test_theme_toggle_rerenders(make_window) -> None:
    window, _repo, _ = make_window()
    assert window.theme.palette.dark
    window.toggle_theme()
    assert not window.theme.palette.dark
    assert window.settings.theme == "light"


def test_settings_dialog_saves_key_and_models(make_window, qtbot, monkeypatch) -> None:
    window, _repo, _ = make_window(configured=False)
    notices = []
    # Without a credential store the dialog explains the key is session-only.
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: notices.append(a[1]))
    dialog = SettingsDialog(window.settings, window.credentials, window)
    qtbot.addWidget(dialog)
    assert dialog.aven_model.currentText() == "claude-opus-5-5"
    dialog.key_edit.setText("sk-ant-new-key-987654")
    dialog.code_model.setCurrentText("claude-sonnet-5-5")
    dialog.theme_combo.setCurrentIndex(2)
    dialog._on_save()
    assert dialog.result() == SettingsDialog.DialogCode.Accepted
    assert window.credentials.get_key("anthropic") == "sk-ant-new-key-987654"
    assert notices == ["Key kept for this session"]
    assert dialog.settings.model_for_mode("code") == "claude-sonnet-5-5"
    assert dialog.settings.theme == "dark"
    assert window.settings.model_for_mode("code") == "claude-opus-5-5"  # unchanged until applied


def test_settings_dialog_rejects_insecure_base_url(make_window, qtbot, monkeypatch) -> None:
    window, _repo, _ = make_window()
    dialog = SettingsDialog(window.settings, window.credentials, window)
    qtbot.addWidget(dialog)
    dialog.provider_combo.setCurrentIndex(1)
    dialog.base_url_edit.setText("http://remote.example.com/v1")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a))
    dialog._on_save()
    assert warnings
    assert dialog.result() != SettingsDialog.DialogCode.Accepted


def test_connection_test_reports_real_result(make_window, qtbot, monkeypatch) -> None:
    window, _repo, _ = make_window()
    dialog = SettingsDialog(window.settings, window.credentials, window)
    qtbot.addWidget(dialog)
    monkeypatch.setattr(dialog, "_make_provider", lambda: FakeProvider(reply="OK"))
    dialog._on_test()
    qtbot.waitUntil(lambda: dialog.test_button.isEnabled(), timeout=5000)
    assert dialog.result_label.text().startswith("✓")
    assert "OK" in dialog.result_label.text()

    monkeypatch.setattr(
        dialog, "_make_provider", lambda: FakeProvider(error=errors.AuthenticationFailedError("Bad key."))
    )
    dialog._on_test()
    qtbot.waitUntil(lambda: dialog.test_button.isEnabled(), timeout=5000)
    assert dialog.result_label.text().startswith("✕")
    assert "Bad key." in dialog.result_label.text()
