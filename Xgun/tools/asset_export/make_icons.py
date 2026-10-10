"""Draw Xgun's UI icons (XON coin, banners, social glyphs) as anti-aliased PNGs.

    python tools/asset_export/make_icons.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "ui" / "icons"
S = 128
Y, X = (np.mgrid[0:S, 0:S] + 0.5) / S * 2 - 1
Y = -Y  # up is +


def aa(d, w=2.0 / S):
    return np.clip(0.5 - d / w, 0, 1)


def circle(cx, cy, r):
    return np.hypot(X - cx, Y - cy) - r


def ring(cx, cy, r, t):
    return np.abs(circle(cx, cy, r)) - t


def box(cx, cy, hw, hh, rot=0.0, r=0.0):
    c, s = math.cos(rot), math.sin(rot)
    x, y = (X - cx) * c + (Y - cy) * s, -(X - cx) * s + (Y - cy) * c
    qx, qy = np.abs(x) - hw + r, np.abs(y) - hh + r
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def seg(ax, ay, bx, by, t):
    px, py = X - ax, Y - ay
    dx, dy = bx - ax, by - ay
    h = np.clip((px * dx + py * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(px - dx * h, py - dy * h) - t


def poly(points):
    """Signed distance to a convex/concave polygon (even-odd)."""
    n = len(points)
    d = np.full(X.shape, np.inf)
    inside = np.zeros(X.shape, bool)
    for i in range(n):
        ax, ay = points[i]
        bx, by = points[(i + 1) % n]
        d = np.minimum(d, seg(ax, ay, bx, by, 0))
        cond = ((ay > Y) != (by > Y)) & (X < (bx - ax) * (Y - ay) / (by - ay + 1e-9) + ax)
        inside ^= cond
    return np.where(inside, -d, d)


def union(*ds):
    return np.minimum.reduce(ds)


def sub(a, b):
    return np.maximum(a, -b)


def layer(img, d, color, alpha=1.0):
    a = aa(d) * alpha
    for i in range(3):
        img[..., i] = img[..., i] * (1 - a) + color[i] * a
    img[..., 3] = np.maximum(img[..., 3], a)


def hexrgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def save(name, img):
    from panda3d.core import PNMImage
    OUT.mkdir(parents=True, exist_ok=True)
    pnm = PNMImage(S, S, 4)
    data = np.clip(img, 0, 1)
    for yy in range(S):
        for xx in range(S):
            r, g, b, a = data[yy, xx]
            pnm.setXelA(xx, yy, r, g, b, a)
    pnm.write(str(OUT / f"{name}.png"))


def new():
    return np.zeros((S, S, 4))


def glyph(d, color="#FFFFFF"):
    img = new()
    layer(img, d, hexrgb(color))
    return img


def build():
    icons = {}
    # XON coin
    img = new()
    layer(img, circle(0, 0, 0.92), hexrgb("#B8860B"))
    layer(img, circle(0, 0.03, 0.84), hexrgb("#FFC94D"))
    layer(img, ring(0, 0.03, 0.66, 0.035), hexrgb("#E0A21A"))
    layer(img, union(seg(-0.33, 0.36, 0.33, -0.3, 0.1), seg(-0.33, -0.3, 0.33, 0.36, 0.1)), hexrgb("#7A4B00"))
    layer(img, circle(-0.35, 0.45, 0.12), (1, 1, 1), 0.5)
    icons["xon"] = img
    # banners
    def banner(bg1, draw):
        img = new()
        layer(img, box(0, 0, 0.9, 0.9, r=0.18), hexrgb(bg1))
        layer(img, box(0, 0, 0.78, 0.78, r=0.12), [c * 0.7 for c in hexrgb(bg1)])
        draw(img)
        return img
    icons["banner_x"] = banner("#7C4DFF", lambda im: layer(im, union(seg(-0.45, 0.45, 0.45, -0.45, 0.14),
                                                                      seg(-0.45, -0.45, 0.45, 0.45, 0.14)), (1, 1, 1)))
    def wave(im):
        pts = [(x, 0.25 * math.sin(x * 5)) for x in np.linspace(-0.6, 0.6, 30)]
        d = union(*[seg(*pts[i], *pts[i + 1], 0.09) for i in range(len(pts) - 1)])
        layer(im, d, hexrgb("#00E5FF"))
        d2 = union(*[seg(pts[i][0], pts[i][1] - 0.3, pts[i + 1][0], pts[i + 1][1] - 0.3, 0.06) for i in range(len(pts) - 1)])
        layer(im, d2, (1, 1, 1), 0.7)
    icons["banner_wave"] = banner("#1B4965", wave)
    icons["banner_crown"] = banner("#B8860B", lambda im: layer(im, poly([(-0.55, -0.35), (-0.6, 0.35), (-0.25, 0.05), (0, 0.5),
                                                                         (0.25, 0.05), (0.6, 0.35), (0.55, -0.35)]), hexrgb("#FFE08A")))
    icons["banner_bolt"] = banner("#2B2D42", lambda im: (layer(im, ring(0, 0, 0.6, 0.05), hexrgb("#C6FF00")),
                                                         layer(im, poly([(0.1, 0.6), (-0.35, -0.05), (-0.02, -0.05), (-0.12, -0.6),
                                                                         (0.35, 0.08), (0.03, 0.08)]), hexrgb("#C6FF00"))))
    icons["banner_flame"] = banner("#6A040F", lambda im: (layer(im, union(circle(0, -0.18, 0.38), poly([(-0.38, -0.1), (0, 0.65), (0.38, -0.1)])),
                                                                hexrgb("#FF7B00")),
                                                          layer(im, union(circle(0, -0.25, 0.2), poly([(-0.2, -0.2), (0, 0.25), (0.2, -0.2)])),
                                                                hexrgb("#FFBA08"))))
    # social / ui glyphs (white, tinted at runtime)
    heart = union(circle(-0.3, 0.2, 0.38), circle(0.3, 0.2, 0.38), poly([(-0.66, 0.08), (0.66, 0.08), (0, -0.72)]))
    icons["heart"] = glyph(heart)
    icons["heart_outline"] = glyph(sub(heart, union(circle(-0.3, 0.2, 0.26), circle(0.3, 0.2, 0.26),
                                                    poly([(-0.52, 0.12), (0.52, 0.12), (0, -0.52)]))))
    bubble = union(box(0, 0.08, 0.72, 0.52, r=0.3), poly([(-0.3, -0.3), (-0.5, -0.75), (0.05, -0.38)]))
    icons["comment"] = glyph(sub(bubble, union(circle(-0.3, 0.08, 0.09), circle(0, 0.08, 0.09), circle(0.3, 0.08, 0.09))))
    bm = poly([(-0.45, 0.75), (0.45, 0.75), (0.45, -0.75), (0, -0.35), (-0.45, -0.75)])
    icons["bookmark"] = glyph(bm)
    icons["bookmark_outline"] = glyph(sub(bm, poly([(-0.3, 0.6), (0.3, 0.6), (0.3, -0.42), (0, -0.15), (-0.3, -0.42)])))
    icons["share"] = glyph(union(poly([(0.75, 0.15), (0.05, 0.7), (0.05, 0.4), (-0.7, 0.1), (-0.4, -0.65), (0.05, -0.1),
                                       (0.05, -0.4)])))
    icons["play"] = glyph(poly([(-0.45, 0.7), (0.7, 0), (-0.45, -0.7)]))
    icons["pause"] = glyph(union(box(-0.3, 0, 0.16, 0.65, r=0.05), box(0.3, 0, 0.16, 0.65, r=0.05)))
    icons["upload"] = glyph(union(poly([(0, 0.8), (0.55, 0.2), (0.2, 0.2), (0.2, -0.35), (-0.2, -0.35), (-0.2, 0.2), (-0.55, 0.2)]),
                                  box(0, -0.65, 0.7, 0.1)))
    icons["search"] = glyph(union(ring(-0.15, 0.15, 0.45, 0.1), seg(0.18, -0.18, 0.65, -0.65, 0.12)))
    icons["user"] = glyph(union(circle(0, 0.32, 0.33), sub(circle(0, -0.75, 0.75), box(0, -1.2, 1, 0.45))))
    lens = np.maximum(circle(0, -0.45, 0.85), circle(0, 0.45, 0.85))
    icons["eye"] = glyph(union(sub(lens, circle(0, 0, 0.36)), circle(0, 0, 0.2)))
    icons["check"] = glyph(union(seg(-0.55, 0.0, -0.15, -0.45, 0.13), seg(-0.15, -0.45, 0.6, 0.45, 0.13)))
    icons["lock"] = glyph(union(box(0, -0.25, 0.55, 0.45, r=0.1), sub(ring(0, 0.25, 0.32, 0.1), box(0, -0.2, 0.6, 0.35))))
    icons["flag"] = glyph(union(seg(-0.55, -0.8, -0.55, 0.75, 0.08), poly([(-0.5, 0.75), (0.6, 0.45), (-0.5, 0.1)])))
    icons["plus"] = glyph(union(box(0, 0, 0.12, 0.6), box(0, 0, 0.6, 0.12)))
    icons["friends"] = glyph(union(circle(-0.3, 0.3, 0.26), circle(0.35, 0.38, 0.22),
                                   sub(circle(-0.3, -0.65, 0.6), box(0, -1.25, 1.2, 0.5)),
                                   sub(circle(0.4, -0.45, 0.48), box(0, -1.05, 1.2, 0.5))))
    icons["trash"] = glyph(union(box(0, -0.15, 0.45, 0.55, r=0.06), box(0, 0.55, 0.6, 0.07), box(0, 0.67, 0.2, 0.07)))
    icons["gear"] = glyph(sub(union(circle(0, 0, 0.55), *[box(0, 0, 0.14, 0.8, rot=a) for a in np.linspace(0, math.pi, 4, endpoint=False)]),
                              circle(0, 0, 0.25)))
    for name, img in icons.items():
        save(name, img)
    return len(icons)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    print("icons:", build())
