"""Anthropic (Claude) provider using the official ``anthropic`` Python SDK."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import anthropic

from app.ai import errors
from app.ai.base_provider import AIProvider, ChatRequest, StreamEvent

log = logging.getLogger(__name__)

# Models that accept Anthropic's server-side refusal fallback ("fallbacks": "default").
# When the requested model declines a request for policy reasons, the API re-runs it
# on a recommended fallback model inside the same streamed response.
FALLBACK_MODELS = frozenset({"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Models that accept output_config.effort. Other models never receive it.
EFFORT_MODELS = frozenset(
    {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-haiku-5-5"}
)


class AnthropicProvider(AIProvider):
    provider_id = "anthropic"
    display_name = "Anthropic"

    def __init__(self, api_key: str, *, timeout: float = 600.0, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)

    # --- chat ------------------------------------------------------------------
    def stream_chat(self, request: ChatRequest) -> Iterator[StreamEvent]:
        use_fallbacks = request.model in FALLBACK_MODELS
        try:
            yield from self._stream(request, use_fallbacks)
        except anthropic.BadRequestError as exc:
            # Accounts without access to the fallback beta: retry once without it.
            if use_fallbacks and "fallback" in str(exc.message).lower():
                log.info("Fallback beta rejected; retrying without it")
                try:
                    yield from self._stream(request, False)
                except anthropic.APIError as inner:
                    raise map_anthropic_error(inner, request.model) from inner
                return
            raise map_anthropic_error(exc, request.model) from exc
        except anthropic.APIError as exc:
            raise map_anthropic_error(exc, request.model) from exc

    def _stream(self, request: ChatRequest, use_fallbacks: bool) -> Iterator[StreamEvent]:
        params = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "system": request.system_prompt,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.effort and request.model in EFFORT_MODELS:
            params["output_config"] = {"effort": request.effort}
        if use_fallbacks:
            manager = self.client.beta.messages.stream(**params, betas=[FALLBACK_BETA], fallbacks="default")
        else:
            manager = self.client.messages.stream(**params)

        with manager as stream:
            for event in stream:
                if request.cancel_event.is_set():
                    return  # leaving the context manager closes the connection
                if event.type == "message_start":
                    yield StreamEvent("model", event.message.model)
                elif event.type == "text":
                    yield StreamEvent("text", event.text)
            if request.cancel_event.is_set():
                return
            final = stream.get_final_message()

        if final.stop_reason == "refusal":
            raise errors.ContentRefusedError(
                "The model declined to answer this request. Try rephrasing it, or start a new conversation."
            )
        if final.stop_reason == "max_tokens":
            yield StreamEvent("truncated", "")

    # --- utilities -------------------------------------------------------------
    def list_models(self) -> list[str]:
        try:
            return sorted({m.id for m in self.client.models.list(limit=100)})
        except anthropic.APIError as exc:
            raise map_anthropic_error(exc, "") from exc


def map_anthropic_error(exc: Exception, model: str) -> errors.AIError:
    """Translate SDK exceptions into user-facing errors (no secrets included)."""
    if isinstance(exc, errors.AIError):
        return exc
    if isinstance(exc, anthropic.AuthenticationError):
        return errors.AuthenticationFailedError(
            "Anthropic rejected the API key. Check the key in Settings → AI Provider."
        )
    if isinstance(exc, anthropic.PermissionDeniedError):
        return errors.PermissionDeniedError(
            "Your Anthropic API key does not have permission for this request or model."
        )
    if isinstance(exc, anthropic.NotFoundError):
        return errors.ModelNotFoundError(
            f"The model “{model}” was not found or is not available to your account. "
            "Choose a different model in Settings."
            if model
            else "The requested resource was not found."
        )
    if isinstance(exc, anthropic.RateLimitError):
        return errors.RateLimitedError("Anthropic rate limit reached. Wait a moment, then retry.")
    if isinstance(exc, anthropic.BadRequestError):
        return errors.InvalidRequestError(f"Anthropic rejected the request: {exc.message}")
    if isinstance(exc, anthropic.APITimeoutError):
        return errors.ProviderTimeoutError(
            "The request to Anthropic timed out. Check your connection or increase the timeout in Settings."
        )
    if isinstance(exc, anthropic.APIConnectionError):
        return errors.NetworkError("Could not reach Anthropic. Check your internet connection and retry.")
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code >= 500:
            return errors.ProviderOverloadedError(
                f"Anthropic is temporarily unavailable (HTTP {exc.status_code}). Please retry shortly."
            )
        return errors.ProviderError(f"Anthropic returned an error (HTTP {exc.status_code}): {exc.message}")
    return errors.ProviderError(f"Unexpected error from Anthropic: {type(exc).__name__}")
