"""Static-world collision: axis-aligned boxes in a spatial hash plus the terrain.

Characters are vertical cylinders. Movement resolves horizontal overlaps by
pushing out along the shallowest axis, steps up ledges up to STEP_HEIGHT,
and lands on box tops (floors, roofs, stairs) as well as the terrain.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from world.terrain import Terrain

CELL = 16.0
STEP_HEIGHT = 0.45


@dataclass(slots=True)
class Box:
    x0: float
    y0: float
    z0: float
    x1: float
    y1: float
    z1: float
    tag: str = ""
    owner: int = -1      # index of a destructible prop, -1 for static

    @classmethod
    def from_center(cls, c, s, tag="", owner=-1) -> "Box":
        return cls(c[0] - s[0] / 2, c[1] - s[1] / 2, c[2] - s[2] / 2, c[0] + s[0] / 2, c[1] + s[1] / 2, c[2] + s[2] / 2,
                   tag, owner)


@dataclass(slots=True)
class RayHit:
    distance: float
    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    box: Box | None = None       # None => terrain


class CollisionWorld:
    def __init__(self, terrain: Terrain):
        self.terrain = terrain
        self.boxes: list[Box] = []
        self.grid: dict[tuple[int, int], list[int]] = {}
        self.disabled: set[int] = set()

    def add(self, box: Box) -> int:
        idx = len(self.boxes)
        self.boxes.append(box)
        for gx in range(int(math.floor(box.x0 / CELL)), int(math.floor(box.x1 / CELL)) + 1):
            for gy in range(int(math.floor(box.y0 / CELL)), int(math.floor(box.y1 / CELL)) + 1):
                self.grid.setdefault((gx, gy), []).append(idx)
        return idx

    def disable(self, idx: int) -> None:
        self.disabled.add(idx)

    def query(self, x0: float, y0: float, x1: float, y1: float):
        seen = set()
        for gx in range(int(math.floor(x0 / CELL)), int(math.floor(x1 / CELL)) + 1):
            for gy in range(int(math.floor(y0 / CELL)), int(math.floor(y1 / CELL)) + 1):
                for idx in self.grid.get((gx, gy), ()):
                    if idx not in seen and idx not in self.disabled:
                        seen.add(idx)
                        yield self.boxes[idx]

    # -- characters -----------------------------------------------------
    def floor_height(self, x: float, y: float, z: float, radius: float) -> float:
        """Highest walkable surface under (x, y) that is not above z + STEP_HEIGHT."""
        best = self.terrain.ground(x, y)
        r = radius * 0.7
        for b in self.query(x - r, y - r, x + r, y + r):
            if b.x0 - r < x < b.x1 + r and b.y0 - r < y < b.y1 + r and b.z1 <= z + STEP_HEIGHT and b.z1 > best:
                best = b.z1
        return best

    def move(self, x: float, y: float, z: float, dx: float, dy: float, radius: float, height: float):
        """Horizontal move with push-out. Returns new (x, y, blocked)."""
        nx, ny = x + dx, y + dy
        blocked = False
        for _ in range(3):
            moved = False
            for b in self.query(nx - radius, ny - radius, nx + radius, ny + radius):
                if b.z1 <= z + STEP_HEIGHT or b.z0 >= z + height:
                    continue  # walkable step or overhead
                if nx + radius <= b.x0 or nx - radius >= b.x1 or ny + radius <= b.y0 or ny - radius >= b.y1:
                    continue
                pen = (nx + radius - b.x0, b.x1 - (nx - radius), ny + radius - b.y0, b.y1 - (ny - radius))
                k = min(range(4), key=lambda i: pen[i])
                if k == 0:
                    nx -= pen[0]
                elif k == 1:
                    nx += pen[1]
                elif k == 2:
                    ny -= pen[2]
                else:
                    ny += pen[3]
                moved = blocked = True
            if not moved:
                break
        return nx, ny, blocked

    def ceiling(self, x: float, y: float, z: float, radius: float, height: float) -> float | None:
        """Lowest box bottom above the head (for jumping into floors)."""
        best = None
        r = radius * 0.7
        for b in self.query(x - r, y - r, x + r, y + r):
            if b.x0 - r < x < b.x1 + r and b.y0 - r < y < b.y1 + r and b.z0 >= z + height - 0.05:
                if best is None or b.z0 < best:
                    best = b.z0
        return best

    # -- rays -----------------------------------------------------------
    def raycast(self, origin, direction, max_dist: float, *, terrain: bool = True) -> RayHit | None:
        ox, oy, oz = origin
        dx, dy, dz = direction
        best: RayHit | None = None
        ex, ey = ox + dx * max_dist, oy + dy * max_dist
        # walk the grid cells along the ray's bounding box (bounded rays keep this cheap)
        for b in self.query(min(ox, ex), min(oy, ey), max(ox, ex), max(oy, ey)):
            t = _ray_box(ox, oy, oz, dx, dy, dz, b)
            if t is not None and t <= max_dist and (best is None or t < best.distance):
                best = RayHit(t, (ox + dx * t, oy + dy * t, oz + dz * t), _box_normal(ox + dx * t, oy + dy * t, oz + dz * t, b), b)
        if terrain:
            limit = best.distance if best else max_dist
            tt = self.ray_terrain(origin, direction, limit)
            if tt is not None and (best is None or tt < best.distance):
                p = (ox + dx * tt, oy + dy * tt, oz + dz * tt)
                best = RayHit(tt, p, self.terrain.normal(p[0], p[1]), None)
        return best

    def ray_terrain(self, origin, direction, max_dist: float, step: float = 2.0) -> float | None:
        ox, oy, oz = origin
        dx, dy, dz = direction
        prev_t, prev_above = 0.0, oz - self.terrain.height(ox, oy)
        if prev_above < 0:
            return 0.0
        t = step
        while t <= max_dist + step:
            tc = min(t, max_dist)
            above = oz + dz * tc - self.terrain.height(ox + dx * tc, oy + dy * tc)
            if above < 0:
                lo, hi = prev_t, tc  # refine by bisection
                for _ in range(6):
                    mid = (lo + hi) / 2
                    if oz + dz * mid - self.terrain.height(ox + dx * mid, oy + dy * mid) < 0:
                        hi = mid
                    else:
                        lo = mid
                return hi
            if tc >= max_dist:
                break
            prev_t, prev_above = tc, above
            t += step
        return None

    def line_of_sight(self, a, b) -> bool:
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 1e-6:
            return True
        hit = self.raycast(a, (dx / dist, dy / dist, dz / dist), dist - 0.3)
        return hit is None


def _ray_box(ox, oy, oz, dx, dy, dz, b: Box) -> float | None:
    tmin, tmax = 0.0, math.inf
    for o, d, lo, hi in ((ox, dx, b.x0, b.x1), (oy, dy, b.y0, b.y1), (oz, dz, b.z0, b.z1)):
        if abs(d) < 1e-9:
            if o < lo or o > hi:
                return None
        else:
            t1, t2 = (lo - o) / d, (hi - o) / d
            if t1 > t2:
                t1, t2 = t2, t1
            tmin, tmax = max(tmin, t1), min(tmax, t2)
            if tmin > tmax:
                return None
    return tmin


def _box_normal(px, py, pz, b: Box):
    d = [(abs(px - b.x0), (-1, 0, 0)), (abs(px - b.x1), (1, 0, 0)), (abs(py - b.y0), (0, -1, 0)),
         (abs(py - b.y1), (0, 1, 0)), (abs(pz - b.z0), (0, 0, -1)), (abs(pz - b.z1), (0, 0, 1))]
    return min(d)[1]
