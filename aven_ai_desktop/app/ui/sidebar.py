"""Sidebar: branding, the five categories, and the conversations or projects of the current one."""

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

from app.config.catalog import catalog
from app.ui.category_nav import CategoryNav
from app.ui.logo import logo_pixmap
from app.ui.theme_manager import Palette
from app.version import __version__

ID_ROLE = Qt.ItemDataRole.UserRole


def _mode_icon(mode: str, palette: Palette) -> QIcon:
    """Small glyph for the category an entry belongs to (◆, Py, U, </>, ▶)."""
    category = catalog().category(mode)
    glyph = category.icon if category else "◆"
    size = 18
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(palette.text_muted if mode == "aven" else palette.accent)
    painter.setPen(color)
    font = QFont()
    font.setPixelSize(12 if len(glyph) == 1 else 9)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, glyph)
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
    category_selected = Signal(str)
    whats_new_requested = Signal()
    account_requested = Signal()

    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(240)
        self.setMaximumWidth(340)
        self.palette_ = palette
        self._entries: list = []  # Conversation or Project objects (id, title, updated_at, mode)
        self._current_id: int | None = None
        self._noun = "conversations"

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
        layout.addSpacing(2)

        self.categories = CategoryNav()
        self.categories.category_selected.connect(self.category_selected.emit)
        layout.addWidget(self.categories)
        divider = QFrame()
        divider.setObjectName("SidebarDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

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
        self.whats_new_button = QPushButton("✦  What's new")
        self.whats_new_button.setObjectName("SidebarFooterButton")
        self.whats_new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.whats_new_button.clicked.connect(self.whats_new_requested.emit)
        self.account_button = QPushButton("◎  Account && subscription")
        self.account_button.setObjectName("SidebarFooterButton")
        self.account_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.account_button.clicked.connect(self.account_requested.emit)
        footer.addWidget(self.whats_new_button)
        footer.addWidget(self.account_button)
        self.theme_button = QPushButton("◐  Theme")
        self.theme_button.setObjectName("SidebarFooterButton")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.clicked.connect(self.theme_toggle_requested.emit)
        self.settings_button = QPushButton("⚙  Settings")
        self.settings_button.setObjectName("SidebarFooterButton")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip("Settings (Ctrl+,)")
        self.settings_button.clicked.connect(self.settings_requested.emit)
        row = QHBoxLayout()  # theme and settings side by side to leave room for the list
        row.setSpacing(2)
        row.addWidget(self.theme_button)
        row.addWidget(self.settings_button)
        footer.addLayout(row)
        layout.addLayout(footer)

    # --- data ------------------------------------------------------------------
    def set_category(self, category_id: str) -> None:
        self.categories.set_current(category_id)
        studio = category_id == "made"
        self._noun = "projects" if studio else "conversations"
        self.new_button.setText("＋  New game" if studio else "＋  New conversation")
        self.new_button.setToolTip("Start a new game project" if studio else "Start a new conversation (Ctrl+N)")
        self.search.setPlaceholderText(f"Search {self._noun}")

    def set_conversations(self, conversations: list, current_id: int | None) -> None:
        """Entries for the current category (conversations, or game projects in Made With AVEN)."""
        self._entries = conversations
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
        for conversation in self._entries:
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
            mode = getattr(conversation, "mode", "made")
            category = catalog().category(mode)
            item = QListWidgetItem(_mode_icon(mode, self.palette_), conversation.title)
            item.setData(ID_ROLE, conversation.id)
            item.setToolTip(f"{conversation.title}\n{category.name if category else mode}")
            self.list.addItem(item)
            shown += 1
        self.empty_label.setVisible(shown == 0)
        self.empty_label.setText(f"No matching {self._noun}." if query else f"No {self._noun} yet.")
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
