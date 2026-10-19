"""AVEN Local provider: chats with an open-source model running on this computer."""

from __future__ import annotations

from collections.abc import Iterator

from app.ai import errors
from app.ai.base_provider import AIProvider, ChatMessage, ChatRequest, StreamEvent
from app.ai.openai_provider import OpenAIProvider
from app.config.aven_models import aven_model_name
from app.local.downloader import is_downloaded, model_path
from app.local.engine import EngineError, LocalEngine
from app.local.models import LOCAL_MODELS, sampling
from app.local.script_guard import reply_grammar

# Room kept free in the context window for chat-template tokens around each message.
TEMPLATE_TOKENS_PER_MESSAGE = 8
MIN_REPLY_TOKENS = 1024


class ModelNotDownloadedError(errors.AIError):
    title = "Download needed"
    retryable = False

    def __init__(self, aven_model: str) -> None:
        local = LOCAL_MODELS[aven_model]
        super().__init__(
            f"{aven_model_name(aven_model)} runs on this computer and needs a one-time download "
            f"({local.file.size_text})."
        )
        self.aven_model = aven_model


class ThinkingTooLongError(errors.AIError):
    title = "No answer yet"
    retryable = True

    def __init__(self, aven_model: str) -> None:
        super().__init__(
            f"{aven_model_name(aven_model)} used its whole thinking budget before writing an answer. "
            "Try a more specific question, split the task into smaller steps, or use AVEN 1.1 for a "
            "faster, direct answer."
        )


class ContextTooLongError(errors.AIError):
    title = "Message too long"
    retryable = False


def estimate_tokens(text: str) -> int:
    """Rough upper estimate when the engine cannot count (Hebrew needs more tokens per character)."""
    return len(text) // 2 + 1


def fit_messages(
    messages: list[ChatMessage], system_tokens: int, context: int, max_output: int, count
) -> tuple[list[ChatMessage], int]:
    """Keep the newest messages that fit the context window; returns (messages, reply budget).

    ``count`` returns a message's token count. The reply budget shrinks (down to
    MIN_REPLY_TOKENS) before the latest message is dropped.
    """
    available = context - system_tokens - TEMPLATE_TOKENS_PER_MESSAGE
    sizes = [count(m.content) + TEMPLATE_TOKENS_PER_MESSAGE for m in messages]
    latest = sizes[-1] if sizes else 0
    if available - latest < MIN_REPLY_TOKENS:
        raise ContextTooLongError(
            "This message is too long for the on-device model's memory. Shorten it, or split it into parts."
        )
    reply_budget = min(max_output, available - latest)
    kept: list[ChatMessage] = []
    used = 0
    for message, size in zip(reversed(messages), reversed(sizes), strict=True):
        if kept and used + size > available - reply_budget:
            break
        kept.append(message)
        used += size
    kept.reverse()
    while kept and kept[0].role != "user":
        kept.pop(0)
    return kept, reply_budget


class ThinkFilter:
    """Hides <think>…</think> reasoning if the engine passes it through as normal text."""

    def __init__(self) -> None:
        self.buffer = ""
        self.inside = False
        self.skip_whitespace = False  # drop the blank lines that follow </think>

    def feed(self, text: str) -> str:
        out = self._feed(text)
        if self.skip_whitespace:
            stripped = out.lstrip()
            if stripped:
                self.skip_whitespace = False
            return stripped
        return out

    def _feed(self, text: str) -> str:
        self.buffer += text
        out = []
        while self.buffer:
            if self.inside:
                end = self.buffer.find("</think>")
                if end < 0:
                    self.buffer = self.buffer[-len("</think>") :]  # keep a possible partial tag
                    return "".join(out)
                self.buffer = self.buffer[end + len("</think>") :]
                self.inside = False
                if not "".join(out).strip():
                    self.skip_whitespace = True
                continue
            start = self.buffer.find("<think>")
            if start >= 0:
                out.append(self.buffer[:start])
                self.buffer = self.buffer[start + len("<think>") :]
                self.inside = True
                continue
            # Hold back a trailing partial "<think" so it is not emitted as text.
            keep = next((i for i in range(1, len("<think>")) if "<think>".startswith(self.buffer[-i:])), 0)
            out.append(self.buffer[: len(self.buffer) - keep] if keep else self.buffer)
            self.buffer = self.buffer[len(self.buffer) - keep :] if keep else ""
            break
        return "".join(out)

    def flush(self) -> str:
        rest, self.buffer = ("" if self.inside else self.buffer), ""
        return rest


class LocalProvider(AIProvider):
    provider_id = "aven_local"
    display_name = "AVEN Local"

    def __init__(self, engine: LocalEngine, *, timeout: float = 600.0) -> None:
        self.engine = engine
        self.timeout = timeout
        self._token_cache: dict[str, int] = {}

    def stream_chat(self, request: ChatRequest) -> Iterator[StreamEvent]:
        aven_model = request.model
        local = LOCAL_MODELS.get(aven_model)
        if local is None:
            raise errors.ModelNotFoundError(f"{aven_model_name(aven_model)} is not available on this computer.")
        if not is_downloaded(local.file):
            raise ModelNotDownloadedError(aven_model)
        try:
            base_url = self.engine.ensure(model_path(local.file), local.file.context)
        except EngineError as exc:
            raise errors.ProviderError(str(exc)) from exc
        if request.cancel_event.is_set():
            return
        messages, reply_budget = fit_messages(
            request.messages,
            self._count(request.system_prompt),
            local.file.context,
            min(request.max_tokens, local.max_output),
            self._count,
        )

        # Qwen3: turn "thinking mode" on or off for this AVEN model, with the matching
        # recommended sampling settings.
        extra_body: dict = {"chat_template_kwargs": {"enable_thinking": local.thinking}, **sampling(local.thinking)}
        # Keep the reply in the conversation's writing systems (no stray Chinese, Cyrillic…).
        grammar = reply_grammar([m.content for m in messages], messages[-1].content)
        if grammar:
            extra_body["grammar"] = grammar
        client = OpenAIProvider(
            self.engine.token, base_url=base_url, timeout=self.timeout, display_name="AVEN Local", extra_body=extra_body
        )
        local_request = ChatRequest(
            model=local.file.key,
            system_prompt=request.system_prompt,
            messages=messages,
            max_tokens=reply_budget,
            cancel_event=request.cancel_event,
        )
        think = ThinkFilter()
        answered = False
        yield StreamEvent("model", aven_model)
        for event in client.stream_chat(local_request):
            if event.kind == "text":
                text = think.feed(event.text)
                if text:
                    answered = answered or bool(text.strip())
                    yield StreamEvent("text", text)
            elif event.kind == "truncated" and local.thinking and not answered:
                raise ThinkingTooLongError(aven_model)
            elif event.kind != "model":
                yield event
        rest = think.flush()
        if rest:
            yield StreamEvent("text", rest)

    def _count(self, text: str) -> int:
        """Tokens in ``text`` (exact from the engine, cached; estimated if the engine can't say)."""
        cached = self._token_cache.get(text)
        if cached is not None:
            return cached
        count = self.engine.count_tokens(text)
        if count is None:
            return estimate_tokens(text)
        if len(self._token_cache) > 512:
            self._token_cache.clear()
        self._token_cache[text] = count
        return count

    def list_models(self) -> list[str]:
        return list(LOCAL_MODELS)

    def test_connection(self, model: str) -> str:
        local = LOCAL_MODELS.get(model)
        if local is None or not is_downloaded(local.file):
            raise ModelNotDownloadedError(model if local else "aven-light")
        return super().test_connection(model)
