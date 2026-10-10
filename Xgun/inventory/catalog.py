"""Read-only cosmetic catalog loaded from ``data/catalog/cosmetics.json``."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from config import paths

ITEM_TYPES = ("outfit", "backpack", "pickaxe", "glider", "emote", "wrap", "banner")
TYPE_LABELS = {
    "outfit": "Outfit", "backpack": "Back Bling", "pickaxe": "Pickaxe", "glider": "Glider",
    "emote": "Emote", "wrap": "Wrap", "banner": "Banner",
}
MODEL_FOLDERS = {"outfit": "characters", "backpack": "backpacks", "pickaxe": "pickaxes", "glider": "gliders"}


@dataclass(frozen=True)
class Rarity:
    key: str
    label: str
    color: str
    order: int

    @property
    def rgba(self) -> tuple[float, float, float, float]:
        return hex_to_rgba(self.color)


@dataclass(frozen=True)
class CosmeticItem:
    id: str
    type: str
    name: str
    rarity: str
    source: str           # default / shop / battle_pass / quest / milestone
    price: int
    description: str
    set: str = ""
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def type_label(self) -> str:
        return TYPE_LABELS.get(self.type, self.type.title())

    @property
    def model_path(self) -> str | None:
        folder = MODEL_FOLDERS.get(self.type)
        return f"{folder}/{self.id}.glb" if folder else None

    @property
    def is_default(self) -> bool:
        return self.source == "default"

    @property
    def purchasable(self) -> bool:
        return self.source == "shop" and self.price > 0


def hex_to_rgba(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    value = value.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b, alpha)


class Catalog:
    def __init__(self, path: Path | None = None):
        raw = json.loads((path or paths.CATALOG_FILE).read_text(encoding="utf-8"))
        self.season = raw["season"]
        self.rarities = {k: Rarity(k, v["label"], v["color"], v["order"]) for k, v in raw["rarities"].items()}
        self.slots: list[str] = raw["slots"]
        self.items: dict[str, CosmeticItem] = {}
        core = {"id", "type", "name", "rarity", "source", "price", "description", "set"}
        for entry in raw["items"]:
            item = CosmeticItem(
                id=entry["id"], type=entry["type"], name=entry["name"], rarity=entry["rarity"],
                source=entry["source"], price=int(entry.get("price", 0)), description=entry["description"],
                set=entry.get("set", ""), extra={k: v for k, v in entry.items() if k not in core})
            if item.id in self.items:
                raise ValueError(f"Duplicate cosmetic id {item.id}")
            if item.type not in ITEM_TYPES or item.rarity not in self.rarities:
                raise ValueError(f"Invalid cosmetic definition {item.id}")
            self.items[item.id] = item

    def get(self, item_id: str) -> CosmeticItem:
        return self.items[item_id]

    def by_type(self, item_type: str) -> list[CosmeticItem]:
        items = [i for i in self.items.values() if i.type == item_type]
        return sorted(items, key=lambda i: (self.rarities[i.rarity].order, i.name))

    def defaults(self) -> list[CosmeticItem]:
        return [i for i in self.items.values() if i.is_default]

    def shop_items(self) -> list[CosmeticItem]:
        return [i for i in self.items.values() if i.purchasable]

    def rarity(self, item: CosmeticItem | str) -> Rarity:
        key = item if isinstance(item, str) else item.rarity
        return self.rarities[key]
