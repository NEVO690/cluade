"""Hand-drawn vector icons (pygame primitives) used across the UI."""
import math

import pygame

from ilbrawl.ui import theme

INK = theme.INK


def _o(surf, color, pts, w=0):
    pygame.draw.polygon(surf, INK, [(x + 1, y + 2) for x, y in pts])
    pygame.draw.polygon(surf, color, pts, w)


def shop(surf, r):
    x, y, w, h = r
    bag = pygame.Rect(x + w * 0.18, y + h * 0.32, w * 0.64, h * 0.6)
    pygame.draw.rect(surf, INK, bag.inflate(4, 4), border_radius=6)
    pygame.draw.rect(surf, theme.ORANGE, bag, border_radius=5)
    pygame.draw.arc(surf, INK, (x + w * 0.3, y + h * 0.1, w * 0.4, h * 0.45), 0, math.pi, 5)
    theme.draw_coin(surf, bag.center, int(w * 0.14))


def missions(surf, r):
    x, y, w, h = r
    board = pygame.Rect(x + w * 0.2, y + h * 0.12, w * 0.6, h * 0.8)
    pygame.draw.rect(surf, INK, board.inflate(4, 4), border_radius=5)
    pygame.draw.rect(surf, (240, 236, 220), board, border_radius=4)
    for i in range(3):
        yy = board.y + board.h * (0.28 + i * 0.24)
        pygame.draw.line(surf, theme.GREEN, (board.x + 6, yy), (board.x + 12, yy + 5), 3)
        pygame.draw.line(surf, theme.GREEN, (board.x + 12, yy + 5), (board.x + 20, yy - 5), 3)
        pygame.draw.line(surf, theme.GREY, (board.x + 24, yy), (board.right - 6, yy), 3)


def trophy_road(surf, r):
    theme.draw_trophy(surf, (r[0] + r[2] // 2, r[1] + r[3] // 2 - 2), int(r[2] * 0.3))


def profile(surf, r):
    x, y, w, h = r
    cx = x + w // 2
    pygame.draw.circle(surf, INK, (cx, int(y + h * 0.36)), int(w * 0.2) + 2)
    pygame.draw.circle(surf, theme.CYAN, (cx, int(y + h * 0.36)), int(w * 0.2))
    body = pygame.Rect(x + w * 0.2, y + h * 0.58, w * 0.6, h * 0.34)
    pygame.draw.rect(surf, INK, body.inflate(4, 4), border_radius=int(w * 0.2))
    pygame.draw.rect(surf, theme.CYAN, body, border_radius=int(w * 0.2))


def settings(surf, r):
    x, y, w, h = r
    cx, cy = x + w / 2, y + h / 2
    pts = []
    for i in range(16):
        ang = i * math.pi / 8
        rr = w * (0.42 if i % 2 == 0 else 0.32)
        pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
    _o(surf, (200, 200, 220), pts)
    pygame.draw.circle(surf, INK, (int(cx), int(cy)), int(w * 0.13))


def characters(surf, r):
    x, y, w, h = r
    for i, col in enumerate([theme.RED, theme.BLUE]):
        cx = x + w * (0.36 + i * 0.28)
        cy = y + h * (0.55 - i * 0.06)
        pygame.draw.circle(surf, INK, (int(cx), int(cy)), int(w * 0.24) + 2)
        pygame.draw.circle(surf, col, (int(cx), int(cy)), int(w * 0.24))
        pygame.draw.circle(surf, theme.WHITE, (int(cx + w * 0.07), int(cy - h * 0.04)), int(w * 0.07))
        pygame.draw.circle(surf, INK, (int(cx + w * 0.09), int(cy - h * 0.04)), int(w * 0.035))


def modes(surf, r):
    x, y, w, h = r
    cx, cy = x + w / 2, y + h / 2
    for i, col in enumerate([theme.GREEN, theme.YELLOW, theme.PINK, theme.CYAN]):
        ang = i * math.pi / 2 + math.pi / 4
        px, py = cx + math.cos(ang) * w * 0.2, cy + math.sin(ang) * h * 0.2
        rr = pygame.Rect(0, 0, w * 0.32, h * 0.32)
        rr.center = (px, py)
        pygame.draw.rect(surf, INK, rr.inflate(4, 4), border_radius=5)
        pygame.draw.rect(surf, col, rr, border_radius=4)


def play(surf, r):
    x, y, w, h = r
    _o(surf, theme.WHITE, [(x + w * 0.28, y + h * 0.18), (x + w * 0.82, y + h * 0.5), (x + w * 0.28, y + h * 0.82)])


def back(surf, r, rtl=False):
    x, y, w, h = r
    d = -1 if rtl else 1
    cx = x + w / 2
    pts = [(cx - d * w * 0.3, y + h * 0.5), (cx + d * w * 0.05, y + h * 0.2), (cx + d * w * 0.05, y + h * 0.38),
           (cx + d * w * 0.32, y + h * 0.38), (cx + d * w * 0.32, y + h * 0.62), (cx + d * w * 0.05, y + h * 0.62),
           (cx + d * w * 0.05, y + h * 0.8)]
    _o(surf, theme.WHITE, pts)


def editor(surf, r):
    x, y, w, h = r
    for i in range(3):
        for j in range(3):
            col = [theme.GREEN, theme.darken(theme.PANEL_LIGHT, 0.1), (150, 110, 70)][(i + j * 2) % 3]
            pygame.draw.rect(surf, col, (x + w * 0.14 + i * w * 0.24, y + h * 0.14 + j * h * 0.24, w * 0.22, h * 0.22))
    pygame.draw.line(surf, INK, (x + w * 0.5, y + h * 0.9), (x + w * 0.92, y + h * 0.4), 7)
    pygame.draw.line(surf, theme.YELLOW, (x + w * 0.5, y + h * 0.9), (x + w * 0.92, y + h * 0.4), 4)


def gift(surf, r):
    x, y, w, h = r
    box = pygame.Rect(x + w * 0.16, y + h * 0.4, w * 0.68, h * 0.5)
    pygame.draw.rect(surf, INK, box.inflate(4, 4), border_radius=4)
    pygame.draw.rect(surf, theme.PINK, box, border_radius=4)
    lid = pygame.Rect(x + w * 0.1, y + h * 0.28, w * 0.8, h * 0.16)
    pygame.draw.rect(surf, INK, lid.inflate(4, 4), border_radius=4)
    pygame.draw.rect(surf, theme.lighten(theme.PINK, 0.2), lid, border_radius=4)
    pygame.draw.rect(surf, theme.YELLOW, (x + w * 0.44, y + h * 0.28, w * 0.12, h * 0.62))
    pygame.draw.circle(surf, theme.YELLOW, (int(x + w * 0.38), int(y + h * 0.24)), int(w * 0.1), 4)
    pygame.draw.circle(surf, theme.YELLOW, (int(x + w * 0.62), int(y + h * 0.24)), int(w * 0.1), 4)


def check(surf, r, color=theme.GREEN):
    x, y, w, h = r
    pygame.draw.lines(surf, INK, False, [(x + w * 0.2, y + h * 0.55), (x + w * 0.42, y + h * 0.78), (x + w * 0.82, y + h * 0.28)], 9)
    pygame.draw.lines(surf, color, False, [(x + w * 0.2, y + h * 0.55), (x + w * 0.42, y + h * 0.78), (x + w * 0.82, y + h * 0.28)], 5)


def coin(surf, r):
    theme.draw_coin(surf, (r[0] + r[2] // 2, r[1] + r[3] // 2), int(r[2] * 0.36))


def gem(surf, r):
    theme.draw_gem_icon(surf, (r[0] + r[2] / 2, r[1] + r[3] / 2), r[2] * 0.38)


def lock(surf, r):
    theme.draw_lock(surf, (r[0] + r[2] // 2, r[1] + r[3] // 2), int(r[2] * 0.36))


def close(surf, r):
    x, y, w, h = r
    for a, b in (((0.25, 0.25), (0.75, 0.75)), ((0.75, 0.25), (0.25, 0.75))):
        pygame.draw.line(surf, INK, (x + w * a[0], y + h * a[1] + 2), (x + w * b[0], y + h * b[1] + 2), 9)
        pygame.draw.line(surf, theme.WHITE, (x + w * a[0], y + h * a[1]), (x + w * b[0], y + h * b[1]), 6)


def pause(surf, r):
    x, y, w, h = r
    for i in (0.3, 0.58):
        pygame.draw.rect(surf, INK, (x + w * i - 1, y + h * 0.22 + 2, w * 0.14 + 2, h * 0.56), border_radius=3)
        pygame.draw.rect(surf, theme.WHITE, (x + w * i, y + h * 0.22, w * 0.14, h * 0.56), border_radius=3)


# mode icons -------------------------------------------------------------
def mode_icon(surf, r, mode_id):
    x, y, w, h = r
    cx, cy = x + w / 2, y + h / 2
    if mode_id == "gem_collection":
        theme.draw_gem_icon(surf, (cx, cy), w * 0.36, (180, 90, 255))
    elif mode_id == "solo_survival":
        pygame.draw.circle(surf, INK, (int(cx), int(cy)), int(w * 0.38))
        pygame.draw.circle(surf, theme.GREEN, (int(cx), int(cy)), int(w * 0.34))
        pygame.draw.circle(surf, INK, (int(cx - w * 0.12), int(cy - h * 0.04)), int(w * 0.08))
        pygame.draw.circle(surf, INK, (int(cx + w * 0.12), int(cy - h * 0.04)), int(w * 0.08))
        pygame.draw.rect(surf, INK, (cx - w * 0.04, cy + h * 0.1, w * 0.08, h * 0.12))
    elif mode_id == "team_survival":
        for i, col in enumerate([theme.BLUE, theme.RED]):
            ang = math.radians(45 if i == 0 else 135)
            ex, ey = cx + math.cos(ang) * w * 0.34, cy + math.sin(ang) * h * 0.34
            sx, sy = cx - math.cos(ang) * w * 0.34, cy - math.sin(ang) * h * 0.34
            pygame.draw.line(surf, INK, (sx, sy), (ex, ey), 10)
            pygame.draw.line(surf, col, (sx, sy), (ex, ey), 6)
    elif mode_id == "goal_rush":
        pygame.draw.circle(surf, INK, (int(cx), int(cy)), int(w * 0.36))
        pygame.draw.circle(surf, theme.WHITE, (int(cx), int(cy)), int(w * 0.32))
        pts = [(cx + math.cos(a * 2 * math.pi / 5 - math.pi / 2) * w * 0.13,
                cy + math.sin(a * 2 * math.pi / 5 - math.pi / 2) * w * 0.13) for a in range(5)]
        pygame.draw.polygon(surf, INK, pts)
    elif mode_id == "zone_control":
        pygame.draw.circle(surf, INK, (int(cx), int(cy)), int(w * 0.4), 6)
        pygame.draw.circle(surf, theme.YELLOW, (int(cx), int(cy)), int(w * 0.36), 5)
        pygame.draw.rect(surf, INK, (cx - 2, cy - h * 0.3, 5, h * 0.5))
        _o(surf, theme.RED, [(cx + 2, cy - h * 0.3), (cx + w * 0.26, cy - h * 0.2), (cx + 2, cy - h * 0.1)])
    else:
        play(surf, r)
