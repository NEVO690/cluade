"""Application logging.

Logs go to a rotating file in the user data directory. A redaction filter
masks anything that looks like an API key, and the application never logs
conversation contents - only event types, status codes and error classes.
"""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

from app.paths import logs_dir

# Common credential shapes: sk-..., sk-ant-..., long bearer-like tokens.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|authorization|x-api-key)(\s*[:=]\s*)((?:bearer\s+)?\S+)"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
]


def redact(text: str) -> str:
    text = _SECRET_PATTERNS[0].sub("sk-***REDACTED***", text)
    text = _SECRET_PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}***REDACTED***", text)
    text = _SECRET_PATTERNS[2].sub("Bearer ***REDACTED***", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if getattr(root, "_aven_configured", False):
        return
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    redactor = RedactingFilter()

    try:
        file_handler = RotatingFileHandler(logs_dir() / "aven.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(fmt)
        file_handler.addFilter(redactor)
        root.addHandler(file_handler)
    except OSError:
        pass

    # Windowed (no-console) builds have no stderr.
    if sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(fmt)
        stream_handler.addFilter(redactor)
        root.addHandler(stream_handler)

    # Third-party HTTP libraries can log request details at DEBUG; keep them quiet.
    for noisy in ("httpx", "httpx2", "httpcore", "anthropic", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root._aven_configured = True  # type: ignore[attr-defined]
