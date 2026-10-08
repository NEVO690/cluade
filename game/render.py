"""Depth-sorted pseudo-3D renderer built on pygame 2D drawing.

Objects are queued with a depth (distance along z) and drawn far-to-near
(painter's algorithm).  Boxes are rendered with only their visible faces,
distance fog blends far geometry into the zone's horizon colour and a few
cached sprites (glows, billboards) are scaled on demand.
"""
import math

import pygame

from . import settings as S

_raw_poly = pygame.draw.polygon
_CLIP_MARGIN = 2


def _clip_edge(pts, inside, intersect):
    out = []
    n = len(pts)
    if n == 0:
        return out
    prev = pts[-1]
    prev_in = inside(prev)
    for cur in pts:
        cur_in = inside(cur)
        if cur_in:
            if not prev_in:
                out.append(intersect(prev, cur))
            out.append(cur)
        elif prev_in:
            out.append(intersect(prev, cur))
        prev, prev_in = cur, cur_in
    return out


def clip_polygon(pts, w, h):
    """Sutherland-Hodgman clip of a screen polygon to the (slightly enlarged) screen rect."""
    x0, y0, x1, y1 = -_CLIP_MARGIN, -_CLIP_MARGIN, w + _CLIP_MARGIN, h + _CLIP_MARGIN

    def ix(a, b, x):
        t = (x - a[0]) / (b[0] - a[0])
        return (x, a[1] + (b[1] - a[1]) * t)

    def iy(a, b, y):
        t = (y - a[1]) / (b[1] - a[1])
        return (a[0] + (b[0] - a[0]) * t, y)

    pts = _clip_edge(pts, lambda p: p[0] >= x0, lambda a, b: ix(a, b, x0))
    pts = _clip_edge(pts, lambda p: p[0] <= x1, lambda a, b: ix(a, b, x1))
    pts = _clip_edge(pts, lambda p: p[1] >= y0, lambda a, b: iy(a, b, y0))
    pts = _clip_edge(pts, lambda p: p[1] <= y1, lambda a, b: iy(a, b, y1))
    return pts


def _poly(surf, color, pts):
    """pygame.draw.polygon that clips huge/off-screen polygons first.

    pygame's scanline fill gets very slow for polygons extending far outside
    the surface, which happens constantly for geometry close to the camera.
    """
    w, h = surf.get_size()
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    if maxx < 0 or minx > w or maxy < 0 or miny > h:
        return
    if minx < -64 or maxx > w + 64 or miny < -64 or maxy > h + 64:
        pts = clip_polygon(list(pts), w, h)
        if len(pts) < 3:
            return
    _raw_poly(surf, color, pts)


draw_poly = _poly


class Renderer:
    def __init__(self, surface, camera):
        self.surface = surface
        self.cam = camera
        self.items = []
        self._counter = 0
        self.fog_color = (180, 200, 230)
        self.draw_distance = 170.0
        self.fog_start = 70.0
        self._fog_inv = 1 / 100.0
        self.glow_enabled = True
        self._glow_cache = {}
        self._scale_cache = {}
        self.stats_drawn = 0

    def begin(self, fog_color, draw_distance, glow=True):
        self.items.clear()
        self._counter = 0
        self.fog_color = fog_color
        self.draw_distance = draw_distance
        self.fog_start = draw_distance * 0.42
        self._fog_inv = 1.0 / max(1.0, draw_distance - self.fog_start)
        self.glow_enabled = glow

    # ------------------------------------------------------------------
    # Queue / flush
    # ------------------------------------------------------------------
    def queue(self, depth, fn, *args):
        self._counter += 1
        self.items.append((-depth, self._counter, fn, args))

    def flush(self):
        self.items.sort(key=lambda it: (it[0], it[1]))
        self.stats_drawn = len(self.items)
        for _, _, fn, args in self.items:
            fn(*args)
        self.items.clear()

    def visible_range(self, z0, z1):
        cz = self.cam.z
        return z1 > cz + S.NEAR_PLANE and z0 < cz + self.draw_distance

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def fog(self, c, dz):
        t = (dz - self.fog_start) * self._fog_inv
        if t <= 0:
            return c
        f = self.fog_color
        if t >= 1:
            return f
        return (int(c[0] + (f[0] - c[0]) * t), int(c[1] + (f[1] - c[1]) * t), int(c[2] + (f[2] - c[2]) * t))

    def fog_amount(self, dz):
        t = (dz - self.fog_start) * self._fog_inv
        return 0.0 if t <= 0 else 1.0 if t >= 1 else t

    def proj(self, x, y, z):
        cam = self.cam
        dz = z - cam.z
        if dz < S.NEAR_PLANE:
            dz = S.NEAR_PLANE
        s = cam.focal / dz
        return (cam.hx + (x - cam.x) * s, cam.hy - (y - cam.y) * s)

    def scale_at(self, z):
        return self.cam.focal / max(S.NEAR_PLANE, z - self.cam.z)

    def polygon3d(self, pts, color):
        """Draw an arbitrary 3D polygon immediately (no near clipping beyond clamping)."""
        cam = self.cam
        out = []
        for x, y, z in pts:
            dz = z - cam.z
            if dz < S.NEAR_PLANE:
                dz = S.NEAR_PLANE
            s = cam.focal / dz
            out.append((cam.hx + (x - cam.x) * s, cam.hy - (y - cam.y) * s))
        _poly(self.surface, color, out)

    # ------------------------------------------------------------------
    # Boxes
    # ------------------------------------------------------------------
    def box(self, x0, x1, y0, y1, z0, z1, front, side=None, top=None, bottom=None, bias=0.0, detail=None):
        cz = self.cam.z
        zn = cz + S.NEAR_PLANE
        if z1 <= zn or z0 > cz + self.draw_distance:
            return
        if y0 > self.cam.y + 1.0 and z1 < cz + 2.5:
            return  # overhead geometry about to pass over the lens: would just flash the top of the screen
        self.queue(max(z0, zn) + bias, self.draw_box, x0, x1, y0, y1, z0, z1, front, side, top, bottom, detail)

    def draw_box(self, x0, x1, y0, y1, z0, z1, front, side, top, bottom, detail=None):
        cam = self.cam
        cx, cy, cz, F, hx, hy = cam.x, cam.y, cam.z, cam.focal, cam.hx, cam.hy
        zn = cz + S.NEAR_PLANE
        clipped = z0 < zn
        if clipped:
            z0 = zn
        d0 = z0 - cz
        d1 = z1 - cz
        s0 = F / d0
        s1 = F / d1
        ax0 = hx + (x0 - cx) * s0
        ax1 = hx + (x1 - cx) * s0
        ay0 = hy - (y0 - cy) * s0
        ay1 = hy - (y1 - cy) * s0
        bx0 = hx + (x0 - cx) * s1
        bx1 = hx + (x1 - cx) * s1
        by0 = hy - (y0 - cy) * s1
        by1 = hy - (y1 - cy) * s1
        surf = self.surface
        fogc = self.fog
        dm = (d0 + d1) * 0.5 if d1 - d0 < 60 else d0 + 30
        if side is not None:
            if cx < x0:
                _poly(surf, fogc(side, dm), ((ax0, ay0), (ax0, ay1), (bx0, by1), (bx0, by0)))
            elif cx > x1:
                _poly(surf, fogc(side, dm), ((ax1, ay0), (ax1, ay1), (bx1, by1), (bx1, by0)))
        if top is not None and cy > y1:
            _poly(surf, fogc(top, dm), ((ax0, ay1), (ax1, ay1), (bx1, by1), (bx0, by1)))
        elif bottom is not None and cy < y0:
            _poly(surf, fogc(bottom, dm), ((ax0, ay0), (ax1, ay0), (bx1, by0), (bx0, by0)))
        if front is not None:
            if ax1 - ax0 >= 1 and ay0 - ay1 >= 1:
                surf.fill(fogc(front, d0), (ax0, ay1, ax1 - ax0 + 1, ay0 - ay1 + 1))
            else:
                pygame.draw.line(surf, fogc(front, d0), (ax0, ay1), (ax0, ay0))
        if detail is not None:
            detail(self, (ax0, ay1, ax1, ay0), (bx0, by1, bx1, by0), d0, d1, clipped)

    # ------------------------------------------------------------------
    # Sprites & glows
    # ------------------------------------------------------------------
    def _glow_surface(self, radius, color):
        key = (radius, color)
        surf = self._glow_cache.get(key)
        if surf is None:
            if len(self._glow_cache) > 400:
                self._glow_cache.clear()
            size = radius * 2
            surf = pygame.Surface((size, size))
            surf.fill((0, 0, 0))
            steps = max(4, min(16, radius // 2))
            for i in range(steps):
                t = i / steps
                r = int(radius * (1 - t))
                k = (t ** 1.8) * 0.9
                pygame.draw.circle(surf, (int(color[0] * k), int(color[1] * k), int(color[2] * k)), (radius, radius), r)
            self._glow_cache[key] = surf
        return surf

    def glow(self, x, y, z, radius_m, color, bias=0.05):
        if not self.glow_enabled:
            return
        if not self.visible_range(z - 0.1, z + 0.1):
            return
        self.queue(z + bias, self.draw_glow, x, y, z, radius_m, color)

    def draw_glow(self, x, y, z, radius_m, color):
        dz = z - self.cam.z
        if dz < S.NEAR_PLANE:
            return
        s = self.cam.focal / dz
        r = int(radius_m * s)
        if r < 2:
            return
        r = min(r, 260)
        # quantise for the cache
        r = r if r < 24 else (r // 4) * 4
        k = 1.0 - self.fog_amount(dz)
        if k <= 0.05:
            return
        c = (int(color[0] * k), int(color[1] * k), int(color[2] * k))
        c = (c[0] // 8 * 8, c[1] // 8 * 8, c[2] // 8 * 8)
        sx, sy = self.proj(x, y, z)
        self.surface.blit(self._glow_surface(r, c), (sx - r, sy - r), special_flags=pygame.BLEND_ADD)

    def scaled(self, key, surf, height_px):
        """Return ``surf`` scaled to ``height_px`` (quantised and cached)."""
        h = max(2, int(height_px))
        if h >= 40:
            # geometric quantisation (~6% steps) keeps the cache small while objects approach
            q = 1.06 if h < 200 else 1.1
            h = int(round(q ** round(math.log(h, q))))
        ck = (key, h)
        out = self._scale_cache.get(ck)
        if out is None:
            if len(self._scale_cache) > 600:
                self._scale_cache.clear()
            w = max(1, int(surf.get_width() * h / surf.get_height()))
            out = pygame.transform.smoothscale(surf, (w, h)) if h < 260 else pygame.transform.scale(surf, (w, h))
            self._scale_cache[ck] = out
        return out

    def billboard(self, key, surf, x, y, z, height_m, bias=0.0, anchor="bottom", alpha_fog=True):
        if not self.visible_range(z - 0.1, z + 0.1):
            return
        self.queue(z + bias, self.draw_billboard, key, surf, x, y, z, height_m, anchor, alpha_fog)

    def draw_billboard(self, key, surf, x, y, z, height_m, anchor="bottom", alpha_fog=True):
        dz = z - self.cam.z
        if dz < S.NEAR_PLANE:
            return
        s = self.cam.focal / dz
        h = height_m * s
        if h < 2 or h > 480:
            return  # very close sprites are at the screen edge; skipping avoids huge rescales
        img = self.scaled(key, surf, h)
        sx, sy = self.proj(x, y, z)
        w = img.get_width()
        if anchor == "bottom":
            pos = (sx - w / 2, sy - img.get_height())
        else:
            pos = (sx - w / 2, sy - img.get_height() / 2)
        if alpha_fog:
            f = self.fog_amount(dz)
            if f > 0.02:
                if f >= 0.98:
                    return
                img.set_alpha(int(255 * (1 - f)))
                self.surface.blit(img, pos)
                img.set_alpha(None)
                return
        self.surface.blit(img, pos)


def make_radial(radius, color, alpha_center=200):
    """Alpha radial gradient (used for shadows / shield bubbles)."""
    size = radius * 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    steps = max(4, min(20, radius // 2))
    for i in range(steps):
        t = i / steps
        a = int(alpha_center * (t ** 1.5))
        pygame.draw.circle(surf, (*color, a), (radius, radius), int(radius * (1 - t)))
    return surf


def ellipse_points(cx, cy, rx, ry, n=16, start=0.0, end=math.tau):
    pts = []
    for i in range(n + 1):
        a = start + (end - start) * i / n
        pts.append((cx + math.cos(a) * rx, cy + math.sin(a) * ry))
    return pts
