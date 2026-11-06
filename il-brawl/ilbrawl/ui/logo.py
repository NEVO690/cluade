"""The original IL Brawl logo, drawn procedurally."""
import math

import pygame

from ilbrawl.engine import assets
from ilbrawl.ui import theme

_cache = {}


def _word(txt, size, top, bottom, outline):
    font = assets.get().font(size, True)
    base = font.render(txt, True, top)
    low = font.render(txt, True, bottom)
    ink = font.render(txt, True, theme.INK)
    w, h = base.get_width() + outline * 2, base.get_height() + outline * 2 + 8
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for dx in range(-outline, outline + 1, 2):
        for dy in range(-outline, outline + 1, 2):
            if dx * dx + dy * dy <= outline * outline + 2:
                s.blit(ink, (outline + dx, outline + dy + 8))
    s.blit(base, (outline, outline))
    half = base.get_height() // 2 + 4
    s.blit(low, (outline, outline + half), pygame.Rect(0, half, low.get_width(), low.get_height() - half))
    shine = font.render(txt, True, theme.lighten(top, 0.6))
    s.blit(shine, (outline, outline), pygame.Rect(0, 0, shine.get_width(), max(1, base.get_height() // 4)))
    return s


def logo_surface(scale=1.0):
    key = round(scale, 2)
    s = _cache.get(key)
    if s is not None:
        return s
    big = int(118 * scale)
    word = _word("BRAWL", big, (232, 214, 170), (178, 118, 48), max(4, int(9 * scale)))
    badge_h = int(word.get_height() * 0.92)
    badge_w = int(badge_h * 1.05)
    W = word.get_width() + badge_w + int(30 * scale)
    H = max(word.get_height(), badge_h) + int(40 * scale)
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    # IL shield badge
    bx, by = int(10 * scale), int(14 * scale)
    pts = [(bx, by + badge_h * 0.12), (bx + badge_w * 0.5, by), (bx + badge_w, by + badge_h * 0.12),
           (bx + badge_w * 0.92, by + badge_h * 0.72), (bx + badge_w * 0.5, by + badge_h),
           (bx + badge_w * 0.08, by + badge_h * 0.72)]
    pygame.draw.polygon(s, theme.INK, [(x, y + 8 * scale) for x, y in pts])
    pygame.draw.polygon(s, theme.INK, pts)
    inner = [(x + (bx + badge_w / 2 - x) * 0.12, y + (by + badge_h / 2 - y) * 0.12) for x, y in pts]
    pygame.draw.polygon(s, (54, 66, 82), inner)
    hl = [inner[0], inner[1], inner[2], (inner[2][0], inner[2][1] + badge_h * 0.18), (inner[0][0], inner[0][1] + badge_h * 0.18)]
    pygame.draw.polygon(s, (92, 106, 126), hl)
    il = _word("IL", int(big * 0.62), (236, 190, 90), (190, 130, 50), max(3, int(6 * scale)))
    s.blit(il, (bx + badge_w / 2 - il.get_width() / 2, by + badge_h / 2 - il.get_height() / 2 + 4 * scale))
    s.blit(word, (bx + badge_w + int(14 * scale), int(10 * scale)))
    _cache[key] = s
    return s


def draw_logo(surf, center, scale=1.0, t=0.0):
    s = logo_surface(scale)
    cx, cy = center
    # soft amber glow behind the logo
    glow = pygame.Surface((int(s.get_width() * 1.4), int(s.get_height() * 1.4)), pygame.SRCALPHA)
    for i in range(6):
        f = 1 - i / 6
        pygame.draw.ellipse(glow, (220, 140, 60, 10), glow.get_rect().inflate(-int(glow.get_width() * (1 - f)),
                                                                             -int(glow.get_height() * (1 - f))))
    surf.blit(glow, (cx - glow.get_width() / 2, cy - glow.get_height() / 2))
    bob = math.sin(t * 2) * 4 * scale
    rot = math.sin(t * 1.3) * 1.5
    img = pygame.transform.rotozoom(s, rot, 1.0) if abs(rot) > 0.05 else s
    surf.blit(img, (cx - img.get_width() / 2, cy - img.get_height() / 2 + bob))
    for i in range(4):
        a = t * 1.5 + i * 1.6
        sx = cx + math.cos(a) * s.get_width() * 0.52
        sy = cy + math.sin(a * 1.3) * s.get_height() * 0.5
        pygame.draw.circle(surf, (240, 170, 80), (int(sx), int(sy)), max(1, int(2 + math.sin(t * 4 + i))))
