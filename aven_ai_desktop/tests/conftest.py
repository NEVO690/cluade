from __future__ import annotations

import os
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

# Headless Qt and an isolated data directory for every test run.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["AVEN_DATA_DIR"] = tempfile.mkdtemp(prefix="aven-test-")
for var in (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "AVEN_PROVIDER",
    "AVEN_MODEL",
    "AVEN_CODE_MODEL",
    "AVEN_BASE_URL",
    "AVEN_CLOUD_URL",
):
    os.environ.pop(var, None)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from app.ai.base_provider import AIProvider, ChatRequest, StreamEvent  # noqa: E402
from app.ai.errors import AIError  # noqa: E402


class FakeProvider(AIProvider):
    """Deterministic provider for tests: streams a fixed reply or raises."""

    provider_id = "anthropic"
    display_name = "Fake"

    def __init__(
        self,
        reply: str = "Hello from the fake provider.",
        error: AIError | None = None,
        delay: float = 0.0,
        chunk: int = 5,
    ) -> None:
        self.reply = reply
        self.error = error
        self.delay = delay
        self.chunk = chunk
        self.requests: list[ChatRequest] = []

    def stream_chat(self, request: ChatRequest) -> Iterator[StreamEvent]:
        self.requests.append(request)
        yield StreamEvent("model", request.model)
        if self.error is not None:
            raise self.error
        for i in range(0, len(self.reply), self.chunk):
            if request.cancel_event.is_set():
                return
            if self.delay:
                time.sleep(self.delay)
            yield StreamEvent("text", self.reply[i : i + self.chunk])

    def list_models(self) -> list[str]:
        return ["fake-model"]


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()
