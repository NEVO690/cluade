"""AVEN Local provider: chats with an open-source model running on this computer."""

from __future__ import annotations

from collections.abc import Iterator

from app.ai import errors
from app.ai.base_provider import AIProvider, ChatRequest, StreamEvent
from app.ai.openai_provider import OpenAIProvider
from app.config.aven_models import aven_model_name
from app.local.downloader import is_downloaded, model_path
from app.local.engine import EngineError, LocalEngine
from app.local.models import LOCAL_MODELS, sampling

# Replies are kept short enough to fit the local context window next to the history.
LOCAL_MAX_TOKENS = 4096


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

    def stream_chat(self, request: ChatRequest) -> Iterator[StreamEvent]:
        aven_model = request.model
        local = LOCAL_MODELS.get(aven_model)
        if local is None:
            raise errors.ModelNotFoundError(f"{aven_model_name(aven_model)} is not available on this computer.")
        if not is_downloaded(local.file):
            raise ModelNotDownloadedError(aven_model)
        try:
            base_url = self.engine.ensure(model_path(local.file))
        except EngineError as exc:
            raise errors.ProviderError(str(exc)) from exc
        if request.cancel_event.is_set():
            return

        client = OpenAIProvider(
            self.engine.token,
            base_url=base_url,
            timeout=self.timeout,
            display_name="AVEN Local",
            # Qwen3: turn "thinking mode" on or off for this AVEN model, with the matching
            # recommended sampling settings.
            extra_body={"chat_template_kwargs": {"enable_thinking": local.thinking}, **sampling(local.thinking)},
        )
        local_request = ChatRequest(
            model=local.file.key,
            system_prompt=request.system_prompt,
            messages=request.messages,
            max_tokens=min(request.max_tokens, LOCAL_MAX_TOKENS),
            cancel_event=request.cancel_event,
        )
        think = ThinkFilter()
        yield StreamEvent("model", aven_model)
        for event in client.stream_chat(local_request):
            if event.kind == "text":
                text = think.feed(event.text)
                if text:
                    yield StreamEvent("text", text)
            elif event.kind != "model":
                yield event
        rest = think.flush()
        if rest:
            yield StreamEvent("text", rest)

    def list_models(self) -> list[str]:
        return list(LOCAL_MODELS)

    def test_connection(self, model: str) -> str:
        local = LOCAL_MODELS.get(model)
        if local is None or not is_downloaded(local.file):
            raise ModelNotDownloadedError(model if local else "aven-light")
        return super().test_connection(model)
