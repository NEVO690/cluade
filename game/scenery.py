"""City scenery: buildings, street decor, tunnels, bridges, stations, sky.

Everything is generated procedurally from the zone description in
``data/zones.json`` and drawn with the depth-sorted renderer.
"""
import math
import random

import pygame

from . import settings as S
from .render import draw_poly
from .utils import shade, lerp_color, to_color

AD_TEXTS = ["PIXEL PIZZA", "ZIP SODA", "NOVA TECH", "BYTE BURGER", "LUNA CAFE", "HYPER GYM", "METRO LINE 7",
            "RUN THE CITY", "FRESH JUICE", "SKY MART", "TURBO TAXI", "CLOUD BANK"]
NEON_TEXTS = ["OPEN", "HOTEL", "RAMEN", "ARCADE", "24/7", "CLUB", "SYNTH", "NOODLE", "GAMES", "BAR"]
NEON_COLORS = [(255, 40, 200), (0, 240, 255), (180, 80, 255), (255, 220, 40), (60, 255, 140)]
STATION_NAMES = ["CENTRAL", "PARK AVE", "RIVERSIDE", "UNION SQ", "NORTH GATE", "MARKET ST"]


# ---------------------------------------------------------------------------
# Sprite factory (pre-rendered billboards)
# ---------------------------------------------------------------------------
class SpriteBank:
    def __init__(self, assets):
        self.assets = assets
        self._cache = {}

    def get(self, key):
        s = self._cache.get(key)
        if s is None:
            s = self._make(key)
            self._cache[key] = s
        return s

    def _make(self, key):
        kind = key[0]
        if kind == "tree":
            color = key[1]
            s = pygame.Surface((120, 140), pygame.SRCALPHA)
            dark = shade(color, 0.7)
            for cx, cy, r, c in ((60, 70, 52, dark), (38, 62, 34, color), (82, 60, 34, color), (60, 40, 36, shade(color, 1.15)),
                                 (60, 82, 30, color)):
                pygame.draw.circle(s, c, (cx, cy), r)
            return s
        if kind == "ad":
            text, bg, fg = key[1], key[2], key[3]
            s = pygame.Surface((320, 140))
            s.fill(bg)
            pygame.draw.rect(s, fg, (0, 0, 320, 140), 8)
            pygame.draw.circle(s, shade(bg, 1.3), (270, 40), 50)
            t = self.assets.font(44).render(text, True, fg)
            if t.get_width() > 290:
                t = pygame.transform.smoothscale(t, (290, t.get_height()))
            s.blit(t, (160 - t.get_width() // 2, 70 - t.get_height() // 2))
            return s
        if kind == "neon":
            text, color = key[1], key[2]
            t = self.assets.font(48).render(text, True, (255, 255, 255))
            w, h = t.get_width() + 40, t.get_height() + 30
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(s, (20, 10, 30, 220), (0, 0, w, h), border_radius=12)
            pygame.draw.rect(s, (*color, 255), (0, 0, w, h), 5, border_radius=12)
            glow = self.assets.font(48).render(text, True, color)
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                s.blit(glow, (20 + dx, 15 + dy))
            s.blit(t, (20, 15))
            return s
        if kind == "station":
            text = key[1]
            t = self.assets.font(40).render(text, True, (255, 255, 255))
            w, h = t.get_width() + 80, 70
            s = pygame.Surface((w, h))
            s.fill((30, 60, 140))
            pygame.draw.rect(s, (255, 255, 255), (0, 0, w, h), 4)
            pygame.draw.circle(s, (230, 50, 50), (36, 35), 22)
            m = self.assets.font(30).render("M", True, (255, 255, 255))
            s.blit(m, (36 - m.get_width() // 2, 35 - m.get_height() // 2))
            s.blit(t, (66, 35 - t.get_height() // 2))
            return s
        if kind == "bridge_sign":
            text = key[1]
            t = self.assets.font(36).render(text, True, (255, 255, 255))
            s = pygame.Surface((t.get_width() + 40, 56))
            s.fill((20, 110, 60))
            pygame.draw.rect(s, (255, 255, 255), s.get_rect(), 3)
            s.blit(t, (20, 28 - t.get_height() // 2))
            return s
        if kind == "pumpkin":
            s = pygame.Surface((100, 90), pygame.SRCALPHA)
            for dx in (-22, 22, 0):
                pygame.draw.ellipse(s, (240, 120, 10) if dx else (255, 140, 20), (28 + dx, 22, 44, 62))
            pygame.draw.rect(s, (60, 110, 30), (46, 8, 8, 18))
            for ex in (36, 64):
                pygame.draw.polygon(s, (255, 230, 80), [(ex - 7, 50), (ex + 7, 50), (ex, 38)])
            pygame.draw.polygon(s, (255, 230, 80), [(32, 62), (68, 62), (60, 72), (50, 66), (40, 72)])
            return s
        if kind == "snowman":
            s = pygame.Surface((80, 130), pygame.SRCALPHA)
            for cy, r in ((98, 30), (58, 22), (26, 16)):
                pygame.draw.circle(s, (245, 248, 255), (40, cy), r)
            pygame.draw.rect(s, (30, 30, 40), (26, 0, 28, 14))
            pygame.draw.rect(s, (30, 30, 40), (20, 12, 40, 5))
            pygame.draw.polygon(s, (255, 130, 30), [(40, 26), (40, 31), (58, 29)])
            pygame.draw.rect(s, (220, 40, 40), (22, 40, 36, 7))
            return s
        if kind == "umbrella":
            s = pygame.Surface((120, 130), pygame.SRCALPHA)
            pygame.draw.rect(s, (230, 230, 230), (58, 30, 5, 100))
            cols = [(255, 80, 80), (255, 255, 255)]
            for i in range(6):
                a0 = math.pi + i * math.pi / 6
                a1 = a0 + math.pi / 6
                pygame.draw.polygon(s, cols[i % 2], [(60, 40), (60 + math.cos(a0) * 58, 40 + math.sin(a0) * 34),
                                                     (60 + math.cos(a1) * 58, 40 + math.sin(a1) * 34)])
            return s
        if kind == "flags":
            s = pygame.Surface((300, 60), pygame.SRCALPHA)
            pygame.draw.arc(s, (240, 240, 240), (0, -40, 300, 80), math.pi, math.tau, 3)
            pts = [(i * 30 + 15) for i in range(10)]
            cols = [(255, 80, 160), (255, 220, 40), (60, 200, 255), (120, 230, 80), (180, 100, 255)]
            for i, x in enumerate(pts):
                yy = 4 + int(36 * math.sin(math.pi * x / 300))
                pygame.draw.polygon(s, cols[i % len(cols)], [(x - 11, yy), (x + 11, yy), (x, yy + 22)])
            return s
        s = pygame.Surface((16, 16), pygame.SRCALPHA)
        s.fill((255, 0, 255))
        return s


# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------
class Building:
    __slots__ = ("x0", "x1", "z0", "z1", "h", "color", "style", "side", "rows", "lit", "window", "window_lit",
                 "roof_item", "neon", "stack", "awning", "shop", "cols")

    def __init__(self, side, x0, x1, z0, z1, h, color, style, zone, rnd):
        self.side = side
        self.x0, self.x1, self.z0, self.z1, self.h = x0, x1, z0, z1, h
        self.color = color
        self.style = style
        b = zone["buildings"]
        self.window = b["window"]
        self.window_lit = b["window_lit"]
        floor_h = 3.4 if style != "warehouse" else 5.0
        self.rows = max(1, min(12, int(h / floor_h)))
        lit_chance = b["lit_chance"] + (0.35 if zone.get("night") else 0)
        self.lit = [rnd.random() < lit_chance for _ in range(self.rows)]
        self.roof_item = rnd.choice([None, "tank", "ac", "antenna"]) if style in ("office", "tower", "brick") else None
        self.neon = rnd.choice(NEON_COLORS) if style == "neon" else None
        self.stack = []
        self.shop = style in ("office", "brick", "house", "tower", "neon") and rnd.random() < 0.75
        self.awning = rnd.choice(AWNINGS) if self.shop and rnd.random() < 0.7 else None
        c = color
        aw = self.awning or (0, 0, 0)
        # every colour this building needs, computed once instead of every frame
        self.cols = {"side": shade(c, 0.78), "top": shade(c, 1.12), "cornice": shade(c, 0.82),
                     "cornice_side": shade(c, 0.7), "cornice_top": shade(c, 0.95), "aw_side": shade(aw, 0.75),
                     "aw_top": shade(aw, 1.15), "aw_bottom": shade(aw, 0.6)}
        if style == "container":
            pal = b["palette"]
            levels = rnd.randint(1, 3)
            for i in range(levels):
                self.stack.append(rnd.choice(pal))
            self.h = levels * 2.6

    def queue(self, r, quality, night):
        if not r.visible_range(self.z0, self.z1):
            return
        if self.style == "container":
            for i, col in enumerate(self.stack):
                y0 = i * 2.6
                r.box(self.x0, self.x1, y0, y0 + 2.5, self.z0, self.z1, col, shade(col, 0.75), shade(col, 1.12),
                      detail=_container_ridges(col), bias=-i * 0.001)
            return
        c = self.color
        windows = quality.get("windows", True)
        cols = self.cols
        r.box(self.x0, self.x1, 0, self.h, self.z0, self.z1, c, cols["side"], cols["top"],
              detail=self._detail if windows else self._detail_simple)
        if windows and self.z0 - r.cam.z < r.draw_distance * 0.6:
            self._queue_street_level(r, night)
        if self.roof_item and windows:
            cx = (self.x0 + self.x1) / 2
            cz = self.z0 + 2.5
            if self.roof_item == "tank":
                r.box(cx - 1.2, cx + 1.2, self.h, self.h + 2.4, cz, cz + 2.2, (120, 90, 70), (90, 70, 55), (140, 110, 90), bias=-0.05)
            elif self.roof_item == "ac":
                r.box(cx - 2, cx + 1, self.h, self.h + 1.2, cz, cz + 2.5, (170, 170, 175), (130, 130, 135), (200, 200, 205), bias=-0.05)
            elif self.roof_item == "antenna" and self.h > 20:
                r.box(cx - 0.12, cx + 0.12, self.h, self.h + 6, cz, cz + 0.24, (200, 200, 210), (150, 150, 160), None, bias=-0.05)
                if night or self.style == "tower":
                    r.glow(cx, self.h + 6, cz, 1.2, (255, 60, 60))
        if self.neon and r.glow_enabled:
            # vertical neon strip on the corner facing the track
            xs = self.x0 if self.side > 0 else self.x1
            r.glow(xs, self.h * 0.6, self.z0 - 0.2, 3.0, shade(self.neon, 0.45))

    def _queue_street_level(self, r, night):
        """Shop window, awning and roof cornice on the facade facing the tracks."""
        cols = self.cols
        face = self.x0 if self.side > 0 else self.x1
        out = -self.side  # towards the tracks
        if self.shop:
            glass = (255, 214, 140) if night else (70, 100, 125)
            xa, xb = sorted((face, face + out * 0.06))
            r.box(xa, xb, 0.2, 2.7, self.z0 + 0.7, self.z1 - 0.7, glass, glass, None, bias=-0.71)
            if night and r.glow_enabled:
                r.glow(face + out * 0.3, 1.4, (self.z0 + self.z1) / 2, 2.4, (90, 70, 40))
        if self.awning:
            xa, xb = sorted((face, face + out * 1.3))
            aw = self.awning
            r.box(xa, xb, 2.85, 3.15, self.z0 + 0.5, self.z1 - 0.5, aw, cols["aw_side"], cols["aw_top"],
                  cols["aw_bottom"], bias=-0.52, detail=_awning_stripes)
        r.box(self.x0 - 0.25, self.x1 + 0.25, self.h, self.h + 0.55, self.z0 - 0.25, self.z1 + 0.25,
              cols["cornice"], cols["cornice_side"], cols["cornice_top"], bias=-0.001)

    def _rows_geom(self):
        h = self.h
        rows = self.rows
        band = h / rows
        for i in range(rows):
            y_a = i * band + band * 0.3
            y_b = i * band + band * 0.78
            floor = 3.5 if self.shop else 1.2
            if y_a < floor:
                y_a = floor
            if y_b <= y_a:
                continue
            yield i, y_a, y_b

    def _detail_simple(self, r, fr, br, d0, d1, clipped):
        pass

    def _detail(self, r, fr, br, d0, d1, clipped):
        surf = r.surface
        h = self.h
        ax0, ay1, ax1, ay0 = fr
        bx0, by1, bx1, by0 = br
        win = self.window
        lit = self.window_lit if self.neon is None else self.neon
        fw = ax1 - ax0
        # front face windows (screen aligned -> cheap fills)
        if not clipped and fw > 10:
            fh = ay0 - ay1
            cols = max(1, min(6, int((self.x1 - self.x0) / 3)))
            cw = fw / cols
            colw = r.fog(win, d0)
            coll = r.fog(lit, d0)
            for i, y_a, y_b in self._rows_geom():
                ty = ay0 - fh * (y_b / h)
                hh = fh * (y_b - y_a) / h
                if hh < 1:
                    continue
                c = coll if self.lit[i] else colw
                if self.style in ("office", "tower", "neon"):
                    surf.fill(c, (ax0 + fw * 0.06, ty, fw * 0.88, hh))
                else:
                    for k in range(cols):
                        surf.fill(c, (ax0 + k * cw + cw * 0.22, ty, cw * 0.56, hh))
        # side face (towards the track)
        cam = r.cam
        if cam.x < self.x0:
            fx, bx = ax0, bx0
        elif cam.x > self.x1:
            fx, bx = ax1, bx1
        else:
            return
        dm = (d0 + d1) * 0.5
        colw = r.fog(win, dm)
        coll = r.fog(lit, dm)
        fy0, fy1, by0_, by1_ = ay0, ay1, by0, by1
        poly = draw_poly
        individual = self.style in ("brick", "house", "warehouse") and d0 < 60
        for i, y_a, y_b in self._rows_geom():
            ta, tb = y_a / h, y_b / h
            f_a = fy0 + (fy1 - fy0) * ta
            f_b = fy0 + (fy1 - fy0) * tb
            b_a = by0_ + (by1_ - by0_) * ta
            b_b = by0_ + (by1_ - by0_) * tb
            c = coll if self.lit[i] else colw
            if not individual:
                poly(surf, c, ((fx, f_a), (fx, f_b), (bx, b_b), (bx, b_a)))
            else:
                n = max(1, min(6, int((self.z1 - max(self.z0, cam.z + S.NEAR_PLANE)) / 3.2)))
                for k in range(n):
                    t0 = (k + 0.25) / n
                    t1 = (k + 0.75) / n
                    # interpolate along the (projected) edge - perspective-correct enough at this size
                    ux0 = fx + (bx - fx) * _persp(t0, d0, d1)
                    ux1 = fx + (bx - fx) * _persp(t1, d0, d1)
                    ka, kb = _persp(t0, d0, d1), _persp(t1, d0, d1)
                    poly(surf, c, ((ux0, f_a + (b_a - f_a) * ka), (ux0, f_b + (b_b - f_b) * ka),
                                   (ux1, f_b + (b_b - f_b) * kb), (ux1, f_a + (b_a - f_a) * kb)))


AWNINGS = [(200, 50, 50), (40, 130, 90), (40, 90, 170), (230, 160, 30), (150, 60, 140), (230, 230, 230)]


def _awning_stripes(r, fr, br, d0, d1, clipped):
    ax0, ay1, ax1, ay0 = fr
    w = ax1 - ax0
    if w < 8 or clipped:
        return
    col = r.fog((250, 250, 250), d0)
    seg = w / 6
    for i in range(0, 6, 2):
        r.surface.fill(col, (ax0 + i * seg, ay1, seg, ay0 - ay1))


def _persp(t, d0, d1):
    """Screen-space fraction for a world-space fraction t along a face spanning depths d0..d1."""
    z = d0 + (d1 - d0) * t
    return (1 / d0 - 1 / z) / (1 / d0 - 1 / d1) if d1 != d0 else t


def _container_ridges(col):
    dark = shade(col, 0.65)

    def detail(r, fr, br, d0, d1, clipped):
        ax0, ay1, ax1, ay0 = fr
        w = ax1 - ax0
        if w < 12 or clipped:
            return
        cc = r.fog(dark, d0)
        lw = max(1, int(w * 0.02))
        for i in range(1, 10):
            x = ax0 + w * i / 10
            pygame.draw.line(r.surface, cc, (x, ay1 + 2), (x, ay0 - 2), lw)
    return detail


# ---------------------------------------------------------------------------
# Street decor
# ---------------------------------------------------------------------------
class Decor:
    __slots__ = ("kind", "x", "z", "data")

    def __init__(self, kind, x, z, data=None):
        self.kind = kind
        self.x = x
        self.z = z
        self.data = data

    def queue(self, r, sprites, night, zone):
        k = self.kind
        x, z = self.x, self.z
        z_end = self.data if self.kind == "fence" else z + 2
        if not r.visible_range(z - 2, z_end):
            return
        if k == "fence":
            z1 = self.data
            col = (110, 115, 125)
            r.box(x - 0.08, x + 0.08, 0, 1.15, z, z1, col, shade(col, 0.75), shade(col, 1.2), detail=None)
            r.box(x - 0.12, x + 0.12, 1.05, 1.2, z, z1, shade(col, 1.15), shade(col, 0.9), shade(col, 1.3), bias=-0.001)
        elif k == "lamp":
            r.box(x - 0.1, x + 0.1, 0, 6.0, z, z + 0.2, (70, 72, 80), (50, 52, 60), None)
            arm_dir = -1 if x > 0 else 1
            ax = x + arm_dir * 1.2
            r.box(min(x, ax), max(x, ax), 5.8, 6.0, z, z + 0.2, (70, 72, 80), (50, 52, 60), (90, 92, 100), bias=-0.01)
            r.box(ax - 0.3, ax + 0.3, 5.6, 5.85, z - 0.1, z + 0.3, (255, 245, 210), (200, 190, 160), None, bias=-0.02)
            if night or zone.get("id") in ("metro",):
                r.glow(ax, 5.4, z, 3.2, (150, 130, 80))
        elif k == "tree":
            r.box(x - 0.2, x + 0.2, 0, 2.4, z, z + 0.4, (100, 70, 45), (80, 55, 35), None)
            r.queue(z + 0.18, _draw_canopy, r, x, z + 0.2, self.data)
        elif k == "billboard":
            text, bg, fg = self.data
            px = x + (0.9 if x > 0 else -0.9)
            r.box(px - 0.12, px + 0.12, 0, 4.5, z + 0.1, z + 0.3, (90, 90, 100), (60, 60, 70), None, bias=0.02)
            ad = sprites.get(("ad", text, bg, fg))
            r.box(x - 2.3, x + 2.3, 4.2, 6.2, z - 0.1, z + 0.1, bg, shade(bg, 0.6), shade(bg, 1.1),
                  detail=_sign_detail(ad, 1.0, fit=True))
            if night:
                r.glow(x, 5.2, z - 0.2, 2.4, shade(bg, 0.4))
        elif k == "bench":
            r.box(x - 0.8, x + 0.8, 0.4, 0.55, z, z + 0.5, (140, 90, 50), (110, 70, 40), (170, 110, 60))
            r.box(x - 0.7, x + 0.7, 0, 0.4, z + 0.1, z + 0.4, (60, 60, 65), (40, 40, 45), None, bias=0.01)
        elif k == "barrels":
            for i, dx in enumerate((-0.5, 0.5)):
                c = (60, 110, 160) if i == 0 else (200, 70, 50)
                r.box(x + dx - 0.35, x + dx + 0.35, 0, 1.1, z, z + 0.7, c, shade(c, 0.7), shade(c, 1.2))
        elif k == "chimney":
            r.box(x - 1.2, x + 1.2, 0, 26, z, z + 2.4, (150, 80, 60), (120, 64, 48), (90, 50, 40),
                  detail=_chimney_stripes())
        elif k == "crane":
            col = (230, 170, 40)
            r.box(x - 0.6, x + 0.6, 0, 24, z, z + 1.2, col, shade(col, 0.75), None)
            arm_dir = -1 if x > 0 else 1
            x2 = x + arm_dir * 14
            r.box(min(x, x2), max(x, x2), 22.5, 23.8, z, z + 1.2, col, shade(col, 0.75), shade(col, 1.1), bias=-0.01)
            r.box(x - 1.5, x + 1.5, 20, 23, z - 0.5, z + 1.7, (200, 200, 205), (150, 150, 155), (220, 220, 225), bias=-0.02)
        elif k == "bollard":
            r.box(x - 0.18, x + 0.18, 0, 0.8, z, z + 0.36, (60, 60, 70), (40, 40, 50), (90, 90, 100))
        elif k == "neon_sign":
            text, color = self.data
            r.billboard(("neon", text, color), sprites.get(("neon", text, color)), x, 6.0, z, 1.8)
            r.glow(x, 6.9, z - 0.1, 3.6, shade(color, 0.45))
        elif k in ("pumpkin", "snowman", "umbrella"):
            hgt = {"pumpkin": 0.9, "snowman": 1.8, "umbrella": 2.6}[k]
            r.billboard((k,), sprites.get((k,)), x, 0, z, hgt)
            if k == "pumpkin" and r.glow_enabled:
                r.glow(x, 0.5, z - 0.1, 1.2, (120, 60, 0))
        elif k == "flags":
            r.billboard(("flags",), sprites.get(("flags",)), x, 5.0, z, 1.2)


def _draw_canopy(r, x, z, color):
    """Tree canopy drawn as a few projected circles (cheaper than scaling a sprite)."""
    cam = r.cam
    dz = z - cam.z
    if dz < S.NEAR_PLANE:
        return
    s = cam.focal / dz
    cx = cam.hx + (x - cam.x) * s
    cy = cam.hy - (3.4 - cam.y) * s
    rad = 1.5 * s
    if rad < 1:
        return
    surf = r.surface
    if cx + rad * 1.6 < 0 or cx - rad * 1.6 > surf.get_width():
        return
    dark = r.fog(shade(color, 0.7), dz)
    mid = r.fog(color, dz)
    light = r.fog(shade(color, 1.18), dz)
    circle = pygame.draw.circle
    circle(surf, dark, (int(cx), int(cy)), max(1, int(rad)))
    circle(surf, mid, (int(cx - rad * 0.45), int(cy + rad * 0.1)), max(1, int(rad * 0.66)))
    circle(surf, mid, (int(cx + rad * 0.45), int(cy - rad * 0.05)), max(1, int(rad * 0.66)))
    circle(surf, light, (int(cx), int(cy - rad * 0.45)), max(1, int(rad * 0.6)))


def _chimney_stripes():
    def detail(r, fr, br, d0, d1, clipped):
        ax0, ay1, ax1, ay0 = fr
        w, h = ax1 - ax0, ay0 - ay1
        if w < 3:
            return
        c = r.fog((240, 240, 240), d0)
        r.surface.fill(c, (ax0, ay1 + h * 0.04, w, h * 0.05))
        r.surface.fill(c, (ax0, ay1 + h * 0.14, w, h * 0.05))
    return detail


# ---------------------------------------------------------------------------
# Big structures
# ---------------------------------------------------------------------------
class Structure:
    __slots__ = ("kind", "z0", "z1", "data")

    def __init__(self, kind, z0, z1, data=None):
        self.kind = kind
        self.z0 = z0
        self.z1 = z1
        self.data = data

    def queue(self, r, sprites, night, zone):
        if not r.visible_range(self.z0, self.z1):
            return
        k = self.kind
        if k == "tunnel":
            # Roof at 8 m: high enough for train-roof running; hidden while the camera is
            # above it (Jet Boost) so it never fills the screen.
            wall = (92, 88, 86)
            inner = (70, 66, 64)
            roof = (60, 58, 58)
            z = self.z0
            while z < self.z1:
                z2 = min(self.z1, z + 10)
                r.layer = 0
                r.box(-S.SIDEWALK_HALF - 2, -S.ROAD_HALF - 0.3, 0, 8.2, z, z2, wall, inner, None, bias=-0.001)
                r.box(S.ROAD_HALF + 0.3, S.SIDEWALK_HALF + 2, 0, 8.2, z, z2, wall, inner, None, bias=-0.001)
                for sx in (-S.ROAD_HALF - 0.25, S.ROAD_HALF + 0.25):
                    r.glow(sx, 6.0, z + 5, 1.6, (170, 150, 90))
                r.layer = 1
                r.box(-S.SIDEWALK_HALF - 2, S.SIDEWALK_HALF + 2, 8.0, 9.2, z, z2, wall, None, (110, 108, 104), roof,
                      bias=-0.002, overhead=True)
                z = z2
            if self.data and self.data.get("portal"):
                # entrance facade with the tunnel name
                pc = (130, 120, 112)
                r.layer = 0
                r.box(-26, -S.ROAD_HALF - 0.3, 0, 13, self.z0 - 1.5, self.z0, pc, shade(pc, 0.75), shade(pc, 1.1))
                r.box(S.ROAD_HALF + 0.3, 26, 0, 13, self.z0 - 1.5, self.z0, pc, shade(pc, 0.75), shade(pc, 1.1))
                r.layer = 1
                r.box(-S.ROAD_HALF - 0.3, S.ROAD_HALF + 0.3, 8.0, 13, self.z0 - 1.5, self.z0, pc, None, shade(pc, 1.1),
                      shade(pc, 0.6), overhead=True,
                      detail=_sign_detail(sprites.get(("station", self.data.get("name", "TUNNEL"))), 0.55))
        elif k == "bridge":
            # Deck at 11 m, well above the Jet Boost flight path (7.5 m).
            col = self.data.get("color", (150, 150, 160))
            y0 = 11.0
            r.box(-60, 60, y0, y0 + 1.6, self.z0, self.z1, col, shade(col, 0.75), shade(col, 1.15), shade(col, 0.55),
                  overhead=True,
                  detail=_sign_detail(sprites.get(("bridge_sign", self.data.get("name", "CITY LINE"))), 0.75))
            r.box(-60, 60, y0 + 1.6, y0 + 2.4, self.z0 + 0.1, self.z0 + 0.3, shade(col, 0.8), None, None, bias=-0.01,
                  overhead=True)
            r.layer = 0
            for px in (-S.SIDEWALK_HALF - 0.5, S.SIDEWALK_HALF - 0.7):
                r.box(px, px + 1.2, 0, y0, self.z0 + 0.6, self.z1 - 0.6, shade(col, 0.9), shade(col, 0.7), None, bias=0.01)
            r.layer = 1
        elif k == "gantry":
            col = (80, 85, 95)
            z = self.z0
            for px in (-S.ROAD_HALF - 0.4, S.ROAD_HALF + 0.1):
                r.box(px, px + 0.3, 0, 7.6, z, z + 0.3, col, shade(col, 0.7), None, bias=0.01)
            r.box(-S.ROAD_HALF - 0.4, S.ROAD_HALF + 0.4, 7.2, 7.6, z, z + 0.3, col, None, shade(col, 1.2), shade(col, 0.6),
                  overhead=True)
            for i, lx in enumerate(S.LANE_X):
                r.box(lx - 0.25, lx + 0.25, 6.3, 7.2, z - 0.05, z + 0.25, (30, 30, 34), (20, 20, 24), None, bias=-0.01,
                      overhead=True)
                color = (255, 60, 50) if (self.data or {}).get("states", [0, 1, 0])[i] == 0 else (60, 255, 120)
                if r.cam.y < 6.3:
                    r.glow(lx, 6.75, z - 0.1, 0.9, shade(color, 0.6))
        elif k == "station":
            r.layer = 0  # platforms, pillars and canopies all sit beside the tracks
            plat = (150, 146, 140)
            edge = (240, 200, 40)
            for sgn in (-1, 1):
                xa, xb = sorted((sgn * (S.ROAD_HALF + 0.3), sgn * (S.SIDEWALK_HALF + 1.5)))
                r.box(xa, xb, 0, 1.0, self.z0, self.z1, plat, shade(plat, 0.8), shade(plat, 1.12))
                ex = xa if sgn > 0 else xb - 0.4
                r.box(ex, ex + 0.4, 1.0, 1.03, self.z0, self.z1, edge, edge, edge, bias=-0.005)
                cx0, cx1 = sorted((sgn * (S.ROAD_HALF + 0.6), sgn * (S.SIDEWALK_HALF + 1.5)))
                r.box(cx0, cx1, 5.2, 5.6, self.z0, self.z1, (200, 205, 215), shade((200, 205, 215), 0.8),
                      (220, 225, 230), (120, 125, 135), bias=-0.01)
                z = self.z0 + 3
                while z < self.z1 - 2:
                    px = sgn * (S.SIDEWALK_HALF - 0.4)
                    r.box(px - 0.25, px + 0.25, 1.0, 5.2, z, z + 0.5, (210, 210, 220), (160, 160, 170), None, bias=-0.003)
                    r.glow(sgn * (S.ROAD_HALF + 2.5), 5.0, z, 2.0, (110, 105, 80))
                    z += 9
            name = self.data.get("name", "CENTRAL")
            sign = sprites.get(("station", name))
            r.layer = 1
            r.billboard(("station", name), sign, 0, 5.4, self.z0 + 4, 0.9, bias=-0.5)


def _sign_detail(sign_surf, height_frac, fit=False):
    def detail(r, fr, br, d0, d1, clipped):
        ax0, ay1, ax1, ay0 = fr
        h = (ay0 - ay1) * height_frac
        if fit:
            h = min(h, (ax1 - ax0) * sign_surf.get_height() / sign_surf.get_width())
        if h < 6 or clipped or h > 420:
            return
        img = r.scaled(("sign", id(sign_surf)), sign_surf, h)
        if img.get_width() > (ax1 - ax0):
            return
        f = r.fog_amount(d0)
        cx = r.cam.hx - (r.cam.x * r.cam.focal / max(d0, 1))
        cx = min(max(cx, ax0 + img.get_width() / 2), ax1 - img.get_width() / 2)
        if f > 0.02:
            img.set_alpha(int(255 * (1 - f)))
        r.surface.blit(img, (cx - img.get_width() / 2, (ay0 + ay1) / 2 - h / 2))
        img.set_alpha(None)
    return detail


# ---------------------------------------------------------------------------
# Sky
# ---------------------------------------------------------------------------
class Sky:
    def __init__(self):
        self._sky = {}
        self._skyline = {}

    def sky_surface(self, zone, height):
        key = (zone["id"], height)
        s = self._sky.get(key)
        if s is None:
            s = pygame.Surface((S.SCREEN_W, height))
            top, bot = zone["sky_top"], zone["sky_bottom"]
            for y in range(height):
                t = y / max(1, height - 1)
                pygame.draw.line(s, lerp_color(top, bot, t ** 0.9), (0, y), (S.SCREEN_W, y))
            rnd = random.Random(zone["id"])
            if zone.get("night"):
                for _ in range(140):
                    x, y = rnd.randrange(S.SCREEN_W), rnd.randrange(int(height * 0.7))
                    b = rnd.randint(120, 255)
                    s.set_at((x, y), (b, b, b))
                    if rnd.random() < 0.15:
                        pygame.draw.circle(s, (b, b, b), (x, y), 1)
            else:
                for _ in range(7):  # soft clouds
                    cx, cy = rnd.randrange(S.SCREEN_W), rnd.randrange(20, max(30, int(height * 0.55)))
                    cc = lerp_color(bot, (255, 255, 255), 0.55)
                    layer = pygame.Surface((260, 80), pygame.SRCALPHA)
                    for _ in range(6):
                        pygame.draw.ellipse(layer, (*cc, 70), (rnd.randrange(0, 120), rnd.randrange(10, 40), rnd.randrange(80, 140), rnd.randrange(24, 40)))
                    s.blit(layer, (cx - 130, cy - 40))
            if zone.get("sun"):
                sc = zone["sun"]
                cx, cy = int(S.SCREEN_W * 0.72), int(height * 0.62)
                for i in range(6, 0, -1):
                    layer = pygame.Surface((i * 40, i * 40), pygame.SRCALPHA)
                    pygame.draw.circle(layer, (*sc, 30), (i * 20, i * 20), i * 20)
                    s.blit(layer, (cx - i * 20, cy - i * 20))
                pygame.draw.circle(s, sc, (cx, cy), 34)
            if zone.get("moon"):
                mc = zone["moon"]
                cx, cy = int(S.SCREEN_W * 0.25), int(height * 0.3)
                pygame.draw.circle(s, mc, (cx, cy), 30)
                pygame.draw.circle(s, zone["sky_top"], (cx + 12, cy - 6), 26)
            self._sky[key] = s
        return s

    def skyline_surface(self, zone):
        key = zone["id"]
        s = self._skyline.get(key)
        if s is None:
            w, h = S.SCREEN_W + 400, 300
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            rnd = random.Random(key + "sky")
            kind = zone.get("skyline", "towers")
            fog = zone["fog"]
            far_col = lerp_color(fog, zone["sky_top"], 0.25)
            near_col = lerp_color(fog, (30, 30, 50), 0.35 if not zone.get("night") else 0.6)
            for layer, col in ((0, far_col), (1, near_col)):
                x = -20
                while x < w:
                    bw = rnd.randint(30, 90)
                    if kind == "skyscrapers":
                        bh = rnd.randint(110, 290) if layer == 0 else rnd.randint(60, 200)
                    elif kind == "domes":
                        bh = rnd.randint(30, 90)
                    elif kind == "factories":
                        bh = rnd.randint(40, 110)
                    elif kind == "cranes":
                        bh = rnd.randint(20, 60)
                    else:
                        bh = rnd.randint(50, 180) if layer == 0 else rnd.randint(30, 130)
                    if layer == 1:
                        bh = int(bh * 0.7)
                    pygame.draw.rect(s, col, (x, h - bh, bw, bh))
                    if kind == "domes" and rnd.random() < 0.3:
                        pygame.draw.circle(s, col, (x + bw // 2, h - bh), bw // 2)
                        if rnd.random() < 0.5:
                            pygame.draw.rect(s, col, (x + bw // 2 - 3, h - bh - bw // 2 - 30, 6, 30))
                    if kind == "factories" and rnd.random() < 0.4:
                        pygame.draw.rect(s, col, (x + 8, h - bh - 70, 12, 70))
                    if kind == "cranes" and rnd.random() < 0.25 and layer == 0:
                        pygame.draw.rect(s, col, (x + 10, h - 170, 8, 170))
                        pygame.draw.rect(s, col, (x - 40, h - 170, 120, 8))
                    if kind == "neon" and layer == 1:
                        for _ in range(rnd.randint(2, 6)):
                            wc = rnd.choice(NEON_COLORS)
                            pygame.draw.rect(s, wc, (x + rnd.randint(4, max(5, bw - 10)), h - rnd.randint(10, max(11, bh - 4)), 4, 3))
                    if kind in ("towers", "skyscrapers") and layer == 0 and rnd.random() < 0.2:
                        pygame.draw.rect(s, col, (x + bw // 2 - 2, h - bh - 25, 4, 25))
                    x += bw + rnd.randint(-10, 12)
            self._skyline[key] = s
        return s

    def draw(self, surf, cam, zone_a, zone_b, t):
        horizon = int(cam.hy)
        height = max(10, horizon + 70)
        sky_a = self.sky_surface(zone_a, height)
        surf.blit(sky_a, (0, 0))
        line_a = self.skyline_surface(zone_a)
        off = -200 - cam.x * 6
        surf.blit(line_a, (off, horizon - line_a.get_height() + 6))
        if zone_b is not None and t > 0.01:
            sky_b = self.sky_surface(zone_b, height)
            sky_b.set_alpha(int(255 * t))
            surf.blit(sky_b, (0, 0))
            sky_b.set_alpha(None)
            line_b = self.skyline_surface(zone_b)
            line_b.set_alpha(int(255 * t))
            surf.blit(line_b, (off, horizon - line_b.get_height() + 6))
            line_b.set_alpha(None)


def zone_colors(zone_a, zone_b, t):
    if zone_b is None or t <= 0.001:
        return zone_a
    out = dict(zone_a)
    for key in ("fog", "ground", "road", "sidewalk", "ties", "rail", "sky_top", "sky_bottom"):
        out[key] = lerp_color(zone_a[key], zone_b[key], t)
    return out


def random_ad(rnd):
    bg = rnd.choice([(230, 60, 60), (40, 120, 220), (250, 200, 40), (40, 170, 110), (150, 70, 200), (30, 30, 40)])
    fg = (255, 255, 255) if bg != (250, 200, 40) else (30, 30, 40)
    return (rnd.choice(AD_TEXTS), bg, fg)


def tree_color(zone):
    base = {"old_town": (70, 140, 60), "skyline": (60, 160, 90), "downtown": (80, 160, 70)}.get(zone["id"], (80, 150, 70))
    return to_color(base)
