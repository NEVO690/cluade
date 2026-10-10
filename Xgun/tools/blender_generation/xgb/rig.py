"""The shared Xgun humanoid skeleton, pose solver, animation library and skinning.

Every outfit is skinned to this one armature, so all animations (locomotion,
weapon holds, emotes) work on every skin. Poses are authored in *character
space* (+Y forward, +X right, Z up) as bone direction targets and two-bone IK
goals; the solver converts them to bone-local quaternions.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

from xgb.core import link

# name: (head, tail, parent, deform)
BONES: dict[str, tuple] = {
    "root":        ((0, 0, 0), (0, 0.3, 0), None, False),
    "hips":        ((0, 0, 0.95), (0, 0, 1.07), "root", True),
    "spine":       ((0, 0, 1.07), (0, 0.01, 1.24), "hips", True),
    "chest":       ((0, 0.01, 1.24), (0, 0, 1.43), "spine", True),
    "neck":        ((0, 0, 1.43), (0, 0.01, 1.53), "chest", True),
    "head":        ((0, 0.01, 1.53), (0, 0.01, 1.78), "neck", True),
}
for side, s in (("R", 1), ("L", -1)):
    BONES.update({
        f"shoulder.{side}":  ((0.03 * s, 0, 1.40), (0.17 * s, -0.01, 1.41), "chest", True),
        f"upper_arm.{side}": ((0.17 * s, -0.01, 1.41), (0.392 * s, -0.01, 1.224), f"shoulder.{side}", True),
        f"forearm.{side}":   ((0.392 * s, -0.01, 1.224), (0.591 * s, 0.0, 1.057), f"upper_arm.{side}", True),
        f"hand.{side}":      ((0.591 * s, 0.0, 1.057), (0.721 * s, 0.0, 0.948), f"forearm.{side}", True),
        f"thigh.{side}":     ((0.10 * s, 0, 0.94), (0.11 * s, 0.01, 0.52), "hips", True),
        f"shin.{side}":      ((0.11 * s, 0.01, 0.52), (0.115 * s, -0.01, 0.09), f"thigh.{side}", True),
        f"foot.{side}":      ((0.115 * s, -0.01, 0.09), (0.12 * s, 0.15, 0.02), f"shin.{side}", True),
    })
ORDER = list(BONES)
DEFORM = [b for b in ORDER if BONES[b][3]]

SOCKET_BACK = (0.0, -0.135, 1.30)


def V(x, y, z) -> Vector:
    return Vector((x, y, z)).normalized()


def rest_matrices(arm) -> dict[str, Matrix]:
    return {b.name: b.matrix_local.copy() for b in arm.data.bones}


# --------------------------------------------------------------------------
# armature
# --------------------------------------------------------------------------
def build_armature(name: str = "XgunRig"):
    global ORDER
    ORDER = list(BONES)  # socket bones are appended again by add_sockets()
    bpy_parent_cache.clear()
    data = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, data)
    link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for bname in ORDER:
        head, tail, parent, deform = BONES[bname]
        eb = data.edit_bones.new(bname)
        eb.head, eb.tail = Vector(head), Vector(tail)
        eb.roll = 0.0
        eb.use_deform = deform
        if parent:
            eb.parent = data.edit_bones[parent]
            eb.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return arm


def add_socket_bone(arm, name: str, parent: str, world_matrix: Matrix) -> None:
    """Add a non-deforming socket bone whose rest world matrix is ``world_matrix``."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones.new(name)
    eb.head = (0, 0, 0)
    eb.tail = (0, 0.1, 0)
    eb.matrix = world_matrix
    eb.length = 0.1
    eb.use_deform = False
    eb.parent = arm.data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.pose.bones[name].rotation_mode = "QUATERNION"


# --------------------------------------------------------------------------
# pose solving
# --------------------------------------------------------------------------
def two_bone_ik(a: Vector, target: Vector, l1: float, l2: float, pole: Vector) -> tuple[Vector, Vector]:
    to = target - a
    d = max(abs(l1 - l2) + 1e-3, min(l1 + l2 - 1e-3, to.length))
    u = to.normalized()
    cos_a = max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)))
    sin_a = math.sqrt(max(0.0, 1 - cos_a * cos_a))
    p = pole - u * pole.dot(u)
    p = p.normalized() if p.length > 1e-6 else Vector((0, 1, 0))
    elbow = a + u * (l1 * cos_a) + p * (l1 * sin_a)
    reach = a + u * d
    return (elbow - a).normalized(), (reach - elbow).normalized()


def bone_length(name: str) -> float:
    h, t = BONES[name][0], BONES[name][1]
    return (Vector(t) - Vector(h)).length


def solve(rest: dict[str, Matrix], pose: dict) -> tuple[dict[str, Quaternion], Vector, dict[str, Matrix]]:
    """Return local rotations, hips location (bone space) and posed world matrices.

    pose keys:
      dirs:  {bone: Vector | (Vector, twist_degrees)} world-space bone direction
      ik:    {"hand.R"|"hand.L"|"foot.R"|"foot.L": (target_head_pos, pole_vector)}
      hips:  world offset of the hips (crouch, bob)
    """
    dirs: dict = dict(pose.get("dirs", {}))
    ik = pose.get("ik", {})
    hips_offset = Vector(pose.get("hips", (0, 0, 0)))
    posed: dict[str, Matrix] = {}
    rots: dict[str, Quaternion] = {}
    hips_loc = Vector()
    for name in ORDER:
        if name not in rest:
            continue
        parent = BONES.get(name, (None, None, None))[2] if name in BONES else None
        if name not in BONES:  # socket bones
            parent = bpy_parent_cache.get(name)
        if parent:
            m0 = posed[parent] @ (rest[parent].inverted() @ rest[name])
        else:
            m0 = rest[name].copy()
        if name == "hips":
            m0 = Matrix.Translation(hips_offset) @ m0
            hips_loc = rest[name].to_3x3().inverted() @ hips_offset
        # IK chains are resolved when their first bone is reached
        for end, (b1, b2) in (("hand.R", ("upper_arm.R", "forearm.R")), ("hand.L", ("upper_arm.L", "forearm.L")),
                              ("foot.R", ("thigh.R", "shin.R")), ("foot.L", ("thigh.L", "shin.L"))):
            if name == b1 and end in ik:
                target, pole = ik[end]
                d1, d2 = two_bone_ik(m0.translation.copy(), Vector(target), bone_length(b1), bone_length(b2),
                                     Vector(pole))
                dirs[b1], dirs[b2] = d1, d2
        rot = Quaternion()
        if name in dirs:
            spec = dirs[name]
            target, twist = (spec if isinstance(spec, tuple) else (spec, 0.0))
            target = Vector(target).normalized()
            m0q = m0.to_quaternion()
            y0 = m0q @ Vector((0, 1, 0))
            qw = y0.rotation_difference(target)
            if twist:
                qw = Quaternion(target, math.radians(twist)) @ qw
            rot = m0q.inverted() @ qw @ m0q
        rots[name] = rot
        posed[name] = m0 @ rot.to_matrix().to_4x4()
    return rots, hips_loc, posed


bpy_parent_cache: dict[str, str] = {}


# --------------------------------------------------------------------------
# pose library
# --------------------------------------------------------------------------
UP = V(0, 0, 1)


def legs_fk(swing_r: float, knee_r: float, swing_l: float, knee_l: float, foot_r=0.0, foot_l=0.0,
            spread: float = 0.03) -> dict:
    """Leg directions from thigh swing / knee bend angles in degrees (+swing = forward)."""
    out = {}
    for side, sw, kn, ft, s in (("R", swing_r, knee_r, foot_r, 1), ("L", swing_l, knee_l, foot_l, -1)):
        a = math.radians(sw)
        b = math.radians(sw - kn)
        f = math.radians(sw - kn + 70 + ft)
        out[f"thigh.{side}"] = V(spread * s, math.sin(a), -math.cos(a))
        out[f"shin.{side}"] = V(0.0, math.sin(b), -math.cos(b))
        out[f"foot.{side}"] = V(0.0, math.sin(f), -math.cos(f))
    return out


def arms_relaxed(swing_r=0.0, swing_l=0.0, bend=20.0, out=0.18) -> dict:
    res = {}
    for side, sw, s in (("R", swing_r, 1), ("L", swing_l, -1)):
        a = math.radians(sw)
        b = math.radians(sw + bend)
        res[f"upper_arm.{side}"] = V(out * s, math.sin(a), -math.cos(a))
        res[f"forearm.{side}"] = V(out * 0.6 * s, math.sin(b), -math.cos(b))
        res[f"hand.{side}"] = V(out * 0.4 * s, math.sin(b) * 1.1, -math.cos(b))
    return res


def torso(lean=0.0, side=0.0, twist=0.0, head_pitch=0.0, head_yaw=0.0) -> dict:
    """Spine/chest/head directions: ``lean`` forward degrees, ``side`` roll, ``twist`` yaw."""
    l, s = math.radians(lean), math.radians(side)
    d = V(math.sin(s), math.sin(l), math.cos(l) * math.cos(s))
    l2 = math.radians(lean * 1.2)
    dc = V(math.sin(s), math.sin(l2), math.cos(l2) * math.cos(s))
    hp, hy = math.radians(head_pitch - lean * 0.8), math.radians(head_yaw)
    dh = V(math.sin(hy) * 0.3 + math.sin(s) * 0.5, math.sin(hp), math.cos(hp))
    return {"spine": (d, twist * 0.5), "chest": (dc, twist * 0.5), "neck": dh, "head": dh}


def merge(*parts: dict) -> dict:
    out: dict = {"dirs": {}, "ik": {}}
    for p in parts:
        if "dirs" in p or "ik" in p or "hips" in p:
            out["dirs"].update(p.get("dirs", {}))
            out["ik"].update(p.get("ik", {}))
            if "hips" in p:
                out["hips"] = p["hips"]
        else:
            out["dirs"].update(p)
    return out


# Weapon holding (upper body). Wrist targets in character space.
RIFLE_R = ((0.17, 0.30, 1.24), V(0.7, -0.3, -0.6), V(-0.25, 0.92, -0.15))
RIFLE_L = ((-0.03, 0.56, 1.25), V(-0.7, -0.1, -0.7), V(0.35, 0.85, 0.25))
PISTOL_R = ((0.09, 0.44, 1.33), V(0.7, -0.2, -0.7), V(-0.15, 0.95, 0.05))
PISTOL_L = ((-0.02, 0.40, 1.29), V(-0.7, -0.2, -0.7), V(0.45, 0.8, 0.2))
PICK_R = ((0.27, 0.22, 1.04), V(0.5, -0.6, -0.4), V(0.0, 0.85, 0.5))


def hold(kind: str, breathe: float = 0.0, recoil: float = 0.0, lean: float = 4.0) -> dict:
    """Upper-body pose holding a weapon type: rifle / pistol / pickaxe / none."""
    dz = breathe * 0.008
    dy = -recoil * 0.04
    t = torso(lean=lean, head_pitch=-2)
    if kind == "rifle":
        (r, rp, rd), (l, lp, ld) = RIFLE_R, RIFLE_L
    elif kind == "pistol":
        (r, rp, rd), (l, lp, ld) = PISTOL_R, PISTOL_L
    elif kind == "pickaxe":
        (r, rp, rd) = PICK_R
        return merge(t, {"dirs": {"hand.R": rd, **{k: v for k, v in arms_relaxed(0, 8, 25).items() if k.endswith("L")}},
                         "ik": {"hand.R": (Vector(r) + Vector((0, 0, dz)), rp)}})
    else:
        return merge(t, arms_relaxed(0, 0))
    off = Vector((0, dy, dz))
    return merge(t, {"dirs": {"hand.R": rd, "hand.L": ld},
                     "ik": {"hand.R": (Vector(r) + off, rp), "hand.L": (Vector(l) + off, lp)}})


def stand(hips=(0, 0, 0)) -> dict:
    return {"dirs": legs_fk(0, 4, 0, 4), "hips": hips}


def animations() -> dict[str, dict]:
    """name -> {"frames": [(frame, pose)], "loop": bool}"""
    A: dict[str, dict] = {}

    def anim(name, keys, loop=True):
        A[name] = {"frames": keys, "loop": loop}

    # --- idle / lobby -----------------------------------------------------
    anim("idle", [(f, merge(stand((0, 0, -0.01 * b)), torso(lean=2 + b, head_pitch=-b), arms_relaxed(2, -2, 18 + 4 * b)))
                  for f, b in ((0, 0), (30, 1), (60, 0))])
    anim("lobby_idle", [
        (0, merge({"dirs": legs_fk(4, 6, -6, 4, 0, 0, 0.07)}, torso(lean=1, side=2, twist=-8, head_yaw=10),
                  arms_relaxed(4, -3, 24, 0.22))),
        (45, merge({"dirs": legs_fk(4, 8, -6, 6, 0, 0, 0.07), "hips": (0, 0, -0.012)}, torso(lean=3, side=3, twist=-10, head_yaw=-6),
                   arms_relaxed(2, -1, 30, 0.24))),
        (90, merge({"dirs": legs_fk(4, 6, -6, 4, 0, 0, 0.07)}, torso(lean=1, side=2, twist=-8, head_yaw=10),
                   arms_relaxed(4, -3, 24, 0.22))),
    ])

    # --- locomotion ---------------------------------------------------------
    def cycle(name, frames, stride, knee, bob, lean, arm, arm_bend):
        keys = []
        steps = 8
        for i in range(steps + 1):
            ph = 2 * math.pi * i / steps
            sr = stride * math.sin(ph)
            sl = -sr
            kr = knee * max(0.0, math.sin(ph + math.pi / 2)) ** 2 + 6
            kl = knee * max(0.0, math.sin(ph - math.pi / 2)) ** 2 + 6
            hz = -bob * abs(math.cos(ph))
            keys.append((round(frames * i / steps),
                         merge({"dirs": legs_fk(sr, kr, sl, kl, -sr * 0.3, -sl * 0.3), "hips": (0, 0, hz)},
                               torso(lean=lean, twist=6 * math.sin(ph)),
                               arms_relaxed(-arm * math.sin(ph), arm * math.sin(ph), arm_bend))))
        anim(name, keys)

    cycle("walk", 36, 22, 30, 0.02, 3, 16, 18)
    cycle("run", 20, 36, 70, 0.045, 10, 35, 60)
    cycle("sprint", 16, 46, 95, 0.06, 18, 55, 85)

    crouch_h = (0, -0.04, -0.33)
    def crouch_legs(fr=(0.13, 0.12, 0.09), fl=(-0.13, -0.08, 0.09)):
        return {"ik": {"foot.R": (fr, V(0.1, 1, 0)), "foot.L": (fl, V(-0.1, 1, 0))},
                "dirs": {"foot.R": V(0, 0.9, -0.25), "foot.L": V(0, 0.9, -0.25)}, "hips": crouch_h}
    anim("crouch_idle", [(f, merge(crouch_legs(), torso(lean=18 + b * 2, head_pitch=-16), arms_relaxed(10, 10, 40)))
                         for f, b in ((0, 0), (30, 1), (60, 0))])
    ck = []
    for i in range(9):
        ph = 2 * math.pi * i / 8
        o = 0.16 * math.sin(ph)
        lift_r = 0.05 * max(0, math.cos(ph))
        lift_l = 0.05 * max(0, -math.cos(ph))
        ck.append((round(32 * i / 8), merge(crouch_legs((0.13, 0.04 + o, 0.09 + lift_r), (-0.13, 0.04 - o, 0.09 + lift_l)),
                                            torso(lean=20, twist=4 * math.sin(ph), head_pitch=-18),
                                            arms_relaxed(12, 12, 45))))
    anim("crouch_walk", ck)

    anim("jump", [(0, merge({"dirs": legs_fk(10, 40, -15, 30)}, torso(lean=6), arms_relaxed(-25, -25, 40, 0.4))),
                  (10, merge({"dirs": legs_fk(25, 70, -5, 30)}, torso(lean=4), arms_relaxed(-35, -35, 50, 0.5)))], loop=False)
    anim("fall", [(0, merge({"dirs": legs_fk(15, 40, -10, 25)}, torso(lean=0), arms_relaxed(-20, -25, 30, 0.7))),
                  (10, merge({"dirs": legs_fk(10, 35, -5, 30)}, torso(lean=2), arms_relaxed(-28, -18, 35, 0.75))),
                  (20, merge({"dirs": legs_fk(15, 40, -10, 25)}, torso(lean=0), arms_relaxed(-20, -25, 30, 0.7)))])

    # skydive: body flat, facing down, arms spread
    def dive(w):
        spread = 0.5 + 0.05 * w
        return merge({"dirs": {"hips": V(0, 1, 0.05), "spine": V(0, 1, 0.12), "chest": V(0, 1, 0.12),
                               "neck": V(0, 0.7, 0.7), "head": V(0, 0.75, 0.66),
                               "upper_arm.R": V(0.85, 0.35, 0.1 + 0.05 * w), "forearm.R": V(0.55, 0.75, 0.3),
                               "hand.R": V(0.4, 0.9, 0.1),
                               "upper_arm.L": V(-0.85, 0.35, 0.1 - 0.05 * w), "forearm.L": V(-0.55, 0.75, 0.3),
                               "hand.L": V(-0.4, 0.9, 0.1),
                               "thigh.R": V(spread * 0.4, -1, 0.15), "shin.R": V(0.1, -0.8, 0.6), "foot.R": V(0, -0.3, 1),
                               "thigh.L": V(-spread * 0.4, -1, 0.15), "shin.L": V(-0.1, -0.8, 0.6), "foot.L": V(0, -0.3, 1)},
                      "hips": (0, 0, 0)})
    anim("skydive", [(0, dive(0)), (15, dive(1)), (30, dive(0))])
    # glide: hanging from glider handles above the head
    def glide(w):
        return merge({"dirs": legs_fk(-8 + w * 4, 20, -16 - w * 4, 25, 30, 30)}, torso(lean=-4, head_pitch=6),
                     {"ik": {"hand.R": ((0.32, 0.12, 2.12 + 0.01 * w), V(1, 0, 0)),
                             "hand.L": ((-0.32, 0.12, 2.12 - 0.01 * w), V(-1, 0, 0))},
                      "dirs": {"hand.R": V(0, 0.2, 1), "hand.L": V(0, 0.2, 1)}})
    anim("glide", [(0, glide(0)), (20, glide(1)), (40, glide(0))])

    anim("death", [(0, merge(stand(), torso(lean=0), arms_relaxed(0, 0))),
                   (10, merge({"dirs": legs_fk(30, 90, 20, 100), "hips": (0, 0.05, -0.35)}, torso(lean=25, side=10),
                              arms_relaxed(10, 30, 40, 0.4))),
                   (24, merge({"dirs": {**legs_fk(80, 60, 70, 40), "hips": V(0, -1, 0.15), "spine": V(0, -1, 0.05),
                                        "chest": V(0.1, -1, 0.0), "neck": V(0.2, -1, 0.1), "head": V(0.3, -1, 0.2)},
                               "hips": (0, 0.1, -0.78)},
                              arms_relaxed(170, 120, 10, 0.6)))], loop=False)

    # --- weapon holds (played on the upper-body subpart) ------------------
    anim("hold_rifle", [(0, merge(stand(), hold("rifle", 0))), (30, merge(stand(), hold("rifle", 1))),
                        (60, merge(stand(), hold("rifle", 0)))])
    anim("hold_pistol", [(0, merge(stand(), hold("pistol", 0))), (30, merge(stand(), hold("pistol", 1))),
                         (60, merge(stand(), hold("pistol", 0)))])
    anim("hold_pickaxe", [(0, merge(stand(), hold("pickaxe", 0))), (30, merge(stand(), hold("pickaxe", 1))),
                          (60, merge(stand(), hold("pickaxe", 0)))])
    anim("fire_rifle", [(0, merge(stand(), hold("rifle", 0, 1.0))), (4, merge(stand(), hold("rifle", 0, 0.0)))], loop=False)

    def reload_pose(t):
        p = merge(stand(), hold("rifle", 0, 0, lean=8))
        # left hand travels to the magazine and back
        mag = Vector((0.02, 0.28, 1.08))
        base = Vector(RIFLE_L[0])
        target = base.lerp(mag, t)
        p["ik"]["hand.L"] = (target, V(-0.7, -0.3, -0.6))
        p["dirs"]["hand.L"] = V(0.2, 0.6, -0.7 * t + 0.3 * (1 - t))
        return p
    anim("reload_rifle", [(0, reload_pose(0)), (8, reload_pose(1)), (18, reload_pose(1)), (24, reload_pose(0.4)),
                          (32, reload_pose(1)), (40, reload_pose(0))], loop=False)

    def reload_pistol_pose(t):
        p = merge(stand(), hold("pistol", 0))
        p["ik"]["hand.R"] = (Vector(PISTOL_R[0]).lerp(Vector((0.12, 0.30, 1.22)), t), PISTOL_R[1])
        p["ik"]["hand.L"] = (Vector(PISTOL_L[0]).lerp(Vector((0.0, 0.26, 1.08)), t), PISTOL_L[1])
        return p
    anim("reload_pistol", [(0, reload_pistol_pose(0)), (8, reload_pistol_pose(1)), (20, reload_pistol_pose(1)),
                           (30, reload_pistol_pose(0))], loop=False)

    def swing_pose(phase):
        # phase 0 = wind-up high behind shoulder, 1 = follow-through low in front
        base = merge(stand(), torso(lean=4 + 14 * phase, twist=-20 + 30 * phase))
        a = math.radians(-60 + 170 * phase)
        r = Vector((0.24, 0.08 + 0.42 * math.sin(a) * 0.9, 1.30 + 0.38 * math.cos(a)))
        base["ik"]["hand.R"] = (r, V(0.6, -0.5, -0.3))
        base["dirs"]["hand.R"] = V(0, math.cos(a) * 0.9 + 0.1, -math.sin(a))
        base["dirs"].update({k: v for k, v in arms_relaxed(0, -10, 30).items() if k.endswith("L")})
        return base
    anim("pickaxe_swing", [(0, merge(stand(), hold("pickaxe"))), (5, swing_pose(0)), (9, swing_pose(0.85)),
                           (12, swing_pose(1.0)), (18, merge(stand(), hold("pickaxe")))], loop=False)

    def use_item_pose(b):
        p = merge(stand(), torso(lean=8, head_pitch=-20))
        p["ik"] = {"hand.R": ((0.06, 0.26, 1.18 + 0.03 * b), V(1, -0.3, -0.4)),
                   "hand.L": ((-0.06, 0.26, 1.16 - 0.03 * b), V(-1, -0.3, -0.4))}
        p["dirs"].update({"hand.R": V(-0.6, 0.6, 0.2), "hand.L": V(0.6, 0.6, 0.2)})
        return p
    anim("use_item", [(0, use_item_pose(0)), (10, use_item_pose(1)), (20, use_item_pose(0))])

    # --- emotes --------------------------------------------------------------
    def wave(w):
        p = merge(stand(), torso(lean=0, side=-3, head_yaw=-5), arms_relaxed(0, -4, 15))
        p["ik"]["hand.R"] = ((0.42, 0.12, 1.70), V(1, -0.5, -0.5))
        p["dirs"]["hand.R"] = V(0.45 * w, 0.1, 1)
        return p
    anim("emote_wave", [(0, wave(-1)), (8, wave(1)), (16, wave(-1)), (24, wave(1)), (32, wave(-1)), (40, wave(-1))])

    gk = []
    for i in range(9):
        ph = 2 * math.pi * i / 8
        s = math.sin(ph)
        c = math.cos(2 * ph)
        gk.append((round(32 * i / 8), merge(
            {"dirs": legs_fk(8 * s, 18 + 10 * c, -8 * s, 18 - 10 * c, 0, 0, 0.09), "hips": (0.04 * s, 0, -0.04 - 0.03 * c)},
            torso(lean=6, side=8 * s, twist=15 * s, head_pitch=6 * c),
            {"ik": {"hand.R": ((0.3 + 0.1 * s, 0.25, 1.35 + 0.15 * c), V(1, -1, -0.3)),
                    "hand.L": ((-0.3 + 0.1 * s, 0.25, 1.35 - 0.15 * c), V(-1, -1, -0.3))}})))
    anim("emote_groove", gk)

    def flex(t):
        p = merge({"dirs": legs_fk(0, 8, 0, 8, 0, 0, 0.12), "hips": (0, 0, -0.04 * t)},
                  torso(lean=-6 * t, head_pitch=10 * t))
        p["ik"] = {"hand.R": ((0.30, 0.02, 1.40 + 0.25 * t), V(1, 0, -0.8 + t)),
                   "hand.L": ((-0.30, 0.02, 1.40 + 0.25 * t), V(-1, 0, -0.8 + t))}
        p["dirs"].update({"hand.R": V(-0.3, 0.0, 1), "hand.L": V(0.3, 0.0, 1)})
        return p
    anim("emote_flex", [(0, merge(stand(), torso(), arms_relaxed())), (12, flex(1)), (40, flex(0.85)), (52, flex(1)),
                        (60, merge(stand(), torso(), arms_relaxed()))])

    def robot(i):
        s = 1 if i % 2 == 0 else -1
        p = merge({"dirs": legs_fk(6 * s, 10, -6 * s, 10)}, torso(lean=0, twist=20 * s, head_yaw=-25 * s))
        p["dirs"].update({"upper_arm.R": V(0.4, 0, -1), "forearm.R": V(0, 1, 0.05 * s), "hand.R": V(0, 1, 0),
                          "upper_arm.L": V(-0.4, 0, -1), "forearm.L": V(0, 1, -0.05 * s), "hand.L": V(0, 1, 0)})
        if s < 0:
            p["dirs"].update({"forearm.R": V(0, 0.2, 1), "hand.R": V(0, 0.2, 1)})
        else:
            p["dirs"].update({"forearm.L": V(0, 0.2, 1), "hand.L": V(0, 0.2, 1)})
        return p
    anim("emote_robot", [(0, robot(0)), (9, robot(0)), (10, robot(1)), (19, robot(1)), (20, robot(0)),
                         (29, robot(0)), (30, robot(1)), (39, robot(1)), (40, robot(0))])

    bk = []
    for i in range(7):
        ph = 2 * math.pi * i / 6
        down = (1 - math.cos(ph)) / 2
        bk.append((round(24 * i / 6), merge(
            {"dirs": legs_fk(10, 20 + 40 * down, -10, 20 + 40 * down, 0, 0, 0.12), "hips": (0, -0.03 * down, -0.12 * down)},
            torso(lean=10 + 10 * down, head_pitch=-12 * down),
            {"ik": {"hand.R": ((0.32, 0.25, 1.15 + 0.25 * (1 - down)), V(1, -0.5, -0.3)),
                    "hand.L": ((-0.32, 0.25, 1.15 + 0.25 * (1 - down)), V(-1, -0.5, -0.3))},
             "dirs": {"hand.R": V(0, 0.4, 1), "hand.L": V(0, 0.4, 1)}})))
    anim("emote_bounce", bk)
    return A


HOLD_SOCKET_POSES = {"rifle": "hold_rifle", "pistol": "hold_pistol", "pickaxe": "hold_pickaxe"}


# --------------------------------------------------------------------------
# baking animations
# --------------------------------------------------------------------------
def bake_animations(arm) -> dict:
    """Create one action per animation. Returns info incl. socket frames per hold pose."""
    rest = rest_matrices(arm)
    for b in arm.data.bones:
        if b.name not in BONES and b.parent:
            bpy_parent_cache[b.name] = b.parent.name
    if arm.animation_data is None:
        arm.animation_data_create()
    info = {}
    for name, spec in animations().items():
        action = bpy.data.actions.new(name)
        action.use_fake_user = True
        arm.animation_data.action = action
        prev: dict[str, Quaternion] = {}
        for frame, pose in spec["frames"]:
            rots, hips_loc, _ = solve(rest, pose)
            for pb in arm.pose.bones:
                q = rots.get(pb.name, Quaternion())
                if pb.name in prev and prev[pb.name].dot(q) < 0:
                    q = -q
                prev[pb.name] = q
                pb.rotation_quaternion = q
                pb.keyframe_insert("rotation_quaternion", frame=frame)
                if pb.name == "hips":
                    pb.location = hips_loc
                    pb.keyframe_insert("location", frame=frame)
        info[name] = {"frames": spec["frames"][-1][0] + 1, "loop": spec["loop"]}
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_quaternion = Quaternion()
        pb.location = Vector()
    return info


def posed_world(arm, pose_name: str) -> dict[str, Matrix]:
    rest = rest_matrices(arm)
    for b in arm.data.bones:
        if b.name not in BONES and b.parent:
            bpy_parent_cache[b.name] = b.parent.name
    _, _, posed = solve(rest, animations()[pose_name]["frames"][0][1])
    return posed


def add_sockets(arm) -> dict:
    """Weapon socket = right palm in the rifle hold, level with the model axes.

    Returns, for every hold pose, the socket's world transform so the game can
    level non-rifle items (pistols, pickaxes) inside the hand."""
    global ORDER
    rest = rest_matrices(arm)
    aim = posed_world(arm, "hold_rifle")
    hand_aim = aim["hand.R"]
    palm = hand_aim @ Vector((0, 0.075, 0))
    desired = Matrix.Translation(palm)
    socket_rest = rest["hand.R"] @ hand_aim.inverted() @ desired
    add_socket_bone(arm, "socket_weapon", "hand.R", socket_rest)
    add_socket_bone(arm, "socket_back", "chest", Matrix.Translation(Vector(SOCKET_BACK)))
    ORDER = list(BONES) + ["socket_weapon", "socket_back"]
    bpy_parent_cache.update({"socket_weapon": "hand.R", "socket_back": "chest"})
    frames = {}
    for kind, pose_name in HOLD_SOCKET_POSES.items():
        posed = posed_world(arm, pose_name)
        m = posed["socket_weapon"]
        q = m.to_quaternion()
        frames[kind] = {"pos": [round(c, 5) for c in m.translation],
                        "quat": [round(c, 6) for c in (q.w, q.x, q.y, q.z)]}
    return frames


# --------------------------------------------------------------------------
# skinning
# --------------------------------------------------------------------------
def _seg_dist(p: Vector, a: Vector, b: Vector) -> float:
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
    return (p - (a + ab * t)).length


def weight_auto(obj, bones: list[str] | None = None, falloff: float = 5.0, top: int = 2) -> None:
    """Distance-based skin weights to the nearest bone segments (blended over ``top`` bones)."""
    bones = bones or DEFORM
    segs = [(b, Vector(BONES[b][0]), Vector(BONES[b][1])) for b in bones]
    groups = {b: obj.vertex_groups.get(b) or obj.vertex_groups.new(name=b) for b in bones}
    for v in obj.data.vertices:
        d = sorted(((_seg_dist(v.co, a, c), b) for b, a, c in segs))[:top]
        ws = [1.0 / (dist ** falloff + 1e-7) for dist, _ in d]
        total = sum(ws)
        for (dist, b), w in zip(d, ws):
            if w / total > 0.02:
                groups[b].add([v.index], w / total, "REPLACE")


def weight_rigid(obj, bone: str) -> None:
    g = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
    g.add([v.index for v in obj.data.vertices], 1.0, "REPLACE")


def bind(mesh_obj, arm) -> None:
    mesh_obj.parent = arm
    mod = mesh_obj.modifiers.new("rig", "ARMATURE")
    mod.object = arm
