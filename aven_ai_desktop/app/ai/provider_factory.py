"""Registry of supported providers and construction of configured clients."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.ai import errors
from app.ai.base_provider import AIProvider


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    key_env_var: str
    key_help: str
    console_url: str
    privacy_url: str


PROVIDERS: dict[str, ProviderInfo] = {
    "anthropic": ProviderInfo(
        id="anthropic",
        name="Anthropic (Claude)",
        key_env_var="ANTHROPIC_API_KEY",
        key_help="Create a key in the Claude Console under API Keys.",
        console_url="https://platform.claude.com/",
        privacy_url="https://www.anthropic.com/legal/privacy",
    ),
    "openai": ProviderInfo(
        id="openai",
        name="OpenAI / OpenAI-compatible",
        key_env_var="OPENAI_API_KEY",
        key_help="Create a key in the OpenAI dashboard, or set a base URL for a compatible server.",
        console_url="https://platform.openai.com/",
        privacy_url="https://openai.com/policies/privacy-policy",
    ),
}


def is_local_url(url: str) -> bool:
    return urlparse(url).hostname in ("localhost", "127.0.0.1", "::1") if url else False


def key_required(provider_id: str, base_url: str = "") -> bool:
    return not (provider_id == "openai" and is_local_url(base_url))


def create_provider(provider_id: str, api_key: str | None, *, base_url: str = "", timeout: float = 600.0) -> AIProvider:
    if provider_id not in PROVIDERS:
        raise errors.ProviderError(f"Unknown AI provider: {provider_id}")
    if not api_key and key_required(provider_id, base_url):
        info = PROVIDERS[provider_id]
        raise errors.MissingCredentialsError(
            f"No API key is configured for {info.name}. Add one in Settings → AI Provider, "
            f"or set the {info.key_env_var} environment variable."
        )
    # Import lazily so a missing optional SDK only affects that provider.
    if provider_id == "anthropic":
        from app.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key or "", timeout=timeout)
    from app.ai.openai_provider import OpenAIProvider

    return OpenAIProvider(api_key or "", base_url=base_url if provider_id == "openai" else "", timeout=timeout)
