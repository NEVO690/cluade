"""Glue between settings, credentials and providers. Contains no Qt code."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.ai import errors
from app.ai.base_provider import AIProvider, ChatMessage, ChatRequest, StreamEvent
from app.ai.prompts import MODES, system_prompt_for
from app.ai.provider_factory import PROVIDERS, create_provider, key_required
from app.config.secrets import CredentialStore
from app.config.settings import AppSettings

log = logging.getLogger(__name__)

# Roughly 100k tokens of history. Older messages are left out of the request
# (they stay in the local database) so long conversations remain usable.
MAX_HISTORY_CHARS = 400_000

ProviderFactory = Callable[..., AIProvider]


@dataclass(frozen=True)
class ConfigStatus:
    ready: bool
    provider_name: str
    model: str
    problem: str = ""


def trim_history(messages: list[ChatMessage], max_chars: int = MAX_HISTORY_CHARS) -> list[ChatMessage]:
    """Keep the newest messages within ``max_chars``; the result starts with a user turn."""
    cleaned = [m for m in messages if m.content.strip() and m.role in ("user", "assistant")]
    kept: list[ChatMessage] = []
    total = 0
    for message in reversed(cleaned):
        size = len(message.content)
        if kept and total + size > max_chars:
            break
        kept.append(message)
        total += size
    kept.reverse()
    while kept and kept[0].role != "user":
        kept.pop(0)
    return kept


class ChatService:
    def __init__(
        self,
        settings: AppSettings,
        credentials: CredentialStore,
        provider_factory: ProviderFactory = create_provider,
    ) -> None:
        self.settings = settings
        self.credentials = credentials
        self.provider_factory = provider_factory

    # --- configuration ---------------------------------------------------------
    def status(self, mode: str) -> ConfigStatus:
        pid = self.settings.provider
        info = PROVIDERS[pid]
        model = self.settings.model_for_mode(mode)
        base_url = self.settings.openai_base_url if pid == "openai" else ""
        if key_required(pid, base_url) and not self.credentials.get_key(pid):
            return ConfigStatus(False, info.name, model, f"Add an API key for {info.name} to start chatting.")
        if not model:
            return ConfigStatus(
                False, info.name, model, f"Choose a model for {MODES[mode].name} in Settings → AI Provider."
            )
        return ConfigStatus(True, info.name, model)

    def create_provider(self, provider_id: str | None = None, api_key: str | None = None) -> AIProvider:
        pid = provider_id or self.settings.provider
        key = api_key if api_key is not None else self.credentials.get_key(pid)
        return self.provider_factory(
            pid,
            key,
            base_url=self.settings.openai_base_url if pid == "openai" else "",
            timeout=float(self.settings.request_timeout),
        )

    # --- requests --------------------------------------------------------------
    def build_request(self, mode: str, history: list[ChatMessage]) -> ChatRequest:
        model = self.settings.model_for_mode(mode)
        if not model:
            raise errors.MissingModelError(
                f"No model is configured for {MODES[mode].name}. Choose one in Settings → AI Provider."
            )
        messages = trim_history(history)
        if not messages or messages[-1].role != "user":
            raise errors.InvalidRequestError("There is no message to send.")
        return ChatRequest(
            model=model,
            system_prompt=system_prompt_for(mode),
            messages=messages,
            max_tokens=self.settings.max_tokens,
        )

    def stream(self, request: ChatRequest, provider: AIProvider | None = None) -> Iterator[StreamEvent]:
        """Stream a response, converting every failure into an :class:`AIError`."""
        try:
            provider = provider or self.create_provider()
            yield from provider.stream_chat(request)
        except errors.AIError:
            raise
        except Exception as exc:  # defensive: never leak raw exceptions to the UI
            log.exception("Unexpected provider failure (%s)", type(exc).__name__)
            raise errors.ProviderError(f"Unexpected error: {type(exc).__name__}") from exc
