"""Plain-data entities of a match. No rendering code lives here."""
from __future__ import annotations

from dataclasses import dataclass, field

from inventory.match_inventory import Item, MatchInventory

RADIUS = 0.4
HEIGHT = 1.85
CROUCH_HEIGHT = 1.25
EYE = 1.62
CROUCH_EYE = 1.08


@dataclass
class ControlInput:
    """Everything a player or bot can ask for in one tick (network-friendly)."""
    move_x: float = 0.0          # strafe right (+) / left (-)
    move_y: float = 0.0          # forward (+) / back (-)
    yaw: float = 0.0             # degrees, 0 = +Y, positive = turn left
    pitch: float = 0.0           # degrees, positive = look up
    jump: bool = False
    sprint: bool = False
    crouch: bool = False
    fire: bool = False
    fire_pressed: bool = False   # edge-triggered press for semi-automatic weapons
    aim: bool = False
    reload: bool = False
    interact: bool = False
    select: int | None = None    # 0..5
    cycle: int = 0               # -1 / +1 (mouse wheel)
    deploy: bool = False         # leave the drop ship / open glider
    emote: str | None = None
    build_toggle: bool = False   # enter / leave build mode
    build_piece: str | None = None   # wall / floor / ramp
    build_material_next: bool = False


@dataclass
class Stats:
    eliminations: int = 0
    damage: int = 0
    chests: int = 0
    healed: int = 0
    pickaxe_hits: int = 0
    glide_secs: float = 0.0
    sniper_hits: int = 0
    survive_secs: float = 0.0


@dataclass
class Combatant:
    id: int
    name: str
    is_bot: bool
    loadout: dict
    inventory: MatchInventory
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    health: float = 100.0
    shield: float = 0.0
    state: str = "bus"           # bus / skydive / glide / ground / dead
    on_ground: bool = False
    crouching: bool = False
    sprinting: bool = False
    aiming: bool = False
    moving: bool = False
    fire_cooldown: float = 0.0
    bloom: float = 0.0
    reload_timer: float = 0.0
    use_timer: float = 0.0
    use_slot: int = 0
    interact_timer: float = 0.0
    interact_target: tuple | None = None
    emote: str | None = None
    emote_timer: float = 0.0
    placement: int = 0
    killer: int | None = None
    death_time: float = 0.0
    stats: Stats = field(default_factory=Stats)
    prev: tuple = (0.0, 0.0, 0.0)
    last_damage_time: float = -99.0
    storm_tick: float = 0.0
    landed_time: float = -1.0
    action: str = ""             # transient animation cue: fire / reload / swing / use / build
    materials: dict = field(default_factory=lambda: {"wood": 0, "stone": 0, "metal": 0})
    build_mode: bool = False
    build_piece: str = "wall"
    build_material: str = "wood"

    @property
    def alive(self) -> bool:
        return self.state != "dead"

    @property
    def height(self) -> float:
        return CROUCH_HEIGHT if self.crouching else HEIGHT

    @property
    def eye(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z + (CROUCH_EYE if self.crouching else EYE))

    @property
    def pos(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class GroundItem:
    id: int
    kind: str                    # weapon / consumable / ammo
    payload: Item | tuple        # WeaponInstance / ConsumableStack / (ammo kind, amount)
    x: float
    y: float
    z: float
    spawn_time: float = 0.0


@dataclass
class Container:
    id: int
    kind: str                    # chest / ammo_box / crate
    x: float
    y: float
    z: float
    heading: float = 0.0
    opened: bool = False
    hp: float = 100.0
    box_index: int = -1          # collision box (crates are destructible)
    open_time: float = -1.0
