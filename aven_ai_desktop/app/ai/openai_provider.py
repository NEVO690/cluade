"""OpenAI provider using the official ``openai`` Python SDK (Chat Completions).

A custom base URL makes this provider work with OpenAI-compatible servers,
including local model servers on ``localhost``.
"""

from __future__ import annotations

from collections.abc import Iterator

import openai

from app.ai import errors
from app.ai.base_provider import AIProvider, ChatRequest, StreamEvent

# Placeholder for local OpenAI-compatible servers that do not check keys.
LOCAL_SERVER_KEY = "not-required"


class OpenAIProvider(AIProvider):
    provider_id = "openai"
    display_name = "OpenAI"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "",
        timeout: float = 600.0,
        client: openai.OpenAI | None = None,
    ) -> None:
        self.base_url = base_url
        if base_url:
            self.display_name = "OpenAI-compatible server"
        self.client = client or openai.OpenAI(
            api_key=api_key or LOCAL_SERVER_KEY,
            base_url=base_url or None,
            timeout=timeout,
            max_retries=2,
        )

    def stream_chat(self, request: ChatRequest) -> Iterator[StreamEvent]:
        messages = [{"role": "system", "content": request.system_prompt}]
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        # The official API uses max_completion_tokens; many compatible servers only know max_tokens.
        limit = {"max_tokens" if self.base_url else "max_completion_tokens": request.max_tokens}
        try:
            stream = self.client.chat.completions.create(model=request.model, messages=messages, stream=True, **limit)
            model_reported = False
            finish_reason = None
            try:
                for chunk in stream:
                    if request.cancel_event.is_set():
                        return
                    if not model_reported and getattr(chunk, "model", None):
                        model_reported = True
                        yield StreamEvent("model", chunk.model)
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.delta is not None and choice.delta.content:
                        yield StreamEvent("text", choice.delta.content)
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
            finally:
                stream.close()
        except openai.APIError as exc:
            raise map_openai_error(exc, request.model, self.display_name) from exc

        if finish_reason == "content_filter":
            raise errors.ContentRefusedError("The provider's content filter blocked this response.")
        if finish_reason == "length":
            yield StreamEvent("truncated", "")

    def list_models(self) -> list[str]:
        try:
            return sorted({m.id for m in self.client.models.list()})
        except openai.APIError as exc:
            raise map_openai_error(exc, "", self.display_name) from exc


def map_openai_error(exc: Exception, model: str, name: str = "OpenAI") -> errors.AIError:
    if isinstance(exc, openai.AuthenticationError):
        return errors.AuthenticationFailedError(
            f"{name} rejected the API key. Check the key in Settings → AI Provider."
        )
    if isinstance(exc, openai.PermissionDeniedError):
        return errors.PermissionDeniedError(f"Your {name} API key does not have permission for this request or model.")
    if isinstance(exc, openai.NotFoundError):
        return errors.ModelNotFoundError(
            f"The model “{model}” was not found or is not available to your account. "
            "Choose a different model in Settings."
            if model
            else "The requested resource was not found."
        )
    if isinstance(exc, openai.RateLimitError):
        return errors.RateLimitedError(f"{name} rate limit or quota reached. Wait a moment, then retry.")
    if isinstance(exc, openai.BadRequestError):
        return errors.InvalidRequestError(f"{name} rejected the request: {exc.message}")
    if isinstance(exc, openai.APITimeoutError):
        return errors.ProviderTimeoutError(
            f"The request to {name} timed out. Check your connection or increase the timeout in Settings."
        )
    if isinstance(exc, openai.APIConnectionError):
        return errors.NetworkError(f"Could not reach {name}. Check your internet connection and retry.")
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code >= 500:
            return errors.ProviderOverloadedError(
                f"{name} is temporarily unavailable (HTTP {exc.status_code}). Please retry shortly."
            )
        return errors.ProviderError(f"{name} returned an error (HTTP {exc.status_code}): {exc.message}")
    return errors.ProviderError(f"Unexpected error from {name}: {type(exc).__name__}")
