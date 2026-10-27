"""Lightweight particle effects with a fixed pool of billboard cards (no allocation per effect)."""

import math
import random

from panda3d.core import CardMaker, TextNode, TransparencyAttrib

from .procgeom import hex_color


class _Particle:
    __slots__ = ("node", "vx", "vy", "vz", "life", "max_life", "size", "grav", "spin", "color", "alive")


class Effects:
    def __init__(self, parent, pool_size=420, font=None):
        self.root = parent.attachNewNode("effects")
        self.root.setLightOff(1)
        self.root.setShaderOff(1)
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        self.root.setDepthWrite(False)
        self.root.setBin("fixed", 5)
        self.root.setFogOff(1)
        cm = CardMaker("p")
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)
        self.pool = []
        for _ in range(pool_size):
            p = _Particle()
            p.node = self.root.attachNewNode(cm.generate())
            p.node.setBillboardPointEye()
            p.node.hide()
            p.alive = False
            self.pool.append(p)
        self.active = []
        self.free = list(self.pool)
        self.popups = []
        self.font = font
        self.rng = random.Random()

    # ---------------------------------------------------------------- spawning
    def _spawn(self, x, y, z, vx, vy, vz, life, size, color, grav=9.0, spin=0.0):
        if not self.free:
            return
        p = self.free.pop()
        p.vx, p.vy, p.vz = vx, vy, vz
        p.life = p.max_life = life
        p.size = size
        p.grav = grav
        p.spin = spin
        p.color = color
        p.alive = True
        p.node.setPos(x, y, z)
        p.node.setScale(size)
        p.node.setColor(color)
        p.node.show()
        self.active.append(p)

    def dust(self, x, y, z, amount=8, color="#ffffff"):
        c = hex_color(color, 0.8)
        r = self.rng
        for _ in range(amount):
            a = r.uniform(0, 2 * math.pi)
            sp = r.uniform(1.0, 2.6)
            self._spawn(x, y, z + 0.1, math.cos(a) * sp, math.sin(a) * sp, r.uniform(0.3, 1.2),
                        r.uniform(0.35, 0.6), r.uniform(0.18, 0.32), c, grav=2.0)

    def confetti(self, x, y, z, amount=60, spread=4.0):
        r = self.rng
        cols = ["#ff3d6e", "#ffd23f", "#3ff2c4", "#4aa8ff", "#b65cff", "#ffffff"]
        for _ in range(amount):
            a = r.uniform(0, 2 * math.pi)
            sp = r.uniform(0.5, spread)
            self._spawn(x, y, z, math.cos(a) * sp, math.sin(a) * sp, r.uniform(4, 9), r.uniform(1.6, 2.8),
                        r.uniform(0.12, 0.22), hex_color(r.choice(cols)), grav=6.0, spin=r.uniform(-8, 8))

    def stars(self, x, y, z, amount=10):
        r = self.rng
        for _ in range(amount):
            a = r.uniform(0, 2 * math.pi)
            self._spawn(x, y, z, math.cos(a) * 3.2, math.sin(a) * 3.2, r.uniform(1.5, 4.0), 0.6,
                        r.uniform(0.2, 0.35), hex_color(r.choice(["#ffd23f", "#ffffff", "#ffe066"])),
                        grav=8.0, spin=10)

    def splash(self, x, y, z, color="#ff6fb5", amount=24):
        r = self.rng
        c = hex_color(color, 0.9)
        for _ in range(amount):
            a = r.uniform(0, 2 * math.pi)
            sp = r.uniform(0.5, 3.0)
            self._spawn(x, y, z, math.cos(a) * sp, math.sin(a) * sp, r.uniform(4, 9), r.uniform(0.6, 1.1),
                        r.uniform(0.25, 0.5), c, grav=14.0)

    def trail(self, x, y, z, kind):
        """Skin effect trail (sparkle / stardust / confetti) behind a running character."""
        r = self.rng
        if kind == "stardust":
            col = hex_color(r.choice(["#18e0c8", "#ff7ef5", "#ffffff"]), 0.9)
        elif kind == "sparkle":
            col = hex_color(r.choice(["#ffd23f", "#fff1a8"]), 0.9)
        else:
            col = hex_color(r.choice(["#ff3d6e", "#ffd23f", "#3ff2c4", "#4aa8ff"]), 0.9)
        self._spawn(x + r.uniform(-0.3, 0.3), y + r.uniform(-0.3, 0.3), z + r.uniform(0.3, 1.3),
                    0, 0, r.uniform(0.2, 0.8), r.uniform(0.5, 0.9), r.uniform(0.08, 0.16), col, grav=0.5)

    def popup(self, x, y, z, text, color="#ffd23f", scale=0.7):
        tn = TextNode("popup")
        tn.setText(text)
        tn.setAlign(TextNode.ACenter)
        if self.font is not None:
            tn.setFont(self.font)
        tn.setTextColor(hex_color(color))
        tn.setShadow(0.05, 0.05)
        tn.setShadowColor(0, 0, 0, 0.7)
        n = self.root.attachNewNode(tn)
        n.setPos(x, y, z)
        n.setScale(scale)
        n.setBillboardPointEye()
        self.popups.append([n, 0.0])

    # ---------------------------------------------------------------- update
    def update(self, dt):
        still = []
        for p in self.active:
            p.life -= dt
            if p.life <= 0.0:
                p.node.hide()
                p.alive = False
                self.free.append(p)
                continue
            p.vz -= p.grav * dt
            n = p.node
            n.setPos(n.getX() + p.vx * dt, n.getY() + p.vy * dt, n.getZ() + p.vz * dt)
            f = p.life / p.max_life
            n.setAlphaScale(min(1.0, f * 2.0))
            if p.spin:
                n.setR(n.getR() + p.spin * 30 * dt)
            still.append(p)
        self.active = still
        keep = []
        for entry in self.popups:
            n, age = entry
            age += dt
            if age > 1.1:
                n.removeNode()
                continue
            entry[1] = age
            n.setZ(n.getZ() + dt * 1.6)
            n.setAlphaScale(max(0.0, 1.0 - max(0.0, age - 0.6) / 0.5))
            s = 0.7 * (1.0 + 0.4 * max(0.0, 0.15 - age) / 0.15)
            n.setScale(s)
            keep.append(entry)
        self.popups = keep

    def clear(self):
        for p in self.active:
            p.node.hide()
            self.free.append(p)
        self.active = []
        for n, _ in self.popups:
            n.removeNode()
        self.popups = []

    def destroy(self):
        self.root.removeNode()

