"""AVEN's model lineup, as defined in the catalog (``app/data/models.json``).

Users pick an AVEN model in the message box before sending. Each AVEN model is
served by a real model:

* With **AVEN Local** the app runs the open-source model named in the catalog on
  this computer (see :mod:`app.local.models`).
* With **AVEN Cloud** the AVEN AI server decides the mapping, so the app only sends
  the AVEN model id and users need no API key.
* With a personal provider key, the catalog's provider mapping is used; it can be
  edited in Settings → AI Provider → Advanced.

The chat interface only shows AVEN names; Settings and the privacy notice still
state which service processes conversations.
"""

from __future__ import annotations

from app.config.catalog import ModelSpec, catalog

_catalog = catalog()

AvenModel = ModelSpec
AVEN_MODELS: tuple[ModelSpec, ...] = tuple(_catalog.models.values())
AVEN_MODEL_IDS = tuple(m.id for m in AVEN_MODELS)
DEFAULT_AVEN_MODEL = _catalog.categories["aven"].default_model

# Models that were replaced: saved choices are upgraded, old messages keep their name.
LEGACY_MODELS: dict[str, tuple[str, str]] = dict(_catalog.legacy_models)

# Provider model behind each AVEN model when using a personal key. Only providers with
# known, documented model identifiers get defaults.
DEFAULT_MAPPINGS: dict[str, dict[str, str]] = {
    "anthropic": {m.id: m.providers["anthropic"] for m in AVEN_MODELS if "anthropic" in m.providers},
    "openai": {m.id: m.providers["openai"] for m in AVEN_MODELS if "openai" in m.providers},
}

# Reasoning effort per AVEN model (applied only where the provider model supports it).
AVEN_EFFORT: dict[str, str] = {m.id: m.effort for m in AVEN_MODELS if m.effort}


def upgrade_model_id(model_id: str) -> str:
    """Map a replaced model id to its successor (unknown ids are returned unchanged)."""
    return LEGACY_MODELS.get(model_id, (model_id, ""))[0]


def get_aven_model(model_id: str) -> ModelSpec | None:
    return _catalog.models.get(model_id)


def aven_model_name(model_id: str | None) -> str:
    """Display name for a stored model reference, e.g. "AVEN Light 1.1" (falls back to the raw value)."""
    model = get_aven_model(model_id or "")
    if model:
        return model.display_name
    if model_id in LEGACY_MODELS:
        return LEGACY_MODELS[model_id][1]
    return model_id or ""
