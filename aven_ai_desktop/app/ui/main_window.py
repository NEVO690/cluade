"""Main application window and conversation controller."""

from __future__ import annotations

import contextlib
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMainWindow, QMessageBox, QSplitter, QStackedWidget

from app.ai import errors
from app.ai.base_provider import ChatMessage
from app.ai.chat_service import ChatService
from app.ai.prompts import MODES
from app.code.blocks import extract_blocks
from app.code.files import attachment_block, plan_save, write_files
from app.code.validation import validate_reply
from app.config.catalog import catalog
from app.config.secrets import CredentialStore
from app.config.settings import AppSettings, SettingsStore
from app.storage.conversation_repository import Conversation, ConversationRepository, generate_title
from app.storage.database import StorageError
from app.studio.projects import ProjectStore
from app.ui.chat_view import ChatView
from app.ui.logo import app_icon
from app.ui.message_widget import AssistantMessageWidget
from app.ui.settings_dialog import SettingsDialog
from app.ui.sidebar import Sidebar
from app.ui.studio_view import StudioView
from app.ui.theme_manager import ThemeManager
from app.version import APP_DISPLAY_NAME, __version__
from app.workers.ai_worker import StreamWorker

log = logging.getLogger(__name__)

# Number of messages rendered when a conversation opens; older ones load on demand.
PAGE_SIZE = 60
# How much attached file text goes into one message (on-device models have a smaller memory).
ATTACH_CHARS_LOCAL = 30_000
ATTACH_CHARS_CLOUD = 300_000
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
        project_store: ProjectStore | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.settings_store = settings_store
        self.credentials = credentials
        self.repo = repository
        self.theme = theme_manager
        self.chat_service = chat_service or ChatService(settings, credentials)
        self.projects = project_store or ProjectStore(repository.db)

        self.current: Conversation | None = None
        self.category = settings.category if catalog().category(settings.category) else "aven"
        self.mode = self.category if self.category in MODES else "aven"
        self.generation: Generation | None = None
        self._generation_counter = 0
        self._loaded_offset = 0  # index of the first rendered message in the current conversation
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_generation)

        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(900, 640)
        self.resize(1240, 820)

        palette = self.theme.palette
        self.sidebar = Sidebar(palette)
        self.chat = ChatView(palette)
        self.studio = StudioView(self.projects, self.chat_service, palette)
        self.main_stack = QStackedWidget()
        self.main_stack.addWidget(self.chat)
        self.main_stack.addWidget(self.studio)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.main_stack)
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
        self.chat.set_mode(self.mode)
        self._restore_geometry()

        # Keep the model the user chose (including one saved by AVEN AI 1.x) for the category it was used in.
        category = catalog().category(self.category)
        if self.category not in self.settings.category_models and self.settings.model in category.models:
            self.settings.category_models[self.category] = self.settings.model
        self.set_category(self.category, force=True)
        if self.settings.last_seen_version != __version__:
            QTimer.singleShot(400, self.show_whats_new)
        QTimer.singleShot(1500, self.refresh_access_quietly)

    # --- wiring -----------------------------------------------------------------------
    def _connect_signals(self) -> None:
        self.sidebar.new_conversation_requested.connect(self.new_conversation)
        self.sidebar.conversation_selected.connect(self.open_conversation)
        self.sidebar.rename_requested.connect(self.rename_conversation)
        self.sidebar.delete_requested.connect(self.delete_conversation)
        self.sidebar.settings_requested.connect(self.open_settings)
        self.sidebar.theme_toggle_requested.connect(self.toggle_theme)
        self.sidebar.category_selected.connect(self.set_category)
        self.sidebar.whats_new_requested.connect(self.show_whats_new)
        self.sidebar.account_requested.connect(self.open_account)
        self.chat.subscribe_requested.connect(self.open_account)
        self.chat.refresh_access_requested.connect(self.refresh_access)
        self.studio.projects_changed.connect(self.refresh_sidebar)
        self.studio.download_requested.connect(self.download_selected_model)
        self.studio.settings_requested.connect(lambda: self.open_settings(provider_tab=True))
        self.studio.model_changed.connect(self.set_model)
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
        for index, category_id in enumerate(catalog().categories, start=1):
            QShortcut(QKeySequence(f"Ctrl+{index}"), self, activated=lambda c=category_id: self.set_category(c))

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
            if self.category == "made":
                entries = self.projects.list()
                current = self.studio.project.id if self.studio.project else None
            else:
                entries = self.repo.list_conversations(self.category)
                current = self.current.id if self.current else None
        except StorageError as exc:
            self._storage_failed(exc)
            return
        self.sidebar.set_conversations(entries, current)

    def update_status(self) -> None:
        status = self.chat_service.status(self.category)
        notes = self._model_notes()
        if self.category == "made":
            self.studio.set_status(status)
            self.studio.model_picker.set_notes(notes)
        else:
            self.chat.set_status(status)
            self.chat.model_picker.set_notes(notes)

    # --- categories -------------------------------------------------------------------------
    def set_category(self, category_id: str, force: bool = False) -> None:
        category = catalog().category(category_id)
        if category is None or (category_id == self.category and not force):
            return
        if self.studio.busy and category_id != "made":
            QMessageBox.information(self, "Made With AVEN", "The game is still being built. Press Stop first.")
            self.sidebar.set_category(self.category)
            return
        self.stop_generation()
        self.category = category_id
        self.settings.category = category_id
        model = self.settings.category_models.get(category_id, category.default_model)
        self.settings.model = model if model in category.models else category.default_model
        self.save_settings()
        self.sidebar.set_category(category_id)
        if category.kind == "studio":
            self.main_stack.setCurrentWidget(self.studio)
            self.studio.model_picker.set_current(self.settings.model)
            self.studio.show_dashboard()
            self.current = None
            self.refresh_sidebar()
            self.update_status()
        else:
            self.main_stack.setCurrentWidget(self.chat)
            self.mode = category_id
            self.chat.set_mode(category_id)
            self.chat.set_model(self.settings.model)
            self.new_conversation()
            self.refresh_sidebar()

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
        if self.category == "made":
            self.studio.show_dashboard()
            self.studio.description_input.setFocus()
            return
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
        if self.category == "made":
            self.studio.open_project(conversation_id)
            return
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
        self.mode = conversation.mode if conversation.mode in MODES else "aven"
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
            self._check_code(widget)

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
        if self.category == "made":
            self._rename_project(conversation_id)
            return
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
        if self.category == "made":
            self._delete_project(conversation_id)
            return
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

    def _rename_project(self, project_id: int) -> None:
        project = self.projects.get(project_id)
        if project is None:
            return
        title, ok = QInputDialog.getText(self, "Rename game", "Title:", text=project.title)
        if ok and title.strip():
            self.projects.rename(project, title)
            if self.studio.project is not None and self.studio.project.id == project_id:
                self.studio.open_project(project_id)
            self.refresh_sidebar()

    def _delete_project(self, project_id: int) -> None:
        project = self.projects.get(project_id)
        if project is None or self.studio.busy:
            return
        answer = QMessageBox.question(
            self,
            "Delete game?",
            f"“{project.title}” and all its versions will be permanently deleted from this computer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.projects.delete(project)
        except (StorageError, OSError) as exc:
            QMessageBox.warning(self, "Delete failed", str(exc))
            return
        self.studio.show_dashboard()
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
        self.settings.category_models[self.category] = model_id
        self.save_settings()
        self.chat.set_model(model_id)
        self.studio.model_picker.set_current(model_id)
        self.update_status()

    def _assistant_name(self) -> str:
        return MODES[self.mode].name if self.mode in MODES else "AVEN AI"

    # --- sending & generation ---------------------------------------------------------------
    def send_message(self, text: str) -> None:
        if self.generation is not None:
            return  # duplicate submission guard
        text = text.strip()
        if not text:
            return
        status = self.chat_service.status(self.category)
        if not status.ready and status.needs_subscription:
            self.update_status()
            self.open_account()
            return
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

        content = text
        if self.chat.attachments:
            limit = ATTACH_CHARS_LOCAL if self.settings.provider == "aven_local" else ATTACH_CHARS_CLOUD
            block, left_out = attachment_block(self.chat.attachments, limit)
            if (
                left_out
                and QMessageBox.question(
                    self,
                    "Some files do not fit",
                    f"{len(left_out)} file(s) do not fit in what this model can read at once and will be left out:\n"
                    + "\n".join(left_out[:10])
                    + "\n\nSend anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            content = f"{text}\n\n{block}"
        try:
            if self.current is None:
                self.current = self.repo.create_conversation(self.mode, generate_title(text))
                self.chat.set_title(self.current.title)
            message = self.repo.add_message(self.current.id, "user", content)
        except StorageError as exc:
            self._storage_failed(exc)
            return

        self.chat.clear_input()
        self.chat.clear_attachments()
        self.chat.remove_errors()
        self.chat.add_user_message(content, message.id)
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
            provider = self.chat_service.create_provider(category=self.mode)
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
        self._check_code(generation.widget)
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

    # --- code categories ----------------------------------------------------------------------
    def _check_code(self, widget: AssistantMessageWidget) -> None:
        """Run the category's static code checks on a reply (nothing is executed)."""
        category = catalog().category(self.mode)
        if category is None or not category.validators or not widget.content:
            return
        try:
            report = validate_reply(widget.content, category.validators)
        except Exception:  # a checker problem must never break the chat
            log.exception("Code checks failed")
            return
        has_files = any(block.path for block in extract_blocks(widget.content))
        widget.set_code_report(report, has_files)
        if has_files and not getattr(widget, "_save_connected", False):
            widget.save_files_requested.connect(self.save_files)
            widget._save_connected = True

    def save_files(self, widget: AssistantMessageWidget) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Save the files into this folder")
        if not folder:
            return
        files, problems = plan_save(extract_blocks(widget.content), Path(folder))
        if not files:
            QMessageBox.warning(self, "Nothing to save", "\n".join(problems) or "This reply names no files.")
            return
        existing = [str(f.relative) for f in files if f.exists]
        summary = "\n".join(str(f.relative) for f in files[:20])
        question = f"Save {len(files)} file(s) into {folder}?\n\n{summary}"
        if existing:
            question += f"\n\n{len(existing)} existing file(s) will be overwritten:\n" + "\n".join(existing[:10])
        if problems:
            question += "\n\nSkipped (unsafe paths):\n" + "\n".join(problems[:10])
        if (
            QMessageBox.question(
                self, "Save files", question, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            written = write_files(files)
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        QMessageBox.information(self, "Files saved", f"Saved {len(written)} file(s) to {folder}.")

    # --- account, access and release notes --------------------------------------------------------
    def open_account(self) -> None:
        from app.ui.account_dialog import AccountDialog

        dialog = AccountDialog(self.chat_service.account, self)
        dialog.access_changed.connect(self.update_status)
        dialog.exec()
        self.update_status()

    def refresh_access(self) -> None:
        from app.ai.errors import ProviderError
        from app.workers.ai_worker import TaskWorker

        def work():
            from app.account.service import AccountError

            try:
                return self.chat_service.account.refresh()
            except AccountError as exc:
                raise ProviderError(str(exc)) from exc

        worker = TaskWorker(work)
        worker.signals.succeeded.connect(lambda _status: self.update_status())
        worker.signals.failed.connect(lambda exc: QMessageBox.warning(self, "Subscription", exc.user_message))
        worker.start()

    def refresh_access_quietly(self) -> None:
        """At startup, renew the signed entitlement of an existing account (errors are ignored)."""
        account = self.chat_service.account
        if not (account.available and account.account_id):
            return
        from app.workers.ai_worker import TaskWorker

        worker = TaskWorker(account.refresh)
        worker.signals.succeeded.connect(lambda _status: self.update_status())
        worker.start()

    def show_whats_new(self) -> None:
        from app.ui.whats_new import WhatsNewDialog

        dialog = WhatsNewDialog(self)
        dialog.setModal(False)  # the app stays usable while it is open
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
        self.settings.last_seen_version = __version__
        self.save_settings()

    # --- settings & theme ---------------------------------------------------------------------
    def open_settings(self, provider_tab: bool = False) -> None:
        dialog = SettingsDialog(self.settings, self.credentials, self)
        if provider_tab or not self.chat_service.status(self.category).ready:
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
        # Just switched to AVEN Local: offer the one-time model download straight away.
        status = self.chat_service.status(self.category)
        if self.settings.provider == "aven_local" and status.needs_download:
            self.download_selected_model()

    def toggle_theme(self) -> None:
        self.settings.theme = "light" if self.theme.palette.dark else "dark"
        self.theme.apply(self.settings.theme)
        self.save_settings()

    def _on_theme_changed(self, palette) -> None:
        self.sidebar.apply_palette(palette)
        self.chat.apply_palette(palette)
        self.studio.apply_palette(palette)

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
