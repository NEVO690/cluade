from __future__ import annotations

import pytest

from app.ai import errors
from app.ai.base_provider import ChatMessage
from app.ai.chat_service import ChatService, trim_history
from app.ai.prompts import AVEN_CODE_SYSTEM_PROMPT, AVEN_SYSTEM_PROMPT
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
    assert status.model_name == "AVEN 1.0"


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
    assert ready.model_name == "AVEN 1.0"
    assert ready.model == "claude-opus-5-5"


def test_local_openai_server_needs_no_key() -> None:
    settings = AppSettings(provider="openai", openai_base_url="http://localhost:11434/v1")
    settings.mapping_for("openai")["aven-1"] = "llama3"
    assert service(key=None, settings=settings).status().ready


def test_modes_use_distinct_system_prompts() -> None:
    svc = service(settings=AppSettings(provider="anthropic", model="aven-core"))
    history = [ChatMessage("user", "Hello")]
    general = svc.build_request("aven", history)
    code = svc.build_request("code", history)
    assert general.system_prompt == AVEN_SYSTEM_PROMPT
    assert code.system_prompt == AVEN_CODE_SYSTEM_PROMPT
    assert general.model == code.model == "claude-sonnet-5-5"


@pytest.mark.parametrize(
    ("aven_model", "model", "effort"),
    [
        ("aven-1", "claude-opus-5-5", None),
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
    assert "Never claim that code has" in AVEN_CODE_SYSTEM_PROMPT
    for language in ("Roblox Luau", "Unity C#", "Unreal Engine C++", "SQL"):
        assert language in AVEN_CODE_SYSTEM_PROMPT


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
    for prompt, name in ((AVEN_SYSTEM_PROMPT, "AVEN"), (AVEN_CODE_SYSTEM_PROMPT, "AVEN CODE")):
        assert f"you are {name} by AVEN AI" in prompt
        assert "do not deny using a third-party provider" in prompt
