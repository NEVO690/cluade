"""Keyframed actions for Bonklet (24 fps).

Pose conventions (see create_character.py):
  spine / head / root / hips : +rx leans back, -rx leans forward, ry twists, rz tilts sideways
  arms / legs / hands        : +rx swings forward; arm.L -rz raises it sideways, arm.R +rz
  feet                       : +rx lifts the toes
  hips location (0, y, 0)    : y moves the body up/down (bone Y axis = world up)

Every key frame poses *every* bone (unlisted bones are at rest) so switching
animations in the engine never leaves a limb stuck in the previous pose.
"""

import math

import bpy

from create_character import BONES

FPS = 24

# name -> (frame_count, loops, native ground speed in m/s at play rate 1.0, keys)
# keys: list of (frame, {bone: {"r": (x, y, z) degrees, "l": (x, y, z)}})


def mirror_arms(lx, lz, rx=None, rz=None):
    """Arm pose helper: (rx, rz) for the left arm, mirrored for the right."""
    return {"arm.L": {"r": (lx, 0, lz)}, "arm.R": {"r": (lx if rx is None else rx, 0, -lz if rz is None else rz)}}


def merge(*dicts):
    out = {}
    for d in dicts:
        for k, v in d.items():
            out.setdefault(k, {}).update(v)
    return out


def walk_keys():
    a, b = 30, -30
    return [
        (1, merge({"leg.L": {"r": (a, 0, 0)}, "leg.R": {"r": (b, 0, 0)}, "foot.L": {"r": (-10, 0, 0)},
                   "foot.R": {"r": (12, 0, 0)}, "spine": {"r": (-3, 0, 3)}, "head": {"r": (2, 0, -2)}},
                  mirror_arms(-25, 4, rx=25)) ),
        (4, merge({"hips": {"l": (0, 0.04, 0)}, "leg.L": {"r": (5, 0, 0)}, "leg.R": {"r": (-5, 0, 0)},
                   "spine": {"r": (-3, 0, 0)}}, mirror_arms(0, 4, rx=0))),
        (7, merge({"leg.L": {"r": (b, 0, 0)}, "leg.R": {"r": (a, 0, 0)}, "foot.L": {"r": (12, 0, 0)},
                   "foot.R": {"r": (-10, 0, 0)}, "spine": {"r": (-3, 0, -3)}, "head": {"r": (2, 0, 2)}},
                  mirror_arms(25, 4, rx=-25))),
        (10, merge({"hips": {"l": (0, 0.04, 0)}, "leg.L": {"r": (-5, 0, 0)}, "leg.R": {"r": (5, 0, 0)},
                    "spine": {"r": (-3, 0, 0)}}, mirror_arms(0, 4, rx=0))),
        (13, None),  # copy of frame 1 (seamless loop)
    ]


def run_keys():
    lean = {"spine": {"r": (-14, 0, 0)}, "head": {"r": (9, 0, 0)}}
    return [
        (1, merge(lean, {"leg.L": {"r": (55, 0, 0)}, "leg.R": {"r": (-45, 0, 0)}, "foot.L": {"r": (-15, 0, 0)},
                         "foot.R": {"r": (25, 0, 0)}, "antenna": {"r": (22, 0, 0)}, "spine": {"r": (-14, 6, 0)}},
                  mirror_arms(-60, 10, rx=60))),
        (4, merge(lean, {"hips": {"l": (0, 0.07, 0)}, "leg.L": {"r": (5, 0, 0)}, "leg.R": {"r": (0, 0, 0)},
                         "antenna": {"r": (8, 0, 0)}}, mirror_arms(0, 10, rx=0))),
        (6, merge(lean, {"leg.L": {"r": (-45, 0, 0)}, "leg.R": {"r": (55, 0, 0)}, "foot.L": {"r": (25, 0, 0)},
                         "foot.R": {"r": (-15, 0, 0)}, "antenna": {"r": (22, 0, 0)}, "spine": {"r": (-14, -6, 0)}},
                  mirror_arms(60, 10, rx=-60))),
        (9, merge(lean, {"hips": {"l": (0, 0.07, 0)}, "leg.L": {"r": (0, 0, 0)}, "leg.R": {"r": (5, 0, 0)},
                         "antenna": {"r": (8, 0, 0)}}, mirror_arms(0, 10, rx=0))),
        (11, None),
    ]


def idle_keys():
    rest = merge({"antenna": {"r": (5, 0, 0)}}, mirror_arms(0, 6))
    breathe = merge({"hips": {"l": (0, -0.015, 0)}, "spine": {"r": (-3, 0, 0)}, "head": {"r": (3, 0, 0)},
                     "antenna": {"r": (-9, 0, 0)}}, mirror_arms(5, 9, rx=-5))
    return [
        (1, rest),
        (13, merge(breathe, {"head": {"r": (3, 8, 0)}})),
        (25, merge(rest, {"head": {"r": (0, 12, 0)}, "antenna": {"r": (8, 0, 6)}})),
        (37, merge(breathe, {"head": {"r": (3, -10, 0)}})),
        (49, None),
    ]


def jump_keys():
    return [
        (1, merge({"hips": {"l": (0, -0.07, 0)}, "leg.L": {"r": (22, 0, 0)}, "leg.R": {"r": (22, 0, 0)},
                   "foot.L": {"r": (-18, 0, 0)}, "foot.R": {"r": (-18, 0, 0)}, "spine": {"r": (-12, 0, 0)}},
                  mirror_arms(-30, 8, rx=-30))),
        (4, merge({"hips": {"l": (0, 0.04, 0)}, "leg.L": {"r": (-12, 0, 0)}, "leg.R": {"r": (-8, 0, 0)},
                   "foot.L": {"r": (-25, 0, 0)}, "foot.R": {"r": (-25, 0, 0)}, "spine": {"r": (6, 0, 0)},
                   "antenna": {"r": (28, 0, 0)}}, mirror_arms(10, -115))),
        (9, merge({"leg.L": {"r": (40, 0, 0)}, "leg.R": {"r": (15, 0, 0)}, "foot.L": {"r": (20, 0, 0)},
                   "foot.R": {"r": (10, 0, 0)}, "spine": {"r": (-4, 0, 0)}, "head": {"r": (-6, 0, 0)},
                   "antenna": {"r": (-12, 0, 0)}}, mirror_arms(15, -135))),
    ]


def fall_keys():
    return [
        (1, merge({"leg.L": {"r": (28, 0, 0)}, "leg.R": {"r": (-15, 0, 0)}, "spine": {"r": (8, 0, 4)},
                   "head": {"r": (-6, 0, 0)}, "antenna": {"r": (32, 0, 8)}},
                  {"arm.L": {"r": (20, 0, -125)}, "arm.R": {"r": (-25, 0, 95)}})),
        (7, merge({"leg.L": {"r": (-15, 0, 0)}, "leg.R": {"r": (28, 0, 0)}, "spine": {"r": (8, 0, -4)},
                   "head": {"r": (-6, 0, 0)}, "antenna": {"r": (-22, 0, -8)}},
                  {"arm.L": {"r": (-25, 0, -95)}, "arm.R": {"r": (20, 0, 125)}})),
        (13, None),
    ]


def land_keys():
    return [
        (1, merge({"hips": {"l": (0, -0.11, 0)}, "leg.L": {"r": (32, 0, 0)}, "leg.R": {"r": (32, 0, 0)},
                   "foot.L": {"r": (-22, 0, 0)}, "foot.R": {"r": (-22, 0, 0)}, "spine": {"r": (-14, 0, 0)},
                   "head": {"r": (8, 0, 0)}, "antenna": {"r": (-30, 0, 0)}}, mirror_arms(10, -45))),
        (4, merge({"hips": {"l": (0, -0.05, 0)}, "leg.L": {"r": (15, 0, 0)}, "leg.R": {"r": (15, 0, 0)},
                   "spine": {"r": (-6, 0, 0)}, "antenna": {"r": (18, 0, 0)}}, mirror_arms(0, -20))),
        (7, merge({"antenna": {"r": (5, 0, 0)}}, mirror_arms(0, 6))),
    ]


def victory_keys():
    return [
        (1, merge({"hips": {"l": (0, 0, 0)}, "antenna": {"r": (0, 0, 0)}}, mirror_arms(0, -150))),
        (7, merge({"hips": {"l": (0, 0.14, 0)}, "spine": {"r": (4, 20, 0)}, "head": {"r": (-10, 10, 0)},
                   "leg.L": {"r": (20, 0, 0)}, "leg.R": {"r": (12, 0, 0)}, "antenna": {"r": (28, 0, 0)}},
                  {"arm.L": {"r": (30, 0, -130)}, "arm.R": {"r": (-30, 0, 130)}})),
        (13, merge({"hips": {"l": (0, 0, 0)}, "head": {"r": (0, 0, 0)}}, mirror_arms(0, -158))),
        (19, merge({"hips": {"l": (0, 0.14, 0)}, "spine": {"r": (4, -20, 0)}, "head": {"r": (-10, -10, 0)},
                    "leg.L": {"r": (12, 0, 0)}, "leg.R": {"r": (20, 0, 0)}, "antenna": {"r": (-20, 0, 0)}},
                   {"arm.L": {"r": (-30, 0, -130)}, "arm.R": {"r": (30, 0, 130)}})),
        (25, None),
    ]


def elimination_keys():
    return [
        (1, merge({"antenna": {"r": (5, 0, 0)}}, mirror_arms(0, 6))),
        (6, merge({"spine": {"r": (0, 0, 12)}, "head": {"r": (0, 0, 16)}, "antenna": {"r": (30, 0, 20)}},
                  mirror_arms(0, -40))),
        (12, merge({"spine": {"r": (0, 0, -12)}, "head": {"r": (0, 0, -16)}, "antenna": {"r": (-25, 0, -20)}},
                   mirror_arms(0, -40))),
        (18, merge({"root": {"r": (68, 0, 0)}, "head": {"r": (-20, 0, 0)}, "leg.L": {"r": (45, 0, 0)},
                    "leg.R": {"r": (30, 0, 0)}, "antenna": {"r": (40, 0, 0)}}, mirror_arms(10, -80))),
        (25, merge({"root": {"r": (84, 0, 0)}, "head": {"r": (-12, 0, 10)}, "leg.L": {"r": (55, 0, 0)},
                    "leg.R": {"r": (38, 0, 0)}, "antenna": {"r": (55, 0, 0)}}, mirror_arms(15, -95))),
    ]


ANIMATIONS = {
    "Idle": (idle_keys, True, 0.0),
    "Walk": (walk_keys, True, 1.8),
    "Run": (run_keys, True, 3.4),
    "Jump": (jump_keys, False, 0.0),
    "Fall": (fall_keys, True, 0.0),
    "Land": (land_keys, False, 0.0),
    "Victory": (victory_keys, True, 0.0),
    "Elimination": (elimination_keys, False, 0.0),
}


def _apply_pose(rig, pose):
    for name in BONES:
        pb = rig.pose.bones[name]
        spec = (pose or {}).get(name, {})
        r = spec.get("r", (0, 0, 0))
        pb.rotation_euler = tuple(math.radians(v) for v in r)
        pb.location = spec.get("l", (0, 0, 0))
        pb.scale = (1, 1, 1)


def build_actions(rig):
    """Create one Blender action per animation; returns metadata for the game."""
    rig.animation_data_create()
    meta = {}
    for name, (key_fn, loops, native_speed) in ANIMATIONS.items():
        act = bpy.data.actions.new(name)
        act.use_fake_user = True
        rig.animation_data.action = act
        keys = key_fn()
        first_pose = keys[0][1]
        for frame, pose in keys:
            _apply_pose(rig, first_pose if pose is None else pose)
            for bname in BONES:
                pb = rig.pose.bones[bname]
                pb.keyframe_insert("rotation_euler", frame=frame)
                pb.keyframe_insert("location", frame=frame)
        last = keys[-1][0]
        meta[name] = {
            "frames": last,
            "duration": (last - 1) / FPS,
            "loop": loops,
            "native_speed": native_speed,
        }
    rig.animation_data.action = None
    _apply_pose(rig, None)
    return meta
