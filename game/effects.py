"""Visual effects: pooled 3D particles, screen-space particles, floating text,
speed lines, weather and screen flashes.

All particle systems use fixed-size pools so no objects are allocated per
frame and the particle count is capped by the graphics quality setting.
"""
import math
import random

import pygame

from . import settings as S

RAINBOW = [(255, 70, 70), (255, 160, 40), (255, 235, 60), (80, 220, 100), (70, 160, 255), (170, 90, 255)]


class Particle:
    __slots__ = ("x", "y", "z", "vx", "vy", "vz", "life", "max_life", "size", "color", "gravity", "kind", "alive")

    def __init__(self):
        self.alive = False


class ParticleSystem:
    """World-space particles projected through the camera."""

    def __init__(self, capacity=200):
        self.pool = [Particle() for _ in range(600)]
        self.capacity = capacity
        self.active = 0
        self._cursor = 0

    def set_capacity(self, n):
        self.capacity = max(10, min(len(self.pool), n))

    def clear(self):
        for p in self.pool:
            p.alive = False
        self.active = 0

    def emit(self, x, y, z, vx, vy, vz, life, size, color, gravity=0.0, kind="dot"):
        if self.active >= self.capacity:
            return
        pool = self.pool
        n = len(pool)
        for _ in range(n):
            p = pool[self._cursor]
            self._cursor = (self._cursor + 1) % n
            if not p.alive:
                p.x, p.y, p.z, p.vx, p.vy, p.vz = x, y, z, vx, vy, vz
                p.life = p.max_life = life
                p.size = size
                p.color = color
                p.gravity = gravity
                p.kind = kind
                p.alive = True
                self.active += 1
                return

    def burst(self, x, y, z, count, color, speed=4.0, life=0.6, size=0.12, gravity=-9.0, kind="dot", spread_z=1.0):
        for _ in range(count):
            a = random.uniform(0, math.tau)
            e = random.uniform(-0.3, 1.0)
            sp = random.uniform(0.4, 1.0) * speed
            c = random.choice(RAINBOW) if color == "rainbow" else color
            self.emit(x, y, z, math.cos(a) * sp, e * sp, math.sin(a) * sp * spread_z, life * random.uniform(0.6, 1.0),
                      size * random.uniform(0.7, 1.3), c, gravity, kind)

    def update(self, dt):
        active = 0
        for p in self.pool:
            if not p.alive:
                continue
            p.life -= dt
            if p.life <= 0:
                p.alive = False
                continue
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.z += p.vz * dt
            active += 1
        self.active = active

    def queue_draw(self, renderer):
        cam = renderer.cam
        for p in self.pool:
            if p.alive and renderer.visible_range(p.z, p.z):
                renderer.queue(p.z, self._draw_one, renderer, p)

    @staticmethod
    def _draw_one(renderer, p):
        if not p.alive:
            return
        cam = renderer.cam
        dz = p.z - cam.z
        if dz < S.NEAR_PLANE:
            return
        s = cam.focal / dz
        sx = cam.hx + (p.x - cam.x) * s
        sy = cam.hy - (p.y - cam.y) * s
        k = p.life / p.max_life
        r = p.size * s * (0.4 + 0.6 * k)
        surf = renderer.surface
        if r < 0.7:
            return
        c = p.color
        if p.kind == "ring":
            rr = p.size * s * (1.6 - k * 1.2)
            if rr > 2:
                pygame.draw.circle(surf, c, (int(sx), int(sy)), int(rr), max(1, int(rr * 0.12)))
        elif p.kind == "star":
            ri = r * 0.45
            pts = []
            for i in range(8):
                rr = r if i % 2 == 0 else ri
                a = i * math.pi / 4 + p.life * 6
                pts.append((sx + math.cos(a) * rr, sy + math.sin(a) * rr))
            pygame.draw.polygon(surf, c, pts)
        elif p.kind == "bubble":
            pygame.draw.circle(surf, c, (int(sx), int(sy)), max(1, int(r)), max(1, int(r * 0.25)))
        elif p.kind == "square":
            pygame.draw.rect(surf, c, (sx - r, sy - r * 0.6, r * 2, r * 1.2))
        elif p.kind == "streak":
            pygame.draw.line(surf, c, (sx, sy), (sx, sy + r * 3), max(1, int(r)))
        else:
            pygame.draw.circle(surf, c, (int(sx), int(sy)), max(1, int(r)))


class ScreenParticles:
    """2D particles in screen space (UI sparkles, coins flying to the HUD)."""

    def __init__(self, capacity=120):
        self.items = []
        self.capacity = capacity

    def emit(self, x, y, vx, vy, life, size, color, gravity=0.0, target=None):
        if len(self.items) < self.capacity:
            self.items.append([x, y, vx, vy, life, life, size, color, gravity, target])

    def burst(self, x, y, count, color, speed=220, life=0.6, size=4, gravity=300):
        for _ in range(count):
            a = random.uniform(0, math.tau)
            sp = random.uniform(0.3, 1.0) * speed
            c = random.choice(RAINBOW) if color == "rainbow" else color
            self.emit(x, y, math.cos(a) * sp, math.sin(a) * sp, life * random.uniform(0.6, 1.0), size, c, gravity)

    def update(self, dt):
        keep = []
        for p in self.items:
            p[4] -= dt
            if p[4] <= 0:
                continue
            if p[9] is not None:  # homing particle
                tx, ty = p[9]
                k = 1 - p[4] / p[5]
                p[0] += (tx - p[0]) * min(1, dt * (4 + 14 * k))
                p[1] += (ty - p[1]) * min(1, dt * (4 + 14 * k))
            else:
                p[3] += p[8] * dt
                p[0] += p[2] * dt
                p[1] += p[3] * dt
            keep.append(p)
        self.items = keep

    def draw(self, surf):
        for p in self.items:
            k = p[4] / p[5]
            r = max(1, int(p[6] * (0.4 + 0.6 * k)))
            pygame.draw.circle(surf, p[7], (int(p[0]), int(p[1])), r)


class FloatingTexts:
    def __init__(self):
        self.items = []

    def add(self, text, x, y, color=(255, 255, 255), size=30, life=1.0, vy=-60):
        if len(self.items) > 20:
            self.items.pop(0)
        self.items.append([text, x, y, color, size, life, life, vy])

    def update(self, dt):
        for it in self.items:
            it[5] -= dt
            it[2] += it[7] * dt
        self.items = [it for it in self.items if it[5] > 0]

    def draw(self, surf, assets):
        for text, x, y, color, size, life, max_life, _ in self.items:
            img = assets.text(text, size, color, shadow=True)
            k = life / max_life
            if k < 0.3:
                img = img.copy()
                img.set_alpha(int(255 * k / 0.3))
            pop = 1.0 + max(0.0, (k - 0.85)) * 2.0
            if pop > 1.01:
                img = pygame.transform.rotozoom(img, 0, pop)
            surf.blit(img, (x - img.get_width() / 2, y - img.get_height() / 2))


class SpeedLines:
    """Radial streaks from the vanishing point when running fast."""

    def __init__(self, count=26):
        self.layer = None
        self.lines = [[random.uniform(0, math.tau), random.uniform(0.2, 1.0), random.uniform(0.4, 1.0)] for _ in range(count)]

    def draw(self, surf, cx, cy, intensity, dt, color=(255, 255, 255)):
        if intensity <= 0.02:
            return
        w, h = surf.get_size()
        maxr = math.hypot(w, h) * 0.6
        if self.layer is None or self.layer.get_size() != (w, h):
            self.layer = pygame.Surface((w, h), pygame.SRCALPHA)
        layer = self.layer
        layer.fill((0, 0, 0, 0))
        for ln in self.lines:
            ln[1] += dt * (2.2 + ln[2] * 2.5)
            if ln[1] > 1.3:
                ln[0] = random.uniform(0, math.tau)
                ln[1] = random.uniform(0.25, 0.5)
                ln[2] = random.uniform(0.4, 1.0)
            r0 = ln[1] * maxr
            r1 = r0 + maxr * 0.18 * ln[2]
            ca, sa = math.cos(ln[0]), math.sin(ln[0])
            a = int(110 * intensity * ln[2])
            pygame.draw.line(layer, (*color, a), (cx + ca * r0, cy + sa * r0 * 0.7), (cx + ca * r1, cy + sa * r1 * 0.7),
                             max(1, int(2 * ln[2])))
        surf.blit(layer, (0, 0))


class Weather:
    """Screen-space weather for events: snow, leaves, confetti, sun motes."""

    def __init__(self):
        self.kind = ""
        self.flakes = []
        self.count = 60

    def set(self, kind, count):
        if kind == self.kind and count == self.count:
            return
        self.kind = kind
        self.count = count
        self.flakes = [self._new(True) for _ in range(count)] if kind else []

    def _new(self, anywhere=False):
        y = random.uniform(-S.SCREEN_H, S.SCREEN_H) if anywhere else random.uniform(-60, -10)
        if self.kind == "snow":
            c = (255, 255, 255)
        elif self.kind == "leaves":
            c = random.choice([(230, 120, 30), (200, 70, 20), (240, 180, 40), (150, 60, 20)])
        elif self.kind == "confetti":
            c = random.choice(RAINBOW)
        else:
            c = (255, 240, 180)
        return [random.uniform(0, S.SCREEN_W), y, random.uniform(-30, 30), random.uniform(40, 140),
                random.uniform(0, math.tau), random.uniform(2, 5), c]

    def update(self, dt, speed_factor=0.0):
        for f in self.flakes:
            f[4] += dt * 3
            f[0] += (f[2] + math.sin(f[4]) * 25) * dt
            f[1] += f[3] * dt * (1 + speed_factor)
            if f[1] > S.SCREEN_H + 20 or f[0] < -30 or f[0] > S.SCREEN_W + 30:
                f[:] = self._new()

    def draw(self, surf):
        if not self.kind:
            return
        for x, y, _, _, ph, size, c in self.flakes:
            if self.kind == "snow":
                pygame.draw.circle(surf, c, (int(x), int(y)), int(size * 0.8))
            elif self.kind == "leaves":
                w = size * 2.2 * abs(math.cos(ph))
                pygame.draw.ellipse(surf, c, (x - w / 2, y - size * 0.7, max(1, w), size * 1.4))
            elif self.kind == "confetti":
                w = size * 1.6 * abs(math.cos(ph))
                pygame.draw.rect(surf, c, (x - w / 2, y - size / 2, max(1, w), size))
            else:
                pygame.draw.circle(surf, c, (int(x), int(y)), max(1, int(size * 0.4 * (1 + math.sin(ph)))))


class Flash:
    def __init__(self):
        self.color = (255, 255, 255)
        self.time = 0.0
        self.dur = 1.0
        self.layer = None

    def trigger(self, color, dur=0.25):
        self.color = color
        self.time = self.dur = dur

    def update(self, dt):
        self.time = max(0.0, self.time - dt)

    def draw(self, surf):
        if self.time <= 0:
            return
        a = int(170 * self.time / self.dur)
        if self.layer is None or self.layer.get_size() != surf.get_size():
            self.layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        self.layer.fill((*self.color, a))
        surf.blit(self.layer, (0, 0))
