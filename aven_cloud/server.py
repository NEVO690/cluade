"""AVEN Cloud - the AVEN AI server that lets people chat without an API key.

The AVEN AI Desktop app sends chats here. This server holds the AI service key
(in an environment variable, never in the app), maps the AVEN models to the
service's models and streams replies back using the OpenAI-compatible
``/v1/chat/completions`` format the app already understands.

Free setup:  GROQ_API_KEY=... uvicorn server:app --port 8000
See backends.py for the supported services.
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

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from backends import AVEN_MODEL_IDS, SERVICES, UPSTREAM_ERRORS, Backend, make_client, map_upstream_error

log = logging.getLogger("aven_cloud")

AVEN_MODELS = {
    "aven-1": "AVEN 1.0",
    "aven-ultra": "AVEN Ultra",
    "aven-core": "AVEN Core",
    "aven-light": "AVEN Light",
}
assert tuple(AVEN_MODELS) == AVEN_MODEL_IDS


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def detect_service() -> str:
    explicit = os.environ.get("AVEN_UPSTREAM", "").strip().lower()
    if explicit in SERVICES:
        return explicit
    for service_id in ("anthropic", "groq", "gemini"):
        if os.environ.get(SERVICES[service_id].key_env, "").strip():
            return service_id
    return "groq"


@dataclass
class Config:
    service: str = "groq"
    api_key: str = ""
    base_url: str = ""  # only needed for "openai_compatible"
    overrides: dict[str, str] = field(default_factory=dict)  # AVEN model -> exact upstream model
    max_output_tokens: int = 8_000
    max_input_chars: int = 400_000
    requests_per_minute: int = 10  # per install
    requests_per_day: int = 100  # per install
    ip_requests_per_minute: int = 30  # per IP address
    max_concurrent: int = 10
    trust_proxy: bool = False  # read the client IP from X-Forwarded-For (only behind a trusted proxy)
    request_timeout: float = 600.0

    @classmethod
    def from_env(cls) -> Config:
        service = detect_service()
        config = cls(
            service=service,
            api_key=os.environ.get(SERVICES[service].key_env, "").strip(),
            base_url=os.environ.get("AVEN_UPSTREAM_BASE_URL", "").strip(),
            max_output_tokens=_env_int("AVEN_MAX_OUTPUT_TOKENS", 8_000),
            max_input_chars=_env_int("AVEN_MAX_INPUT_CHARS", 400_000),
            requests_per_minute=_env_int("AVEN_REQUESTS_PER_MINUTE", 10),
            requests_per_day=_env_int("AVEN_REQUESTS_PER_DAY", 100),
            ip_requests_per_minute=_env_int("AVEN_IP_REQUESTS_PER_MINUTE", 30),
            max_concurrent=_env_int("AVEN_MAX_CONCURRENT", 10),
            trust_proxy=os.environ.get("AVEN_TRUST_PROXY", "").lower() in ("1", "true", "yes"),
        )
        for model_id in AVEN_MODELS:
            override = os.environ.get(model_id.upper().replace("-", "_") + "_MODEL", "").strip()  # AVEN_1_MODEL
            if override:
                config.overrides[model_id] = override
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


def create_app(config: Config | None = None, client=None) -> FastAPI:
    """Build the app. ``client`` (an Anthropic or OpenAI async client) is injectable for tests."""
    config = config or Config.from_env()
    service = SERVICES[config.service]
    if client is None and config.api_key:
        client = make_client(service, config.api_key, config.base_url, config.request_timeout)
    backend = Backend(service, client, dict(config.overrides)) if client is not None else None
    limiter = RateLimiter()
    semaphore = asyncio.Semaphore(max(1, config.max_concurrent))
    app = FastAPI(title="AVEN Cloud", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "configured": backend is not None, "service": config.service}

    @app.get("/v1/models")
    async def list_models() -> dict:
        return {
            "object": "list",
            "data": [{"id": mid, "object": "model", "created": 0, "owned_by": "aven-ai"} for mid in AVEN_MODELS],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        if backend is None:
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

        upstream_model = await backend.resolve(parsed.aven_model)
        if not upstream_model:
            log.error("No upstream model available for %s", parsed.aven_model)
            return error_response(503, "This AVEN model is temporarily unavailable.", "server_error")

        await semaphore.acquire()
        try:
            # Opening the stream sends the request, so upstream errors become proper HTTP statuses.
            handle = await backend.open_stream(
                parsed.aven_model, upstream_model, parsed.system, parsed.messages, parsed.max_tokens
            )
        except UPSTREAM_ERRORS as exc:
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
                await handle.close()
            finally:
                semaphore.release()

        log.info("chat model=%s client=%s", parsed.aven_model, short_hash(install_id))
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())

        async def events() -> AsyncIterator[str]:
            try:
                yield chunk(completion_id, parsed.aven_model, created, {"role": "assistant", "content": ""})
                async for text in handle.texts:
                    yield chunk(completion_id, parsed.aven_model, created, {"content": text})
                yield chunk(completion_id, parsed.aven_model, created, {}, handle.finish_reason)
                yield "data: [DONE]\n\n"
            except UPSTREAM_ERRORS as exc:
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
