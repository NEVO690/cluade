"""Main application window and conversation controller."""

from __future__ import annotations

import contextlib
import logging
import threading
from dataclasses import dataclass

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QInputDialog, QMainWindow, QMessageBox, QSplitter

from app.ai import errors
from app.ai.base_provider import ChatMessage
from app.ai.chat_service import ChatService
from app.ai.prompts import MODES
from app.config.secrets import CredentialStore
from app.config.settings import AppSettings, SettingsStore
from app.storage.conversation_repository import Conversation, ConversationRepository, generate_title
from app.storage.database import StorageError
from app.ui.chat_view import ChatView
from app.ui.logo import app_icon
from app.ui.message_widget import AssistantMessageWidget
from app.ui.settings_dialog import SettingsDialog
from app.ui.sidebar import Sidebar
from app.ui.theme_manager import ThemeManager
from app.version import APP_DISPLAY_NAME
from app.workers.ai_worker import StreamWorker

log = logging.getLogger(__name__)

# Number of messages rendered when a conversation opens; older ones load on demand.
PAGE_SIZE = 60
RENDER_INTERVAL_MS = 50


@dataclass
class Generation:
    id: int
    conversation_id: int
    mode: str
    aven_model: str  # AVEN model id saved with the reply
    widget: AssistantMessageWidget
    cancel_event: threading.Event
    worker: StreamWorker
    text: str = ""
    truncated: bool = False


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: AppSettings,
        settings_store: SettingsStore,
        credentials: CredentialStore,
        repository: ConversationRepository,
        theme_manager: ThemeManager,
        chat_service: ChatService | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.settings_store = settings_store
        self.credentials = credentials
        self.repo = repository
        self.theme = theme_manager
        self.chat_service = chat_service or ChatService(settings, credentials)

        self.current: Conversation | None = None
        self.mode = "aven"
        self.generation: Generation | None = None
        self._generation_counter = 0
        self._loaded_offset = 0  # index of the first rendered message in the current conversation
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_generation)

        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(760, 520)
        self.resize(1240, 820)

        palette = self.theme.palette
        self.sidebar = Sidebar(palette)
        self.chat = ChatView(palette)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.chat)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([270, 970])
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        self.setCentralWidget(splitter)

        self._connect_signals()
        self._install_shortcuts()
        self.theme.changed.connect(self._on_theme_changed)
        self.chat.set_send_with_enter(settings.send_with_enter)
        self.chat.set_model(settings.model)
        self.chat.set_mode(self.mode)
        self._restore_geometry()

        self.refresh_sidebar()
        self.new_conversation()

    # --- wiring -----------------------------------------------------------------------
    def _connect_signals(self) -> None:
        self.sidebar.new_conversation_requested.connect(self.new_conversation)
        self.sidebar.conversation_selected.connect(self.open_conversation)
        self.sidebar.rename_requested.connect(self.rename_conversation)
        self.sidebar.delete_requested.connect(self.delete_conversation)
        self.sidebar.settings_requested.connect(self.open_settings)
        self.sidebar.theme_toggle_requested.connect(self.toggle_theme)
        self.chat.send_requested.connect(self.send_message)
        self.chat.stop_requested.connect(self.stop_generation)
        self.chat.mode_changed.connect(self.set_mode)
        self.chat.model_changed.connect(self.set_model)
        self.chat.settings_requested.connect(self.open_settings)
        self.chat.download_requested.connect(self.download_selected_model)
        self.chat.retry_requested.connect(self.retry)
        self.chat.regenerate_requested.connect(self.regenerate)
        self.chat.load_earlier_requested.connect(self.load_earlier)

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence.StandardKey.New, self, activated=self.new_conversation)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.open_settings)
        QShortcut(QKeySequence("Escape"), self, activated=self._on_escape)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.chat.focus_input)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self._switch_mode_from_shortcut("aven"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self._switch_mode_from_shortcut("code"))

    def _switch_mode_from_shortcut(self, mode: str) -> None:
        self.chat.set_mode(mode)
        self.set_mode(mode)

    def _on_escape(self) -> None:
        if self.generation is not None:
            self.stop_generation()

    # --- error helpers -------------------------------------------------------------------
    def _storage_failed(self, exc: StorageError) -> None:
        log.error("Storage error: %s", exc)
        QMessageBox.critical(self, "Storage error", f"{exc}\n\nYour latest change may not have been saved.")

    # --- conversations ---------------------------------------------------------------------
    def refresh_sidebar(self) -> None:
        try:
            conversations = self.repo.list_conversations()
        except StorageError as exc:
            self._storage_failed(exc)
            return
        self.sidebar.set_conversations(conversations, self.current.id if self.current else None)

    def update_status(self) -> None:
        self.chat.set_status(self.chat_service.status())
        self.chat.model_picker.set_notes(self._model_notes())

    def _model_notes(self) -> dict[str, str]:
        if self.settings.provider != "aven_local":
            return {}
        from app.local.downloader import is_downloaded
        from app.local.models import LOCAL_MODELS

        return {
            model_id: "· On this computer" if is_downloaded(local.file) else f"· {local.file.size_text} download"
            for model_id, local in LOCAL_MODELS.items()
        }

    def download_selected_model(self) -> bool:
        """Download the model behind the selected AVEN model (AVEN Local). Returns True when ready."""
        from app.ui.download_dialog import DownloadDialog

        dialog = DownloadDialog(self.settings.model, self)
        ok = dialog.exec() == DownloadDialog.DialogCode.Accepted
        self.update_status()
        return ok

    def new_conversation(self) -> None:
        self.stop_generation()
        self.current = None
        self.chat.clear_messages()
        self.chat.set_title("New conversation")
        self.chat.set_mode(self.mode)
        self.chat.show_welcome()
        self.sidebar.set_current(None)
        self.update_status()
        self.chat.focus_input()

    def open_conversation(self, conversation_id: int) -> None:
        if self.current is not None and self.current.id == conversation_id:
            return
        self.stop_generation()
        try:
            conversation = self.repo.get_conversation(conversation_id)
            messages = self.repo.list_messages(conversation_id) if conversation else []
        except StorageError as exc:
            self._storage_failed(exc)
            return
        if conversation is None:
            self.refresh_sidebar()
            return
        self.current = conversation
        self.mode = conversation.mode
        self.chat.set_mode(self.mode)
        self.chat.set_title(conversation.title)
        self.chat.clear_messages()
        self._loaded_offset = max(0, len(messages) - PAGE_SIZE)
        for message in messages[self._loaded_offset :]:
            self._render_stored_message(message)
        self.chat.set_has_earlier(self._loaded_offset > 0)
        if messages:
            self.chat.show_messages()
        else:
            self.chat.show_welcome()
        self.chat.refresh_regenerate_buttons()
        self.sidebar.set_current(conversation.id)
        self.update_status()
        self.chat.scroll_to_bottom()

    def _render_stored_message(self, message, at_top: bool = False) -> None:
        if message.role == "user":
            self.chat.add_user_message(message.content, message.id, at_top=at_top)
        else:
            widget = self.chat.add_assistant_message(
                self._assistant_name(), message.content, message.model, message.id, at_top=at_top
            )
            widget.finish(message.status)

    def load_earlier(self) -> None:
        if self.current is None or self._loaded_offset == 0:
            return
        try:
            messages = self.repo.list_messages(self.current.id)
        except StorageError as exc:
            self._storage_failed(exc)
            return
        start = max(0, self._loaded_offset - PAGE_SIZE)
        for message in reversed(messages[start : self._loaded_offset]):
            self._render_stored_message(message, at_top=True)
        self._loaded_offset = start
        self.chat.set_has_earlier(start > 0)
        self.chat.refresh_regenerate_buttons()

    def rename_conversation(self, conversation_id: int) -> None:
        try:
            conversation = self.repo.get_conversation(conversation_id)
        except StorageError as exc:
            self._storage_failed(exc)
            return
        if conversation is None:
            return
        title, ok = QInputDialog.getText(self, "Rename conversation", "Title:", text=conversation.title)
        if not ok or not title.strip():
            return
        try:
            self.repo.rename_conversation(conversation_id, title)
        except (StorageError, ValueError) as exc:
            QMessageBox.warning(self, "Rename failed", str(exc))
            return
        if self.current is not None and self.current.id == conversation_id:
            self.current = self.repo.get_conversation(conversation_id)
            self.chat.set_title(self.current.title if self.current else title)
        self.refresh_sidebar()

    def delete_conversation(self, conversation_id: int) -> None:
        answer = QMessageBox.question(
            self,
            "Delete conversation?",
            "This conversation will be permanently deleted from this computer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        is_current = self.current is not None and self.current.id == conversation_id
        if is_current:
            self.stop_generation()
        try:
            self.repo.delete_conversation(conversation_id)
        except StorageError as exc:
            self._storage_failed(exc)
            return
        if is_current:
            self.new_conversation()
        self.refresh_sidebar()

    def delete_all_conversations(self) -> None:
        self.stop_generation()
        try:
            self.repo.delete_all()
        except StorageError as exc:
            self._storage_failed(exc)
            return
        self.new_conversation()
        self.refresh_sidebar()

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            return
        self.mode = mode
        if self.current is not None:
            try:
                self.repo.set_mode(self.current.id, mode)
                self.current.mode = mode
            except StorageError as exc:
                self._storage_failed(exc)
            self.refresh_sidebar()
        self.update_status()

    def set_model(self, model_id: str) -> None:
        """AVEN model chosen in the message box; applies from the next message."""
        if model_id == self.settings.model:
            return
        self.settings.model = model_id
        self.save_settings()
        self.update_status()

    def _assistant_name(self) -> str:
        return MODES[self.mode].name

    # --- sending & generation ---------------------------------------------------------------
    def send_message(self, text: str) -> None:
        if self.generation is not None:
            return  # duplicate submission guard
        text = text.strip()
        if not text:
            return
        status = self.chat_service.status()
        if not status.ready and status.needs_download:
            if self.download_selected_model():
                self.send_message(text)
            return
        if not status.ready:
            self.update_status()
            if (
                QMessageBox.question(
                    self,
                    "Set up an AI provider",
                    f"{status.problem}\n\nOpen Settings now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                == QMessageBox.StandardButton.Yes
            ):
                self.open_settings(provider_tab=True)
            return

        try:
            if self.current is None:
                self.current = self.repo.create_conversation(self.mode, generate_title(text))
                self.chat.set_title(self.current.title)
            message = self.repo.add_message(self.current.id, "user", text)
        except StorageError as exc:
            self._storage_failed(exc)
            return

        self.chat.clear_input()
        self.chat.remove_errors()
        self.chat.add_user_message(text, message.id)
        self.chat.scroll_to_bottom()
        self.refresh_sidebar()
        self.start_generation()

    def start_generation(self) -> None:
        if self.current is None or self.generation is not None:
            return
        try:
            history = [ChatMessage(m.role, m.content) for m in self.repo.list_messages(self.current.id)]
        except StorageError as exc:
            self._storage_failed(exc)
            return
        try:
            request = self.chat_service.build_request(self.mode, history)
            provider = self.chat_service.create_provider()
        except errors.AIError as exc:
            self.chat.show_error(exc)
            self.update_status()
            return

        self._generation_counter += 1
        gid = self._generation_counter
        aven_model = self.settings.model
        widget = self.chat.add_assistant_message(self._assistant_name(), model=aven_model)
        worker = StreamWorker(gid, lambda: self.chat_service.stream(request, provider), request.cancel_event)
        worker.signals.text.connect(self._on_stream_text)
        worker.signals.truncated.connect(self._on_stream_truncated)
        worker.signals.finished.connect(self._on_stream_finished)
        worker.signals.failed.connect(self._on_stream_failed)
        self.generation = Generation(
            id=gid,
            conversation_id=self.current.id,
            mode=self.mode,
            aven_model=aven_model,
            widget=widget,
            cancel_event=request.cancel_event,
            worker=worker,
        )
        self.chat.set_busy(True)
        self.chat.scroll_to_bottom()
        log.info("Generation %d started (mode=%s)", gid, self.mode)
        worker.start()

    def _active(self, gid: int) -> Generation | None:
        generation = self.generation
        return generation if generation is not None and generation.id == gid else None

    def _on_stream_text(self, gid: int, delta: str) -> None:
        generation = self._active(gid)
        if generation is None:
            return
        generation.text += delta
        if not self._render_timer.isActive():
            self._render_timer.start(RENDER_INTERVAL_MS)

    def _render_generation(self) -> None:
        if self.generation is not None:
            self.generation.widget.set_content(self.generation.text)

    def _on_stream_truncated(self, gid: int) -> None:
        generation = self._active(gid)
        if generation is not None:
            generation.truncated = True

    def _on_stream_finished(self, gid: int) -> None:
        generation = self._active(gid)
        if generation is None:
            return
        if not generation.text.strip():
            self._on_stream_failed(gid, errors.ProviderError("The provider returned an empty response."))
            return
        self._complete_generation(generation, "truncated" if generation.truncated else "complete")

    def _on_stream_failed(self, gid: int, error: errors.AIError) -> None:
        generation = self._active(gid)
        if generation is None:
            return
        self._render_timer.stop()
        self.generation = None
        # Partial output from a failed or declined response is discarded, not saved.
        self.chat.remove_widget(generation.widget)
        self.chat.set_busy(False)
        self.chat.show_error(error)
        self.update_status()

    def _complete_generation(self, generation: Generation, status: str) -> None:
        self._render_timer.stop()
        self.generation = None
        generation.widget.set_content(generation.text)
        try:
            message = self.repo.add_message(
                generation.conversation_id,
                "assistant",
                generation.text,
                model=generation.aven_model,
                status=status,
            )
            generation.widget.message_id = message.id
        except StorageError as exc:
            self._storage_failed(exc)
        generation.widget.finish(status)
        self.chat.set_busy(False)
        self.update_status()
        self.refresh_sidebar()

    def stop_generation(self) -> None:
        generation = self.generation
        if generation is None:
            return
        generation.cancel_event.set()
        log.info("Generation %d stopped by user", generation.id)
        if generation.text.strip():
            self._complete_generation(generation, "stopped")
        else:
            self._render_timer.stop()
            self.generation = None
            self.chat.remove_widget(generation.widget)
            self.chat.set_busy(False)
            self.update_status()

    def retry(self) -> None:
        if self.generation is not None or self.current is None:
            return
        self.chat.remove_errors()
        self.start_generation()

    def regenerate(self) -> None:
        if self.generation is not None or self.current is None:
            return
        widgets = self.chat.message_widgets()
        last = widgets[-1] if widgets else None
        if not isinstance(last, AssistantMessageWidget):
            return
        try:
            if last.message_id is not None:
                self.repo.delete_message(last.message_id)
        except StorageError as exc:
            self._storage_failed(exc)
            return
        self.chat.remove_widget(last)
        self.start_generation()

    # --- settings & theme ---------------------------------------------------------------------
    def open_settings(self, provider_tab: bool = False) -> None:
        dialog = SettingsDialog(self.settings, self.credentials, self)
        if provider_tab or not self.chat_service.status().ready:
            dialog.tabs.setCurrentIndex(1)
        dialog.delete_all_requested.connect(self.delete_all_conversations)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            self.update_status()  # a key may have been removed
            return
        new = dialog.settings
        for name in (
            "theme",
            "provider",
            "model_map",
            "openai_base_url",
            "max_tokens",
            "request_timeout",
            "send_with_enter",
        ):
            setattr(self.settings, name, getattr(new, name))
        self.save_settings()
        self.theme.apply(self.settings.theme)
        self.chat.set_send_with_enter(self.settings.send_with_enter)
        self.update_status()

    def toggle_theme(self) -> None:
        self.settings.theme = "light" if self.theme.palette.dark else "dark"
        self.theme.apply(self.settings.theme)
        self.save_settings()

    def _on_theme_changed(self, palette) -> None:
        self.sidebar.apply_palette(palette)
        self.chat.apply_palette(palette)

    def save_settings(self) -> None:
        try:
            self.settings_store.save(self.settings)
        except OSError as exc:
            log.error("Could not save settings: %s", type(exc).__name__)
            QMessageBox.warning(self, "Settings not saved", f"Could not write the settings file: {exc}")

    # --- window state ----------------------------------------------------------------------------
    def _restore_geometry(self) -> None:
        if self.settings.window_geometry:
            with contextlib.suppress(ValueError, UnicodeEncodeError):
                self.restoreGeometry(QByteArray.fromBase64(self.settings.window_geometry.encode("ascii")))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt API)
        self.stop_generation()
        from app.local.engine import get_engine

        get_engine().stop()  # free the memory used by an on-device model
        self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.save_settings()
        super().closeEvent(event)
