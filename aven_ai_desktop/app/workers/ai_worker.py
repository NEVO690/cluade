"""Background execution so network calls never block the GUI thread.

Each job runs on a daemon thread, so a request stuck waiting on the network can
never keep the application from exiting. Signals emitted from that thread are
delivered to GUI-thread slots as queued connections, so receivers may touch
widgets safely.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from app.ai.base_provider import StreamEvent
from app.ai.errors import AIError, ProviderError

log = logging.getLogger(__name__)

# Text deltas are batched so a fast stream does not flood the event loop.
EMIT_INTERVAL = 0.04


class StreamSignals(QObject):
    done = Signal()  # always the last signal a job emits
    text = Signal(int, str)  # generation id, accumulated delta
    model = Signal(int, str)
    truncated = Signal(int)
    finished = Signal(int)
    failed = Signal(int, object)  # generation id, AIError


# Jobs are referenced from the GUI thread until shortly after they finish, so their
# signal objects are always destroyed on the GUI thread.
_LIVE_JOBS: set[_Job] = set()
RELEASE_DELAY_MS = 2000


class _Job:
    signals: StreamSignals | TaskSignals

    def start(self) -> None:
        """Start the job. Must be called from the GUI thread."""
        _LIVE_JOBS.add(self)
        self.signals.done.connect(lambda: QTimer.singleShot(RELEASE_DELAY_MS, lambda: _LIVE_JOBS.discard(self)))
        threading.Thread(target=self._run_and_signal, name=type(self).__name__, daemon=True).start()

    def _run_and_signal(self) -> None:
        try:
            self.run()
        finally:
            self.signals.done.emit()

    def run(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class StreamWorker(_Job):
    """Consumes a stream of :class:`StreamEvent` produced by ``stream_factory``."""

    def __init__(
        self,
        generation_id: int,
        stream_factory: Callable[[], Iterator[StreamEvent]],
        cancel_event: threading.Event,
    ) -> None:
        self.generation_id = generation_id
        self.stream_factory = stream_factory
        self.cancel_event = cancel_event
        self.signals = StreamSignals()

    def run(self) -> None:
        gid = self.generation_id
        buffer: list[str] = []
        last_emit = time.monotonic()
        try:
            for event in self.stream_factory():
                if self.cancel_event.is_set():
                    break
                if event.kind == "text":
                    buffer.append(event.text)
                    now = time.monotonic()
                    if now - last_emit >= EMIT_INTERVAL:
                        self.signals.text.emit(gid, "".join(buffer))
                        buffer.clear()
                        last_emit = now
                elif event.kind == "model":
                    self.signals.model.emit(gid, event.text)
                elif event.kind == "truncated":
                    if buffer:
                        self.signals.text.emit(gid, "".join(buffer))
                        buffer.clear()
                    self.signals.truncated.emit(gid)
            if buffer:
                self.signals.text.emit(gid, "".join(buffer))
            self.signals.finished.emit(gid)
        except AIError as exc:
            log.info("Generation %d failed: %s", gid, type(exc).__name__)
            self.signals.failed.emit(gid, exc)
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("Generation %d crashed", gid)
            self.signals.failed.emit(gid, ProviderError(f"Unexpected error: {type(exc).__name__}"))


class TaskSignals(QObject):
    done = Signal()
    succeeded = Signal(object)
    failed = Signal(object)  # AIError


class TaskWorker(_Job):
    """Runs a short blocking call (connection test, model listing) off the GUI thread."""

    def __init__(self, func: Callable[[], Any]) -> None:
        self.func = func
        self.signals = TaskSignals()

    def run(self) -> None:
        try:
            result = self.func()
        except AIError as exc:
            self.signals.failed.emit(exc)
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("Background task crashed")
            self.signals.failed.emit(ProviderError(f"Unexpected error: {type(exc).__name__}"))
        else:
            self.signals.succeeded.emit(result)
