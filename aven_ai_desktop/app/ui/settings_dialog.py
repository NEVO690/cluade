"""Settings dialog: appearance, AI provider, privacy & data, about."""

from __future__ import annotations

import copy
import platform

import PySide6
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ai.errors import AIError
from app.ai.provider_factory import PROVIDERS, create_provider, key_required
from app.config.aven_models import AVEN_MODELS, aven_model_name
from app.config.secrets import CredentialStore, mask_key
from app.config.settings import (
    MAX_MAX_TOKENS,
    MAX_TIMEOUT,
    MIN_MAX_TOKENS,
    MIN_TIMEOUT,
    PROVIDER_IDS,
    AppSettings,
    sanitize_model_id,
    validate_base_url,
)
from app.paths import user_data_dir
from app.ui.logo import logo_pixmap
from app.version import APP_DISPLAY_NAME, __version__
from app.workers.ai_worker import TaskWorker

THEME_CHOICES = (("system", "Match Windows"), ("light", "Light"), ("dark", "Dark"))


def _help(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("HelpText")
    label.setWordWrap(True)
    label.setOpenExternalLinks(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    return label


class SettingsDialog(QDialog):
    delete_all_requested = Signal()

    def __init__(self, settings: AppSettings, credentials: CredentialStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(620, 600)
        self.settings = copy.deepcopy(settings)
        self.credentials = credentials
        self._tasks: list[TaskWorker] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general(), "General")
        self.tabs.addTab(self._build_provider(), "AI Provider")
        self.tabs.addTab(self._build_privacy(), "Privacy && Data")
        self.tabs.addTab(self._build_about(), "About")
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("PrimaryButton")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._previous_provider = self._selected_provider()
        self._load_provider_fields()

    # --- tabs -----------------------------------------------------------------------
    def _build_general(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setVerticalSpacing(14)
        self.theme_combo = QComboBox()
        for value, label in THEME_CHOICES:
            self.theme_combo.addItem(label, value)
        self.theme_combo.setCurrentIndex(max(0, [v for v, _ in THEME_CHOICES].index(self.settings.theme)))
        form.addRow("Theme", self.theme_combo)

        self.aven_model = self._aven_model_combo(self.settings.aven_model)
        self.code_model = self._aven_model_combo(self.settings.code_model)
        form.addRow("AVEN model", self.aven_model)
        form.addRow("AVEN CODE model", self.code_model)
        form.addRow(
            "",
            _help(
                "<b>AVEN Swift</b> - fastest replies for everyday questions.<br>"
                "<b>AVEN Core</b> - balanced speed and quality.<br>"
                "<b>AVEN Ultra</b> - most capable, for complex reasoning, writing and code."
            ),
        )
        self.enter_checkbox = QCheckBox("Press Enter to send (Shift+Enter inserts a new line)")
        self.enter_checkbox.setChecked(self.settings.send_with_enter)
        form.addRow("Composer", self.enter_checkbox)
        form.addRow(_help("When disabled, use Ctrl+Enter to send and Enter for a new line."))
        return page

    def _build_provider(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(18, 18, 18, 18)
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.provider_combo = QComboBox()
        for pid in PROVIDER_IDS:
            self.provider_combo.addItem(PROVIDERS[pid].name, pid)
        self.provider_combo.setCurrentIndex(PROVIDER_IDS.index(self.settings.provider))
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider", self.provider_combo)
        self.provider_help = _help("")
        form.addRow("", self.provider_help)

        key_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setClearButtonEnabled(True)
        self.show_key = QPushButton("Show")
        self.show_key.setCheckable(True)
        self.show_key.toggled.connect(
            lambda on: (
                self.key_edit.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password),
                self.show_key.setText("Hide" if on else "Show"),
            )
        )
        self.remove_key = QPushButton("Remove saved key")
        self.remove_key.clicked.connect(self._on_remove_key)
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(self.show_key)
        key_row.addWidget(self.remove_key)
        form.addRow("API key", key_row)
        self.key_status = _help("")
        form.addRow("", self.key_status)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("Optional, e.g. http://localhost:11434/v1 for a local server")
        self.base_url_label = QLabel("Base URL")
        form.addRow(self.base_url_label, self.base_url_edit)

        advanced = QLabel("Advanced: provider model behind each AVEN model")
        advanced.setObjectName("SectionLabel")
        form.addRow(advanced)
        self.map_combos: dict[str, QComboBox] = {}
        for model in AVEN_MODELS:
            combo = QComboBox()
            combo.setEditable(True)
            combo.lineEdit().setPlaceholderText("Provider model ID")
            combo.setToolTip(model.description)
            self.map_combos[model.id] = combo
            form.addRow(model.name, combo)
        form.addRow(
            "",
            _help(
                "AVEN models run on the provider selected above. Enter any model ID your account can use, "
                "or load the list of models available to your key."
            ),
        )

        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(MIN_MAX_TOKENS, MAX_MAX_TOKENS)
        self.max_tokens.setSingleStep(1024)
        self.max_tokens.setValue(self.settings.max_tokens)
        form.addRow("Max response tokens", self.max_tokens)
        self.timeout = QSpinBox()
        self.timeout.setRange(MIN_TIMEOUT, MAX_TIMEOUT)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(self.settings.request_timeout)
        form.addRow("Request timeout", self.timeout)
        outer.addLayout(form)

        actions = QHBoxLayout()
        self.list_button = QPushButton("Load available models")
        self.list_button.clicked.connect(self._on_list_models)
        self.test_button = QPushButton("Test connection")
        self.test_button.setObjectName("PrimaryButton")
        self.test_button.clicked.connect(self._on_test)
        actions.addWidget(self.list_button)
        actions.addWidget(self.test_button)
        actions.addStretch(1)
        outer.addLayout(actions)
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.result_label)
        outer.addStretch(1)
        return page

    def _build_privacy(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(
            _help(
                "<b>What leaves your computer.</b> When you send a message, the conversation so far and the "
                "mode's instructions are sent over HTTPS to the AI provider you selected. The provider processes "
                "it under its own terms and privacy policy "
                f"(<a href='{PROVIDERS['anthropic'].privacy_url}'>Anthropic</a>, "
                f"<a href='{PROVIDERS['openai'].privacy_url}'>OpenAI</a>). AVEN AI does not send your data "
                "anywhere else and has no analytics or telemetry."
            )
        )
        layout.addWidget(
            _help(
                "<b>What stays on your computer.</b> Conversations are stored in a local SQLite database in "
                "your user data folder. API keys are kept in the system credential store - Windows Credential "
                "Manager on Windows (never in the database, settings file or logs). Logs record errors and "
                "events only, not message contents."
            )
        )
        folder_row = QHBoxLayout()
        path_label = QLabel(str(user_data_dir()))
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setObjectName("HelpText")
        open_button = QPushButton("Open data folder")
        open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(user_data_dir()))))
        folder_row.addWidget(path_label, 1)
        folder_row.addWidget(open_button)
        layout.addLayout(folder_row)

        delete_button = QPushButton("Delete all conversations…")
        delete_button.setObjectName("DangerButton")
        delete_button.clicked.connect(self._on_delete_all)
        row = QHBoxLayout()
        row.addWidget(delete_button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _build_about(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 24, 18, 18)
        layout.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(72, self.devicePixelRatioF() or 1.0))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        title = QLabel(APP_DISPLAY_NAME)
        title.setObjectName("WelcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        version = QLabel(f"Version {__version__}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        details = _help(
            "AVEN is a general-purpose assistant; AVEN CODE is a programming assistant. "
            "Responses are generated by the AI provider you configure and may be inaccurate. "
            "AVEN CODE never runs code on your computer.<br><br>"
            f"Python {platform.python_version()} · Qt {PySide6.QtCore.qVersion()} · "
            f"PySide6 {PySide6.__version__} · {platform.system()} {platform.release()}"
        )
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(details)
        layout.addStretch(1)
        return page

    def _aven_model_combo(self, current: str) -> QComboBox:
        combo = QComboBox()
        for model in AVEN_MODELS:
            combo.addItem(model.name, model.id)
            combo.setItemData(combo.count() - 1, model.description, Qt.ItemDataRole.ToolTipRole)
        combo.setCurrentIndex(max(0, combo.findData(current)))
        return combo

    # --- provider fields ----------------------------------------------------------------
    def _selected_provider(self) -> str:
        return self.provider_combo.currentData()

    def _load_provider_fields(self) -> None:
        pid = self._selected_provider()
        info = PROVIDERS[pid]
        self.provider_help.setText(f"{info.key_help} <a href='{info.console_url}'>{info.console_url}</a>")
        is_openai = pid == "openai"
        self.base_url_label.setVisible(is_openai)
        self.base_url_edit.setVisible(is_openai)
        self.base_url_edit.setText(self.settings.openai_base_url)

        mapping = self.settings.mapping_for(pid)
        for model_id, combo in self.map_combos.items():
            value = mapping.get(model_id, "")
            combo.clear()
            if value:
                combo.addItem(value)
            combo.setCurrentText(value)

        self.key_edit.clear()
        self._refresh_key_status()
        self.result_label.clear()

    def _refresh_key_status(self) -> None:
        pid = self._selected_provider()
        lookup = self.credentials.lookup(pid)
        env_var = PROVIDERS[pid].key_env_var
        if lookup.source == "environment":
            status = f"Using the {env_var} environment variable ({mask_key(lookup.key)})."
            self.key_edit.setPlaceholderText("Provided by environment variable")
        elif lookup.source == "credential store":
            status = (
                f"A key is saved in the system credential store ({mask_key(lookup.key)}). "
                "Enter a new key to replace it."
            )
            self.key_edit.setPlaceholderText("Saved - enter a new key to replace")
        elif lookup.source == "session":
            status = f"A key is set for this session only ({mask_key(lookup.key)}); it is not saved."
            self.key_edit.setPlaceholderText("Set for this session")
        else:
            status = "No key configured."
            self.key_edit.setPlaceholderText("Paste your API key")
        if not self.credentials.persistent_storage_available:
            status += (
                " No secure credential store is available on this system, so a key entered here is kept in "
                f"memory until you close the app. Use the {env_var} environment variable to avoid re-entering it."
            )
        else:
            status += (
                " Saved keys go to the system credential store (Windows Credential Manager on Windows), protected "
                "by your sign-in. Other programs running under your user account can still read them."
            )
        self.key_status.setText(status)
        self.remove_key.setEnabled(lookup.source in ("credential store", "session"))

    def _store_current_models(self) -> None:
        mapping = self.settings.mapping_for(self._previous_provider)
        for model_id, combo in self.map_combos.items():
            mapping[model_id] = sanitize_model_id(combo.currentText())
        if self._previous_provider == "openai":
            self.settings.openai_base_url = self.base_url_edit.text().strip()

    def _on_provider_changed(self) -> None:
        self._store_current_models()
        self._previous_provider = self._selected_provider()
        self._load_provider_fields()

    def _effective_key(self) -> str | None:
        typed = self.key_edit.text().strip()
        return typed or self.credentials.get_key(self._selected_provider())

    def _make_provider(self):
        pid = self._selected_provider()
        base_url = self.base_url_edit.text().strip() if pid == "openai" else ""
        error = validate_base_url(base_url)
        if error:
            raise ValueError(error)
        return create_provider(pid, self._effective_key(), base_url=base_url, timeout=float(self.timeout.value()))

    def _run_task(self, func, on_success) -> None:
        self._set_testing(True)
        worker = TaskWorker(func)
        self._tasks.append(worker)

        def done() -> None:
            self._set_testing(False)
            if worker in self._tasks:
                self._tasks.remove(worker)

        worker.signals.succeeded.connect(lambda result: (done(), on_success(result)))
        worker.signals.failed.connect(lambda error: (done(), self._show_result(False, self._format_error(error))))
        worker.start()

    @staticmethod
    def _format_error(error: AIError) -> str:
        return f"{error.title}: {error.user_message}"

    def _set_testing(self, busy: bool) -> None:
        self.test_button.setEnabled(not busy)
        self.list_button.setEnabled(not busy)
        if busy:
            self.result_label.setObjectName("")
            self.result_label.setText("Contacting provider…")
            self.result_label.style().unpolish(self.result_label)
            self.result_label.style().polish(self.result_label)

    def _show_result(self, ok: bool, text: str) -> None:
        self.result_label.setObjectName("ResultOk" if ok else "ResultError")
        self.result_label.setText(("✓ " if ok else "✕ ") + text)
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)

    def _on_test(self) -> None:
        aven_model = self.aven_model.currentData()
        model = sanitize_model_id(self.map_combos[aven_model].currentText())
        if not model:
            self._show_result(False, f"Set the provider model for {aven_model_name(aven_model)} under Advanced first.")
            return
        try:
            provider = self._make_provider()
        except (AIError, ValueError) as exc:
            self._show_result(False, self._format_error(exc) if isinstance(exc, AIError) else str(exc))
            return
        name = aven_model_name(aven_model)
        self._run_task(
            lambda: provider.test_connection(model),
            lambda text: self._show_result(True, f"{name} is ready. {text}"),
        )

    def _on_list_models(self) -> None:
        try:
            provider = self._make_provider()
        except (AIError, ValueError) as exc:
            self._show_result(False, self._format_error(exc) if isinstance(exc, AIError) else str(exc))
            return
        self._run_task(provider.list_models, self._on_models_loaded)

    def _on_models_loaded(self, models: list[str]) -> None:
        if not models:
            self._show_result(False, "The provider returned no models for this key.")
            return
        for combo in self.map_combos.values():
            current = combo.currentText()
            combo.clear()
            combo.addItems(models)
            combo.setCurrentText(current)  # never guess a mapping for an unset AVEN model
        self._show_result(True, f"Loaded {len(models)} models available to this key.")

    def _on_remove_key(self) -> None:
        pid = self._selected_provider()
        self.credentials.delete_key(pid)
        self._refresh_key_status()
        self._show_result(True, "Saved key removed.")

    def _on_delete_all(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Delete all conversations?",
            "This permanently deletes every conversation stored on this computer. This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_all_requested.emit()

    # --- save --------------------------------------------------------------------------
    def _on_save(self) -> None:
        pid = self._selected_provider()
        base_url = self.base_url_edit.text().strip()
        if pid == "openai":
            error = validate_base_url(base_url)
            if error:
                self.tabs.setCurrentIndex(1)
                QMessageBox.warning(self, "Invalid base URL", error)
                return
        self._previous_provider = pid
        self._store_current_models()

        typed_key = self.key_edit.text().strip()
        if typed_key:
            try:
                where = self.credentials.save_key(pid, typed_key)
            except ValueError as exc:
                self.tabs.setCurrentIndex(1)
                QMessageBox.warning(self, "Invalid API key", str(exc))
                return
            if where == "session":
                QMessageBox.information(
                    self,
                    "Key kept for this session",
                    "No secure credential store is available, so the API key will be forgotten when you close "
                    f"AVEN AI. Set the {PROVIDERS[pid].key_env_var} environment variable to make it permanent.",
                )

        self.settings.provider = pid
        self.settings.aven_model = self.aven_model.currentData()
        self.settings.code_model = self.code_model.currentData()
        self.settings.theme = self.theme_combo.currentData()
        self.settings.send_with_enter = self.enter_checkbox.isChecked()
        self.settings.max_tokens = self.max_tokens.value()
        self.settings.request_timeout = self.timeout.value()
        self.settings.normalized()
        if key_required(pid, self.settings.openai_base_url) and not self.credentials.get_key(pid):
            QMessageBox.information(
                self, "API key needed", "Settings were saved, but no API key is configured for this provider yet."
            )
        self.accept()
