"""Application bootstrap: logging, services, theme and main window."""

from __future__ import annotations

import logging
import sys
import traceback
from types import TracebackType

from PySide6.QtWidgets import QApplication, QMessageBox

from app.ai.chat_service import ChatService
from app.config.secrets import CredentialStore
from app.config.settings import SettingsStore, apply_env_overrides, load_dotenv_file
from app.logging_setup import setup_logging
from app.paths import database_path, is_frozen, logs_dir
from app.storage.conversation_repository import ConversationRepository
from app.storage.database import Database, StorageError
from app.ui.logo import app_icon
from app.ui.main_window import MainWindow
from app.ui.theme_manager import ThemeManager
from app.version import APP_DISPLAY_NAME, APP_NAME, APP_ORGANIZATION, __version__

log = logging.getLogger(__name__)

WINDOWS_APP_ID = "AVENAI.Desktop"


def _set_windows_app_id() -> None:
    """Give the process its own taskbar identity so the AVEN icon is used."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except (AttributeError, OSError):
        pass


def _install_excepthook() -> None:
    def hook(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None,
                f"{APP_NAME} - unexpected error",
                f"An unexpected error occurred: {exc_type.__name__}.\n\n"
                f"Details were written to the log folder:\n{logs_dir()}",
            )

    sys.excepthook = hook


def run(argv: list[str]) -> int:
    if not is_frozen():
        load_dotenv_file()
    setup_logging()
    log.info("Starting %s %s", APP_DISPLAY_NAME, __version__)
    _set_windows_app_id()

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    _install_excepthook()

    settings_store = SettingsStore()
    settings = apply_env_overrides(settings_store.load())
    credentials = CredentialStore()

    theme = ThemeManager(app)
    theme.apply(settings.theme)

    try:
        database = Database(database_path())
    except StorageError as exc:
        QMessageBox.critical(None, APP_NAME, f"{exc}\n\nDatabase location:\n{database_path()}")
        return 2

    repository = ConversationRepository(database)
    window = MainWindow(settings, settings_store, credentials, repository, theme, ChatService(settings, credentials))
    window.show()
    try:
        return app.exec()
    finally:
        database.close()


def report_startup_failure(exc: BaseException) -> None:
    """Last-resort error reporting when the app fails before the window appears."""
    details = "".join(traceback.format_exception(exc))
    try:
        (logs_dir() / "startup-error.log").write_text(details, encoding="utf-8")
        location = str(logs_dir() / "startup-error.log")
    except OSError:
        location = "(could not write log file)"
    message = f"{APP_NAME} could not start:\n\n{type(exc).__name__}: {exc}\n\nDetails: {location}"
    try:
        app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841 - needed for the dialog
        QMessageBox.critical(None, APP_NAME, message)
        return
    except Exception:
        log.debug("Qt error dialog unavailable", exc_info=True)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
            return
        except Exception:
            log.debug("Native error dialog unavailable", exc_info=True)
    if sys.stderr is not None:
        print(message, file=sys.stderr)
