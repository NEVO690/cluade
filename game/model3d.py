"""Low-poly 3D character models.

Each character is a real mesh (head, hair, torso, backpack, arms, legs,
shoes, accessories) attached to a small skeleton.  Poses (run, jump, slide,
fall, idle, wave, cheer) rotate the bones; vertices are transformed with
forward kinematics, back-face culled, depth sorted, flat shaded with a
directional light and projected through either the game camera or a menu
"turntable" camera.

Character model: x = right, y = up, z = forward (the direction of running),
origin between the feet.  Units are metres.
"""
import math

import pygame

from .utils import shade

LIGHT = (-0.38, 0.82, -0.43)
_ln = math.sqrt(sum(c * c for c in LIGHT))
LIGHT = tuple(c / _ln for c in LIGHT)
AMBIENT = 0.56
DIFFUSE = 0.48
HIP = 0.89


# ---------------------------------------------------------------------------
# Small 3x3 matrix helpers (tuples of rows)
# ---------------------------------------------------------------------------
def rot(pitch=0.0, roll=0.0, yaw=0.0):
    """Ry(yaw) * Rz(roll) * Rx(pitch)."""
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    cy, sy = math.cos(yaw), math.sin(yaw)
    # Rz * Rx
    a = ((cr, -sr * cp, sr * sp),
         (sr, cr * cp, -cr * sp),
         (0.0, sp, cp))
    # Ry * a
    return ((cy * a[0][0] + sy * a[2][0], cy * a[0][1] + sy * a[2][1], cy * a[0][2] + sy * a[2][2]),
            a[1],
            (-sy * a[0][0] + cy * a[2][0], -sy * a[0][1] + cy * a[2][1], -sy * a[0][2] + cy * a[2][2]))


def mmul(A, B):
    return tuple(tuple(A[i][0] * B[0][j] + A[i][1] * B[1][j] + A[i][2] * B[2][j] for j in range(3)) for i in range(3))


def mvec(A, v):
    return (A[0][0] * v[0] + A[0][1] * v[1] + A[0][2] * v[2],
            A[1][0] * v[0] + A[1][1] * v[1] + A[1][2] * v[2],
            A[2][0] * v[0] + A[2][1] * v[1] + A[2][2] * v[2])


IDENT = rot()


# ---------------------------------------------------------------------------
# Mesh building
# ---------------------------------------------------------------------------
class Part:
    """Vertices + faces attached to one bone."""
    __slots__ = ("bone", "verts", "faces")

    def __init__(self, bone):
        self.bone = bone
        self.verts = []
        self.faces = []   # (vertex indices, local normal, color)

    def _add_face(self, idx, color, ref):
        pts = [self.verts[i] for i in idx]
        nx = ny = nz = 0.0
        n = len(pts)
        for i in range(n):
            x1, y1, z1 = pts[i]
            x2, y2, z2 = pts[(i + 1) % n]
            nx += (y1 - y2) * (z1 + z2)
            ny += (z1 - z2) * (x1 + x2)
            nz += (x1 - x2) * (y1 + y2)
        ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        nx, ny, nz = nx / ln, ny / ln, nz / ln
        cx = sum(p[0] for p in pts) / n
        cy = sum(p[1] for p in pts) / n
        cz = sum(p[2] for p in pts) / n
        if nx * (cx - ref[0]) + ny * (cy - ref[1]) + nz * (cz - ref[2]) < 0:
            nx, ny, nz = -nx, -ny, -nz
            idx = tuple(reversed(idx))
        self.faces.append((tuple(idx), (nx, ny, nz), color))

    def box(self, x0, x1, y0, y1, z0, z1, color, colors=None):
        """Axis-aligned box. ``colors`` may override per side: dict of top/bottom/front/back/side."""
        b = len(self.verts)
        for x in (x0, x1):
            for y in (y0, y1):
                for z in (z0, z1):
                    self.verts.append((x, y, z))
        ref = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
        c = colors or {}
        quads = {
            "left": (0, 1, 3, 2), "right": (4, 6, 7, 5), "bottom": (0, 4, 5, 1),
            "top": (2, 3, 7, 6), "back": (0, 2, 6, 4), "front": (1, 5, 7, 3),
        }
        for name, q in quads.items():
            col = c.get(name, c.get("side", color) if name in ("left", "right") else color)
            self._add_face(tuple(b + i for i in q), col, ref)

    def hexa(self, bottom, top, color):
        """Tapered box from 4 bottom + 4 top corners (each ((x,y,z) * 4) in order around)."""
        b = len(self.verts)
        self.verts.extend(bottom)
        self.verts.extend(top)
        ref = tuple(sum(p[i] for p in bottom + top) / 8 for i in range(3))
        for i in range(4):
            j = (i + 1) % 4
            self._add_face((b + i, b + j, b + 4 + j, b + 4 + i), color, ref)
        self._add_face((b, b + 1, b + 2, b + 3), color, ref)
        self._add_face((b + 4, b + 5, b + 6, b + 7), color, ref)

    def prism(self, length, r0, r1, color, n=6, depth=1.0, y0=0.0, cap_color=None, x=0.0, z=0.0):
        """Tapered n-sided prism hanging down from (x, y0, z) along -y."""
        b = len(self.verts)
        for ring, (y, r) in enumerate(((y0, r0), (y0 - length, r1))):
            for i in range(n):
                a = (i + 0.5) * math.tau / n
                self.verts.append((x + math.cos(a) * r, y, z + math.sin(a) * r * depth))
        ref = (x, y0 - length / 2, z)
        for i in range(n):
            j = (i + 1) % n
            self._add_face((b + i, b + j, b + n + j, b + n + i), color, ref)
        self._add_face(tuple(b + i for i in range(n)), cap_color or color, ref)
        self._add_face(tuple(b + n + i for i in range(n)), cap_color or color, ref)

    def ellipsoid(self, cx, cy, cz, rx, ry, rz, color, lat=5, lon=8, lat_max=math.pi, colors_fn=None):
        """Low-poly ellipsoid; ``lat_max`` < pi makes a cap (used for hair)."""
        b = len(self.verts)
        rings = []
        for i in range(lat + 1):
            th = lat_max * i / lat
            ring = []
            for j in range(lon):
                ph = math.tau * (j + 0.5) / lon
                self.verts.append((cx + rx * math.sin(th) * math.cos(ph), cy + ry * math.cos(th),
                                   cz + rz * math.sin(th) * math.sin(ph)))
                ring.append(len(self.verts) - 1)
            rings.append(ring)
        ref = (cx, cy, cz)
        for i in range(lat):
            for j in range(lon):
                k = (j + 1) % lon
                if i == 0:
                    idx = (rings[0][j], rings[1][j], rings[1][k])
                else:
                    idx = (rings[i][j], rings[i + 1][j], rings[i + 1][k], rings[i][k])
                col = colors_fn(i, j) if colors_fn else color
                self._add_face(idx, col, ref)
        if lat_max < math.pi - 1e-3:
            self._add_face(tuple(rings[-1]), color, (cx, cy + ry, cz))
        return b

    def pyramid(self, base_c, half, height, color, tilt=(0.0, 0.0)):
        """Square pyramid (hair spikes)."""
        cx, cy, cz = base_c
        b = len(self.verts)
        for dx, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            self.verts.append((cx + dx * half, cy, cz + dz * half))
        self.verts.append((cx + tilt[0], cy + height, cz + tilt[1]))
        ref = (cx, cy + height * 0.3, cz)
        for i in range(4):
            self._add_face((b + i, b + (i + 1) % 4, b + 4), color, ref)


def _col(c):
    return tuple(int(v) for v in c)


def build_model(look):
    """Build the mesh parts for a character look (cached by the caller)."""
    sk, hair, shirt = _col(look["skin"]), _col(look["hair"]), _col(look["shirt"])
    pants, shoes, acc = _col(look["pants"]), _col(look["shoes"]), _col(look["accent"])
    bw = float(look.get("build", 1.0))
    style = look.get("hair_style", "short")
    accessory = look.get("accessory", "none")
    parts = []

    # pelvis / shorts / belt
    p = Part("pelvis")
    p.box(-0.17 * bw, 0.17 * bw, -0.12, 0.07, -0.11, 0.11, pants)
    p.box(-0.175 * bw, 0.175 * bw, 0.04, 0.09, -0.115, 0.115, shade(pants, 0.55))
    parts.append(p)

    # torso: tapered, with chest stripe, collar and backpack
    t = Part("spine")
    w0, w1, d0, d1 = 0.165 * bw, 0.24 * bw, 0.115, 0.13
    t.hexa(((-w0, 0.05, -d0), (w0, 0.05, -d0), (w0, 0.05, d0), (-w0, 0.05, d0)),
           ((-w1, 0.5, -d1), (w1, 0.5, -d1), (w1, 0.5, d1), (-w1, 0.5, d1)), shirt)
    t.hexa(((-0.207 * bw, 0.29, -0.126), (0.207 * bw, 0.29, -0.126), (0.207 * bw, 0.29, 0.126), (-0.207 * bw, 0.29, 0.126)),
           ((-0.215 * bw, 0.34, -0.128), (0.215 * bw, 0.34, -0.128), (0.215 * bw, 0.34, 0.128), (-0.215 * bw, 0.34, 0.128)), acc)
    t.prism(0.09, 0.07, 0.065, sk, n=6, y0=0.6)                      # neck
    t.box(-0.15 * bw, 0.15 * bw, 0.13, 0.43, -0.25, -0.12, shade(acc, 0.85),
          {"top": shade(acc, 1.05)})                                  # backpack
    t.box(-0.11 * bw, 0.11 * bw, 0.2, 0.36, -0.265, -0.245, shade(acc, 0.6))  # pocket
    for sx in (-0.11, 0.11):                                         # straps
        t.box(sx * bw - 0.025, sx * bw + 0.025, 0.2, 0.5, 0.115, 0.14, shade(acc, 0.7))
    parts.append(t)

    # head
    h = Part("head")
    head_c = (0.0, 0.16, 0.01)
    if accessory == "pumpkin":
        orange, dark = (240, 125, 20), (40, 20, 10)
        h.ellipsoid(0, 0.16, 0.0, 0.22, 0.19, 0.21, orange, lat=5, lon=10,
                    colors_fn=lambda i, j: orange if j % 2 else shade(orange, 0.85))
        h.prism(0.09, 0.03, 0.025, (70, 120, 40), n=5, y0=0.43)
        for ex in (-0.08, 0.08):
            h.pyramid((ex, 0.19, 0.205), 0.035, 0.05, dark)
        h.box(-0.1, 0.1, 0.07, 0.1, 0.19, 0.215, dark)
    else:
        h.ellipsoid(*head_c, 0.155, 0.17, 0.155, sk, lat=5, lon=8)
        for ex in (-1, 1):
            h.box(ex * 0.165 - 0.02, ex * 0.165 + 0.02, 0.1, 0.19, -0.02, 0.04, shade(sk, 0.92))     # ears
            h.box(ex * 0.058 - 0.03, ex * 0.058 + 0.03, 0.15, 0.2, 0.135, 0.16, (250, 250, 250))  # eye white
            h.box(ex * 0.058 - 0.014, ex * 0.058 + 0.016, 0.155, 0.195, 0.158, 0.168, (30, 30, 40))  # pupil
            h.box(ex * 0.058 - 0.035, ex * 0.058 + 0.035, 0.215, 0.235, 0.13, 0.16, shade(hair, 0.8))  # brow
        h.box(-0.018, 0.018, 0.1, 0.15, 0.15, 0.185, shade(sk, 0.9))   # nose
        h.box(-0.045, 0.045, 0.06, 0.08, 0.135, 0.155, (150, 60, 60))   # mouth
        _hair(h, style, hair, head_c)
    _accessory(h, accessory, acc, head_c)
    parts.append(h)

    # arms
    for side in ("l", "r"):
        a = Part("arm_" + side)
        a.prism(0.3, 0.068, 0.058, shirt, n=6)
        parts.append(a)
        f = Part("fore_" + side)
        f.prism(0.25, 0.054, 0.045, sk, n=6)
        f.box(-0.045, 0.045, -0.33, -0.24, -0.035, 0.05, sk)  # hand
        parts.append(f)
        th = Part("thigh_" + side)
        th.prism(0.43, 0.088, 0.07, pants, n=6, y0=0.02)
        parts.append(th)
        sh = Part("shin_" + side)
        sh.prism(0.4, 0.068, 0.052, shade(pants, 0.92), n=6)
        parts.append(sh)
        ft = Part("foot_" + side)
        ft.box(-0.065, 0.065, -0.055, 0.05, -0.08, 0.17, shoes, {"top": shade(shoes, 1.05)})
        ft.box(-0.068, 0.068, -0.085, -0.05, -0.085, 0.175, shade(shoes, 0.55))   # sole
        ft.box(-0.067, 0.067, -0.02, 0.01, -0.06, 0.12, acc)                       # shoe stripe
        parts.append(ft)
    return parts


def _hair(h, style, hair, c):
    cx, cy, cz = c
    if style == "bald":
        return
    if style == "mohawk":
        h.box(-0.035, 0.035, cy + 0.12, cy + 0.28, -0.14, 0.13, hair)
        return
    # base cap covering the top and back of the head
    h.ellipsoid(cx, cy + 0.005, cz - 0.005, 0.165, 0.18, 0.166, hair, lat=3, lon=8, lat_max=1.35)
    h.box(-0.15, 0.15, cy - 0.12, cy + 0.06, -0.165, -0.06, hair)  # back of the head
    if style == "spiky":
        for x, z, tl in ((0, 0.06, (0, 0.05)), (-0.09, 0.0, (-0.04, 0)), (0.09, 0.0, (0.04, 0)),
                         (-0.05, -0.08, (-0.02, -0.05)), (0.05, -0.08, (0.02, -0.05)), (0, -0.02, (0, 0))):
            h.pyramid((x, cy + 0.12, z), 0.05, 0.12, hair, tilt=tl)
    elif style == "bun":
        h.ellipsoid(cx, cy + 0.2, cz - 0.07, 0.07, 0.065, 0.07, hair, lat=3, lon=6)
    elif style == "long":
        h.box(-0.16, 0.16, cy - 0.38, cy + 0.02, -0.18, -0.08, hair)
        for ex in (-1, 1):
            h.box(ex * 0.16 - 0.03, ex * 0.16 + 0.03, cy - 0.22, cy + 0.08, -0.08, 0.06, hair)


def _accessory(h, kind, acc, c):
    cx, cy, cz = c
    if kind == "cap":
        h.prism(0.09, 0.172, 0.168, acc, n=8, y0=cy + 0.2, cap_color=shade(acc, 1.1))
        h.box(-0.12, 0.12, cy + 0.11, cy + 0.135, 0.1, 0.3, shade(acc, 0.85))
        h.box(-0.02, 0.02, cy + 0.2, cy + 0.215, -0.02, 0.02, shade(acc, 0.6))
    elif kind == "headphones":
        h.box(-0.17, 0.17, cy + 0.17, cy + 0.2, -0.03, 0.03, (40, 40, 50))
        for ex in (-1, 1):
            h.box(ex * 0.17 - 0.02, ex * 0.17 + 0.02, cy + 0.05, cy + 0.19, -0.03, 0.03, (40, 40, 50))
            h.box(ex * 0.18 - 0.04, ex * 0.18 + 0.04, cy - 0.04, cy + 0.08, -0.06, 0.06, acc)
    elif kind == "goggles":
        h.prism(0.04, 0.163, 0.163, (40, 40, 50), n=8, y0=cy + 0.12)
        for ex in (-1, 1):
            h.box(ex * 0.06 - 0.045, ex * 0.06 + 0.045, cy + 0.06, cy + 0.12, 0.14, 0.18, acc)
    elif kind == "bandana":
        h.prism(0.05, 0.168, 0.168, acc, n=8, y0=cy + 0.13)
        h.box(-0.04, 0.04, cy + 0.02, cy + 0.11, -0.2, -0.15, acc)
    elif kind == "visor":
        h.box(-0.14, 0.14, cy + 0.03, cy + 0.08, 0.12, 0.17, acc)


SKELETON = [
    # bone, parent, offset (x scaled by build)
    ("pelvis", None, (0.0, HIP, 0.0)),
    ("spine", "pelvis", (0.0, 0.05, 0.0)),
    ("head", "spine", (0.0, 0.62, 0.0)),
    ("arm_l", "spine", (-0.27, 0.47, 0.0)),
    ("fore_l", "arm_l", (0.0, -0.3, 0.0)),
    ("arm_r", "spine", (0.27, 0.47, 0.0)),
    ("fore_r", "arm_r", (0.0, -0.3, 0.0)),
    ("thigh_l", "pelvis", (-0.105, -0.03, 0.0)),
    ("shin_l", "thigh_l", (0.0, -0.41, 0.0)),
    ("foot_l", "shin_l", (0.0, -0.4, 0.0)),
    ("thigh_r", "pelvis", (0.105, -0.03, 0.0)),
    ("shin_r", "thigh_r", (0.0, -0.41, 0.0)),
    ("foot_r", "shin_r", (0.0, -0.4, 0.0)),
]


def pose_angles(pose, phase, t, lean=0.0):
    """Return (pelvis_y, {bone: rotation matrix})."""
    R = {}
    hip = HIP
    if pose == "run":
        for side, off in (("l", 0.0), ("r", math.pi)):
            p = phase + off
            swing = 0.78 * math.sin(p)
            knee = 0.2 + 1.3 * max(0.0, -math.sin(p)) + 0.25 * max(0.0, math.cos(p))
            R["thigh_" + side] = rot(pitch=-swing)
            R["shin_" + side] = rot(pitch=knee)
            R["foot_" + side] = rot(pitch=(swing - knee) * 0.6)
            sgn = -1 if side == "l" else 1
            R["arm_" + side] = rot(pitch=0.75 * math.sin(p), roll=0.12 * sgn)
            R["fore_" + side] = rot(pitch=-1.35)
        hip = HIP - 0.05 + 0.06 * abs(math.cos(phase))
        R["spine"] = rot(pitch=0.22, yaw=0.12 * math.sin(phase))
        R["head"] = rot(pitch=-0.18, yaw=-0.1 * math.sin(phase))
    elif pose == "jump":
        R["thigh_l"] = rot(pitch=-1.15)
        R["shin_l"] = rot(pitch=1.7)
        R["thigh_r"] = rot(pitch=-0.55)
        R["shin_r"] = rot(pitch=1.2)
        R["foot_l"] = rot(pitch=-0.4)
        R["foot_r"] = rot(pitch=-0.4)
        R["arm_l"] = rot(pitch=-0.3, roll=-2.3)
        R["arm_r"] = rot(pitch=-0.3, roll=2.3)
        R["fore_l"] = rot(pitch=-0.5)
        R["fore_r"] = rot(pitch=-0.5)
        R["spine"] = rot(pitch=0.12)
        R["head"] = rot(pitch=-0.1)
    elif pose == "slide":
        hip = 0.42
        R["spine"] = rot(pitch=1.0)
        R["head"] = rot(pitch=-0.75)
        for side, sgn in (("l", -1), ("r", 1)):
            R["thigh_" + side] = rot(pitch=-1.45, roll=0.15 * sgn)
            R["shin_" + side] = rot(pitch=2.35)
            R["foot_" + side] = rot(pitch=-0.6)
            R["arm_" + side] = rot(pitch=-1.1, roll=0.45 * sgn)
            R["fore_" + side] = rot(pitch=-0.7)
    elif pose == "fall":
        hip = 0.46
        R["spine"] = rot(pitch=-1.15)
        R["head"] = rot(pitch=0.35)
        flail = math.sin(t * 18) * 0.4
        for side, sgn in (("l", -1), ("r", 1)):
            R["thigh_" + side] = rot(pitch=-1.35, roll=0.25 * sgn)
            R["shin_" + side] = rot(pitch=0.6)
            R["arm_" + side] = rot(pitch=-0.4, roll=(1.9 + flail * sgn) * sgn)
            R["fore_" + side] = rot(pitch=-0.4)
    else:  # idle / wave / cheer
        breath = math.sin(t * 2.2)
        R["spine"] = rot(pitch=0.02 * breath)
        R["head"] = rot(yaw=0.18 * math.sin(t * 0.7), pitch=-0.03)
        for side, sgn in (("l", -1), ("r", 1)):
            R["thigh_" + side] = rot(roll=0.04 * sgn)
            R["shin_" + side] = rot(pitch=0.03)
            R["foot_" + side] = rot(roll=-0.04 * sgn)
            R["arm_" + side] = rot(pitch=0.05, roll=(0.14 + 0.02 * breath) * sgn)
            R["fore_" + side] = rot(pitch=-0.25)
        if pose == "wave":
            R["arm_r"] = rot(pitch=-0.2, roll=2.55)
            R["fore_r"] = rot(roll=0.35 + 0.45 * math.sin(t * 9))
        elif pose == "cheer":
            bounce = abs(math.sin(t * 5.5))
            hip = HIP + 0.08 * bounce
            for side, sgn in (("l", -1), ("r", 1)):
                R["arm_" + side] = rot(pitch=-0.15, roll=(2.75 - 0.2 * bounce) * sgn)
                R["fore_" + side] = rot(pitch=-0.3)
                R["thigh_" + side] = rot(pitch=-0.25 * bounce, roll=0.08 * sgn)
                R["shin_" + side] = rot(pitch=0.5 * bounce)
    R["pelvis"] = rot(roll=-lean * 0.28, yaw=lean * 0.15)
    return hip, R


def skeleton_world(look, pose, phase, t, lean=0.0):
    bw = float(look.get("build", 1.0))
    hip, R = pose_angles(pose, phase, t, lean)
    world = {}
    for bone, parent, off in SKELETON:
        local = R.get(bone, IDENT)
        if parent is None:
            world[bone] = (local, (0.0, hip, 0.0))
        else:
            pR, pT = world[parent]
            o = mvec(pR, (off[0] * bw, off[1], off[2]))
            world[bone] = (mmul(pR, local), (pT[0] + o[0], pT[1] + o[1], pT[2] + o[2]))
    return world


def posed_faces(parts, world, extra=()):
    """Transform every part into model space. Returns [(pts, normal, color)]."""
    out = []
    for part in list(parts) + list(extra):
        R, T = world.get(part.bone, (IDENT, (0.0, 0.0, 0.0)))
        r0, r1, r2 = R
        tx, ty, tz = T
        vs = [(r0[0] * x + r0[1] * y + r0[2] * z + tx,
               r1[0] * x + r1[1] * y + r1[2] * z + ty,
               r2[0] * x + r2[1] * y + r2[2] * z + tz) for x, y, z in part.verts]
        for idx, n, col in part.faces:
            nw = (r0[0] * n[0] + r0[1] * n[1] + r0[2] * n[2],
                  r1[0] * n[0] + r1[1] * n[1] + r1[2] * n[2],
                  r2[0] * n[0] + r2[1] * n[1] + r2[2] * n[2])
            out.append(([vs[i] for i in idx], nw, col))
    return out


def draw_faces(surf, faces, project, eye, fog=None, outline=None):
    """Cull, light, sort and draw model-space faces.

    ``project(p)`` maps a model-space point to screen; ``eye`` is the camera in
    model space; ``fog(color, point)`` optionally tints by distance.
    """
    ex, ey, ez = eye
    lx, ly, lz = LIGHT
    items = []
    for pts, n, col in faces:
        k = len(pts)
        cx = sum(p[0] for p in pts) / k
        cy = sum(p[1] for p in pts) / k
        cz = sum(p[2] for p in pts) / k
        vx, vy, vz = ex - cx, ey - cy, ez - cz
        if n[0] * vx + n[1] * vy + n[2] * vz <= 0:
            continue
        lit = AMBIENT + DIFFUSE * max(0.0, n[0] * lx + n[1] * ly + n[2] * lz)
        c = (min(255, int(col[0] * lit)), min(255, int(col[1] * lit)), min(255, int(col[2] * lit)))
        if fog is not None:
            c = fog(c, (cx, cy, cz))
        items.append((vx * vx + vy * vy + vz * vz, pts, c))
    items.sort(key=lambda it: -it[0])
    poly = pygame.draw.polygon
    for _, pts, c in items:
        sp = [project(p) for p in pts]
        poly(surf, c, sp)
        if outline is not None:
            poly(surf, outline, sp, 1)
    return len(items)


# ---------------------------------------------------------------------------
# Extra props (board, jetpack)
# ---------------------------------------------------------------------------
def board_part(board):
    deck = board["colors"]["deck"]
    stripe = board["colors"]["stripe"]
    style = board.get("style", "street")
    p = Part("board")
    p.box(-0.21, 0.21, 0.0, 0.06, -0.52, 0.52, deck, {"top": shade(deck, 1.1)})
    p.box(-0.17, 0.17, 0.0, 0.08, 0.5, 0.6, deck)      # nose kick
    p.box(-0.17, 0.17, 0.0, 0.08, -0.6, -0.5, deck)    # tail kick
    p.box(-0.05, 0.05, 0.06, 0.065, -0.45, 0.45, stripe)
    if style in ("street", "cyber", "neon"):
        for z in (-0.36, 0.36):
            p.box(-0.18, 0.18, -0.04, 0.0, z - 0.04, z + 0.04, (90, 90, 100))
            for x in (-0.19, 0.19):
                p.box(x - 0.035, x + 0.035, -0.1, -0.02, z - 0.05, z + 0.05, (30, 30, 34))
    else:  # hover pads
        for z in (-0.32, 0.32):
            p.box(-0.15, 0.15, -0.06, 0.0, z - 0.1, z + 0.1, board["colors"]["glow"])
    return p


def jetpack_part():
    p = Part("spine")
    p.box(-0.16, 0.16, 0.12, 0.5, -0.32, -0.13, (200, 205, 220), {"top": (225, 230, 240)})
    for sx in (-0.1, 0.1):
        p.prism(0.14, 0.055, 0.045, (90, 95, 110), n=6, x=sx, z=-0.25, y0=0.14)
    p.box(-0.04, 0.04, 0.35, 0.45, -0.335, -0.32, (255, 80, 60))
    return p


# ---------------------------------------------------------------------------
# High level helpers
# ---------------------------------------------------------------------------
_cache = {}


def model_for(look):
    key = tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in look.items()))
    m = _cache.get(key)
    if m is None:
        if len(_cache) > 64:
            _cache.clear()
        m = build_model(look)
        _cache[key] = m
    return m


def draw_in_world(r, look, pose, phase, t, x, y, z, lean=0.0, extra=()):
    """Draw a character into the game world through the renderer's camera (call inside a queued draw)."""
    cam = r.cam
    world = skeleton_world(look, pose, phase, t, lean)
    faces = posed_faces(model_for(look), world, extra)
    F, hx, hy, cx, cy, cz = cam.focal, cam.hx, cam.hy, cam.x, cam.y, cam.z
    near = 0.3

    def project(p):
        dz = max(near, p[2] + z - cz)
        s = F / dz
        return (hx + (p[0] + x - cx) * s, hy - (p[1] + y - cy) * s)

    def fog(c, p):
        return r.fog(c, p[2] + z - cz)

    return draw_faces(r.surface, faces, project, (cx - x, cy - y, cz - z), fog)


def draw_on_screen(surf, look, pose, cx, feet_y, height_px, t=0.0, phase=0.0, yaw=math.pi, outline=None, extra=()):
    """Draw a character for menus with a turntable camera. yaw=pi faces the viewer."""
    world = skeleton_world(look, pose, phase, t)
    faces = posed_faces(model_for(look), world, extra)
    cyw, sy = math.cos(yaw), math.sin(yaw)
    D = 6.0
    cam_h = 1.05
    F = height_px / 1.8 * D
    oy = feet_y - cam_h * F / D

    def turn(p):
        return (cyw * p[0] + sy * p[2], p[1], -sy * p[0] + cyw * p[2])

    faces = [([turn(p) for p in pts], turn(n), c) for pts, n, c in faces]

    def project(p):
        d = D + p[2]
        return (cx + p[0] * F / d, oy - (p[1] - cam_h) * F / d)

    return draw_faces(surf, faces, project, (0.0, cam_h, -D), None, outline)


_thumbs = {}


def thumbnail(look, size, pose="idle"):
    """Cached small render of a character (shop cards, character strip)."""
    key = (tuple(sorted((k, str(v)) for k, v in look.items())), size, pose)
    s = _thumbs.get(key)
    if s is None:
        if len(_thumbs) > 120:
            _thumbs.clear()
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        draw_on_screen(s, look, pose, size / 2, size * 0.94, size * 0.88, t=0.0, yaw=math.pi + 0.35)
        _thumbs[key] = s
    return s
