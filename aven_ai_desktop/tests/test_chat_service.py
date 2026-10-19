from __future__ import annotations

import datetime

import pytest

from app.ai import errors
from app.ai.base_provider import ChatMessage
from app.ai.chat_service import ChatService, trim_history
from app.ai.prompts import system_prompt_for
from app.config.secrets import CredentialStore
from app.config.settings import AppSettings
from tests.conftest import FakeProvider


def service(key: str | None = "sk-test-key", provider=None, settings: AppSettings | None = None) -> ChatService:
    credentials = CredentialStore(use_keyring=False)
    if key:
        credentials.save_key("anthropic", key)
    return ChatService(settings or AppSettings(), credentials, provider_factory=lambda *a, **k: provider)


def test_aven_cloud_is_ready_without_any_key(monkeypatch) -> None:
    monkeypatch.setenv("AVEN_CLOUD_URL", "https://cloud.aven.example")
    status = service(key=None, settings=AppSettings(provider="aven_cloud")).status()
    assert status.ready
    assert status.provider_name == "AVEN Cloud"
    assert status.model_name == "AVEN 1.1"


def test_aven_cloud_unavailable_when_build_has_no_server() -> None:
    status = service(key=None, settings=AppSettings(provider="aven_cloud")).status()
    assert not status.ready
    assert "own API key" in status.problem


def test_aven_cloud_requests_send_aven_model_id_and_no_effort() -> None:
    svc = service(settings=AppSettings(provider="aven_cloud", model="aven-ultra"))
    request = svc.build_request("aven", [ChatMessage("user", "Hi")])
    assert request.model == "aven-ultra"  # the server maps it
    assert request.effort is None  # the server applies effort


def test_personal_key_status_reports_missing_key_and_mapping() -> None:
    status = service(key=None, settings=AppSettings(provider="anthropic")).status()
    assert not status.ready
    assert "API key" in status.problem

    settings = AppSettings(provider="anthropic", model="aven-core")
    settings.mapping_for().pop("aven-core")
    status = service(settings=settings).status()
    assert not status.ready
    assert "AVEN Core" in status.problem and "Advanced" in status.problem

    ready = service(settings=AppSettings(provider="anthropic")).status()
    assert ready.ready
    assert ready.model_name == "AVEN 1.1"
    assert ready.model == "claude-opus-5-5"


def test_local_openai_server_needs_no_key() -> None:
    settings = AppSettings(provider="openai", openai_base_url="http://localhost:11434/v1")
    settings.mapping_for("openai")["aven-1-1"] = "llama3"
    assert service(key=None, settings=settings).status().ready


def test_modes_use_distinct_system_prompts() -> None:
    svc = service(settings=AppSettings(provider="anthropic", model="aven-core"))
    history = [ChatMessage("user", "Hello")]
    general = svc.build_request("aven", history)
    code = svc.build_request("code", history)
    assert general.system_prompt.startswith("You are AVEN, the general-purpose assistant")
    assert code.system_prompt.startswith("You are AVEN CODE, the programming assistant")
    assert general.system_prompt == system_prompt_for(
        "aven", "aven-core", provider="anthropic", provider_name="Anthropic (Claude)"
    )
    assert general.model == code.model == "claude-sonnet-5-5"


@pytest.mark.parametrize(
    ("aven_model", "model", "effort"),
    [
        ("aven-1-1", "claude-opus-5-5", "high"),
        ("aven-ultra", "claude-opus-5-5", "xhigh"),
        ("aven-core", "claude-sonnet-5-5", None),
        ("aven-light", "claude-haiku-5-5", None),
    ],
)
def test_personal_key_model_mapping_and_effort(aven_model, model, effort) -> None:
    svc = service(settings=AppSettings(provider="anthropic", model=aven_model))
    request = svc.build_request("aven", [ChatMessage("user", "Hi")])
    assert (request.model, request.effort) == (model, effort)


def test_code_prompt_forbids_claiming_execution() -> None:
    code_prompt = system_prompt_for("code")
    assert "Never claim that code has been executed" in code_prompt
    for language in ("Roblox Luau", "Unity C#", "Unreal Engine C++", "SQL"):
        assert language in code_prompt


@pytest.mark.parametrize(
    ("aven_model", "name", "profile"),
    [
        ("aven-1-1", "AVEN 1.1", "main AVEN model"),
        ("aven-ultra", "AVEN Ultra", "hardest tasks"),
        ("aven-core", "AVEN Core", "balanced"),
        ("aven-light", "AVEN Light", "fast AVEN model"),
    ],
)
def test_each_model_gets_its_name_and_profile(aven_model, name, profile) -> None:
    prompt = system_prompt_for("aven", aven_model, today=datetime.date(2026, 10, 19))
    assert f"You are {name}." in prompt
    assert profile in prompt
    assert "Today's date is Monday, 19 October 2026 (mention it only when it is relevant)." in prompt
    # Official names only; never internal labels.
    assert "AVEN 1.1, AVEN Ultra, AVEN Core, AVEN Light" in prompt
    assert "flagship" not in prompt.lower()


def test_prompts_cover_language_honesty_and_tools() -> None:
    prompt = system_prompt_for("aven")
    for rule in (
        "Always reply in the same language as the user's latest message",
        "ktiv male",
        "never join Hebrew and English letters in one word",
        "Never use characters from another writing system",
        "no internet access, web search, file access or code execution",
        "Never claim to have searched, browsed, opened a file or run code",
        "ask them to paste the text",
        "Never state a result\n  before you have worked it out",
        "never inside code, JSON or formal text",
    ):
        assert rule in prompt
    assert len(prompt) < 4000  # on-device models process this on the CPU for every new chat


def test_build_request_requires_trailing_user_message() -> None:
    with pytest.raises(errors.InvalidRequestError):
        service().build_request("aven", [ChatMessage("user", "q"), ChatMessage("assistant", "a")])


def test_build_request_without_model() -> None:
    settings = AppSettings(provider="openai")
    with pytest.raises(errors.MissingModelError):
        service(settings=settings).build_request("aven", [ChatMessage("user", "q")])


def test_trim_history_keeps_newest_and_starts_with_user() -> None:
    history = [ChatMessage("user" if i % 2 == 0 else "assistant", f"{i}" * 100) for i in range(10)]
    trimmed = trim_history(history, max_chars=350)
    assert trimmed[-1] == history[-1] or trimmed[-1].role == "assistant"
    assert trimmed[0].role == "user"
    assert sum(len(m.content) for m in trimmed) <= 350
    assert trim_history([ChatMessage("assistant", "x"), ChatMessage("user", " ")]) == []


def test_stream_passes_events_through() -> None:
    provider = FakeProvider(reply="abcdefghij")
    svc = service(provider=provider)
    request = svc.build_request("aven", [ChatMessage("user", "hi")])
    text = "".join(e.text for e in svc.stream(request) if e.kind == "text")
    assert text == "abcdefghij"
    assert provider.requests[0].messages[-1].content == "hi"


def test_stream_wraps_unexpected_exceptions() -> None:
    class Broken(FakeProvider):
        def stream_chat(self, request):
            raise RuntimeError("boom with sk-secret-key-123456")
            yield  # pragma: no cover

    svc = service(provider=Broken())
    request = svc.build_request("aven", [ChatMessage("user", "hi")])
    with pytest.raises(errors.ProviderError) as info:
        list(svc.stream(request))
    assert "sk-secret" not in info.value.user_message


def test_missing_credentials_from_real_factory() -> None:
    svc = ChatService(AppSettings(provider="aven_cloud"), CredentialStore(use_keyring=False))
    request = svc.build_request("aven", [ChatMessage("user", "hi")])
    with pytest.raises(errors.MissingCredentialsError):
        list(svc.stream(request))


def test_prompts_keep_aven_branding_without_hiding_the_provider() -> None:
    local = system_prompt_for("aven", provider="aven_local")
    assert "open-source Qwen3 language model" in local
    keyed = system_prompt_for("code", provider="anthropic", provider_name="Anthropic (Claude)")
    assert "large language models from Anthropic (Claude)" in keyed
    for prompt in (local, keyed):
        assert "made by AVEN AI" in prompt
        assert "do not deny which provider or model is used" in prompt
