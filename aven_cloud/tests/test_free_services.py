"""AVEN Cloud on free OpenAI-compatible services (Groq, Gemini). HTTP is mocked; no key needed."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx2
import openai
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backends import SERVICES, choose_model, match_candidate
from server import Config, create_app, detect_service

SSE = {"content-type": "text/event-stream"}


def openai_sse(parts: list[str], finish: str = "stop", model: str = "upstream") -> bytes:
    lines = []
    for i, part in enumerate(parts):
        delta = {"role": "assistant", "content": part} if i == 0 else {"content": part}
        lines.append(
            {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
        )
    lines.append(
        {
            "id": "c",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
        }
    )
    return ("".join(f"data: {json.dumps(x)}\n\n" for x in lines) + "data: [DONE]\n\n").encode()


class FakeService:
    """Mocks an OpenAI-compatible service: a model list and streaming chat completions."""

    def __init__(self, models: list[str], chat=None) -> None:
        self.models = models
        self.chats: list[dict] = []
        self.paths: list[str] = []
        self.chat = chat or (lambda body: httpx2.Response(200, headers=SSE, content=openai_sse(["Free", " reply"])))

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.paths.append(request.url.path)
        if request.url.path.endswith("/models"):
            return httpx2.Response(
                200,
                json={
                    "object": "list",
                    "data": [{"id": m, "object": "model", "created": 0, "owned_by": "x"} for m in self.models],
                },
            )
        body = json.loads(request.content)
        self.chats.append(body)
        return self.chat(body)

    def client(self, service: str) -> openai.AsyncOpenAI:
        return openai.AsyncOpenAI(
            api_key="free-key",
            base_url=SERVICES[service].base_url,
            max_retries=0,
            http_client=openai.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(self.handler)),
        )


def app_for(service: str, fake: FakeService, **config) -> TestClient:
    return TestClient(create_app(Config(service=service, api_key="free-key", **config), fake.client(service)))


def chat(client: TestClient, model: str):
    return client.post(
        "/v1/chat/completions",
        json={
            "model": model,
            "stream": True,
            "messages": [{"role": "system", "content": "You are AVEN."}, {"role": "user", "content": "Hi"}],
        },
        headers={"Authorization": "Bearer install1"},
    )


def text_of(response) -> str:
    out = []
    for line in response.text.splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            out.append(json.loads(line[6:])["choices"][0]["delta"].get("content", ""))
    return "".join(out)


GROQ_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "whisper-large-v3",
    "meta-llama/llama-guard-4-12b",
]


@pytest.mark.parametrize(
    ("aven_model", "expected"),
    [
        ("aven-1-1", "openai/gpt-oss-120b"),
        ("aven-ultra", "openai/gpt-oss-120b"),
        ("aven-core", "llama-3.3-70b-versatile"),
        ("aven-light", "llama-3.1-8b-instant"),
    ],
)
def test_groq_free_models(aven_model, expected) -> None:
    fake = FakeService(GROQ_MODELS)
    client = app_for("groq", fake)
    response = chat(client, aven_model)
    assert response.status_code == 200
    assert text_of(response) == "Free reply"
    sent = fake.chats[0]
    assert sent["model"] == expected
    assert sent["messages"][0] == {"role": "system", "content": "You are AVEN."}
    assert sent["stream"] is True
    assert "/openai/v1/" in fake.paths[-1]


def test_ultra_reasons_more_on_gpt_oss() -> None:
    fake = FakeService(["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"])
    client = app_for("groq", fake)
    chat(client, "aven-ultra")
    chat(client, "aven-1-1")
    chat(client, "aven-core")
    assert fake.chats[0]["reasoning_effort"] == "high"
    assert "reasoning_effort" not in fake.chats[1]  # gpt-oss default (medium)
    assert "reasoning_effort" not in fake.chats[2]  # not a reasoning model


def test_renamed_models_are_found_automatically() -> None:
    # The service retired the exact ids we know; patterns still find suitable replacements.
    fake = FakeService(["llama-4.1-70b-versatile", "llama-4.0-8b-instant", "gpt-oss-120b-v2", "whisper-x"])
    client = app_for("groq", fake)
    for aven_model, expected in (
        ("aven-1-1", "gpt-oss-120b-v2"),
        ("aven-core", "llama-4.1-70b-versatile"),
        ("aven-light", "llama-4.0-8b-instant"),
    ):
        assert chat(client, aven_model).status_code == 200
        assert fake.chats[-1]["model"] == expected


def test_model_list_is_cached() -> None:
    fake = FakeService(GROQ_MODELS)
    client = app_for("groq", fake)
    for _ in range(3):
        chat(client, "aven-light")
    assert sum(path.endswith("/models") for path in fake.paths) == 1


def test_gemini_picks_newest_flash_models() -> None:
    models = [
        "models/gemini-2.5-flash",
        "models/gemini-3.5-flash",
        "models/gemini-3.5-flash-lite",
        "models/gemini-3.5-pro",
        "models/gemini-3.5-flash-preview-tts",
        "models/text-embedding-004",
    ]
    fake = FakeService(models)
    client = app_for("gemini", fake)
    expected = {
        "aven-1-1": "gemini-3.5-flash",
        "aven-ultra": "gemini-3.5-flash",
        "aven-core": "gemini-3.5-flash",
        "aven-light": "gemini-3.5-flash-lite",
    }
    for aven_model, model in expected.items():
        assert chat(client, aven_model).status_code == 200
        assert fake.chats[-1]["model"] == model
    assert "/v1beta/openai/" in fake.paths[-1]


def test_explicit_override_wins() -> None:
    fake = FakeService(GROQ_MODELS)
    client = app_for("groq", fake, overrides={"aven-1-1": "llama-3.1-8b-instant"})
    chat(client, "aven-1-1")
    assert fake.chats[0]["model"] == "llama-3.1-8b-instant"


def test_free_service_rate_limit_becomes_friendly_busy_message() -> None:
    fake = FakeService(
        GROQ_MODELS,
        chat=lambda body: httpx2.Response(
            429, json={"error": {"message": "Rate limit reached for model on tokens per day", "type": "tokens"}}
        ),
    )
    response = chat(app_for("groq", fake), "aven-1-1")
    assert response.status_code == 429
    assert "busy" in response.json()["error"]["message"]
    assert "free-key" not in response.text


def test_bad_key_is_reported_as_unavailable_without_leaking() -> None:
    fake = FakeService(GROQ_MODELS, chat=lambda body: httpx2.Response(401, json={"error": {"message": "bad key"}}))
    response = chat(app_for("groq", fake), "aven-light")
    assert response.status_code == 503
    assert "free-key" not in response.text


def test_truncation_reported() -> None:
    fake = FakeService(
        GROQ_MODELS, chat=lambda body: httpx2.Response(200, headers=SSE, content=openai_sse(["x"], finish="length"))
    )
    response = chat(app_for("groq", fake), "aven-core")
    finishes = [
        json.loads(line[6:])["choices"][0]["finish_reason"]
        for line in response.text.splitlines()
        if line.startswith("data: {")
    ]
    assert finishes[-1] == "length"


def test_model_list_failure_falls_back_to_known_ids() -> None:
    fake = FakeService(GROQ_MODELS)
    original = fake.handler

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx2.Response(500, json={"error": {"message": "down"}})
        return original(request)

    fake.handler = handler
    assert chat(app_for("groq", fake), "aven-core").status_code == 200
    assert fake.chats[0]["model"] == "llama-3.3-70b-versatile"


# --- pure functions -----------------------------------------------------------------------------


def test_match_candidate_patterns() -> None:
    available = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-flash-preview-tts"]
    assert match_candidate("~gemini flash -lite", available) == "gemini-2.5-flash"
    assert match_candidate("~gemini flash lite", available) == "gemini-2.5-flash-lite"
    assert match_candidate("gemini-2.0-flash", available) == "gemini-2.0-flash"
    assert match_candidate("gemini-9-ultra", available) is None


def test_choose_model_fallbacks() -> None:
    assert choose_model(("~nothing", "exact-a"), ["exact-a"]) == "exact-a"
    assert choose_model(("~nothing",), ["chat-model-2", "whisper-1"]) == "chat-model-2"
    assert choose_model(("~x", "known-id"), None) == "known-id"
    assert choose_model(("~x",), []) is None


def test_service_detection(monkeypatch) -> None:
    for var in ("AVEN_UPSTREAM", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert detect_service() == "groq"
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert detect_service() == "gemini"
    monkeypatch.setenv("GROQ_API_KEY", "q")
    assert detect_service() == "groq"
    monkeypatch.setenv("AVEN_UPSTREAM", "gemini")
    assert detect_service() == "gemini"
    config = Config.from_env()
    assert (config.service, config.api_key) == ("gemini", "g")
