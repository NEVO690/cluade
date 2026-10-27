"""Skin and rarity definitions loaded from data/skins.json."""

import json
import os
from dataclasses import dataclass, field

from ..paths import DATA_DIR, MODELS_DIR


@dataclass(frozen=True)
class Rarity:
    id: str
    order: int
    color: str
    min_price: int
    max_price: int


@dataclass(frozen=True)
class SkinDefinition:
    id: str
    name: str
    rarity: str
    price: int
    description: str
    colors: dict
    accessory: str = None
    effect: str = None
    glow: bool = False
    unlock: dict = field(default_factory=dict)  # {"level": n, "rank": "SILVER", "achievement": "id"}

    @property
    def model_path(self):
        return os.path.join(MODELS_DIR, "bonk_character.glb")

    @property
    def accessory_path(self):
        return os.path.join(MODELS_DIR, "acc_%s.glb" % self.accessory) if self.accessory else None

    def asset_paths(self):
        paths = [self.model_path]
        if self.accessory_path:
            paths.append(self.accessory_path)
        return paths


class SkinCatalog:
    def __init__(self, path=None):
        path = path or os.path.join(DATA_DIR, "skins.json")
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        self.rarities = {r["id"]: Rarity(r["id"], int(r["order"]), r["color"], int(r["min_price"]),
                                         int(r["max_price"])) for r in raw["rarities"]}
        self.skins = {}
        for s in raw["skins"]:
            if s["rarity"] not in self.rarities:
                raise ValueError("skin %s has unknown rarity %s" % (s["id"], s["rarity"]))
            if s["id"] in self.skins:
                raise ValueError("duplicate skin id %s" % s["id"])
            self.skins[s["id"]] = SkinDefinition(
                id=s["id"], name=s["name"], rarity=s["rarity"], price=int(s["price"]),
                description=s.get("description", ""), colors=dict(s["colors"]),
                accessory=s.get("accessory"), effect=s.get("effect"), glow=bool(s.get("glow")),
                unlock=dict(s.get("unlock") or {}))

    def get(self, skin_id):
        return self.skins.get(skin_id) or self.skins["classic"]

    def __contains__(self, skin_id):
        return skin_id in self.skins

    def ordered(self):
        return sorted(self.skins.values(), key=lambda s: (self.rarities[s.rarity].order, s.price, s.name))

    def by_rarity(self, rarity_id):
        return [s for s in self.ordered() if s.rarity == rarity_id]

    def rarity_of(self, skin):
        return self.rarities[skin.rarity]
