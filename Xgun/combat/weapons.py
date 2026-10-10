"""Weapon definitions (from data/gameplay/weapons.json) and per-instance state."""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field

from config import paths

RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary"]


@dataclass(frozen=True)
class WeaponDef:
    id: str
    name: str
    category: str
    model: str
    damage: float
    fire_rate: float
    automatic: bool
    magazine: int
    reload_time: float
    ammo: str
    pellets: int
    spread_hip: float
    spread_ads: float
    bloom: float
    bloom_max: float
    range: float
    falloff_start: float
    min_falloff: float
    headshot: float
    zoom: float
    recoil: float
    sound: str
    tracer: tuple
    rarities: tuple

    @property
    def hold(self) -> str:
        return "pistol" if self.category == "pistol" else "rifle"


@dataclass(frozen=True)
class ConsumableDef:
    id: str
    name: str
    model: str
    heal: int
    cap: int
    shield: int
    use_time: float
    stack: int
    pickup: int
    rarity: str


class Armory:
    def __init__(self):
        raw = json.loads(paths.WEAPONS_FILE.read_text(encoding="utf-8"))
        self.rarity_mult = raw["rarity_multipliers"]
        self.weapons = {k: WeaponDef(id=k, tracer=tuple(v["tracer"]), rarities=tuple(v["rarities"]),
                                     **{f: v[f] for f in WeaponDef.__dataclass_fields__ if f not in ("id", "tracer", "rarities")})
                        for k, v in raw["weapons"].items()}
        self.ammo = raw["ammo"]
        self.consumables = {k: ConsumableDef(id=k, **v) for k, v in raw["consumables"].items()}
        self.pickaxe = raw["pickaxe"]
        loot = json.loads(paths.LOOT_FILE.read_text(encoding="utf-8"))
        self.loot = loot

    def damage(self, wdef: WeaponDef, rarity: str) -> float:
        return wdef.damage * self.rarity_mult[rarity]["damage"]

    def reload_time(self, wdef: WeaponDef, rarity: str) -> float:
        return wdef.reload_time * self.rarity_mult[rarity]["reload"]

    def roll_weapon(self, rng: random.Random, table: str = "floor") -> "WeaponInstance":
        wid = _weighted(rng, self.loot["weapon_weights"])
        wdef = self.weapons[wid]
        weights = {r: w for r, w in self.loot["rarity_weights"][table].items() if r in wdef.rarities}
        if not weights:
            weights = {wdef.rarities[0]: 1}
        rarity = _weighted(rng, weights)
        return WeaponInstance(wdef, rarity, wdef.magazine)

    def roll_consumable(self, rng: random.Random) -> tuple[str, int]:
        cid = _weighted(rng, self.loot["consumable_weights"])
        return cid, self.consumables[cid].pickup


def _weighted(rng: random.Random, weights: dict) -> str:
    total = sum(weights.values())
    r = rng.uniform(0, total)
    for k, w in weights.items():
        r -= w
        if r <= 0:
            return k
    return next(iter(weights))


@dataclass
class WeaponInstance:
    wdef: WeaponDef
    rarity: str
    in_mag: int
    uid: int = field(default_factory=lambda: random.getrandbits(31))

    @property
    def name(self) -> str:
        return self.wdef.name

    @property
    def rarity_index(self) -> int:
        return RARITY_ORDER.index(self.rarity)


def falloff(wdef: WeaponDef, distance: float) -> float:
    if distance <= wdef.falloff_start:
        return 1.0
    if distance >= wdef.range:
        return wdef.min_falloff
    t = (distance - wdef.falloff_start) / max(1.0, wdef.range - wdef.falloff_start)
    return 1.0 - (1.0 - wdef.min_falloff) * t


def spread_direction(yaw: float, pitch: float, spread_deg: float, rng: random.Random) -> tuple[float, float, float]:
    """Direction from yaw/pitch (degrees; yaw 0 = +Y, positive = left/CCW) with a random cone."""
    if spread_deg > 0:
        r = spread_deg * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        yaw += r * math.cos(a)
        pitch += r * math.sin(a)
    return direction(yaw, pitch)


def direction(yaw: float, pitch: float) -> tuple[float, float, float]:
    y, p = math.radians(yaw), math.radians(pitch)
    cp = math.cos(p)
    return (-math.sin(y) * cp, math.cos(y) * cp, math.sin(p))
