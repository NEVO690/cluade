"""Small preview images of maps for menus and the editor."""
import pygame

from ilbrawl.ui import theme

_cache = {}

MARK_COLORS = {"1": (64, 160, 255), "2": (255, 72, 88), "S": (255, 200, 60), "G": (184, 100, 255),
               "O": (255, 230, 90), "Z": (255, 255, 255), "A": (64, 160, 255), "R": (255, 72, 88)}


def tile_color(c, th):
    if c == "#":
        return tuple(th.get("wall_top", (150, 150, 160)))
    if c == "B":
        return tuple(th.get("bush", (60, 150, 70)))
    if c == "W":
        return tuple(th.get("water", (80, 170, 240)))
    if c in ("C", "X"):
        return tuple(th.get("crate", (180, 130, 80)))
    if c == "P":
        return (130, 140, 160)
    return tuple(th.get("floor_a", (130, 200, 100)))


def thumbnail(mapdef, themes, cell=6, cache=True):
    key = (mapdef.get("id"), cell, tuple(mapdef["tiles"]), mapdef.get("theme"))
    if cache and key in _cache:
        return _cache[key]
    rows = mapdef["tiles"]
    h, w = len(rows), max(len(r) for r in rows)
    th = themes.get(mapdef.get("theme"), {})
    s = pygame.Surface((w * cell, h * cell))
    s.fill(tuple(th.get("floor_a", (130, 200, 100))))
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            r = (x * cell, y * cell, cell, cell)
            if c in MARK_COLORS:
                s.fill(tuple(th.get("floor_a", (130, 200, 100))), r)
                pygame.draw.circle(s, MARK_COLORS[c], (x * cell + cell // 2, y * cell + cell // 2), max(2, cell // 2))
            elif c != ".":
                s.fill(tile_color(c, th), r)
    pygame.draw.rect(s, theme.INK, s.get_rect(), 2)
    if cache:
        _cache[key] = s
    return s
