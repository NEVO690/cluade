"""AI services AVEN Cloud can run on, and how AVEN models are mapped to them.

* ``groq``      - free API key (console.groq.com), OpenAI-compatible
* ``gemini``    - free tier with a Google AI Studio key, OpenAI-compatible
* ``anthropic`` - paid, Claude models
* ``openai_compatible`` - any other OpenAI-compatible service (set the base URL and models)

Free services rename and retire models often, so for each AVEN model the
server keeps a list of *candidates*. On first use it asks the service which
models exist and picks the first candidate that is available. A candidate is
either an exact model id or a pattern ``"~include -exclude"`` that matches
model ids containing every include word and none of the exclude words (the
newest-looking match wins).
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import anthropic
import openai

log = logging.getLogger("aven_cloud")

AVEN_MODEL_IDS = ("aven-1", "aven-ultra", "aven-core", "aven-light")

# Model ids that are never used for chat (speech, images, embeddings, safety classifiers, previews).
NON_CHAT_WORDS = (
    "embed",
    "tts",
    "whisper",
    "audio",
    "image",
    "imagen",
    "veo",
    "guard",
    "moderation",
    "transcribe",
    "live",
    "native",
    "preview",
    "exp",
    "aqa",
    "vision",
    "compound",
    "robotics",
)


@dataclass(frozen=True)
class ServiceInfo:
    id: str
    kind: str  # "anthropic" or "openai"
    key_env: str
    base_url: str
    candidates: dict[str, tuple[str, ...]]


SERVICES: dict[str, ServiceInfo] = {
    "groq": ServiceInfo(
        id="groq",
        kind="openai",
        key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        candidates={
            "aven-1": ("openai/gpt-oss-120b", "llama-3.3-70b-versatile", "~gpt-oss-120b", "~70b"),
            "aven-ultra": ("openai/gpt-oss-120b", "~gpt-oss-120b", "llama-3.3-70b-versatile", "~70b"),
            "aven-core": ("llama-3.3-70b-versatile", "~70b", "openai/gpt-oss-20b", "~gpt-oss"),
            "aven-light": ("llama-3.1-8b-instant", "~8b", "openai/gpt-oss-20b", "~gpt-oss-20b"),
        },
    ),
    "gemini": ServiceInfo(
        id="gemini",
        kind="openai",
        key_env="GEMINI_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        candidates={
            "aven-1": ("~gemini flash -lite",),
            # Free-tier access to Pro models is very limited, so Ultra also uses Flash by default.
            "aven-ultra": ("~gemini flash -lite",),
            "aven-core": ("~gemini flash -lite",),
            "aven-light": ("~gemini flash lite", "~gemini flash"),
        },
    ),
    "anthropic": ServiceInfo(
        id="anthropic",
        kind="anthropic",
        key_env="ANTHROPIC_API_KEY",
        base_url="",
        candidates={
            "aven-1": ("claude-opus-5-5",),
            "aven-ultra": ("claude-opus-5-5",),
            "aven-core": ("claude-sonnet-5-5",),
            "aven-light": ("claude-haiku-5-5",),
        },
    ),
    "openai_compatible": ServiceInfo(
        id="openai_compatible", kind="openai", key_env="AVEN_UPSTREAM_API_KEY", base_url="", candidates={}
    ),
}

# Reasoning effort per AVEN model, only for Anthropic models that accept it.
ANTHROPIC_EFFORT = {"aven-ultra": "xhigh"}
ANTHROPIC_EFFORT_MODELS = frozenset(
    {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-haiku-5-5"}
)
# Server-side refusal fallback (Anthropic): a declined request is re-run on a recommended model.
FALLBACK_MODELS = frozenset({"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"

ANTHROPIC_FINISH = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length", "refusal": "content_filter"}


# --- model resolution ----------------------------------------------------------------------


def _version_key(model_id: str) -> tuple:
    """Sort key that orders "gemini-3.5-flash" above "gemini-2.5-flash"."""
    parts: list = []
    number = ""
    for ch in model_id:
        if ch.isdigit():
            number += ch
        else:
            if number:
                parts.append((1, int(number)))
                number = ""
            parts.append((0, ch))
    if number:
        parts.append((1, int(number)))
    return tuple(parts)


def is_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(word in lowered for word in NON_CHAT_WORDS)


def match_candidate(candidate: str, available: list[str]) -> str | None:
    if not candidate.startswith("~"):
        return candidate if candidate in available else None
    words = candidate[1:].split()
    include = [w.lower() for w in words if not w.startswith("-")]
    exclude = [w[1:].lower() for w in words if w.startswith("-")]
    matches = [
        m
        for m in available
        if is_chat_model(m) and all(w in m.lower() for w in include) and not any(w in m.lower() for w in exclude)
    ]
    return max(matches, key=_version_key) if matches else None


def choose_model(candidates: tuple[str, ...], available: list[str] | None) -> str | None:
    """First candidate that exists; without a model list, the first exact candidate."""
    if available is None:
        return next((c for c in candidates if not c.startswith("~")), None)
    for candidate in candidates:
        found = match_candidate(candidate, available)
        if found:
            return found
    chat_models = sorted((m for m in available if is_chat_model(m)), key=_version_key, reverse=True)
    return chat_models[0] if chat_models else None


# --- backends -----------------------------------------------------------------------------


@dataclass
class StreamHandle:
    """An open upstream stream: iterate ``texts()``, then read ``finish_reason``; always ``close()``."""

    texts: AsyncIterator[str]
    close: object  # async callable
    finish_reason: str = "stop"


@dataclass
class Backend:
    service: ServiceInfo
    client: object  # anthropic.AsyncAnthropic or openai.AsyncOpenAI
    overrides: dict[str, str] = field(default_factory=dict)
    models_ttl: float = 3600.0
    _available: list[str] | None = None
    _fetched_at: float = 0.0

    @property
    def kind(self) -> str:
        return self.service.kind

    async def available_models(self) -> list[str] | None:
        if self._available is not None and time.monotonic() - self._fetched_at < self.models_ttl:
            return self._available
        try:
            ids: list[str] = []
            async for model in self.client.models.list():
                ids.append(model.id.removeprefix("models/"))
            self._available, self._fetched_at = ids, time.monotonic()
            log.info("Upstream offers %d models", len(ids))
        except (anthropic.APIError, openai.APIError) as exc:
            log.warning("Could not list upstream models (%s); using configured defaults", type(exc).__name__)
            return None
        return self._available

    async def resolve(self, aven_model: str) -> str | None:
        if aven_model in self.overrides:
            return self.overrides[aven_model]
        candidates = self.service.candidates.get(aven_model, ())
        if self.kind == "anthropic":
            return candidates[0] if candidates else None
        return choose_model(candidates, await self.available_models())

    async def open_stream(
        self, aven_model: str, model: str, system: str, messages: list[dict], max_tokens: int
    ) -> StreamHandle:
        """Send the request. Raises the SDK's APIError before any output if the upstream rejects it."""
        if self.kind == "anthropic":
            return await self._open_anthropic(aven_model, model, system, messages, max_tokens)
        return await self._open_openai(model, system, messages, max_tokens)

    async def _open_anthropic(self, aven_model, model, system, messages, max_tokens) -> StreamHandle:
        params: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system:
            params["system"] = system
        effort = ANTHROPIC_EFFORT.get(aven_model)
        if effort and model in ANTHROPIC_EFFORT_MODELS:
            params["output_config"] = {"effort": effort}
        if model in FALLBACK_MODELS:
            manager = self.client.beta.messages.stream(**params, betas=[FALLBACK_BETA], fallbacks="default")
        else:
            manager = self.client.messages.stream(**params)
        stream = await manager.__aenter__()
        handle = StreamHandle(texts=None, close=lambda: manager.__aexit__(None, None, None))

        async def texts() -> AsyncIterator[str]:
            async for event in stream:
                if event.type == "text":
                    yield event.text
            final = await stream.get_final_message()
            handle.finish_reason = ANTHROPIC_FINISH.get(final.stop_reason or "", "stop")

        handle.texts = texts()
        return handle

    async def _open_openai(self, model, system, messages, max_tokens) -> StreamHandle:
        full = ([{"role": "system", "content": system}] if system else []) + messages
        stream = await self.client.chat.completions.create(
            model=model, messages=full, max_tokens=max_tokens, stream=True
        )
        handle = StreamHandle(texts=None, close=stream.close)

        async def texts() -> AsyncIterator[str]:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.delta is not None and choice.delta.content:
                    yield choice.delta.content
                if choice.finish_reason:
                    handle.finish_reason = (
                        "length"
                        if choice.finish_reason == "length"
                        else ("content_filter" if choice.finish_reason == "content_filter" else "stop")
                    )

        handle.texts = texts()
        return handle


def make_client(service: ServiceInfo, api_key: str, base_url: str, timeout: float):
    if service.kind == "anthropic":
        return anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=2)
    return openai.AsyncOpenAI(api_key=api_key, base_url=base_url or service.base_url, timeout=timeout, max_retries=2)


UPSTREAM_ERRORS = (anthropic.APIError, openai.APIError)


def map_upstream_error(exc: Exception) -> tuple[int, str, str]:
    """Translate SDK errors into safe client-facing errors (never leak the server key)."""
    sdk = anthropic if isinstance(exc, anthropic.APIError) else openai
    if isinstance(exc, (sdk.AuthenticationError, sdk.PermissionDeniedError)):
        log.error("Upstream rejected the server credentials (%s)", type(exc).__name__)
        return 503, "AVEN Cloud is temporarily unavailable. Please try again later.", "server_error"
    if isinstance(exc, sdk.RateLimitError):
        return 429, "AVEN Cloud is very busy right now. Please wait a moment and try again.", "rate_limit_error"
    if isinstance(exc, sdk.NotFoundError):
        log.error("Upstream model not found - check the model mapping")
        return 503, "This AVEN model is temporarily unavailable.", "server_error"
    if isinstance(exc, sdk.BadRequestError):
        return 400, f"The request was rejected: {exc.message}", "invalid_request_error"
    if isinstance(exc, sdk.APITimeoutError):
        return 504, "The reply took too long. Please try again.", "server_error"
    if isinstance(exc, sdk.APIConnectionError):
        return 503, "AVEN Cloud could not reach the AI service. Please try again.", "server_error"
    if isinstance(exc, sdk.APIStatusError) and exc.status_code >= 500:
        return 503, "The AI service is temporarily unavailable. Please try again shortly.", "server_error"
    log.exception("Unexpected upstream error")
    return 500, "Unexpected server error.", "server_error"
