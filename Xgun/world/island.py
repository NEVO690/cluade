"""Island layout: named locations, buildings, roads, vegetation and loot spots.

Everything is deterministic for a seed and derived from the asset manifest,
so the simulation (collision, loot) and the renderer always agree.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field

from config import paths
from world.collision import Box, CollisionWorld
from world.terrain import Terrain


def load_manifest() -> dict:
    if paths.MODEL_MANIFEST.exists():
        return json.loads(paths.MODEL_MANIFEST.read_text(encoding="utf-8"))
    return {}


@dataclass
class Placement:
    asset: str
    x: float
    y: float
    z: float
    heading: int = 0          # degrees, multiple of 90 for colliding buildings
    scale: float = 1.0
    poi: str = ""


@dataclass
class POI:
    name: str
    x: float
    y: float
    radius: float
    kind: str
    height: float = 0.0


@dataclass
class Entrance:
    poi: str
    building: int
    footprint: tuple[float, float, float, float]   # x0, y0, x1, y1
    door: tuple[float, float]
    base_z: float = 0.0
    routes: list = field(default_factory=list)      # [(floor_z_world, [(x, y), ...])] door -> upper floor

    def contains(self, x: float, y: float, margin: float = 0.0) -> bool:
        x0, y0, x1, y1 = self.footprint
        return x0 - margin < x < x1 + margin and y0 - margin < y < y1 + margin


@dataclass
class IslandLayout:
    terrain: Terrain
    pois: list[POI]
    placements: list[Placement] = field(default_factory=list)
    roads: list[list[tuple[float, float]]] = field(default_factory=list)
    loot_spots: list[tuple[float, float, float]] = field(default_factory=list)
    chest_spots: list[tuple[float, float, float, float]] = field(default_factory=list)
    crate_spots: list[tuple[float, float, float]] = field(default_factory=list)
    ammo_spots: list[tuple[float, float, float]] = field(default_factory=list)
    entrances: list[Entrance] = field(default_factory=list)
    footprints: list[tuple[float, float, float, float]] = field(default_factory=list)
    collision: CollisionWorld | None = None


POI_DEFS = [
    ("Neon Plaza", 0, 10, 70, "town"),
    ("Harbor Point", 330, -40, 60, "harbor"),
    ("Pinewood Lodge", -60, 300, 60, "village"),
    ("Sunset Dunes", -300, -210, 55, "outpost"),
    ("Maple Row", 210, -270, 60, "village"),
    ("Ridge Watch", 230, 230, 45, "lookout"),
    ("Rustyard", -320, 90, 55, "industrial"),
]

BUILDING_SETS = {
    "town": ["env_shop", "env_house_b", "env_shop", "env_gas_station", "env_house_b", "env_house_a", "env_warehouse"],
    "harbor": ["env_warehouse", "env_warehouse", "env_shop", "env_house_a", "env_tower"],
    "village": ["env_house_a", "env_house_b", "env_house_a", "env_house_a", "env_tower", "env_house_b"],
    "outpost": ["env_gas_station", "env_house_a", "env_tower", "env_shop"],
    "lookout": ["env_tower", "env_house_a", "env_tower"],
    "industrial": ["env_warehouse", "env_tower", "env_warehouse", "env_house_b"],
}

# door positions (model space) per building, used by bot navigation
DOORS = {"env_house_a": (0.0, 6.0), "env_house_b": (0.0, 6.0), "env_warehouse": (-4.5, 9.0), "env_shop": (0.0, 6.5),
         "env_gas_station": (1.6, -1.0), "env_tower": (-4.6, -4.5)}


def _rot(x: float, y: float, heading: int) -> tuple[float, float]:
    a = math.radians(heading)
    c, s = round(math.cos(a)), round(math.sin(a))
    return x * c - y * s, x * s + y * c


def _rot_size(sx: float, sy: float, heading: int) -> tuple[float, float]:
    return (sy, sx) if heading % 180 == 90 else (sx, sy)


def build_island(seed: int = 7, manifest: dict | None = None) -> IslandLayout:
    manifest = manifest if manifest is not None else load_manifest()
    rng = random.Random(seed)
    terrain = Terrain(seed)
    pois = [POI(n, x, y, r, k) for n, x, y, r, k in POI_DEFS]
    layout = IslandLayout(terrain, pois)

    # roads: ring of POIs around the central plaza, plus spokes
    hub = pois[0]
    outer = sorted(pois[1:], key=lambda p: math.atan2(p.y, p.x))
    for p in outer:
        layout.roads.append(_road(hub, p, rng))
    for a, b in zip(outer, outer[1:] + outer[:1]):
        if math.hypot(a.x - b.x, a.y - b.y) < 420:
            layout.roads.append(_road(a, b, rng))
    for road in layout.roads:
        terrain.smooth_path(road)
    for p in pois:
        # wide plateau: every building (and its doorway) must sit on level ground
        p.height = terrain.flatten(p.x, p.y, p.radius + 12.0, 30.0)

    collision = CollisionWorld(terrain)
    layout.collision = collision

    def place(asset: str, x: float, y: float, heading: int = 0, poi: str = "", scale: float = 1.0,
              z: float | None = None) -> Placement | None:
        info = manifest.get(asset)
        zz = terrain.height(x, y) if z is None else z
        pl = Placement(asset, x, y, zz, heading, scale, poi)
        layout.placements.append(pl)
        if not info:
            return pl
        for c in info.get("colliders", []):
            cx, cy = _rot(c["center"][0] * scale, c["center"][1] * scale, heading)
            sx, sy = _rot_size(c["size"][0] * scale, c["size"][1] * scale, heading)
            collision.add(Box.from_center((x + cx, y + cy, zz + c["center"][2] * scale),
                                          (sx, sy, c["size"][2] * scale), asset))
        return pl

    # buildings on a jittered ring around each POI centre
    for p in pois:
        assets = BUILDING_SETS[p.kind]
        n = len(assets)
        footprints: list[tuple[float, float, float, float]] = []
        for i, asset in enumerate(assets):
            b = manifest.get(asset, {}).get("bounds", {"min": [-5, -5, 0], "max": [5, 5, 5]})
            spot = None
            for attempt in range(60):
                ring = (0.42 if i % 2 == 0 else 0.68) + 0.05 * (attempt // 12)
                ang = 2 * math.pi * i / n + rng.uniform(-0.15, 0.15) + (attempt % 12) * 0.21
                bx, by = p.x + math.cos(ang) * p.radius * ring, p.y + math.sin(ang) * p.radius * ring
                heading = int(round((math.degrees(math.atan2(p.y - by, p.x - bx)) - 90) / 90.0)) * 90 % 360
                ax0, ay0 = _rot(b["min"][0], b["min"][1], heading)
                ax1, ay1 = _rot(b["max"][0], b["max"][1], heading)
                fp = (bx + min(ax0, ax1), by + min(ay0, ay1), bx + max(ax0, ax1), by + max(ay0, ay1))
                corners_ok = all(math.hypot(cx - p.x, cy - p.y) < p.radius + 8 for cx in fp[0::2] for cy in fp[1::2])
                clear = all(fp[2] + 4 < o[0] or o[2] + 4 < fp[0] or fp[3] + 4 < o[1] or o[3] + 4 < fp[1] for o in footprints)
                if corners_ok and clear:
                    spot = (bx, by, heading, fp)
                    break
            if spot is None:
                continue          # no room left at this location
            bx, by, heading, fp = spot
            footprints.append(fp)
            layout.footprints.append(fp)
            pl = place(asset, bx, by, heading, p.name, z=p.height)
            info = manifest.get(asset, {})
            for lx, ly, lz in info.get("loot_spots", []):
                rx, ry = _rot(lx, ly, heading)
                layout.loot_spots.append((bx + rx, by + ry, p.height + lz))
            for cx, cy, cz, ch in info.get("chest_spots", []):
                rx, ry = _rot(cx, cy, heading)
                layout.chest_spots.append((bx + rx, by + ry, p.height + cz, (ch + heading) % 360))
            b = info.get("bounds")
            if b:
                x0, y0 = _rot(b["min"][0], b["min"][1], heading)
                x1, y1 = _rot(b["max"][0], b["max"][1], heading)
                door = _rot(*DOORS.get(asset, (0.0, 0.0)), heading)
                routes = []
                for r in info.get("nav_routes", []):
                    pts = [_rot(px, py, heading) for px, py in r["points"]]
                    routes.append((p.height + r["to_z"], [(bx + px, by + py) for px, py in pts]))
                layout.entrances.append(Entrance(p.name, len(layout.placements) - 1,
                                                 (bx + min(x0, x1), by + min(y0, y1), bx + max(x0, x1), by + max(y0, y1)),
                                                 (bx + door[0], by + door[1]), p.height, routes))
        # street props
        for k in range(4):
            ang = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(8, p.radius * 0.3)
            x, y = p.x + math.cos(ang) * d, p.y + math.sin(ang) * d
            if any(f[0] - 6 < x < f[2] + 6 and f[1] - 6 < y < f[3] + 6 for f in layout.footprints):
                continue          # never block a doorway
            choice = rng.choice(["env_car", "env_barrel", "env_streetlamp", "env_car"])
            place(choice, x, y, rng.choice((0, 90, 180, 270)), p.name, z=p.height)
        def outside_buildings(x, y):
            return not any(f[0] - 2 < x < f[2] + 2 and f[1] - 2 < y < f[3] + 2 for f in layout.footprints)
        for k in range(3):
            ang = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(10, p.radius * 0.9)
            x, y = p.x + math.cos(ang) * d, p.y + math.sin(ang) * d
            if outside_buildings(x, y):
                layout.crate_spots.append((x, y, p.height))
            ang2 = rng.uniform(0, 2 * math.pi)
            x, y = p.x + math.cos(ang2) * d * 0.8, p.y + math.sin(ang2) * d * 0.8
            if outside_buildings(x, y):
                layout.ammo_spots.append((x, y, p.height))

    # lamps and fences along roads
    for road in layout.roads:
        for (x0, y0), (x1, y1) in zip(road, road[1:]):
            seg = math.hypot(x1 - x0, y1 - y0)
            for t in range(0, int(seg), 60):
                f = t / seg
                x, y = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
                nx, ny = -(y1 - y0) / seg, (x1 - x0) / seg
                if _near_poi(pois, x, y, 15):
                    continue
                place("env_streetlamp", x + nx * 6, y + ny * 6, 0)

    # vegetation scatter
    def free(x, y, clearance):
        if not terrain.is_land(x, y, 1.2) or _near_poi(pois, x, y, clearance):
            return False
        return not any(_dist_to_polyline(x, y, r) < 9 for r in layout.roads)

    for i in range(900):
        x, y = rng.uniform(-470, 470), rng.uniform(-470, 470)
        if not free(x, y, 8):
            continue
        h = terrain.height(x, y)
        if h < 4.0 and rng.random() < 0.6:
            asset = "env_tree_palm"
        elif y > 120 and rng.random() < 0.75:
            asset = "env_tree_pine"
        else:
            asset = rng.choice(["env_tree_oak", "env_tree_oak", "env_tree_pine", "env_bush", "env_bush"])
        place(asset, x, y, rng.choice((0, 90, 180, 270)), scale=rng.uniform(0.85, 1.25), z=h - 0.1)
    for i in range(140):
        x, y = rng.uniform(-470, 470), rng.uniform(-470, 470)
        if free(x, y, 10):
            place(rng.choice(["env_rock_a", "env_rock_b"]), x, y, rng.choice((0, 90, 180, 270)),
                  scale=rng.uniform(0.7, 1.6), z=terrain.height(x, y) - 0.3)
    # wilderness chests
    for i in range(40):
        for _ in range(20):
            x, y = rng.uniform(-430, 430), rng.uniform(-430, 430)
            if free(x, y, 30):
                layout.chest_spots.append((x, y, terrain.height(x, y), rng.choice((0, 90, 180, 270))))
                break
    return layout


def _road(a: POI, b: POI, rng: random.Random) -> list[tuple[float, float]]:
    pts = [(a.x, a.y)]
    mx, my = (a.x + b.x) / 2, (a.y + b.y) / 2
    nx, ny = -(b.y - a.y), b.x - a.x
    length = math.hypot(nx, ny) or 1.0
    bend = rng.uniform(-0.12, 0.12) * length
    pts.append((mx + nx / length * bend, my + ny / length * bend))
    pts.append((b.x, b.y))
    return pts


def _near_poi(pois, x, y, extra) -> bool:
    return any(math.hypot(x - p.x, y - p.y) < p.radius + extra for p in pois)


def _dist_to_polyline(x, y, pts) -> float:
    best = math.inf
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        l2 = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / l2))
        best = min(best, math.hypot(x - (x0 + dx * t), y - (y0 + dy * t)))
    return best
