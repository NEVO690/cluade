"""Sidebar with branding, new-conversation button, search and conversation history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.storage.conversation_repository import Conversation
from app.ui.logo import logo_pixmap
from app.ui.theme_manager import Palette
from app.version import __version__

ID_ROLE = Qt.ItemDataRole.UserRole


def _mode_icon(mode: str, palette: Palette) -> QIcon:
    """Small glyph distinguishing AVEN (◆) and AVEN CODE (</>) conversations."""
    size = 18
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(palette.accent if mode == "code" else palette.text_muted)
    painter.setPen(color)
    font = QFont()
    font.setPixelSize(10 if mode == "code" else 12)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "</>" if mode == "code" else "◆")
    painter.end()
    return QIcon(pixmap)


def _group_label(updated_at: str, now: datetime) -> str:
    try:
        stamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return "Older"
    local = stamp.astimezone()
    today = now.astimezone().date()
    if local.date() == today:
        return "Today"
    if local.date() == today - timedelta(days=1):
        return "Yesterday"
    if local.date() > today - timedelta(days=7):
        return "Previous 7 days"
    if local.date() > today - timedelta(days=30):
        return "Previous 30 days"
    return "Older"


class Sidebar(QFrame):
    new_conversation_requested = Signal()
    conversation_selected = Signal(int)
    rename_requested = Signal(int)
    delete_requested = Signal(int)
    settings_requested = Signal()
    theme_toggle_requested = Signal()

    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(240)
        self.setMaximumWidth(340)
        self.palette_ = palette
        self._conversations: list[Conversation] = []
        self._current_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 12)
        layout.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        self.logo = QLabel()
        self.logo.setPixmap(logo_pixmap(34, self.devicePixelRatioF() or 1.0))
        self.logo.setFixedSize(34, 34)
        names = QVBoxLayout()
        names.setSpacing(0)
        name = QLabel("AVEN AI")
        name.setObjectName("BrandName")
        edition = QLabel(f"Desktop · v{__version__}")
        edition.setObjectName("BrandEdition")
        names.addWidget(name)
        names.addWidget(edition)
        brand.addWidget(self.logo)
        brand.addLayout(names)
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addSpacing(4)

        self.new_button = QPushButton("＋  New conversation")
        self.new_button.setObjectName("NewChatButton")
        self.new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_button.setToolTip("Start a new conversation (Ctrl+N)")
        self.new_button.clicked.connect(self.new_conversation_requested.emit)
        layout.addWidget(self.new_button)

        self.search = QLineEdit()
        self.search.setObjectName("SearchField")
        self.search.setPlaceholderText("Search conversations")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _text: self._rebuild())
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.setObjectName("ConversationList")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_context_menu)
        self.list.itemClicked.connect(self._on_item_clicked)
        self.list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list, 1)

        self.empty_label = QLabel("No conversations yet.")
        self.empty_label.setObjectName("HelpText")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        footer = QVBoxLayout()
        footer.setSpacing(2)
        self.theme_button = QPushButton("◐  Toggle theme")
        self.theme_button.setObjectName("SidebarFooterButton")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.clicked.connect(self.theme_toggle_requested.emit)
        self.settings_button = QPushButton("⚙  Settings")
        self.settings_button.setObjectName("SidebarFooterButton")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip("Settings (Ctrl+,)")
        self.settings_button.clicked.connect(self.settings_requested.emit)
        footer.addWidget(self.theme_button)
        footer.addWidget(self.settings_button)
        layout.addLayout(footer)

    # --- data ------------------------------------------------------------------
    def set_conversations(self, conversations: list[Conversation], current_id: int | None) -> None:
        self._conversations = conversations
        self._current_id = current_id
        self._rebuild()

    def set_current(self, conversation_id: int | None) -> None:
        self._current_id = conversation_id
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(ID_ROLE) == conversation_id and conversation_id is not None:
                self.list.setCurrentItem(item)
                return
        self.list.clearSelection()
        self.list.setCurrentItem(None)

    def _rebuild(self) -> None:
        query = self.search.text().strip().lower()
        self.list.clear()
        now = datetime.now(UTC)
        last_group = None
        shown = 0
        for conversation in self._conversations:
            if query and query not in conversation.title.lower():
                continue
            group = _group_label(conversation.updated_at, now)
            if group != last_group:
                header = QListWidgetItem(group.upper())
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                font = header.font()
                font.setPointSizeF(max(7.5, font.pointSizeF() * 0.78))
                font.setBold(True)
                header.setFont(font)
                header.setForeground(QColor(self.palette_.text_muted))
                self.list.addItem(header)
                last_group = group
            item = QListWidgetItem(_mode_icon(conversation.mode, self.palette_), conversation.title)
            item.setData(ID_ROLE, conversation.id)
            item.setToolTip(f"{conversation.title}\n{'AVEN CODE' if conversation.mode == 'code' else 'AVEN'}")
            self.list.addItem(item)
            shown += 1
        self.empty_label.setVisible(shown == 0)
        self.empty_label.setText("No matching conversations." if query else "No conversations yet.")
        self.set_current(self._current_id)

    # --- interaction -----------------------------------------------------------------
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        conversation_id = item.data(ID_ROLE)
        if conversation_id is not None:
            self.conversation_selected.emit(int(conversation_id))

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        conversation_id = item.data(ID_ROLE)
        if conversation_id is not None:
            self.rename_requested.emit(int(conversation_id))

    def _show_context_menu(self, pos: QPoint) -> None:
        item = self.list.itemAt(pos)
        if item is None or item.data(ID_ROLE) is None:
            return
        conversation_id = int(item.data(ID_ROLE))
        menu = QMenu(self)
        rename = menu.addAction("Rename")
        delete = menu.addAction("Delete")
        chosen = menu.exec(self.list.viewport().mapToGlobal(pos))
        if chosen is rename:
            self.rename_requested.emit(conversation_id)
        elif chosen is delete:
            self.delete_requested.emit(conversation_id)

    def apply_palette(self, palette: Palette) -> None:
        self.palette_ = palette
        self._rebuild()
