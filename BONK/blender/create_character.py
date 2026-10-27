"""Builds "Bonklet", the BONK! base character: mesh, materials and armature.

Coordinates: Blender Z up, the character faces +Y (that is also Panda3D's
forward axis after the glTF round trip).  Feet at z = 0, body top ~1.40 m,
antenna bulb ~1.70 m.

Material zones (recoloured per skin in the game):
  Bonk_Body    main colour (body, arms, legs)
  Bonk_Accent  second colour (belly, mittens, feet, antenna bulb)
  Bonk_Visor   the dark face plate
  Bonk_Eyes    glowing eyes
"""

import math

import bpy
from mathutils import Euler, Vector

from bonk_mesh import MeshBuilder, material, smoothstep

BONES = {
    # name: (head, tail, parent)
    "root": ((0, 0, 0), (0, 0, 0.2), None),
    "hips": ((0, 0, 0.42), (0, 0, 0.70), "root"),
    "spine": ((0, 0, 0.70), (0, 0, 1.05), "hips"),
    "head": ((0, 0, 1.05), (0, 0, 1.36), "spine"),
    "antenna": ((0, 0, 1.36), (0, -0.05, 1.64), "head"),
    "arm.L": ((0.36, 0, 0.92), (0.60, 0.04, 0.64), "spine"),
    "hand.L": ((0.60, 0.04, 0.64), (0.65, 0.06, 0.52), "arm.L"),
    "arm.R": ((-0.36, 0, 0.92), (-0.60, 0.04, 0.64), "spine"),
    "hand.R": ((-0.60, 0.04, 0.64), (-0.65, 0.06, 0.52), "arm.R"),
    "leg.L": ((0.17, 0, 0.42), (0.17, 0, 0.13), "hips"),
    "foot.L": ((0.17, 0, 0.13), (0.17, 0.17, 0.05), "leg.L"),
    "leg.R": ((-0.17, 0, 0.42), (-0.17, 0, 0.13), "hips"),
    "foot.R": ((-0.17, 0, 0.13), (-0.17, 0.17, 0.05), "leg.R"),
}

DEFAULT_COLORS = {"body": "#ff8a3d", "accent": "#ffe066", "visor": "#1d1840", "eyes": "#9ff7ff"}


def build_armature():
    data = bpy.data.armatures.new("BonkRig")
    rig = bpy.data.objects.new("BonkRig", data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    made = {}
    for name, (head, tail, parent) in BONES.items():
        b = data.edit_bones.new(name)
        b.head, b.tail = head, tail
        b.roll = 0.0
        # Limbs: local Z faces forward, so +X rotation swings a limb forward.
        if name.startswith(("arm", "hand", "leg")):
            b.align_roll(Vector((0, 1, 0)))
        elif name.startswith("foot"):
            b.align_roll(Vector((0, 0, 1)))
        if parent:
            b.parent = made[parent]
            b.use_connect = False
        made[name] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"
    return rig


def body_weights(co):
    """Smooth blend hips -> spine -> head up the bean-shaped body."""
    z = co.z
    w_spine = smoothstep(0.52, 0.80, z)
    w_head = smoothstep(0.95, 1.15, z)
    hips = 1.0 - w_spine
    spine = w_spine * (1.0 - w_head)
    head = w_spine * w_head
    return {"hips": hips, "spine": spine, "head": head}


def side(x, left, right):
    return left if x > 0 else right


def build_meshes(rig, colors=None):
    c = dict(DEFAULT_COLORS)
    c.update(colors or {})
    mats = {
        "body": material("Bonk_Body", c["body"], roughness=0.45),
        "accent": material("Bonk_Accent", c["accent"], roughness=0.55),
        "visor": material("Bonk_Visor", c["visor"], roughness=0.12, metallic=0.2),
        "eyes": material("Bonk_Eyes", c["eyes"], roughness=0.3, emission=c["eyes"], emission_strength=1.5),
    }
    objs = []

    # ---- main body colour: bean body, arms, legs
    mb = MeshBuilder()
    mb.sphere((0, 0, 0.86), (0.42, 0.38, 0.56), body_weights, segs=32, rings=20,
              taper=lambda zn: 1.0 - 0.10 * max(0.0, zn) + 0.04 * min(0.0, zn))
    for sx in (1, -1):
        sfx = ".L" if sx > 0 else ".R"
        mb.cylinder((0.33 * sx, 0, 0.93), (0.60 * sx, 0.04, 0.64), 0.085, 0.07, {"arm" + sfx: 1.0}, segs=12)
        mb.sphere((0.33 * sx, 0, 0.93), (0.09, 0.09, 0.09), {"arm" + sfx: 0.6, "spine": 0.4}, segs=12, rings=8)
        mb.cylinder((0.17 * sx, 0, 0.46), (0.17 * sx, 0.0, 0.12), 0.10, 0.085, {"leg" + sfx: 1.0}, segs=12)
    objs.append(mb.to_object("Bonk_Body", mats["body"], parent=rig))

    # ---- accent: belly, mittens, feet, antenna bulb
    ma = MeshBuilder()
    ma.sphere((0, 0.29, 0.62), (0.27, 0.11, 0.25), lambda co: {"hips": 0.6, "spine": 0.4}, segs=20, rings=12)
    for sx in (1, -1):
        sfx = ".L" if sx > 0 else ".R"
        ma.sphere((0.63 * sx, 0.05, 0.58), (0.11, 0.10, 0.12), {"hand" + sfx: 1.0}, segs=14, rings=10)
        ma.sphere((0.17 * sx, 0.05, 0.065), (0.13, 0.18, 0.075), {"foot" + sfx: 1.0}, segs=16, rings=10)
    ma.sphere((0, -0.05, 1.68), (0.075, 0.075, 0.075), {"antenna": 1.0}, segs=14, rings=10)
    ma.cylinder((0, 0, 1.33), (0, -0.05, 1.64), 0.028, 0.022,
                lambda co: {"head": 1.0 - smoothstep(1.36, 1.6, co.z), "antenna": smoothstep(1.36, 1.6, co.z)},
                segs=8)
    objs.append(ma.to_object("Bonk_Accent", mats["accent"], parent=rig))

    # ---- visor (face plate)
    mv = MeshBuilder()
    mv.sphere((0, 0.27, 1.02), (0.31, 0.14, 0.21), {"head": 0.85, "spine": 0.15}, segs=24, rings=14)
    objs.append(mv.to_object("Bonk_Visor", mats["visor"], parent=rig))

    # ---- eyes
    me = MeshBuilder()
    for sx in (1, -1):
        me.sphere((0.105 * sx, 0.395, 1.045), (0.06, 0.03, 0.09), {"head": 1.0}, segs=12, rings=8,
                  rot=Euler((0, 0, math.radians(-14 * sx))))
    objs.append(me.to_object("Bonk_Eyes", mats["eyes"], parent=rig))
    return objs


def build_character(colors=None):
    rig = build_armature()
    meshes = build_meshes(rig, colors)
    return rig, meshes


def head_bone_rest():
    """World position of the head bone (accessories are modelled relative to it)."""
    return Vector(BONES["head"][0])
