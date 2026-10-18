"""AVEN's own model lineup.

Users choose between AVEN models (Swift, Core, Ultra). Each one is a tier that
maps to a real model at the configured AI provider; the mapping is editable in
Settings → AI Provider → Advanced. The chat interface only shows AVEN names,
while Settings and the privacy notice still state which provider processes
the conversation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AvenModel:
    id: str
    name: str
    description: str


AVEN_MODELS: tuple[AvenModel, ...] = (
    AvenModel("aven-swift", "AVEN Swift", "Fastest replies for everyday questions."),
    AvenModel("aven-core", "AVEN Core", "Balanced speed and quality."),
    AvenModel("aven-ultra", "AVEN Ultra", "Most capable, for complex reasoning, writing and code."),
)
AVEN_MODEL_IDS = tuple(m.id for m in AVEN_MODELS)
DEFAULT_AVEN_MODEL = "aven-ultra"

# Default provider model behind each AVEN model. Only providers with known,
# documented model identifiers get defaults; others are mapped by the user.
DEFAULT_MAPPINGS: dict[str, dict[str, str]] = {
    "anthropic": {
        "aven-swift": "claude-haiku-5-5",
        "aven-core": "claude-sonnet-5-5",
        "aven-ultra": "claude-opus-5-5",
    },
    "openai": {},
}


def get_aven_model(model_id: str) -> AvenModel | None:
    return next((m for m in AVEN_MODELS if m.id == model_id), None)


def aven_model_name(model_id: str | None) -> str:
    """Display name for a stored model reference (falls back to the raw value)."""
    model = get_aven_model(model_id or "")
    return model.name if model else (model_id or "")
