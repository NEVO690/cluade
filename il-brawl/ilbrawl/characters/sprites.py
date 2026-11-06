"""Procedural, original art for every brawler, drawn as realistic top-down (3/4 view) human figures.

Each fighter is built from shaded body parts (boots, legs, torso with gear, arms, head with
face and hair), a realistic weapon that follows the aim direction, and signature gear
(helmets, hoods, caps, goggles...). Light comes from the top-left. Portraits are cached.
"""
import math

import pygame

from ilbrawl.ui import theme

GUNMETAL = (52, 56, 64)
STEEL = (120, 128, 140)
LEATHER = (66, 48, 36)


def _c(v):
    return tuple(int(max(0, min(255, x))) for x in v[:3])


def mute(c, amt=0.28):
    """Pull a colour toward grey and slightly darker for a grounded look."""
    c = _c(c)
    lum = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
    return tuple(int((v * (1 - amt) + lum * amt) * 0.9) for v in c)


def _outline(c):
    return theme.darken(c, 0.62)


def _shaded_ellipse(surf, color, rect, ow=1):
    rect = pygame.Rect(rect)
    pygame.draw.ellipse(surf, _outline(color), rect.inflate(ow * 2, ow * 2))
    pygame.draw.ellipse(surf, color, rect)
    sh = pygame.Rect(rect.x + rect.w * 0.35, rect.y + rect.h * 0.3, rect.w * 0.62, rect.h * 0.66)
    pygame.draw.ellipse(surf, theme.darken(color, 0.18), sh)
    hl = pygame.Rect(rect.x + rect.w * 0.16, rect.y + rect.h * 0.12, rect.w * 0.36, rect.h * 0.3)
    pygame.draw.ellipse(surf, theme.lighten(color, 0.16), hl)


def _shaded_poly(surf, color, pts, ow=1):
    pygame.draw.polygon(surf, _outline(color), pts, 0)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    inner = [(x + (cx - x) * 0.06, y + (cy - y) * 0.06) for x, y in pts]
    pygame.draw.polygon(surf, color, inner)
    # shadow on the right side, light on the left
    right = [(x, y) if x >= cx else (cx + (x - cx) * 0.05, y) for x, y in inner]
    pygame.draw.polygon(surf, theme.darken(color, 0.2), [(cx + (x - cx) * 0.96, y) for x, y in right])
    pygame.draw.polygon(surf, color, [(x if x < cx else cx + (x - cx) * 0.25, y) for x, y in inner])


def _limb(surf, color, a, b, width):
    width = max(2, int(width))
    pygame.draw.line(surf, _outline(color), a, b, width + 2)
    pygame.draw.circle(surf, _outline(color), (int(a[0]), int(a[1])), width // 2 + 1)
    pygame.draw.circle(surf, _outline(color), (int(b[0]), int(b[1])), width // 2 + 1)
    pygame.draw.line(surf, color, a, b, width)
    pygame.draw.circle(surf, color, (int(a[0]), int(a[1])), width // 2)
    pygame.draw.circle(surf, color, (int(b[0]), int(b[1])), width // 2)


def _weapon(surf, hand, facing, R, trim, kind, attack):
    fx, fy = math.cos(facing), math.sin(facing)
    px, py = -fy, fx
    hx, hy = hand
    if kind == "melee":
        # blade / anchor style weapon held upright toward the aim
        tip = (hx + fx * R * 1.35, hy + fy * R * 1.35)
        _limb(surf, LEATHER, (hx - fx * R * 0.2, hy - fy * R * 0.2), (hx + fx * R * 0.25, hy + fy * R * 0.25), R * 0.16)
        pts = [(hx + fx * R * 0.25 + px * R * 0.12, hy + fy * R * 0.25 + py * R * 0.12), tip,
               (hx + fx * R * 0.25 - px * R * 0.12, hy + fy * R * 0.25 - py * R * 0.12)]
        pygame.draw.polygon(surf, _outline(STEEL), [(x + 1, y + 1) for x, y in pts])
        pygame.draw.polygon(surf, (196, 204, 214), pts)
        pygame.draw.line(surf, trim, (hx + px * R * 0.22, hy + py * R * 0.22), (hx - px * R * 0.22, hy - py * R * 0.22),
                         max(2, int(R * 0.12)))
        return
    length = R * (1.5 if kind == "long" else 0.95 if kind == "short" else 1.2)
    thick = R * (0.19 if kind in ("heavy", "lob") else 0.13)
    back = (hx - fx * R * 0.35, hy - fy * R * 0.35)
    front = (hx + fx * length * 0.55, hy + fy * length * 0.55)
    body = [(back[0] + px * thick, back[1] + py * thick), (front[0] + px * thick, front[1] + py * thick),
            (front[0] - px * thick, front[1] - py * thick), (back[0] - px * thick, back[1] - py * thick)]
    pygame.draw.polygon(surf, (20, 22, 26), [(x + 1, y + 1) for x, y in body])
    pygame.draw.polygon(surf, GUNMETAL, body)
    # top highlight and coloured trim
    pygame.draw.line(surf, STEEL, body[0], body[1], 1)
    mid = ((back[0] + front[0]) / 2, (back[1] + front[1]) / 2)
    pygame.draw.line(surf, trim, (mid[0] - fx * thick, mid[1] - fy * thick), (mid[0] + fx * thick, mid[1] + fy * thick), max(1, int(thick * 0.6)))
    # barrel
    bw = max(2, int(thick * (1.1 if kind in ("heavy", "lob") else 0.75)))
    muzzle = (hx + fx * length, hy + fy * length)
    pygame.draw.line(surf, (20, 22, 26), front, muzzle, bw + 2)
    pygame.draw.line(surf, (82, 86, 96), front, muzzle, bw)
    if kind == "long":
        scope_a = (back[0] + fx * R * 0.3 + px * thick * 1.5, back[1] + fy * R * 0.3 + py * thick * 1.5)
        scope_b = (scope_a[0] + fx * R * 0.45, scope_a[1] + fy * R * 0.45)
        pygame.draw.line(surf, (20, 22, 26), scope_a, scope_b, max(3, int(thick * 0.9)))
    if attack > 0.08:
        fl = R * 0.45 * (attack / 0.18)
        tip = (muzzle[0] + fx * fl, muzzle[1] + fy * fl)
        flame = [(muzzle[0] + px * R * 0.15, muzzle[1] + py * R * 0.15), tip,
                 (muzzle[0] - px * R * 0.15, muzzle[1] - py * R * 0.15)]
        pygame.draw.polygon(surf, (255, 190, 80), flame)
        pygame.draw.circle(surf, (255, 240, 190), (int(muzzle[0]), int(muzzle[1])), max(2, int(R * 0.12)))


def _weapon_kind(style):
    return style.get("weapon", "rifle")


def _hair(surf, style, head, hr, back_view, side):
    hair = style.get("hair")
    acc = style.get("accessory", "")
    if not hair or acc in ("hood", "visor", "captain_hat", "horns", "halo"):
        return
    hair = mute(hair, 0.15)
    hx, hy = head
    if acc == "flame_hair":
        for i in range(5):
            a = math.pi * (1.05 + i * 0.22)
            tip = (hx + math.cos(a) * hr * 1.45, hy + math.sin(a) * hr * 1.45)
            base_l = (hx + math.cos(a - 0.3) * hr * 0.85, hy + math.sin(a - 0.3) * hr * 0.85)
            base_r = (hx + math.cos(a + 0.3) * hr * 0.85, hy + math.sin(a + 0.3) * hr * 0.85)
            pygame.draw.polygon(surf, _outline(hair), [base_l, tip, base_r])
            pygame.draw.polygon(surf, hair if i % 2 else theme.lighten(hair, 0.25), [base_l, tip, base_r])
        return
    if back_view:
        pygame.draw.circle(surf, _outline(hair), (int(hx), int(hy)), int(hr) + 1)
        pygame.draw.circle(surf, hair, (int(hx), int(hy)), int(hr))
        pygame.draw.circle(surf, theme.lighten(hair, 0.15), (int(hx - hr * 0.3), int(hy - hr * 0.35)), max(1, int(hr * 0.35)))
        return
    # hair cap over the top of the head with a side parting
    rect = pygame.Rect(hx - hr * 1.05, hy - hr * 1.12, hr * 2.1, hr * 1.5)
    pygame.draw.ellipse(surf, _outline(hair), rect.inflate(2, 2))
    pygame.draw.ellipse(surf, hair, rect)
    fringe = [(hx - hr * 1.0, hy - hr * 0.1), (hx - hr * 0.2 * side, hy - hr * 0.55), (hx + hr * 1.0, hy - hr * 0.1),
              (hx + hr * 1.0, hy - hr * 0.6), (hx - hr * 1.0, hy - hr * 0.6)]
    pygame.draw.polygon(surf, hair, fringe)
    pygame.draw.line(surf, theme.lighten(hair, 0.22), (hx - hr * 0.6, hy - hr * 0.85), (hx - hr * 0.1, hy - hr * 0.95),
                     max(1, int(hr * 0.15)))


def _face(surf, style, head, hr, facing, angry):
    hx, hy = head
    fx = math.cos(facing)
    ox = fx * hr * 0.22
    skin = _c(style.get("skin", (230, 190, 160)))
    eye_y = hy + hr * 0.05
    robot = style.get("robot")
    for s in (-1, 1):
        ex = hx + ox + s * hr * 0.36 * (1 - abs(fx) * 0.25)
        if robot:
            pygame.draw.circle(surf, (255, 220, 90), (int(ex), int(eye_y)), max(2, int(hr * 0.17)))
            continue
        if style.get("accessory") == "visor":
            continue
        pygame.draw.ellipse(surf, (245, 245, 240), (ex - hr * 0.16, eye_y - hr * 0.09, hr * 0.32, hr * 0.2))
        pygame.draw.circle(surf, (40, 34, 30), (int(ex + fx * hr * 0.05), int(eye_y + hr * 0.01)), max(1, int(hr * 0.09)))
        by = eye_y - hr * (0.24 if not angry else 0.18)
        tilt = hr * 0.06 * (1 if angry else 0) * s
        pygame.draw.line(surf, theme.darken(_c(style.get("hair") or (60, 50, 40)), 0.2),
                         (ex - hr * 0.17, by - tilt), (ex + hr * 0.17, by + tilt), max(1, int(hr * 0.1)))
    if not robot:
        # nose shadow and mouth
        nx = hx + ox * 1.3
        pygame.draw.line(surf, theme.darken(skin, 0.22), (nx, hy + hr * 0.12), (nx + hr * 0.08, hy + hr * 0.32),
                         max(1, int(hr * 0.09)))
        pygame.draw.line(surf, theme.darken(skin, 0.38), (hx + ox - hr * 0.18, hy + hr * 0.52),
                         (hx + ox + hr * 0.18, hy + hr * 0.5), max(1, int(hr * 0.08)))
    if style.get("beard"):
        hair = mute(style.get("hair") or (60, 50, 40), 0.15)
        beard = pygame.Rect(hx + ox - hr * 0.62, hy + hr * 0.3, hr * 1.24, hr * 0.8)
        pygame.draw.ellipse(surf, _outline(hair), beard.inflate(2, 2))
        pygame.draw.ellipse(surf, hair, beard)
        pygame.draw.line(surf, theme.darken(hair, 0.3), (hx + ox - hr * 0.2, hy + hr * 0.5), (hx + ox + hr * 0.2, hy + hr * 0.5),
                         max(1, int(hr * 0.08)))


def _gear(surf, style, head, hr, back_view, trim, cloth, t, side):
    acc = style.get("accessory", "")
    hx, hy = head
    o = max(1, int(hr * 0.08))
    if acc == "visor":
        helm = pygame.Rect(hx - hr * 1.1, hy - hr * 1.15, hr * 2.2, hr * 1.9)
        _shaded_ellipse(surf, (210, 216, 224), helm)
        if not back_view:
            v = pygame.Rect(hx - hr * 0.85, hy - hr * 0.35, hr * 1.7, hr * 0.65)
            pygame.draw.ellipse(surf, (20, 30, 40), v.inflate(2, 2))
            pygame.draw.ellipse(surf, (40, 120, 150), v)
            pygame.draw.ellipse(surf, (150, 220, 240), (v.x + v.w * 0.12, v.y + v.h * 0.15, v.w * 0.35, v.h * 0.3))
        pygame.draw.line(surf, trim, (hx - hr * 1.0, hy - hr * 0.45), (hx - hr * 0.4, hy - hr * 1.0), max(2, o * 2))
    elif acc == "horns":
        helm = pygame.Rect(hx - hr * 1.08, hy - hr * 1.12, hr * 2.16, hr * 1.35)
        _shaded_ellipse(surf, (110, 112, 118), helm)
        pygame.draw.line(surf, (70, 72, 78), (hx - hr * 1.0, hy - hr * 0.3), (hx + hr * 1.0, hy - hr * 0.3), max(2, o * 2))
        for s in (-1, 1):
            pts = [(hx + s * hr * 0.75, hy - hr * 0.6), (hx + s * hr * 1.55, hy - hr * 1.5), (hx + s * hr * 1.05, hy - hr * 0.35)]
            pygame.draw.polygon(surf, (60, 50, 40), [(x + 1, y + 1) for x, y in pts])
            pygame.draw.polygon(surf, (226, 214, 190), pts)
    elif acc == "leaf":
        cap = pygame.Rect(hx - hr * 1.0, hy - hr * 1.15, hr * 2.0, hr * 1.1)
        _shaded_ellipse(surf, mute(trim, 0.1), cap)
        if not back_view:
            pygame.draw.rect(surf, (230, 230, 230), (hx - hr * 0.2, hy - hr * 0.95, hr * 0.4, hr * 0.4))
            pygame.draw.rect(surf, (200, 50, 50), (hx - hr * 0.06, hy - hr * 0.92, hr * 0.12, hr * 0.34))
            pygame.draw.rect(surf, (200, 50, 50), (hx - hr * 0.17, hy - hr * 0.81, hr * 0.34, hr * 0.12))
    elif acc == "mask":
        if not back_view:
            m = [(hx - hr * 0.98, hy + hr * 0.15), (hx + hr * 0.98, hy + hr * 0.15), (hx + hr * 0.7, hy + hr * 0.85),
                 (hx - hr * 0.7, hy + hr * 0.85)]
            pygame.draw.polygon(surf, (24, 22, 30), m)
        pygame.draw.line(surf, trim, (hx - hr, hy - hr * 0.4), (hx + hr, hy - hr * 0.4), max(2, o * 2))
        sx = hx - side * hr
        pygame.draw.line(surf, trim, (sx, hy - hr * 0.4), (sx - side * hr * 0.9, hy - hr * 0.1 + math.sin(t * 8) * 2),
                         max(2, o * 2))
    elif acc == "goggles":
        pygame.draw.line(surf, LEATHER, (hx - hr, hy - hr * 0.55), (hx + hr, hy - hr * 0.55), max(2, o * 3))
        for s in (-1, 1):
            c = (int(hx + s * hr * 0.4), int(hy - hr * 0.58))
            pygame.draw.circle(surf, (40, 36, 30), c, int(hr * 0.33))
            pygame.draw.circle(surf, (150, 196, 200), c, int(hr * 0.24))
            pygame.draw.circle(surf, (230, 245, 245), (c[0] - int(hr * 0.08), c[1] - int(hr * 0.08)), max(1, int(hr * 0.07)))
    elif acc == "antenna":
        pygame.draw.line(surf, (60, 64, 72), (hx + hr * 0.4, hy - hr * 0.8), (hx + hr * 0.55, hy - hr * 1.6), max(2, o))
        blink = 0.5 + 0.5 * math.sin(t * 6)
        pygame.draw.circle(surf, theme.lerp_color(trim, (255, 255, 255), blink * 0.5),
                           (int(hx + hr * 0.55), int(hy - hr * 1.65)), max(2, int(hr * 0.16)))
        pygame.draw.line(surf, (90, 96, 106), (hx - hr * 0.95, hy), (hx + hr * 0.95, hy), 1)
    elif acc == "feather":
        for i, col in enumerate([(176, 66, 50), (210, 170, 70), (70, 120, 160)]):
            a = -math.pi / 2 - 0.35 + i * 0.3
            base = (hx + hr * 0.5, hy - hr * 0.7)
            tip = (base[0] + math.cos(a) * hr * 1.2, base[1] + math.sin(a) * hr * 1.2)
            _limb(surf, col, base, tip, hr * 0.22)
    elif acc == "crystal":
        for i, (dx, hh) in enumerate([(-0.5, 0.55), (0, 0.85), (0.5, 0.55)]):
            x = hx + dx * hr
            pts = [(x - hr * 0.18, hy - hr * 0.75), (x, hy - hr * (0.75 + hh)), (x + hr * 0.18, hy - hr * 0.75)]
            pygame.draw.polygon(surf, (90, 130, 160), [(px + 1, py + 1) for px, py in pts])
            pygame.draw.polygon(surf, (200, 232, 250) if i != 1 else (160, 210, 240), pts)
    elif acc == "captain_hat":
        crown = pygame.Rect(hx - hr * 0.95, hy - hr * 1.35, hr * 1.9, hr * 0.85)
        pygame.draw.rect(surf, (30, 30, 36), crown.inflate(2, 2), border_radius=max(2, int(hr * 0.4)))
        pygame.draw.rect(surf, (236, 236, 236), crown, border_radius=max(2, int(hr * 0.4)))
        brim = pygame.Rect(hx - hr * 1.05, hy - hr * 0.68, hr * 2.1, hr * 0.38)
        pygame.draw.ellipse(surf, (24, 26, 34), brim)
        pygame.draw.rect(surf, (28, 34, 60), (crown.x, crown.bottom - hr * 0.3, crown.w, hr * 0.3))
        pygame.draw.circle(surf, (210, 176, 70), (int(hx), int(crown.centery)), max(2, int(hr * 0.16)))
    elif acc == "headphones":
        pygame.draw.arc(surf, (30, 30, 36), (hx - hr * 1.1, hy - hr * 1.3, hr * 2.2, hr * 2.0), 0.2, math.pi - 0.2,
                        max(2, o * 2))
        for s in (-1, 1):
            c = (int(hx + s * hr * 1.0), int(hy - hr * 0.05))
            pygame.draw.circle(surf, (30, 30, 36), c, int(hr * 0.36))
            pygame.draw.circle(surf, trim, c, int(hr * 0.24))
    elif acc == "hood":
        hood = pygame.Rect(hx - hr * 1.25, hy - hr * 1.3, hr * 2.5, hr * 2.4)
        _shaded_ellipse(surf, theme.darken(cloth, 0.2), hood)
        if not back_view:
            face = pygame.Rect(hx - hr * 0.72, hy - hr * 0.55, hr * 1.44, hr * 1.25)
            pygame.draw.ellipse(surf, (16, 14, 20), face)
            for s in (-1, 1):
                pygame.draw.circle(surf, trim, (int(hx + s * hr * 0.3), int(hy)), max(1, int(hr * 0.12)))
    elif acc == "bandana":
        band = [(hx - hr * 1.02, hy - hr * 0.35), (hx + hr * 1.02, hy - hr * 0.35), (hx + hr * 0.95, hy - hr * 0.75),
                (hx - hr * 0.95, hy - hr * 0.75)]
        pygame.draw.polygon(surf, theme.darken(trim, 0.3), [(x, y + 1) for x, y in band])
        pygame.draw.polygon(surf, trim, band)
        sx = hx - side * hr
        pygame.draw.polygon(surf, trim, [(sx, hy - hr * 0.6), (sx - side * hr * 0.8, hy - hr * 0.5 + math.sin(t * 7) * 2),
                                         (sx - side * hr * 0.6, hy - hr * 0.1)])
    elif acc == "moss":
        for i in range(5):
            x = hx - hr * 0.8 + i * hr * 0.4
            pygame.draw.circle(surf, (58, 92, 50), (int(x), int(hy - hr * 0.8)), max(2, int(hr * 0.3)))
            pygame.draw.circle(surf, mute(trim, 0.2), (int(x - 1), int(hy - hr * 0.85)), max(2, int(hr * 0.24)))
    elif acc == "beret":
        b = pygame.Rect(hx - hr * 1.05, hy - hr * 1.2, hr * 1.9, hr * 0.85)
        _shaded_ellipse(surf, mute(trim, 0.1), b)
        pygame.draw.circle(surf, (190, 160, 70), (int(hx + hr * 0.45), int(hy - hr * 0.85)), max(1, int(hr * 0.13)))
    elif acc == "crown":
        w = hr * 1.2
        x0 = hx - w / 2
        y0 = hy - hr * 0.95
        pts = [(x0, y0), (x0 + w * 0.2, y0 - hr * 0.35), (x0 + w * 0.5, y0 - hr * 0.1), (x0 + w * 0.8, y0 - hr * 0.35),
               (x0 + w, y0)]
        pygame.draw.lines(surf, (200, 170, 80), False, pts, max(2, o * 2))
        pygame.draw.circle(surf, trim, (int(hx), int(y0 - hr * 0.12)), max(1, int(hr * 0.13)))
    elif acc == "halo":
        hood = pygame.Rect(hx - hr * 1.2, hy - hr * 1.25, hr * 2.4, hr * 2.3)
        _shaded_ellipse(surf, theme.darken(cloth, 0.1), hood)
        if not back_view:
            face = pygame.Rect(hx - hr * 0.7, hy - hr * 0.5, hr * 1.4, hr * 1.2)
            pygame.draw.ellipse(surf, _c(style.get("skin", (120, 96, 160))), face)
            for s in (-1, 1):
                pygame.draw.circle(surf, trim, (int(hx + s * hr * 0.3), int(hy)), max(1, int(hr * 0.12)))
        for i in range(3):
            a = t * 2 + i * 2.1
            pygame.draw.circle(surf, trim, (int(hx + math.cos(a) * hr * 1.8), int(hy + hr * 1.6 + math.sin(a) * hr * 0.6)),
                               max(2, int(hr * 0.14)))


def draw_brawler(surf, style, cx, cy, R, facing=0.0, t=0.0, walk=0.0, moving=False, flash=0.0,
                 attack=0.0, alpha=255, weapon=True):
    """Draw a realistic fighter standing with feet around (cx, cy + R)."""
    shape = style.get("shape", "round")
    cloth = mute(style["body"])
    trim = mute(style["accent"], 0.2)
    skin = _c(style.get("skin", (230, 190, 160)))
    if style.get("golem"):
        cloth = theme.darken(skin, 0.1)
    if flash > 0:
        k = min(1.0, flash * 6)
        cloth = theme.lerp_color(cloth, (255, 255, 255), k)
        skin = theme.lerp_color(skin, (255, 255, 255), k)
    target = surf
    if alpha < 255:
        target = pygame.Surface((int(R * 6), int(R * 6)), pygame.SRCALPHA)
        ox, oy = cx - R * 3, cy - R * 3
        cx, cy = R * 3, R * 3
    bulk = {"wide": 1.25, "square": 1.12, "tall": 0.88}.get(shape, 1.0)
    tall = {"tall": 1.08, "wide": 0.96}.get(shape, 1.0)
    bob = math.sin(walk * 2) * R * 0.04 if moving else math.sin(t * 2.2) * R * 0.02
    fx, fy = math.cos(facing), math.sin(facing)
    back_view = fy < -0.5
    side = 1 if fx >= 0 else -1
    pants = theme.darken(cloth, 0.45)
    boots = (38, 32, 30)
    hip_y = cy + R * 0.18 + bob
    foot_y = cy + R * 0.92
    # legs + boots
    for s in (-1, 1):
        stride = math.sin(walk + (0 if s < 0 else math.pi)) * R * 0.2 if moving else 0.0
        lx = cx + s * R * 0.22 * bulk
        knee = (lx + stride * 0.2, (hip_y + foot_y) / 2 + stride * 0.1)
        foot = (lx + stride * 0.35, foot_y + stride * 0.25)
        _limb(target, pants, (lx, hip_y), knee, R * 0.34 * bulk)
        _limb(target, pants, knee, foot, R * 0.3 * bulk)
        b = pygame.Rect(0, 0, R * 0.42 * bulk, R * 0.26)
        b.center = (int(foot[0] + side * R * 0.04), int(foot[1] + R * 0.05))
        pygame.draw.ellipse(target, (12, 10, 10), b.inflate(2, 2))
        pygame.draw.ellipse(target, boots, b)
    sh_y = cy - R * 0.6 * tall + bob
    hand = (cx + fx * R * 0.72, sh_y + R * 0.42 + fy * R * 0.3)
    kind = "melee" if style.get("weapon") == "melee" else _weapon_kind(style)

    def arms_and_weapon():
        for s, far in ((-1, 0.0), (1, 0.0)):
            shoulder = (cx + s * R * 0.48 * bulk, sh_y + R * 0.12)
            grip = (hand[0] - fx * R * (0.0 if s == side else -0.32), hand[1] - fy * R * (0.0 if s == side else -0.32))
            elbow = ((shoulder[0] + grip[0]) / 2 + s * R * 0.12, (shoulder[1] + grip[1]) / 2 + R * 0.1)
            _limb(target, cloth, shoulder, elbow, R * 0.26 * bulk)
            _limb(target, skin if not style.get("robot") else (120, 126, 138), elbow, grip, R * 0.22 * bulk)
        if weapon:
            _weapon(target, hand, facing, R, trim, kind, attack)

    if back_view:
        arms_and_weapon()
    # torso: tapered with shading, belt and gear
    sw, ww = R * 0.62 * bulk, R * 0.46 * bulk
    torso = [(cx - sw, sh_y), (cx + sw, sh_y), (cx + ww, hip_y + R * 0.05), (cx - ww, hip_y + R * 0.05)]
    _shaded_poly(target, cloth, torso)
    for s in (-1, 1):
        pygame.draw.circle(target, _outline(cloth), (int(cx + s * sw * 0.9), int(sh_y + R * 0.06)), int(R * 0.2 * bulk) + 1)
        pygame.draw.circle(target, cloth if s < 0 else theme.darken(cloth, 0.15),
                           (int(cx + s * sw * 0.9), int(sh_y + R * 0.06)), int(R * 0.2 * bulk))
    pygame.draw.line(target, LEATHER, (cx - ww, hip_y - R * 0.02), (cx + ww, hip_y - R * 0.02), max(2, int(R * 0.12)))
    pygame.draw.rect(target, (170, 150, 90), (cx - R * 0.07, hip_y - R * 0.07, R * 0.14, R * 0.11))
    if not back_view:
        pygame.draw.line(target, trim, (cx - sw * 0.8, sh_y + R * 0.05), (cx + ww * 0.7, hip_y - R * 0.1),
                         max(2, int(R * 0.12)))
        if shape == "square" or style.get("robot"):
            plate = pygame.Rect(cx - sw * 0.6, sh_y + R * 0.15, sw * 1.2, R * 0.4)
            pygame.draw.rect(target, theme.darken(trim, 0.3), plate.inflate(2, 2), border_radius=3)
            pygame.draw.rect(target, trim, plate, border_radius=3)
        else:
            pygame.draw.rect(target, theme.darken(cloth, 0.25), (cx + side * sw * 0.15, sh_y + R * 0.3, R * 0.2, R * 0.16))
    # neck + head
    head = (cx + fx * R * 0.04, sh_y - R * 0.34)
    hr = R * 0.37
    pygame.draw.rect(target, theme.darken(skin, 0.15), (cx - hr * 0.35, sh_y - hr * 0.5, hr * 0.7, hr * 0.6))
    _shaded_ellipse(target, skin, pygame.Rect(head[0] - hr, head[1] - hr * 1.05, hr * 2, hr * 2.1))
    if style.get("robot"):
        pygame.draw.rect(target, (60, 64, 72), (head[0] - hr * 0.8, head[1] - hr * 0.15, hr * 1.6, hr * 0.38),
                         border_radius=max(1, int(hr * 0.15)))
    if style.get("golem"):
        for i in range(3):
            pygame.draw.line(target, theme.darken(skin, 0.35), (head[0] - hr * 0.6 + i * hr * 0.5, head[1] - hr * 0.8),
                             (head[0] - hr * 0.4 + i * hr * 0.45, head[1] - hr * 0.3), 1)
    acc = style.get("accessory", "")
    _hair(target, style, head, hr, back_view, side)
    if not back_view and acc not in ("hood", "halo"):
        _face(target, style, head, hr, facing, attack > 0)
    _gear(target, style, head, hr, back_view, trim, cloth, t, side)
    if not back_view:
        arms_and_weapon()
    if target is not surf:
        target.set_alpha(alpha)
        surf.blit(target, (ox, oy))
    return pygame.Rect(int(cx - R), int(sh_y - R), int(R * 2), int(R * 2.6))


_portrait_cache = {}


def portrait(style, size, key=None, gray=False):
    """Cached square portrait surface of a character (3/4 front view)."""
    k = (key or id(style), size, gray, tuple(style.get("body", ())), tuple(style.get("accent", ())))
    s = _portrait_cache.get(k)
    if s is None:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        R = size * 0.31
        draw_brawler(s, style, size / 2, size / 2 + R * 0.22, R, facing=0.55, t=0.0, weapon=True)
        _portrait_cache[k] = s
    return s
