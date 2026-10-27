"""Builds and animates the 3D scene for a CourseWorld.

Static platforms are merged into a few big meshes (fast).  Moving pieces
(movers, pistons, tiles, hammers, sweepers) get their own nodes and are
posed every frame from the simulation clock, so what you see is exactly
what the physics uses.
"""

import math
import random

from panda3d.core import (Fog, NodePath, TransparencyAttrib)

from .character_view import model_file
from .model_utils import srgb_fix
from .procgeom import MeshBuilder, hex_color, mix, shade, sky_dome

DEFAULT_THEME = {"sky_top": "#3fa9ff", "sky_bottom": "#ffe3f3", "fog": "#ffd6ee", "void": "#ff6fb5",
                 "floor_a": "#ffcf5c", "floor_b": "#ffe08a", "accent": "#ff5d8f", "side": "#6c4bd8"}


def rotation_sign(setter_name):
    """Which way a positive roll/pitch swings a hanging object (engine convention check)."""
    t = NodePath("t")
    getattr(t, setter_name)(30)
    p = NodePath("root").getRelativePoint(t, (0, 0, -1))
    return (1 if p.x > 0 else -1) if setter_name == "setR" else (1 if p.y > 0 else -1)


class CourseView:
    def __init__(self, base, loaded_map, world, parent=None):
        self.base = base
        self.map = loaded_map
        self.world = world
        self.root = (parent or base.render).attachNewNode("course_" + loaded_map.id)
        theme = dict(DEFAULT_THEME)
        theme.update(loaded_map.theme or {})
        self.theme = {k: hex_color(v) for k, v in theme.items()}
        self.movers = []  # (solid, node)
        self.tiles = []  # (tile, node, base_color)
        self.hammers = []  # (hazard, node)
        self.sweepers = []  # (hazard, node)
        self._roll_sign = rotation_sign("setR")
        self._pitch_sign = rotation_sign("setP")
        self._build_sky()
        self._build_void()
        self._build_static()
        self._build_dynamic()
        self._build_hazards()
        self._build_props()
        self._build_decor()
        self.update(0.0, 0.0)

    # ---------------------------------------------------------------- environment
    def _build_sky(self):
        th = self.theme
        sky = sky_dome(th["sky_top"], th["sky_bottom"])
        sky.reparentTo(self.root)
        sky.setBin("background", 0)
        sky.setDepthWrite(False)
        sky.setLightOff(1)
        sky.setShaderOff(1)
        sky.setFogOff(1)
        sky.setTwoSided(True)
        self.sky = sky
        fog = Fog("course_fog")
        fog.setMode(Fog.MLinear)  # setLinearRange alone keeps the (very dense) exponential default
        fog.setColor(th["fog"])
        fog.setLinearRange(70, 260)
        self.fog = fog
        self.root.setFog(fog)

    def _build_void(self):
        """A shiny 'goo' sea far below the course."""
        th = self.theme
        mb = MeshBuilder("void")
        z = self.world.kill_z + 3.0
        c1 = th["void"]
        c2 = shade(c1, 1.25)
        size = 30.0
        for i in range(-6, 7):
            for j in range(-4, 13):
                c = c1 if (i + j) % 2 == 0 else mix(c1, c2, 0.5)
                x0, y0 = i * size, j * size
                mb.quad((x0, y0, z), (x0 + size, y0, z), (x0 + size, y0 + size, z), (x0, y0 + size, z),
                        (0, 0, 1), c)
        self.void = mb.node()
        self.void.reparentTo(self.root)
        self.void.setLightOff(1)
        self.void.setShaderOff(1)
        self.void_z = z

    # ---------------------------------------------------------------- solids
    def _solid_colors(self, s, index):
        th = self.theme
        style = s.style or {}
        if "color" in style:
            top = hex_color(style["color"])
        elif style.get("role") == "hurdle":
            top = th["accent"]
        else:
            top = th["floor_a"] if index % 2 == 0 else th["floor_b"]
        side = mix(shade(top, 0.75), th["side"], 0.35)
        return top, side

    def _build_static(self):
        mb = MeshBuilder("static")
        th = self.theme
        idx = 0
        for s in self.world.solids:
            if s.moving or s.kind == "tile":
                continue
            top, side = self._solid_colors(s, idx)
            idx += 1
            pattern = (s.style or {}).get("pattern")
            if s.kind == "ramp":
                mb.wedge(s.minx, s.miny, s.maxx, s.maxy, s.z0, s.z1, s.minz, top, side)
                continue
            if (s.style or {}).get("role") == "hurdle":
                mb.box(s.minx, s.miny, s.minz, s.maxx, s.maxy, s.maxz, top, side, pattern="stripes",
                       stripe=hex_color("#ffffff"))
                continue
            if s.kind == "bounce":
                mb.box(s.minx, s.miny, s.minz, s.maxx, s.maxy, s.maxz, hex_color("#3ff2c4"), side)
                continue
            if pattern == "finish":
                mb.box(s.minx, s.miny, s.minz, s.maxx, s.maxy, s.maxz, hex_color("#ffffff"), side,
                       pattern="checker", stripe=hex_color("#222244"), cell=1.0)
            elif pattern == "start":
                mb.box(s.minx, s.miny, s.minz, s.maxx, s.maxy, s.maxz, top, side, pattern="checker",
                       stripe=shade(top, 0.88), cell=2.0)
            else:
                big = (s.maxx - s.minx) * (s.maxy - s.miny) > 30
                mb.box(s.minx, s.miny, s.minz, s.maxx, s.maxy, s.maxz, top, side,
                       pattern="checker" if big else None, stripe=shade(top, 0.93), cell=2.0)
        node = mb.node()
        node.reparentTo(self.root)
        node.flattenStrong()
        self.static = node
        del th

    def _box_node(self, s, top, side, name, pattern=None, stripe=None):
        mb = MeshBuilder(name)
        mb.box(-s.hx, -s.hy, -s.hz, s.hx, s.hy, s.hz, top, side, pattern=pattern, stripe=stripe, cell=1.0)
        n = mb.node()
        n.reparentTo(self.root)
        return n

    def _build_dynamic(self):
        th = self.theme
        for s in self.world.solids:
            if s.kind == "moving":
                top = hex_color((s.style or {}).get("color", "#a37bff"))
                n = self._box_node(s, top, shade(top, 0.7), s.id, pattern="stripes", stripe=shade(top, 1.15))
                self.movers.append((s, n))
            elif s.kind == "pusher":
                n = self._box_node(s, th["accent"], shade(th["accent"], 0.7), s.id, pattern="stripes",
                                   stripe=hex_color("#ffd23f"))
                self.movers.append((s, n))
            elif s.kind == "tile":
                if "color" in (s.style or {}):
                    base = hex_color(s.style["color"])
                else:
                    parity = int(round(s.cx / 2.3)) + int(round(s.cy / 2.3))
                    base = th["floor_a"] if parity % 2 == 0 else th["floor_b"]
                mb = MeshBuilder(s.id)
                mb.box(-s.hx, -s.hy, -s.hz, s.hx, s.hy, s.hz, (1, 1, 1, 1), (0.8, 0.8, 0.85, 1))
                n = mb.node()
                n.reparentTo(self.root)
                n.setPos(s.cx, s.cy, s.cz)
                n.setColorScale(base)
                self.tiles.append((s, n, base))
        # One flatten per tile would break per-tile colour changes, so tiles stay separate nodes.

    # ---------------------------------------------------------------- hazards
    def _build_hazards(self):
        small = self.base.loader.loadModel(model_file("prop_hammer.glb"))
        big = self.base.loader.loadModel(model_file("prop_hammer_big.glb"))
        srgb_fix(small)
        srgb_fix(big)
        for h in self.world.hazards:
            if h.kind == "hammer":
                src = big if (h.style or {}).get("size") == "big" else small
                pivot = self.root.attachNewNode(h.id)
                pivot.setPos(*h.pivot)
                swing = pivot.attachNewNode("swing")
                inst = src.instanceTo(swing)
                # The Blender prop is built at a fixed size; scale it to this hammer.
                ref_len = 6.4 if src is big else 5.6
                inst.setScale(1.0, 1.0, h.length / ref_len)
                if h.axis == "x":
                    swing.setH(90)  # head axis now along Y (tangent of a Y-Z swing)
                    holder = swing
                else:
                    holder = swing
                self.hammers.append((h, pivot, holder))
            elif h.kind == "sweeper":
                node = self.root.attachNewNode(h.id)
                node.setPos(h.cx, h.cy, h.z)
                post = MeshBuilder("post")
                post.cylinder(0, 0, -h.z - 0.05, h.radius + 0.45, 0.45, self.theme["side"], segs=18,
                              top_color=self.theme["accent"])
                pn = post.node()
                pn.reparentTo(self.root)
                pn.setPos(h.cx, h.cy, h.z)
                for k in range(h.arms):
                    arm = MeshBuilder("arm")
                    arm.capsule_bar(h.length, h.radius, hex_color("#ff3d6e"), hex_color("#ffffff"),
                                    stripes=int(h.length * 1.5))
                    an = arm.node()
                    an.reparentTo(node)
                    an.setTwoSided(True)
                    an.setH(360.0 * k / h.arms)
                self.sweepers.append((h, node))

    # ---------------------------------------------------------------- props & decor
    def _build_props(self):
        f = self.world.finish
        arch = srgb_fix(self.base.loader.loadModel(model_file("prop_finish_arch.glb")))
        arch.reparentTo(self.root)
        arch.setPos((f.minx + f.maxx) / 2, (f.miny + f.maxy) / 2, f.minz + 0.5)
        width = f.maxx - f.minx
        arch.setScale(max(0.6, width / 12.0), 1, 1)
        self.finish_arch = arch
        sp = self.map.spawn
        start = srgb_fix(self.base.loader.loadModel(model_file("prop_start_arch.glb")))
        start.reparentTo(self.root)
        start.setPos(sp["x"], sp["y"] + 2.6, sp["top"])
        start.setScale(1.05, 1, 1)
        self.start_arch = start

    def _build_decor(self):
        rng = random.Random(hash(self.map.id) & 0xFFFF)
        cloud = srgb_fix(self.base.loader.loadModel(model_file("prop_cloud.glb")))
        length = self.world.route.length
        decor = self.root.attachNewNode("decor")
        for i in range(26):
            side = rng.choice((-1, 1))
            c = cloud.instanceTo(decor)
            c.setPos(side * rng.uniform(28, 80), rng.uniform(-30, length + 60), rng.uniform(-6, 30))
            s = rng.uniform(1.6, 4.0)
            c.setScale(s, s, s * 0.8)
            c.setH(rng.uniform(0, 360))
        # Floating islands with candy-coloured pillars far from the course.
        mb = MeshBuilder("islands")
        th = self.theme
        for i in range(14):
            side = rng.choice((-1, 1))
            x = side * rng.uniform(32, 70)
            y = rng.uniform(-10, length + 40)
            z = rng.uniform(-8, 6)
            w = rng.uniform(4, 10)
            top = mix(th["floor_a"], hex_color("#7bdcb5"), rng.random())
            mb.box(x - w / 2, y - w / 2, z - rng.uniform(2, 6), x + w / 2, y + w / 2, z, top,
                   mix(top, th["side"], 0.5))
            if rng.random() < 0.6:
                mb.cylinder(x, y, z, z + rng.uniform(3, 9), rng.uniform(0.4, 0.9),
                            mix(th["accent"], th["sky_top"], rng.random()), segs=12)
        isl = mb.node()
        isl.reparentTo(decor)
        isl.flattenStrong()
        decor.flattenMedium()
        self.decor = decor
        # Course-side flag poles along the start platform.
        sp = self.map.spawn
        flags = MeshBuilder("flags")
        for k, x in enumerate((-7.6, 7.6)):
            flags.cylinder(x, sp["y"] - 6, sp["top"], sp["top"] + 4.5, 0.08, hex_color("#ffffff"), segs=8)
            col = th["accent"] if k == 0 else th["sky_top"]
            flags.quad((x, sp["y"] - 6, sp["top"] + 3.6), (x + 1.4 * (1 if x < 0 else -1), sp["y"] - 6, sp["top"] + 4.0),
                       (x + 1.4 * (1 if x < 0 else -1), sp["y"] - 6, sp["top"] + 4.5), (x, sp["y"] - 6, sp["top"] + 4.5),
                       (0, -1, 0), col)
        fl = flags.node()
        fl.reparentTo(self.root)
        fl.setTwoSided(True)

    # ---------------------------------------------------------------- per frame
    def update(self, t, dt, camera_pos=None):
        for s, n in self.movers:
            x, y, z = s.position_at(t)
            n.setPos(x, y, z)
        for tile, n, base in self.tiles:
            st = tile.state_at(t)
            if st == "gone":
                if not n.isHidden():
                    n.hide()
                continue
            if n.isHidden():
                n.show()
            if st == "warning":
                f = tile.warning_fraction(t)
                blink = 0.5 + 0.5 * math.sin(t * (18 + 30 * f))
                warn = mix(base, hex_color("#ff3355"), min(1.0, 0.35 + f * 0.65))
                n.setColorScale(mix(warn, (1, 1, 1, 1), blink * 0.35))
                jit = 0.03 + 0.06 * f
                n.setPos(tile.cx + math.sin(t * 63) * jit, tile.cy + math.cos(t * 71) * jit,
                         tile.cz - f * 0.12)
            else:
                n.setColorScale(base)
                n.setPos(tile.cx, tile.cy, tile.cz)
        for h, pivot, holder in self.hammers:
            a = math.degrees(h.angle_at(t))
            if h.axis == "y":
                pivot.setR(a * self._roll_sign)
            else:
                pivot.setP(a * self._pitch_sign)
        for h, node in self.sweepers:
            node.setH(math.degrees(h.angle_at(t)))
        if camera_pos is not None:
            self.sky.setPos(camera_pos)

    def destroy(self):
        self.root.removeNode()
