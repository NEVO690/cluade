"""AVEN Cloud server tests. Anthropic is mocked at the HTTP level; no key or network needed."""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path

import anthropic
import httpx2
import pytest
import uvicorn
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import Config, RateLimiter, create_app  # noqa: E402

SSE_HEADERS = {"content-type": "text/event-stream"}


def anthropic_sse(parts: list[str], stop_reason: str = "end_turn", model: str = "claude-opus-5-5") -> bytes:
    events = [
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
                    "usage": {"input_tokens": 5, "output_tokens": 1},
                },
            },
        ),
        (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        ),
    ]
    for part in parts:
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
                "usage": {"output_tokens": 3},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


class Upstream:
    """Records requests sent to the mocked Anthropic API."""

    def __init__(self, response=None) -> None:
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        self.response = response or (
            lambda body: httpx2.Response(200, headers=SSE_HEADERS, content=anthropic_sse(["Hello", " there"]))
        )

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.headers.append(dict(request.headers))
        return self.response(body)

    def client(self) -> anthropic.AsyncAnthropic:
        return anthropic.AsyncAnthropic(
            api_key="sk-ant-server-key",
            max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(self.handler)),
        )


def make(config: Config | None = None, upstream: Upstream | None = None):
    upstream = upstream or Upstream()
    config = config or Config(anthropic_api_key="sk-ant-server-key")
    return TestClient(create_app(config, upstream.client())), upstream


def chat(client: TestClient, model: str = "aven-1", stream: bool = True, token: str = "install123", **extra):
    body = {
        "model": model,
        "stream": stream,
        "messages": [{"role": "system", "content": "You are AVEN."}, {"role": "user", "content": "Hi"}],
        **extra,
    }
    return client.post("/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {token}"})


def sse_payloads(text: str) -> list:
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            data = line[6:]
            out.append(data if data == "[DONE]" else json.loads(data))
    return out


# --- behaviour ----------------------------------------------------------------------------


def test_streams_openai_compatible_chunks_and_maps_model() -> None:
    client, upstream = make()
    response = chat(client)
    assert response.status_code == 200
    payloads = sse_payloads(response.text)
    assert payloads[-1] == "[DONE]"
    text = "".join(p["choices"][0]["delta"].get("content", "") for p in payloads[:-1])
    assert text == "Hello there"
    assert payloads[-2]["choices"][0]["finish_reason"] == "stop"
    assert all(p["model"] == "aven-1" for p in payloads[:-1])  # AVEN name, not the upstream model

    sent = upstream.requests[0]
    assert sent["model"] == "claude-opus-5-5"
    assert sent["system"] == "You are AVEN."
    assert sent["messages"] == [{"role": "user", "content": "Hi"}]
    assert sent["fallbacks"] == "default"
    assert "output_config" not in sent
    assert upstream.headers[0]["x-api-key"] == "sk-ant-server-key"


@pytest.mark.parametrize(
    ("aven_model", "upstream_model", "effort"),
    [
        ("aven-ultra", "claude-opus-5-5", "xhigh"),
        ("aven-core", "claude-sonnet-5-5", None),
        ("aven-light", "claude-haiku-5-5", None),
    ],
)
def test_each_aven_model_mapping(aven_model, upstream_model, effort) -> None:
    client, upstream = make()
    assert chat(client, model=aven_model).status_code == 200
    sent = upstream.requests[0]
    assert sent["model"] == upstream_model
    assert sent.get("output_config", {}).get("effort") == effort
    if upstream_model == "claude-haiku-5-5":
        assert "fallbacks" not in sent


def test_non_streaming_response() -> None:
    client, _ = make()
    response = chat(client, stream=False)
    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] == "Hello there"
    assert data["model"] == "aven-1"


def test_max_tokens_is_capped() -> None:
    client, upstream = make(Config(anthropic_api_key="k", max_output_tokens=1000))
    chat(client, max_tokens=999_999)
    assert upstream.requests[0]["max_tokens"] == 1000


def test_truncation_and_refusal_finish_reasons() -> None:
    for stop, finish in (("max_tokens", "length"), ("refusal", "content_filter")):
        upstream = Upstream(
            lambda body, s=stop: httpx2.Response(200, headers=SSE_HEADERS, content=anthropic_sse(["x"], stop_reason=s))
        )
        client, _ = make(upstream=upstream)
        payloads = sse_payloads(chat(client).text)
        assert payloads[-2]["choices"][0]["finish_reason"] == finish


def test_models_and_health() -> None:
    client, _ = make()
    ids = [m["id"] for m in client.get("/v1/models").json()["data"]]
    assert ids == ["aven-1", "aven-ultra", "aven-core", "aven-light"]
    assert client.get("/health").json() == {"status": "ok", "configured": True}
    unconfigured = TestClient(create_app(Config(anthropic_api_key="")))
    assert unconfigured.get("/health").json()["configured"] is False
    assert chat(unconfigured).status_code == 503


# --- validation -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "x"}]}, 404),
        ({"model": "aven-1", "messages": []}, 400),
        ({"model": "aven-1", "messages": [{"role": "tool", "content": "x"}]}, 400),
        ({"model": "aven-1", "messages": [{"role": "assistant", "content": "x"}]}, 400),
        ({"model": "aven-1", "messages": [{"role": "user", "content": ["not", "text"]}]}, 400),
    ],
)
def test_invalid_requests_rejected(body, status) -> None:
    client, upstream = make()
    response = client.post("/v1/chat/completions", json=body)
    assert response.status_code == status
    assert "error" in response.json()
    assert upstream.requests == []


def test_oversized_conversation_rejected() -> None:
    client, upstream = make(Config(anthropic_api_key="k", max_input_chars=10))
    response = client.post(
        "/v1/chat/completions", json={"model": "aven-1", "messages": [{"role": "user", "content": "x" * 50}]}
    )
    assert response.status_code == 413
    assert upstream.requests == []


# --- limits and errors ----------------------------------------------------------------------


def test_per_install_rate_limit() -> None:
    client, upstream = make(Config(anthropic_api_key="k", requests_per_minute=2))
    assert chat(client, token="a").status_code == 200
    assert chat(client, token="a").status_code == 200
    limited = chat(client, token="a")
    assert limited.status_code == 429
    assert limited.json()["error"]["type"] == "rate_limit_error"
    assert chat(client, token="b").status_code == 200  # other installs unaffected
    assert len(upstream.requests) == 3


def test_daily_limit() -> None:
    client, _ = make(Config(anthropic_api_key="k", requests_per_day=1))
    assert chat(client).status_code == 200
    response = chat(client)
    assert response.status_code == 429
    assert "today" in response.json()["error"]["message"]


def test_rate_limiter_window_expires() -> None:
    limiter = RateLimiter()
    assert limiter.allow("k", 1, 60, now=0)
    assert not limiter.allow("k", 1, 60, now=30)
    assert limiter.allow("k", 1, 60, now=61)


@pytest.mark.parametrize(
    ("status", "error_type", "expected_status"),
    [
        (401, "authentication_error", 503),
        (429, "rate_limit_error", 429),
        (529, "overloaded_error", 503),
        (400, "invalid_request_error", 400),
    ],
)
def test_upstream_errors_are_mapped_without_leaking(status, error_type, expected_status) -> None:
    upstream = Upstream(
        lambda body: httpx2.Response(
            status, json={"type": "error", "error": {"type": error_type, "message": "upstream detail"}}
        )
    )
    client, _ = make(upstream=upstream)
    response = chat(client, model="aven-light")
    assert response.status_code == expected_status
    assert "sk-ant-server-key" not in response.text


def test_concurrency_slot_released_after_requests() -> None:
    client, _ = make(Config(anthropic_api_key="k", max_concurrent=1))
    for _ in range(3):  # would hang if the single slot leaked
        assert chat(client).status_code == 200
    upstream = Upstream(
        lambda body: httpx2.Response(500, json={"type": "error", "error": {"type": "api_error", "message": "boom"}})
    )
    client, _ = make(Config(anthropic_api_key="k", max_concurrent=1), upstream)
    for _ in range(3):
        assert chat(client).status_code == 503


# --- end to end with the desktop app's provider ------------------------------------------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_desktop_app_provider_talks_to_server_over_http() -> None:
    desktop = ROOT.parent / "aven_ai_desktop"
    sys.path.insert(0, str(desktop))
    from app.ai.base_provider import ChatMessage, ChatRequest
    from app.ai.provider_factory import create_provider

    upstream = Upstream(
        lambda body: httpx2.Response(200, headers=SSE_HEADERS, content=anthropic_sse(["Shalom", " from AVEN"]))
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(Config(anthropic_api_key="k"), upstream.client()),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    try:
        provider = create_provider("aven_cloud", None, base_url=f"http://127.0.0.1:{port}/v1", client_id="abc123")
        request = ChatRequest(
            model="aven-ultra", system_prompt="You are AVEN.", messages=[ChatMessage("user", "Hi")], max_tokens=500
        )
        events = list(provider.stream_chat(request))
        assert "".join(e.text for e in events if e.kind == "text") == "Shalom from AVEN"
        assert upstream.requests[0]["model"] == "claude-opus-5-5"
        assert upstream.requests[0]["output_config"] == {"effort": "xhigh"}
        assert upstream.requests[0]["max_tokens"] == 500
        assert provider.list_models() == ["aven-1", "aven-core", "aven-light", "aven-ultra"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)
