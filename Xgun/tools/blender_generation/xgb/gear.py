"""Pickaxes, back blings, gliders and emote props.

Pivot conventions
* Pickaxe: origin = centre of the grip where the right hand closes, handle
  along +Z, blade swinging toward +Y. ``socket_grip`` (origin) and
  ``socket_head`` (impact point) empties are exported.
* Backpack: origin = centre of the face that touches the wearer's back; the
  pack extends toward -Y (behind the character). ``socket_back``.
* Glider: origin = the handle bar the character holds; canopy above (+Z).
"""
from __future__ import annotations

import math

from mathutils import Vector

from xgb import core

M = core.material


# ------------------------------------------------------------------ pickaxes
def _grip(handle_len, radius, mat, wrap_mat, z0=-0.18):
    parts = [core.cylinder("handle", radius, handle_len, (0, 0, z0 + handle_len / 2), mat=mat, verts=14, bevel=0.004)]
    for i in range(7):
        parts.append(core.torus(f"wrap{i}", radius + 0.002, 0.006, (0, 0, -0.1 + i * 0.03), (8, 0, 0), wrap_mat,
                                seg=14, ring=6))
    parts.append(core.cylinder("pommel", radius * 1.5, 0.04, (0, 0, z0 - 0.01), mat=wrap_mat, verts=14, bevel=0.008))
    return parts


def pickaxe_iron_pick():
    wood = M("pick_wood", "#8b5a2b", rough=0.75, texture="wood", tex_scale=6)
    leather = M("pick_leather", "#3b2a1e", rough=0.8, texture="leather", tex_scale=6)
    iron = M("pick_iron", "#7d8590", metal=1.0, rough=0.38, texture="brushed", tex_scale=3)
    parts = _grip(0.78, 0.018, wood, leather)
    head = core.prism("head", [(-0.3, -0.012), (-0.16, 0.02), (0.0, 0.035), (0.16, 0.02), (0.3, -0.012),
                               (0.16, -0.0), (0.0, -0.025), (-0.16, -0.0)], 0.035, (0, 0, 0.56), mat=iron, bevel=0.006)
    collar = core.box("collar", (0.05, 0.06, 0.07), (0, 0, 0.56), mat=iron, bevel=0.008)
    rivet = core.cylinder("rivet", 0.008, 0.06, (0, 0, 0.56), (0, 90, 0), iron, verts=8)
    return parts + [head, collar, rivet], (0, 0.3, 0.55)


def pickaxe_spray_hook():
    deck = M("spray_deck", "#ff5d8f", rough=0.6, texture="planks", tex_scale=6)
    grip = M("spray_grip", "#1d1d1d", rough=0.95, texture="asphalt", tex_scale=6)
    metal = M("spray_metal", "#d0d4da", metal=1.0, rough=0.3)
    paint = M("spray_paint", "#7cff4f", rough=0.5, emit=0.5)
    can = M("spray_can", "#2f80ed", metal=0.6, rough=0.3)
    parts = [core.box("deck", (0.07, 0.025, 0.85), (0, 0, 0.22), mat=deck, bevel=0.03),
             core.box("griptape", (0.066, 0.004, 0.75), (0, 0.014, 0.22), mat=grip, bevel=0.002)]
    for z in (-0.08, 0.5):
        parts.append(core.box("truck", (0.1, 0.03, 0.03), (0, -0.025, z), mat=metal, bevel=0.006))
        for s in (1, -1):
            parts.append(core.cylinder("wheel", 0.025, 0.02, (0.055 * s, -0.035, z), (0, 90, 0), paint, verts=14))
    hook = core.torus("hook", 0.13, 0.022, (0, 0.13, 0.66), (90, 0, 90), metal, arc=200, seg=20, ring=10)
    hook_tip = core.cylinder("hook_tip", 0.022, 0.08, (0, 0.27, 0.62), (20, 0, 0), metal, verts=12, radius_top=0.002)
    can_body = core.cylinder("can", 0.035, 0.12, (0, -0.06, 0.62), mat=can, verts=16, bevel=0.006)
    nozzle = core.cylinder("nozzle", 0.01, 0.02, (0, -0.06, 0.69), mat=paint, verts=8)
    splat = [core.sphere(f"splat{i}", 0.02 + 0.01 * (i % 2), (0.036, -0.1 + i * 0.07, 0.3 + (i * 37 % 50) / 100),
                         scale=(0.3, 1, 1), mat=paint, segments=8, rings=6) for i in range(4)]
    return parts + [hook, hook_tip, can_body, nozzle] + splat, (0, 0.27, 0.62)


def pickaxe_frostbite():
    steel = M("frost_haft", "#5b6b7a", metal=1.0, rough=0.35, texture="brushed", tex_scale=4)
    wrap = M("frost_wrap", "#22333b", rough=0.8, texture="leather", tex_scale=6)
    ice = M("frostbite_ice", "#9be7ff", rough=0.05, emit=1.5, alpha=1.0)
    ice2 = M("frostbite_ice2", "#e0fbfc", rough=0.08, emit=0.8)
    parts = _grip(0.8, 0.017, steel, wrap)
    blade = core.prism("ice_blade", [(-0.04, -0.05), (0.08, -0.04), (0.32, 0.06), (0.12, 0.08), (-0.02, 0.12),
                                     (-0.06, 0.02)], 0.05, (0, 0, 0.55), mat=ice, bevel=0.008)
    spike = core.cylinder("ice_spike", 0.03, 0.22, (0, -0.12, 0.58), (-100, 0, 0), ice2, verts=6, radius_top=0.002)
    shards = [core.cylinder(f"shard{i}", 0.018, 0.12, (0.02 * (i - 1), 0.02 + 0.03 * i, 0.68 + 0.02 * i),
                            (-20 + 15 * i, 10 * (i - 1), 0), ice2, verts=5, radius_top=0.001) for i in range(3)]
    clamp = core.box("clamp", (0.05, 0.08, 0.08), (0, 0, 0.56), mat=steel, bevel=0.01)
    return parts + [blade, spike, clamp] + shards, (0, 0.3, 0.6)


def pickaxe_gearbreaker():
    dark = M("gear_dark", "#2d3436", metal=0.9, rough=0.4, texture="panel", tex_scale=4)
    brass = M("gear_brass", "#c9a227", metal=1.0, rough=0.3, texture="brushed", tex_scale=4)
    hose = M("gear_hose", "#d63031", rough=0.6)
    grip_m = M("gear_grip", "#111111", rough=0.9, texture="rubber")
    parts = _grip(0.82, 0.02, dark, grip_m)
    hammer = core.box("hammer", (0.08, 0.2, 0.11), (0, -0.06, 0.6), mat=dark, bevel=0.015)
    pick = core.prism("pick", [(0.0, -0.04), (0.28, -0.01), (0.33, 0.02), (0.0, 0.05)], 0.05, (0, 0.04, 0.6), mat=brass,
                      bevel=0.006)
    gears = []
    for i, (y, z, r) in enumerate([(-0.07, 0.6, 0.06), (-0.02, 0.68, 0.035)]):
        gears.append(core.cylinder(f"gear{i}", r, 0.02, (0.05, y, z), (0, 90, 0), brass, verts=12))
        for k in range(8):
            a = 2 * math.pi * k / 8
            gears.append(core.box(f"tooth{i}{k}", (0.018, 0.016, 0.016), (0.05, y + math.cos(a) * r, z + math.sin(a) * r),
                                  (math.degrees(a), 0, 0), brass))
    piston = core.cylinder("piston", 0.018, 0.22, (-0.045, -0.02, 0.45), (0, 0, 0), brass, verts=12)
    tube_h = core.tube("hydraulic", [(-0.045, -0.04, 0.34), (-0.07, -0.08, 0.45), (-0.05, -0.12, 0.58)], 0.012, hose)
    return parts + [hammer, pick, piston, tube_h] + gears, (0, 0.33, 0.62)


def pickaxe_circuit_splitter():
    body = M("circuit_body", "#1b1f3b", metal=0.7, rough=0.3, texture="hex", tex_scale=6)
    blade = M("circuit_blade", "#00f5d4", rough=0.15, emit=3.5)
    blade2 = M("circuit_blade2", "#f15bb5", rough=0.15, emit=3.5)
    trim = M("circuit_trim", "#e0e0e0", metal=1.0, rough=0.2)
    grip_m = M("circuit_grip", "#0d0d0d", rough=0.9, texture="rubber")
    parts = _grip(0.8, 0.018, body, grip_m)
    core_cell = core.cylinder("cell", 0.035, 0.12, (0, 0, 0.5), mat=blade, verts=16)
    cage = [core.box(f"cage{i}", (0.012, 0.012, 0.13), (0.04 * math.cos(i * 1.57), 0.04 * math.sin(i * 1.57), 0.5),
                     mat=trim) for i in range(4)]
    mount = core.box("mount", (0.06, 0.12, 0.06), (0, 0, 0.6), mat=body, bevel=0.012)
    b1 = core.prism("blade_a", [(0.0, -0.03), (0.32, 0.0), (0.36, 0.04), (0.0, 0.05)], 0.012, (0.012, 0.03, 0.6), mat=blade,
                    bevel=0.003)
    b2 = core.prism("blade_b", [(0.0, -0.05), (-0.28, -0.02), (-0.3, 0.02), (0.0, 0.03)], 0.012, (-0.012, -0.03, 0.62),
                    mat=blade2, bevel=0.003)
    return parts + [core_cell, mount, b1, b2] + cage, (0, 0.36, 0.62)


def pickaxe_dragonfang():
    bone = M("fang_bone", "#efe6d2", rough=0.55, texture="bark", tex_scale=5)
    blade = M("fang_blade", "#c1121f", metal=0.6, rough=0.25, texture="scales", tex_scale=4)
    gold = M("fang_gold", "#ffba08", metal=1.0, rough=0.25)
    ember = M("fang_ember", "#ff7b00", rough=0.3, emit=3.0)
    wrap = M("fang_wrap", "#3c1518", rough=0.8, texture="leather", tex_scale=6)
    parts = [core.tube("spine_handle", [(0, 0, -0.2), (0, 0.02, 0.1), (0, -0.01, 0.35), (0, 0.0, 0.58)], 0.02, bone,
                       radii=[0.022, 0.018, 0.02, 0.024])]
    for i in range(6):
        parts.append(core.sphere(f"vertebra{i}", 0.026, (0, 0.0, -0.05 + i * 0.1), scale=(1, 1, 0.5), mat=bone,
                                 segments=12, rings=8))
    for i in range(5):
        parts.append(core.torus(f"fwrap{i}", 0.022, 0.006, (0, 0, -0.1 + i * 0.03), mat=wrap, seg=12, ring=6))
    fang = core.prism("fang", [(0.0, -0.02), (0.15, -0.06), (0.32, -0.02), (0.42, 0.08), (0.28, 0.04), (0.12, 0.05),
                               (0.0, 0.06)], 0.035, (0, 0.0, 0.57), mat=blade, bevel=0.006)
    spur = core.cylinder("spur", 0.025, 0.16, (0, -0.1, 0.6), (-110, 0, 0), bone, verts=8, radius_top=0.002)
    guard = core.torus("guard", 0.04, 0.012, (0, 0, 0.56), (0, 90, 0), gold, seg=16, ring=8)
    gem = core.sphere("gem", 0.02, (0.03, 0.0, 0.57), mat=ember, segments=10, rings=8)
    return parts + [fang, spur, guard, gem], (0, 0.4, 0.65)


PICKAXES = {"pickaxe_iron_pick": pickaxe_iron_pick, "pickaxe_spray_hook": pickaxe_spray_hook,
            "pickaxe_frostbite": pickaxe_frostbite, "pickaxe_gearbreaker": pickaxe_gearbreaker,
            "pickaxe_circuit_splitter": pickaxe_circuit_splitter, "pickaxe_dragonfang": pickaxe_dragonfang}


# ----------------------------------------------------------------- backpacks
def _straps(mat, buckle, top=0.14, width=0.13):
    out = []
    for s in (1, -1):
        out.append(core.box("strap", (0.04, 0.012, 0.36), (width / 2 * s, 0.006, 0.0), mat=mat, bevel=0.004))
        out.append(core.box("buckle", (0.05, 0.016, 0.03), (width / 2 * s, 0.01, -0.12), mat=buckle, bevel=0.004))
    return out


def backpack_daypack():
    canvas = M("day_canvas", "#3a86ff", rough=0.85, texture="fabric", tex_scale=4)
    dark = M("day_dark", "#1d3557", rough=0.85, texture="fabric", tex_scale=4)
    zip_m = M("day_zip", "#f1faee", metal=0.8, rough=0.3)
    body = core.box("bag", (0.3, 0.16, 0.4), (0, -0.09, 0.0), mat=canvas, bevel=0.06, segments=3)
    pocket = core.box("pocket", (0.22, 0.06, 0.16), (0, -0.18, -0.08), mat=dark, bevel=0.03, segments=3)
    lid = core.box("lid", (0.3, 0.17, 0.06), (0, -0.09, 0.19), mat=dark, bevel=0.025)
    zips = [core.box("zip", (0.2, 0.01, 0.008), (0, -0.215, 0.0), mat=zip_m),
            core.box("pull", (0.012, 0.012, 0.035), (0.08, -0.22, -0.01), mat=zip_m)]
    handle = core.torus("handle", 0.035, 0.008, (0, -0.07, 0.23), (0, 90, 0), dark, arc=180, seg=12, ring=6)
    return [body, pocket, lid, handle] + zips + _straps(dark, zip_m)


def backpack_explorer_roll():
    canvas = M("exp_canvas", "#606c38", rough=0.85, texture="fabric", tex_scale=4)
    leather = M("exp_leather", "#7f5539", rough=0.7, texture="leather", tex_scale=4)
    roll = M("exp_roll", "#bc4749", rough=0.9, texture="knit", tex_scale=4)
    metal = M("exp_metal", "#adb5bd", metal=1.0, rough=0.35)
    frame = [core.cylinder(f"frame{s}", 0.01, 0.55, (0.16 * s, -0.03, 0.02), mat=metal, verts=8) for s in (1, -1)]
    body = core.box("bag", (0.3, 0.2, 0.42), (0, -0.12, 0.0), mat=canvas, bevel=0.07, segments=3)
    flap = core.box("flap", (0.31, 0.22, 0.12), (0, -0.12, 0.17), (8, 0, 0), leather, bevel=0.04)
    bedroll = core.cylinder("bedroll", 0.075, 0.42, (0, -0.12, 0.3), (0, 90, 0), roll, verts=20, bevel=0.02)
    ties = [core.torus("tie", 0.08, 0.01, (0.12 * s, -0.12, 0.3), (0, 90, 0), leather, seg=16, ring=6) for s in (1, -1)]
    side = [core.cylinder(f"bottle{s}", 0.04, 0.16, (0.19 * s, -0.12, -0.08), mat=metal, verts=14, bevel=0.01)
            for s in (1, -1)]
    biners = [core.torus(f"biner{i}", 0.02, 0.005, (0.08 * (i - 0.5), -0.23, -0.14), (90, 0, 0), metal, seg=12, ring=5)
              for i in range(2)]
    return frame + [body, flap, bedroll] + ties + side + biners + _straps(leather, metal)


def backpack_crystal_core():
    cage = M("cc_cage", "#3d405b", metal=0.9, rough=0.35, texture="panel", tex_scale=4)
    crystal = M("cc_crystal", "#b388ff", rough=0.05, emit=3.0)
    crystal2 = M("cc_crystal2", "#64dfdf", rough=0.05, emit=2.5)
    plate = core.box("plate", (0.24, 0.04, 0.36), (0, -0.02, 0), mat=cage, bevel=0.015)
    big = core.cylinder("crystal", 0.07, 0.36, (0, -0.13, 0.05), (0, 0, 22), crystal, verts=6, radius_top=0.01)
    big2 = core.cylinder("crystal_b", 0.06, 0.12, (0, -0.13, -0.16), (180, 0, 22), crystal, verts=6, radius_top=0.01)
    small = [core.cylinder(f"shard{i}", 0.03, 0.16, (0.08 * s, -0.11, -0.02 + 0.06 * i), (0, 25 * s, 0), crystal2,
                           verts=6, radius_top=0.004) for i, s in enumerate((1, -1))]
    rings = [core.torus(f"ring{i}", 0.1, 0.012, (0, -0.13, -0.08 + i * 0.16), (0, 0, 0), cage, seg=20, ring=6)
             for i in range(2)]
    bars = [core.cylinder(f"bar{i}", 0.008, 0.2, (0.1 * math.cos(a), -0.13 + 0.1 * math.sin(a), 0.0), mat=cage, verts=6)
            for i, a in enumerate((0.3, 2.0, 3.4, 4.9))]
    return [plate, big, big2] + small + rings + bars + _straps(cage, cage, width=0.15)


def backpack_boombox():
    case = M("boom_case", "#2b2d42", rough=0.45, texture="plain")
    accent = M("boom_accent", "#ef476f", rough=0.4, texture="rubber")
    cone = M("boom_cone", "#111111", rough=0.7, texture="rubber")
    chrome = M("boom_chrome", "#e9ecef", metal=1.0, rough=0.15)
    led = M("boom_led", "#06d6a0", emit=3.0)
    body = core.box("case", (0.42, 0.14, 0.24), (0, -0.09, 0.0), mat=case, bevel=0.03, segments=3)
    parts = [body]
    for s in (1, -1):
        parts.append(core.cylinder("speaker", 0.075, 0.02, (0.12 * s, -0.165, 0.0), (90, 0, 0), cone, verts=24))
        parts.append(core.torus("speaker_ring", 0.075, 0.01, (0.12 * s, -0.168, 0.0), (90, 0, 0), chrome, seg=24, ring=6))
        parts.append(core.sphere("dust_cap", 0.025, (0.12 * s, -0.17, 0.0), scale=(1, 0.5, 1), mat=accent))
    parts.append(core.box("deck", (0.12, 0.02, 0.07), (0, -0.165, 0.03), mat=chrome, bevel=0.006))
    for i in range(5):
        parts.append(core.box(f"eq{i}", (0.01, 0.012, 0.02 + 0.012 * (i % 3)), (-0.04 + i * 0.02, -0.168, -0.06), mat=led))
    parts.append(core.torus("handle", 0.16, 0.014, (0, -0.09, 0.12), (90, 0, 0), chrome, arc=180, seg=20, ring=8))
    parts += _straps(accent, chrome, width=0.18)
    return parts


def backpack_jet_canister():
    shell = M("jet_shell", "#e8eef8", metal=0.4, rough=0.25, texture="panel", tex_scale=3)
    dark = M("jet_dark", "#2a2f3a", metal=0.7, rough=0.3, texture="brushed")
    glow = M("jet_glow", "#00e5ff", emit=4.0)
    fins = M("jet_fins", "#ff6b35", metal=0.3, rough=0.4)
    parts = [core.box("spine_plate", (0.18, 0.05, 0.38), (0, -0.03, 0), mat=dark, bevel=0.015)]
    for s in (1, -1):
        parts.append(core.cylinder("tank", 0.075, 0.4, (0.1 * s, -0.12, 0.02), mat=shell, verts=20, bevel=0.03))
        parts.append(core.cylinder("nozzle", 0.06, 0.08, (0.1 * s, -0.12, -0.22), mat=dark, verts=16, radius_top=0.075))
        parts.append(core.cylinder("nozzle_glow", 0.045, 0.01, (0.1 * s, -0.12, -0.262), mat=glow, verts=16))
        parts.append(core.torus("band", 0.077, 0.008, (0.1 * s, -0.12, 0.12), mat=glow, seg=20, ring=6))
        for k in range(3):
            parts.append(core.box("fin", (0.006, 0.06, 0.1), (0.1 * s + 0.08 * s, -0.12, -0.05 + 0.08 * k), mat=fins,
                                  bevel=0.003))
    parts.append(core.sphere("dome", 0.06, (0, -0.1, 0.2), scale=(1, 0.8, 0.6), mat=glow))
    return parts + _straps(dark, shell, width=0.16)


def backpack_ember_quiver():
    lacquer = M("quiver_lacquer", "#6a040f", metal=0.2, rough=0.2, texture="scales", tex_scale=4)
    gold = M("quiver_gold", "#ffba08", metal=1.0, rough=0.25)
    shaft = M("quiver_shaft", "#d4a373", rough=0.7, texture="wood", tex_scale=8)
    fletch = M("quiver_fletch", "#d00000", rough=0.8, texture="fabric")
    cord = M("quiver_cord", "#f8f9fa", rough=0.8)
    tube = core.cylinder("quiver", 0.075, 0.55, (0, -0.1, 0.02), (0, -25, 0), lacquer, verts=18, radius_top=0.085,
                         bevel=0.01)
    parts = [tube]
    axis = Vector((math.sin(math.radians(-25)), 0, math.cos(math.radians(-25))))
    center = Vector((0, -0.1, 0.02))
    for t in (-0.2, 0.02, 0.24):
        parts.append(core.torus("ring", 0.081 + 0.01 * (t + 0.27) / 0.55, 0.01, center + axis * t, (0, -25, 0), gold,
                                seg=20, ring=6))
    mouth = center + axis * 0.275
    for i in range(5):
        top = mouth + axis * 0.1 + Vector((0.025 * (i - 2), 0.02 * ((i % 2) - 0.5), 0))
        parts.append(core.cylinder(f"arrow{i}", 0.006, 0.22, top - axis * 0.1, (0, -25, 0), shaft, verts=6))
        parts.append(core.prism(f"fletch{i}", [(0, 0), (0.05, 0.0), (0.06, 0.03), (0.0, 0.025)], 0.004,
                                top, (0, -25 - 90 + (i - 2) * 12, 0), fletch, axis="Y"))
    parts.append(core.tube("cord", [(-0.12, 0.0, 0.2), (0.0, 0.01, 0.0), (0.12, 0.0, -0.2)], 0.008, cord))
    return parts


BACKPACKS = {"backpack_daypack": backpack_daypack, "backpack_explorer_roll": backpack_explorer_roll,
             "backpack_crystal_core": backpack_crystal_core, "backpack_boombox": backpack_boombox,
             "backpack_jet_canister": backpack_jet_canister, "backpack_ember_quiver": backpack_ember_quiver}


# ------------------------------------------------------------------- gliders
def _handlebar(mat, grip):
    return [core.cylinder("bar", 0.015, 0.8, (0, 0, 0), (0, 90, 0), mat, verts=10),
            core.cylinder("grip_r", 0.02, 0.12, (0.32, 0, 0), (0, 90, 0), grip, verts=10),
            core.cylinder("grip_l", 0.02, 0.12, (-0.32, 0, 0), (0, 90, 0), grip, verts=10)]


def _risers(mat, pts):
    return [core.tube(f"riser{i}", [p0, p1], 0.006, mat, seg=6) for i, (p0, p1) in enumerate(pts)]


def glider_wing_sail():
    sail = M("sail_cloth", "#ff9f1c", rough=0.8, texture="fabric", tex_scale=2)
    sail2 = M("sail_cloth2", "#ffffff", rough=0.8, texture="fabric", tex_scale=2)
    alu = M("sail_alu", "#ced4da", metal=1.0, rough=0.3)
    grip = M("sail_grip", "#212529", rough=0.9, texture="rubber")
    parts = _handlebar(alu, grip)
    wing = core.prism("wing", [(-1.4, -0.35), (0.0, 0.65), (1.4, -0.35), (0.0, -0.05)], 0.03, (0, 0.0, 1.1), (0, 0, 0), sail,
                      axis="Z")
    stripe = core.prism("stripe", [(-0.9, -0.12), (0.0, 0.55), (0.9, -0.12), (0.0, 0.12)], 0.035, (0, 0.0, 1.1), mat=sail2,
                        axis="Z")
    keel = core.cylinder("keel", 0.02, 1.0, (0, 0.15, 1.08), (90, 0, 0), alu, verts=8)
    spar = core.cylinder("spar", 0.018, 2.8, (0, 0.0, 1.1), (0, 90, 0), alu, verts=8)
    parts += [wing, stripe, keel, spar]
    parts += _risers(alu, [((0.3, 0, 0), (0.6, 0, 1.08)), ((-0.3, 0, 0), (-0.6, 0, 1.08)), ((0, 0, 0), (0, 0, 1.08))])
    return parts


def glider_patchwork():
    colors = ["#e63946", "#f1faee", "#a8dadc", "#457b9d", "#ffb703", "#8ac926"]
    cord = M("chute_cord", "#f8f9fa", rough=0.8)
    grip = M("chute_grip", "#1d3557", rough=0.9, texture="rubber")
    parts = _handlebar(M("chute_bar", "#6c757d", metal=1.0, rough=0.4), grip)
    n = 12
    for i in range(n):
        a0, a1 = math.pi * i / n, math.pi * (i + 1) / n
        r = 1.5
        pts = [(math.cos(a0) * r, 0.0, 0.0), (math.cos(a1) * r, 0.0, 0.0), (math.cos(a1) * r * 0.9, 0.0, 0.0)]
        mat = M(f"chute_patch{i % len(colors)}", colors[i % len(colors)], rough=0.85, texture="fabric", tex_scale=3)
        panel = core.box(f"panel{i}", (0.42, 0.9, 0.025), (math.cos((a0 + a1) / 2) * r, 0.0, 1.0 + math.sin((a0 + a1) / 2) * 0.9),
                         (0, -math.degrees((a0 + a1) / 2) + 90, 0), mat, bevel=0.01)
        parts.append(panel)
    parts += _risers(cord, [((0.3, 0, 0), (1.2, 0.3, 1.2)), ((0.3, 0, 0), (1.2, -0.3, 1.2)), ((-0.3, 0, 0), (-1.2, 0.3, 1.2)),
                            ((-0.3, 0, 0), (-1.2, -0.3, 1.2)), ((0.15, 0, 0), (0.5, 0, 1.85)), ((-0.15, 0, 0), (-0.5, 0, 1.85))])
    return parts


def glider_kite_ray():
    skin = M("ray_skin", "#1b263b", rough=0.4, texture="leather", tex_scale=2)
    belly = M("ray_belly", "#4cc9f0", rough=0.4, emit=0.6)
    glow = M("ray_glow", "#f72585", emit=3.0)
    grip = M("ray_grip", "#0d1b2a", rough=0.9, texture="rubber")
    parts = _handlebar(M("ray_bar", "#778da9", metal=1.0, rough=0.3), grip)
    wing = core.prism("ray_wing", [(-1.5, 0.05), (-0.6, 0.35), (0.0, 0.45), (0.6, 0.35), (1.5, 0.05), (0.6, -0.1),
                                   (0.0, -0.15), (-0.6, -0.1)], 0.06, (0, 0.0, 1.1), (90, 0, 0), skin, axis="Y")
    under = core.prism("ray_belly", [(-1.1, 0.06), (0.0, 0.3), (1.1, 0.06), (0.0, -0.08)], 0.065, (0, 0.0, 1.1), (90, 0, 0),
                       belly, axis="Y")
    eyes = [core.sphere("ray_eye", 0.05, (0.25 * s, 0.45, 1.12), mat=glow) for s in (1, -1)]
    tail = core.tube("ray_tail", [(0, -0.15, 1.1), (0, -0.7, 1.05), (0, -1.3, 1.15), (0, -1.8, 1.0)], 0.02, glow,
                     radii=[0.04, 0.025, 0.015, 0.004])
    parts += [wing, under, tail] + eyes
    parts += _risers(M("ray_line", "#e0e1dd", rough=0.8), [((0.3, 0, 0), (0.7, 0, 1.06)), ((-0.3, 0, 0), (-0.7, 0, 1.06))])
    return parts


def glider_delta_jet():
    body = M("delta_body", "#f8f9fa", metal=0.5, rough=0.25, texture="panel", tex_scale=2)
    dark = M("delta_dark", "#212529", metal=0.7, rough=0.3, texture="carbon", tex_scale=3)
    glow = M("delta_glow", "#00e5ff", emit=4.0)
    red = M("delta_red", "#ff006e", emit=3.0)
    parts = _handlebar(dark, dark)
    wing = core.prism("delta_wing", [(-1.3, -0.35), (0.0, 0.9), (1.3, -0.35), (0.0, -0.1)], 0.05, (0, 0.0, 1.0), (90, 0, 0),
                      body, bevel=0.01, axis="Y")
    fuselage = core.cylinder("fuselage", 0.12, 1.2, (0, 0.15, 1.05), (90, 0, 0), dark, verts=16, radius_top=0.05, bevel=0.02)
    canopy = core.sphere("canopy", 0.1, (0, 0.35, 1.12), scale=(0.8, 2.0, 0.6), mat=glow)
    engines = []
    for s in (1, -1):
        engines.append(core.cylinder("engine", 0.07, 0.3, (0.45 * s, -0.2, 1.0), (90, 0, 0), dark, verts=16, bevel=0.01))
        engines.append(core.cylinder("exhaust", 0.055, 0.01, (0.45 * s, -0.355, 1.0), (90, 0, 0), glow, verts=16))
        engines.append(core.sphere("nav_light", 0.025, (1.25 * s, -0.33, 1.0), mat=red if s > 0 else glow))
        engines.append(core.prism("tailfin", [(0.0, 0.0), (-0.25, 0.0), (-0.32, 0.25), (-0.15, 0.25)], 0.02,
                                  (0.25 * s, 0.0, 1.03), mat=dark, axis="X"))
    parts += [wing, fuselage, canopy] + engines
    parts += _risers(dark, [((0.3, 0, 0), (0.4, 0.1, 0.98)), ((-0.3, 0, 0), (-0.4, 0.1, 0.98))])
    return parts


def glider_phoenix():
    f1 = M("phoenix_f1", "#d00000", rough=0.5, emit=0.8, texture="leaf", tex_scale=3)
    f2 = M("phoenix_f2", "#ff7b00", rough=0.5, emit=1.6)
    f3 = M("phoenix_f3", "#ffba08", rough=0.5, emit=2.5)
    gold = M("phoenix_gold", "#ffd166", metal=1.0, rough=0.25)
    parts = _handlebar(gold, M("phoenix_grip", "#370617", rough=0.8, texture="leather"))
    for s in (1, -1):
        for k, (mat, length, z, spread) in enumerate(((f1, 1.6, 1.1, 0), (f2, 1.25, 1.05, 8), (f3, 0.9, 1.0, 16))):
            for j in range(5):
                ang = -10 + j * 14 + spread
                ln = length * (1.0 - 0.08 * j)
                rad = math.radians(ang)
                center = Vector((s * (0.15 + math.cos(rad) * ln / 2), -0.05 * k - 0.02 * j, z + math.sin(rad) * ln / 2 * 0.6))
                parts.append(core.prism(f"feather{s}{k}{j}", [(-ln / 2, 0.0), (-ln / 4, 0.16), (ln / 2, 0.0), (-ln / 4, -0.12)],
                                        0.02, center, (0, -s * 12, s * ang * 0.6), mat, axis="Z"))
    parts.append(core.sphere("phoenix_heart", 0.09, (0, 0.0, 1.12), mat=f3))
    parts.append(core.cylinder("crest", 0.04, 0.4, (0, 0.18, 1.25), (-60, 0, 0), f2, verts=6, radius_top=0.002))
    parts += _risers(gold, [((0.3, 0, 0), (0.5, 0, 1.05)), ((-0.3, 0, 0), (-0.5, 0, 1.05))])
    return parts


GLIDERS = {"glider_wing_sail": glider_wing_sail, "glider_patchwork": glider_patchwork, "glider_kite_ray": glider_kite_ray,
           "glider_delta_jet": glider_delta_jet, "glider_phoenix": glider_phoenix}


# ------------------------------------------------------------------- props
def prop_boombox():
    parts = backpack_boombox()
    # free-standing version: drop the straps and add little feet
    keep = [p for p in parts if not p.name.startswith(("strap", "buckle"))]
    foot = M("boom_foot", "#111111", rough=0.8)
    keep += [core.box("foot", (0.06, 0.06, 0.02), (0.15 * s, -0.09, -0.13), mat=foot, bevel=0.005) for s in (1, -1)]
    return keep


PROPS = {"prop_boombox": prop_boombox}


# ------------------------------------------------------------------- build
def build_rigid(category: str, asset_id: str, builder, render: bool = True, **preview) -> dict:
    core.reset_scene()
    result = builder()
    parts, head = (result if isinstance(result, tuple) else (result, None))
    obj = core.finalize(parts, asset_id)
    sockets = {}
    if category == "pickaxes":
        s1 = core.socket("socket_grip", (0, 0, 0))
        s2 = core.socket("socket_head", head)
        s1.parent = s2.parent = obj
        sockets = {"grip": [0, 0, 0], "head": list(head)}
    elif category == "backpacks":
        s = core.socket("socket_back", (0, 0, 0))
        s.parent = obj
        sockets = {"back": [0, 0, 0]}
    elif category == "gliders":
        s = core.socket("socket_handle", (0, 0, 0))
        s.parent = obj
        sockets = {"handle": [0, 0, 0]}
    entry = core.export(category, asset_id, [obj])
    entry.update({"type": category[:-1], "sockets": sockets, "bounds": core.bounds([obj])})
    if render:
        from xgb.previews import render_preview
        entry["thumb"] = render_preview(asset_id, [obj], **preview)
    return entry
