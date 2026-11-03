"""What's New: release notes from the catalog (``app/data/releases.json``)."""

from __future__ import annotations

import html

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextBrowser, QVBoxLayout, QWidget

from app.config.catalog import Release, catalog
from app.version import __version__


def release_html(releases: tuple[Release, ...]) -> str:
    parts = []
    for release in releases:
        items = "".join(
            f"<li><b>{html.escape(item.title)}</b><br>{html.escape(item.body)}</li>" for item in release.items
        )
        parts.append(
            f"<h2>{html.escape(release.title)}</h2>"
            f"<p><small>Version {html.escape(release.version)} · {html.escape(release.date)}</small></p>"
            f"<ul>{items}</ul>"
        )
    return "".join(parts) or "<p>No release notes yet.</p>"


class WhatsNewDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("What's new in AVEN AI")
        self.resize(640, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        title = QLabel(f"What's new · AVEN AI {__version__}")
        title.setObjectName("WelcomeTitle")
        layout.addWidget(title)
        self.view = QTextBrowser()
        self.view.setObjectName("WhatsNewView")
        self.view.setOpenExternalLinks(False)
        self.view.setHtml(release_html(catalog().releases))
        layout.addWidget(self.view, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
