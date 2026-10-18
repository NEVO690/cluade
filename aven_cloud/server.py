"""AVEN Cloud - the AVEN AI server that lets people chat without an API key.

The AVEN AI Desktop app sends chats here; this server holds the Anthropic API
key (in an environment variable, never in the app), maps the AVEN models to
Claude models and streams replies back using the OpenAI-compatible
``/v1/chat/completions`` format the app already understands.

Run locally:  ANTHROPIC_API_KEY=... uvicorn server:app --port 8000
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import anthropic
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

log = logging.getLogger("aven_cloud")

# --- AVEN models ------------------------------------------------------------------------

AVEN_MODELS = {
    "aven-1": "AVEN 1.0",
    "aven-ultra": "AVEN Ultra",
    "aven-core": "AVEN Core",
    "aven-light": "AVEN Light",
}
DEFAULT_MAPPING = {
    "aven-1": "claude-opus-5-5",
    "aven-ultra": "claude-opus-5-5",
    "aven-core": "claude-sonnet-5-5",
    "aven-light": "claude-haiku-5-5",
}
# AVEN Ultra runs the same model as AVEN 1.0 but reasons more deeply.
DEFAULT_EFFORT = {"aven-ultra": "xhigh"}
EFFORT_MODELS = frozenset(
    {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-haiku-5-5"}
)
# Server-side refusal fallback: if a model declines on policy grounds, Anthropic
# answers with a recommended fallback model inside the same stream.
FALLBACK_MODELS = frozenset({"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Config:
    anthropic_api_key: str = ""
    mapping: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MAPPING))
    effort: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_EFFORT))
    max_output_tokens: int = 16_000
    max_input_chars: int = 400_000
    requests_per_minute: int = 20  # per install
    requests_per_day: int = 300  # per install
    ip_requests_per_minute: int = 60  # per IP address
    max_concurrent: int = 20
    trust_proxy: bool = False  # read the client IP from X-Forwarded-For (only behind a trusted proxy)
    request_timeout: float = 600.0

    @classmethod
    def from_env(cls) -> Config:
        config = cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            max_output_tokens=_env_int("AVEN_MAX_OUTPUT_TOKENS", 16_000),
            max_input_chars=_env_int("AVEN_MAX_INPUT_CHARS", 400_000),
            requests_per_minute=_env_int("AVEN_REQUESTS_PER_MINUTE", 20),
            requests_per_day=_env_int("AVEN_REQUESTS_PER_DAY", 300),
            ip_requests_per_minute=_env_int("AVEN_IP_REQUESTS_PER_MINUTE", 60),
            max_concurrent=_env_int("AVEN_MAX_CONCURRENT", 20),
            trust_proxy=os.environ.get("AVEN_TRUST_PROXY", "").lower() in ("1", "true", "yes"),
        )
        for model_id in AVEN_MODELS:
            override = os.environ.get(model_id.upper().replace("-", "_") + "_MODEL", "").strip()  # AVEN_1_MODEL
            if override:
                config.mapping[model_id] = override
        return config


# --- fair-use limits -----------------------------------------------------------------------


class RateLimiter:
    """In-memory sliding-window limits (per process; run a single instance)."""

    def __init__(self) -> None:
        self.events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float, now: float | None = None) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic() if now is None else now
        bucket = self.events[key]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


# --- helpers -------------------------------------------------------------------------------


def error_response(status: int, message: str, error_type: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": error_type, "code": None}}, status_code=status)


def map_upstream_error(exc: Exception) -> tuple[int, str, str]:
    """Translate Anthropic errors into safe client-facing errors (never leak the server key)."""
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        log.error("Upstream rejected the server credentials (%s)", type(exc).__name__)
        return 503, "AVEN Cloud is temporarily unavailable. Please try again later.", "server_error"
    if isinstance(exc, anthropic.RateLimitError):
        return 429, "AVEN Cloud is very busy right now. Please wait a moment and try again.", "rate_limit_error"
    if isinstance(exc, anthropic.NotFoundError):
        log.error("Upstream model not found - check the model mapping")
        return 503, "This AVEN model is temporarily unavailable.", "server_error"
    if isinstance(exc, anthropic.BadRequestError):
        return 400, f"The request was rejected: {exc.message}", "invalid_request_error"
    if isinstance(exc, anthropic.APITimeoutError):
        return 504, "The reply took too long. Please try again.", "server_error"
    if isinstance(exc, anthropic.APIConnectionError):
        return 503, "AVEN Cloud could not reach the AI service. Please try again.", "server_error"
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return 503, "The AI service is temporarily unavailable. Please try again shortly.", "server_error"
    log.exception("Unexpected upstream error")
    return 500, "Unexpected server error.", "server_error"


def client_identity(request: Request, trust_proxy: bool) -> tuple[str, str]:
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    token = "".join(ch for ch in token if ch.isalnum() or ch in "-_")[:64] or "anonymous"
    ip = request.client.host if request.client else "unknown"
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            ip = forwarded.split(",")[0].strip() or ip
    return token, ip


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:10]


@dataclass
class ParsedRequest:
    aven_model: str
    system: str
    messages: list[dict]
    max_tokens: int
    stream: bool


def parse_chat_request(body: object, config: Config) -> ParsedRequest | JSONResponse:
    if not isinstance(body, dict):
        return error_response(400, "The request body must be a JSON object.", "invalid_request_error")
    aven_model = body.get("model")
    if aven_model not in AVEN_MODELS:
        names = ", ".join(AVEN_MODELS)
        return error_response(404, f"Unknown model. Available models: {names}.", "invalid_request_error")
    raw_messages = body.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        return error_response(400, "messages must be a non-empty list.", "invalid_request_error")

    system_parts: list[str] = []
    messages: list[dict] = []
    total = 0
    for item in raw_messages:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            return error_response(400, "Each message needs a role and text content.", "invalid_request_error")
        role, content = item.get("role"), item["content"]
        total += len(content)
        if role in ("system", "developer"):
            system_parts.append(content)
        elif role in ("user", "assistant"):
            if content.strip():
                messages.append({"role": role, "content": content})
        else:
            return error_response(400, f"Unsupported message role: {role!r}.", "invalid_request_error")
    if total > config.max_input_chars:
        return error_response(413, "The conversation is too long. Start a new conversation.", "invalid_request_error")
    if not messages or messages[0]["role"] != "user" or messages[-1]["role"] != "user":
        return error_response(400, "The conversation must start and end with a user message.", "invalid_request_error")

    requested = body.get("max_completion_tokens") or body.get("max_tokens") or config.max_output_tokens
    try:
        max_tokens = max(1, min(int(requested), config.max_output_tokens))
    except (TypeError, ValueError):
        max_tokens = config.max_output_tokens
    return ParsedRequest(aven_model, "\n\n".join(system_parts), messages, max_tokens, bool(body.get("stream")))


FINISH_REASONS = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length", "refusal": "content_filter"}


def chunk(completion_id: str, model: str, created: int, delta: dict, finish: str | None = None) -> str:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload)}\n\n"


# --- application ---------------------------------------------------------------------------


def create_app(config: Config | None = None, client: anthropic.AsyncAnthropic | None = None) -> FastAPI:
    config = config or Config.from_env()
    if client is None and config.anthropic_api_key:
        client = anthropic.AsyncAnthropic(
            api_key=config.anthropic_api_key, timeout=config.request_timeout, max_retries=2
        )
    limiter = RateLimiter()
    semaphore = asyncio.Semaphore(max(1, config.max_concurrent))
    app = FastAPI(title="AVEN Cloud", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "configured": client is not None}

    @app.get("/v1/models")
    async def list_models() -> dict:
        return {
            "object": "list",
            "data": [{"id": mid, "object": "model", "created": 0, "owned_by": "aven-ai"} for mid in AVEN_MODELS],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        if client is None:
            return error_response(503, "AVEN Cloud is not configured yet.", "server_error")
        install_id, ip = client_identity(request, config.trust_proxy)
        if not (
            limiter.allow(f"ip:{ip}", config.ip_requests_per_minute, 60)
            and limiter.allow(f"min:{install_id}", config.requests_per_minute, 60)
        ):
            return error_response(
                429, "You're sending messages too quickly. Wait a minute and try again.", "rate_limit_error"
            )
        if not limiter.allow(f"day:{install_id}", config.requests_per_day, 86_400):
            return error_response(
                429,
                "You've reached today's free message limit for AVEN Cloud. Please come back tomorrow.",
                "rate_limit_error",
            )
        try:
            body = await request.json()
        except ValueError:
            return error_response(400, "Invalid JSON.", "invalid_request_error")
        parsed = parse_chat_request(body, config)
        if isinstance(parsed, JSONResponse):
            return parsed

        upstream_model = config.mapping[parsed.aven_model]
        params: dict = {
            "model": upstream_model,
            "max_tokens": parsed.max_tokens,
            "messages": parsed.messages,
        }
        if parsed.system:
            params["system"] = parsed.system
        effort = config.effort.get(parsed.aven_model)
        if effort and upstream_model in EFFORT_MODELS:
            params["output_config"] = {"effort": effort}

        def open_stream():
            if upstream_model in FALLBACK_MODELS:
                return client.beta.messages.stream(**params, betas=[FALLBACK_BETA], fallbacks="default")
            return client.messages.stream(**params)

        await semaphore.acquire()
        manager = open_stream()
        try:
            # Entering the stream sends the request, so upstream errors become proper HTTP statuses.
            stream = await manager.__aenter__()
        except anthropic.APIError as exc:
            semaphore.release()
            status, message, kind = map_upstream_error(exc)
            return error_response(status, message, kind)
        except BaseException:
            semaphore.release()
            raise

        closed = False

        async def cleanup() -> None:
            # Idempotent: runs from the stream's finally block and as a background task, so the
            # upstream stream is closed and the slot released even if the client disconnects early.
            nonlocal closed
            if closed:
                return
            closed = True
            try:
                await manager.__aexit__(None, None, None)
            finally:
                semaphore.release()

        log.info("chat model=%s client=%s", parsed.aven_model, short_hash(install_id))
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())

        async def events() -> AsyncIterator[str]:
            try:
                yield chunk(completion_id, parsed.aven_model, created, {"role": "assistant", "content": ""})
                async for event in stream:
                    if event.type == "text":
                        yield chunk(completion_id, parsed.aven_model, created, {"content": event.text})
                final = await stream.get_final_message()
                finish = FINISH_REASONS.get(final.stop_reason or "", "stop")
                yield chunk(completion_id, parsed.aven_model, created, {}, finish)
                yield "data: [DONE]\n\n"
            except anthropic.APIError as exc:
                _status, message, kind = map_upstream_error(exc)
                yield f"data: {json.dumps({'error': {'message': message, 'type': kind}})}\n\n"
            finally:
                await cleanup()

        if parsed.stream:
            return StreamingResponse(
                events(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                background=BackgroundTask(cleanup),
            )

        # Non-streaming: collect the same events into one response.
        text: list[str] = []
        finish = "stop"
        try:
            async for line in events():
                data = line[6:].strip()
                if data == "[DONE]":
                    continue
                payload = json.loads(data)
                if "error" in payload:
                    return error_response(502, payload["error"]["message"], payload["error"]["type"])
                choice = payload["choices"][0]
                text.append(choice["delta"].get("content", ""))
                finish = choice["finish_reason"] or finish
        finally:
            await cleanup()
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": parsed.aven_model,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "".join(text)}, "finish_reason": finish}
            ],
        }

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
