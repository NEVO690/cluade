"""User settings: theme, provider and model configuration.

Settings are stored as JSON in the user data directory. API keys are *never*
written here - see :mod:`app.config.secrets`.

Environment variables (useful for development, also read by packaged builds)
take precedence over saved values for the current session only:

* ``AVEN_PROVIDER``     - ``aven_local``, ``aven_cloud``, ``anthropic`` or ``openai``
* ``AVEN_MODEL``        - selected AVEN model (``aven-1``, ``aven-ultra``, ``aven-core``, ``aven-light``)
* ``AVEN_1_MODEL`` / ``AVEN_ULTRA_MODEL`` / ``AVEN_CORE_MODEL`` / ``AVEN_LIGHT_MODEL``
                        - provider model ID behind each AVEN model (personal-key providers)
* ``AVEN_BASE_URL``     - custom HTTPS base URL for the OpenAI provider
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from app.config.aven_models import AVEN_MODEL_IDS, DEFAULT_AVEN_MODEL, DEFAULT_MAPPINGS
from app.paths import project_root, settings_path

log = logging.getLogger(__name__)

THEMES = ("system", "light", "dark")
# "aven_local" runs open-source models on this computer and "aven_cloud" uses the AVEN AI
# server (neither needs an API key); the others use a personal key.
PROVIDER_IDS = ("aven_local", "aven_cloud", "anthropic", "openai")
KEY_PROVIDER_IDS = ("anthropic", "openai")

MIN_MAX_TOKENS = 256
MAX_MAX_TOKENS = 128_000
MIN_TIMEOUT = 10
MAX_TIMEOUT = 1800


def default_provider() -> str:
    """AVEN Cloud when this build includes a server address, otherwise AVEN Local."""
    from app.config.cloud import cloud_url

    return "aven_cloud" if cloud_url() else "aven_local"


def default_model(provider: str) -> str:
    # On a home computer the smallest model is the best first experience.
    return "aven-light" if provider == "aven_local" else DEFAULT_AVEN_MODEL


def _default_mappings() -> dict[str, dict[str, str]]:
    return {pid: dict(DEFAULT_MAPPINGS.get(pid, {})) for pid in KEY_PROVIDER_IDS}


@dataclass
class AppSettings:
    theme: str = "system"
    provider: str = field(default_factory=default_provider)
    # AVEN model selected in the message box ("" = the provider's default).
    model: str = ""
    # Provider model ID behind each AVEN model, per personal-key provider.
    model_map: dict[str, dict[str, str]] = field(default_factory=_default_mappings)
    openai_base_url: str = ""
    max_tokens: int = 32_000
    request_timeout: int = 600
    send_with_enter: bool = True
    window_geometry: str = ""
    # Random identifier sent to AVEN Cloud for fair-use limits (not linked to any account).
    install_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not self.model:
            self.model = default_model(self.provider)

    # --- convenience accessors -------------------------------------------------
    def mapping_for(self, provider: str | None = None) -> dict[str, str]:
        pid = provider or self.provider
        return self.model_map.setdefault(pid, dict(DEFAULT_MAPPINGS.get(pid, {})))

    def provider_model_for(self, aven_model: str, provider: str | None = None) -> str:
        return self.mapping_for(provider).get(aven_model, "")

    def resolved_model(self) -> str:
        """Model ID sent to the provider for the selected AVEN model ("" when not mapped).

        AVEN Cloud and AVEN Local receive the AVEN model id itself and map it.
        """
        if self.provider in ("aven_cloud", "aven_local"):
            return self.model
        return self.provider_model_for(self.model)

    # --- validation ------------------------------------------------------------
    def normalized(self) -> AppSettings:
        if self.theme not in THEMES:
            self.theme = "system"
        if self.provider not in PROVIDER_IDS:
            self.provider = default_provider()
        self.max_tokens = _clamp(self.max_tokens, MIN_MAX_TOKENS, MAX_MAX_TOKENS, 32_000)
        self.request_timeout = _clamp(self.request_timeout, MIN_TIMEOUT, MAX_TIMEOUT, 600)
        self.openai_base_url = (self.openai_base_url or "").strip()
        if self.model not in AVEN_MODEL_IDS:
            self.model = default_model(self.provider)
        if not (isinstance(self.install_id, str) and len(self.install_id) == 32 and self.install_id.isalnum()):
            self.install_id = uuid.uuid4().hex
        for pid in KEY_PROVIDER_IDS:
            mapping = self.mapping_for(pid)
            for key in list(mapping):
                value = sanitize_model_id(mapping[key])
                if key in AVEN_MODEL_IDS and value:
                    mapping[key] = value
                else:
                    del mapping[key]
        return self


def _clamp(value: object, low: int, high: int, default: int) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def sanitize_model_id(value: str | None) -> str:
    """Model identifiers are short tokens; strip whitespace and reject control chars."""
    text = (value or "").strip()
    if len(text) > 200 or any(ch.isspace() or ord(ch) < 32 for ch in text):
        return ""
    return text


def validate_base_url(url: str) -> str | None:
    """Return an error message, or None when the URL is acceptable.

    HTTPS is required, except for loopback addresses (local model servers).
    """
    url = url.strip()
    if not url:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        return None
    if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        return None
    return "The base URL must start with https:// (plain http is only allowed for localhost)."


# --- persistence -------------------------------------------------------------------


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings_path()

    def load(self) -> AppSettings:
        settings = AppSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return settings.normalized()
        except (OSError, ValueError) as exc:
            log.warning("Could not read settings file (%s); using defaults", type(exc).__name__)
            return settings.normalized()
        if not isinstance(raw, dict):
            return settings.normalized()

        known = {f.name for f in fields(AppSettings)}
        for key, value in raw.items():
            if key == "model_map" and isinstance(value, dict):
                for pid, mapping in value.items():
                    if isinstance(mapping, dict):
                        settings.model_map[str(pid)] = {str(k): str(v) for k, v in mapping.items()}
            elif key in known and key != "model_map":
                default = getattr(settings, key)
                if isinstance(value, type(default)):
                    setattr(settings, key, value)
        return settings.normalized()

    def save(self, settings: AppSettings) -> None:
        data = asdict(settings.normalized())
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)


def apply_env_overrides(settings: AppSettings) -> AppSettings:
    """Apply development environment variables on top of saved settings."""
    provider = os.environ.get("AVEN_PROVIDER", "").strip().lower()
    if provider in PROVIDER_IDS:
        settings.provider = provider
    if os.environ.get("AVEN_MODEL", "").strip() in AVEN_MODEL_IDS:
        settings.model = os.environ["AVEN_MODEL"].strip()
    if settings.provider in KEY_PROVIDER_IDS:
        mapping = settings.mapping_for()
        for model_id in AVEN_MODEL_IDS:
            env_name = model_id.upper().replace("-", "_") + "_MODEL"  # e.g. AVEN_ULTRA_MODEL
            value = sanitize_model_id(os.environ.get(env_name))
            if value:
                mapping[model_id] = value
    base_url = os.environ.get("AVEN_BASE_URL", "").strip()
    if base_url and validate_base_url(base_url) is None:
        settings.openai_base_url = base_url
    return settings


def load_dotenv_file(path: Path | None = None) -> int:
    """Minimal ``.env`` loader for development. Existing variables win.

    Only used when running from source; packaged builds never read ``.env``.
    Returns the number of variables set.
    """
    path = path or (project_root() / ".env")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    count = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and value and key not in os.environ:
            os.environ[key] = value
            count += 1
    return count
