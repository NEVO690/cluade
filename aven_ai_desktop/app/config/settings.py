"""User settings: theme, provider and model configuration.

Settings are stored as JSON in the user data directory. API keys are *never*
written here - see :mod:`app.config.secrets`.

Environment variables (useful for development, also read by packaged builds)
take precedence over saved values for the current session only:

* ``AVEN_PROVIDER``     - ``anthropic`` or ``openai``
* ``AVEN_MODEL``        - model used by AVEN mode
* ``AVEN_CODE_MODEL``   - model used by AVEN CODE mode
* ``AVEN_BASE_URL``     - custom HTTPS base URL for the OpenAI provider
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from app.paths import project_root, settings_path

log = logging.getLogger(__name__)

THEMES = ("system", "light", "dark")
PROVIDER_IDS = ("anthropic", "openai")

# Defaults applied only for providers where we know a current, documented model
# identifier. Users can always enter any model their account has access to.
DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-opus-5-5",
    "openai": "",
}

MIN_MAX_TOKENS = 256
MAX_MAX_TOKENS = 128_000
MIN_TIMEOUT = 10
MAX_TIMEOUT = 1800


@dataclass
class ProviderModels:
    aven_model: str = ""
    aven_code_model: str = ""


@dataclass
class AppSettings:
    theme: str = "system"
    provider: str = "anthropic"
    # Per-provider model selection so switching providers keeps each one's choice.
    models: dict[str, ProviderModels] = field(
        default_factory=lambda: {pid: ProviderModels(DEFAULT_MODELS[pid], DEFAULT_MODELS[pid]) for pid in PROVIDER_IDS}
    )
    openai_base_url: str = ""
    max_tokens: int = 32_000
    request_timeout: int = 600
    send_with_enter: bool = True
    window_geometry: str = ""

    # --- convenience accessors -------------------------------------------------
    def models_for(self, provider: str | None = None) -> ProviderModels:
        pid = provider or self.provider
        if pid not in self.models:
            self.models[pid] = ProviderModels(DEFAULT_MODELS.get(pid, ""), DEFAULT_MODELS.get(pid, ""))
        return self.models[pid]

    def model_for_mode(self, mode: str) -> str:
        models = self.models_for()
        return models.aven_code_model if mode == "code" else models.aven_model

    # --- validation ------------------------------------------------------------
    def normalized(self) -> AppSettings:
        if self.theme not in THEMES:
            self.theme = "system"
        if self.provider not in PROVIDER_IDS:
            self.provider = "anthropic"
        self.max_tokens = _clamp(self.max_tokens, MIN_MAX_TOKENS, MAX_MAX_TOKENS, 32_000)
        self.request_timeout = _clamp(self.request_timeout, MIN_TIMEOUT, MAX_TIMEOUT, 600)
        self.openai_base_url = (self.openai_base_url or "").strip()
        for pid in PROVIDER_IDS:
            m = self.models_for(pid)
            m.aven_model = sanitize_model_id(m.aven_model)
            m.aven_code_model = sanitize_model_id(m.aven_code_model)
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
            if key == "models" and isinstance(value, dict):
                for pid, models in value.items():
                    if isinstance(models, dict):
                        settings.models[pid] = ProviderModels(
                            str(models.get("aven_model", "")), str(models.get("aven_code_model", ""))
                        )
            elif key in known and key != "models":
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
    models = settings.models_for()
    if os.environ.get("AVEN_MODEL"):
        models.aven_model = sanitize_model_id(os.environ["AVEN_MODEL"])
    if os.environ.get("AVEN_CODE_MODEL"):
        models.aven_code_model = sanitize_model_id(os.environ["AVEN_CODE_MODEL"])
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
