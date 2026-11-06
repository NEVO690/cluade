"""Visual identity of IL Brawl: palette and shared drawing helpers."""
import math

import pygame

WHITE = (236, 238, 242)
BLACK = (0, 0, 0)
INK = (10, 12, 16)            # outline / shadow colour
TEXT_DIM = (150, 160, 174)
BG_TOP = (14, 17, 22)
BG_BOTTOM = (34, 40, 50)
PANEL = (24, 29, 37)
PANEL_LIGHT = (44, 52, 64)
PANEL_BORDER = (74, 86, 104)

YELLOW = (222, 172, 62)       # amber accent
ORANGE = (196, 104, 44)
GREEN = (64, 140, 86)
BLUE = (56, 104, 160)
RED = (170, 50, 50)
PURPLE = (100, 80, 140)
PINK = (160, 80, 112)
CYAN = (66, 140, 160)
GREY = (84, 90, 102)
COIN = (206, 164, 66)
GEM = (86, 180, 146)
TROPHY = (204, 146, 58)

RARITY_COLORS = {
    "common": (128, 150, 160),
    "rare": (84, 150, 90),
    "super_rare": (70, 116, 176),
    "epic": (128, 84, 170),
    "mythic": (176, 64, 80),
    "legendary": (214, 168, 62),
}
CLASS_COLORS = {
    "tank": (176, 104, 60),
    "assassin": (140, 70, 140),
    "marksman": (70, 124, 176),
    "support": (76, 150, 100),
    "controller": (190, 150, 60),
}


def lighten(c, amt=0.25):
    return tuple(min(255, int(v + (255 - v) * amt)) for v in c[:3])


def darken(c, amt=0.25):
    return tuple(max(0, int(v * (1 - amt))) for v in c[:3])


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


_gradient_cache = {}


def vertical_gradient(size, top, bottom):
    key = (size, top, bottom)
    s = _gradient_cache.get(key)
    if s is None:
        w, h = size
        s = pygame.Surface((w, h))
        steps = 48
        for i in range(steps):
            y0 = h * i // steps
            y1 = h * (i + 1) // steps
            s.fill(lerp_color(top, bottom, i / (steps - 1)), (0, y0, w, y1 - y0 + 1))
        _gradient_cache[key] = s
    return s


def draw_panel(surf, rect, color=PANEL, border=PANEL_BORDER, radius=18, shadow=True, border_w=3):
    rect = pygame.Rect(rect)
    radius = min(radius, 8)
    border_w = min(border_w, 2)
    if shadow:
        pygame.draw.rect(surf, darken(color, 0.55), rect.move(0, 5), border_radius=radius)
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surf, border, rect, border_w, border_radius=radius)


def draw_button_shape(surf, rect, color, pressed=False, hover=False, radius=16, disabled=False):
    rect = pygame.Rect(rect)
    radius = min(radius, 6)
    base = GREY if disabled else color
    if hover and not disabled:
        base = lighten(base, 0.12)
    depth = 1 if pressed else 3
    body = rect.move(0, 3 - depth)
    pygame.draw.rect(surf, INK, rect.inflate(4, 4).move(0, 2), border_radius=radius + 2)
    pygame.draw.rect(surf, darken(base, 0.45), body.move(0, depth), border_radius=radius)
    pygame.draw.rect(surf, base, body, border_radius=radius)
    # brushed-metal style top sheen and thin bevel
    hl = pygame.Rect(body.x + 2, body.y + 2, body.w - 4, max(3, body.h // 2 - 2))
    pygame.draw.rect(surf, lighten(base, 0.1), hl, border_radius=max(1, radius - 2))
    pygame.draw.line(surf, lighten(base, 0.35), (body.x + radius, body.y + 1), (body.right - radius, body.y + 1), 1)
    pygame.draw.rect(surf, darken(base, 0.5), body, 1, border_radius=radius)
    return body


def draw_coin(surf, center, r):
    x, y = int(center[0]), int(center[1])
    pygame.draw.circle(surf, INK, (x, y + 1), r + 2)
    pygame.draw.circle(surf, darken(COIN, 0.25), (x, y), r)
    pygame.draw.circle(surf, COIN, (x, y - 1), max(1, r - 2))
    pygame.draw.circle(surf, lighten(COIN, 0.5), (x - r // 3, y - r // 3), max(1, r // 4))


def draw_gem_icon(surf, center, r, color=GEM):
    x, y = center
    pts = [(x, y - r), (x + r * 0.85, y - r * 0.2), (x, y + r), (x - r * 0.85, y - r * 0.2)]
    pygame.draw.polygon(surf, INK, [(px + (1 if px > x else -1) * 2, py + (2 if py > y else -2)) for px, py in pts])
    pygame.draw.polygon(surf, color, pts)
    pygame.draw.polygon(surf, lighten(color, 0.45), [(x, y - r), (x + r * 0.85, y - r * 0.2), (x, y - r * 0.05)])


def draw_trophy(surf, center, r):
    x, y = int(center[0]), int(center[1])
    cup = pygame.Rect(x - r, y - r, r * 2, int(r * 1.3))
    pygame.draw.rect(surf, INK, cup.inflate(4, 4), border_radius=r // 2)
    pygame.draw.rect(surf, TROPHY, cup, border_radius=r // 2)
    pygame.draw.rect(surf, INK, (x - r // 3 - 2, y + r // 4, r * 2 // 3 + 4, r // 2 + 2))
    pygame.draw.rect(surf, darken(TROPHY, 0.2), (x - r // 3, y + r // 4, r * 2 // 3, r // 2))
    pygame.draw.rect(surf, INK, (x - r * 2 // 3 - 2, y + r * 2 // 3 - 2, r * 4 // 3 + 4, r // 3 + 4), border_radius=3)
    pygame.draw.rect(surf, TROPHY, (x - r * 2 // 3, y + r * 2 // 3, r * 4 // 3, r // 3), border_radius=2)
    pygame.draw.circle(surf, lighten(TROPHY, 0.5), (x - r // 3, y - r // 3), max(1, r // 4))


def draw_star(surf, center, r, color=YELLOW, points=5):
    x, y = center
    pts = []
    for i in range(points * 2):
        ang = -math.pi / 2 + i * math.pi / points
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((x + math.cos(ang) * rr, y + math.sin(ang) * rr))
    pygame.draw.polygon(surf, INK, [(px, py + 2) for px, py in pts])
    pygame.draw.polygon(surf, color, pts)


def draw_lock(surf, center, r):
    x, y = int(center[0]), int(center[1])
    pygame.draw.circle(surf, INK, (x, y - r // 3), r // 2 + 2, 4)
    pygame.draw.circle(surf, (210, 210, 230), (x, y - r // 3), r // 2, 3)
    body = pygame.Rect(x - r * 2 // 3, y - r // 6, r * 4 // 3, r)
    pygame.draw.rect(surf, INK, body.inflate(4, 4), border_radius=5)
    pygame.draw.rect(surf, (230, 200, 70), body, border_radius=4)
    pygame.draw.circle(surf, INK, (x, y + r // 4), max(2, r // 6))


def draw_xp_icon(surf, center, r):
    draw_star(surf, center, r, CYAN)
