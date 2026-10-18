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


def test_status_reports_missing_key_and_model() -> None:
    status = service(key=None).status("aven")
    assert not status.ready
    assert "API key" in status.problem

    settings = AppSettings()
    settings.models_for().aven_code_model = ""
    status = service(settings=settings).status("code")
    assert not status.ready
    assert "AVEN CODE" in status.problem
    assert service().status("aven").ready


def test_local_openai_server_needs_no_key() -> None:
    settings = AppSettings(provider="openai", openai_base_url="http://localhost:11434/v1")
    settings.models_for("openai").aven_model = "llama3"
    assert service(key=None, settings=settings).status("aven").ready


def test_modes_use_distinct_system_prompts_and_models() -> None:
    settings = AppSettings()
    settings.models_for().aven_model = "general-model"
    settings.models_for().aven_code_model = "code-model"
    svc = service(settings=settings)
    history = [ChatMessage("user", "Hello")]
    general = svc.build_request("aven", history)
    code = svc.build_request("code", history)
    assert general.system_prompt == AVEN_SYSTEM_PROMPT
    assert code.system_prompt == AVEN_CODE_SYSTEM_PROMPT
    assert (general.model, code.model) == ("general-model", "code-model")


def test_code_prompt_forbids_claiming_execution() -> None:
    assert "Never claim that code has" in AVEN_CODE_SYSTEM_PROMPT
    for language in ("Roblox Luau", "Unity C#", "Unreal Engine C++", "SQL"):
        assert language in AVEN_CODE_SYSTEM_PROMPT


def test_build_request_requires_trailing_user_message() -> None:
    with pytest.raises(errors.InvalidRequestError):
        service().build_request("aven", [ChatMessage("user", "q"), ChatMessage("assistant", "a")])


def test_build_request_without_model() -> None:
    settings = AppSettings()
    settings.models_for().aven_model = ""
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
    svc = ChatService(AppSettings(), CredentialStore(use_keyring=False))
    request = svc.build_request("aven", [ChatMessage("user", "hi")])
    with pytest.raises(errors.MissingCredentialsError):
        list(svc.stream(request))
