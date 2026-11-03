"""Open-source models AVEN Local runs on the user's own computer.

The files and which AVEN model uses which file are defined in the catalog
(``app/data/models.json``). Each download is pinned to an exact repository revision
and verified against its SHA-256 checksum, so a changed or tampered file is rejected.
"""

from __future__ import annotations

from app.config.catalog import LocalBackend, ModelFile, catalog

__all__ = ["DEFAULT_LOCAL_MODEL", "LOCAL_MODELS", "MODEL_FILES", "LocalModel", "ModelFile", "sampling"]

LocalModel = LocalBackend
MODEL_FILES: dict[str, ModelFile] = dict(catalog().files)
# AVEN model -> local model. Several AVEN models may share one download.
LOCAL_MODELS: dict[str, LocalBackend] = {mid: m.local for mid, m in catalog().models.items() if m.local}
DEFAULT_LOCAL_MODEL = "aven-light"


def sampling(local: LocalBackend) -> dict[str, float | int]:
    """Sampling settings for a local model (the model makers' recommendations, from the catalog)."""
    if local.sampling:
        return dict(local.sampling)
    if local.thinking:
        return {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0}
    return {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0}
