"""AVEN's product catalog: models, categories and release notes, loaded from data files.

Everything that describes *what* AVEN offers lives in ``app/data/*.json`` so it can be
changed without touching code:

* ``models.json``: each AVEN model's display name, version, availability, access tier,
  prompt profile, the on-device model file behind it, and the provider models used with
  a personal key.
* ``categories.json``: the five product categories (AVEN AI, AVEN Python, AVEN Unity,
  AVEN CODE, Made With AVEN), which models they offer and whether they are free or paid.
* ``releases.json``: the What's New entries.

The files are validated when loaded; a broken catalog is a packaging bug, so it fails
loudly instead of half-working. Names of models that were never released are refused.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from app.paths import project_root

MODEL_STATUSES = ("available", "unavailable", "in_development")
ACCESS_LEVELS = ("free", "paid")
CATEGORY_KINDS = ("chat", "studio")
# Never released and must never appear as models, upcoming releases or prices.
RETIRED_NAMES = ("Starter AVEN", "AVEN Energy")


class CatalogError(Exception):
    """The bundled catalog files are missing or inconsistent."""


@dataclass(frozen=True)
class ModelFile:
    """An open-source model file AVEN Local downloads, pinned to a revision and checksum."""

    key: str
    repo: str
    revision: str
    filename: str
    size: int
    sha256: str
    label: str
    license: str
    context: int = 12_288  # context window the engine opens (prompt + history + reply), in tokens

    @property
    def url(self) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{self.filename}"

    @property
    def size_text(self) -> str:
        return f"{self.size / 1_000_000_000:.1f} GB"


@dataclass(frozen=True)
class LocalBackend:
    file: ModelFile
    thinking: bool  # reasons before answering (Qwen "thinking mode")
    max_output: int = 4096  # longest reply in tokens; with thinking it also covers the reasoning
    sampling: dict = field(default_factory=dict)  # temperature, top_p, top_k, min_p…


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str  # e.g. "AVEN Light"
    version: str  # e.g. "1.1"
    description: str
    status: str
    access: str
    released: str  # ISO date of the release that introduced this version
    profile: str  # how this model should work, added to the system prompt
    local: LocalBackend | None
    providers: dict  # personal-key provider -> model id
    effort: str | None  # reasoning effort where the provider supports it
    entitlement: str = ""  # required entitlement when access is "paid"

    @property
    def display_name(self) -> str:
        """Name with version, e.g. "AVEN Light 1.1" (names that carry their version stay as they are)."""
        return self.name if self.version in self.name else f"{self.name} {self.version}"

    @property
    def available(self) -> bool:
        return self.status == "available"


@dataclass(frozen=True)
class CategorySpec:
    id: str
    name: str
    kind: str
    icon: str
    tagline: str
    description: str
    placeholder: str
    suggestions: tuple[str, ...]
    access: str
    entitlement: str
    pricing_note: str
    models: tuple[str, ...]
    default_model: str
    validators: tuple[str, ...]

    @property
    def paid(self) -> bool:
        return self.access == "paid"


@dataclass(frozen=True)
class ReleaseItem:
    title: str
    body: str


@dataclass(frozen=True)
class Release:
    version: str
    date: str
    title: str
    items: tuple[ReleaseItem, ...]


@dataclass(frozen=True)
class Catalog:
    files: dict[str, ModelFile]
    models: dict[str, ModelSpec]
    legacy_models: dict[str, tuple[str, str]]  # old id -> (replacement id, old display name)
    categories: dict[str, CategorySpec]
    releases: tuple[Release, ...]

    def model(self, model_id: str) -> ModelSpec | None:
        return self.models.get(model_id)

    def category(self, category_id: str) -> CategorySpec | None:
        return self.categories.get(category_id)

    def models_for(self, category_id: str) -> list[ModelSpec]:
        category = self.categories.get(category_id)
        return [self.models[m] for m in category.models] if category else []


def _load_json(directory: Path, name: str) -> dict:
    path = directory / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogError(f"Could not read {path}: {exc}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CatalogError(message)


def _check_names(text: str, where: str) -> None:
    for retired in RETIRED_NAMES:
        _require(retired.lower() not in text.lower(), f"{where} mentions {retired!r}, which was never released")


def load_catalog(directory: Path | None = None) -> Catalog:
    directory = directory or (project_root() / "app" / "data")
    models_data = _load_json(directory, "models.json")
    categories_data = _load_json(directory, "categories.json")
    releases_data = _load_json(directory, "releases.json")
    for name, data in (("models.json", models_data), ("categories.json", categories_data)):
        _check_names(json.dumps(data, ensure_ascii=False), name)
    _check_names(json.dumps(releases_data, ensure_ascii=False), "releases.json")

    files: dict[str, ModelFile] = {}
    for key, raw in models_data["files"].items():
        _require(len(raw["revision"]) == 40 and len(raw["sha256"]) == 64, f"model file {key} is not pinned")
        files[key] = ModelFile(key=key, **raw)

    models: dict[str, ModelSpec] = {}
    for raw in models_data["models"]:
        mid = raw["id"]
        _require(mid not in models, f"duplicate model id {mid}")
        _require(raw["status"] in MODEL_STATUSES, f"{mid}: unknown status {raw['status']!r}")
        _require(raw["access"] in ACCESS_LEVELS, f"{mid}: unknown access {raw['access']!r}")
        local = None
        if raw.get("local"):
            lraw = raw["local"]
            _require(lraw["file"] in files, f"{mid}: unknown model file {lraw['file']!r}")
            local = LocalBackend(
                file=files[lraw["file"]],
                thinking=bool(lraw.get("thinking", False)),
                max_output=int(lraw.get("max_output", 4096)),
                sampling=dict(lraw.get("sampling", {})),
            )
        models[mid] = ModelSpec(
            id=mid,
            name=raw["name"],
            version=raw["version"],
            description=raw["description"],
            status=raw["status"],
            access=raw["access"],
            released=raw.get("released", ""),
            profile=raw.get("profile", ""),
            local=local,
            providers=dict(raw.get("providers", {})),
            effort=raw.get("effort"),
            entitlement=raw.get("entitlement", ""),
        )
    legacy = {old: (new, name) for old, (new, name) in models_data.get("legacy", {}).items()}
    for old, (new, _name) in legacy.items():
        _require(new in models and old not in models, f"legacy model {old} must point to a current model")

    categories: dict[str, CategorySpec] = {}
    for raw in categories_data["categories"]:
        cid = raw["id"]
        _require(cid not in categories, f"duplicate category id {cid}")
        _require(raw["kind"] in CATEGORY_KINDS, f"{cid}: unknown kind {raw['kind']!r}")
        _require(raw["access"] in ACCESS_LEVELS, f"{cid}: unknown access {raw['access']!r}")
        _require(raw["access"] != "paid" or bool(raw.get("entitlement")), f"{cid}: paid categories need an entitlement")
        for mid in raw["models"]:
            _require(mid in models, f"{cid}: unknown model {mid}")
        _require(raw["default_model"] in raw["models"], f"{cid}: default model is not offered")
        categories[cid] = CategorySpec(
            id=cid,
            name=raw["name"],
            kind=raw["kind"],
            icon=raw.get("icon", "◆"),
            tagline=raw["tagline"],
            description=raw.get("description", ""),
            placeholder=raw.get("placeholder", ""),
            suggestions=tuple(raw.get("suggestions", ())),
            access=raw["access"],
            entitlement=raw.get("entitlement", ""),
            pricing_note=raw.get("pricing_note", ""),
            models=tuple(raw["models"]),
            default_model=raw["default_model"],
            validators=tuple(raw.get("validators", ())),
        )

    releases = tuple(
        Release(
            version=r["version"],
            date=r["date"],
            title=r["title"],
            items=tuple(ReleaseItem(i["title"], i["body"]) for i in r["items"]),
        )
        for r in releases_data["releases"]
    )
    return Catalog(files, models, legacy, categories, releases)


@cache
def catalog() -> Catalog:
    """The bundled catalog (loaded once)."""
    return load_catalog()
