"""Runs llama.cpp's ``llama-server`` locally for AVEN Local.

The server listens only on 127.0.0.1, on a random free port, and requires a
random per-session token, so other programs on the network cannot use it.
"""

from __future__ import annotations

import atexit
import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

from app.paths import logs_dir, project_root

log = logging.getLogger(__name__)

CONTEXT_TOKENS = 12_288
STARTUP_TIMEOUT = 300.0  # loading a large model from a slow disk can take a while


class EngineError(Exception):
    """User-facing local engine failure."""


def default_binary() -> Path:
    override = os.environ.get("AVEN_LLAMA_SERVER", "").strip()
    if override:
        return Path(override)
    name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    return project_root() / "engine" / name


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LocalEngine:
    def __init__(self, binary: Path | None = None, command_prefix: list[str] | None = None) -> None:
        self.binary = binary or default_binary()
        # Tests run a fake server script: command_prefix = [python, fake_server.py]
        self.command_prefix = command_prefix
        self.token = secrets.token_hex(16)
        self.port = 0
        self.model_path: Path | None = None
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._stderr_tail: deque[str] = deque(maxlen=40)
        atexit.register(self.stop)

    def available(self) -> bool:
        return self.command_prefix is not None or self.binary.is_file()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def ensure(self, model_path: Path) -> str:
        """Start (or switch) the server for ``model_path``; returns the OpenAI-compatible base URL."""
        with self._lock:
            if self.process is not None and self.process.poll() is None and self.model_path == model_path:
                return self.base_url
            self._stop_locked()
            if not self.available():
                raise EngineError("The local AI engine is not included in this build of AVEN AI.")
            self._start_locked(model_path)
            return self.base_url

    def _start_locked(self, model_path: Path) -> None:
        self.port = _free_port()
        args = [
            "-m", str(model_path),
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "-c", str(CONTEXT_TOKENS),
            "--jinja",
            "--api-key", self.token,
        ]  # fmt: skip
        command = [*(self.command_prefix or [str(self.binary)]), *args]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # no console window
        log.info("Starting local engine for %s", model_path.name)
        self._stderr_tail.clear()
        self.process = subprocess.Popen(  # noqa: S603 - fixed binary and arguments, no shell
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            cwd=str(Path(command[0]).parent) if self.command_prefix is None else None,
            creationflags=flags,
        )
        threading.Thread(target=self._pump_stderr, args=(self.process,), daemon=True).start()
        self.model_path = model_path
        self._wait_ready()

    def _pump_stderr(self, process: subprocess.Popen) -> None:
        try:
            with (logs_dir() / "engine.log").open("a", encoding="utf-8", errors="replace") as log_file:
                for raw in process.stderr:  # type: ignore[union-attr]
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    self._stderr_tail.append(line)
                    log_file.write(line + "\n")
        except (OSError, ValueError):
            pass

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT
        url = f"http://127.0.0.1:{self.port}/health"
        while time.monotonic() < deadline:
            if self.process is None or self.process.poll() is not None:
                detail = " ".join(list(self._stderr_tail)[-3:])
                self._stop_locked()
                raise EngineError(
                    "The local AI engine stopped while loading the model. Your computer may not have enough "
                    f"free memory for this model; try AVEN Light. {detail[-300:]}"
                )
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        log.info("Local engine ready on port %d", self.port)
                        return
            except (urllib.error.URLError, OSError):
                pass  # still loading (503) or not listening yet
            time.sleep(0.25)
        self._stop_locked()
        raise EngineError("The local AI engine took too long to load the model.")

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        process, self.process, self.model_path = self.process, None, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.info("Local engine stopped")


_engine: LocalEngine | None = None


def get_engine() -> LocalEngine:
    global _engine
    if _engine is None:
        _engine = LocalEngine()
    return _engine


def set_engine(engine: LocalEngine | None) -> None:
    """Replace the shared engine (used by tests)."""
    global _engine
    if _engine is not None and _engine is not engine:
        _engine.stop()
    _engine = engine
