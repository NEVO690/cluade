"""Account & subscription: AVEN CODE access, checkout and subscription management.

Every decision comes from the AVEN Cloud server: this dialog only shows what the server
reports and opens Stripe's own pages (created by the server) in the browser.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.account.service import AccountError, AccountService
from app.ai.errors import ProviderError
from app.workers.ai_worker import TaskWorker

PRODUCT = "aven_code"


def _wrap(func):
    def call():
        try:
            return func()
        except AccountError as exc:
            raise ProviderError(str(exc)) from exc

    return call


class AccountDialog(QDialog):
    access_changed = Signal()

    def __init__(self, account: AccountService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.account = account
        self.setWindowTitle("Account & subscription")
        self.resize(520, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        title = QLabel("AVEN CODE subscription")
        title.setObjectName("WelcomeTitle")
        layout.addWidget(title)
        intro = QLabel(
            "AVEN AI, AVEN Python and AVEN Unity are free. AVEN CODE, the professional coding category, needs a "
            "subscription. Payments are handled by Stripe in your browser; AVEN AI never sees your card."
        )
        intro.setWordWrap(True)
        intro.setObjectName("HelpText")
        layout.addWidget(intro)
        self.status_label = QLabel("Checking…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.mode_label = QLabel("")
        self.mode_label.setObjectName("AccessBadge")
        self.mode_label.setProperty("kind", "preview")
        self.mode_label.hide()
        layout.addWidget(self.mode_label)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        self.subscribe_button = QPushButton("Subscribe to AVEN CODE")
        self.subscribe_button.setObjectName("PrimaryButton")
        self.subscribe_button.clicked.connect(self.subscribe)
        self.manage_button = QPushButton("Manage subscription")
        self.manage_button.clicked.connect(self.manage)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        for button in (self.subscribe_button, self.manage_button, self.refresh_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        if not account.available:
            self.status_label.setText(
                "Subscriptions are not available in this build yet: it is not connected to the AVEN AI server. "
                "The free categories work as usual."
            )
            for button in (self.subscribe_button, self.manage_button, self.refresh_button):
                button.setEnabled(False)
        else:
            self.refresh()

    def _run(self, func, on_success) -> None:
        for button in (self.subscribe_button, self.manage_button, self.refresh_button):
            button.setEnabled(False)
        worker = TaskWorker(_wrap(func))
        worker.signals.succeeded.connect(on_success)
        worker.signals.failed.connect(lambda exc: self.status_label.setText(f"⚠ {exc.user_message}"))
        worker.signals.done.connect(self._enable)
        worker.start()

    def _enable(self) -> None:
        if self.account.available:
            for button in (self.subscribe_button, self.manage_button, self.refresh_button):
                button.setEnabled(True)
            self.subscribe_button.setVisible(not self.account.has(PRODUCT))

    def refresh(self) -> None:
        def work():
            status = self.account.refresh()
            price = None
            mode = "disabled"
            try:
                price = self.account.price(PRODUCT)
                mode = self.account.billing_mode()
            except AccountError:
                pass
            return status, price, mode

        self._run(work, self._show)

    def _show(self, result) -> None:
        status, price, mode = result
        active = self.account.has(PRODUCT)
        lines = []
        if active:
            expiry = self.account.entitlement_expiry()
            lines.append("✓ AVEN CODE is active on this account.")
            if expiry:
                lines.append(
                    f"Access confirmed until {expiry:%Y-%m-%d %H:%M} UTC (renews automatically while subscribed)."
                )
        else:
            lines.append("AVEN CODE is not active on this account.")
            lines.append(f"Price: {price}" if price else "Price: shown on the checkout page.")
        for sub in status.subscriptions:
            note = " (cancels at the end of the period)" if sub.get("cancel_at_period_end") else ""
            lines.append(f"Subscription: {sub.get('status')}{note}")
            if sub.get("status") in ("past_due", "unpaid"):
                lines.append("⚠ The last payment failed. Update your card under Manage subscription.")
        lines.append(f"Account: {status.account_id}")
        self.status_label.setText("\n".join(lines))
        self.mode_label.setVisible(mode == "test")
        self.mode_label.setText("Test mode: no real payments are taken")
        self.access_changed.emit()

    def subscribe(self) -> None:
        self._run(lambda: self.account.checkout_url(PRODUCT), self._open)

    def manage(self) -> None:
        self._run(self.account.portal_url, self._open)

    def _open(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))
        self.status_label.setText("Stripe opened in your browser. When you are done, come back here and click Refresh.")
