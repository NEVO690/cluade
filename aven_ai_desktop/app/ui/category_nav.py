"""The five AVEN AI categories, shown at the top of the sidebar."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.config.catalog import CategorySpec, catalog


def access_badge(category: CategorySpec) -> tuple[str, str]:
    """(badge text, badge kind) for a category: Free, Paid or Preview."""
    if category.paid:
        return "Paid", "paid"
    if category.pricing_note:
        return "Preview", "preview"
    return "Free", "free"


class CategoryButton(QFrame):
    clicked = Signal(str)

    def __init__(self, category: CategorySpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.category_id = category.id
        self.setObjectName("CategoryButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(category.tagline)
        self.setAccessibleName(f"{category.name} category")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)
        icon = QLabel(category.icon)
        icon.setObjectName("CategoryIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(30, 30)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        name = QLabel(category.name)
        name.setObjectName("CategoryName")
        texts.addWidget(name)
        layout.addWidget(icon)
        layout.addLayout(texts, 1)
        text, kind = access_badge(category)
        self.badge = QLabel(text)
        self.badge.setObjectName("AccessBadge")
        self.badge.setProperty("kind", kind)
        layout.addWidget(self.badge)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.category_id)
        super().mouseReleaseEvent(event)


class CategoryNav(QWidget):
    category_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.buttons: dict[str, CategoryButton] = {}
        for category in catalog().categories.values():
            button = CategoryButton(category)
            button.clicked.connect(self._on_clicked)
            layout.addWidget(button)
            self.buttons[category.id] = button
        self.current = ""

    def set_current(self, category_id: str) -> None:
        self.current = category_id
        for cid, button in self.buttons.items():
            button.set_selected(cid == category_id)

    def _on_clicked(self, category_id: str) -> None:
        if category_id != self.current:
            self.set_current(category_id)
            self.category_selected.emit(category_id)
