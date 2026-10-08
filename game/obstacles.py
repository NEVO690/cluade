"""Obstacles: geometry, collision shapes and zone-styled drawing.

Mechanical kinds (what the player must do):

* ``low``    - jump over it
* ``high``   - slide under it
* ``block``  - change lane
* ``train``  - change lane, or run up a ``ramp`` / super-jump onto the roof
* ``ramp``   - walkable slope leading onto a train roof
* ``car``    - jump onto the roof or change lane

Visual style comes from the zone's ``obstacle_style`` (see ``STYLES``), so a
new zone can restyle every obstacle without touching collision code.
"""
import math

import pygame

from . import settings as S
from .utils import shade

LOW, HIGH, BLOCK, TRAIN, RAMP, CAR = "low", "high", "block", "train", "ramp", "car"

# Standard dimensions (depth along z, bottom y, top y)
DIMENSIONS = {
    LOW: (0.5, 0.0, 1.0),
    HIGH: (0.45, 1.2, 2.8),
    BLOCK: (1.8, 0.0, 2.9),
    TRAIN: (24.0, 0.0, 3.3),
    RAMP: (7.0, 0.0, 3.3),
    CAR: (4.2, 0.0, 1.45),
}

TRAIN_COLORS = [(60, 120, 200), (210, 70, 60), (60, 160, 110), (230, 180, 50), (140, 90, 190), (200, 200, 210)]
CAR_COLORS = [(220, 50, 50), (40, 90, 200), (235, 235, 240), (40, 40, 45), (250, 190, 40), (60, 170, 120)]

STYLES = {
    "downtown": {LOW: ("barrier", (225, 60, 50), (250, 250, 250)), HIGH: ("sign", (245, 195, 40), (40, 40, 40)),
                 BLOCK: ("construction", (235, 125, 40), (250, 250, 250)), "train_palette": [0, 1, 5]},
    "metro": {LOW: ("barrier", (240, 200, 40), (40, 40, 40)), HIGH: ("sign", (60, 120, 220), (255, 255, 255)),
              BLOCK: ("kiosk", (90, 110, 140), (230, 230, 240)), "train_palette": [0, 5, 4, 2]},
    "old_town": {LOW: ("crate", (170, 120, 70), (120, 80, 45)), HIGH: ("sign", (150, 90, 50), (240, 220, 180)),
                 BLOCK: ("cart", (140, 90, 60), (230, 200, 120)), "train_palette": [1, 2, 3]},
    "industrial": {LOW: ("pipe", (220, 170, 40), (60, 60, 60)), HIGH: ("sign", (235, 160, 30), (30, 30, 30)),
                   BLOCK: ("container", (180, 90, 50), (120, 60, 30)), "train_palette": [3, 5, 1]},
    "harbor": {LOW: ("crate", (90, 130, 170), (60, 90, 120)), HIGH: ("sign", (240, 240, 240), (220, 60, 50)),
               BLOCK: ("container", (40, 110, 170), (25, 75, 120)), "train_palette": [1, 0, 3]},
    "neon": {LOW: ("neon", (40, 30, 60), (0, 255, 220)), HIGH: ("neon", (40, 30, 60), (255, 40, 200)),
             BLOCK: ("neon", (35, 30, 55), (120, 120, 255)), "train_palette": [4, 0, 5]},
    "skyline": {LOW: ("barrier", (230, 230, 240), (230, 60, 60)), HIGH: ("sign", (60, 70, 90), (120, 220, 255)),
                BLOCK: ("construction", (90, 100, 120), (255, 200, 40)), "train_palette": [5, 0, 4]},
}

DARK = (28, 28, 34)


class Obstacle:
    __slots__ = ("kind", "lane", "x", "z0", "z1", "y0", "y1", "vel", "style", "variant", "prev_z0",
                 "passed", "alive", "color", "accent", "train_color", "has_ramp", "counted")

    def __init__(self, kind, lane, z0, length=None, vel=0.0, style="downtown", variant=0):
        depth, y0, y1 = DIMENSIONS[kind]
        self.kind = kind
        self.lane = lane
        self.x = S.LANE_X[lane]
        self.z0 = z0
        self.z1 = z0 + (length if length is not None else depth)
        self.y0 = y0
        self.y1 = y1
        self.vel = vel
        self.style = style if style in STYLES else "downtown"
        self.variant = variant
        self.prev_z0 = z0
        self.passed = False
        self.alive = True
        self.counted = False
        self.has_ramp = False
        st = STYLES[self.style]
        if kind in st:
            _, self.color, self.accent = st[kind]
        else:
            self.color, self.accent = (200, 200, 200), (60, 60, 60)
        pal = st.get("train_palette", [0])
        self.train_color = TRAIN_COLORS[pal[variant % len(pal)]]
        if kind == CAR:
            self.color = CAR_COLORS[variant % len(CAR_COLORS)]

    # ------------------------------------------------------------------
    @property
    def x0(self):
        return self.x - S.LANE_HALF

    @property
    def x1(self):
        return self.x + S.LANE_HALF

    def top_at(self, z):
        """Height of the walkable top surface at z."""
        if self.kind == RAMP:
            t = (z - self.z0) / (self.z1 - self.z0)
            return self.y1 * (0.0 if t < 0 else 1.0 if t > 1 else t)
        return self.y1

    @property
    def walkable(self):
        return self.kind in (TRAIN, RAMP, CAR, BLOCK)

    def update(self, dt):
        self.prev_z0 = self.z0
        if self.vel:
            d = self.vel * dt
            self.z0 += d
            self.z1 += d

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def queue_draw(self, r, quality, night=False):
        if not self.alive or not r.visible_range(self.z0, self.z1):
            return
        k = self.kind
        if k == LOW:
            self._draw_low(r, night)
        elif k == HIGH:
            self._draw_high(r, night)
        elif k == BLOCK:
            self._draw_block(r, night)
        elif k == TRAIN:
            self._draw_train(r, quality, night)
        elif k == RAMP:
            r.queue(max(self.z0, r.cam.z + S.NEAR_PLANE) + 0.01, self._draw_ramp, r)
        elif k == CAR:
            self._draw_car(r, night)

    def _stripes(self, n, c1, c2, diagonal=True):
        def detail(r, fr, br, d0, d1, clipped):
            ax0, ay1, ax1, ay0 = fr
            w = ax1 - ax0
            h = ay0 - ay1
            if w < 6 or h < 3:
                return
            c2f = r.fog(c2, d0)
            seg = w / n
            for i in range(0, n, 2):
                x = ax0 + i * seg
                if diagonal:
                    pts = [(x, ay0), (x + seg * 0.6, ay1), (x + seg * 1.6, ay1), (x + seg, ay0)]
                    pts = [(min(ax1, max(ax0, px)), py) for px, py in pts]
                    pygame.draw.polygon(r.surface, c2f, pts)
                else:
                    r.surface.fill(c2f, (x, ay1, seg, h))
        return detail

    def _draw_low(self, r, night):
        typ = STYLES[self.style][LOW][0]
        x0, x1, z0, z1 = self.x0 + 0.1, self.x1 - 0.1, self.z0, self.z1
        c, a = self.color, self.accent
        if typ == "barrier":
            for lx in (x0 + 0.15, x1 - 0.35):
                r.box(lx, lx + 0.2, 0, 0.55, z0 + 0.15, z1 - 0.15, shade(a, 0.7), shade(a, 0.5), None)
            r.box(x0, x1, 0.5, 1.0, z0, z1, c, shade(c, 0.7), shade(c, 1.15), detail=self._stripes(6, c, a), bias=-0.01)
        elif typ == "crate":
            w = (x1 - x0) / 2
            for i in range(2):
                cx0 = x0 + i * w + 0.03
                r.box(cx0, cx0 + w - 0.06, 0, 1.0, z0, z1, c, shade(c, 0.7), shade(c, 1.2), detail=self._crate_detail(a))
        elif typ == "pipe":
            r.box(x0, x1, 0.0, 0.2, z0 + 0.1, z1 - 0.1, DARK, DARK, None)
            r.box(x0, x1, 0.2, 1.0, z0, z1, c, shade(c, 0.7), shade(c, 1.25),
                  detail=self._stripes(4, c, a, diagonal=False), bias=-0.01)
        elif typ == "neon":
            r.box(x0, x1, 0.0, 1.0, z0, z1, c, shade(c, 0.8), shade(c, 1.3), detail=self._neon_edge(a))
            r.glow(self.x, 0.6, z0 - 0.1, 1.6, a)
        else:
            r.box(x0, x1, 0, 1.0, z0, z1, c, shade(c, 0.7), shade(c, 1.2))

    def _crate_detail(self, plank):
        def detail(r, fr, br, d0, d1, clipped):
            ax0, ay1, ax1, ay0 = fr
            if ax1 - ax0 < 8:
                return
            col = r.fog(plank, d0)
            w = max(1, int((ax1 - ax0) * 0.08))
            pygame.draw.rect(r.surface, col, (ax0, ay1, ax1 - ax0, ay0 - ay1), w)
            pygame.draw.line(r.surface, col, (ax0, ay1), (ax1, ay0), w)
            pygame.draw.line(r.surface, col, (ax0, ay0), (ax1, ay1), w)
        return detail

    def _neon_edge(self, glow):
        def detail(r, fr, br, d0, d1, clipped):
            ax0, ay1, ax1, ay0 = fr
            if ax1 - ax0 < 4:
                return
            col = r.fog(glow, d0 * 0.6)
            w = max(1, int((ax1 - ax0) * 0.04))
            pygame.draw.rect(r.surface, col, (ax0, ay1, ax1 - ax0, ay0 - ay1), w)
            my = (ay0 + ay1) / 2
            pygame.draw.line(r.surface, col, (ax0 + w * 2, my), (ax1 - w * 2, my), w)
        return detail

    def _draw_high(self, r, night):
        typ = STYLES[self.style][HIGH][0]
        x0, x1, z0, z1 = self.x0, self.x1, self.z0, self.z1
        c, a = self.color, self.accent
        post = (90, 90, 100) if typ != "neon" else (60, 50, 80)
        for px in (x0, x1 - 0.16):
            r.box(px, px + 0.16, 0, self.y1, z0 + 0.1, z1 - 0.1, post, shade(post, 0.7), shade(post, 1.2), bias=0.02)
        if typ == "neon":
            r.box(x0, x1, self.y0, self.y1, z0, z1, c, shade(c, 0.7), shade(c, 1.2), detail=self._neon_edge(a))
            r.glow(self.x, (self.y0 + self.y1) / 2, z0 - 0.1, 2.0, a)
        else:
            r.box(x0, x1, self.y0, self.y1, z0, z1, c, shade(c, 0.7), shade(c, 1.2), detail=self._chevrons(a))

    def _chevrons(self, col):
        def detail(r, fr, br, d0, d1, clipped):
            ax0, ay1, ax1, ay0 = fr
            w = ax1 - ax0
            h = ay0 - ay1
            if w < 10:
                return
            cc = r.fog(col, d0)
            band_top = ay1 + h * 0.32
            band_bot = ay1 + h * 0.68
            n = 4
            seg = w / n
            for i in range(n):
                x = ax0 + i * seg + seg * 0.2
                pygame.draw.polygon(r.surface, cc, [(x, band_top), (x + seg * 0.4, (band_top + band_bot) / 2),
                                                    (x, band_bot), (x + seg * 0.25, band_bot),
                                                    (x + seg * 0.65, (band_top + band_bot) / 2), (x + seg * 0.25, band_top)])
            lw = max(1, int(h * 0.07))
            pygame.draw.rect(r.surface, cc, (ax0, ay1, w, h), lw)
        return detail

    def _draw_block(self, r, night):
        typ = STYLES[self.style][BLOCK][0]
        x0, x1, z0, z1 = self.x0 + 0.05, self.x1 - 0.05, self.z0, self.z1
        c, a = self.color, self.accent
        if typ == "container":
            r.box(x0, x1, 0, self.y1, z0, z1, c, shade(c, 0.75), shade(c, 1.15), detail=self._ridges(a))
        elif typ == "kiosk":
            r.box(x0, x1, 0, self.y1 - 0.5, z0, z1, c, shade(c, 0.75), None, detail=self._kiosk(a))
            r.box(x0 - 0.15, x1 + 0.15, self.y1 - 0.5, self.y1, z0 - 0.15, z1 + 0.15, a, shade(a, 0.75), shade(a, 1.1), bias=-0.02)
        elif typ == "cart":
            r.box(x0, x1, 0.5, self.y1, z0, z1, c, shade(c, 0.75), shade(a, 1.0), detail=self._crate_detail(shade(c, 0.6)))
            for wx in (x0 + 0.2, x1 - 0.45):
                r.box(wx, wx + 0.25, 0, 0.55, z0 + 0.3, z1 - 0.3, DARK, DARK, None, bias=0.01)
        elif typ == "neon":
            r.box(x0, x1, 0, self.y1, z0, z1, c, shade(c, 0.8), shade(c, 1.3), detail=self._neon_edge(a))
            r.glow(self.x, 1.5, z0 - 0.1, 2.6, a)
        else:  # construction
            r.box(x0, x1, 0, self.y1, z0, z1, c, shade(c, 0.72), shade(c, 1.15), detail=self._construction(a))

    def _ridges(self, col):
        def detail(r, fr, br, d0, d1, clipped):
            ax0, ay1, ax1, ay0 = fr
            w = ax1 - ax0
            if w < 12:
                return
            cc = r.fog(col, d0)
            lw = max(1, int(w * 0.03))
            for i in range(1, 8):
                x = ax0 + w * i / 8
                pygame.draw.line(r.surface, cc, (x, ay1 + 2), (x, ay0 - 2), lw)
        return detail

    def _kiosk(self, col):
        def detail(r, fr, br, d0, d1, clipped):
            ax0, ay1, ax1, ay0 = fr
            w, h = ax1 - ax0, ay0 - ay1
            if w < 10:
                return
            r.surface.fill(r.fog(col, d0), (ax0 + w * 0.1, ay1 + h * 0.1, w * 0.8, h * 0.4))
        return detail

    def _construction(self, col):
        def detail(r, fr, br, d0, d1, clipped):
            ax0, ay1, ax1, ay0 = fr
            w, h = ax1 - ax0, ay0 - ay1
            if w < 8:
                return
            cc = r.fog(col, d0)
            for frac in (0.18, 0.62):
                y = ay1 + h * frac
                bh = h * 0.16
                r.surface.fill(cc, (ax0, y, w, bh))
                seg = w / 6
                dark = r.fog((235, 60, 50), d0)
                for i in range(0, 6, 2):
                    pygame.draw.polygon(r.surface, dark, [(ax0 + i * seg, y + bh), (ax0 + i * seg + seg * 0.5, y),
                                                          (ax0 + (i + 1) * seg, y), (ax0 + (i + 0.5) * seg, y + bh)])
        return detail

    def _draw_train(self, r, quality, night):
        x0, x1, z0, z1 = self.x0 + 0.05, self.x1 - 0.05, self.z0, self.z1
        body = self.train_color
        roof = shade(body, 0.85)
        moving = self.vel != 0
        r.box(x0 + 0.15, x1 - 0.15, 0.0, 0.45, z0 + 0.4, z1 - 0.4, DARK, DARK, None, bias=0.02)
        r.box(x0, x1, 0.4, self.y1, z0, z1, body, shade(body, 0.72), roof,
              detail=self._train_detail(quality, moving, night))
        if moving or night:
            for sx in (-0.65, 0.65):
                r.glow(self.x + sx, 1.0, z0 - 0.2, 1.4 if moving else 0.9, (255, 240, 180) if moving else (255, 120, 80))
        if moving:
            r.glow(self.x, 2.2, z0 - 0.3, 3.5, (120, 100, 60))

    def _train_detail(self, quality, moving, night):
        ob = self

        def detail(r, fr, br, d0, d1, clipped):
            ax0, ay1, ax1, ay0 = fr
            w, h = ax1 - ax0, ay0 - ay1
            surf = r.surface
            if not clipped and w > 6:
                # windshield
                surf.fill(r.fog((40, 60, 90) if not night else (255, 230, 150), d0),
                          (ax0 + w * 0.12, ay1 + h * 0.12, w * 0.76, h * 0.3))
                # stripe
                surf.fill(r.fog((250, 250, 250), d0), (ax0, ay1 + h * 0.52, w, h * 0.07))
                # headlights
                lc = (255, 250, 210) if moving else (220, 50, 40)
                rad = max(1, int(w * 0.07))
                for fx in (0.2, 0.8):
                    pygame.draw.circle(surf, r.fog(lc, d0), (int(ax0 + w * fx), int(ay1 + h * 0.8)), rad)
                if w > 40:
                    num = r.fog((30, 30, 40), d0)
                    surf.fill(num, (ax0 + w * 0.38, ay1 + h * 0.62, w * 0.24, h * 0.1))
            # side windows
            cam = r.cam
            if cam.x < ob.x0 + 0.05:
                sx = ob.x0 + 0.05
            elif cam.x > ob.x1 - 0.05:
                sx = ob.x1 - 0.05
            else:
                return
            if not quality.get("windows", True):
                return
            zs = max(ob.z0, cam.z + S.NEAR_PLANE)
            win = (40, 60, 90) if not night else (255, 225, 140)
            z = ob.z0 + 1.2
            n = 0
            far = cam.z + r.draw_distance
            while z < ob.z1 - 1.5 and z < far and n < 14:
                if z > zs:
                    zz = min(z + 1.6, ob.z1 - 1.0)
                    r.polygon3d(((sx, 1.8, z), (sx, 2.75, z), (sx, 2.75, zz), (sx, 1.8, zz)), r.fog(win, z - cam.z))
                z += 2.6
                n += 1
            r.polygon3d(((sx, 1.35, zs), (sx, 1.5, zs), (sx, 1.5, ob.z1), (sx, 1.35, ob.z1)),
                        r.fog((245, 245, 245), (zs + ob.z1) / 2 - cam.z))
        return detail

    def _draw_ramp(self, r):
        cam = r.cam
        x0, x1 = self.x0 + 0.1, self.x1 - 0.1
        zn = cam.z + S.NEAR_PLANE
        z0 = max(self.z0, zn)
        z1 = self.z1
        if z1 <= z0:
            return
        h0 = self.top_at(z0)
        h1 = self.y1
        dz = (z0 + z1) / 2 - cam.z
        col = (150, 150, 160)
        side = r.fog(shade(col, 0.6), dz)
        if cam.x < x0:
            r.polygon3d(((x0, 0, z0), (x0, h0, z0), (x0, h1, z1), (x0, 0, z1)), side)
        elif cam.x > x1:
            r.polygon3d(((x1, 0, z0), (x1, h0, z0), (x1, h1, z1), (x1, 0, z1)), side)
        if cam.y > h0:
            r.polygon3d(((x0, h0, z0), (x1, h0, z0), (x1, h1, z1), (x0, h1, z1)), r.fog(col, dz))
            # yellow warning bars across the slope
            bar = r.fog((250, 200, 40), dz)
            step = (self.z1 - self.z0) / 6
            for i in range(1, 6, 2):
                za = self.z0 + i * step
                zb = za + step * 0.5
                if za > zn:
                    ha, hb = self.top_at(za), self.top_at(zb)
                    r.polygon3d(((x0, ha, za), (x1, ha, za), (x1, hb, zb), (x0, hb, zb)), bar)

    def _draw_car(self, r, night):
        x0, x1, z0, z1 = self.x - 0.95, self.x + 0.95, self.z0, self.z1
        c = self.color
        moving = self.vel != 0
        r.box(x0 + 0.1, x1 - 0.1, 0.0, 0.32, z0 + 0.3, z1 - 0.3, DARK, DARK, None, bias=0.02)
        r.box(x0, x1, 0.3, 0.92, z0, z1, c, shade(c, 0.72), shade(c, 1.1), detail=self._car_lights(moving))
        r.box(x0 + 0.18, x1 - 0.18, 0.92, self.y1, z0 + 0.9, z1 - 1.0, (60, 80, 110), shade(c, 0.65), shade(c, 1.05),
              bias=-0.9)
        if moving or night:
            for sx in (-0.65, 0.65):
                r.glow(self.x + sx, 0.65, z0 - 0.1, 0.8, (255, 240, 190) if moving else (255, 60, 50))

    def _car_lights(self, moving):
        def detail(r, fr, br, d0, d1, clipped):
            ax0, ay1, ax1, ay0 = fr
            w, h = ax1 - ax0, ay0 - ay1
            if w < 8 or clipped:
                return
            lc = r.fog((255, 250, 220) if moving else (230, 40, 40), d0)
            r.surface.fill(lc, (ax0 + w * 0.05, ay1 + h * 0.25, w * 0.18, h * 0.2))
            r.surface.fill(lc, (ax1 - w * 0.23, ay1 + h * 0.25, w * 0.18, h * 0.2))
            r.surface.fill(r.fog((30, 30, 35), d0), (ax0 + w * 0.32, ay1 + h * 0.55, w * 0.36, h * 0.22))
        return detail
