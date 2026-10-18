"""Widgets that display a single chat message."""

from __future__ import annotations

import html
import math

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication, QTextOption, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.ai.errors import AIError
from app.rendering.markdown_renderer import (
    ALLOWED_LINK_SCHEMES,
    Segment,
    display_language,
    highlight_code_html,
    markdown_to_html,
    split_segments,
)
from app.ui.logo import logo_pixmap
from app.ui.theme_manager import CODE_FONT_FAMILIES, Palette, message_css

USER_BUBBLE_MAX_RATIO = 0.78


def open_link_safely(url: QUrl, parent: QWidget | None) -> None:
    """Open a link from AI output in the browser, after showing where it goes."""
    if url.scheme().lower() not in ALLOWED_LINK_SCHEMES:
        return
    target = url.toString()
    answer = QMessageBox.question(
        parent,
        "Open link?",
        f"This link was written by the AI and will open in your browser:\n\n{target}",
        QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel,
    )
    if answer == QMessageBox.StandardButton.Open:
        QDesktopServices.openUrl(url)


class AutoHeightTextBrowser(QTextBrowser):
    """Read-only rich text view that grows to fit its content (no inner vertical scroll)."""

    def __init__(self, wrap: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.wrap = wrap
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(lambda url: open_link_safely(url, self))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff if wrap else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth if wrap else QTextBrowser.LineWrapMode.NoWrap)
        if wrap:
            self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.viewport().setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")
        self.document().documentLayout().documentSizeChanged.connect(lambda _size: self.update_height())

    def update_height(self) -> None:
        doc = self.document()
        if self.wrap:
            doc.setTextWidth(self.viewport().width())
        height = doc.size().height()
        if not self.wrap and doc.idealWidth() > self.viewport().width():
            height += self.horizontalScrollBar().sizeHint().height()
        height = math.ceil(height) + 2
        if height != self.height():
            self.setFixedHeight(height)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        self.update_height()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (Qt API)
        # Let vertical scrolling reach the chat scroll area.
        if not self.wrap and event.angleDelta().x() != 0:
            super().wheelEvent(event)
        else:
            event.ignore()


class MarkdownView(AutoHeightTextBrowser):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(wrap=True, parent=parent)
        self.document().setDocumentMargin(0)
        self._source = None
        self._palette: Palette | None = None

    def set_markdown(self, text: str, palette: Palette) -> None:
        if text == self._source and palette is self._palette:
            return
        self._source = text
        self._palette = palette
        self.document().setDefaultStyleSheet(message_css(palette))
        self.setHtml(markdown_to_html(text))
        self.update_height()


class CodeBlockWidget(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CodeBlock")
        self._code = ""
        self._language = ""
        self._palette: Palette | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("CodeHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 4, 6, 4)
        self.language_label = QLabel("code")
        self.language_label.setObjectName("CodeLanguage")
        self.copy_button = QPushButton("Copy code")
        self.copy_button.setObjectName("CodeCopy")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.clicked.connect(self.copy_code)
        header_layout.addWidget(self.language_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.copy_button)
        layout.addWidget(header)

        self.view = AutoHeightTextBrowser(wrap=False)
        self.view.document().setDocumentMargin(12)
        font = QFont()
        font.setFamilies(["Cascadia Code", "Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono"])
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSizeF(10)
        self.view.setFont(font)
        layout.addWidget(self.view)

    def set_code(self, code: str, language: str, palette: Palette) -> None:
        if code == self._code and language == self._language and palette is self._palette:
            return
        self._code, self._language, self._palette = code, language, palette
        self.language_label.setText(display_language(language))
        body = highlight_code_html(code, language, palette.dark)
        self.view.setHtml(
            f'<pre style="font-family: {html.escape(CODE_FONT_FAMILIES, quote=True)}; '
            f'color: {palette.text}; margin: 0;">{body}</pre>'
        )
        self.view.update_height()

    def copy_code(self) -> None:
        QGuiApplication.clipboard().setText(self._code)
        self.copy_button.setText("Copied ✓")
        QTimer.singleShot(1500, lambda: self.copy_button.setText("Copy code"))


class TypingIndicator(QLabel):
    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TypingLabel")
        self._name = name
        self._dots = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(400)
        self._tick()

    def _tick(self) -> None:
        self._dots = (self._dots % 3) + 1
        self.setText(f"{self._name} is thinking" + "." * self._dots)

    def stop(self) -> None:
        self._timer.stop()


def _action_button(text: str, tooltip: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("MessageAction")
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class UserMessageWidget(QWidget):
    def __init__(self, content: str, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.role = "user"
        self.content = content
        self.message_id: int | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(2)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        self.bubble = QFrame()
        self.bubble.setObjectName("UserBubble")
        bubble_layout = QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(14, 10, 14, 10)
        self.view = AutoHeightTextBrowser(wrap=True)
        self.view.document().setDocumentMargin(0)
        self.view.setPlainText(content)
        bubble_layout.addWidget(self.view)
        row.addWidget(self.bubble)
        outer.addLayout(row)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.copy_button = _action_button("Copy", "Copy message")
        self.copy_button.clicked.connect(self._copy)
        actions.addWidget(self.copy_button)
        outer.addLayout(actions)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.content)
        self.copy_button.setText("Copied ✓")
        QTimer.singleShot(1500, lambda: self.copy_button.setText("Copy"))

    def apply_palette(self, palette: Palette) -> None:
        pass  # styled entirely by the application stylesheet

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        self._fit_bubble()

    def _fit_bubble(self) -> None:
        max_width = int(self.width() * USER_BUBBLE_MAX_RATIO)
        doc = self.view.document()
        doc.setTextWidth(-1)
        ideal = math.ceil(doc.idealWidth()) + 6
        margins = self.bubble.layout().contentsMargins()
        inner = max(40, min(ideal, max_width - margins.left() - margins.right()))
        self.view.setFixedWidth(inner)
        self.view.update_height()


class AssistantMessageWidget(QWidget):
    copy_requested = Signal()
    regenerate_requested = Signal()

    def __init__(self, assistant_name: str, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.role = "assistant"
        self.content = ""
        self.message_id: int | None = None
        self.palette_ = palette
        self.assistant_name = assistant_name
        self._segment_widgets: list[tuple[str, QWidget]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 8)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        avatar = QLabel()
        avatar.setPixmap(logo_pixmap(22, self.devicePixelRatioF() or 1.0))
        avatar.setFixedSize(22, 22)
        self.name_label = QLabel(assistant_name)
        self.name_label.setObjectName("AssistantName")
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("MessageMeta")
        header.addWidget(avatar)
        header.addWidget(self.name_label)
        header.addWidget(self.meta_label)
        header.addStretch(1)
        outer.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(30, 0, 0, 0)
        self.body.setSpacing(10)
        outer.addLayout(self.body)

        self.typing = TypingIndicator(assistant_name)
        self.body.addWidget(self.typing)

        self.status_note = QLabel("")
        self.status_note.setObjectName("StatusNote")
        self.status_note.setContentsMargins(30, 0, 0, 0)
        self.status_note.hide()
        outer.addWidget(self.status_note)

        actions = QHBoxLayout()
        actions.setContentsMargins(24, 0, 0, 0)
        self.copy_button = _action_button("Copy", "Copy the whole response as Markdown")
        self.copy_button.clicked.connect(self._copy)
        self.regenerate_button = _action_button("Regenerate", "Ask for a new response")
        self.regenerate_button.clicked.connect(self.regenerate_requested.emit)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.regenerate_button)
        actions.addStretch(1)
        self.actions_widget = QWidget()
        self.actions_widget.setLayout(actions)
        self.actions_widget.hide()
        outer.addWidget(self.actions_widget)

    # --- content ----------------------------------------------------------------
    def set_model(self, model: str | None) -> None:
        self.meta_label.setText(model or "")

    def set_content(self, text: str) -> None:
        self.content = text
        if text and self.typing is not None:
            self.typing.stop()
            self.typing.deleteLater()
            self.typing = None
        self._render(split_segments(text))

    def _render(self, segments: list[Segment]) -> None:
        palette = self.palette_
        for index, segment in enumerate(segments):
            existing = self._segment_widgets[index] if index < len(self._segment_widgets) else None
            if existing is None or existing[0] != segment.kind:
                self._truncate_segments(index)
                widget: QWidget = MarkdownView() if segment.kind == "markdown" else CodeBlockWidget()
                self.body.addWidget(widget)
                self._segment_widgets.append((segment.kind, widget))
            widget = self._segment_widgets[index][1]
            if isinstance(widget, MarkdownView):
                widget.set_markdown(segment.text, palette)
            elif isinstance(widget, CodeBlockWidget):
                widget.set_code(segment.text, segment.language, palette)
        self._truncate_segments(len(segments))

    def _truncate_segments(self, keep: int) -> None:
        while len(self._segment_widgets) > keep:
            _kind, widget = self._segment_widgets.pop()
            self.body.removeWidget(widget)
            widget.deleteLater()

    def finish(self, status: str = "complete", can_regenerate: bool = True) -> None:
        if self.typing is not None:
            self.typing.stop()
            self.typing.deleteLater()
            self.typing = None
        notes = {
            "stopped": "Generation stopped.",
            "truncated": "The response reached the maximum length set in Settings and was cut off.",
        }
        if status in notes:
            self.status_note.setText(notes[status])
            self.status_note.show()
        self.regenerate_button.setVisible(can_regenerate)
        self.actions_widget.setVisible(bool(self.content))

    def set_can_regenerate(self, value: bool) -> None:
        self.regenerate_button.setVisible(value)

    def apply_palette(self, palette: Palette) -> None:
        self.palette_ = palette
        self._render(split_segments(self.content))

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.content)
        self.copy_button.setText("Copied ✓")
        QTimer.singleShot(1500, lambda: self.copy_button.setText("Copy"))


class ErrorWidget(QFrame):
    retry_requested = Signal()
    settings_requested = Signal()

    def __init__(self, error: AIError, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ErrorCard")
        self.role = "error"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        title = QLabel(error.title)
        title.setObjectName("ErrorTitle")
        message = QLabel(error.user_message)
        message.setWordWrap(True)
        message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title)
        layout.addWidget(message)

        buttons = QHBoxLayout()
        self.retry_button = QPushButton("Retry")
        self.retry_button.setObjectName("PrimaryButton")
        self.retry_button.clicked.connect(self.retry_requested.emit)
        buttons.addWidget(self.retry_button)
        if error.opens_settings:
            settings_button = QPushButton("Open Settings")
            settings_button.clicked.connect(self.settings_requested.emit)
            buttons.addWidget(settings_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def apply_palette(self, palette: Palette) -> None:
        pass
