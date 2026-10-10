"""Procedural island heightmap (deterministic per seed).

The terrain is a numpy grid sampled with bilinear interpolation. Points of
interest and roads are flattened so buildings sit level and paths are
walkable. Water level is 0 m; the island is roughly 1 km across.
"""
from __future__ import annotations

import math

import numpy as np

HALF_EXTENT = 600.0      # map spans -600..600 on X and Y
CELL = 3.0               # metres between height samples
ISLAND_RADIUS = 470.0
WATER_LEVEL = 0.0
SEA_FLOOR = -6.0


def _value_noise(n: int, cells: int, rng: np.random.Generator) -> np.ndarray:
    grid = rng.random((cells + 1, cells + 1))
    t = np.linspace(0, cells, n, endpoint=False)
    i0 = np.floor(t).astype(int)
    f = t - i0
    f = f * f * (3 - 2 * f)
    a = grid[i0][:, i0] * (1 - f)[None, :] + grid[i0][:, i0 + 1] * f[None, :]
    b = grid[i0 + 1][:, i0] * (1 - f)[None, :] + grid[i0 + 1][:, i0 + 1] * f[None, :]
    return a * (1 - f)[:, None] + b * f[:, None]


def fbm(n: int, seed: int, base_cells: int = 4, octaves: int = 6, persistence: float = 0.5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.zeros((n, n))
    amp = total = 0.0
    amp = 1.0
    for o in range(octaves):
        out += _value_noise(n, base_cells * 2 ** o, rng) * amp
        total += amp
        amp *= persistence
    return out / total


class Terrain:
    def __init__(self, seed: int = 7):
        self.seed = seed
        self.size = int(round(HALF_EXTENT * 2 / CELL)) + 1
        n = self.size
        coords = np.linspace(-HALF_EXTENT, HALF_EXTENT, n)
        self.xs = coords
        X, Y = np.meshgrid(coords, coords)            # heights[iy, ix]
        dist = np.sqrt(X ** 2 + Y ** 2)
        angle = np.arctan2(Y, X)
        rng = np.random.default_rng(seed)
        phases = rng.uniform(0, 2 * math.pi, 4)
        wobble = sum(np.sin(angle * k + phases[k - 2]) * (26 / k) for k in range(2, 6))
        coast = ISLAND_RADIUS + wobble
        mask = np.clip((coast - dist) / 90.0, 0, 1)
        mask = mask * mask * (3 - 2 * mask)
        hills = fbm(n, seed, 3, 6)
        ridges = 1 - np.abs(fbm(n, seed + 1, 2, 5) * 2 - 1)
        land = 3.0 + hills * 26.0 + ridges ** 3 * 30.0
        self.h = (SEA_FLOOR + (land - SEA_FLOOR) * mask).astype(np.float32)
        self.base = self.h.copy()

    # -- sampling -------------------------------------------------------
    def _index(self, x: float, y: float) -> tuple[int, int, float, float]:
        fx = (x + HALF_EXTENT) / CELL
        fy = (y + HALF_EXTENT) / CELL
        fx = min(max(fx, 0.0), self.size - 1.001)
        fy = min(max(fy, 0.0), self.size - 1.001)
        ix, iy = int(fx), int(fy)
        return ix, iy, fx - ix, fy - iy

    def height(self, x: float, y: float) -> float:
        ix, iy, tx, ty = self._index(x, y)
        h = self.h
        a = h[iy, ix] + (h[iy, ix + 1] - h[iy, ix]) * tx
        b = h[iy + 1, ix] + (h[iy + 1, ix + 1] - h[iy + 1, ix]) * tx
        return float(a + (b - a) * ty)

    def ground(self, x: float, y: float) -> float:
        """Walkable height: shallow water counts as a wade-able floor just under the surface."""
        return max(self.height(x, y), WATER_LEVEL - 1.0)

    def normal(self, x: float, y: float) -> tuple[float, float, float]:
        e = CELL
        dx = self.height(x + e, y) - self.height(x - e, y)
        dy = self.height(x, y + e) - self.height(x, y - e)
        nx, ny, nz = -dx, -dy, 2 * e
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        return nx / length, ny / length, nz / length

    def is_land(self, x: float, y: float, min_height: float = 1.0) -> bool:
        return self.height(x, y) > min_height

    # -- shaping --------------------------------------------------------
    def flatten(self, cx: float, cy: float, radius: float, falloff: float = 25.0, target: float | None = None) -> float:
        """Level a circular area (for a POI). Returns the plateau height."""
        if target is None:
            target = max(2.0, self.height(cx, cy))
        X, Y = np.meshgrid(self.xs, self.xs)
        d = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
        w = np.clip(1 - (d - radius) / falloff, 0, 1)
        w = w * w * (3 - 2 * w)
        self.h = (self.h * (1 - w) + target * w).astype(np.float32)
        return target

    def smooth_path(self, points: list[tuple[float, float]], width: float = 8.0) -> None:
        """Ease the terrain along a road polyline toward a locally averaged height."""
        X, Y = np.meshgrid(self.xs, self.xs)
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            seg = math.hypot(x1 - x0, y1 - y0)
            steps = max(2, int(seg / 6))
            for i in range(steps + 1):
                t = i / steps
                px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                lo = max(0, int((py - width * 2 + HALF_EXTENT) / CELL))
                hi = min(self.size, int((py + width * 2 + HALF_EXTENT) / CELL) + 2)
                lx = max(0, int((px - width * 2 + HALF_EXTENT) / CELL))
                hx = min(self.size, int((px + width * 2 + HALF_EXTENT) / CELL) + 2)
                sub = self.h[lo:hi, lx:hx]
                if sub.size == 0:
                    continue
                target = max(1.0, float(sub.mean()))
                d = np.sqrt((X[lo:hi, lx:hx] - px) ** 2 + (Y[lo:hi, lx:hx] - py) ** 2)
                w = np.clip(1 - (d - width * 0.5) / width, 0, 1) * 0.6
                self.h[lo:hi, lx:hx] = sub * (1 - w) + target * w
