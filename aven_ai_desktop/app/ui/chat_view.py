"""Main chat panel: header, message list, welcome screen and composer."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from app.ai.chat_service import ConfigStatus
from app.ai.errors import AIError
from app.ai.prompts import MODES
from app.code.files import AttachedFile, collect_folder, read_attachment
from app.config.aven_models import AVEN_MODELS, DEFAULT_AVEN_MODEL, AvenModel, aven_model_name, get_aven_model
from app.ui.category_nav import access_badge
from app.ui.logo import logo_pixmap
from app.ui.message_widget import AssistantMessageWidget, ErrorWidget, UserMessageWidget
from app.ui.theme_manager import Palette

CONTENT_MAX_WIDTH = 860
WELCOME_TITLES = {
    "aven": "How can I help you today?",
    "python": "What are we building in Python?",
    "unity": "What are we making in Unity?",
    "code": "What are we building today?",
}
MAX_INPUT_CHARS = 100_000
COMPOSER_MAX_LINES = 10


class ComposerInput(QPlainTextEdit):
    submit = Signal()
    focus_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ComposerInput")
        self.send_with_enter = True
        self.setTabChangesFocus(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(4)
        self.textChanged.connect(self._adjust_height)
        self._adjust_height()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt API)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            mods = event.modifiers()
            shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
            if ctrl or (self.send_with_enter and not shift):
                self.submit.emit()
                return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().focusInEvent(event)
        self.focus_changed.emit(True)

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().focusOutEvent(event)
        self.focus_changed.emit(False)

    def _adjust_height(self) -> None:
        line_height = self.fontMetrics().lineSpacing()
        lines = max(1, min(COMPOSER_MAX_LINES, int(self.document().size().height())))
        margins = int(self.document().documentMargin() * 2) + 6
        self.setFixedHeight(lines * line_height + margins)


class ModelOption(QFrame):
    """One entry in the model menu: name, description and a check mark."""

    clicked = Signal()

    def __init__(self, model: AvenModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ModelOption")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        name = QLabel(model.display_name)
        name.setObjectName("ModelOptionName")
        self.available = model.available
        self.base_description = model.description
        if not model.available:
            self.base_description += " · " + ("In development" if model.status == "in_development" else "Unavailable")
            self.setEnabled(False)
        self.description = QLabel(model.description)
        self.description.setObjectName("ModelOptionDescription")
        texts.addWidget(name)
        texts.addWidget(self.description)
        layout.addLayout(texts, 1)
        self.check = QLabel("✓")
        self.check.setObjectName("ModelOptionCheck")
        layout.addWidget(self.check)

    def set_note(self, note: str) -> None:
        self.description.setText(f"{self.base_description} {note}".strip())

    def set_selected(self, selected: bool) -> None:
        self.check.setText("✓" if selected else "")
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.LeftButton and self.available:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ModelPicker(QToolButton):
    """Button in the message box that opens the AVEN model menu."""

    model_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ModelPicker")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Choose the AVEN model for your next message")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_ = QMenu(self)
        self.menu_.setObjectName("ModelMenu")
        self.options: dict[str, ModelOption] = {}
        self.actions_: dict[str, QWidgetAction] = {}
        for model in AVEN_MODELS:
            option = ModelOption(model)
            option.clicked.connect(lambda m=model.id: self._choose(m))
            action = QWidgetAction(self.menu_)
            action.setDefaultWidget(option)
            self.menu_.addAction(action)
            self.options[model.id] = option
            self.actions_[model.id] = action
        self.setMenu(self.menu_)
        self.current = ""
        self.allowed: tuple[str, ...] = tuple(self.options)
        self.set_current(DEFAULT_AVEN_MODEL)

    def set_allowed(self, model_ids: tuple[str, ...]) -> None:
        """Show only the models offered in the current category."""
        self.allowed = model_ids or tuple(self.options)
        for model_id, action in self.actions_.items():
            action.setVisible(model_id in self.allowed)

    def set_current(self, model_id: str) -> None:
        if get_aven_model(model_id) is None:
            model_id = DEFAULT_AVEN_MODEL
        self.current = model_id
        self.setText(f"{aven_model_name(model_id)}  ▾")
        for mid, option in self.options.items():
            option.set_selected(mid == model_id)

    def set_notes(self, notes: dict[str, str]) -> None:
        """Extra text per model, e.g. its download size for AVEN Local."""
        for model_id, option in self.options.items():
            option.set_note(notes.get(model_id, ""))

    def _choose(self, model_id: str) -> None:
        self.menu_.close()
        changed = model_id != self.current
        self.set_current(model_id)
        if changed:
            self.model_selected.emit(model_id)


class AttachmentChip(QFrame):
    removed = Signal(str)

    def __init__(self, path: str, size: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AttachmentChip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 2, 2)
        layout.setSpacing(4)
        label = QLabel(f"📄 {path}  ·  {max(1, size // 1000)} KB")
        label.setObjectName("AttachmentLabel")
        remove = QToolButton()
        remove.setObjectName("AttachmentRemove")
        remove.setText("✕")
        remove.setToolTip(f"Remove {path}")
        remove.clicked.connect(lambda: self.removed.emit(path))
        layout.addWidget(label)
        layout.addWidget(remove)


class ChatView(QWidget):
    send_requested = Signal(str)
    stop_requested = Signal()
    mode_changed = Signal(str)
    subscribe_requested = Signal()
    refresh_access_requested = Signal()
    model_changed = Signal(str)
    settings_requested = Signal()
    download_requested = Signal()
    retry_requested = Signal()
    regenerate_requested = Signal()
    load_earlier_requested = Signal()

    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette_ = palette
        self.mode = "aven"
        self.busy = False
        self._stick_to_bottom = True
        self._status: ConfigStatus | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_welcome())
        self.stack.addWidget(self._build_messages())
        root.addWidget(self.stack, 1)
        root.addWidget(self._build_composer())

    # --- construction ------------------------------------------------------------
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("ChatHeader")
        header.setFixedHeight(60)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 16, 0)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addStretch(1)
        self.title_label = QLabel("New conversation")
        self.title_label.setObjectName("ConversationTitle")
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.model_label = QLabel("")
        self.model_label.setObjectName("ModelLabel")
        self.model_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        titles.addWidget(self.title_label)
        titles.addWidget(self.model_label)
        titles.addStretch(1)
        layout.addLayout(titles, 1)

        self.access_badge = QLabel("Free")
        self.access_badge.setObjectName("AccessBadge")
        layout.addWidget(self.access_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    def _build_welcome(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(2)

        column = QWidget()
        column.setMaximumWidth(720)
        layout = QVBoxLayout(column)
        layout.setSpacing(12)

        self.welcome_logo = QLabel()
        self.welcome_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_logo.setPixmap(logo_pixmap(64, self.devicePixelRatioF() or 1.0))
        layout.addWidget(self.welcome_logo)

        self.welcome_title = QLabel()
        self.welcome_title.setObjectName("WelcomeTitle")
        self.welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.welcome_title)
        self.welcome_subtitle = QLabel()
        self.welcome_subtitle.setObjectName("WelcomeSubtitle")
        self.welcome_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_subtitle.setWordWrap(True)
        layout.addWidget(self.welcome_subtitle)

        self.setup_card = QFrame()
        self.setup_card.setObjectName("SetupCard")
        setup_layout = QHBoxLayout(self.setup_card)
        setup_layout.setContentsMargins(16, 12, 12, 12)
        self.setup_label = QLabel()
        self.setup_label.setWordWrap(True)
        self.setup_button = QPushButton("Open Settings")
        self.setup_button.setObjectName("PrimaryButton")
        self.setup_button.clicked.connect(self._on_setup_clicked)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Check your subscription again")
        self.refresh_button.clicked.connect(self.refresh_access_requested.emit)
        self.refresh_button.hide()
        setup_layout.addWidget(self.setup_label, 1)
        setup_layout.addWidget(self.refresh_button)
        setup_layout.addWidget(self.setup_button)
        layout.addSpacing(6)
        layout.addWidget(self.setup_card)

        self.suggestion_grid = QGridLayout()
        self.suggestion_grid.setSpacing(10)
        self.suggestion_buttons: list[QPushButton] = []
        for index in range(4):
            button = QPushButton()
            button.setObjectName("SuggestionCard")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            button.setMinimumHeight(56)
            button.clicked.connect(lambda _=False, b=button: self._on_suggestion(b))
            self.suggestion_grid.addWidget(button, index // 2, index % 2)
            self.suggestion_buttons.append(button)
        layout.addSpacing(10)
        layout.addLayout(self.suggestion_grid)

        privacy = QLabel(
            "With AVEN Local, everything runs on this computer and nothing is sent anywhere. With AVEN Cloud "
            "or your own key, messages are processed by that service. Conversations are saved only here."
        )
        privacy.setObjectName("HelpText")
        privacy.setWordWrap(True)
        privacy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(8)
        layout.addWidget(privacy)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(column, 100)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(3)
        return page

    def _build_messages(self) -> QWidget:
        self.scroll = QScrollArea()
        self.scroll.setObjectName("ChatScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        holder = QWidget()
        holder.setObjectName("MessageList")
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(24, 16, 24, 16)
        self.column = QWidget()
        self.column.setMaximumWidth(CONTENT_MAX_WIDTH)
        self.messages_layout = QVBoxLayout(self.column)
        self.messages_layout.setContentsMargins(0, 0, 0, 0)
        self.messages_layout.setSpacing(6)

        self.load_earlier_button = QPushButton("Show earlier messages")
        self.load_earlier_button.clicked.connect(self.load_earlier_requested.emit)
        self.load_earlier_button.hide()
        self.messages_layout.addWidget(self.load_earlier_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.messages_layout.addStretch(1)

        holder_layout.addStretch(1)
        holder_layout.addWidget(self.column, 100)
        holder_layout.addStretch(1)
        self.scroll.setWidget(holder)

        bar = self.scroll.verticalScrollBar()
        bar.rangeChanged.connect(self._on_range_changed)
        bar.valueChanged.connect(self._on_scrolled)
        return self.scroll

    def _build_composer(self) -> QWidget:
        wrapper = QWidget()
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(24, 8, 24, 14)
        outer.setSpacing(6)

        row = QHBoxLayout()
        row.addStretch(1)
        self.composer_frame = QFrame()
        self.composer_frame.setObjectName("ComposerFrame")
        self.composer_frame.setMaximumWidth(CONTENT_MAX_WIDTH)
        frame_layout = QVBoxLayout(self.composer_frame)
        frame_layout.setContentsMargins(12, 8, 8, 8)
        frame_layout.setSpacing(4)
        self.attachments: list[AttachedFile] = []
        self.attachment_row = QHBoxLayout()
        self.attachment_row.setSpacing(6)
        self.attachment_holder = QWidget()
        self.attachment_holder.setLayout(self.attachment_row)
        self.attachment_holder.hide()
        frame_layout.addWidget(self.attachment_holder)
        self.input = ComposerInput()
        self.input.submit.connect(self._on_submit)
        self.input.textChanged.connect(self._update_send_state)
        self.input.focus_changed.connect(self._on_focus_changed)
        frame_layout.addWidget(self.input)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.model_picker = ModelPicker()
        self.model_picker.model_selected.connect(self._on_model_selected)
        controls.addWidget(self.model_picker)
        self.attach_button = QToolButton()
        self.attach_button.setObjectName("AttachButton")
        self.attach_button.setText("📎 Add files")
        self.attach_button.setToolTip("Attach project files so AVEN can read them")
        self.attach_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        attach_menu = QMenu(self.attach_button)
        attach_menu.addAction("Files…", self._pick_files)
        attach_menu.addAction("Project folder…", self._pick_folder)
        self.attach_button.setMenu(attach_menu)
        controls.addWidget(self.attach_button)
        controls.addStretch(1)
        frame_layout.addLayout(controls)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("SendButton")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setMinimumSize(QSize(76, 36))
        self.send_button.clicked.connect(self._on_send_clicked)
        controls.addWidget(self.send_button)
        row.addWidget(self.composer_frame, 100)
        row.addStretch(1)
        outer.addLayout(row)

        self.hint_label = QLabel()
        self.hint_label.setObjectName("ComposerHint")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.hint_label)
        self._update_hint()
        self._update_send_state()
        return wrapper

    # --- mode / header -------------------------------------------------------------
    def set_mode(self, mode: str) -> None:
        """Show a chat category (AVEN AI, AVEN Python, AVEN Unity or AVEN CODE)."""
        self.mode = mode
        info = MODES[mode]
        self.input.setPlaceholderText(info.placeholder)
        self.welcome_title.setText(WELCOME_TITLES.get(mode, "How can I help you today?"))
        self.welcome_subtitle.setText(info.description or info.tagline)
        for button, text in zip(self.suggestion_buttons, info.suggestions, strict=False):
            button.setText(text)
            button.setToolTip(text)
        text, kind = access_badge(info)
        self.access_badge.setText(text)
        self.access_badge.setProperty("kind", kind)
        self.access_badge.style().unpolish(self.access_badge)
        self.access_badge.style().polish(self.access_badge)
        self.access_badge.setToolTip(info.pricing_note or ("AVEN CODE needs a subscription." if info.paid else "Free"))
        self.model_picker.set_allowed(info.models)
        # Attaching files is for the coding categories.
        self.attach_button.setVisible(bool(info.validators))
        if not info.validators:
            self.clear_attachments()

    # --- attachments -------------------------------------------------------------
    def _pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach files")
        files, problems = [], []
        for path in paths:
            try:
                files.append(read_attachment(Path(path)))
            except (OSError, ValueError) as exc:
                problems.append(str(exc))
        self.add_attachments(files, problems)

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Attach a project folder")
        if folder:
            files, problems = collect_folder(Path(folder))
            if not files:
                problems.insert(0, "No text files were found in that folder.")
            self.add_attachments(files, problems)

    def add_attachments(self, files: list[AttachedFile], problems: list[str] | None = None) -> None:
        known = {f.path for f in self.attachments}
        self.attachments += [f for f in files if f.path not in known]
        self._render_attachments()
        if problems:
            QMessageBox.information(self, "Some files were not attached", "\n".join(problems[:12]))

    def remove_attachment(self, path: str) -> None:
        self.attachments = [f for f in self.attachments if f.path != path]
        self._render_attachments()

    def clear_attachments(self) -> None:
        self.attachments = []
        self._render_attachments()

    def _render_attachments(self) -> None:
        while self.attachment_row.count():
            item = self.attachment_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        shown = self.attachments[:6]
        for f in shown:
            chip = AttachmentChip(f.path, f.size)
            chip.removed.connect(self.remove_attachment)
            self.attachment_row.addWidget(chip)
        if len(self.attachments) > len(shown):
            more = QLabel(f"+{len(self.attachments) - len(shown)} more")
            more.setObjectName("HelpText")
            self.attachment_row.addWidget(more)
        clear = QToolButton()
        clear.setObjectName("AttachmentRemove")
        clear.setText("Clear all")
        clear.clicked.connect(self.clear_attachments)
        if self.attachments:
            self.attachment_row.addWidget(clear)
        self.attachment_row.addStretch(1)
        self.attachment_holder.setVisible(bool(self.attachments))
        self._update_send_state()

    def set_model(self, model_id: str) -> None:
        self.model_picker.set_current(model_id)

    def _on_model_selected(self, model_id: str) -> None:
        self.model_changed.emit(model_id)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
        self.title_label.setToolTip(title)

    def set_status(self, status: ConfigStatus) -> None:
        self._status = status
        self.refresh_button.setVisible(status.needs_subscription and "Subscribe" in status.problem)
        if status.ready:
            self.model_label.setText(f"{MODES[self.mode].name} · {status.model_name}")
            self.setup_card.hide()
        elif status.needs_subscription:
            self.model_label.setText(f"{MODES[self.mode].name} · subscription needed")
            self.setup_label.setText(status.problem)
            self.setup_button.setText("Subscribe" if "Subscribe" in status.problem else "Learn more")
            self.setup_card.show()
        elif status.needs_download:
            self.model_label.setText(f"{MODES[self.mode].name} · {status.model_name} · download needed")
            self.setup_label.setText(status.problem)
            self.setup_button.setText("Download")
            self.setup_card.show()
        else:
            self.model_label.setText(f"{MODES[self.mode].name} · not configured")
            self.setup_label.setText(status.problem)
            self.setup_button.setText("Open Settings")
            self.setup_card.show()

    def _on_setup_clicked(self) -> None:
        if self._status is not None and self._status.needs_subscription:
            self.subscribe_requested.emit()
        elif self._status is not None and self._status.needs_download:
            self.download_requested.emit()
        else:
            self.settings_requested.emit()

    def set_send_with_enter(self, value: bool) -> None:
        self.input.send_with_enter = value
        self._update_hint()

    def _update_hint(self) -> None:
        if self.input.send_with_enter:
            keys = "Enter to send · Shift+Enter for a new line"
        else:
            keys = "Ctrl+Enter to send · Enter for a new line"
        self.hint_label.setText(f"{keys} · AI can make mistakes - verify important information.")

    # --- messages ----------------------------------------------------------------------
    def show_welcome(self) -> None:
        self.stack.setCurrentIndex(0)

    def show_messages(self) -> None:
        self.stack.setCurrentIndex(1)

    def clear_messages(self) -> None:
        for widget in self.message_widgets():
            self.messages_layout.removeWidget(widget)
            widget.deleteLater()
        self.load_earlier_button.hide()
        self._stick_to_bottom = True

    def message_widgets(self) -> list[QWidget]:
        widgets = []
        for i in range(self.messages_layout.count()):
            widget = self.messages_layout.itemAt(i).widget()
            if widget is not None and widget is not self.load_earlier_button:
                widgets.append(widget)
        return widgets

    def _insert_widget(self, widget: QWidget, at_top: bool = False) -> None:
        if at_top:
            self.messages_layout.insertWidget(1, widget)
        else:
            # Insert before the trailing stretch.
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, widget)
        self.show_messages()

    def add_user_message(self, content: str, message_id: int | None = None, at_top: bool = False) -> UserMessageWidget:
        widget = UserMessageWidget(content, self.palette_)
        widget.message_id = message_id
        self._insert_widget(widget, at_top)
        return widget

    def add_assistant_message(
        self,
        name: str,
        content: str = "",
        model: str | None = None,
        message_id: int | None = None,
        at_top: bool = False,
    ) -> AssistantMessageWidget:
        widget = AssistantMessageWidget(name, self.palette_)
        widget.message_id = message_id
        widget.set_model(aven_model_name(model))
        widget.regenerate_requested.connect(self.regenerate_requested.emit)
        if content:
            widget.set_content(content)
        self._insert_widget(widget, at_top)
        return widget

    def show_error(self, error: AIError) -> ErrorWidget:
        self.remove_errors()
        widget = ErrorWidget(error)
        widget.retry_requested.connect(self.retry_requested.emit)
        widget.settings_requested.connect(self.settings_requested.emit)
        self._insert_widget(widget)
        self.scroll_to_bottom()
        return widget

    def remove_errors(self) -> None:
        for widget in self.message_widgets():
            if isinstance(widget, ErrorWidget):
                self.messages_layout.removeWidget(widget)
                widget.deleteLater()

    def remove_widget(self, widget: QWidget) -> None:
        self.messages_layout.removeWidget(widget)
        widget.deleteLater()

    def set_has_earlier(self, value: bool) -> None:
        self.load_earlier_button.setVisible(value)

    def refresh_regenerate_buttons(self) -> None:
        """Only the final assistant message offers Regenerate."""
        assistants = [w for w in self.message_widgets() if isinstance(w, AssistantMessageWidget)]
        last = self.message_widgets()[-1] if self.message_widgets() else None
        for widget in assistants:
            widget.set_can_regenerate(widget is last and not self.busy)

    # --- scrolling -----------------------------------------------------------------------
    def scroll_to_bottom(self) -> None:
        self._stick_to_bottom = True
        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def _on_range_changed(self, _minimum: int, maximum: int) -> None:
        if self._stick_to_bottom:
            self.scroll.verticalScrollBar().setValue(maximum)

    def _on_scrolled(self, value: int) -> None:
        bar = self.scroll.verticalScrollBar()
        self._stick_to_bottom = value >= bar.maximum() - 48

    # --- composer ------------------------------------------------------------------------
    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.send_button.setText("Stop" if busy else "Send")
        self.send_button.setToolTip("Stop generating (Esc)" if busy else "Send message")
        self.send_button.setProperty("stop", "true" if busy else "false")
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)
        self._update_send_state()
        self.refresh_regenerate_buttons()

    def _update_send_state(self) -> None:
        text = self.input.toPlainText()
        self.send_button.setEnabled(self.busy or bool(text.strip()))
        if len(text) > MAX_INPUT_CHARS:
            self.hint_label.setText(f"Message is too long ({len(text):,} / {MAX_INPUT_CHARS:,} characters).")
        elif not self.hint_label.text() or self.hint_label.text().startswith("Message is too long"):
            self._update_hint()

    def _on_focus_changed(self, focused: bool) -> None:
        self.composer_frame.setProperty("focused", "true" if focused else "false")
        self.composer_frame.style().unpolish(self.composer_frame)
        self.composer_frame.style().polish(self.composer_frame)

    def _on_send_clicked(self) -> None:
        if self.busy:
            self.stop_requested.emit()
        else:
            self._on_submit()

    def _on_submit(self) -> None:
        if self.busy:
            return  # prevent duplicate submissions while a response is generating
        text = self.input.toPlainText().strip()
        if not text or len(text) > MAX_INPUT_CHARS:
            return
        self.send_requested.emit(text)

    def _on_suggestion(self, button: QPushButton) -> None:
        if not self.busy:
            self.input.setPlainText(button.text())
            self._on_submit()

    def clear_input(self) -> None:
        self.input.clear()

    def focus_input(self) -> None:
        self.input.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt API)
        if event.key() == Qt.Key.Key_Escape and self.busy:
            self.stop_requested.emit()
            return
        super().keyPressEvent(event)

    def apply_palette(self, palette: Palette) -> None:
        self.palette_ = palette
        for widget in self.message_widgets():
            widget.apply_palette(palette)
