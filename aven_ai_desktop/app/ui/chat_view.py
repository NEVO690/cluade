"""Main chat panel: header, message list, welcome screen and composer."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ai.chat_service import ConfigStatus
from app.ai.errors import AIError
from app.ai.prompts import MODES
from app.ui.logo import logo_pixmap
from app.ui.message_widget import AssistantMessageWidget, ErrorWidget, UserMessageWidget
from app.ui.theme_manager import Palette

CONTENT_MAX_WIDTH = 860
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


class ChatView(QWidget):
    send_requested = Signal(str)
    stop_requested = Signal()
    mode_changed = Signal(str)
    settings_requested = Signal()
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

        switch = QFrame()
        switch.setObjectName("ModeSwitch")
        switch_layout = QHBoxLayout(switch)
        switch_layout.setContentsMargins(3, 3, 3, 3)
        switch_layout.setSpacing(2)
        self.mode_group = QButtonGroup(self)
        self.mode_buttons: dict[str, QPushButton] = {}
        for mode_id in ("aven", "code"):
            button = QPushButton(MODES[mode_id].name)
            button.setObjectName("ModeButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(MODES[mode_id].tagline)
            button.clicked.connect(lambda _=False, m=mode_id: self._on_mode_clicked(m))
            self.mode_group.addButton(button)
            self.mode_buttons[mode_id] = button
            switch_layout.addWidget(button)
        self.mode_buttons["aven"].setChecked(True)
        switch.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)
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
        setup_button = QPushButton("Open Settings")
        setup_button.setObjectName("PrimaryButton")
        setup_button.clicked.connect(self.settings_requested.emit)
        setup_layout.addWidget(self.setup_label, 1)
        setup_layout.addWidget(setup_button)
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
            "Messages are sent to the AI provider you configure and processed under its privacy policy. "
            "Conversations are saved only on this computer."
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
        frame_layout = QHBoxLayout(self.composer_frame)
        frame_layout.setContentsMargins(12, 8, 8, 8)
        frame_layout.setSpacing(8)
        self.input = ComposerInput()
        self.input.submit.connect(self._on_submit)
        self.input.textChanged.connect(self._update_send_state)
        self.input.focus_changed.connect(self._on_focus_changed)
        frame_layout.addWidget(self.input, 1)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("SendButton")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setMinimumSize(QSize(76, 36))
        self.send_button.clicked.connect(self._on_send_clicked)
        frame_layout.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignBottom)
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
        self.mode = mode
        self.mode_buttons[mode].setChecked(True)
        info = MODES[mode]
        self.input.setPlaceholderText(info.placeholder)
        self.welcome_title.setText("What are we building today?" if mode == "code" else "How can I help you today?")
        self.welcome_subtitle.setText(info.tagline)
        for button, text in zip(self.suggestion_buttons, info.suggestions, strict=True):
            button.setText(text)
            button.setToolTip(text)

    def _on_mode_clicked(self, mode: str) -> None:
        if mode != self.mode:
            self.set_mode(mode)
            self.mode_changed.emit(mode)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
        self.title_label.setToolTip(title)

    def set_status(self, status: ConfigStatus, served_model: str | None = None) -> None:
        self._status = status
        if status.ready:
            model = served_model or status.model
            self.model_label.setText(f"{MODES[self.mode].name} · {model} · {status.provider_name}")
            self.setup_card.hide()
        else:
            self.model_label.setText(f"{MODES[self.mode].name} · not configured")
            self.setup_label.setText(status.problem)
            self.setup_card.show()

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
        widget.set_model(model)
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
