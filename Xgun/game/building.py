"""Building: harvested materials and grid-snapped walls, floors and ramps.

Pure simulation data (no rendering). Pieces are made of axis-aligned
collision boxes so the existing movement / bullet code handles them: a ramp
is a run of shallow steps that characters can walk up.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

GRID = 4.0
PIECE_HEIGHT = 4.0
COST = 10
MAX_MATERIAL = 999
MAX_PIECES = 800
RAMP_STEPS = 13
PIECES = ("wall", "floor", "ramp")
MATERIALS = ("wood", "stone", "metal")
HP = {"wood": 150, "stone": 300, "metal": 450}

# what a pickaxe hit yields, by the asset the collision box belongs to
HARVEST = {
    "env_tree_oak": ("wood", 12), "env_tree_pine": ("wood", 12), "env_tree_palm": ("wood", 10), "env_bush": ("wood", 5),
    "env_fence": ("wood", 6), "env_house_a": ("wood", 6), "env_house_b": ("stone", 6), "env_shop": ("stone", 6),
    "env_tower": ("wood", 8), "env_rock_a": ("stone", 12), "env_rock_b": ("stone", 12), "env_car": ("metal", 10),
    "env_barrel": ("metal", 8), "env_streetlamp": ("metal", 6), "env_warehouse": ("metal", 6),
    "env_gas_station": ("metal", 6),
}

# yaw quadrant -> unit grid direction (yaw 0 = +Y, 90 = -X, 180 = -Y, 270 = +X)
DIRS = {0: (0, 1), 1: (-1, 0), 2: (0, -1), 3: (1, 0)}


def facing(yaw: float) -> int:
    return int(round((yaw % 360) / 90.0)) % 4


def cell_of(x: float, y: float) -> tuple[int, int]:
    return int(math.floor(x / GRID)), int(math.floor(y / GRID))


def cell_center(ix: int, iy: int) -> tuple[float, float]:
    return (ix + 0.5) * GRID, (iy + 0.5) * GRID


@dataclass
class BuildPiece:
    id: int
    kind: str
    material: str
    ix: int
    iy: int
    z: float
    direction: int
    owner: int
    hp: float = 0.0
    max_hp: float = 0.0
    boxes: list[int] = field(default_factory=list)

    @property
    def key(self):
        return piece_key(self.kind, self.ix, self.iy, self.z, self.direction)


def piece_key(kind, ix, iy, z, direction):
    return kind, ix, iy, int(round(z * 2)), direction if kind != "floor" else 0


def target_for(kind: str, x: float, y: float, z: float, yaw: float, pitch: float) -> tuple[int, int, float, int]:
    """Where a piece goes for a builder at (x, y, z) looking along yaw/pitch."""
    d = facing(yaw)
    ix, iy = cell_of(x, y)
    if kind == "wall":
        return ix, iy, z, d
    dx, dy = DIRS[d]
    level = z + (PIECE_HEIGHT if kind == "floor" and pitch > 35 else 0.0)
    return ix + dx, iy + dy, level, d


def piece_boxes(kind: str, ix: int, iy: int, z: float, direction: int) -> list[tuple[tuple, tuple]]:
    """(center, size) collision boxes for a piece."""
    cx, cy = cell_center(ix, iy)
    dx, dy = DIRS[direction]
    if kind == "wall":
        center = (cx + dx * GRID / 2, cy + dy * GRID / 2, z + PIECE_HEIGHT / 2)
        size = (GRID, 0.3, PIECE_HEIGHT) if dy else (0.3, GRID, PIECE_HEIGHT)
        return [(center, size)]
    if kind == "floor":
        return [((cx, cy, z - 0.1), (GRID, GRID, 0.2))]
    boxes = []
    run = GRID / RAMP_STEPS
    for k in range(RAMP_STEPS):
        h = (k + 1) * PIECE_HEIGHT / RAMP_STEPS
        along = -GRID / 2 + (k + 0.5) * run
        center = (cx + dx * along, cy + dy * along, z + h / 2)
        size = (GRID, run, h) if dy else (run, GRID, h)
        boxes.append((center, size))
    return boxes
