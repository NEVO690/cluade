from __future__ import annotations

import json

import keyring
import pytest
from keyring.backend import KeyringBackend

from app.config.aven_models import AVEN_MODELS, aven_model_name
from app.config.secrets import CredentialStore, mask_key
from app.config.settings import (
    AppSettings,
    SettingsStore,
    apply_env_overrides,
    load_dotenv_file,
    sanitize_model_id,
    validate_base_url,
)

# --- settings ---------------------------------------------------------------------------


def test_defaults_use_aven_ultra_mapped_to_documented_anthropic_model() -> None:
    settings = AppSettings().normalized()
    assert settings.provider == "anthropic"
    assert settings.aven_model == settings.code_model == "aven-ultra"
    assert settings.model_for_mode("aven") == "claude-opus-5-5"
    assert settings.model_for_mode("code") == "claude-opus-5-5"
    assert settings.provider_model_for("aven-swift") == "claude-haiku-5-5"
    assert settings.provider_model_for("aven-core") == "claude-sonnet-5-5"
    assert settings.mapping_for("openai") == {}  # no guessed OpenAI model IDs


def test_aven_model_names() -> None:
    assert [m.name for m in AVEN_MODELS] == ["AVEN Swift", "AVEN Core", "AVEN Ultra"]
    assert aven_model_name("aven-core") == "AVEN Core"
    assert aven_model_name("legacy-raw-id") == "legacy-raw-id"
    assert aven_model_name(None) == ""


def test_settings_round_trip(tmp_path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = AppSettings(theme="dark", provider="openai", max_tokens=4096, aven_model="aven-swift")
    settings.mapping_for("openai").update({"aven-swift": "my-fast-model", "aven-ultra": "my-big-model"})
    store.save(settings)

    loaded = store.load()
    assert loaded.theme == "dark"
    assert loaded.provider == "openai"
    assert loaded.max_tokens == 4096
    assert loaded.model_for_mode("aven") == "my-fast-model"
    assert loaded.model_for_mode("code") == "my-big-model"
    assert loaded.mapping_for("anthropic")["aven-ultra"] == "claude-opus-5-5"


def test_invalid_model_choices_are_normalized(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"aven_model": "gpt-9", "model_map": {"anthropic": {"aven-core": "bad id", "x": "y"}}}))
    loaded = SettingsStore(path).load()
    assert loaded.aven_model == "aven-ultra"
    assert "aven-core" not in loaded.mapping_for("anthropic")
    assert "x" not in loaded.mapping_for("anthropic")


def test_settings_file_never_contains_api_keys(tmp_path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings())
    data = json.loads((tmp_path / "settings.json").read_text())
    assert not any("key" in name.lower() for name in data)


def test_corrupt_or_invalid_settings_fall_back_to_defaults(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert SettingsStore(path).load().theme == "system"

    path.write_text(json.dumps({"theme": "neon", "provider": "nope", "max_tokens": 10**9, "request_timeout": "x"}))
    loaded = SettingsStore(path).load()
    assert loaded.theme == "system"
    assert loaded.provider == "anthropic"
    assert loaded.max_tokens == 128_000
    assert loaded.request_timeout == 600


def test_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("AVEN_PROVIDER", "openai")
    monkeypatch.setenv("AVEN_MODEL", "aven-swift")
    monkeypatch.setenv("AVEN_CODE_MODEL", "not-a-tier")
    monkeypatch.setenv("AVEN_SWIFT_MODEL", "local-small")
    monkeypatch.setenv("AVEN_ULTRA_MODEL", "local-large")
    monkeypatch.setenv("AVEN_BASE_URL", "javascript:alert(1)")
    settings = apply_env_overrides(AppSettings())
    assert settings.provider == "openai"
    assert settings.aven_model == "aven-swift"
    assert settings.code_model == "aven-ultra"  # invalid value ignored
    assert settings.model_for_mode("aven") == "local-small"
    assert settings.model_for_mode("code") == "local-large"
    assert settings.openai_base_url == ""  # invalid URL ignored


@pytest.mark.parametrize(
    ("value", "expected"),
    [(" claude-opus-5-5 ", "claude-opus-5-5"), ("bad model", ""), ("x" * 300, ""), ("a\x00b", "")],
)
def test_sanitize_model_id(value: str, expected: str) -> None:
    assert sanitize_model_id(value) == expected


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("", True),
        ("https://api.example.com/v1", True),
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:8000/v1", True),
        ("http://api.example.com/v1", False),
        ("ftp://example.com", False),
        ("not a url", False),
    ],
)
def test_validate_base_url(url: str, ok: bool) -> None:
    assert (validate_base_url(url) is None) is ok


def test_dotenv_loader_does_not_override_existing(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text('# comment\nAVEN_TEST_A="quoted"\nexport AVEN_TEST_B=plain\nAVEN_TEST_C=new\n')
    monkeypatch.setenv("AVEN_TEST_C", "existing")
    monkeypatch.delenv("AVEN_TEST_A", raising=False)
    monkeypatch.delenv("AVEN_TEST_B", raising=False)
    assert load_dotenv_file(env) == 2
    import os

    assert os.environ["AVEN_TEST_A"] == "quoted"
    assert os.environ["AVEN_TEST_B"] == "plain"
    assert os.environ["AVEN_TEST_C"] == "existing"
    assert load_dotenv_file(tmp_path / "missing.env") == 0


# --- credentials -------------------------------------------------------------------------


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        self.store.pop((service, username), None)


@pytest.fixture
def memory_keyring():
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


def test_keys_go_to_credential_store(memory_keyring) -> None:
    store = CredentialStore()
    assert store.persistent_storage_available
    assert store.save_key("anthropic", "sk-ant-test-key-1234") == "credential store"
    assert memory_keyring.store
    lookup = store.lookup("anthropic")
    assert (lookup.key, lookup.source) == ("sk-ant-test-key-1234", "credential store")
    store.delete_key("anthropic")
    assert store.lookup("anthropic").source == "none"


def test_environment_variable_takes_precedence(memory_keyring, monkeypatch) -> None:
    store = CredentialStore()
    store.save_key("openai", "sk-stored-0000000")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env-11111")
    lookup = store.lookup("openai")
    assert (lookup.key, lookup.source) == ("sk-from-env-11111", "environment")


def test_session_fallback_without_keyring() -> None:
    store = CredentialStore(use_keyring=False)
    assert not store.persistent_storage_available
    assert store.save_key("anthropic", "sk-session-12345") == "session"
    assert store.lookup("anthropic").source == "session"


@pytest.mark.parametrize("bad", ["", "   ", "has space", "x" * 600])
def test_invalid_keys_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        CredentialStore(use_keyring=False).save_key("anthropic", bad)


def test_mask_key_hides_most_of_the_key() -> None:
    masked = mask_key("sk-ant-api03-abcdefghijklmnop")
    assert masked.startswith("sk-ant") and masked.endswith("mnop")
    assert "abcdefgh" not in masked
    assert mask_key("") == ""
