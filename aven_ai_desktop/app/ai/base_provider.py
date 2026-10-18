"""Provider interface shared by every AI backend."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" or "assistant"
    content: str


@dataclass(frozen=True)
class StreamEvent:
    """Emitted while a response streams.

    ``kind`` is ``"text"`` (a text delta in ``text``) or ``"model"`` (the model
    that is actually serving the response, in ``text``).
    """

    kind: str
    text: str


@dataclass
class ChatRequest:
    model: str
    system_prompt: str
    messages: list[ChatMessage]
    max_tokens: int = 32_000
    cancel_event: threading.Event = field(default_factory=threading.Event)


class AIProvider(ABC):
    """A configured client for one provider. Instances are cheap to create."""

    #: Stable identifier, e.g. "anthropic".
    provider_id: str = ""
    #: Human readable name shown in the UI.
    display_name: str = ""

    @abstractmethod
    def stream_chat(self, request: ChatRequest) -> Iterator[StreamEvent]:
        """Yield events for a streamed response.

        Must stop promptly once ``request.cancel_event`` is set and must raise
        :class:`app.ai.errors.AIError` subclasses for failures.
        """

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return model identifiers available to the configured credentials."""

    def test_connection(self, model: str) -> str:
        """Send a minimal real request and return a short confirmation string."""
        request = ChatRequest(
            model=model,
            system_prompt="Reply with the single word: OK",
            messages=[ChatMessage("user", "Connection test. Reply with OK.")],
            max_tokens=1024,
        )
        served_by = model
        received = []
        for event in self.stream_chat(request):
            if event.kind == "model" and event.text:
                served_by = event.text
            elif event.kind == "text":
                received.append(event.text)
        reply = "".join(received).strip()
        preview = (reply[:40] + "…") if len(reply) > 40 else reply
        return f"Connected to {self.display_name} using {served_by}. Reply: “{preview or '(empty)'}”"
