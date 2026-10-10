"""Shared texture sets: weapon wraps and terrain splat textures used directly by the game."""
from __future__ import annotations

from xgb import textures
from xgb.core import TEX_DIR


def build_textures() -> None:
    for kind in ("carbon", "neon_grid", "frost", "magma", "gold_rush"):
        textures.save_png(textures.wrap_texture(kind), TEX_DIR / "wraps" / f"wrap_{kind}.png")
    for kind in ("grass", "sand", "rock", "dirt"):
        textures.save_png(textures.terrain_texture(kind), TEX_DIR / "terrain" / f"{kind}.png")
    road = textures._to_srgb(textures.p_asphalt()[..., None] * 0.18)
    import numpy as np
    road = np.repeat(road, 3, axis=2)
    x = np.arange(textures.SIZE)
    lane = (np.abs(x - textures.SIZE / 2) < 3)[None, :] & ((np.arange(textures.SIZE) // 32) % 2 == 0)[:, None]
    road[lane] = (0.95, 0.85, 0.3)
    textures.save_png(road.astype(np.float32), TEX_DIR / "terrain" / "road.png")
