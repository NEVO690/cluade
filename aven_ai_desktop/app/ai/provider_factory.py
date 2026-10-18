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
    "aven_local": ProviderInfo(
        id="aven_local",
        name="AVEN Local (on this computer, free)",
        key_env_var="",
        key_help=(
            "No API key and no account. AVEN runs open-source Qwen3 models on this computer; each model "
            "is downloaded once. Conversations never leave your computer. Replies are slower on older PCs."
        ),
        console_url="",
        privacy_url="",
    ),
    "aven_cloud": ProviderInfo(
        id="aven_cloud",
        name="AVEN Cloud",
        key_env_var="",
        key_help=(
            "No API key needed. Messages go to the AVEN AI server, which generates replies with a "
            "third-party AI service (such as Groq, Google Gemini or Anthropic)."
        ),
        console_url="",
        privacy_url="https://www.anthropic.com/legal/privacy",
    ),
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
    if provider_id in ("aven_cloud", "aven_local"):
        return False
    return not (provider_id == "openai" and is_local_url(base_url))


def create_provider(
    provider_id: str,
    api_key: str | None,
    *,
    base_url: str = "",
    timeout: float = 600.0,
    client_id: str = "",
) -> AIProvider:
    if provider_id not in PROVIDERS:
        raise errors.ProviderError(f"Unknown AI provider: {provider_id}")
    if provider_id == "aven_local":
        from app.ai.local_provider import LocalProvider
        from app.local.engine import get_engine

        return LocalProvider(get_engine(), timeout=timeout)
    if provider_id == "aven_cloud":
        from app.ai.openai_provider import OpenAIProvider
        from app.config.cloud import cloud_url

        url = base_url or cloud_url()
        if not url:
            raise errors.MissingCredentialsError(
                "AVEN Cloud is not available in this build yet. Choose a provider with your own API key "
                "in Settings → AI Provider."
            )
        # AVEN Cloud speaks the OpenAI-compatible chat API. The "key" is only an anonymous
        # install id the server uses for fair-use limits; the real provider key stays on the server.
        return OpenAIProvider(client_id or "anonymous", base_url=url, timeout=timeout, display_name="AVEN Cloud")
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
