"""The Season 1 outfits. Each returns [(object, weighting)] layered on the base body.

Weighting is "auto" (blended nearest-bone skinning), a list of bones to
blend between, or one bone name for rigid pieces (armour, hats, shoes).
"""
from __future__ import annotations

import math

from mathutils import Vector

from xgb import core
from xgb.body import ARM_L, ARM_R, LEG_L, LEG_R, NODES, TORSO, body_parts, graph_mesh, sphere_cut

M = core.material
SIDES = (("R", 1), ("L", -1))


# --------------------------------------------------------------------------
# reusable garment pieces
# --------------------------------------------------------------------------
UPPER = TORSO + ["neck0"]
ARMS = ARM_R + ARM_L
LEGS = LEG_R + LEG_L


def top(name, mat, scale=1.04, sleeves="long", overrides=None, collar=True, margin=0.016):
    arm = {"long": ARM_R + ARM_L, "elbow": ARM_R[:3] + ARM_L[:3], "short": ARM_R[:2] + ARM_L[:2], "none": []}[sleeves]
    nodes = ["pelvis"] + TORSO[1:] + (["neck0"] if collar else []) + arm
    ov = {"pelvis": (0.165, 0.126), "neck0": (0.072, 0.07)}
    ov.update(overrides or {})
    return graph_mesh(name, nodes, mat, scale, ov, root="chest", margin=margin)


def pants(name, mat, scale=1.04, length="full", overrides=None, margin=0.016):
    leg = {"full": 5, "calf": 4, "knee": 3, "shorts": 2}[length]
    nodes = ["pelvis", "waist"] + LEG_R[:leg] + LEG_L[:leg]
    ov = {"waist": (0.142, 0.104)}
    ov.update(overrides or {})
    # full-length legs reach into the shoes so the rounded end caps stay hidden
    offsets = {"ankle.R": (0, 0, -0.05), "ankle.L": (0, 0, -0.05)} if length == "full" else {}
    return graph_mesh(name, nodes, mat, scale, ov, root="pelvis", offsets=offsets, margin=margin)


def sneaker(side, s, upper, sole, accent, high=False, name="shoe"):
    x = 0.115 * s
    parts = [
        core.box(f"{name}_sole.{side}", (0.1, 0.27, 0.035), (x, 0.045, 0.018), mat=sole, bevel=0.012),
        core.sphere(f"{name}_upper.{side}", 0.06, (x, 0.05, 0.065), scale=(0.82, 2.0, 0.85), mat=upper,
                    segments=18, rings=10),
        core.sphere(f"{name}_toe.{side}", 0.05, (x, 0.135, 0.05), scale=(0.95, 1.0, 0.7), mat=sole,
                    segments=14, rings=8),
        core.box(f"{name}_stripe.{side}", (0.006, 0.12, 0.022), (x + 0.048 * s, 0.03, 0.06), (0, 0, -6 * s),
                 accent, bevel=0.003),
        core.box(f"{name}_heel.{side}", (0.05, 0.02, 0.05), (x, -0.075, 0.09), mat=accent, bevel=0.006),
    ]
    for i in range(3):
        parts.append(core.box(f"{name}_lace{i}.{side}", (0.05, 0.008, 0.006), (x, 0.06 + i * 0.025, 0.112 - i * 0.008),
                              (12, 0, 0), sole, bevel=0.002))
    if high:
        parts.append(core.cylinder(f"{name}_collar.{side}", 0.052, 0.09, (x, -0.01, 0.15), mat=upper, verts=14,
                                   radius_top=0.046))
    return [(p, f"foot.{side}") for p in parts]


def boot(side, s, mat, sole, *, shaft=0.22, spikes=None, cuff=None):
    x = 0.115 * s
    parts = [(core.box(f"boot_sole.{side}", (0.11, 0.28, 0.045), (x, 0.045, 0.022), mat=sole, bevel=0.012), f"foot.{side}"),
             (core.sphere(f"boot_foot.{side}", 0.065, (x, 0.055, 0.07), scale=(0.85, 1.95, 0.9), mat=mat,
                          segments=18, rings=10), f"foot.{side}"),
             (core.cylinder(f"boot_shaft.{side}", 0.06, shaft, (x, -0.01, 0.06 + shaft / 2), mat=mat, verts=16,
                            radius_top=0.056), ["shin." + side, "foot." + side])]
    if cuff:
        parts.append((core.torus(f"boot_cuff.{side}", 0.062, 0.016, (x, -0.01, 0.06 + shaft), mat=cuff), "shin." + side))
    if spikes:
        for i in range(4):
            for j in (-1, 1):
                parts.append((core.cylinder(f"spike.{side}", 0.008, 0.025, (x + j * 0.035, -0.06 + i * 0.07, -0.008),
                                            (180, 0, 0), spikes, verts=6, radius_top=0.001), f"foot.{side}"))
    return parts


def gloves(mat, cuff=None, scale=1.15):
    out = []
    for side, s in SIDES:
        d = Vector((0.766 * s, 0, -0.643))
        w = Vector((0.591 * s, 0.0, 1.057))
        palm = core.box(f"glove_palm.{side}", (0.09 * scale, 0.082 * scale, 0.036 * scale), w + d * 0.05, (0, 40 * s, 0),
                        mat, bevel=0.014)
        fing = core.box(f"glove_fing.{side}", (0.074 * scale, 0.084 * scale, 0.04 * scale), w + d * 0.115 + Vector((0, 0, -0.012)),
                        (0, 40 * s, 0), mat, bevel=0.016)
        thumb = core.tube(f"glove_thumb.{side}", [w + d * 0.03 + Vector((0, 0.03, 0)), w + d * 0.07 + Vector((0, 0.052, -0.005)),
                                                  w + d * 0.1 + Vector((0, 0.047, -0.02))], 0.016, mat, seg=8)
        out += [(palm, f"hand.{side}"), (fing, f"hand.{side}"), (thumb, f"hand.{side}")]
        if cuff:
            out.append((core.torus(f"glove_cuff.{side}", 0.038, 0.013, w - d * 0.005, (0, 130 * s, 0), cuff), f"hand.{side}"))
    return out


def arm_band(node, mat, radius_scale=1.25, width=0.012, name="band"):
    pos, rx, _ = NODES[node]
    s = 1 if node.endswith("R") else -1
    # arm axis in A-pose
    return core.torus(name, rx * radius_scale, width, pos, (0, 130 * s, 0), mat, seg=20, ring=8)


def hair_cap(mat, *, hairline=0.15, back=-0.55, scale=(1.08, 1.12, 1.14), z=1.672):
    return sphere_cut("hair", 0.104, (0, 0.006, z), scale, mat,
                      keep=lambda c: c.z > (-0.15 if c.y < 0 else hairline) and not (c.y > 0.55 and c.z < 0.55)
                      and c.z > back + (0.4 if c.y > 0.2 else 0))


def belt(mat, buckle, z=0.985, rx=0.162, ry=0.123):
    b = core.torus("belt", 1.0, 0.024, (0, 0.002, z), mat=mat, scale=(rx, ry, 0.8), seg=28, ring=6)
    k = core.box("buckle", (0.06, 0.02, 0.042), (0, ry + 0.012, z), mat=buckle, bevel=0.006)
    return [(b, "hips"), (k, "hips")]


def pouch(loc, mat, flap, size=(0.07, 0.04, 0.07), rot=(0, 0, 0), bone="hips"):
    return [(core.box("pouch", size, loc, rot, mat, bevel=0.01), bone),
            (core.box("pouch_flap", (size[0] * 1.04, size[1] * 1.1, size[2] * 0.35),
                      (loc[0], loc[1] + 0.003, loc[2] + size[2] * 0.36), rot, flap, bevel=0.008), bone)]


def emblem_x(loc, size, mat, rot=(90, 0, 0)):
    a = core.box("emblem_a", (size * 0.22, size, 0.006), loc, (rot[0], rot[1], 45), mat, bevel=0.002)
    b = core.box("emblem_b", (size * 0.22, size, 0.006), loc, (rot[0], rot[1], -45), mat, bevel=0.002)
    return [a, b]


# --------------------------------------------------------------------------
# outfits
# --------------------------------------------------------------------------
def vex_runner():
    hood_c = M("vex_hoodie", "#2b2f3a", rough=0.85, texture="fabric", tex_scale=3)
    jog = M("vex_jogger", "#4b5263", rough=0.9, texture="knit", tex_scale=3)
    neon = M("vex_neon", "#00e5ff", rough=0.4, emit=2.0)
    white = M("vex_white", "#eef1f4", rough=0.6, texture="rubber")
    pink = M("vex_cap", "#ff3d71", rough=0.7, texture="fabric", tex_scale=4)
    hair = M("vex_hair", "#1e1410", rough=0.8, texture="leather")
    tape = M("vex_tape", "#f8f6f0", rough=0.9, texture="fabric", tex_scale=6)
    chain = M("vex_chain", "#d4af37", metal=1.0, rough=0.25)
    parts = body_parts("#c98e6b", TORSO + ARMS + LEGS)
    parts.append((top("hoodie", hood_c, 1.08, overrides={"wrist.R": 0.05, "wrist.L": 0.05, "pelvis": (0.172, 0.132)}),
                  "auto"))
    parts.append((pants("joggers", jog, 1.05, overrides={"ankle.R": 0.05, "ankle.L": 0.05}), "auto"))
    # hood bunched behind the neck
    parts.append((core.torus("hood_roll", 0.082, 0.032, (0, -0.02, 1.47), (12, 0, 0), hood_c, scale=(1.15, 1.0, 1.0)), "chest"))
    parts.append((sphere_cut("hood_back", 0.11, (0, -0.075, 1.5), (1.05, 0.7, 0.8), hood_c,
                             keep=lambda c: c.y < 0.1 and c.z > -0.3), "chest"))
    parts.append((core.box("kangaroo", (0.2, 0.03, 0.1), (0, 0.128, 1.11), (-6, 0, 0), hood_c, bevel=0.02), "spine"))
    for s in (1, -1):
        parts.append((core.tube("drawstring", [(0.03 * s, 0.11, 1.44), (0.035 * s, 0.135, 1.36), (0.04 * s, 0.14, 1.28)],
                                0.005, white), "chest"))
        parts.append((core.cylinder("aglet", 0.007, 0.025, (0.04 * s, 0.14, 1.265), mat=neon, verts=8), "chest"))
    for node in ("elbow.R", "elbow.L"):
        parts.append((arm_band(node, neon, 1.3, 0.009, "sleeve_band"), "forearm." + node[-1]))
    parts.append((core.torus("chain", 0.085, 0.006, (0, 0.04, 1.43), (20, 0, 0), chain, seg=24, ring=6,
                             scale=(1.0, 1.15, 1.0)), "chest"))
    for side, s in SIDES:
        parts.append((core.torus("jog_cuff", 0.05, 0.016, (0.115 * s, -0.01, 0.15), mat=jog), f"shin.{side}"))
        parts += sneaker(side, s, white, M("vex_sole", "#d9dde3", rough=0.7, texture="rubber"), neon, high=False)
        d = Vector((0.766 * s, 0, -0.643))
        w = Vector((0.591 * s, 0.0, 1.057))
        parts.append((core.torus("tape", 0.036, 0.013, w + d * 0.11, (0, 130 * s, 0), tape, seg=16, ring=6,
                                 scale=(1.0, 1.15, 1.0)), f"hand.{side}"))
    # backwards snapback + short hair
    parts.append((hair_cap(hair, hairline=0.2), "head"))
    parts.append((sphere_cut("cap", 0.112, (0, 0.0, 1.71), (1.04, 1.1, 0.95), pink,
                             keep=lambda c: c.z > 0.05), "head"))
    parts.append((core.box("cap_brim", (0.15, 0.11, 0.012), (0, -0.14, 1.72), (-12, 0, 0), pink, bevel=0.02), "head"))
    parts.append((core.cylinder("cap_button", 0.012, 0.012, (0, 0.0, 1.816), mat=neon, verts=10), "head"))
    for p in emblem_x((0, 0.138, 1.33), 0.07, neon):
        parts.append((p, "chest"))
    return parts


def tidal_drifter():
    suit = M("tide_suit", "#16425b", rough=0.45, texture="rubber")
    panel = M("tide_panel", "#4cc9f0", rough=0.45, texture="rubber")
    shorts = M("tide_shorts", "#f77f00", rough=0.8, texture="fabric", tex_scale=3)
    shorts2 = M("tide_shorts_trim", "#fcbf49", rough=0.8)
    hair = M("tide_hair", "#e9c46a", rough=0.75, texture="leather")
    lens = M("tide_lens", "#8fd3ff", metal=1.0, rough=0.06)
    frame = M("tide_frame", "#ffffff", rough=0.3)
    shell = M("tide_shell", "#fff1e6", rough=0.4)
    shoe = M("tide_shoe", "#264653", rough=0.6, texture="rubber")
    parts = body_parts("#8d5a3b", TORSO + ["sh.R", "uarm.R", "sh.L", "uarm.L", "hip.R", "thigh.R", "knee.R", "hip.L", "thigh.L", "knee.L"])
    parts.append((top("wetsuit_top", suit, 1.0, sleeves="elbow", collar=True, margin=0.01), "auto"))
    parts.append((pants("wetsuit_legs", suit, 1.0, length="calf", margin=0.01), "auto"))
    # chest + side panels
    parts.append((core.prism("chest_panel", [(-0.14, 0.0), (0.14, 0.0), (0.1, 0.12), (-0.1, 0.12)], 0.02,
                             (0, 0.118, 1.26), (0, 0, 0), panel, axis="Y"), "chest"))
    for s in (1, -1):
        parts.append((core.box("side_stripe", (0.012, 0.05, 0.3), (0.152 * s, 0.0, 1.2), mat=panel, bevel=0.005), ["chest", "spine"]))
        parts.append((arm_band(f"elbow.{'R' if s > 0 else 'L'}", panel, 1.12, 0.014, "suit_cuff"),
                      f"upper_arm.{'R' if s > 0 else 'L'}"))
    parts.append((pants("boardshorts", shorts, 1.12, length="shorts", margin=0.03,
                        overrides={"thigh.R": 0.118, "thigh.L": 0.118, "waist": (0.158, 0.12)}), "auto"))
    parts.append((core.torus("shorts_band", 1.0, 0.018, (0, 0.003, 1.02), mat=shorts2, scale=(0.165, 0.125, 1)), "hips"))
    for s in (1, -1):
        parts.append((core.box("short_trim", (0.03, 0.004, 0.16), (0.2 * s, 0.03, 0.82), (0, 0, 0), shorts2, bevel=0.002),
                      "thigh." + ("R" if s > 0 else "L")))
    # mop of hair
    parts.append((hair_cap(hair, hairline=0.35, scale=(1.14, 1.16, 1.2)), "head"))
    for i, (x, y, z, r) in enumerate([(0.05, 0.07, 1.755, 0.05), (-0.05, 0.075, 1.75, 0.05), (0.0, 0.08, 1.77, 0.05),
                                      (0.08, 0.0, 1.74, 0.045), (-0.08, 0.0, 1.74, 0.045), (0, -0.07, 1.74, 0.06),
                                      (0.06, -0.05, 1.7, 0.05), (-0.06, -0.05, 1.7, 0.05)]):
        parts.append((core.sphere(f"lock{i}", r, (x, y, z), scale=(1.1, 1.0, 0.7), mat=hair, segments=12, rings=8), "head"))
    # mirrored shades
    for s in (1, -1):
        parts.append((core.box("lens", (0.045, 0.01, 0.028), (0.038 * s, 0.112, 1.682), (0, 0, -6 * s), lens, bevel=0.008), "head"))
        parts.append((core.box("temple", (0.006, 0.09, 0.006), (0.075 * s, 0.065, 1.69), mat=frame), "head"))
    parts.append((core.box("bridge", (0.03, 0.008, 0.006), (0, 0.118, 1.69), mat=frame), "head"))
    # shell necklace
    for i in range(9):
        a = math.radians(-60 + i * 15)
        parts.append((core.sphere("shell", 0.012, (math.sin(a) * 0.075, 0.035 + math.cos(a) * 0.06, 1.44 - abs(math.cos(a)) * 0.01),
                                  scale=(1, 0.6, 1.2), mat=shell if i % 2 else panel, segments=8, rings=6), "chest"))
    for side, s in SIDES:
        parts += boot(side, s, shoe, M("tide_sole", "#e9edc9", rough=0.7, texture="rubber"), shaft=0.08)
        parts.append((core.torus("leash", 0.05, 0.01, (0.115 * s, -0.01, 0.2), mat=panel), f"shin.{side}"))
    return parts


def glitch_medic():
    suit = M("medic_suit", "#e7ecef", rough=0.75, texture="fabric", tex_scale=3)
    vest = M("medic_vest", "#3d405b", rough=0.7, texture="panel")
    red = M("medic_red", "#ef233c", rough=0.5, emit=0.6)
    glove = M("medic_glove", "#7b2cbf", rough=0.35, texture="rubber")
    boot_m = M("medic_boot", "#1b1b1e", rough=0.6, texture="leather")
    hair = M("medic_hair", "#3a2618", rough=0.8, texture="leather")
    lens = M("medic_lens", "#38f9d7", rough=0.1, emit=1.5)
    rim = M("medic_rim", "#9aa0a6", metal=1.0, rough=0.3)
    strap = M("medic_strap", "#22223b", rough=0.8, texture="fabric")
    parts = body_parts("#f1c27d", TORSO + ARMS + LEGS)
    parts.append((top("jumpsuit_top", suit, 1.04), "auto"))
    parts.append((pants("jumpsuit_legs", suit, 1.06), "auto"))
    parts.append((graph_mesh("vest", ["waist", "belly", "chest", "upchest"], vest, 1.1,
                             {"upchest": (0.19, 0.13)}, root="chest", margin=0.03), ["spine", "chest"]))
    for s, side in ((1, "R"), (-1, "L")):
        parts += pouch((0.09 * s, 0.13, 1.16), vest, strap, (0.07, 0.035, 0.06), bone="spine")
        parts.append((arm_band(f"uarm.{side}", red if side == "L" else strap, 1.3, 0.016, "armband"), f"upper_arm.{side}"))
        parts.append((core.box("kneepad", (0.1, 0.04, 0.11), (0.115 * s, 0.075, 0.52), mat=vest, bevel=0.02), f"shin.{side}"))
        parts += boot(side, s, boot_m, M("medic_sole", "#2b2d42", rough=0.8, texture="rubber"), shaft=0.2)
    # red cross on left arm band, chest and back
    for loc, rot, bone in (((-0.31, 0.0, 1.33), (90, 0, -90), "upper_arm.L"), ((0.0, 0.142, 1.3), (90, 0, 0), "chest"),
                           ((0.0, -0.13, 1.3), (90, 0, 0), "chest")):
        parts.append((core.box("cross_v", (0.022, 0.07, 0.006), loc, rot, red, bevel=0.002), bone))
        parts.append((core.box("cross_h", (0.07, 0.022, 0.006), loc, rot, red, bevel=0.002), bone))
    parts += belt(strap, rim)
    parts += [(o, "hips") for o, _ in pouch((0.16, 0.05, 0.94), M("medic_kit", "#fefae0", rough=0.5), red,
                                            (0.06, 0.09, 0.08), (0, 0, 90))]
    parts.append((core.box("kit_cross", (0.006, 0.04, 0.014), (0.195, 0.05, 0.94), mat=red), "hips"))
    parts += gloves(glove)
    # ponytail
    parts.append((hair_cap(hair, hairline=0.25), "head"))
    parts.append((core.sphere("pony_tie", 0.022, (0, -0.105, 1.72), mat=red, segments=10, rings=8), "head"))
    parts.append((core.tube("ponytail", [(0, -0.11, 1.72), (0, -0.16, 1.68), (0, -0.175, 1.6), (0, -0.165, 1.52)], 0.03,
                            hair, radii=[0.028, 0.034, 0.028, 0.012]), ["head", "neck"]))
    # flip goggles on forehead
    for s in (1, -1):
        parts.append((core.torus("goggle_rim", 0.026, 0.008, (0.038 * s, 0.098, 1.745), (80, 0, 0), rim, seg=16, ring=6), "head"))
        parts.append((core.sphere("goggle_lens", 0.025, (0.038 * s, 0.1, 1.745), scale=(1, 0.4, 1), mat=lens), "head"))
    parts.append((core.torus("goggle_strap", 1.0, 0.009, (0, 0.0, 1.735), (6, 0, 0), strap, scale=(0.112, 0.118, 1)), "head"))
    return parts


def volt_brawler():
    jacket = M("volt_jacket", "#6dff3c", rough=0.55, texture="fabric", tex_scale=3)
    black = M("volt_black", "#121418", rough=0.6, texture="fabric", tex_scale=3)
    neon = M("volt_neon", "#c6ff00", rough=0.4, emit=1.2)
    wrap = M("volt_wrap", "#f5f3ee", rough=0.9, texture="fabric", tex_scale=6)
    glove = M("volt_glove", "#e01e37", rough=0.4, texture="leather")
    phones = M("volt_phones", "#1d1d22", rough=0.35)
    hair = M("volt_hair", "#0f0b09", rough=0.85, texture="leather")
    zip_m = M("volt_zip", "#c0c0c0", metal=1.0, rough=0.3)
    parts = body_parts("#5b3a29", TORSO + ARMS + LEGS)
    parts.append((top("track_jacket", jacket, 1.07, overrides={"neck0": (0.088, 0.085), "wrist.R": 0.048, "wrist.L": 0.048}),
                  "auto"))
    parts.append((pants("track_pants", black, 1.06, overrides={"ankle.R": 0.054, "ankle.L": 0.054}), "auto"))
    parts.append((core.box("zipper", (0.012, 0.01, 0.38), (0, 0.13, 1.25), (-4, 0, 0), zip_m), ["spine", "chest"]))
    for side, s in SIDES:
        pts = [Vector(NODES[n][0]) + Vector((0, -0.01, 0.055 if i < 2 else 0.045)) for i, n in
               enumerate([f"sh.{side}", f"uarm.{side}", f"elbow.{side}", f"farm.{side}", f"wrist.{side}"])]
        parts.append((core.tube("sleeve_stripe", pts, 0.012, black), "auto"))
        lp = [Vector(NODES[n][0]) + Vector((0.075 * s, 0, 0)) for n in (f"hip.{side}", f"thigh.{side}", f"knee.{side}",
                                                                        f"calf.{side}")]
        lp[0] += Vector((0.02 * s, 0, 0))
        parts.append((core.tube("pant_stripe", lp, 0.011, neon), "auto"))
        parts += sneaker(side, s, M("volt_shoe", "#f8f9fa", rough=0.5, texture="leather"), black, neon, high=True)
        d = Vector((0.766 * s, 0, -0.643))
        w = Vector((0.591 * s, 0.0, 1.057))
        parts.append((core.torus("hand_wrap", 0.04, 0.016, w - d * 0.01, (0, 130 * s, 0), wrap, seg=16, ring=6), f"hand.{side}"))
    parts += [(o, w) for o, w in gloves(glove, scale=1.3)]
    # flat-top fade
    parts.append((hair_cap(hair, hairline=0.3, scale=(1.05, 1.08, 1.06)), "head"))
    parts.append((core.box("flattop", (0.17, 0.19, 0.07), (0, 0.0, 1.785), mat=hair, bevel=0.03), "head"))
    # studio headphones around the neck-top
    parts.append((core.torus("phone_band", 0.118, 0.012, (0, -0.005, 1.7), (0, 90, 0), phones, arc=180, seg=20, ring=8,
                             scale=(1, 1, 1.05)), "head"))
    for s in (1, -1):
        parts.append((core.cylinder("phone_cup", 0.045, 0.035, (0.118 * s, -0.005, 1.68), (0, 90, 0), phones, verts=18,
                                    bevel=0.008), "head"))
        parts.append((core.torus("phone_ring", 0.035, 0.006, (0.137 * s, -0.005, 1.68), (0, 90, 0), neon, seg=18, ring=6), "head"))
    for p in emblem_x((0.08, 0.14, 1.35), 0.05, neon):
        parts.append((p, "chest"))
    return parts


def frost_warden():
    parka = M("frost_parka", "#e3ebf2", rough=0.8, texture="fabric", tex_scale=2)
    panel = M("frost_panel", "#3a6ea5", rough=0.7, texture="fabric", tex_scale=3)
    fur = M("frost_fur", "#f3ead8", rough=1.0, texture="knit", tex_scale=5)
    pants_m = M("frost_pants", "#2f3e46", rough=0.85, texture="denim", tex_scale=3)
    boot_m = M("frost_boot", "#4a3728", rough=0.7, texture="leather")
    steel = M("frost_steel", "#b8c4ce", metal=1.0, rough=0.3)
    ice = M("frost_ice", "#9be7ff", rough=0.05, emit=1.2)
    mitt = M("frost_mitt", "#3a6ea5", rough=0.85, texture="knit", tex_scale=4)
    parts = body_parts("#e0ac69", TORSO + ARMS + LEGS)
    parts.append((top("parka", parka, 1.18, margin=0.03, overrides={"wrist.R": 0.066, "wrist.L": 0.066,
                                                                     "pelvis": (0.21, 0.17), "neck0": (0.095, 0.095)}), "auto"))
    # quilting rings around the torso
    for i, z in enumerate((1.02, 1.12, 1.22, 1.32)):
        parts.append((core.torus(f"quilt{i}", 1.0, 0.016, (0, 0.012, z), mat=panel if i == 1 else parka,
                                 scale=(0.205 - 0.004 * i, 0.155 - 0.003 * i, 1)), ["spine", "chest"] if z > 1.15 else ["hips", "spine"]))
    # coat skirt
    parts.append((core.cylinder("coat_skirt", 0.25, 0.26, (0, 0.0, 0.86), mat=parka, verts=24, radius_top=0.2, cap=False,
                                ), ["hips", "thigh.R", "thigh.L"]))
    for s in (1, -1):
        parts.append((core.box("chest_pocket", (0.09, 0.03, 0.08), (0.1 * s, 0.16, 1.3), mat=panel, bevel=0.012), "chest"))
        parts.append((arm_band(f"elbow.{'R' if s > 0 else 'L'}", panel, 1.55, 0.02, "elbow_patch"), f"forearm.{'R' if s > 0 else 'L'}"))
    # fur-lined hood framing the face
    parts.append((sphere_cut("hood", 0.135, (0, -0.02, 1.67), (1.05, 1.05, 1.08), parka,
                             keep=lambda c: c.y < 0.55 and c.z > -0.62), "head"))
    parts.append((core.torus("hood_fur", 0.118, 0.04, (0, 0.06, 1.68), (90 - 12, 0, 0), fur, scale=(1.0, 1.25, 1.0),
                             seg=28, ring=10), "head"))
    parts.append((core.torus("scarf", 0.09, 0.03, (0, 0.02, 1.49), (8, 0, 0), panel, scale=(1.1, 1.1, 1.0)), "neck"))
    # ice goggles on the hood
    for s in (1, -1):
        parts.append((core.sphere("goggle", 0.03, (0.045 * s, 0.11, 1.76), scale=(1.2, 0.5, 0.9), mat=ice), "head"))
    parts.append((core.box("goggle_band", (0.2, 0.02, 0.018), (0, 0.105, 1.76), mat=steel, bevel=0.006), "head"))
    parts.append((pants("snow_pants", pants_m, 1.1, margin=0.02), "auto"))
    for side, s in SIDES:
        parts += boot(side, s, boot_m, M("frost_sole", "#22252a", rough=0.9, texture="rubber"), shaft=0.24,
                      spikes=steel, cuff=fur)
        parts.append((core.box("thigh_pocket", (0.03, 0.09, 0.1), (0.19 * s, 0.0, 0.7), mat=panel, bevel=0.01), f"thigh.{side}"))
    parts += gloves(mitt, cuff=fur, scale=1.35)
    for p in emblem_x((-0.1, 0.165, 1.3), 0.05, ice):
        parts.append((p, "chest"))
    return parts


def nova_sentinel():
    under = M("nova_under", "#15171d", rough=0.5, texture="hex", tex_scale=4)
    plate = M("nova_plate", "#e8eef8", metal=0.35, rough=0.28, texture="panel", tex_scale=2)
    dark = M("nova_dark", "#2a2f3a", metal=0.6, rough=0.35, texture="brushed")
    glow = M("nova_glow", "#00e5ff", rough=0.2, emit=4.0)
    visor = M("nova_visor", "#0b0f19", metal=0.9, rough=0.05)
    parts = body_parts("#a26b4b", TORSO + ARMS + LEGS)
    parts.append((top("undersuit", under, 1.0, margin=0.01), "auto"))
    parts.append((pants("underlegs", under, 1.0, margin=0.01), "auto"))
    # chest cuirass and abs
    parts.append((core.prism("cuirass", [(-0.17, 0.0), (0.17, 0.0), (0.2, 0.14), (0.12, 0.2), (-0.12, 0.2), (-0.2, 0.14)],
                             0.06, (0, 0.11, 1.24), (0, 0, 0), plate, bevel=0.012, axis="Y"), "chest"))
    parts.append((core.prism("backplate", [(-0.16, 0.0), (0.16, 0.0), (0.18, 0.18), (-0.18, 0.18)], 0.05, (0, -0.1, 1.24),
                             (0, 0, 0), plate, bevel=0.012, axis="Y"), "chest"))
    for i in range(3):
        parts.append((core.box(f"ab{i}", (0.2 - 0.02 * i, 0.04, 0.045), (0, 0.105, 1.18 - 0.055 * i), mat=dark if i % 2 else plate,
                               bevel=0.01), "spine" if i < 2 else "hips"))
    parts.append((core.cylinder("reactor", 0.035, 0.03, (0, 0.145, 1.36), (90, 0, 0), glow, verts=20), "chest"))
    parts.append((core.torus("reactor_ring", 0.042, 0.009, (0, 0.142, 1.36), (90, 0, 0), dark, seg=20, ring=6), "chest"))
    for side, s in SIDES:
        sh = Vector(NODES[f"sh.{side}"][0])
        parts.append((sphere_cut("pauldron", 0.11, sh + Vector((0.03 * s, 0, 0.03)), (1.0, 1.0, 0.8), plate,
                                 keep=lambda c: c.z > -0.05), f"upper_arm.{side}"))
        parts.append((core.torus("pauldron_trim", 0.1, 0.008, sh + Vector((0.03 * s, 0, 0.022)), (0, 0, 0), glow,
                                 scale=(1.0, 1.0, 0.8), seg=24, ring=6), f"upper_arm.{side}"))
        f = Vector(NODES[f"farm.{side}"][0])
        parts.append((core.cylinder("bracer", 0.058, 0.17, f, (0, 130 * s, 0), plate, verts=16, radius_top=0.05, bevel=0.006),
                      f"forearm.{side}"))
        parts.append((core.torus("bracer_glow", 0.06, 0.006, f + Vector((-0.03 * s, 0, 0.03)), (0, 130 * s, 0), glow), f"forearm.{side}"))
        parts.append((core.box("thigh_plate", (0.13, 0.05, 0.22), (0.11 * s, 0.07, 0.72), (8, 0, 0), plate, bevel=0.015), f"thigh.{side}"))
        parts.append((core.box("knee_cop", (0.1, 0.05, 0.08), (0.11 * s, 0.075, 0.52), (0, 0, 0), dark, bevel=0.02), f"shin.{side}"))
        parts.append((core.box("greave", (0.11, 0.05, 0.26), (0.113 * s, 0.065, 0.3), (-4, 0, 0), plate, bevel=0.015), f"shin.{side}"))
        parts.append((core.box("greave_glow", (0.012, 0.01, 0.18), (0.113 * s, 0.093, 0.3), (-4, 0, 0), glow), f"shin.{side}"))
        parts += boot(side, s, dark, plate, shaft=0.12)
    parts += gloves(dark, scale=1.2)
    # helmet with visor and fin
    parts.append((sphere_cut("helmet", 0.13, (0, 0.005, 1.685), (1.0, 1.08, 1.05), plate,
                             keep=lambda c: c.z > -0.75 and not (c.y > 0.35 and -0.45 < c.z < 0.35)), "head"))
    parts.append((sphere_cut("visor", 0.128, (0, 0.012, 1.68), (0.98, 1.06, 1.0), visor,
                             keep=lambda c: c.y > 0.3 and -0.5 < c.z < 0.4), "head"))
    parts.append((core.box("visor_line", (0.18, 0.008, 0.008), (0, 0.142, 1.69), mat=glow), "head"))
    parts.append((core.prism("fin", [(-0.1, 0.0), (0.12, 0.0), (0.02, 0.07)], 0.014, (0, -0.01, 1.82), (0, 0, 0), dark,
                             bevel=0.004, axis="X"), "head"))
    for s in (1, -1):
        parts.append((core.cylinder("ear_pod", 0.035, 0.03, (0.135 * s, 0.0, 1.68), (0, 90, 0), dark, verts=16, bevel=0.006), "head"))
    return parts


def ember_ronin():
    robe = M("ember_robe", "#9d0208", rough=0.7, texture="fabric", tex_scale=3)
    inner = M("ember_inner", "#f8f4ec", rough=0.8, texture="fabric", tex_scale=3)
    hakama = M("ember_hakama", "#16161a", rough=0.85, texture="denim", tex_scale=3)
    gold = M("ember_gold", "#ffba08", metal=1.0, rough=0.3)
    lacquer = M("ember_lacquer", "#2b0a0a", metal=0.2, rough=0.2, texture="scales", tex_scale=3)
    straw = M("ember_straw", "#c9a66b", rough=0.9, texture="wood", tex_scale=4)
    cord = M("ember_cord", "#d00000", rough=0.6)
    ember = M("ember_glow", "#ff7b00", rough=0.3, emit=3.0)
    sandal = M("ember_sandal", "#5c3d2e", rough=0.8, texture="wood")
    sock = M("ember_sock", "#f1f1f1", rough=0.9, texture="fabric", tex_scale=5)
    mask = M("ember_mask", "#111111", metal=0.3, rough=0.35)
    parts = body_parts("#d8a47f", TORSO + ARMS + LEGS)
    parts.append((top("robe", robe, 1.08, overrides={"farm.R": 0.085, "farm.L": 0.085, "wrist.R": 0.1, "wrist.L": 0.1,
                                                      "neck0": (0.078, 0.074)}), "auto"))
    # crossed white inner collar (V)
    for s in (1, -1):
        parts.append((core.box("collar", (0.035, 0.012, 0.26), (0.045 * s, 0.128, 1.36), (0, 25 * s, 0), inner, bevel=0.006), "chest"))
    parts.append((pants("hakama", hakama, 1.12, margin=0.02, overrides={"knee.R": 0.11, "knee.L": 0.11, "calf.R": 0.13, "calf.L": 0.13,
                                                            "ankle.R": 0.12, "ankle.L": 0.12}), "auto"))
    # obi sash + knot + ember charms
    parts.append((core.torus("obi", 1.0, 0.045, (0, 0.005, 1.03), mat=gold, scale=(0.17, 0.13, 0.9), seg=28, ring=8), "hips"))
    parts.append((core.box("obi_knot", (0.1, 0.05, 0.07), (0.06, 0.14, 1.02), (0, 0, 12), cord, bevel=0.02), "hips"))
    parts.append((core.tube("obi_tail", [(0.08, 0.15, 1.0), (0.1, 0.17, 0.9), (0.11, 0.165, 0.8)], 0.018, cord), ["hips", "thigh.R"]))
    for i in range(3):
        parts.append((core.sphere("ember_charm", 0.014, (-0.06 + i * 0.025, 0.155, 0.98 - i * 0.01), mat=ember, segments=10,
                                  rings=6), "hips"))
    # layered shoulder guards (sode)
    for side, s in SIDES:
        sh = Vector(NODES[f"sh.{side}"][0])
        for k in range(3):
            parts.append((core.box(f"sode{k}", (0.17, 0.2, 0.03), sh + Vector((0.07 * s + 0.012 * k * s, 0, -0.04 - 0.05 * k)),
                                   (0, 30 * s, 0), lacquer, bevel=0.01), f"upper_arm.{side}"))
            parts.append((core.box(f"sode_trim{k}", (0.172, 0.202, 0.008), sh + Vector((0.07 * s + 0.012 * k * s, 0, -0.058 - 0.05 * k)),
                                   (0, 30 * s, 0), gold), f"upper_arm.{side}"))
        x = 0.115 * s
        parts.append((core.cylinder("tabi", 0.045, 0.1, (x, -0.0, 0.1), mat=sock, verts=14), ["shin." + side, "foot." + side]))
        parts.append((core.sphere("tabi_foot", 0.055, (x, 0.055, 0.06), scale=(0.85, 1.9, 0.75), mat=sock), f"foot.{side}"))
        parts.append((core.box("geta", (0.1, 0.26, 0.03), (x, 0.045, 0.015), mat=sandal, bevel=0.008), f"foot.{side}"))
        parts.append((core.torus("strap", 0.04, 0.007, (x, 0.08, 0.06), (0, 90, 0), cord, scale=(1, 1.3, 1)), f"foot.{side}"))
    # half mask, topknot and wide kasa hat
    parts.append((sphere_cut("menpo", 0.108, (0, 0.02, 1.64), (1.0, 1.05, 1.0), mask,
                             keep=lambda c: c.y > 0.25 and c.z < -0.05), "head"))
    hair = M("ember_hair", "#120c0a", rough=0.75, texture="leather")
    parts.append((hair_cap(hair, hairline=0.3), "head"))
    parts.append((core.lathe("kasa", [(0.36, 0.0), (0.3, 0.035), (0.18, 0.08), (0.06, 0.12), (0.0, 0.13)], (0, 0.0, 1.735),
                             mat=straw, seg=32), "head"))
    parts.append((core.torus("kasa_band", 0.13, 0.012, (0, 0, 1.775), mat=cord, seg=24, ring=6), "head"))
    parts.append((core.tube("chin_cord", [(0.11, 0.0, 1.74), (0.09, 0.05, 1.6), (0.0, 0.08, 1.56), (-0.09, 0.05, 1.6),
                                          (-0.11, 0.0, 1.74)], 0.005, cord), "head"))
    parts += gloves(M("ember_glove", "#3c1518", rough=0.6, texture="leather"), cuff=gold)
    return parts


OUTFITS = {
    "outfit_vex_runner": vex_runner,
    "outfit_tidal_drifter": tidal_drifter,
    "outfit_glitch_medic": glitch_medic,
    "outfit_volt_brawler": volt_brawler,
    "outfit_frost_warden": frost_warden,
    "outfit_nova_sentinel": nova_sentinel,
    "outfit_ember_ronin": ember_ronin,
}
