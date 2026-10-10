"""Short-lived visual effects: tracers, muzzle flashes, impacts, damage numbers, storm wall."""
from __future__ import annotations

import math

import numpy as np
from panda3d.core import (CardMaker, ColorBlendAttrib, LineSegs, NodePath, TextNode, Texture, TransparencyAttrib)

from ui import theme as T


def _glow_texture(size=64) -> Texture:
    y, x = np.mgrid[0:size, 0:size] / (size - 1) * 2 - 1
    a = np.clip(1 - np.sqrt(x * x + y * y), 0, 1) ** 2
    img = np.dstack([np.full_like(a, 255), np.full_like(a, 255), np.full_like(a, 255), a * 255]).astype(np.uint8)
    tex = Texture("glow")
    tex.setup2dTexture(size, size, Texture.T_unsigned_byte, Texture.F_rgba8)
    tex.setRamImageAs(img.tobytes(), "RGBA")
    return tex


def _additive(np_: NodePath) -> None:
    np_.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha, ColorBlendAttrib.O_one))
    np_.setDepthWrite(False)
    np_.setLightOff(1)
    np_.setShaderOff(30)
    np_.setBin("fixed", 10)


class Effects:
    def __init__(self, app, parent: NodePath):
        self.app = app
        self.root = parent.attachNewNode("fx")
        self.live: list[tuple[float, float, NodePath, callable]] = []   # (start, duration, node, updater)
        self.glow = _glow_texture()
        self.font = app.fonts.black if getattr(app, "fonts", None) else None
        self.storm = None
        self.time = 0.0

    def _card(self, size, color) -> NodePath:
        cm = CardMaker("fx")
        cm.setFrame(-size, size, -size, size)
        c = self.root.attachNewNode(cm.generate())
        c.setTexture(self.glow)
        c.setColor(*color)
        c.setTransparency(TransparencyAttrib.M_alpha)
        c.setBillboardPointEye()
        _additive(c)
        return c

    def tracer(self, start, end, color) -> None:
        ls = LineSegs()
        ls.setThickness(2.5)
        ls.setColor(color[0], color[1], color[2], 0.9)
        ls.moveTo(*start)
        ls.drawTo(*end)
        node = self.root.attachNewNode(ls.create())
        _additive(node)
        self.live.append((self.time, 0.07, node, lambda n, f: n.setAlphaScale(1 - f)))

    def muzzle(self, pos, color) -> None:
        c = self._card(0.22, (color[0], color[1] * 0.9, color[2] * 0.6, 1))
        c.setPos(*pos)
        self.live.append((self.time, 0.05, c, lambda n, f: n.setScale(1 + f)))

    def impact(self, pos, color=(1, 0.9, 0.7, 1), size=0.25) -> None:
        c = self._card(size, color)
        c.setPos(*pos)
        self.live.append((self.time, 0.25, c, lambda n, f: (n.setScale(1 + 2 * f), n.setAlphaScale(1 - f))))

    def sparkle(self, pos, color=(1, 0.85, 0.3, 1)) -> None:
        for i in range(6):
            c = self._card(0.15, color)
            a = i * math.pi / 3
            c.setPos(pos[0], pos[1], pos[2])
            vx, vy = math.cos(a) * 1.5, math.sin(a) * 1.5
            self.live.append((self.time, 0.6, c, lambda n, f, vx=vx, vy=vy, p=pos:
                              (n.setPos(p[0] + vx * f, p[1] + vy * f, p[2] + 1.5 * f - 1.0 * f * f), n.setAlphaScale(1 - f))))

    def damage_number(self, pos, amount: int, head: bool, shield: bool) -> None:
        tn = TextNode("dmg")
        tn.setText(str(amount))
        if self.font:
            tn.setFont(self.font)
        tn.setAlign(TextNode.ACenter)
        color = (1, 0.85, 0.2, 1) if head else ((0.5, 0.85, 1, 1) if shield else (1, 1, 1, 1))
        tn.setTextColor(*color)
        tn.setShadow(0.06, 0.06)
        tn.setShadowColor(0, 0, 0, 0.8)
        n = self.root.attachNewNode(tn)
        n.setBillboardPointEye()
        n.setLightOff(1)
        n.setShaderOff(30)
        n.setDepthTest(False)
        n.setDepthWrite(False)
        n.setBin("fixed", 20)
        base = (pos[0] + (hash(amount) % 7 - 3) * 0.08, pos[1], pos[2] + 0.4)
        n.setPos(*base)
        n.setScale(0.0)
        self.live.append((self.time, 0.9, n, lambda nd, f, b=base, h=head: (
            nd.setPos(b[0], b[1], b[2] + f * 0.9), nd.setScale(_dmg_scale(nd, f, h)), nd.setAlphaScale(1 - max(0, f - 0.6) / 0.4))))

    def beam(self, pos, color) -> NodePath:
        """Loot beam / glow ring for ground items."""
        c = self._card(0.6, (color[0], color[1], color[2], 0.55))
        c.setPos(pos[0], pos[1], pos[2] + 0.15)
        return c

    # ----------------------------------------------------------- storm
    def storm_wall(self, storm) -> None:
        if self.storm is None:
            seg = 72
            verts, tris = [], []
            from world.world_view import build_mesh
            for i in range(seg + 1):
                a = 2 * math.pi * i / seg
                verts += [(math.cos(a), math.sin(a), -50), (math.cos(a), math.sin(a), 500)]
            for i in range(seg):
                a = i * 2
                tris += [(a, a + 2, a + 3), (a, a + 3, a + 1)]
            v = np.array(verts, float)
            uv = np.array([(i // 2 / seg * 24, (i % 2) * 6) for i in range(len(verts))], float)
            cols = np.tile([0.55, 0.2, 0.95, 0.5], (len(verts), 1))
            node = build_mesh("storm", v, np.zeros_like(v), uv, cols, np.array(tris))
            self.storm = self.root.attachNewNode(node)
            self.storm.setTwoSided(True)
            self.storm.setTransparency(TransparencyAttrib.M_alpha)
            self.storm.setDepthWrite(False)
            self.storm.setLightOff(1)
            self.storm.setShaderOff(30)
            self.storm.setBin("transparent", 30)
            tex = _stripe_texture()
            self.storm.setTexture(tex)
        if storm.radius > 640:   # still out over the ocean: keep the horizon clean
            self.storm.hide()
            return
        self.storm.show()
        self.storm.setPos(storm.center[0], storm.center[1], 0)
        self.storm.setScale(max(storm.radius, 0.5), max(storm.radius, 0.5), 1)
        from panda3d.core import TextureStage
        self.storm.setTexOffset(TextureStage.getDefault(), self.time * 0.05, -self.time * 0.15)

    def update(self, dt: float) -> None:
        self.time += dt
        keep = []
        for start, dur, node, fn in self.live:
            f = (self.time - start) / dur
            if f >= 1:
                node.removeNode()
                continue
            fn(node, f)
            keep.append((start, dur, node, fn))
        self.live = keep

    def destroy(self):
        self.root.removeNode()


def _dmg_scale(node, f, head):
    s = 0.45 if head else 0.35
    pop = min(1.0, f * 8)
    return s * (0.6 + 0.6 * pop - 0.2 * min(1, f * 4))


def _stripe_texture() -> Texture:
    size = 64
    y, x = np.mgrid[0:size, 0:size] / size
    v = 0.6 + 0.4 * np.sin((x + y) * 2 * np.pi * 2)
    a = (0.18 + 0.3 * v) * 255
    img = np.dstack([np.full_like(a, 150), np.full_like(a, 70), np.full_like(a, 255), a]).astype(np.uint8)
    tex = Texture("storm")
    tex.setup2dTexture(size, size, Texture.T_unsigned_byte, Texture.F_rgba8)
    tex.setRamImageAs(img.tobytes(), "RGBA")
    return tex
