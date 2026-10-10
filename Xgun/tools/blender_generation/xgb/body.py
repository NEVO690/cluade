"""Base body graph shared by the character and every garment.

The body is a Skin-modifier tube network. Garments are built from *subsets*
of the same graph with larger radii, so sleeves, trousers and jackets follow
the body exactly and deform with the same bones.
"""
from __future__ import annotations

import math

import bpy  # must precede bmesh/mathutils when running as the bpy module
import bmesh
from mathutils import Vector

from xgb import core
from xgb.rig import weight_auto, weight_rigid

# name: (position, radius_x, radius_y)
NODES: dict[str, tuple] = {
    "pelvis": ((0, 0.0, 0.95), 0.150, 0.110),
    "waist": ((0, 0.005, 1.08), 0.128, 0.092),
    "belly": ((0, 0.012, 1.19), 0.140, 0.100),
    "chest": ((0, 0.018, 1.31), 0.162, 0.112),
    "upchest": ((0, 0.005, 1.40), 0.150, 0.098),
    "neck0": ((0, 0.0, 1.47), 0.056, 0.056),
    "neck1": ((0, 0.01, 1.55), 0.050, 0.050),
}
for side, s in (("R", 1), ("L", -1)):
    NODES.update({
        f"sh.{side}": ((0.17 * s, -0.01, 1.405), 0.066, 0.066),
        f"uarm.{side}": ((0.28 * s, -0.01, 1.318), 0.054, 0.054),
        f"elbow.{side}": ((0.392 * s, -0.01, 1.224), 0.044, 0.044),
        f"farm.{side}": ((0.49 * s, -0.005, 1.14), 0.044, 0.042),
        f"wrist.{side}": ((0.585 * s, 0.0, 1.062), 0.033, 0.030),
        f"hip.{side}": ((0.10 * s, 0.0, 0.90), 0.090, 0.090),
        f"thigh.{side}": ((0.105 * s, 0.006, 0.72), 0.078, 0.078),
        f"knee.{side}": ((0.11 * s, 0.01, 0.52), 0.058, 0.058),
        f"calf.{side}": ((0.112 * s, -0.008, 0.36), 0.057, 0.057),
        f"ankle.{side}": ((0.115 * s, -0.01, 0.11), 0.038, 0.038),
    })

EDGES = [("pelvis", "waist"), ("waist", "belly"), ("belly", "chest"), ("chest", "upchest"),
         ("upchest", "neck0"), ("neck0", "neck1")]
for side in "RL":
    EDGES += [("upchest", f"sh.{side}"), (f"sh.{side}", f"uarm.{side}"), (f"uarm.{side}", f"elbow.{side}"),
              (f"elbow.{side}", f"farm.{side}"), (f"farm.{side}", f"wrist.{side}"),
              ("pelvis", f"hip.{side}"), (f"hip.{side}", f"thigh.{side}"), (f"thigh.{side}", f"knee.{side}"),
              (f"knee.{side}", f"calf.{side}"), (f"calf.{side}", f"ankle.{side}")]

TORSO = ["pelvis", "waist", "belly", "chest", "upchest"]
ARM_R = ["sh.R", "uarm.R", "elbow.R", "farm.R", "wrist.R"]
ARM_L = [n.replace(".R", ".L") for n in ARM_R]
LEG_R = ["hip.R", "thigh.R", "knee.R", "calf.R", "ankle.R"]
LEG_L = [n.replace(".R", ".L") for n in LEG_R]


def graph_mesh(name: str, nodes: list[str], mat, scale: float = 1.0, overrides: dict | None = None,
               offsets: dict | None = None, subdiv: int = 1, root: str | None = None, margin: float = 0.0):
    """Skin mesh over a subset of the body graph.

    Radius = body radius * ``scale`` + ``margin`` (an absolute thickness, so thin
    limbs still get a visible garment layer)."""
    overrides = overrides or {}
    offsets = offsets or {}
    idx = {n: i for i, n in enumerate(nodes)}
    verts, radii = [], []
    for n in nodes:
        pos, rx, ry = NODES[n]
        p = Vector(pos) + Vector(offsets.get(n, (0, 0, 0)))
        verts.append(p)
        if n in overrides:
            o = overrides[n]
            radii.append(o if isinstance(o, tuple) else (o, o))  # absolute radius
        else:
            radii.append((rx * scale + margin, ry * scale + margin))
    edges = [(idx[a], idx[b]) for a, b in EDGES if a in idx and b in idx]
    return core.skin_mesh(name, verts, edges, radii, mat, subdiv=subdiv, root=idx.get(root or nodes[0], 0))


def sphere_cut(name, radius, loc, scale, mat, keep, segments=24, rings=14, rot=(0, 0, 0)):
    """UV sphere with vertices removed where ``keep(local_co)`` is False (hair caps, helmets, hoods)."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius, calc_uvs=True)
    doomed = [v for v in bm.verts if not keep(v.co / radius)]
    bmesh.ops.delete(bm, geom=doomed, context="VERTS")
    obj = core._new_obj(name, bm, mat)
    core._place(obj, loc, rot, scale)
    sol = obj.modifiers.new("solid", "SOLIDIFY")
    sol.thickness = radius * 0.08
    sol.offset = 1.0
    core.smooth(obj, 180)
    return obj


# --------------------------------------------------------------------------
def body_parts(skin: str, covered=()) -> list[tuple]:
    """Return [(object, weighting)] for the bare body: torso/limbs, hands, head and face.

    ``covered`` lists graph nodes hidden under clothing; the body is slimmed
    there so it never pokes through garments when posed."""
    skin_mat = core.material(f"skin_{skin}", skin, rough=0.55, texture="plain")
    parts = []
    body = graph_mesh("body", list(NODES), skin_mat, root="pelvis", overrides={n: (NODES[n][1] * 0.8, NODES[n][2] * 0.8) for n in covered})
    parts.append((body, "auto"))
    for side, s in (("R", 1), ("L", -1)):
        parts.extend((o, f"hand.{side}") for o in hand(side, s, skin_mat))
    parts.extend((o, "head") for o in head(skin_mat))
    return parts


def hand(side, s, mat):
    # palm + finger block form a relaxed fist pointing along the hand bone direction
    d = Vector((0.766 * s, 0, -0.643))
    wrist = Vector((0.591 * s, 0.0, 1.057))
    palm = core.box(f"palm.{side}", (0.1, 0.09, 0.038), wrist + d * 0.05, (0, 40 * s, 0), mat, bevel=0.012)
    fingers = core.box(f"fingers.{side}", (0.085, 0.092, 0.042), wrist + d * 0.125 + Vector((0, 0.0, -0.012)),
                       (0, 40 * s, 0), mat, bevel=0.014)
    thumb = core.tube(f"thumb.{side}", [wrist + d * 0.03 + Vector((0, 0.03, 0)),
                                         wrist + d * 0.07 + Vector((0, 0.05, -0.005)),
                                         wrist + d * 0.1 + Vector((0, 0.045, -0.02))], 0.016, mat, seg=8)
    for o in (palm, fingers):
        core.subdivide(o, 1)
    return [palm, fingers, thumb]


def head(mat):
    parts = []
    skull = core.sphere("skull", 0.1, (0, 0.012, 1.665), scale=(1.0, 1.08, 1.18), mat=mat, segments=28, rings=18)
    jaw = core.sphere("jaw", 0.075, (0, 0.045, 1.6), scale=(1.05, 1.0, 0.8), mat=mat, segments=20, rings=12)
    nose = core.sphere("nose", 0.017, (0, 0.118, 1.652), scale=(1.0, 1.1, 1.5), mat=mat, segments=10, rings=8)
    parts += [skull, jaw, nose]
    for s in (1, -1):
        parts.append(core.sphere("ear", 0.022, (0.098 * s, 0.0, 1.665), scale=(0.5, 1.0, 1.4), mat=mat,
                                 segments=10, rings=8))
    white = core.material("eye_white", "#f4f2ee", rough=0.3)
    iris = core.material("eye_iris", "#1d1a24", rough=0.15)
    brow = core.material("brow", "#2a1d17", rough=0.8)
    lip = core.material("lip", "#a65e55", rough=0.5)
    for s in (1, -1):
        parts.append(core.sphere("eye", 0.019, (0.037 * s, 0.093, 1.68), scale=(1.0, 0.7, 1.05), mat=white,
                                 segments=12, rings=8))
        parts.append(core.sphere("iris", 0.0105, (0.037 * s, 0.105, 1.681), scale=(1.0, 0.5, 1.1), mat=iris,
                                 segments=10, rings=6))
        parts.append(core.box("brow", (0.034, 0.008, 0.008), (0.04 * s, 0.103, 1.708), (0, 8 * s, 0), brow,
                              bevel=0.003))
    parts.append(core.box("mouth", (0.034, 0.006, 0.006), (0, 0.106, 1.608), (0, 0, 0), lip, bevel=0.002))
    return parts


def finish_character(arm, parts: list[tuple], name: str):
    """Bake every part, weight it, join into one skinned mesh and bind to the rig."""
    baked = []
    bpy.context.view_layer.update()  # make every part's matrix_world current before baking
    for obj, weighting in parts:
        core.bake_part(obj)
        if weighting == "auto":
            weight_auto(obj)
        elif isinstance(weighting, list):
            weight_auto(obj, weighting)
        else:
            weight_rigid(obj, weighting)
        baked.append(obj)
    mesh = core.join(baked, name)
    from xgb.rig import bind
    bind(mesh, arm)
    return mesh
