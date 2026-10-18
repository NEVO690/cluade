"""Provider tests that drive the real SDKs against a mocked HTTP transport.

No network access or API key is needed: requests are answered by
``httpx2.MockTransport`` with responses shaped like the providers' documented
streaming formats.
"""

from __future__ import annotations

import json

import anthropic
import httpx2
import openai
import pytest

from app.ai import errors
from app.ai.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from app.ai.base_provider import ChatMessage, ChatRequest
from app.ai.openai_provider import OpenAIProvider
from app.ai.provider_factory import create_provider, key_required


def sse(events: list[tuple[str | None, dict | str]]) -> bytes:
    lines = []
    for name, data in events:
        if name:
            lines.append(f"event: {name}")
        lines.append(f"data: {data if isinstance(data, str) else json.dumps(data)}")
        lines.append("")
    return ("\n".join(lines) + "\n").encode()


def anthropic_stream(text_parts: list[str], stop_reason: str = "end_turn", model: str = "claude-opus-5-5") -> bytes:
    events: list[tuple[str | None, dict | str]] = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            },
        ),
        (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        ),
    ]
    for part in text_parts:
        events.append(
            (
                "content_block_delta",
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": part}},
            )
        )
    events += [
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 5},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return sse(events)


def make_anthropic(handler) -> AnthropicProvider:
    client = anthropic.Anthropic(
        api_key="sk-ant-test",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicProvider("unused", client=client)


def make_openai(handler, base_url: str = "") -> OpenAIProvider:
    client = openai.OpenAI(
        api_key="sk-test",
        base_url=base_url or None,
        max_retries=0,
        http_client=openai.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return OpenAIProvider("unused", base_url=base_url, client=client)


def request_for(model: str = "claude-opus-5-5") -> ChatRequest:
    return ChatRequest(model=model, system_prompt="SYSTEM", messages=[ChatMessage("user", "Hi")], max_tokens=1000)


def collect(provider, request) -> tuple[str, list[str]]:
    text, kinds = [], []
    for event in provider.stream_chat(request):
        kinds.append(event.kind)
        if event.kind == "text":
            text.append(event.text)
    return "".join(text), kinds


SSE_HEADERS = {"content-type": "text/event-stream"}

# --- Anthropic ----------------------------------------------------------------------------


def test_anthropic_streams_text_and_uses_refusal_fallback_on_supported_models() -> None:
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta", "")
        seen["key"] = request.headers.get("x-api-key")
        return httpx2.Response(200, headers=SSE_HEADERS, content=anthropic_stream(["Hel", "lo!"]))

    text, kinds = collect(make_anthropic(handler), request_for("claude-opus-5-5"))
    assert text == "Hello!"
    assert kinds[0] == "model"
    assert seen["body"]["system"] == "SYSTEM"
    assert seen["body"]["messages"] == [{"role": "user", "content": "Hi"}]
    assert seen["body"]["max_tokens"] == 1000
    assert seen["body"]["fallbacks"] == "default"
    assert FALLBACK_BETA in seen["beta"]
    assert seen["key"] == "sk-ant-test"


def test_anthropic_plain_request_for_other_models() -> None:
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta", "")
        return httpx2.Response(200, headers=SSE_HEADERS, content=anthropic_stream(["ok"], model="claude-haiku-4-5"))

    text, _ = collect(make_anthropic(handler), request_for("claude-haiku-4-5"))
    assert text == "ok"
    assert "fallbacks" not in seen["body"]
    assert FALLBACK_BETA not in seen["beta"]


def test_anthropic_retries_without_fallback_when_beta_rejected() -> None:
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        calls.append("fallbacks" in body)
        if "fallbacks" in body:
            return httpx2.Response(
                400,
                json={
                    "type": "error",
                    "error": {
                        "type": "invalid_request_error",
                        "message": "fallbacks is not enabled for this organization",
                    },
                },
            )
        return httpx2.Response(200, headers=SSE_HEADERS, content=anthropic_stream(["fine"]))

    text, _ = collect(make_anthropic(handler), request_for())
    assert text == "fine"
    assert calls == [True, False]


def test_anthropic_refusal_raises_content_refused() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers=SSE_HEADERS, content=anthropic_stream(["partial"], stop_reason="refusal"))

    with pytest.raises(errors.ContentRefusedError):
        collect(make_anthropic(handler), request_for())


def test_anthropic_max_tokens_reports_truncation() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers=SSE_HEADERS, content=anthropic_stream(["long"], stop_reason="max_tokens"))

    _, kinds = collect(make_anthropic(handler), request_for())
    assert kinds[-1] == "truncated"


def test_anthropic_cancellation_stops_stream() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers=SSE_HEADERS, content=anthropic_stream(["a", "b", "c", "d"]))

    request = request_for()
    received = []
    for event in make_anthropic(handler).stream_chat(request):
        if event.kind == "text":
            received.append(event.text)
            request.cancel_event.set()
    assert received == ["a"]


@pytest.mark.parametrize(
    ("status", "error_type", "expected"),
    [
        (401, "authentication_error", errors.AuthenticationFailedError),
        (403, "permission_error", errors.PermissionDeniedError),
        (404, "not_found_error", errors.ModelNotFoundError),
        (429, "rate_limit_error", errors.RateLimitedError),
        (400, "invalid_request_error", errors.InvalidRequestError),
        (529, "overloaded_error", errors.ProviderOverloadedError),
        (500, "api_error", errors.ProviderOverloadedError),
    ],
)
def test_anthropic_http_errors_are_mapped(status, error_type, expected) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json={"type": "error", "error": {"type": error_type, "message": "nope"}})

    with pytest.raises(expected) as info:
        collect(make_anthropic(handler), request_for("claude-haiku-4-5"))
    assert "sk-ant-test" not in info.value.user_message


def test_anthropic_network_and_timeout_errors_are_mapped() -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(errors.NetworkError):
        collect(make_anthropic(refuse), request_for())

    def slow(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    with pytest.raises(errors.ProviderTimeoutError):
        collect(make_anthropic(slow), request_for())


def test_anthropic_list_models() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/v1/models")
        return httpx2.Response(
            200,
            json={
                "data": [
                    {
                        "type": "model",
                        "id": "claude-sonnet-5-5",
                        "display_name": "Sonnet",
                        "created_at": "2026-01-01T00:00:00Z",
                    },
                    {
                        "type": "model",
                        "id": "claude-opus-5-5",
                        "display_name": "Opus",
                        "created_at": "2026-01-01T00:00:00Z",
                    },
                ],
                "has_more": False,
                "first_id": "claude-sonnet-5-5",
                "last_id": "claude-opus-5-5",
            },
        )

    assert make_anthropic(handler).list_models() == ["claude-opus-5-5", "claude-sonnet-5-5"]


# --- OpenAI -------------------------------------------------------------------------------


def openai_chunks(parts: list[str], finish: str = "stop", model: str = "gpt-test") -> bytes:
    events: list[tuple[str | None, dict | str]] = []
    for i, part in enumerate(parts):
        events.append(
            (
                None,
                {
                    "id": "c1",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": part} if i == 0 else {"content": part},
                            "finish_reason": None,
                        }
                    ],
                },
            )
        )
    events.append(
        (
            None,
            {
                "id": "c1",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
            },
        )
    )
    events.append((None, "[DONE]"))
    return sse(events)


def test_openai_streams_and_sends_system_prompt() -> None:
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, headers=SSE_HEADERS, content=openai_chunks(["Hel", "lo"]))

    text, kinds = collect(make_openai(handler), request_for("gpt-test"))
    assert text == "Hello"
    assert kinds[0] == "model"
    assert seen["url"].startswith("https://")
    assert seen["body"]["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert seen["body"]["max_completion_tokens"] == 1000
    assert seen["body"]["stream"] is True


def test_openai_compatible_server_uses_base_url_and_max_tokens() -> None:
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, headers=SSE_HEADERS, content=openai_chunks(["x"], finish="length"))

    _, kinds = collect(make_openai(handler, base_url="http://localhost:11434/v1"), request_for("llama"))
    assert seen["url"].startswith("http://localhost:11434/v1/chat/completions")
    assert seen["body"]["max_tokens"] == 1000
    assert kinds[-1] == "truncated"


def test_openai_content_filter_is_reported() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers=SSE_HEADERS, content=openai_chunks(["x"], finish="content_filter"))

    with pytest.raises(errors.ContentRefusedError):
        collect(make_openai(handler), request_for("gpt-test"))


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, errors.AuthenticationFailedError),
        (404, errors.ModelNotFoundError),
        (429, errors.RateLimitedError),
        (503, errors.ProviderOverloadedError),
    ],
)
def test_openai_http_errors_are_mapped(status, expected) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json={"error": {"message": "nope", "type": "x", "code": None}})

    with pytest.raises(expected):
        collect(make_openai(handler), request_for("gpt-test"))


# --- factory ------------------------------------------------------------------------------


def test_factory_requires_key_except_for_local_servers() -> None:
    with pytest.raises(errors.MissingCredentialsError) as info:
        create_provider("anthropic", None)
    assert "ANTHROPIC_API_KEY" in info.value.user_message
    with pytest.raises(errors.MissingCredentialsError):
        create_provider("openai", "", base_url="https://api.example.com/v1")
    assert not key_required("openai", "http://localhost:8080/v1")
    assert isinstance(create_provider("openai", None, base_url="http://localhost:8080/v1"), OpenAIProvider)
    assert isinstance(create_provider("anthropic", "sk-ant-x"), AnthropicProvider)
    with pytest.raises(errors.ProviderError):
        create_provider("unknown", "key")
