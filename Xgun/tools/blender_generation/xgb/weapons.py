"""Original, fictional weapon models plus consumable pickups.

Pivot: the centre of the pistol grip where the right hand closes. Barrel along
+Y, top +Z. Sockets: ``socket_muzzle``, ``socket_grip_l`` (support hand),
``socket_sight`` (camera anchor for aiming). Materials containing ``_wrap``
mark the surfaces that cosmetic weapon wraps recolour.
"""
from __future__ import annotations

import math

from mathutils import Vector

from xgb import core

M = core.material


def _wrap(name, color, **kw):
    kw.setdefault("rough", 0.42)
    kw.setdefault("metal", 0.35)
    kw.setdefault("texture", "panel")
    kw.setdefault("tex_scale", 4)
    return M(f"{name}_wrap", color, **kw)


def _grip(mat, angle=18, height=0.11, depth=0.045, y=0.0):
    a = math.radians(angle)
    prof = [(-0.02, 0.03), (0.026, 0.03), (0.026 - math.tan(a) * height, -height), (-0.024 - math.tan(a) * height, -height - 0.008)]
    g = core.prism("grip", prof, depth, (0, y, 0), mat=mat, bevel=0.008)
    return [g]


def _trigger(mat, y=0.045):
    guard = core.tube("trigger_guard", [(0, y + 0.035, 0.025), (0, y + 0.035, -0.012), (0, y + 0.012, -0.03),
                                         (0, y - 0.025, -0.028), (0, y - 0.03, -0.01)], 0.005, mat, seg=6)
    trig = core.box("trigger", (0.006, 0.008, 0.025), (0, y - 0.004, -0.008), (-12, 0, 0), mat)
    return [guard, trig]


def _holo_sight(base, glass, reticle, loc):
    x, y, z = loc
    return [core.box("sight_base", (0.03, 0.07, 0.015), (x, y, z), mat=base, bevel=0.004),
            core.torus("sight_frame", 0.024, 0.005, (x, y + 0.015, z + 0.032), (90, 0, 0), base, seg=16, ring=6,
                       scale=(1.15, 1.0, 1)),
            core.cylinder("sight_glass", 0.022, 0.003, (x, y + 0.015, z + 0.032), (90, 0, 0), glass, verts=16),
            core.sphere("sight_dot", 0.004, (x, y + 0.016, z + 0.032), mat=reticle, segments=8, rings=6)]


def _rail(mat, y0, y1, z, x=0.0):
    out = [core.box("rail", (0.022, y1 - y0, 0.008), (x, (y0 + y1) / 2, z), mat=mat)]
    n = int((y1 - y0) / 0.018)
    out += [core.box(f"rail_tooth{i}", (0.026, 0.008, 0.006), (x, y0 + 0.01 + i * 0.018, z + 0.006), mat=mat)
            for i in range(n)]
    return out


# ---------------------------------------------------------------- weapons
def weapon_striker_ar():
    body = _wrap("ar_body", "#3a3f47")
    tan = _wrap("ar_tan", "#b08d57", texture="fabric", metal=0.0, rough=0.7)
    dark = M("ar_dark", "#1c1f24", metal=0.8, rough=0.35, texture="brushed")
    glass = M("ar_glass", "#7fdbff", rough=0.05, alpha=0.6)
    red = M("ar_reticle", "#ff2e63", emit=5.0)
    p = []
    p.append(core.prism("receiver", [(-0.06, 0.03), (0.2, 0.03), (0.22, 0.06), (0.2, 0.1), (-0.04, 0.1), (-0.08, 0.075)],
                        0.05, mat=body, bevel=0.006))
    p += _grip(dark)
    p += _trigger(dark)
    p.append(core.prism("handguard", [(0.2, 0.035), (0.48, 0.04), (0.48, 0.095), (0.2, 0.1)], 0.056, mat=tan, bevel=0.008))
    for i in range(5):
        p.append(core.box(f"vent{i}", (0.058, 0.03, 0.01), (0, 0.24 + i * 0.05, 0.068), mat=dark))
    p.append(core.cylinder("barrel", 0.012, 0.22, (0, 0.56, 0.07), (90, 0, 0), dark, verts=12))
    p.append(core.cylinder("brake", 0.02, 0.06, (0, 0.68, 0.07), (90, 0, 0), dark, verts=8, bevel=0.003))
    for i in range(3):
        p.append(core.box(f"brake_port{i}", (0.044, 0.008, 0.008), (0, 0.665 + i * 0.015, 0.07), mat=body))
    p.append(core.prism("mag", [(0.07, 0.03), (0.12, 0.03), (0.15, -0.06), (0.13, -0.14), (0.08, -0.13), (0.1, -0.05)],
                        0.034, mat=tan, bevel=0.005))
    p.append(core.prism("stock", [(-0.06, 0.09), (-0.3, 0.085), (-0.31, 0.0), (-0.28, -0.03), (-0.24, 0.0),
                                  (-0.12, 0.035), (-0.06, 0.04)], 0.04, mat=body, bevel=0.007))
    p.append(core.box("buttpad", (0.042, 0.02, 0.12), (0, -0.315, 0.035), mat=dark, bevel=0.006))
    p += _rail(dark, -0.04, 0.44, 0.104)
    p += _holo_sight(dark, glass, red, (0, 0.06, 0.112))
    p.append(core.box("charging", (0.02, 0.02, 0.012), (0.03, -0.02, 0.09), mat=dark, bevel=0.003))
    p.append(core.box("ejection", (0.002, 0.06, 0.02), (0.026, 0.1, 0.065), mat=dark))
    sockets = {"muzzle": (0, 0.72, 0.07), "grip_l": (0, 0.33, 0.035), "sight": (0, 0.07, 0.145)}
    return p, sockets


def weapon_hornet_smg():
    body = _wrap("smg_body", "#2b2b2b")
    yellow = _wrap("smg_yellow", "#ffc300", texture="plain")
    dark = M("smg_dark", "#141414", metal=0.8, rough=0.35, texture="brushed")
    glass = M("smg_glass", "#ffe066", rough=0.05, alpha=0.6)
    dot = M("smg_reticle", "#39ff14", emit=5.0)
    p = []
    p.append(core.prism("receiver", [(-0.05, 0.02), (0.22, 0.02), (0.24, 0.05), (0.22, 0.1), (-0.05, 0.1)], 0.055, mat=body,
                        bevel=0.008))
    for i in range(3):
        p.append(core.box(f"stripe{i}", (0.057, 0.025, 0.08), (0, 0.04 + i * 0.06, 0.06), (0, 0, 0), yellow))
    p += _grip(dark, angle=10)
    p += _trigger(dark)
    p.append(core.cylinder("shroud", 0.026, 0.14, (0, 0.3, 0.065), (90, 0, 0), body, verts=14, bevel=0.004))
    for i in range(4):
        for s in (1, -1):
            p.append(core.cylinder(f"hole{i}{s}", 0.007, 0.01, (0.026 * s, 0.25 + i * 0.03, 0.065), (0, 90, 0), dark, verts=8))
    p.append(core.cylinder("barrel", 0.01, 0.06, (0, 0.39, 0.065), (90, 0, 0), dark, verts=10))
    p.append(core.box("mag", (0.03, 0.035, 0.2), (0, 0.11, -0.08), (8, 0, 0), dark, bevel=0.005))
    p.append(core.box("foregrip", (0.03, 0.03, 0.1), (0, 0.26, -0.02), (-8, 0, 0), yellow, bevel=0.01))
    p.append(core.tube("stock_wire", [(0.02, -0.05, 0.08), (0.02, -0.24, 0.07), (0.02, -0.25, 0.0), (0.02, -0.06, 0.02)], 0.006,
                       dark, seg=8))
    p.append(core.tube("stock_wire2", [(-0.02, -0.05, 0.08), (-0.02, -0.24, 0.07), (-0.02, -0.25, 0.0), (-0.02, -0.06, 0.02)],
                       0.006, dark, seg=8))
    p.append(core.box("stock_pad", (0.06, 0.02, 0.08), (0, -0.25, 0.035), mat=yellow, bevel=0.008))
    p += _holo_sight(dark, glass, dot, (0, 0.05, 0.102))
    sockets = {"muzzle": (0, 0.42, 0.065), "grip_l": (0, 0.26, -0.03), "sight": (0, 0.065, 0.135)}
    return p, sockets


def weapon_breacher_shotgun():
    wood = _wrap("sg_wood", "#8b4513", texture="wood", metal=0.0, rough=0.6, tex_scale=6)
    steel = M("sg_steel", "#4a4e57", metal=1.0, rough=0.3, texture="brushed")
    dark = M("sg_dark", "#1b1b1f", metal=0.7, rough=0.4)
    shell_m = M("sg_shell", "#e63946", rough=0.4)
    brass = M("sg_brass", "#d4a017", metal=1.0, rough=0.3)
    p = []
    p.append(core.box("receiver", (0.055, 0.22, 0.08), (0, 0.06, 0.06), mat=steel, bevel=0.008))
    p.append(core.cylinder("barrel", 0.02, 0.5, (0, 0.42, 0.085), (90, 0, 0), steel, verts=16, bevel=0.003))
    p.append(core.cylinder("tube_mag", 0.016, 0.42, (0, 0.37, 0.045), (90, 0, 0), dark, verts=14))
    p.append(core.cylinder("pump", 0.03, 0.17, (0, 0.33, 0.045), (90, 0, 0), wood, verts=16, bevel=0.006))
    for i in range(6):
        p.append(core.torus(f"pump_rib{i}", 0.03, 0.004, (0, 0.26 + i * 0.028, 0.045), (90, 0, 0), dark, seg=16, ring=5))
    p.append(core.cylinder("muzzle_ring", 0.026, 0.04, (0, 0.66, 0.085), (90, 0, 0), dark, verts=14, bevel=0.004))
    p += _grip(wood, angle=22, height=0.1)
    p += _trigger(dark)
    p.append(core.prism("stock", [(-0.05, 0.09), (-0.33, 0.08), (-0.35, -0.04), (-0.3, -0.06), (-0.1, 0.0), (-0.05, 0.02)],
                        0.045, mat=wood, bevel=0.01))
    p.append(core.box("butt", (0.048, 0.02, 0.135), (0, -0.355, 0.02), mat=dark, bevel=0.008))
    p.append(core.cylinder("bead", 0.004, 0.01, (0, 0.66, 0.11), mat=brass, verts=8))
    for i in range(4):  # side saddle shells
        p.append(core.cylinder(f"saddle{i}", 0.01, 0.05, (0.034, 0.0 + i * 0.024, 0.065), (0, 0, 0), shell_m, verts=10))
        p.append(core.cylinder(f"saddle_cap{i}", 0.0105, 0.012, (0.034, 0.0 + i * 0.024, 0.036), mat=brass, verts=10))
    sockets = {"muzzle": (0, 0.68, 0.085), "grip_l": (0, 0.33, 0.02), "sight": (0, 0.1, 0.125)}
    return p, sockets


def weapon_longshot_sniper():
    body = _wrap("sn_body", "#4b5320", texture="camo", metal=0.0, rough=0.7, tex_scale=3)
    steel = M("sn_steel", "#2f3237", metal=1.0, rough=0.3, texture="brushed")
    dark = M("sn_dark", "#141414", metal=0.6, rough=0.4)
    lens = M("sn_lens", "#5ab4ff", metal=0.5, rough=0.02, emit=0.5)
    p = []
    p.append(core.prism("chassis", [(-0.06, 0.03), (0.3, 0.03), (0.32, 0.06), (0.3, 0.09), (-0.06, 0.09)], 0.06, mat=body,
                        bevel=0.008))
    p.append(core.cylinder("barrel", 0.016, 0.6, (0, 0.6, 0.065), (90, 0, 0), steel, verts=16))
    for i in range(6):  # fluting
        a = 2 * math.pi * i / 6
        p.append(core.box(f"flute{i}", (0.004, 0.36, 0.004), (math.cos(a) * 0.016, 0.55, 0.065 + math.sin(a) * 0.016), mat=dark))
    p.append(core.cylinder("suppressor", 0.026, 0.14, (0, 0.95, 0.065), (90, 0, 0), dark, verts=16, bevel=0.006))
    p.append(core.cylinder("scope", 0.024, 0.3, (0, 0.08, 0.15), (90, 0, 0), dark, verts=16, bevel=0.004))
    p.append(core.cylinder("scope_bell", 0.034, 0.08, (0, 0.24, 0.15), (90, 0, 0), dark, verts=16, radius_top=0.024))
    p.append(core.cylinder("scope_eye", 0.03, 0.06, (0, -0.09, 0.15), (90, 0, 0), dark, verts=16, radius_top=0.024))
    p.append(core.cylinder("scope_lens", 0.031, 0.004, (0, 0.282, 0.15), (90, 0, 0), lens, verts=16))
    p.append(core.cylinder("turret_top", 0.014, 0.03, (0, 0.06, 0.18), mat=steel, verts=12))
    p.append(core.cylinder("turret_side", 0.014, 0.03, (0.034, 0.06, 0.15), (0, 90, 0), steel, verts=12))
    for y in (-0.02, 0.15):
        p.append(core.box("scope_ring", (0.04, 0.02, 0.07), (0, y, 0.115), mat=steel, bevel=0.004))
    p.append(core.tube("bolt", [(0.03, -0.02, 0.07), (0.07, -0.03, 0.06), (0.08, -0.03, 0.04)], 0.007, steel, seg=8))
    p.append(core.sphere("bolt_knob", 0.014, (0.08, -0.03, 0.035), mat=dark))
    p += _grip(dark, angle=12)
    p += _trigger(steel)
    p.append(core.box("mag", (0.04, 0.07, 0.07), (0, 0.12, 0.0), mat=dark, bevel=0.006))
    p.append(core.prism("stock", [(-0.06, 0.09), (-0.38, 0.1), (-0.4, -0.06), (-0.34, -0.07), (-0.2, -0.0), (-0.1, -0.02),
                                  (-0.06, 0.03)], 0.05, mat=body, bevel=0.01))
    p.append(core.box("cheek", (0.045, 0.14, 0.03), (0, -0.27, 0.11), mat=dark, bevel=0.01))
    for s in (1, -1):
        p.append(core.cylinder("bipod", 0.007, 0.2, (0.02 * s, 0.42, -0.0), (95, 0, 0), dark, verts=8))
    sockets = {"muzzle": (0, 1.02, 0.065), "grip_l": (0, 0.3, 0.03), "sight": (0, -0.12, 0.15)}
    return p, sockets


def weapon_sidekick_pistol():
    slide = _wrap("pistol_slide", "#2e3440")
    frame = M("pistol_frame", "#1b1d21", rough=0.6, texture="rubber")
    steel = M("pistol_steel", "#a3a8b0", metal=1.0, rough=0.25)
    glow = M("pistol_glow", "#ff9f1c", emit=3.0)
    p = []
    p.append(core.box("slide", (0.032, 0.2, 0.035), (0, 0.06, 0.06), mat=slide, bevel=0.005))
    for i in range(6):
        p.append(core.box(f"serration{i}", (0.034, 0.004, 0.025), (0, -0.02 + i * 0.008, 0.06), mat=frame))
    p.append(core.box("frame", (0.028, 0.17, 0.03), (0, 0.05, 0.03), mat=frame, bevel=0.004))
    p += _grip(frame, angle=14, height=0.1, depth=0.032)
    p += _trigger(steel, y=0.04)
    p.append(core.cylinder("barrel", 0.007, 0.02, (0, 0.165, 0.06), (90, 0, 0), steel, verts=10))
    p.append(core.box("compensator", (0.032, 0.03, 0.035), (0, 0.175, 0.06), mat=steel, bevel=0.004))
    p.append(core.box("rear_sight", (0.026, 0.008, 0.01), (0, -0.03, 0.082), mat=steel))
    p.append(core.box("front_sight", (0.006, 0.008, 0.01), (0, 0.15, 0.082), mat=glow))
    p.append(core.box("mag_base", (0.034, 0.05, 0.012), (0, -0.03, -0.105), (14, 0, 0), steel, bevel=0.003))
    sockets = {"muzzle": (0, 0.195, 0.06), "grip_l": (0, -0.005, -0.04), "sight": (0, -0.02, 0.09)}
    return p, sockets


def weapon_ion_lance():
    shell = _wrap("ion_shell", "#eef2f7", metal=0.4, rough=0.25)
    dark = M("ion_dark", "#1a1d26", metal=0.8, rough=0.3, texture="hex", tex_scale=6)
    glow = M("ion_glow", "#00e5ff", emit=5.0)
    pink = M("ion_pink", "#ff4dd2", emit=3.0)
    p = []
    p.append(core.prism("body", [(-0.08, 0.02), (0.18, 0.02), (0.3, 0.05), (0.3, 0.1), (0.1, 0.12), (-0.08, 0.1)], 0.06,
                        mat=shell, bevel=0.012))
    p.append(core.cylinder("core_barrel", 0.02, 0.42, (0, 0.5, 0.07), (90, 0, 0), dark, verts=14))
    for i in range(6):
        p.append(core.torus(f"coil{i}", 0.032, 0.007, (0, 0.34 + i * 0.05, 0.07), (90, 0, 0), glow, seg=16, ring=6))
    for s in (1, -1):
        p.append(core.prism(f"prong{s}", [(0.6, 0.0), (0.78, 0.02), (0.8, 0.04), (0.6, 0.03)], 0.016,
                            (0.03 * s, 0.0, 0.05 + 0.02), mat=shell, bevel=0.004))
    p.append(core.sphere("emitter", 0.016, (0, 0.73, 0.07), mat=pink))
    p.append(core.cylinder("cell", 0.024, 0.11, (0, -0.02, 0.05), (90, 0, 0), glow, verts=16))
    p.append(core.cylinder("cell_cage", 0.027, 0.12, (0, -0.02, 0.05), (90, 0, 0), dark, verts=8, cap=False))
    p += _grip(dark, angle=16)
    p += _trigger(dark)
    p.append(core.prism("stock", [(-0.08, 0.1), (-0.3, 0.08), (-0.32, -0.02), (-0.2, -0.0), (-0.08, 0.03)], 0.05, mat=shell,
                        bevel=0.012))
    p.append(core.box("stock_glow", (0.052, 0.12, 0.006), (0, -0.2, 0.06), mat=glow))
    p.append(core.box("scope_body", (0.03, 0.12, 0.035), (0, 0.06, 0.14), mat=dark, bevel=0.008))
    p.append(core.box("scope_lens", (0.022, 0.004, 0.022), (0, 0.122, 0.14), mat=pink))
    sockets = {"muzzle": (0, 0.8, 0.07), "grip_l": (0, 0.3, 0.035), "sight": (0, 0.02, 0.17)}
    return p, sockets


WEAPONS = {"weapon_striker_ar": weapon_striker_ar, "weapon_hornet_smg": weapon_hornet_smg,
           "weapon_breacher_shotgun": weapon_breacher_shotgun, "weapon_longshot_sniper": weapon_longshot_sniper,
           "weapon_sidekick_pistol": weapon_sidekick_pistol, "weapon_ion_lance": weapon_ion_lance}


# -------------------------------------------------------------- consumables
def item_bandage_roll():
    cloth = M("bandage_cloth", "#f5efe6", rough=0.9, texture="fabric", tex_scale=8)
    red = M("bandage_red", "#e63946", rough=0.6)
    roll = core.cylinder("roll", 0.06, 0.09, (0, 0, 0.045), (0, 0, 0), cloth, verts=20, bevel=0.01)
    hole = core.cylinder("core", 0.02, 0.092, (0, 0, 0.045), mat=M("bandage_core", "#c8b6a6", rough=0.8), verts=12)
    tail = core.box("tail", (0.08, 0.004, 0.08), (0.03, 0.065, 0.04), (0, 0, 20), cloth, bevel=0.002)
    stripe = core.torus("stripe", 0.0605, 0.004, (0, 0, 0.045), mat=red, seg=24, ring=4)
    return [roll, hole, tail, stripe]


def item_medkit():
    case = M("medkit_case", "#f8f9fa", rough=0.4, texture="plain")
    red = M("medkit_red", "#d90429", rough=0.4, emit=0.5)
    dark = M("medkit_dark", "#2b2d42", rough=0.6)
    body = core.box("case", (0.3, 0.12, 0.2), (0, 0, 0.1), mat=case, bevel=0.025, segments=3)
    band = core.box("band", (0.305, 0.125, 0.03), (0, 0, 0.1), mat=dark, bevel=0.006)
    cv = core.box("cross_v", (0.035, 0.01, 0.1), (0, 0.062, 0.12), mat=red, bevel=0.004)
    ch = core.box("cross_h", (0.1, 0.01, 0.035), (0, 0.062, 0.12), mat=red, bevel=0.004)
    handle = core.torus("handle", 0.05, 0.01, (0, 0, 0.205), (90, 0, 0), dark, arc=180, seg=14, ring=6)
    latches = [core.box("latch", (0.03, 0.01, 0.03), (0.09 * s, 0.062, 0.18), mat=dark, bevel=0.003) for s in (1, -1)]
    return [body, band, cv, ch, handle] + latches


def item_shield_cell():
    glass = M("cell_fluid", "#3a86ff", rough=0.05, emit=2.5)
    cap = M("cell_cap", "#e9ecef", metal=1.0, rough=0.25)
    body = core.lathe("bottle", [(0.0, 0.0), (0.04, 0.0), (0.045, 0.02), (0.045, 0.12), (0.025, 0.15), (0.018, 0.17),
                                 (0.0, 0.17)], mat=glass, seg=20)
    c = core.cylinder("cap", 0.02, 0.025, (0, 0, 0.18), mat=cap, verts=14, bevel=0.004)
    base = core.cylinder("base", 0.047, 0.015, (0, 0, 0.007), mat=cap, verts=20, bevel=0.003)
    ring = core.torus("ring", 0.046, 0.005, (0, 0, 0.07), mat=cap, seg=20, ring=5)
    return [body, c, base, ring]


def item_shield_keg():
    glass = M("keg_fluid", "#4361ee", rough=0.05, emit=2.0)
    frame = M("keg_frame", "#adb5bd", metal=1.0, rough=0.3, texture="brushed")
    body = core.cylinder("keg", 0.09, 0.25, (0, 0, 0.125), mat=glass, verts=20)
    rings = [core.torus(f"hoop{i}", 0.092, 0.012, (0, 0, 0.04 + i * 0.09), mat=frame, seg=24, ring=6) for i in range(3)]
    lid = core.cylinder("lid", 0.08, 0.02, (0, 0, 0.25), mat=frame, verts=20, bevel=0.005)
    tap = core.box("tap", (0.03, 0.04, 0.03), (0, 0.1, 0.06), mat=frame, bevel=0.005)
    return [body, lid, tap] + rings


ITEMS = {"item_bandage_roll": item_bandage_roll, "item_medkit": item_medkit, "item_shield_cell": item_shield_cell,
         "item_shield_keg": item_shield_keg}


def build_weapon(asset_id, render=True) -> dict:
    core.reset_scene()
    parts, sockets = WEAPONS[asset_id]()
    obj = core.finalize(parts, asset_id)
    for name, loc in sockets.items():
        s = core.socket("socket_" + name, loc)
        s.parent = obj
    entry = core.export("weapons", asset_id, [obj])
    entry.update({"type": "weapon", "sockets": {k: list(v) for k, v in sockets.items()}, "bounds": core.bounds([obj]),
                  "hold": "pistol" if "pistol" in asset_id else "rifle"})
    if render:
        from xgb.previews import render_preview
        entry["thumb"] = render_preview(asset_id, [obj], yaw=90, pitch=8, margin=1.0)
    return entry


def build_item(asset_id, render=True) -> dict:
    core.reset_scene()
    obj = core.finalize(ITEMS[asset_id](), asset_id)
    entry = core.export("items", asset_id, [obj])
    entry.update({"type": "item", "bounds": core.bounds([obj])})
    if render:
        from xgb.previews import render_preview
        entry["thumb"] = render_preview(asset_id, [obj], yaw=30, pitch=20)
    return entry
