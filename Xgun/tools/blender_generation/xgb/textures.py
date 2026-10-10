"""Procedural, tileable texture generation (numpy) for Xgun assets.

Detail patterns return a float32 HxW "luminance multiplier" around 1.0 which
is multiplied with a material colour and baked to PNG. Full-colour patterns
(weapon wraps, terrain) return HxWx3 sRGB arrays directly.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from xgb.core import TEX_DIR

SIZE = 256


# ---------------------------------------------------------------- noise ---
def _smooth_upsample(grid: np.ndarray, n: int) -> np.ndarray:
    cells = grid.shape[0]
    t = np.arange(n) * cells / n
    i0 = np.floor(t).astype(int)
    f = t - i0
    f = f * f * (3 - 2 * f)
    i1 = (i0 + 1) % cells
    rows = grid[i0] * (1 - f)[:, None] + grid[i1] * f[:, None]
    return rows[:, i0] * (1 - f)[None, :] + rows[:, i1] * f[None, :]


def fbm(n=SIZE, cells=4, octaves=5, seed=0, persistence=0.5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.zeros((n, n), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        c = cells * 2 ** o
        grid = rng.random((c, c)).astype(np.float32)
        out += _smooth_upsample(grid, n) * amp
        total += amp
        amp *= persistence
    return out / total


def _coords(n=SIZE):
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) / n
    return x, y


def _norm(a, lo=0.75, hi=1.15):
    a = (a - a.min()) / max(1e-6, a.max() - a.min())
    return lo + a * (hi - lo)


# ------------------------------------------------------ detail patterns ---
def p_plain(seed=1):
    return _norm(fbm(cells=8, octaves=3, seed=seed), 0.94, 1.04)


def p_fabric(seed=2):
    x, y = _coords()
    weave = (np.sin(x * 2 * np.pi * 64) * np.sin(y * 2 * np.pi * 64)) * 0.5 + 0.5
    return _norm(weave * 0.25 + fbm(cells=8, seed=seed) * 0.75, 0.82, 1.08)


def p_denim(seed=3):
    x, y = _coords()
    twill = np.sin((x + y) * 2 * np.pi * 48) * 0.5 + 0.5
    streak = fbm(cells=16, octaves=3, seed=seed)
    return _norm(twill * 0.35 + streak * 0.65, 0.78, 1.1)


def p_knit(seed=4):
    x, y = _coords()
    v = np.abs(np.sin(x * 2 * np.pi * 32 + np.abs(np.sin(y * 2 * np.pi * 64)) * 1.6))
    return _norm(v * 0.6 + fbm(cells=8, seed=seed) * 0.4, 0.8, 1.08)


def p_leather(seed=5):
    n = fbm(cells=24, octaves=3, seed=seed)
    cracks = np.abs(n - 0.5) < 0.02
    return _norm(n, 0.85, 1.05) * np.where(cracks, 0.85, 1.0)


def p_rubber(seed=6):
    return _norm(fbm(cells=32, octaves=2, seed=seed), 0.9, 1.03)


def p_brushed(seed=7):
    rng = np.random.default_rng(seed)
    lines = rng.random((SIZE, 1)).astype(np.float32)
    lines = np.repeat(lines, SIZE, axis=1)
    return _norm(lines * 0.6 + fbm(cells=4, seed=seed) * 0.4, 0.86, 1.1)


def p_panel(seed=8):
    x, y = _coords()
    gx = (np.abs(((x * 4) % 1) - 0.5) > 0.485)
    gy = (np.abs(((y * 2) % 1) - 0.5) > 0.49)
    rivets = ((((x * 16) % 1) - 0.5) ** 2 + (((y * 8) % 1) - 0.08) ** 2) < 0.004
    base = _norm(fbm(cells=6, seed=seed), 0.9, 1.06)
    return base * np.where(gx | gy, 0.55, 1.0) * np.where(rivets, 1.2, 1.0)


def p_carbon(seed=9):
    x, y = _coords()
    cx, cy = (x * 32).astype(int), (y * 32).astype(int)
    fx, fy = (x * 32) % 1, (y * 32) % 1
    a = np.where((cx + cy) % 2 == 0, np.sin(fx * np.pi), np.sin(fy * np.pi))
    return _norm(a, 0.6, 1.15)


def p_wood(seed=10):
    x, y = _coords()
    n = fbm(cells=4, octaves=4, seed=seed)
    rings = np.sin((x * 6 + n * 3) * 2 * np.pi * 3) * 0.5 + 0.5
    grain = fbm(cells=32, octaves=2, seed=seed + 1)
    return _norm(rings * 0.55 + grain * 0.45, 0.72, 1.12)


def p_rock(seed=11):
    n = fbm(cells=4, octaves=6, seed=seed, persistence=0.55)
    return _norm(n ** 1.3, 0.6, 1.2)


def p_bark(seed=12):
    x, y = _coords()
    n = fbm(cells=8, octaves=4, seed=seed)
    ridges = np.abs(np.sin(x * 2 * np.pi * 10 + n * 6))
    return _norm(ridges * 0.7 + n * 0.3, 0.55, 1.15)


def p_leaf(seed=13):
    return _norm(fbm(cells=8, octaves=4, seed=seed), 0.75, 1.15)


def p_concrete(seed=14):
    n = fbm(cells=8, octaves=6, seed=seed)
    rng = np.random.default_rng(seed)
    speck = rng.random((SIZE, SIZE)) > 0.985
    return _norm(n, 0.82, 1.08) * np.where(speck, 0.8, 1.0)


def p_plaster(seed=15):
    return _norm(fbm(cells=12, octaves=5, seed=seed), 0.88, 1.06)


def p_brick(seed=16):
    x, y = _coords()
    rows = 8
    row = (y * rows).astype(int)
    xs = (x * 4 + (row % 2) * 0.5) % 1
    ys = (y * rows) % 1
    mortar = (xs < 0.04) | (ys < 0.08)
    rng = np.random.default_rng(seed)
    tint = rng.uniform(0.85, 1.1, (rows, 8))[row % rows, ((x * 4 + (row % 2) * 0.5) * 2).astype(int) % 8]
    base = _norm(fbm(cells=16, octaves=3, seed=seed), 0.88, 1.05) * tint
    return np.where(mortar, 1.35, base)


def p_shingle(seed=17):
    x, y = _coords()
    rows = 10
    row = (y * rows).astype(int)
    xs = (x * 8 + (row % 2) * 0.5) % 1
    ys = (y * rows) % 1
    edge = (xs < 0.05) | (ys > 0.9)
    shade = 1.0 - ys * 0.25
    return np.where(edge, 0.6, shade * _norm(fbm(cells=16, seed=seed), 0.9, 1.06))


def p_asphalt(seed=18):
    rng = np.random.default_rng(seed)
    grit = rng.random((SIZE, SIZE)).astype(np.float32)
    return _norm(fbm(cells=8, seed=seed) * 0.5 + grit * 0.5, 0.8, 1.12)


def p_planks(seed=19):
    x, y = _coords()
    plank = (x * 6).astype(int)
    gap = ((x * 6) % 1) < 0.03
    rng = np.random.default_rng(seed)
    tint = rng.uniform(0.85, 1.12, 6)[plank % 6]
    grain = fbm(cells=32, octaves=3, seed=seed)
    return np.where(gap, 0.5, _norm(grain, 0.85, 1.08) * tint)


def p_camo(seed=20):
    a = fbm(cells=4, octaves=4, seed=seed)
    b = fbm(cells=6, octaves=4, seed=seed + 7)
    v = np.where(a > 0.55, 0.62, np.where(b > 0.52, 1.18, 0.92))
    return v.astype(np.float32)


def p_scales(seed=21):
    x, y = _coords()
    row = (y * 16).astype(int)
    xs = (x * 16 + (row % 2) * 0.5) % 1
    ys = (y * 16) % 1
    d = np.sqrt((xs - 0.5) ** 2 + (ys * 1.2) ** 2)
    return _norm(np.clip(1.0 - d, 0, 1), 0.7, 1.15)


def p_hex(seed=22):
    x, y = _coords()
    q = x * 12
    r = y * 12 * 1.1547
    d = np.minimum(np.abs(np.sin(q * np.pi)), np.abs(np.sin((q * 0.5 + r * 0.866) * np.pi)))
    d = np.minimum(d, np.abs(np.sin((q * 0.5 - r * 0.866) * np.pi)))
    return np.where(d < 0.12, 0.7, 1.04).astype(np.float32)


PATTERNS = {name[2:]: fn for name, fn in globals().items() if name.startswith("p_")}


# ------------------------------------------------------------ baking ------
def _to_srgb(lin: np.ndarray) -> np.ndarray:
    lin = np.clip(lin, 0, 1)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)


def save_png(rgb_srgb: np.ndarray, path: Path) -> Path:
    """Save an HxWx3 (or 4) sRGB float array via Blender's image API."""
    import bpy
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = rgb_srgb.shape[:2]
    if rgb_srgb.shape[2] == 3:
        rgba = np.concatenate([rgb_srgb, np.ones((h, w, 1), np.float32)], axis=2)
    else:
        rgba = rgb_srgb
    img = bpy.data.images.new(path.stem + "_tmp", w, h, alpha=True)
    img.pixels.foreach_set(np.flipud(rgba).astype(np.float32).ravel())
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return path


_BAKED: dict[str, Path] = {}


def baked(pattern: str, rgb_linear, name: str) -> Path:
    key = f"{pattern}:{name}"
    if key in _BAKED:
        return _BAKED[key]
    detail = PATTERNS[pattern]()
    lin = detail[..., None] * np.array(rgb_linear, np.float32)[None, None, :]
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name.lower())
    path = save_png(_to_srgb(lin), TEX_DIR / "generated" / f"{safe}.png")
    _BAKED[key] = path
    return path


# ------------------------------------------------- full-colour textures ----
def wrap_texture(kind: str) -> np.ndarray:
    x, y = _coords()
    if kind == "carbon":
        v = p_carbon()
        c = np.stack([v * 0.09, v * 0.09, v * 0.1], -1)
    elif kind == "neon_grid":
        gx = np.minimum(np.abs((x * 8) % 1 - 0.5), np.abs((y * 8) % 1 - 0.5))
        line = np.clip(1 - gx * 18, 0, 1)
        grad = y
        c = np.stack([0.05 + 0.6 * grad, np.full_like(grad, 0.02), 0.18 + 0.2 * (1 - grad)], -1)
        c = c * (1 - line[..., None]) + np.stack([1.0 * line, 0.2 * line, 0.9 * line], -1)
        c += np.stack([0 * line, 0.8 * line * (1 - grad), 1.0 * line * (1 - grad)], -1) * 0.5
    elif kind == "frost":
        n = fbm(cells=6, octaves=6, seed=31)
        cracks = np.clip(1 - np.abs(fbm(cells=8, octaves=3, seed=32) - 0.5) * 25, 0, 1)
        c = np.stack([0.55 + n * 0.3, 0.75 + n * 0.2, 0.95 + n * 0.05], -1) + cracks[..., None] * 0.35
    elif kind == "magma":
        n = fbm(cells=4, octaves=5, seed=41)
        cracks = np.clip(1 - np.abs(fbm(cells=6, octaves=4, seed=42) - 0.5) * 12, 0, 1) ** 2
        rock = np.stack([0.08 + n * 0.08, 0.05 + n * 0.05, 0.05 + n * 0.04], -1)
        glow = np.stack([1.0 * cracks, 0.35 * cracks, 0.02 * cracks], -1)
        c = rock + glow
    elif kind == "gold_rush":
        n = fbm(cells=8, octaves=4, seed=51)
        engrave = (np.sin((x + y) * 2 * np.pi * 10 + n * 4) > 0.92)
        c = np.stack([0.95 + n * 0.05, 0.72 + n * 0.1, 0.25 + n * 0.1], -1) * np.where(engrave, 0.65, 1.0)[..., None]
    else:
        raise KeyError(kind)
    return np.clip(c, 0, 1).astype(np.float32)


def terrain_texture(kind: str) -> np.ndarray:
    n = fbm(cells=8, octaves=6, seed={"grass": 61, "sand": 62, "rock": 63, "dirt": 64}[kind])
    fine = fbm(cells=64, octaves=2, seed=65)
    m = (n * 0.6 + fine * 0.4)[..., None]
    base = {"grass": (0.28, 0.52, 0.2), "sand": (0.86, 0.78, 0.58), "rock": (0.5, 0.48, 0.46),
            "dirt": (0.45, 0.34, 0.24)}[kind]
    return np.clip(np.array(base, np.float32) * (0.75 + m * 0.5), 0, 1).astype(np.float32)
