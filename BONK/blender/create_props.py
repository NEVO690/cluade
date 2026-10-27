"""Skin accessories and course props for BONK!

Accessories are modelled in character space (where they sit on the rest-pose
character) and the game attaches them to the "head" joint.  Props are
modelled at their real in-game size with the pivot at the origin.
"""

import math

import bpy
from mathutils import Euler

from bonk_mesh import MeshBuilder, material

NOW = {}  # no bone weights for static props


def _obj(builder, name, mat):
    return builder.to_object(name, mat)


# --------------------------------------------------------------------------- accessories
def acc_crown():
    gold = material("Acc_Gold", "#ffcc33", roughness=0.25, metallic=0.9)
    gem = material("Acc_Ruby", "#ff2d6f", roughness=0.15, emission="#ff2d6f", emission_strength=0.6)
    m = MeshBuilder()
    m.cylinder((0, 0, 1.30), (0, 0, 1.42), 0.215, 0.225, NOW, segs=24, caps=False)
    for i in range(6):
        a = 2 * math.pi * i / 6
        x, y = math.sin(a) * 0.21, math.cos(a) * 0.21
        m.cone((x, y, 1.41), (x * 1.05, y * 1.05, 1.56), 0.055, NOW, segs=8)
    o1 = _obj(m, "Crown", gold)
    g = MeshBuilder()
    for i in range(6):
        a = 2 * math.pi * i / 6 + math.pi / 6
        g.sphere((math.sin(a) * 0.225, math.cos(a) * 0.225, 1.36), (0.03, 0.03, 0.03), NOW, segs=8, rings=6)
    o2 = _obj(g, "CrownGems", gem)
    return [o1, o2]


def acc_viking():
    steel = material("Acc_Steel", "#c9d3e0", roughness=0.3, metallic=0.8)
    horn = material("Acc_Horn", "#fff4d6", roughness=0.6)
    m = MeshBuilder()
    m.sphere((0, 0, 1.18), (0.40, 0.37, 0.30), NOW, segs=24, rings=12)
    o1 = _obj(m, "VikingHelm", steel)
    h = MeshBuilder()
    for sx in (1, -1):
        # Three-segment curved horn.
        pts = [(0.34 * sx, 0, 1.30), (0.48 * sx, 0, 1.40), (0.56 * sx, 0, 1.55), (0.55 * sx, 0, 1.70)]
        radii = [0.08, 0.06, 0.04, 0.012]
        for i in range(3):
            h.cylinder(pts[i], pts[i + 1], radii[i], radii[i + 1], NOW, segs=10)
    o2 = _obj(h, "VikingHorns", horn)
    return [o1, o2]


def acc_chef():
    white = material("Acc_Cloth", "#ffffff", roughness=0.85)
    m = MeshBuilder()
    m.cylinder((0, 0, 1.30), (0, 0, 1.58), 0.22, 0.25, NOW, segs=20)
    for i in range(5):
        a = 2 * math.pi * i / 5
        m.sphere((math.sin(a) * 0.16, math.cos(a) * 0.16, 1.66), (0.14, 0.14, 0.12), NOW, segs=12, rings=8)
    m.sphere((0, 0, 1.70), (0.17, 0.17, 0.13), NOW, segs=14, rings=8)
    return [_obj(m, "ChefHat", white)]


def acc_shades():
    lens = material("Acc_Lens", "#111122", roughness=0.05, metallic=0.5)
    frame = material("Acc_Frame", "#ff3d8b", roughness=0.4)
    m = MeshBuilder()
    for sx in (1, -1):
        m.sphere((0.11 * sx, 0.40, 1.05), (0.10, 0.03, 0.07), NOW, segs=14, rings=8,
                 rot=Euler((0, 0, math.radians(-12 * sx))))
    o1 = _obj(m, "ShadesLens", lens)
    f = MeshBuilder()
    f.cylinder((-0.05, 0.425, 1.07), (0.05, 0.425, 1.07), 0.012, 0.012, NOW, segs=6)
    for sx in (1, -1):
        f.cylinder((0.20 * sx, 0.39, 1.07), (0.30 * sx, 0.20, 1.08), 0.014, 0.014, NOW, segs=6)
    o2 = _obj(f, "ShadesFrame", frame)
    return [o1, o2]


def acc_bow():
    pink = material("Acc_Bow", "#ff5fa8", roughness=0.5)
    m = MeshBuilder()
    c = (0.17, 0.10, 1.33)
    m.sphere((c[0] + 0.09, c[1], c[2] + 0.05), (0.10, 0.05, 0.07), NOW, segs=12, rings=8,
             rot=Euler((0, math.radians(-25), 0)))
    m.sphere((c[0] - 0.09, c[1], c[2] - 0.03), (0.10, 0.05, 0.07), NOW, segs=12, rings=8,
             rot=Euler((0, math.radians(-25), 0)))
    m.sphere(c, (0.04, 0.05, 0.04), NOW, segs=10, rings=6)
    return [_obj(m, "Bow", pink)]


def acc_halo():
    glow = material("Acc_Halo", "#fff1a8", roughness=0.2, emission="#ffe066", emission_strength=3.0)
    m = MeshBuilder()
    m.torus((0, 0, 1.86), 0.20, 0.028, NOW, segs=32, rings=10)
    return [_obj(m, "Halo", glow)]


def acc_propeller():
    cap = material("Acc_Cap", "#2f7bff", roughness=0.5)
    blade = material("Acc_Blade", "#ffd23f", roughness=0.4)
    m = MeshBuilder()
    m.sphere((0, 0, 1.26), (0.36, 0.34, 0.20), NOW, segs=20, rings=10)
    m.box((0, 0.30, 1.22), (0.34, 0.20, 0.04), NOW)
    m.cylinder((0, 0, 1.44), (0, 0, 1.55), 0.025, 0.025, NOW, segs=8)
    o1 = _obj(m, "PropCap", cap)
    b = MeshBuilder()
    b.box((0, 0, 1.56), (0.62, 0.09, 0.02), NOW)
    b.sphere((0, 0, 1.57), (0.04, 0.04, 0.03), NOW, segs=8, rings=6)
    o2 = _obj(b, "Propeller", blade)  # spun by the game
    return [o1, o2]


def acc_party():
    hat = material("Acc_Party", "#7c4dff", roughness=0.5)
    pom = material("Acc_Pom", "#3ff2c4", roughness=0.7)
    m = MeshBuilder()
    m.cone((0.05, 0, 1.33), (0.10, -0.02, 1.80), 0.17, NOW, segs=18)
    o1 = _obj(m, "PartyHat", hat)
    p = MeshBuilder()
    p.sphere((0.10, -0.02, 1.82), (0.055, 0.055, 0.055), NOW, segs=10, rings=8)
    o2 = _obj(p, "PartyPom", pom)
    return [o1, o2]


ACCESSORIES = {
    "crown": acc_crown,
    "viking": acc_viking,
    "chef_hat": acc_chef,
    "shades": acc_shades,
    "bow": acc_bow,
    "halo": acc_halo,
    "propeller": acc_propeller,
    "party_hat": acc_party,
}


# --------------------------------------------------------------------------- props
def prop_hammer(name, length, head_radius, head_half_len):
    """Pendulum hammer hanging from the origin, head axis along X (matches the sim)."""
    wood = material("Prop_Handle", "#6b3fa0", roughness=0.6)
    head = material("Prop_HammerHead", "#ff3d6e", roughness=0.35)
    band = material("Prop_Band", "#ffd23f", roughness=0.3, metallic=0.4)
    m = MeshBuilder()
    m.cylinder((0, 0, 0.2), (0, 0, -length + head_radius * 0.6), 0.12, 0.14, NOW, segs=12)
    m.sphere((0, 0, 0), (0.28, 0.28, 0.28), NOW, segs=14, rings=8)
    o1 = _obj(m, name + "_Handle", wood)
    h = MeshBuilder()
    h.cylinder((-head_half_len, 0, -length), (head_half_len, 0, -length), head_radius, head_radius, NOW, segs=24)
    o2 = _obj(h, name + "_Head", head)
    b = MeshBuilder()
    for sx in (-1, 1):
        x = head_half_len * 0.62 * sx
        b.cylinder((x - 0.08, 0, -length), (x + 0.08, 0, -length), head_radius * 1.05, head_radius * 1.05,
                   NOW, segs=24)
        b.cylinder((head_half_len * sx, 0, -length), (head_half_len * sx * 1.04, 0, -length),
                   head_radius * 0.8, head_radius * 0.8, NOW, segs=24)
    o3 = _obj(b, name + "_Bands", band)
    return [o1, o2, o3]


def prop_arch(name, width, height, text, color):
    post = material("Prop_ArchPost", "#ffffff", roughness=0.5)
    top = material("Prop_Arch_" + name, color, roughness=0.4)
    txt = material("Prop_ArchText", "#ffffff", roughness=0.3, emission="#ffffff", emission_strength=0.6)
    m = MeshBuilder()
    for sx in (-1, 1):
        m.cylinder((sx * width / 2, 0, 0), (sx * width / 2, 0, height), 0.35, 0.3, NOW, segs=16)
        m.sphere((sx * width / 2, 0, height + 0.15), (0.45, 0.45, 0.45), NOW, segs=16, rings=10)
    o1 = _obj(m, name + "_Posts", post)
    t = MeshBuilder()
    t.box((0, 0, height), (width, 0.5, 1.1), NOW, bevel=0.12)
    o2 = _obj(t, name + "_Banner", top)
    # 3D text on the banner (front and back).
    objs = [o1, o2]
    for flip, yoff in ((0, -0.26), (math.pi, 0.26)):
        cu = bpy.data.curves.new(name + "_TextCurve%d" % int(flip), "FONT")
        cu.body = text
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.size = 0.85
        cu.extrude = 0.04
        tob = bpy.data.objects.new(name + "_Text%d" % int(flip), cu)
        bpy.context.scene.collection.objects.link(tob)
        tob.location = (0, yoff, height)
        tob.rotation_euler = (math.pi / 2, 0, flip)
        dg = bpy.context.evaluated_depsgraph_get()
        mesh = bpy.data.meshes.new_from_object(tob.evaluated_get(dg))
        bpy.data.objects.remove(tob)
        mo = bpy.data.objects.new(name + "_Text%d" % int(flip), mesh)
        mo.location = (0, yoff, height)
        mo.rotation_euler = (math.pi / 2, 0, flip)
        mesh.materials.append(txt)
        bpy.context.scene.collection.objects.link(mo)
        objs.append(mo)
    return objs


def prop_trophy():
    gold = material("Prop_Trophy", "#ffcc33", roughness=0.2, metallic=0.9)
    base = material("Prop_TrophyBase", "#3b1f8a", roughness=0.5)
    m = MeshBuilder()
    m.cylinder((0, 0, 0.35), (0, 0, 0.75), 0.07, 0.12, NOW, segs=14)
    m.sphere((0, 0, 1.0), (0.32, 0.32, 0.34), NOW, segs=20, rings=12)
    for sx in (-1, 1):
        m.torus((0.32 * sx, 0, 1.02), 0.12, 0.03, NOW, segs=16, rings=6, rot=Euler((math.pi / 2, 0, 0)))
    m.sphere((0, 0, 1.40), (0.10, 0.10, 0.10), NOW, segs=12, rings=8)
    o1 = _obj(m, "Trophy_Cup", gold)
    b = MeshBuilder()
    b.box((0, 0, 0.18), (0.6, 0.6, 0.36), NOW, bevel=0.05)
    o2 = _obj(b, "Trophy_Base", base)
    return [o1, o2]


def prop_cloud():
    white = material("Prop_Cloud", "#ffffff", roughness=1.0)
    m = MeshBuilder()
    for (x, y, z, r) in ((0, 0, 0, 1.6), (1.6, 0.2, -0.3, 1.2), (-1.5, -0.1, -0.35, 1.1),
                         (0.7, 0.6, 0.5, 1.0), (-0.6, -0.5, 0.4, 0.95)):
        m.sphere((x, y, z), (r, r * 0.85, r * 0.7), NOW, segs=14, rings=8)
    return [_obj(m, "Cloud", white)]


PROPS = {
    "hammer": lambda: prop_hammer("Hammer", 5.6, 0.6, 0.8),
    "hammer_big": lambda: prop_hammer("HammerBig", 6.4, 0.85, 1.3),
    "finish_arch": lambda: prop_arch("Finish", 12.0, 5.0, "FINISH", "#ff3d6e"),
    "start_arch": lambda: prop_arch("Start", 14.0, 5.0, "BONK!", "#6c4bd8"),
    "trophy": prop_trophy,
    "cloud": prop_cloud,
}
