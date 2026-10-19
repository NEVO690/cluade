"""AVEN's own model lineup.

Users pick an AVEN model in the message box before sending. Each AVEN model is
served by a real model:

* With **AVEN Local** the app runs an open-source model on this computer
  (see :mod:`app.local.models`).
* With **AVEN Cloud** the AVEN AI server decides the mapping, so the app only
  sends the AVEN model id and users need no API key.
* With a personal provider key, the mapping below is used and can be edited in
  Settings → AI Provider → Advanced.

The chat interface only shows AVEN names; Settings and the privacy notice still
state which service processes conversations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AvenModel:
    id: str
    name: str
    description: str


AVEN_MODELS: tuple[AvenModel, ...] = (
    AvenModel(
        "aven-1-1",
        "AVEN 1.1",
        "Our best everyday model: far smarter than Light and Core, close to Ultra, and faster.",
    ),
    AvenModel("aven-ultra", "AVEN Ultra", "Thinks longer for the hardest questions, research and code."),
    AvenModel("aven-core", "AVEN Core", "Balanced speed and quality for everyday work."),
    AvenModel("aven-light", "AVEN Light", "The fastest replies for quick questions."),
)
AVEN_MODEL_IDS = tuple(m.id for m in AVEN_MODELS)
DEFAULT_AVEN_MODEL = "aven-1-1"

# Models that were replaced: saved choices are upgraded, old messages keep their name.
LEGACY_MODELS: dict[str, tuple[str, str]] = {
    "aven-1": ("aven-1-1", "AVEN 1.0"),  # old id -> (replacement, display name)
}

# Provider model behind each AVEN model when using a personal key. Only
# providers with known, documented model identifiers get defaults.
DEFAULT_MAPPINGS: dict[str, dict[str, str]] = {
    "anthropic": {
        "aven-1-1": "claude-opus-5-5",
        "aven-ultra": "claude-opus-5-5",
        "aven-core": "claude-sonnet-5-5",
        "aven-light": "claude-haiku-5-5",
    },
    "openai": {},
}

# Reasoning effort per AVEN model (applied only where the provider model supports it).
# AVEN 1.1 reasons more than the old AVEN 1.0 (which used the default); Ultra reasons the most.
AVEN_EFFORT: dict[str, str] = {"aven-1-1": "high", "aven-ultra": "xhigh"}


def upgrade_model_id(model_id: str) -> str:
    """Map a replaced model id to its successor (unknown ids are returned unchanged)."""
    return LEGACY_MODELS.get(model_id, (model_id, ""))[0]


def get_aven_model(model_id: str) -> AvenModel | None:
    return next((m for m in AVEN_MODELS if m.id == model_id), None)


def aven_model_name(model_id: str | None) -> str:
    """Display name for a stored model reference (falls back to the raw value)."""
    model = get_aven_model(model_id or "")
    if model:
        return model.name
    if model_id in LEGACY_MODELS:
        return LEGACY_MODELS[model_id][1]
    return model_id or ""
