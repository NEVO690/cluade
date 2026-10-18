"""One-time download of an AVEN Local model, with progress and cancel."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from app.config.aven_models import aven_model_name
from app.local.downloader import DownloadCancelledError, DownloadError, download_model
from app.local.models import LOCAL_MODELS, ModelFile
from app.workers.ai_worker import BackgroundJob


class DownloadSignals(QObject):
    done = Signal()
    progress = Signal(object, object)  # bytes done, total (Python ints: sizes exceed 32 bits)
    succeeded = Signal()
    failed = Signal(str)
    cancelled = Signal()


class DownloadJob(BackgroundJob):
    def __init__(self, file: ModelFile, cancel: threading.Event) -> None:
        self.file = file
        self.cancel = cancel
        self.signals = DownloadSignals()

    def run(self) -> None:
        last = 0.0

        def report(done: int, total: int) -> None:
            nonlocal last
            now = time.monotonic()
            if now - last >= 0.1 or done == total:
                last = now
                self.signals.progress.emit(done, total)

        try:
            download_model(self.file, progress=report, cancel=self.cancel)
        except DownloadCancelledError:
            self.signals.cancelled.emit()
        except DownloadError as exc:
            self.signals.failed.emit(str(exc))
        except OSError as exc:  # e.g. disk full
            self.signals.failed.emit(f"Could not save the model: {exc.strerror or exc}.")
        else:
            self.signals.succeeded.emit()


def _gb(value: int) -> str:
    return f"{value / 1_000_000_000:.2f} GB"


class DownloadDialog(QDialog):
    """Downloads the model behind ``aven_model``; ``exec()`` returns Accepted when it is ready."""

    def __init__(self, aven_model: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.local = LOCAL_MODELS[aven_model]
        self.cancel_event = threading.Event()
        self._started_at = 0.0
        name = aven_model_name(aven_model)
        self.setWindowTitle(f"Download {name}")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        title = QLabel(f"Download {name} ({self.local.file.size_text})")
        title.setObjectName("ConversationTitle")
        layout.addWidget(title)
        info = QLabel(
            f"{name} runs on this computer using the open-source {self.local.file.label} model (Apache-2.0). "
            "It is downloaded once from Hugging Face and verified. After that it works free, with no key and "
            "no account, and your conversations stay on this computer."
        )
        info.setObjectName("HelpText")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)
        self.status = QLabel("Ready to download.")
        self.status.setObjectName("HelpText")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        self.start_button = QPushButton("Download")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self.start)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)
        self.job: DownloadJob | None = None

    def start(self) -> None:
        self.start_button.setEnabled(False)
        self.start_button.setText("Downloading…")
        self.cancel_event.clear()
        self._started_at = time.monotonic()
        self.status.setText("Connecting…")
        self.job = DownloadJob(self.local.file, self.cancel_event)
        self.job.signals.progress.connect(self._on_progress)
        self.job.signals.succeeded.connect(self._on_success)
        self.job.signals.failed.connect(self._on_failed)
        self.job.signals.cancelled.connect(self.reject)
        self.job.start()

    def _on_progress(self, done: int, total: int) -> None:
        self.bar.setValue(int(done * 1000 / max(total, 1)))
        elapsed = max(time.monotonic() - self._started_at, 0.001)
        self.status.setText(f"{_gb(done)} of {_gb(total)}")
        speed = done / elapsed
        if speed > 0 and done < total:
            minutes = (total - done) / speed / 60
            self.status.setText(f"{_gb(done)} of {_gb(total)} · about {max(1, round(minutes))} min left")

    def _on_success(self) -> None:
        self.bar.setValue(1000)
        self.status.setText("Downloaded and verified.")
        self.accept()

    def _on_failed(self, message: str) -> None:
        self.status.setText(message)
        self.start_button.setEnabled(True)
        self.start_button.setText("Try again")

    def _on_cancel(self) -> None:
        if self.job is not None and not self.start_button.isEnabled():
            self.cancel_event.set()  # the job reports back and closes the dialog
            self.status.setText("Cancelling… (the partial download is kept and resumes next time)")
        else:
            self.reject()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.cancel_event.set()
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.key() == Qt.Key.Key_Escape:
            self._on_cancel()
            return
        super().keyPressEvent(event)
