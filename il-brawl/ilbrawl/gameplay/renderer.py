"""Draws the battle world: map, objectives, entities, projectiles and effects.

Rendering is kept separate from the simulation: it only reads World state and the
events the world emits each tick.
"""
import math
import random

import pygame

from ilbrawl import config
from ilbrawl.characters import sprites
from ilbrawl.config import TILE
from ilbrawl.gameplay.entities import Brawler
from ilbrawl.ui import text, theme

INK = theme.INK
WALL_H = 14

DEFAULT_THEME = {"floor_a": [132, 200, 100], "floor_b": [122, 190, 92], "wall_top": [150, 150, 160],
                 "wall_side": [104, 104, 116], "bush": [60, 150, 70], "bush_dark": [40, 110, 50],
                 "crate": [180, 130, 80], "water": [80, 170, 240], "deco": [[255, 240, 120]], "border": [60, 110, 50]}


def _t(c):
    return tuple(int(v) for v in c[:3])


# ---------------------------------------------------------------- static map art
class MapRenderer:
    def __init__(self, tm, theme_def, quality="high"):
        self.tm = tm
        from ilbrawl.characters.sprites import mute
        raw = dict(DEFAULT_THEME, **(theme_def or {}))
        # grounded, slightly desaturated palettes for a realistic look
        self.th = {k: (mute(v, 0.22) if k != "deco" else [mute(c, 0.3) for c in v]) for k, v in raw.items()}
        self.quality = quality
        self.base = pygame.Surface((tm.pw, tm.ph))
        self.bushes = pygame.Surface((tm.pw, tm.ph + TILE), pygame.SRCALPHA)
        try:  # match the display format for fast blits
            self.base = self.base.convert()
            self.bushes = self.bushes.convert_alpha()
        except pygame.error:
            pass
        for y in range(tm.h):
            for x in range(tm.w):
                self._floor(x, y)
        for y in range(tm.h):
            for x in range(tm.w):
                self._object(x, y)
        for y in range(tm.h):
            for x in range(tm.w):
                if tm.grid[y][x] == "B":
                    self._bush(x, y)

    def _floor(self, x, y):
        tm, th = self.tm, self.th
        r = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
        tile = tm.grid[y][x]
        rnd = random.Random(x * 7919 + y * 104729 + sum(map(ord, tm.id)))
        col = theme.lerp_color(th["floor_a"], th["floor_b"], rnd.random())
        self.base.fill(col, r)
        if self.quality != "low":
            # grainy ground texture: soft blotches and specks
            for _ in range(10 if self.quality == "high" else 5):
                v = rnd.uniform(-0.09, 0.09)
                c = theme.lighten(col, v) if v > 0 else theme.darken(col, -v)
                w = rnd.randint(4, 14)
                h = rnd.randint(3, 9)
                pygame.draw.ellipse(self.base, c, (r.x + rnd.randint(-2, TILE - w + 2), r.y + rnd.randint(-2, TILE - h + 2), w, h))
            for _ in range(8):
                c = theme.darken(col, rnd.uniform(0.1, 0.25))
                self.base.set_at((r.x + rnd.randint(0, TILE - 1), r.y + rnd.randint(0, TILE - 1)), c)
        if tile == "W":
            self.base.fill(th["water"], r)
            light = theme.lighten(th["water"], 0.3)
            for i in range(2):
                yy = r.y + 14 + i * 18
                pygame.draw.arc(self.base, light, (r.x + 6 + i * 10, yy, 22, 10), 0.2, math.pi - 0.2, 2)
            # shoreline
            for dx, dy, edge in ((0, -1, (r.x, r.y, TILE, 4)), (0, 1, (r.x, r.bottom - 4, TILE, 4)),
                                 (-1, 0, (r.x, r.y, 4, TILE)), (1, 0, (r.right - 4, r.y, 4, TILE))):
                if tm.tile(x + dx, y + dy) != "W" and tm.in_bounds(x + dx, y + dy):
                    self.base.fill(theme.lighten(th["water"], 0.55), edge)
            return
        if self.quality != "low" and rnd.random() < 0.35:
            for _ in range(rnd.randint(0, 2)):
                c = rnd.choice(th["deco"])
                px, py = r.x + rnd.randint(6, TILE - 6), r.y + rnd.randint(6, TILE - 6)
                if rnd.random() < 0.5:
                    pygame.draw.circle(self.base, c, (px, py), rnd.randint(1, 3))
                else:
                    pygame.draw.line(self.base, theme.darken(col, 0.12), (px, py), (px + 3, py - 4), 2)
        # contact shadow below solid tiles
        above = tm.tile(x, y - 1) if y > 0 else "."
        if above in ("#", "C", "X", "P"):
            self.base.fill(theme.darken(col, 0.38), (r.x, r.y, TILE, 8))
            self.base.fill(theme.darken(col, 0.22), (r.x, r.y + 8, TILE, 8))
        left = tm.tile(x - 1, y) if x > 0 else "."
        if left in ("#", "C", "X", "P"):
            self.base.fill(theme.darken(col, 0.3), (r.x, r.y, 10, TILE))

    def _object(self, x, y):
        tm, th = self.tm, self.th
        tile = tm.grid[y][x]
        r = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
        if tile == "#":
            self._block(r, th["wall_top"], th["wall_side"], x, y, "#")
        elif tile == "C":
            self._block(r.inflate(-6, -6), th["crate"], theme.darken(th["crate"], 0.35), x, y, "C", lone=True)
            top = pygame.Rect(r.x + 3, r.y + 3 - WALL_H + 2, TILE - 6, TILE - 6)
            for i in (1, 2):
                yy = top.y + top.h * i // 3
                pygame.draw.line(self.base, theme.darken(th["crate"], 0.25), (top.x + 4, yy), (top.right - 4, yy), 2)
            pygame.draw.line(self.base, theme.darken(th["crate"], 0.35), top.topleft, top.bottomright, 3)
        elif tile == "X":
            c = (196, 74, 60)
            body = pygame.Rect(r.x + 8, r.y + 2 - WALL_H + 6, TILE - 16, TILE - 6)
            pygame.draw.rect(self.base, INK, body.inflate(4, 4), border_radius=10)
            pygame.draw.rect(self.base, c, body, border_radius=9)
            for yy in (body.y + body.h // 3, body.y + body.h * 2 // 3):
                pygame.draw.line(self.base, theme.darken(c, 0.4), (body.x, yy), (body.right, yy), 3)
            pygame.draw.ellipse(self.base, theme.lighten(c, 0.25), (body.x + 4, body.y + 3, body.w - 8, 10))
        elif tile == "P":
            self._block(r.inflate(-4, -4), (120, 130, 150), (76, 84, 100), x, y, "P", lone=True)
            top = pygame.Rect(r.x + 2, r.y + 2 - WALL_H + 2, TILE - 4, TILE - 4)
            g = pygame.Rect(0, 0, 18, 18)
            g.center = top.center
            pygame.draw.rect(self.base, INK, g.inflate(4, 4), border_radius=4)
            pygame.draw.rect(self.base, (90, 255, 140), g, border_radius=3)
            for cx, cy in ((top.x + 5, top.y + 5), (top.right - 5, top.y + 5), (top.x + 5, top.bottom - 5),
                           (top.right - 5, top.bottom - 5)):
                pygame.draw.circle(self.base, (60, 64, 80), (cx, cy), 3)

    def _block(self, r, top_c, side_c, x, y, kind, lone=False):
        tm = self.tm
        same_below = (not lone) and tm.tile(x, y + 1) == kind and y + 1 < tm.h
        side = pygame.Rect(r.x, r.bottom - WALL_H, r.w, WALL_H)
        top = pygame.Rect(r.x, r.y - WALL_H, r.w, r.h)
        if not same_below:
            pygame.draw.rect(self.base, side_c, side)
            pygame.draw.line(self.base, INK, (side.x, side.bottom - 1), (side.right - 1, side.bottom - 1), 3)
        pygame.draw.rect(self.base, top_c, top)
        hl = theme.lighten(top_c, 0.22)
        dk = theme.darken(top_c, 0.15)
        nb = (lambda dx, dy: (not lone) and tm.tile(x + dx, y + dy) == kind)
        if not nb(0, -1):
            pygame.draw.line(self.base, hl, (top.x + 2, top.y + 3), (top.right - 3, top.y + 3), 4)
            pygame.draw.line(self.base, INK, (top.x, top.y), (top.right - 1, top.y), 3)
        if not nb(-1, 0):
            pygame.draw.line(self.base, INK, (top.x, top.y), (top.x, side.bottom - 1), 3)
        if not nb(1, 0):
            pygame.draw.line(self.base, dk, (top.right - 4, top.y + 2), (top.right - 4, top.bottom - 2), 3)
            pygame.draw.line(self.base, INK, (top.right - 1, top.y), (top.right - 1, side.bottom - 1), 3)
        if kind == "#" and self.quality != "low":
            rnd = random.Random(x * 31 + y * 17)
            mortar = theme.darken(top_c, 0.28)
            for row in range(3):
                yy = top.y + 4 + row * (r.h - 8) // 3
                pygame.draw.line(self.base, mortar, (top.x + 3, yy), (top.right - 4, yy), 1)
                off = (row % 2) * r.w // 3
                for k in range(2):
                    xx = top.x + off + k * r.w // 2 + 6
                    if top.x + 3 < xx < top.right - 4:
                        pygame.draw.line(self.base, mortar, (xx, yy), (xx, yy + (r.h - 8) // 3), 1)
            for _ in range(4):
                c = theme.darken(top_c, rnd.uniform(0.05, 0.18))
                pygame.draw.circle(self.base, c, (top.x + rnd.randint(6, r.w - 6), top.y + rnd.randint(6, r.h - 8)), rnd.randint(1, 3))

    def _bush(self, x, y):
        th = self.th
        cx, cy = x * TILE + TILE // 2, y * TILE + TILE // 2
        rnd = random.Random(x * 13 + y * 101)
        blobs = [(cx + rnd.randint(-11, 11), cy + rnd.randint(-11, 9), rnd.randint(13, 18)) for _ in range(4)]
        for bx, by, br in blobs:
            pygame.draw.circle(self.bushes, (0, 0, 0, 70), (bx + 4, by + 6), br + 2)
        for bx, by, br in blobs:
            pygame.draw.circle(self.bushes, theme.darken(th["bush_dark"], 0.25), (bx, by), br + 1)
        # many small leaves with light from the top-left
        for _ in range(26 if self.quality == "high" else 12):
            bx, by, br = rnd.choice(blobs)
            a = rnd.uniform(0, 2 * math.pi)
            d = rnd.uniform(0, br - 3)
            lx, ly = bx + math.cos(a) * d, by + math.sin(a) * d
            shade = 0.25 * ((lx - cx) + (ly - cy)) / TILE
            c = theme.darken(th["bush"], max(0.0, shade)) if shade > 0 else theme.lighten(th["bush"], min(0.25, -shade))
            pygame.draw.circle(self.bushes, theme.darken(c, 0.3), (int(lx), int(ly) + 1), rnd.randint(4, 6))
            pygame.draw.circle(self.bushes, c, (int(lx), int(ly)), rnd.randint(3, 5))

    def redraw_dirty(self):
        tm = self.tm
        if not tm.dirty:
            return
        cells = set()
        for (x, y) in tm.dirty:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if tm.in_bounds(x + dx, y + dy):
                        cells.add((x + dx, y + dy))
        for (x, y) in sorted(cells, key=lambda c: (c[1], c[0])):
            self._floor(x, y)
        for (x, y) in sorted(cells | {(cx, cy + 1) for cx, cy in cells if tm.in_bounds(cx, cy + 1)},
                             key=lambda c: (c[1], c[0])):
            self._object(x, y)
        tm.dirty.clear()


# ---------------------------------------------------------------- particles
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max", "size", "color", "kind", "text", "grav")

    def __init__(self, x, y, vx, vy, life, size, color, kind="dot", txt=None, grav=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max = life
        self.size = size
        self.color = color
        self.kind = kind
        self.text = txt
        self.grav = grav


class Effects:
    def __init__(self, quality):
        self.p = []
        self.limit = {"low": 120, "medium": 320, "high": 700}.get(quality, 500)
        self.mult = {"low": 0.35, "medium": 0.7, "high": 1.0}.get(quality, 1.0)

    def burst(self, x, y, color, n=10, speed=160, size=4, life=0.45, grav=0.0, kind="dot"):
        n = max(1, int(n * self.mult))
        for _ in range(n):
            if len(self.p) >= self.limit:
                return
            a = random.uniform(0, 2 * math.pi)
            s = random.uniform(speed * 0.3, speed)
            self.p.append(Particle(x, y, math.cos(a) * s, math.sin(a) * s, random.uniform(life * 0.6, life),
                                   random.uniform(size * 0.6, size), color, kind, grav=grav))

    def ring(self, x, y, color, radius, life=0.35):
        self.p.append(Particle(x, y, 0, 0, life, radius, color, "ring"))

    def float_text(self, x, y, txt, color, size=20):
        self.p.append(Particle(x + random.uniform(-8, 8), y, 0, -70, 0.9, size, color, "text", txt))

    def update(self, dt):
        for q in self.p:
            q.life -= dt
            q.x += q.vx * dt
            q.y += q.vy * dt
            q.vy += q.grav * dt
            if q.kind != "text":
                q.vx *= (1 - 3 * dt)
                q.vy *= (1 - 3 * dt)
        self.p = [q for q in self.p if q.life > 0]

    def draw(self, surf, ox, oy):
        for q in self.p:
            f = q.life / q.max
            x, y = int(q.x - ox), int(q.y - oy)
            if q.kind == "ring":
                r = int(q.size * (1.15 - f * 0.6))
                if r > 2:
                    pygame.draw.circle(surf, q.color, (x, y), r, max(1, int(5 * f)))
            elif q.kind == "text":
                s = text.render(q.text, int(q.size), q.color, True, 2, rtl=False)
                if f < 0.4:
                    s = s.copy()
                    s.set_alpha(int(255 * f / 0.4))
                surf.blit(s, (x - s.get_width() // 2, y - s.get_height() // 2))
            elif q.kind == "spark":
                pygame.draw.line(surf, q.color, (x, y), (int(x - q.vx * 0.04), int(y - q.vy * 0.04)), max(1, int(q.size * f)))
            else:
                r = max(1, int(q.size * (0.4 + 0.6 * f)))
                pygame.draw.circle(surf, q.color, (x, y), r)


# ---------------------------------------------------------------- world renderer
_circle_cache = {}
_shadow_cache = {}


def shadow(surf, x, y, w, h, alpha=70):
    key = (int(w), int(h), alpha)
    s = _shadow_cache.get(key)
    if s is None:
        s = pygame.Surface((int(w), int(h)), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, alpha), s.get_rect())
        _shadow_cache[key] = s
    surf.blit(s, (int(x - w / 2), int(y - h / 2)))


def alpha_circle(radius, color, alpha, width=0):
    key = (int(radius), tuple(color[:3]), alpha, width)
    s = _circle_cache.get(key)
    if s is None:
        r = int(radius)
        s = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(s, tuple(color[:3]) + (alpha,), (r + 2, r + 2), r, width)
        if len(_circle_cache) > 200:
            _circle_cache.clear()
        _circle_cache[key] = s
    return s


class WorldRenderer:
    def __init__(self, world, themes, settings, i18n):
        self.world = world
        self.quality = settings["graphics"]
        self.settings = settings
        self.i18n = i18n
        self.mapr = MapRenderer(world.map, themes.get(world.map.theme), self.quality)
        self.fx = Effects(self.quality)
        self.cam_x = self.cam_y = 0.0
        self.shake = 0.0
        self.t = 0.0
        self.focus = world.player
        if world.player:
            self._snap(world.player.x, world.player.y)
        else:
            self._snap(world.map.pw / 2, world.map.ph / 2)

    # ------------------------------------------------------------ camera
    def _clamp(self, x, y):
        vw, vh = config.VIRTUAL_W, config.VIRTUAL_H
        tm = self.world.map
        if tm.pw <= vw:
            x = tm.pw / 2
        else:
            x = min(max(x, vw / 2), tm.pw - vw / 2)
        if tm.ph <= vh:
            y = tm.ph / 2
        else:
            y = min(max(y, vh / 2 - 40), tm.ph - vh / 2 + 20)
        return x, y

    def _snap(self, x, y):
        self.cam_x, self.cam_y = self._clamp(x, y)

    def screen_to_world(self, sx, sy):
        return sx + self.cam_x - config.VIRTUAL_W / 2, sy + self.cam_y - config.VIRTUAL_H / 2

    def world_to_screen(self, x, y):
        return x - self.cam_x + config.VIRTUAL_W / 2, y - self.cam_y + config.VIRTUAL_H / 2

    def update(self, dt, events, aim=None):
        self.t += dt
        w = self.world
        f = self.focus
        if f is None or not f.alive:
            # spectate a living teammate, then anyone
            team = w.player.team if w.player else None
            cands = [b for b in w.brawlers if b.alive and b.team == team] or [b for b in w.brawlers if b.alive]
            if w.player and w.player.alive:
                cands = [w.player]
            if cands:
                f = cands[0]
            if w.player and not w.player.alive and w.player.respawn_timer is not None:
                f = w.player
        if f is not None:
            tx, ty = f.x, f.y
            if aim and f is w.player and f.alive:
                tx += (aim[0] - f.x) * 0.15
                ty += (aim[1] - f.y) * 0.15
            tx, ty = self._clamp(tx, ty)
            k = min(1.0, dt * 6)
            self.cam_x += (tx - self.cam_x) * k
            self.cam_y += (ty - self.cam_y) * k
        self.shake = max(0.0, self.shake - dt * 30)
        self.fx.update(dt)
        self._consume(events)
        self.mapr.redraw_dirty()

    def _consume(self, events):
        w = self.world
        player = w.player
        for e in events:
            ev = e["ev"]
            if ev == "damage":
                tgt = e["target"]
                col = (255, 80, 80) if tgt is player else theme.WHITE
                if e["amount"] >= 1:
                    self.fx.float_text(e["x"], e["y"] - 40, str(e["amount"]), col, 18 if e["amount"] < 1000 else 22)
                self.fx.burst(e["x"], e["y"], (255, 255, 255), 4, 140, 3, 0.25)
                if tgt is player:
                    self.shake = max(self.shake, 5)
            elif ev == "heal" and e["amount"] >= 20:
                if random.random() < 0.35:
                    self.fx.float_text(e["x"], e["y"] - 44, "+" + str(e["amount"]), (110, 255, 140), 16)
                self.fx.burst(e["x"], e["y"], (120, 255, 150), 2, 60, 3, 0.4, -60)
            elif ev == "explosion":
                c = tuple(e.get("color") or (255, 160, 60))
                r = e["radius"]
                self.fx.ring(e["x"], e["y"], c, r)
                self.fx.burst(e["x"], e["y"], c, 18 if not e.get("small") else 10, r * 3, 7, 0.5)
                self.fx.burst(e["x"], e["y"], (90, 80, 90), 8, r * 1.5, 9, 0.7, -40)
                if self.focus and math.hypot(e["x"] - self.focus.x, e["y"] - self.focus.y) < 500:
                    self.shake = max(self.shake, 9 if e.get("big") else 5)
            elif ev == "death":
                v = e["victim"]
                c = tuple(v.style["body"])
                self.fx.burst(e["x"], e["y"], c, 26, 280, 7, 0.8)
                self.fx.burst(e["x"], e["y"], theme.WHITE, 10, 200, 4, 0.5, kind="spark")
                self.fx.ring(e["x"], e["y"], (255, 255, 255), 60, 0.4)
                self.shake = max(self.shake, 6)
            elif ev == "impact":
                self.fx.burst(e["x"], e["y"], tuple(e.get("color") or (255, 255, 255)), 5 if e.get("hit") else 3, 120, 3, 0.25)
            elif ev == "tile_break":
                col = self.mapr.th["crate"] if e["tile"] == "C" else (120, 130, 150) if e["tile"] == "P" else (196, 74, 60)
                self.fx.burst(e["x"], e["y"], col, 16, 240, 6, 0.6, 200)
            elif ev == "super":
                who = e["who"]
                self.fx.ring(who.x, who.y, theme.YELLOW, 70, 0.4)
                self.fx.burst(who.x, who.y, theme.YELLOW, 12, 200, 4, 0.4, kind="spark")
            elif ev == "blink":
                c = tuple(e.get("color") or (255, 100, 180))
                self.fx.burst(e["x0"], e["y0"], c, 14, 160, 5, 0.4)
                steps = 8
                for i in range(steps):
                    t = i / steps
                    self.fx.burst(e["x0"] + (e["x"] - e["x0"]) * t, e["y0"] + (e["y"] - e["y0"]) * t, c, 1, 30, 6, 0.35)
            elif ev == "ring":
                self.fx.ring(e["x"], e["y"], tuple(e.get("color") or (255, 255, 255)), e["radius"], 0.5)
            elif ev == "melee":
                c = tuple(e.get("color") or (255, 255, 255))
                a, arc, rng = e["angle"], e["arc"], e["range"]
                for i in range(7):
                    aa = a - arc / 2 + arc * i / 6
                    self.fx.p.append(Particle(e["x"] + math.cos(aa) * rng * 0.8, e["y"] + math.sin(aa) * rng * 0.8,
                                              math.cos(aa) * 60, math.sin(aa) * 60, 0.2, 7, c, "spark"))
            elif ev == "pickup":
                c = (190, 110, 255) if e["item"] == "gem" else (90, 255, 140) if e["item"] == "cube" else theme.WHITE
                self.fx.burst(e["x"], e["y"], c, 8, 120, 4, 0.4)
            elif ev == "goal":
                for _ in range(3):
                    self.fx.burst(self.world.orb.home[0], self.world.orb.home[1], theme.YELLOW, 20, 400, 6, 0.9)
            elif ev == "capture":
                self.fx.ring(e["x"], e["y"], config.TEAM_COLORS[e["team"]], TILE * 2.4, 0.6)
            elif ev == "respawn":
                self.fx.ring(e["x"], e["y"], theme.WHITE, 50, 0.4)
            elif ev == "dash":
                self.fx.burst(e["x"], e["y"], (230, 220, 200), 8, 100, 6, 0.4)
            elif ev == "wall":
                self.fx.burst(e["x"], e["y"], (150, 110, 70), 16, 200, 6, 0.5)
            elif ev == "shot" and not e.get("quiet"):
                c = tuple(e.get("color") or (255, 255, 255))
                self.fx.burst(e["x"] + math.cos(e["angle"]) * 18, e["y"] + math.sin(e["angle"]) * 18, c, 3, 90, 3, 0.15)
            elif ev == "destroyed":
                self.fx.burst(e["x"], e["y"], (160, 160, 180), 14, 200, 5, 0.5)

    # ------------------------------------------------------------ draw
    def draw(self, surf, aim=None, aim_super=False, show_attack_aim=False):
        w = self.world
        vw, vh = config.VIRTUAL_W, config.VIRTUAL_H
        sx = random.uniform(-self.shake, self.shake) if self.settings["screen_shake"] else 0
        sy = random.uniform(-self.shake, self.shake) if self.settings["screen_shake"] else 0
        ox = self.cam_x - vw / 2 + sx
        oy = self.cam_y - vh / 2 + sy
        surf.fill(self.mapr.th["border"])
        surf.blit(self.mapr.base, (-ox, -oy))
        tm = w.map
        pw, ph = tm.pw, tm.ph
        pygame.draw.rect(surf, INK, (-ox - 6, -oy - 6, pw + 12, ph + 12), 6, border_radius=6)
        self._draw_objectives(surf, ox, oy)
        # temporary walls
        for (tx, ty) in tm.temp_walls:
            r = pygame.Rect(tx * TILE - ox, ty * TILE - oy, TILE, TILE)
            top = r.move(0, -WALL_H)
            pygame.draw.rect(surf, (110, 80, 52), r)
            pygame.draw.rect(surf, (170, 128, 86), top)
            pygame.draw.rect(surf, INK, top.union(r), 3)
        for a in w.areas:
            self._draw_area(surf, a, ox, oy)
        for pk in w.pickups:
            self._draw_pickup(surf, pk, ox, oy)
        player = w.player
        my_team = player.team if player else 0
        # entities sorted by depth
        ents = [b for b in w.brawlers if b.alive] + list(w.deployables)
        ents.sort(key=lambda e: e.y)
        bushed = []
        for e in ents:
            if isinstance(e, Brawler):
                hidden = w.is_hidden_from(e, my_team)
                if hidden:
                    continue
                in_bush = tm.is_bush_at(e.x, e.y) or e.invis_t > 0
                if in_bush:
                    bushed.append(e)
                    continue
                self._draw_brawler(surf, e, ox, oy)
            else:
                self._draw_deployable(surf, e, ox, oy)
        if w.orb and not w.orb.carrier:
            self._draw_orb(surf, w.orb.x - ox, w.orb.y - oy)
        for p in w.projectiles:
            self._draw_projectile(surf, p, ox, oy)
        surf.blit(self.mapr.bushes, (-ox, -oy))
        for e in bushed:
            self._draw_brawler(surf, e, ox, oy, alpha=150)
        for e in ents:
            if isinstance(e, Brawler) and not w.is_hidden_from(e, my_team):
                self._draw_bars(surf, e, ox, oy)
            elif not isinstance(e, Brawler):
                self._draw_small_bar(surf, e, ox, oy)
        self.fx.draw(surf, ox, oy)
        if w.mode_id == "solo_survival":
            self._draw_poison(surf, ox, oy)
        if player and player.alive and aim is not None:
            self._draw_aim(surf, player, aim, aim_super, show_attack_aim, ox, oy)
        if self.quality != "low":
            from ilbrawl.engine.scene import vignette
            surf.blit(vignette((vw, vh), 120), (0, 0))

    def _draw_objectives(self, surf, ox, oy):
        w = self.world
        tm = w.map
        t = self.t
        if w.mode_id == "gem_collection":
            for (mx, my) in w.mode.mines:
                x, y = int(mx - ox), int(my - oy)
                pygame.draw.ellipse(surf, INK, (x - 34, y - 20, 68, 40))
                pygame.draw.ellipse(surf, (60, 30, 90), (x - 30, y - 17, 60, 34))
                glow = 0.5 + 0.5 * math.sin(t * 3)
                pygame.draw.ellipse(surf, theme.lerp_color((120, 60, 200), (200, 140, 255), glow), (x - 20, y - 10, 40, 20))
        if w.mode_id == "goal_rush":
            for key, team in (("A", 0), ("R", 1)):
                col = config.TEAM_COLORS[team]
                for (gx, gy) in tm.goals[key]:
                    r = pygame.Rect(gx * TILE - ox, gy * TILE - oy, TILE, TILE)
                    pygame.draw.rect(surf, theme.darken(col, 0.2), r)
                    for i in range(0, TILE, 12):
                        pygame.draw.line(surf, theme.lighten(col, 0.3), (r.x + i, r.y), (r.x, r.y + i), 2)
                tiles = list(tm.goals[key])
                if tiles:
                    ys = [g[1] for g in tiles]
                    xs = [g[0] for g in tiles]
                    rr = pygame.Rect(min(xs) * TILE - ox, min(ys) * TILE - oy, (max(xs) - min(xs) + 1) * TILE,
                                     (max(ys) - min(ys) + 1) * TILE)
                    pygame.draw.rect(surf, theme.WHITE, rr, 4)
            hx, hy = w.orb.home
            pygame.draw.circle(surf, theme.WHITE, (int(hx - ox), int(hy - oy)), 26, 3)
        if w.mode_id == "zone_control":
            for z in w.mode.zones:
                x, y = int(z.x - ox), int(z.y - oy)
                col = config.TEAM_COLORS[z.owner] if z.owner is not None else (230, 230, 230)
                surf.blit(alpha_circle(z.radius, col, 60), (x - z.radius - 2, y - z.radius - 2))
                pygame.draw.circle(surf, col, (x, y), int(z.radius), 4)
                if abs(z.cap) > 0.01:
                    ccol = config.TEAM_COLORS[0 if z.cap > 0 else 1]
                    ang = abs(z.cap) * 2 * math.pi
                    pygame.draw.arc(surf, ccol, (x - z.radius + 8, y - z.radius + 8, (z.radius - 8) * 2, (z.radius - 8) * 2),
                                    math.pi / 2, math.pi / 2 + ang, 8)
                if z.contested and int(t * 4) % 2 == 0:
                    pygame.draw.circle(surf, theme.WHITE, (x, y), int(z.radius) + 4, 2)
        if w.mode_id == "solo_survival":
            pass

    def _draw_area(self, surf, a, ox, oy):
        x, y = int(a.x - ox), int(a.y - oy)
        r = int(a.radius)
        pulse = 0.5 + 0.5 * math.sin(self.t * 6)
        alpha = int(60 + 30 * pulse)
        if a.kind == "rain":
            surf.blit(alpha_circle(r, (255, 120, 60), 40), (x - r - 2, y - r - 2))
            pygame.draw.circle(surf, (255, 140, 60), (x, y), r, 2)
            return
        surf.blit(alpha_circle(r, a.color, alpha), (x - r - 2, y - r - 2))
        pygame.draw.circle(surf, a.color, (x, y), r, 3)
        if a.kind == "pull":
            for i in range(4):
                ang = self.t * 5 + i * math.pi / 2
                rr = r * (0.3 + 0.6 * ((self.t * 1.5 + i * 0.25) % 1))
                pygame.draw.circle(surf, theme.WHITE, (int(x + math.cos(ang) * rr), int(y + math.sin(ang) * rr)), 4)
        elif a.kind == "heal_zone":
            for i in range(3):
                yy = y + r * 0.5 - ((self.t * 60 + i * 30) % (r))
                pygame.draw.line(surf, theme.WHITE, (x - 6 + i * 20 - 20, yy), (x + 6 + i * 20 - 20, yy), 3)
                pygame.draw.line(surf, theme.WHITE, (x + i * 20 - 20, yy - 6), (x + i * 20 - 20, yy + 6), 3)

    def _draw_pickup(self, surf, pk, ox, oy):
        x, y = pk.x - ox, pk.y - oy - 6 + math.sin(self.t * 4 + pk.x) * 3
        shadow(surf, x, pk.y - oy + 10, 20, 8)
        if pk.kind == "gem":
            theme.draw_gem_icon(surf, (x, y), 11, (184, 100, 255))
        else:
            r = pygame.Rect(0, 0, 18, 18)
            r.center = (int(x), int(y))
            pygame.draw.rect(surf, INK, r.inflate(4, 4), border_radius=4)
            pygame.draw.rect(surf, (90, 255, 140), r, border_radius=3)
            pygame.draw.rect(surf, (200, 255, 210), (r.x + 3, r.y + 3, 6, 6), border_radius=2)

    def _draw_orb(self, surf, x, y):
        x, y = int(x), int(y)
        shadow(surf, x, y + 14, 28, 8)
        glow = 0.5 + 0.5 * math.sin(self.t * 5)
        pygame.draw.circle(surf, INK, (x, y), 17)
        pygame.draw.circle(surf, theme.lerp_color((255, 220, 60), (255, 255, 200), glow), (x, y), 14)
        pygame.draw.circle(surf, theme.WHITE, (x - 5, y - 5), 4)

    def _draw_brawler(self, surf, b, ox, oy, alpha=255):
        w = self.world
        x, y = b.x - ox, b.y - oy
        my_team = w.player.team if w.player else 0
        team_col = config.TEAM_COLORS[0 if b.team == my_team else 1]
        # shadow + team ring
        shadow(surf, x, y + 17, 40, 14)
        ring = pygame.Rect(0, 0, 50, 20)
        ring.center = (int(x), int(y + 17))
        pygame.draw.ellipse(surf, team_col, ring, 4)
        if b.is_player:
            pygame.draw.ellipse(surf, theme.YELLOW, ring.inflate(8, 4), 2)
        moving = abs(b.vx) + abs(b.vy) > 20
        if b.dash is not None:
            for i in range(3):
                gx, gy = x - b.dash["dx"] * 18 * (i + 1), y - b.dash["dy"] * 18 * (i + 1)
                pygame.draw.circle(surf, theme.lighten(tuple(b.style["body"]), 0.4), (int(gx), int(gy)), 16 - i * 4)
        sprites.draw_brawler(surf, b.style, x, y - 6, 22, b.facing, self.t + b.id, b.walk_phase, moving,
                             b.hit_flash, b.attack_anim, alpha)
        if b.shield_t > 0:
            pygame.draw.circle(surf, (255, 170, 230), (int(x), int(y - 6)), 30, 3)
        if b.stun_t > 0:
            for i in range(3):
                a = self.t * 6 + i * 2.1
                theme.draw_star(surf, (x + math.cos(a) * 18, y - 40 + math.sin(a) * 5), 6)
        if b.rage_t > 0:
            pygame.draw.circle(surf, (255, 70, 70), (int(x), int(y - 6)), 28 + int(math.sin(self.t * 12) * 2), 2)
        if b.slow_t > 0:
            pygame.draw.circle(surf, (150, 220, 255), (int(x), int(y + 12)), 22, 2)
        if b.carrying_orb:
            self._draw_orb(surf, x, y - 62)
        if b.spawn_protect > 0 and int(self.t * 10) % 2 == 0:
            pygame.draw.circle(surf, theme.WHITE, (int(x), int(y - 6)), 30, 2)

    def _draw_deployable(self, surf, d, ox, oy):
        x, y = int(d.x - ox), int(d.y - oy)
        my_team = self.world.player.team if self.world.player else 0
        col = config.TEAM_COLORS[0 if d.team == my_team else 1]
        shadow(surf, x, y + 14, 36, 12)
        if d.kind == "decoy":
            pygame.draw.ellipse(surf, col, (x - 25, y + 7, 50, 20), 4)
            sprites.draw_brawler(surf, d.style, x, y - 6, 22, d.facing, self.t, 0, False, d.hit_flash, 0, 200)
            return
        if d.kind == "turret":
            base = pygame.Rect(x - 16, y - 8, 32, 22)
            pygame.draw.rect(surf, INK, base.inflate(4, 4), border_radius=6)
            pygame.draw.rect(surf, (120, 128, 150), base, border_radius=5)
            hx, hy = x + math.cos(d.facing) * 22, y - 8 + math.sin(d.facing) * 22
            pygame.draw.line(surf, INK, (x, y - 8), (hx, hy), 10)
            pygame.draw.line(surf, (80, 80, 96), (x, y - 8), (hx, hy), 6)
            pygame.draw.circle(surf, INK, (x, y - 10), 13)
            pygame.draw.circle(surf, tuple(d.spec.get("color", (255, 220, 60))), (x, y - 10), 10)
        else:
            pole = pygame.Rect(x - 7, y - 40, 14, 48)
            pygame.draw.rect(surf, INK, pole.inflate(4, 4), border_radius=5)
            pygame.draw.rect(surf, (140, 100, 60), pole, border_radius=4)
            glow = 0.5 + 0.5 * math.sin(self.t * 4)
            pygame.draw.circle(surf, INK, (x, y - 44), 14)
            pygame.draw.circle(surf, theme.lerp_color((120, 230, 110), (220, 255, 200), glow), (x, y - 44), 11)
            r = int(d.spec.get("heal_radius", 3) * TILE)
            pygame.draw.circle(surf, (140, 240, 120), (x, y), r, 2)
        pygame.draw.circle(surf, col, (x, y + 14), 6)

    def _draw_bars(self, surf, b, ox, oy):
        x, y = b.x - ox, b.y - oy
        w = self.world
        my_team = w.player.team if w.player else 0
        friendly = b.team == my_team
        bw = 60
        top = y - 60
        col = (90, 230, 110) if b.is_player else ((80, 170, 255) if friendly else (255, 80, 90))
        r = pygame.Rect(int(x - bw / 2), int(top), bw, 13)
        pygame.draw.rect(surf, INK, r.inflate(4, 4), border_radius=7)
        pygame.draw.rect(surf, (40, 28, 28), r, border_radius=6)
        fw = int(bw * b.hp_frac)
        if fw > 0:
            pygame.draw.rect(surf, col, (r.x, r.y, fw, r.h), border_radius=6)
        text.draw(surf, str(int(b.hp)), (x, top + 6), 11, theme.WHITE, "center", "middle", outline=2, rtl=False)
        text.draw(surf, b.name, (x, top - 3), 14, theme.lighten(col, 0.3), "center", "bottom", outline=2)
        if b.is_player:
            # ammo bars under the brawler
            n = b.ammo_max
            seg = 18
            total = n * seg + (n - 1) * 3
            ax = x - total / 2
            for i in range(n):
                fill = max(0.0, min(1.0, b.ammo - i))
                rr = pygame.Rect(int(ax + i * (seg + 3)), int(y + 26), seg, 6)
                pygame.draw.rect(surf, INK, rr.inflate(2, 2), border_radius=3)
                pygame.draw.rect(surf, (60, 40, 30), rr, border_radius=3)
                if fill > 0:
                    pygame.draw.rect(surf, (255, 160, 40) if fill >= 1 else (200, 120, 50),
                                     (rr.x, rr.y, int(seg * fill), rr.h), border_radius=3)
        if b.gems:
            theme.draw_gem_icon(surf, (x - 10, top - 30), 8, (184, 100, 255))
            text.draw(surf, str(b.gems), (x + 2, top - 30), 15, theme.WHITE, "left", "middle", rtl=False)
        if b.cubes:
            pygame.draw.rect(surf, (90, 255, 140), (x + bw / 2 + 4, top, 10, 10), border_radius=2)
            text.draw(surf, str(b.cubes), (x + bw / 2 + 16, top + 5), 13, theme.WHITE, "left", "middle", rtl=False)
        if b.super_ready and not b.is_player:
            pygame.draw.circle(surf, theme.YELLOW, (int(x + bw / 2 + 8), int(top - 6)), 5)

    def _draw_small_bar(self, surf, d, ox, oy):
        x, y = d.x - ox, d.y - oy
        r = pygame.Rect(int(x - 22), int(y - 62 if d.kind == "totem" else y - 40), 44, 6)
        pygame.draw.rect(surf, INK, r.inflate(2, 2), border_radius=3)
        pygame.draw.rect(surf, (200, 200, 220), (r.x, r.y, int(r.w * d.hp_frac), r.h), border_radius=3)

    def _draw_projectile(self, surf, p, ox, oy):
        x, y = p.x - ox, p.y - oy
        c = p.color
        r = max(3, int(p.radius))
        if p.lob is not None:
            L = p.lob
            t = min(1.0, L["t"])
            h = math.sin(t * math.pi) * L["h"]
            tx, ty = L["tx"] - ox, L["ty"] - oy
            er = int(p.explode_radius)
            pygame.draw.circle(surf, theme.lighten(c, 0.2), (int(tx), int(ty)), er, 2)
            shadow(surf, x, y, r * 2, r * 0.8)
            yy = y - h
            pygame.draw.circle(surf, INK, (int(x), int(yy)), r + 3)
            pygame.draw.circle(surf, c, (int(x), int(yy)), r)
            pygame.draw.circle(surf, theme.lighten(c, 0.5), (int(x - r * 0.35), int(yy - r * 0.35)), max(1, r // 3))
            if p.shape == "meteor":
                for i in range(3):
                    pygame.draw.circle(surf, (255, 200, 80), (int(x - p.vx * 0.02 * i), int(yy + 6 * i)), max(2, r - 4 * i))
            return
        ang = math.atan2(p.vy, p.vx)
        dx, dy = math.cos(ang), math.sin(ang)
        shape = p.shape
        if shape in ("bolt", "beam"):
            ln = 26 if shape == "bolt" else 46
            pygame.draw.line(surf, INK, (x - dx * ln, y - dy * ln), (x, y), r + 4)
            pygame.draw.line(surf, c, (x - dx * ln, y - dy * ln), (x, y), r)
            pygame.draw.line(surf, theme.WHITE, (x - dx * ln * 0.6, y - dy * ln * 0.6), (x, y), max(1, r // 2))
        elif shape in ("wave", "ring", "shock"):
            px, py = -dy, dx
            rr = p.radius
            pts = [(x + px * rr, y + py * rr), (x + dx * rr * 0.5, y + dy * rr * 0.5), (x - px * rr, y - py * rr)]
            pygame.draw.lines(surf, INK, False, pts, 9)
            pygame.draw.lines(surf, c, False, pts, 5)
            if shape == "shock":
                pygame.draw.lines(surf, theme.WHITE, False, pts, 2)
        elif shape == "flame":
            f = 1 - min(1.0, p.travelled / max(1, p.max_range))
            rr = int(r * (0.6 + 0.8 * (1 - f)))
            pygame.draw.circle(surf, (255, 90, 30), (int(x), int(y)), rr + 2)
            pygame.draw.circle(surf, c, (int(x), int(y)), rr)
            pygame.draw.circle(surf, (255, 240, 160), (int(x), int(y)), max(1, rr // 2))
        elif shape == "blade":
            a = p.age * 20
            pts = [(x + math.cos(a + i * math.pi / 2) * r * (1.6 if i % 2 == 0 else 0.6),
                    y + math.sin(a + i * math.pi / 2) * r * (1.6 if i % 2 == 0 else 0.6)) for i in range(4)]
            pygame.draw.polygon(surf, INK, pts, 0)
            pygame.draw.polygon(surf, c, [(px * 0.85 + x * 0.15, py * 0.85 + y * 0.15) for px, py in pts])
        elif shape == "star":
            theme.draw_star(surf, (x, y), r + 3, c)
        else:  # pellet / orb
            pygame.draw.circle(surf, INK, (int(x), int(y)), r + 3)
            pygame.draw.circle(surf, c, (int(x), int(y)), r)
            pygame.draw.circle(surf, theme.WHITE, (int(x - r * 0.3), int(y - r * 0.3)), max(1, r // 3))

    def _draw_poison(self, surf, ox, oy):
        s = self.world.mode.safe
        tm = self.world.map
        if s[0] <= 1 and s[1] <= 1:
            return
        vw, vh = config.VIRTUAL_W, config.VIRTUAL_H
        overlay = pygame.Surface((vw, vh), pygame.SRCALPHA)
        overlay.fill((70, 200, 90, 90))
        hole = pygame.Rect(int(s[0] - ox), int(s[1] - oy), int(s[2] - s[0]), int(s[3] - s[1]))
        overlay.fill((0, 0, 0, 0), hole)
        surf.blit(overlay, (0, 0))
        pygame.draw.rect(surf, (60, 160, 70), hole, 4)
        for i in range(14):
            bx = (i * 173 + self.t * 40) % vw
            by = (i * 97 + self.t * 25) % vh
            if not hole.collidepoint(bx, by):
                pygame.draw.circle(surf, (150, 255, 160), (int(bx), int(by)), 6 + i % 5, 2)

    def _draw_aim(self, surf, b, aim, aim_super, strong, ox, oy):
        x, y = b.x - ox, b.y - oy
        ax, ay = aim[0] - ox, aim[1] - oy
        ang = math.atan2(ay - y, ax - x)
        if aim_super:
            s = b.sup
            from ilbrawl.abilities.supers import super_range_tiles
            rng = super_range_tiles(s) * TILE
            col = (255, 214, 60)
            st = s["type"]
            if st in ("heal_zone", "slow_field", "pull", "meteor", "rain", "blink", "turret", "heal_totem", "decoy", "wall"):
                d = min(rng, math.hypot(ax - x, ay - y))
                tx, ty = x + math.cos(ang) * d, y + math.sin(ang) * d
                rad = s.get("radius", s.get("explode_radius", s.get("spread", 1.2)))
                rad = int(rad * TILE) if rad < 20 else int(rad)
                surf.blit(alpha_circle(max(16, rad), col, 70), (tx - max(16, rad) - 2, ty - max(16, rad) - 2))
                pygame.draw.circle(surf, col, (int(tx), int(ty)), max(16, rad), 3)
                pygame.draw.circle(surf, col, (int(x), int(y)), int(rng), 1)
            elif st in ("shield_aura", "nova_ring", "stealth", "rage"):
                pygame.draw.circle(surf, col, (int(x), int(y)), int(rng), 3)
            else:
                self._aim_cone(surf, x, y, ang, rng, s.get("radius", 14) * 1.2, col)
            return
        a = b.attack
        rng = b.attack_range_px
        alpha_col = (255, 255, 255)
        t = a["type"]
        if t == "lob":
            d = min(rng, math.hypot(ax - x, ay - y))
            tx, ty = x + math.cos(ang) * d, y + math.sin(ang) * d
            rad = int(a.get("explode_radius", 1.2) * TILE)
            pygame.draw.circle(surf, alpha_col, (int(tx), int(ty)), rad, 2 if not strong else 3)
            for i in range(1, 8):
                f = i / 8
                hx = x + (tx - x) * f
                hy = y + (ty - y) * f - math.sin(f * math.pi) * 40
                pygame.draw.circle(surf, alpha_col, (int(hx), int(hy)), 2)
        elif t == "melee":
            arc = math.radians(a.get("arc", 100))
            pts = [(x, y)] + [(x + math.cos(ang - arc / 2 + arc * i / 10) * rng, y + math.sin(ang - arc / 2 + arc * i / 10) * rng)
                              for i in range(11)]
            pygame.draw.lines(surf, alpha_col, True, pts, 2)
        elif t in ("spread", "flame"):
            sp = math.radians(a.get("spread", 20)) / 2
            pts = [(x, y), (x + math.cos(ang - sp) * rng, y + math.sin(ang - sp) * rng),
                   (x + math.cos(ang + sp) * rng, y + math.sin(ang + sp) * rng)]
            pygame.draw.lines(surf, alpha_col, True, pts, 2)
        else:
            self._aim_cone(surf, x, y, ang, rng, a.get("radius", 8), alpha_col, strong)

    @staticmethod
    def _aim_cone(surf, x, y, ang, rng, width, col, strong=False):
        dx, dy = math.cos(ang), math.sin(ang)
        px, py = -dy * width, dx * width
        ex, ey = x + dx * rng, y + dy * rng
        pts = [(x + px, y + py), (ex + px, ey + py), (ex - px, ey - py), (x - px, y - py)]
        pygame.draw.lines(surf, col, True, pts, 3 if strong else 2)
