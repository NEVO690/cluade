"""Island environment kit: buildings with enterable interiors, vegetation, props,
the drop ship and the lobby stage.

Buildings export their collision as axis-aligned boxes (``colliders``) plus
``loot_spots`` / ``chest_spots`` in the manifest, so gameplay collision
always matches the art.
"""
from __future__ import annotations

import math
import random

from mathutils import Vector

from xgb import core

M = core.material
WALL_T = 0.25


class Kit:
    """Collects visual parts plus matching colliders and spawn markers."""

    def __init__(self):
        self.parts = []
        self.colliders = []
        self.loot = []
        self.chests = []

    def box(self, name, size, loc, mat, collide=True, bevel=0.0, rot=(0, 0, 0)):
        self.parts.append(core.box(name, size, loc, rot, mat, bevel=bevel))
        if collide:
            self.colliders.append({"center": [round(c, 3) for c in loc], "size": [round(c, 3) for c in size]})
        return self.parts[-1]

    def add(self, *objs):
        self.parts.extend(objs)

    def wall(self, axis, fixed, a0, a1, z0, height, mat, openings=(), thickness=WALL_T, glass=None):
        """Wall along ``axis`` ('x' or 'y') from a0..a1 at the other coordinate ``fixed``.

        openings: [(start, end, bottom, top)] in wall coordinates (doors/windows)."""
        cuts = sorted(openings)
        segments = []
        cursor = a0
        for s, e, b, t in cuts:
            if s > cursor:
                segments.append((cursor, s, z0, z0 + height))
            if b > 0:
                segments.append((s, e, z0, z0 + b))
            if t < height:
                segments.append((s, e, z0 + t, z0 + height))
            if glass is not None and b > 0:
                mid = (s + e) / 2
                loc = (mid, fixed, z0 + (b + t) / 2) if axis == "x" else (fixed, mid, z0 + (b + t) / 2)
                size = (e - s, 0.03, t - b) if axis == "x" else (0.03, e - s, t - b)
                self.box("glass", size, loc, glass, collide=False)
            cursor = e
        if cursor < a1:
            segments.append((cursor, a1, z0, z0 + height))
        for s, e, zb, zt in segments:
            length, h = e - s, zt - zb
            if length <= 0.01 or h <= 0.01:
                continue
            mid = (s + e) / 2
            loc = (mid, fixed, (zb + zt) / 2) if axis == "x" else (fixed, mid, (zb + zt) / 2)
            size = (length, thickness, h) if axis == "x" else (thickness, length, h)
            self.box("wall", size, loc, mat)

    def floor(self, x0, x1, y0, y1, z, mat, thickness=0.2, collide=True):
        self.box("floor", (x1 - x0, y1 - y0, thickness), ((x0 + x1) / 2, (y0 + y1) / 2, z - thickness / 2), mat,
                 collide=collide)

    def stairs(self, x, y0, y1, z0, z1, width, mat, axis="y"):
        steps = max(2, int(round((z1 - z0) / 0.3)))
        run = (y1 - y0) / steps
        for i in range(steps):
            h = (i + 1) * (z1 - z0) / steps
            if axis == "y":
                self.box(f"step{i}", (width, abs(run), h), (x, y0 + run * (i + 0.5), z0 + h / 2), mat)
            else:
                self.box(f"step{i}", (abs(run), width, h), (y0 + run * (i + 0.5), x, z0 + h / 2), mat)


def gable_roof(kit, x0, x1, y0, y1, z, rise, mat, trim=None, overhang=0.4):
    w = (x1 - x0) + overhang * 2
    d = (y1 - y0) / 2 + overhang
    slope = math.degrees(math.atan2(rise, d))
    length = math.hypot(rise, d)
    cx = (x0 + x1) / 2
    for s in (1, -1):
        y_mid = (y0 + y1) / 2 + s * d / 2
        kit.add(core.box("roof", (w, length, 0.14), (cx, y_mid, z + rise / 2), (s * slope, 0, 0), mat))
    # gable triangles
    for x in (x0, x1):
        kit.add(core.prism("gable", [(y0, 0), (y1, 0), ((y0 + y1) / 2, rise)], WALL_T, (x, 0, z), mat=trim or mat, axis="X"))
    # flat collider at the eaves so bullets and players stop at the roof
    kit.colliders.append({"center": [cx, (y0 + y1) / 2, z + rise * 0.45], "size": [x1 - x0, y1 - y0, rise * 0.9]})


# ---------------------------------------------------------------- buildings
def env_house_a():
    k = Kit()
    plaster = M("house_a_plaster", "#e9d8a6", rough=0.9, texture="plaster", tex_scale=0.5)
    trim = M("house_a_trim", "#f8f9fa", rough=0.6, texture="plain")
    roof = M("house_a_roof", "#ae2012", rough=0.8, texture="shingle", tex_scale=0.5)
    floor = M("house_a_floor", "#9c6644", rough=0.7, texture="planks", tex_scale=0.4)
    glass = M("house_glass", "#a9d6e5", rough=0.05, metal=0.2, alpha=0.35)
    door = M("house_a_door", "#005f73", rough=0.5, texture="planks", tex_scale=1)
    stone = M("house_a_stone", "#6c757d", rough=0.9, texture="brick", tex_scale=0.5)
    W, D, H = 10.0, 8.0, 3.2
    x0, x1, y0, y1 = -W / 2, W / 2, -D / 2, D / 2
    k.floor(x0, x1, y0, y1, 0.3, floor)
    k.box("foundation", (W + 0.3, D + 0.3, 0.3), (0, 0, 0.0), stone, collide=False)
    win = (1.0, 1.0, 1.0, 2.1)
    k.wall("x", y1, x0, x1, 0.3, H, plaster, [(-3.2, -1.8, *win[2:]), (-0.6, 0.6, 0, 2.3), (1.8, 3.2, *win[2:])], glass=glass)
    k.wall("x", y0, x0, x1, 0.3, H, plaster, [(-3.0, -1.6, 1.0, 2.1), (1.4, 2.6, 0, 2.3)], glass=glass)
    k.wall("y", x0, y0 + WALL_T / 2, y1 - WALL_T / 2, 0.3, H, plaster, [(-1.0, 1.0, 1.0, 2.1)], glass=glass)
    k.wall("y", x1, y0 + WALL_T / 2, y1 - WALL_T / 2, 0.3, H, plaster, [(-1.0, 1.0, 1.0, 2.1)], glass=glass)
    # interior partition with doorway
    k.wall("y", 1.0, y0 + WALL_T / 2, y1 - WALL_T / 2, 0.3, H, plaster, [(-0.5, 0.5, 0, 2.3)], thickness=0.15)
    gable_roof(k, x0, x1, y0, y1, 0.3 + H, 2.2, roof, plaster)
    k.add(core.box("chimney", (0.8, 0.8, 2.4), (3.0, -1.5, 0.3 + H + 1.6), (0, 0, 0), stone))
    # porch
    k.box("porch", (3.2, 1.6, 0.25), (0, y1 + 0.8, 0.125), stone)
    k.add(core.box("porch_roof", (3.4, 1.8, 0.12), (0, y1 + 0.8, 2.85), (-8, 0, 0), trim))
    for s in (1, -1):
        k.box("porch_post", (0.16, 0.16, 2.6), (1.5 * s, y1 + 1.5, 1.55), trim)
    k.add(core.box("front_door", (1.1, 0.06, 2.2), (0.55, y1 + 0.3, 1.4), (0, 0, -70), door))
    for x in (-2.5, 2.5):
        k.add(core.box("trim", (1.6, 0.1, 0.12), (x, y1 + 0.12, 2.45), (0, 0, 0), trim))
    k.loot += [(-3.0, 1.5, 0.3), (3.0, 2.5, 0.3), (-1.5, -2.5, 0.3)]
    k.chests += [(3.6, -2.8, 0.3, 180)]
    return k


def env_house_b():
    k = Kit()
    brick = M("house_b_brick", "#9d4b3e", rough=0.9, texture="brick", tex_scale=0.5)
    concrete = M("house_b_concrete", "#adb5bd", rough=0.9, texture="concrete", tex_scale=0.3)
    floor = M("house_b_floor", "#ddb892", rough=0.7, texture="planks", tex_scale=0.4)
    glass = M("house_glass", "#a9d6e5", rough=0.05, metal=0.2, alpha=0.35)
    rail = M("house_b_rail", "#343a40", metal=0.8, rough=0.4)
    W, D, H = 9.0, 9.0, 3.0
    x0, x1, y0, y1 = -W / 2, W / 2, -D / 2, D / 2
    k.floor(x0, x1, y0, y1, 0.2, floor)
    for level, z in enumerate((0.2, 0.2 + H)):
        door = [(-0.6, 0.6, 0, 2.3)] if level == 0 else [(-0.6, 0.6, 0, 2.3)]
        k.wall("x", y1, x0, x1, z, H, brick, door + [(-3.6, -2.0, 1.0, 2.2), (2.0, 3.6, 1.0, 2.2)], glass=glass)
        k.wall("x", y0, x0, x1, z, H, brick, [(-3.0, -1.8, 1.0, 2.2), (1.8, 3.0, 1.0, 2.2)], glass=glass)
        k.wall("y", x0, y0 + WALL_T / 2, y1 - WALL_T / 2, z, H, brick, [(-1.0, 1.0, 1.0, 2.2)], glass=glass)
        k.wall("y", x1, y0 + WALL_T / 2, y1 - WALL_T / 2, z, H, brick, [(-1.0, 1.0, 1.0, 2.2)], glass=glass)
    # upper floor with a stair opening
    k.floor(x0, x1, y0, 1.0, 0.2 + H, floor)
    k.floor(x0, 1.0, 1.0, y1, 0.2 + H, floor)
    # stairs climb toward -Y inside the floor opening and land on the upper floor at y < 1
    k.stairs(3.2, 4.3, 1.0, 0.2, 0.2 + H, 1.4, floor)
    # flat roof with parapet
    k.floor(x0, x1, y0, y1, 0.2 + 2 * H + 0.2, concrete)
    for (ax, fixed, a0, a1) in (("x", y1, x0, x1), ("x", y0, x0, x1), ("y", x0, y0, y1), ("y", x1, y0, y1)):
        k.wall(ax, fixed, a0, a1, 0.2 + 2 * H + 0.2, 0.7, concrete, thickness=0.3)
    # balcony on the first floor front
    k.box("balcony", (3.0, 1.4, 0.2), (0, y1 + 0.7, 0.2 + H - 0.1), concrete)
    for i in range(7):
        k.box(f"baluster{i}", (0.05, 0.05, 1.0), (-1.4 + i * 0.466, y1 + 1.35, 0.2 + H + 0.5), rail, collide=False)
    k.box("handrail", (3.0, 0.08, 0.08), (0, y1 + 1.35, 0.2 + H + 1.0), rail)
    k.loot += [(-3.0, -3.0, 0.2), (-2.0, 3.0, 0.2), (-3.0, -2.5, 0.2 + H), (2.0, -3.0, 0.2 + H)]
    k.chests += [(-3.5, 3.4, 0.2 + H, 90), (0.0, 0.0, 0.2 + 2 * H + 0.2, 0)]
    return k


def env_warehouse():
    k = Kit()
    metal = M("wh_metal", "#5c7c8a", metal=0.6, rough=0.5, texture="panel", tex_scale=0.4)
    concrete = M("wh_concrete", "#8d99ae", rough=0.9, texture="concrete", tex_scale=0.25)
    door = M("wh_door", "#ffb703", metal=0.5, rough=0.5, texture="panel", tex_scale=0.8)
    roof = M("wh_roof", "#495057", metal=0.6, rough=0.6, texture="panel", tex_scale=0.3)
    crate = M("wh_crate", "#bc6c25", rough=0.8, texture="planks", tex_scale=1)
    W, D, H = 20.0, 14.0, 7.0
    x0, x1, y0, y1 = -W / 2, W / 2, -D / 2, D / 2
    k.floor(x0, x1, y0, y1, 0.15, concrete)
    k.wall("x", y1, x0, x1, 0.15, H, metal, [(-7.0, -2.0, 0, 4.5), (3.0, 4.4, 0, 2.4)], thickness=0.3)
    k.wall("x", y0, x0, x1, 0.15, H, metal, [(2.0, 7.0, 0, 4.5)], thickness=0.3)
    k.wall("y", x0, y0, y1, 0.15, H, metal, [(-1.0, 1.0, 0, 2.4)], thickness=0.3)
    k.wall("y", x1, y0, y1, 0.15, H, metal, [], thickness=0.3)
    k.add(core.box("roller_up", (5.0, 0.3, 1.0), (-4.5, y1 + 0.2, 4.4), (0, 0, 0), door))
    k.box("roof", (W + 0.6, D + 0.6, 0.3), (0, 0, H + 0.3), roof)
    for x in (-6, 0, 6):
        k.add(core.box("skylight", (2.0, 3.0, 0.2), (x, 0, H + 0.5), (0, 0, 0), M("wh_sky", "#caf0f8", emit=0.3, alpha=0.6)))
    rng = random.Random(4)
    for i in range(7):
        x, y = rng.uniform(-8, 8), rng.uniform(-5, 5)
        if abs(x) < 3 and abs(y) < 3:
            continue
        s = rng.choice((1.2, 1.5))
        k.box(f"crate{i}", (s, s, s), (x, y, 0.15 + s / 2), crate, bevel=0.04)
    # catwalk with stairs
    k.box("catwalk", (W - 1.0, 2.0, 0.2), (0, y0 + 1.3, 3.6), metal)
    k.stairs(x0 + 1.4, y1 - 1.0, y0 + 2.4, 0.15, 3.6, 1.6, metal)
    k.loot += [(-6, 3, 0.15), (6, 3, 0.15), (0, -2, 0.15), (-5, y0 + 1.3, 3.7), (5, y0 + 1.3, 3.7)]
    k.chests += [(8.5, -5.5, 0.15, 180), (0, y0 + 1.3, 3.7, 0)]
    return k


def env_shop():
    k = Kit()
    wall = M("shop_wall", "#f2e9e4", rough=0.9, texture="plaster", tex_scale=0.5)
    accent = M("shop_accent", "#3a0ca3", rough=0.5, texture="panel", tex_scale=1)
    glass = M("shop_glass", "#bde0fe", rough=0.05, alpha=0.3)
    floor = M("shop_floor", "#e9ecef", rough=0.4, texture="concrete", tex_scale=0.5)
    awning = M("shop_awning", "#f72585", rough=0.8, texture="fabric", tex_scale=1)
    neon = M("shop_neon", "#4cc9f0", emit=4.0)
    shelf = M("shop_shelf", "#adb5bd", metal=0.6, rough=0.4)
    W, D, H = 12.0, 9.0, 3.6
    x0, x1, y0, y1 = -W / 2, W / 2, -D / 2, D / 2
    k.floor(x0, x1, y0, y1, 0.2, floor)
    k.wall("x", y1, x0, x1, 0.2, H, wall, [(-5.0, -1.2, 0.5, 3.0), (-0.8, 0.8, 0, 2.5), (1.2, 5.0, 0.5, 3.0)], glass=glass)
    k.wall("x", y0, x0, x1, 0.2, H, wall, [(3.0, 4.2, 0, 2.4)])
    k.wall("y", x0, y0 + WALL_T / 2, y1 - WALL_T / 2, 0.2, H, wall, [(-1.5, 1.5, 1.0, 2.6)], glass=glass)
    k.wall("y", x1, y0 + WALL_T / 2, y1 - WALL_T / 2, 0.2, H, wall)
    k.box("roof", (W + 0.4, D + 0.4, 0.3), (0, 0, 0.2 + H + 0.15), accent)
    k.box("sign_board", (8.0, 0.3, 1.0), (0, y1 + 0.2, 0.2 + H + 0.8), accent)
    k.add(core.box("sign_neon", (6.0, 0.05, 0.12), (0, y1 + 0.37, 0.2 + H + 0.8), (0, 0, 0), neon))
    for i in range(6):
        k.add(core.box(f"awning{i}", (1.6, 1.6, 0.06), (-4.75 + i * 1.9, y1 + 0.75, 3.1), (-20, 0, 0),
                       awning if i % 2 == 0 else M("shop_awning2", "#ffffff", rough=0.8)))
    for x in (-3.5, 0.0, 3.5):
        k.box(f"shelf{x}", (2.4, 0.6, 1.8), (x, -1.5, 1.1), shelf)
    k.box("counter", (3.0, 0.8, 1.1), (-3.5, 2.6, 0.75), accent)
    k.loot += [(-3.5, -0.6, 0.2), (3.5, -0.6, 0.2), (0, 2.0, 0.2), (4.5, 3.0, 0.2)]
    k.chests += [(-5.2, -3.6, 0.2, 90)]
    return k


def env_tower():
    k = Kit()
    wood = M("tower_wood", "#7f5539", rough=0.8, texture="planks", tex_scale=0.6)
    beam = M("tower_beam", "#5e3c22", rough=0.8, texture="wood", tex_scale=1)
    roof = M("tower_roof", "#2a9d8f", rough=0.7, texture="shingle", tex_scale=0.6)
    P = 10.0
    for sx in (1, -1):
        for sy in (1, -1):
            k.box("leg", (0.4, 0.4, P), (2.2 * sx, 2.2 * sy, P / 2), beam)
    for z in (3.0, 6.5):
        for s in (1, -1):
            k.add(core.box("brace", (0.15, 4.6, 0.15), (2.2 * s, 0, z), (45, 0, 0), beam))
            k.add(core.box("brace", (4.6, 0.15, 0.15), (0, 2.2 * s, z), (0, 45, 0), beam))
    k.floor(-2.8, 2.8, -2.8, 2.8, P, wood)
    for (ax, fixed, a0, a1, gap) in (("x", 2.75, -2.8, 2.8, []), ("x", -2.75, -2.8, 2.8, []), ("y", 2.75, -2.8, 2.8, []),
                                     ("y", -2.75, -2.8, 2.8, [(-2.8, -1.4, 0, 1.1)])):
        k.wall(ax, fixed, a0, a1, P, 1.1, wood, gap, thickness=0.15)
    for sx in (1, -1):
        for sy in (1, -1):
            k.box("post", (0.15, 0.15, 2.4), (2.7 * sx, 2.7 * sy, P + 1.2), beam, collide=False)
    k.add(core.lathe("tower_roof", [(4.0, 0), (2.5, 0.8), (0.0, 1.8)], (0, 0, P + 2.4), mat=roof, seg=4))
    # switchback stairs to the platform
    k.stairs(-4.6, -3.0, 3.0, 0.0, 5.0, 1.2, wood)
    k.box("landing", (2.4, 1.6, 0.2), (-4.0, 3.8, 4.9), wood)
    for i in range(14):  # second flight back toward -Y, ending at the railing gap
        h = 5.0 + (i + 1) * (P - 5.0) / 14
        k.box(f"step_b{i}", (1.2, 0.42, 0.25), (-3.4, 3.2 - i * 0.42, h - 0.12), wood)
    k.loot += [(0, 0, P)]
    k.chests += [(1.5, 1.5, P, 225)]
    return k


def env_gas_station():
    k = Kit()
    canopy = M("gas_canopy", "#f8f9fa", rough=0.5, texture="panel", tex_scale=0.5)
    red = M("gas_red", "#d00000", rough=0.5)
    pump = M("gas_pump", "#e9ecef", rough=0.4, texture="plain")
    pillar = M("gas_pillar", "#6c757d", metal=0.6, rough=0.4)
    concrete = M("gas_concrete", "#adb5bd", rough=0.9, texture="concrete", tex_scale=0.25)
    glass = M("gas_glass", "#a2d2ff", rough=0.05, alpha=0.3)
    screen = M("gas_screen", "#80ffdb", emit=2.0)
    k.box("slab", (16, 12, 0.2), (0, 0, 0.1), concrete)
    k.box("canopy", (10, 7, 0.6), (0, 1.0, 5.3), canopy)
    k.add(core.box("canopy_band", (10.1, 7.1, 0.25), (0, 1.0, 5.1), (0, 0, 0), red))
    for x in (-3.5, 3.5):
        for y in (-1.0, 3.0):
            k.box("pillar", (0.4, 0.4, 5.0), (x, y, 2.6), pillar)
    for x in (-1.5, 1.5):
        k.box("island", (1.2, 4.0, 0.25), (x, 1.0, 0.32), concrete)
        for y in (0.0, 2.0):
            k.box("pump", (0.7, 0.5, 1.6), (x, y, 1.25), pump, bevel=0.05)
            k.add(core.box("pump_screen", (0.4, 0.02, 0.3), (x, y + 0.26, 1.6), (0, 0, 0), screen))
            k.add(core.box("pump_top", (0.75, 0.55, 0.2), (x, y, 2.1), (0, 0, 0), red))
    # kiosk
    kw = M("gas_kiosk", "#ffd166", rough=0.9, texture="plaster", tex_scale=0.5)
    k.floor(-4.0, 4.0, -6.0, -3.0, 0.2, concrete, collide=False)
    k.wall("x", -3.0, -4.0, 4.0, 0.2, 3.0, kw, [(-3.5, -0.5, 0.9, 2.4), (1.0, 2.2, 0, 2.3)], glass=glass)
    k.wall("x", -6.0, -4.0, 4.0, 0.2, 3.0, kw)
    k.wall("y", -4.0, -6.0, -3.0, 0.2, 3.0, kw)
    k.wall("y", 4.0, -6.0, -3.0, 0.2, 3.0, kw)
    k.box("kiosk_roof", (8.4, 3.4, 0.25), (0, -4.5, 3.3), red)
    k.loot += [(-2.0, -4.5, 0.2), (0.0, 1.0, 0.45)]
    k.chests += [(3.2, -5.3, 0.2, 180)]
    return k


# --------------------------------------------------------------- vegetation
def _jitter(obj, amount, seed):
    rng = random.Random(seed)
    for v in obj.data.vertices:
        v.co += Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * amount
    return obj


def _blob(name, radius, loc, mat, seed, subdiv=3, scale=(1, 1, 1)):
    import bpy  # noqa: F401
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius, calc_uvs=True)
    obj = core._new_obj(name, bm, mat)
    core._place(obj, loc, (0, 0, 0), scale)
    _jitter(obj, radius * 0.15, seed)
    core.smooth(obj, 30)
    return obj


def env_tree_oak():
    k = Kit()
    bark = M("oak_bark", "#5c4033", rough=0.9, texture="bark", tex_scale=2)
    leaves = M("oak_leaves", "#4f772d", rough=0.8, texture="leaf", tex_scale=1)
    leaves2 = M("oak_leaves2", "#90a955", rough=0.8, texture="leaf", tex_scale=1)
    k.add(core.cylinder("trunk", 0.35, 4.5, (0, 0, 2.25), mat=bark, verts=10, radius_top=0.22))
    k.add(core.tube("branch1", [(0, 0, 3.0), (1.0, 0.3, 4.0), (1.6, 0.5, 4.6)], 0.12, bark, seg=8))
    k.add(core.tube("branch2", [(0, 0, 3.4), (-0.9, -0.4, 4.3), (-1.4, -0.6, 4.9)], 0.11, bark, seg=8))
    for i, (x, y, z, r) in enumerate([(0, 0, 5.6, 2.0), (1.5, 0.6, 5.0, 1.5), (-1.4, -0.6, 5.2, 1.5), (0.3, -1.3, 5.0, 1.3),
                                      (-0.4, 1.3, 5.4, 1.4), (0, 0, 6.8, 1.3)]):
        k.add(_blob(f"canopy{i}", r, (x, y, z), leaves if i % 2 == 0 else leaves2, i))
    k.colliders.append({"center": [0, 0, 2.25], "size": [0.7, 0.7, 4.5]})
    return k


def env_tree_pine():
    k = Kit()
    bark = M("pine_bark", "#6f4e37", rough=0.9, texture="bark", tex_scale=2)
    needles = M("pine_needles", "#2d6a4f", rough=0.85, texture="leaf", tex_scale=1)
    needles2 = M("pine_needles2", "#40916c", rough=0.85, texture="leaf", tex_scale=1)
    k.add(core.cylinder("trunk", 0.3, 7.0, (0, 0, 3.5), mat=bark, verts=10, radius_top=0.1))
    for i in range(5):
        r = 2.6 - i * 0.45
        o = core.cylinder(f"tier{i}", r, 2.4, (0, 0, 2.8 + i * 1.35), mat=needles if i % 2 == 0 else needles2, verts=9,
                          radius_top=0.05)
        _jitter(o, 0.12, i)
        k.add(o)
    k.colliders.append({"center": [0, 0, 3.0], "size": [0.6, 0.6, 6.0]})
    return k


def env_tree_palm():
    k = Kit()
    bark = M("palm_bark", "#a68a64", rough=0.9, texture="bark", tex_scale=3)
    frond = M("palm_frond", "#3a7d44", rough=0.7, texture="leaf", tex_scale=2)
    coconut = M("palm_coconut", "#4a3728", rough=0.8)
    pts = [(0, 0, 0), (0.3, 0, 2.0), (0.9, 0, 4.0), (1.6, 0, 5.8)]
    k.add(core.tube("trunk", pts, 0.25, bark, seg=10, radii=[0.3, 0.25, 0.2, 0.17]))
    for i in range(8):
        a = 2 * math.pi * i / 8
        k.add(core.prism(f"frond{i}", [(0, 0), (1.2, 0.35), (2.8, 0.0), (1.2, -0.35)], 0.04, (1.6, 0, 5.85),
                         (0, 25 + 10 * (i % 2), math.degrees(a)), frond, axis="Z"))
    for i in range(3):
        a = 2 * math.pi * i / 3
        k.add(core.sphere(f"coconut{i}", 0.15, (1.6 + math.cos(a) * 0.22, math.sin(a) * 0.22, 5.6), mat=coconut))
    k.colliders.append({"center": [0.5, 0, 2.5], "size": [0.8, 0.6, 5.0]})
    return k


def env_rock_a():
    k = Kit()
    rock = M("rock_grey", "#7d8597", rough=0.95, texture="rock", tex_scale=0.5)
    k.add(_blob("rock", 1.6, (0, 0, 0.7), rock, 11, subdiv=3, scale=(1.3, 1.0, 0.75)))
    k.add(_blob("rock2", 0.9, (1.6, 0.6, 0.35), rock, 12, subdiv=1, scale=(1.0, 0.9, 0.8)))
    for o in k.parts:
        core.smooth(o, 20)
    k.colliders.append({"center": [0.3, 0.1, 0.8], "size": [3.6, 2.6, 1.6]})
    return k


def env_rock_b():
    k = Kit()
    rock = M("rock_sand", "#b08968", rough=0.95, texture="rock", tex_scale=0.5)
    k.add(_blob("spire", 1.2, (0, 0, 1.6), rock, 21, subdiv=3, scale=(0.9, 0.8, 1.8)))
    k.add(_blob("base", 1.4, (0.4, 0.2, 0.4), rock, 22, subdiv=1, scale=(1.2, 1.0, 0.5)))
    k.colliders.append({"center": [0.1, 0.0, 1.6], "size": [2.2, 2.0, 3.2]})
    return k


def env_bush():
    k = Kit()
    leaves = M("bush_leaves", "#55a630", rough=0.8, texture="leaf", tex_scale=1)
    flower = M("bush_flower", "#ff70a6", rough=0.6)
    for i, (x, y, r) in enumerate([(0, 0, 0.8), (0.6, 0.2, 0.6), (-0.5, -0.3, 0.6), (0.1, -0.5, 0.55)]):
        k.add(_blob(f"bush{i}", r, (x, y, r * 0.7), leaves, 30 + i, subdiv=1))
    rng = random.Random(9)
    for i in range(6):
        k.add(core.sphere(f"flower{i}", 0.06, (rng.uniform(-0.7, 0.7), rng.uniform(-0.6, 0.6), rng.uniform(0.7, 1.1)),
                          mat=flower, segments=8, rings=6))
    return k


# -------------------------------------------------------------------- props
def env_loot_chest():
    k = Kit()
    wood = M("chest_wood", "#8d5524", rough=0.7, texture="planks", tex_scale=3)
    gold = M("chest_gold", "#ffd60a", metal=1.0, rough=0.25, emit=0.3)
    glow = M("chest_glow", "#ffe66d", emit=3.0)
    k.box("chest_base", (1.0, 0.6, 0.45), (0, 0, 0.225), wood, bevel=0.03)
    for x in (-0.38, 0.38):
        k.add(core.box("band", (0.08, 0.62, 0.47), (x, 0, 0.226), (0, 0, 0), gold, bevel=0.01))
    k.add(core.box("lock", (0.14, 0.05, 0.16), (0, 0.31, 0.38), (0, 0, 0), gold, bevel=0.02))
    k.add(core.box("glow_strip", (0.8, 0.02, 0.03), (0, 0.305, 0.43), (0, 0, 0), glow))
    return k


def env_loot_chest_lid():
    k = Kit()
    wood = M("chest_wood", "#8d5524", rough=0.7, texture="planks", tex_scale=3)
    gold = M("chest_gold", "#ffd60a", metal=1.0, rough=0.25, emit=0.3)
    lid = core.cylinder("lid", 0.3, 1.0, (0, 0.0, 0.0), (0, 90, 0), wood, verts=16)
    import bmesh  # cut away the lower half of the drum
    bm = bmesh.new()
    bm.from_mesh(lid.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0), plane_no=(-1, 0, 0),
                           clear_inner=True)
    bm.to_mesh(lid.data)
    bm.free()
    lid.location = (0, 0.3, 0)  # origin = hinge line at the chest's back edge; the game places it there
    k.add(lid)
    for x in (-0.38, 0.38):
        k.add(core.torus("lid_band", 0.3, 0.025, (x, 0.3, 0.0), (90, 0, 90), gold, arc=180, seg=12, ring=6))
    return k


def env_supply_crate():
    k = Kit()
    wood = M("supply_wood", "#d4a373", rough=0.8, texture="planks", tex_scale=2)
    frame = M("supply_frame", "#264653", metal=0.6, rough=0.4)
    glow = M("supply_glow", "#00f5d4", emit=3.0)
    k.box("crate", (1.1, 1.1, 1.1), (0, 0, 0.55), wood, bevel=0.03)
    for axis in range(3):
        for s1 in (1, -1):
            for s2 in (1, -1):
                size = [0.08, 0.08, 0.08]
                size[axis] = 1.14
                loc = [0, 0, 0.55]
                o = [i for i in range(3) if i != axis]
                loc[o[0]] += 0.53 * s1
                loc[o[1]] += 0.53 * s2
                k.add(core.box("edge", tuple(size), tuple(loc), (0, 0, 0), frame))
    for s in (1, -1):
        k.add(core.box("x_glow", (0.04, 0.02, 0.9), (0, 0.56 * s, 0.55), (0, 45, 0), glow))
        k.add(core.box("x_glow2", (0.04, 0.02, 0.9), (0, 0.56 * s, 0.55), (0, -45, 0), glow))
    return k


def env_ammo_box():
    k = Kit()
    olive = M("ammo_olive", "#606c38", metal=0.4, rough=0.5, texture="panel", tex_scale=3)
    k.box("ammo", (0.6, 0.3, 0.3), (0, 0, 0.15), olive, bevel=0.02)
    k.add(core.box("ammo_lid", (0.62, 0.32, 0.05), (0, 0, 0.31), (0, 0, 0), olive, bevel=0.01))
    k.add(core.torus("ammo_handle", 0.07, 0.012, (0, 0, 0.34), (90, 0, 0), M("ammo_dark", "#222222", rough=0.6), arc=180))
    k.add(core.box("ammo_label", (0.2, 0.01, 0.1), (0, 0.155, 0.15), (0, 0, 0), M("ammo_label", "#ffffff", emit=0.8)))
    return k


def env_barrel():
    k = Kit()
    red = M("barrel_red", "#c1121f", metal=0.5, rough=0.4, texture="brushed", tex_scale=2)
    k.add(core.cylinder("barrel", 0.42, 1.2, (0, 0, 0.6), mat=red, verts=20, bevel=0.02))
    for z in (0.3, 0.9):
        k.add(core.torus("rib", 0.425, 0.02, (0, 0, z), mat=red, seg=24, ring=6))
    k.colliders.append({"center": [0, 0, 0.6], "size": [0.84, 0.84, 1.2]})
    return k


def env_fence():
    k = Kit()
    wood = M("fence_wood", "#b08968", rough=0.85, texture="planks", tex_scale=2)
    for x in (-2.0, 0.0, 2.0):
        k.box("post", (0.15, 0.15, 1.3), (x, 0, 0.65), wood, collide=False)
    for z in (0.45, 0.95):
        k.box("rail", (4.2, 0.08, 0.14), (0, 0, z), wood, collide=False)
    k.colliders.append({"center": [0, 0, 0.6], "size": [4.2, 0.2, 1.2]})
    return k


def env_streetlamp():
    k = Kit()
    pole = M("lamp_pole", "#343a40", metal=0.8, rough=0.4)
    light = M("lamp_light", "#fff3b0", emit=5.0)
    k.add(core.cylinder("pole", 0.09, 6.0, (0, 0, 3.0), mat=pole, verts=12, radius_top=0.06))
    k.add(core.tube("arm", [(0, 0, 5.8), (0.5, 0, 6.1), (1.3, 0, 6.1)], 0.05, pole))
    k.add(core.box("head", (0.6, 0.3, 0.12), (1.4, 0, 6.05), (0, 0, 0), pole, bevel=0.03))
    k.add(core.box("bulb", (0.5, 0.22, 0.03), (1.4, 0, 5.98), (0, 0, 0), light))
    k.colliders.append({"center": [0, 0, 3.0], "size": [0.25, 0.25, 6.0]})
    return k


def env_car():
    k = Kit()
    paint = M("car_paint", "#219ebc", metal=0.6, rough=0.25)
    dark = M("car_dark", "#14213d", rough=0.5, texture="rubber")
    glass = M("car_glass", "#1d3557", metal=0.6, rough=0.05)
    chrome = M("car_chrome", "#e5e5e5", metal=1.0, rough=0.2)
    light = M("car_light", "#fff9db", emit=2.0)
    tail = M("car_tail", "#e63946", emit=1.5)
    k.add(core.prism("body", [(-2.1, 0.35), (2.1, 0.35), (2.2, 0.75), (1.9, 0.95), (-2.0, 0.95), (-2.2, 0.7)], 1.8,
                     (0, 0, 0), mat=paint, bevel=0.06))
    k.add(core.prism("cabin", [(-1.2, 0.93), (1.0, 0.93), (0.4, 1.5), (-0.9, 1.5)], 1.6, (0, 0, 0), mat=glass, bevel=0.04))
    k.add(core.box("roof", (1.62, 1.35, 0.06), (0, -0.25, 1.52), (0, 0, 0), paint, bevel=0.02))
    for x in (-0.95, 0.95):
        for y in (-1.3, 1.3):
            k.add(core.cylinder("tire", 0.36, 0.28, (x, y, 0.36), (0, 90, 0), dark, verts=18, bevel=0.04))
            k.add(core.cylinder("rim", 0.2, 0.3, (x, y, 0.36), (0, 90, 0), chrome, verts=12))
    for s in (1, -1):
        k.add(core.box("headlight", (0.35, 0.05, 0.15), (0.6 * s, 2.18, 0.72), (0, 0, 0), light))
        k.add(core.box("taillight", (0.35, 0.05, 0.12), (0.6 * s, -2.2, 0.75), (0, 0, 0), tail))
    k.add(core.box("bumper_f", (1.8, 0.15, 0.2), (0, 2.2, 0.45), (0, 0, 0), chrome, bevel=0.04))
    k.add(core.box("bumper_r", (1.8, 0.15, 0.2), (0, -2.22, 0.45), (0, 0, 0), chrome, bevel=0.04))
    k.colliders.append({"center": [0, 0, 0.8], "size": [1.9, 4.4, 1.6]})
    return k


def env_dropship():
    k = Kit()
    hull = M("ship_hull", "#f1faee", metal=0.4, rough=0.3, texture="panel", tex_scale=0.5)
    stripe = M("ship_stripe", "#7c4dff", metal=0.3, rough=0.3)
    dark = M("ship_dark", "#1d3557", metal=0.6, rough=0.4, texture="carbon", tex_scale=1)
    glass = M("ship_glass", "#4cc9f0", rough=0.05, emit=0.6)
    thrust = M("ship_thrust", "#00f5d4", emit=4.0)
    k.add(core.lathe("fuselage", [(0.0, -7.0), (1.2, -6.4), (2.2, -4.5), (2.5, -1.0), (2.5, 3.5), (2.1, 5.5), (1.2, 6.8),
                                  (0.0, 7.2)], (0, 0, 0), (-90, 0, 0), hull, seg=24))
    k.add(core.torus("stripe_band", 2.52, 0.12, (0, 1.0, 0), (90, 0, 0), stripe, seg=32, ring=6))
    k.add(core.sphere("cockpit", 1.4, (0, 5.4, 0.9), scale=(1.0, 1.4, 0.6), mat=glass))
    for s in (1, -1):
        k.add(core.prism("wing", [(-1.5, 0.0), (2.0, 0.0), (1.0, 0.3), (-2.5, 0.3)], 6.0, (4.5 * s, 0, -0.2), mat=hull,
                         bevel=0.05))
        k.add(core.torus("fan_ring", 1.4, 0.25, (7.2 * s, 1.0, 0.0), mat=dark, seg=28, ring=8))
        k.add(core.cylinder("fan_hub", 0.4, 0.6, (7.2 * s, 1.0, 0.0), mat=dark, verts=14))
        k.add(core.cylinder("fan_glow", 1.2, 0.05, (7.2 * s, 1.0, -0.3), mat=thrust, verts=24))
        for b in range(5):
            a = 360 * b / 5
            k.add(core.box("blade", (1.1, 0.25, 0.04), (7.2 * s + math.cos(math.radians(a)) * 0.6, 1.0 + math.sin(math.radians(a)) * 0.6, 0.0),
                           (12, 0, a), dark))
    k.add(core.prism("tail_fin", [(-6.8, 0.0), (-4.0, 0.0), (-5.6, 3.0), (-6.9, 3.0)], 0.3, (0, 0, 1.6), mat=stripe, bevel=0.05))
    for s in (1, -1):
        k.add(core.cylinder("engine", 0.6, 2.0, (1.4 * s, -7.0, -0.5), (90, 0, 0), dark, verts=16))
        k.add(core.cylinder("engine_glow", 0.5, 0.05, (1.4 * s, -8.02, -0.5), (90, 0, 0), thrust, verts=16))
    k.add(core.box("ramp", (2.4, 0.2, 3.0), (0, -6.2, -1.6), (-60, 0, 0), dark))
    return k


def env_lobby_stage():
    k = Kit()
    base = M("stage_base", "#1b1b3a", metal=0.6, rough=0.3, texture="hex", tex_scale=1)
    top = M("stage_top", "#2d2a5a", metal=0.3, rough=0.4, texture="panel", tex_scale=1)
    neon = M("stage_neon", "#7c4dff", emit=5.0)
    neon2 = M("stage_neon2", "#00e5ff", emit=4.0)
    k.add(core.lathe("stage", [(2.2, 0.0), (2.4, 0.15), (2.3, 0.35), (2.0, 0.4), (0.0, 0.4)], (0, 0, -0.4), mat=base, seg=48))
    k.add(core.cylinder("stage_top", 1.9, 0.04, (0, 0, 0.0), mat=top, verts=48))
    k.add(core.torus("ring_outer", 2.35, 0.03, (0, 0, -0.1), mat=neon, seg=64, ring=6))
    k.add(core.torus("ring_inner", 1.92, 0.02, (0, 0, 0.02), mat=neon2, seg=64, ring=6))
    for i in range(3):
        a = math.radians(-50 + i * 50)
        k.add(core.box(f"panel{i}", (2.6, 0.2, 6.0), (math.sin(a) * 6.0, -math.cos(a) * 6.0 - 1.0, 2.5),
                       (0, 0, math.degrees(a)), base, bevel=0.05))
        k.add(core.box(f"panel_strip{i}", (0.08, 0.22, 5.6), (math.sin(a) * 5.9, -math.cos(a) * 5.9 - 1.0, 2.5),
                       (0, 0, math.degrees(a)), neon if i != 1 else neon2))
    for i in range(2):
        for s in (1, -1):
            k.add(core.cylinder(f"spot{i}{s}", 0.25, 0.4, (3.6 * s, 2.5 + i * 1.2, 0.2), (60, 0, 25 * s), base, verts=16))
    return k


ENVIRONMENT = {f.__name__: f for f in (
    env_house_a, env_house_b, env_warehouse, env_shop, env_tower, env_gas_station,
    env_tree_oak, env_tree_pine, env_tree_palm, env_rock_a, env_rock_b, env_bush,
    env_loot_chest, env_loot_chest_lid, env_supply_crate, env_ammo_box, env_barrel, env_fence, env_streetlamp, env_car,
    env_dropship, env_lobby_stage)}

PREVIEW = {"env_dropship": dict(yaw=40, pitch=20), "env_lobby_stage": dict(yaw=10, pitch=18)}


def build_env(asset_id, fn, render=True) -> dict:
    core.reset_scene()
    kit = fn()
    obj = core.finalize(kit.parts, asset_id, uv_scale=1.0)
    entry = core.export("environment", asset_id, [obj])
    entry.update({"type": "environment", "bounds": core.bounds([obj]), "colliders": kit.colliders,
                  "loot_spots": [list(p) for p in kit.loot], "chest_spots": [list(p) for p in kit.chests]})
    if render:
        from xgb.previews import render_preview
        entry["thumb"] = render_preview(asset_id, [obj], **PREVIEW.get(asset_id, dict(yaw=35, pitch=25)))
    return entry
