"""Procedurally drawn icons (placeholders for real art).

Every icon is drawn into a transparent square surface.  To replace an icon
with real art, drop ``assets/images/icons/<name>.png`` - the asset manager
prefers files over these drawings.
"""
import math

import pygame

from .utils import shade

WHITE = (255, 255, 255)
DARK = (25, 25, 40)


def _star_points(cx, cy, r_out, r_in, n=5, rot=-math.pi / 2):
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = rot + i * math.pi / n
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


def draw_icon(name, size, color=None):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size / 2
    u = size / 64.0  # design units: icons are designed on a 64x64 grid
    col = color or (255, 200, 60)
    dark = shade(col, 0.55)
    light = shade(col, 1.35)

    def circle(color_, center, radius, width=0):
        pygame.draw.circle(s, color_, (int(center[0]), int(center[1])), max(1, int(radius)), width)

    def poly(color_, pts, width=0):
        pygame.draw.polygon(s, color_, [(x * u, y * u) for x, y in pts], width)

    def rect(color_, x, y, w, h, r=0):
        pygame.draw.rect(s, color_, (int(x * u), int(y * u), max(1, int(w * u)), max(1, int(h * u))), border_radius=int(r * u))

    def line(color_, p1, p2, w):
        pygame.draw.line(s, color_, (p1[0] * u, p1[1] * u), (p2[0] * u, p2[1] * u), max(1, int(w * u)))

    if name == "coin":
        circle(shade((255, 205, 40), 0.7), (c, c), 30 * u)
        circle((255, 205, 40), (c, c), 26 * u)
        circle((255, 236, 140), (c, c), 18 * u, max(1, int(3 * u)))
        rect((255, 245, 200), 28, 20, 8, 24, 3)
    elif name == "gem":
        poly(shade((90, 230, 255), 0.6), [(32, 58), (6, 24), (16, 10), (48, 10), (58, 24)])
        poly((90, 230, 255), [(32, 54), (11, 24), (19, 13), (45, 13), (53, 24)])
        poly((200, 250, 255), [(19, 13), (32, 24), (45, 13)])
        poly((150, 240, 255), [(11, 24), (53, 24), (32, 54)], max(1, int(2 * u)))
    elif name == "token":
        circle(dark, (c, c), 29 * u)
        circle(col, (c, c), 25 * u)
        pts = _star_points(c, c, 17 * u, 7 * u)
        pygame.draw.polygon(s, light, pts)
    elif name == "magnet":
        w = 12
        rect(col, 8, 10, w, 30)
        rect(col, 44, 10, w, 30)
        pygame.draw.arc(s, col, (8 * u, 18 * u, 48 * u, 40 * u), math.pi, 2 * math.pi, int(w * u))
        rect((230, 230, 240), 8, 6, w, 10)
        rect((230, 230, 240), 44, 6, w, 10)
    elif name == "jet":
        poly((210, 215, 230), [(32, 4), (44, 20), (44, 44), (20, 44), (20, 20)])
        poly(col, [(20, 30), (8, 46), (20, 44)])
        poly(col, [(44, 30), (56, 46), (44, 44)])
        circle((80, 180, 255), (32 * u, 22 * u), 6 * u)
        poly((255, 200, 40), [(22, 46), (42, 46), (32, 62)])
        poly((255, 120, 30), [(26, 46), (38, 46), (32, 56)])
    elif name == "shield":
        poly(dark, [(32, 4), (56, 12), (54, 36), (32, 60), (10, 36), (8, 12)])
        poly(col, [(32, 9), (51, 15), (49, 35), (32, 54), (15, 35), (13, 15)])
        poly(light, [(32, 9), (32, 54), (15, 35), (13, 15)])
    elif name == "multiplier":
        circle(dark, (c, c), 29 * u)
        circle(col, (c, c), 25 * u)
        line(WHITE, (16, 22), (30, 42), 5)
        line(WHITE, (30, 22), (16, 42), 5)
        font = pygame.font.Font(None, int(34 * u))
        t = font.render("2", True, WHITE)
        s.blit(t, (36 * u, 32 * u - t.get_height() / 2))
    elif name == "super_jump":
        for i in range(4):
            y = 40 - i * 7
            line((200, 200, 210), (18, y), (46, y - 3), 4)
        rect(col, 12, 44, 40, 14, 6)
        poly(light, [(32, 2), (46, 16), (38, 16), (38, 24), (26, 24), (26, 16), (18, 16)])
    elif name == "speed":
        poly(dark, [(38, 2), (12, 36), (30, 36), (24, 62), (52, 24), (34, 24)])
        poly(col, [(36, 7), (16, 33), (32, 33), (28, 54), (47, 27), (31, 27)])
    elif name == "board":
        pygame.draw.ellipse(s, dark, (4 * u, 20 * u, 56 * u, 24 * u))
        pygame.draw.ellipse(s, col, (6 * u, 21 * u, 52 * u, 20 * u))
        rect(light, 14, 29, 36, 4, 2)
        circle(DARK, (16 * u, 46 * u), 5 * u)
        circle(DARK, (48 * u, 46 * u), 5 * u)
    elif name == "head_start":
        poly((220, 220, 235), [(32, 2), (46, 22), (46, 46), (18, 46), (18, 22)])
        circle((70, 170, 255), (32 * u, 24 * u), 6 * u)
        poly(col, [(18, 34), (6, 52), (18, 48)])
        poly(col, [(46, 34), (58, 52), (46, 48)])
        poly((255, 140, 30), [(22, 48), (42, 48), (32, 63)])
    elif name == "booster":
        poly(dark, _star_points(32, 32, 30, 14))
        poly(col, _star_points(32, 32, 26, 11))
        font = pygame.font.Font(None, int(26 * u))
        t = font.render("+1", True, WHITE)
        s.blit(t, (c - t.get_width() / 2, c - t.get_height() / 2 + 2 * u))
    elif name == "key":
        circle(col, (20 * u, 32 * u), 14 * u)
        circle((0, 0, 0, 0), (20 * u, 32 * u), 6 * u)
        rect(col, 30, 28, 30, 8, 2)
        rect(col, 48, 36, 6, 10)
        rect(col, 38, 36, 6, 8)
    elif name == "trail":
        for i, cc in enumerate([(255, 80, 80), (255, 200, 60), (80, 220, 120), (80, 160, 255)]):
            pygame.draw.arc(s, cc, (6 * u + i * 5 * u, 14 * u + i * 5 * u, 60 * u - i * 10 * u, 70 * u - i * 10 * u),
                            math.pi * 0.5, math.pi * 1.0, max(2, int(5 * u)))
        circle(col, (46 * u, 22 * u), 10 * u)
    elif name == "outfit":
        poly(dark, [(20, 6), (44, 6), (60, 18), (52, 30), (46, 26), (46, 58), (18, 58), (18, 26), (12, 30), (4, 18)])
        poly(col, [(22, 9), (42, 9), (56, 19), (51, 26), (43, 22), (43, 55), (21, 55), (21, 22), (13, 26), (8, 19)])
        pygame.draw.arc(s, dark, (24 * u, 2 * u, 16 * u, 14 * u), math.pi, 2 * math.pi, max(1, int(3 * u)))
    elif name == "effect":
        pygame.draw.polygon(s, col, _star_points(c, c, 28 * u, 10 * u, 4))
        pygame.draw.polygon(s, light, _star_points(c, c, 14 * u, 5 * u, 4, rot=math.pi / 4))
    elif name == "emote":
        pygame.draw.ellipse(s, WHITE, (4 * u, 8 * u, 56 * u, 38 * u))
        poly(WHITE, [(16, 40), (12, 58), (30, 42)])
        circle(DARK, (22 * u, 27 * u), 4 * u)
        circle(DARK, (42 * u, 27 * u), 4 * u)
        pygame.draw.arc(s, DARK, (22 * u, 24 * u, 20 * u, 14 * u), math.pi * 1.1, math.pi * 1.9, max(1, int(3 * u)))
    elif name == "character":
        circle(col, (c, 20 * u), 12 * u)
        pygame.draw.ellipse(s, col, (12 * u, 34 * u, 40 * u, 40 * u))
    elif name == "star":
        pygame.draw.polygon(s, dark, _star_points(c, c, 30 * u, 13 * u))
        pygame.draw.polygon(s, col, _star_points(c, c + 1, 25 * u, 11 * u))
    elif name == "trophy":
        poly(col, [(14, 6), (50, 6), (46, 30), (32, 38), (18, 30)])
        pygame.draw.arc(s, col, (2 * u, 8 * u, 18 * u, 18 * u), math.pi * 0.5, math.pi * 1.5, max(2, int(4 * u)))
        pygame.draw.arc(s, col, (44 * u, 8 * u, 18 * u, 18 * u), -math.pi * 0.5, math.pi * 0.5, max(2, int(4 * u)))
        rect(col, 28, 36, 8, 12)
        rect(dark, 18, 48, 28, 10, 3)
    elif name == "lock":
        pygame.draw.arc(s, (200, 200, 210), (16 * u, 4 * u, 32 * u, 36 * u), 0, math.pi, max(2, int(6 * u)))
        rect((200, 200, 210), 16, 20, 6, 10)
        rect((200, 200, 210), 42, 20, 6, 10)
        rect(col, 10, 28, 44, 32, 6)
        circle(DARK, (c, 42 * u), 5 * u)
    elif name == "mission":
        rect((240, 240, 250), 10, 6, 44, 54, 6)
        for i in range(3):
            rect(col, 16, 16 + i * 14, 8, 8, 2)
            rect((150, 150, 170), 28, 18 + i * 14, 20, 4, 2)
    elif name == "gear":
        pygame.draw.polygon(s, col, _star_points(c, c, 29 * u, 22 * u, 8, rot=0))
        circle(col, (c, c), 22 * u)
        circle((0, 0, 0, 0), (c, c), 9 * u)
    elif name == "calendar":
        rect((240, 240, 250), 6, 10, 52, 48, 6)
        rect(col, 6, 10, 52, 14, 6)
        for i in range(3):
            for j in range(2):
                rect((150, 150, 170), 12 + i * 15, 30 + j * 12, 10, 8, 2)
    elif name == "play":
        poly(col, [(18, 8), (56, 32), (18, 56)])
    elif name == "pause":
        rect(col, 14, 10, 12, 44, 3)
        rect(col, 38, 10, 12, 44, 3)
    elif name == "home":
        poly(col, [(32, 6), (60, 32), (52, 32), (52, 58), (12, 58), (12, 32), (4, 32)])
        rect(DARK, 26, 40, 12, 18)
    elif name == "retry":
        pygame.draw.arc(s, col, (8 * u, 8 * u, 48 * u, 48 * u), 0.6, math.pi * 2 - 0.2, max(2, int(8 * u)))
        poly(col, [(46, 2), (62, 22), (40, 24)])
    elif name == "cart":
        poly(col, [(4, 10), (14, 10), (20, 40), (54, 40), (60, 18), (16, 18)], 0)
        circle(col, (24 * u, 50 * u), 6 * u)
        circle(col, (50 * u, 50 * u), 6 * u)
    elif name == "upgrade":
        poly(col, [(32, 4), (58, 30), (44, 30), (44, 60), (20, 60), (20, 30), (6, 30)])
        poly(light, [(32, 10), (50, 28), (40, 28), (40, 56), (32, 56)])
    elif name == "back":
        poly(col, [(6, 32), (30, 8), (30, 22), (58, 22), (58, 42), (30, 42), (30, 56)])
    elif name == "distance":
        poly(col, [(10, 58), (24, 6), (40, 6), (54, 58)])
        for i in range(3):
            rect(WHITE, 30, 12 + i * 16, 4, 9)
    elif name == "train":
        rect(col, 10, 6, 44, 46, 10)
        rect((200, 230, 255), 16, 12, 32, 16, 4)
        circle(WHITE, (20 * u, 40 * u), 4 * u)
        circle(WHITE, (44 * u, 40 * u), 4 * u)
        line(DARK, (14, 52), (6, 62), 4)
        line(DARK, (50, 52), (58, 62), 4)
    elif name == "map":
        poly(col, [(4, 12), (22, 6), (42, 14), (60, 8), (60, 52), (42, 58), (22, 50), (4, 56)])
        line(DARK, (22, 6), (22, 50), 2)
        line(DARK, (42, 14), (42, 58), 2)
        circle((240, 60, 60), (32 * u, 30 * u), 6 * u)
    elif name == "event":
        poly(col, _star_points(c, c, 30 * u, 18 * u, 8))
        circle(light, (c, c), 14 * u)
    else:
        circle(col, (c, c), 26 * u)
    return s
