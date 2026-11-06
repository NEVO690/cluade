"""Drawings for profile icons and other cosmetics."""
import math

import pygame

from ilbrawl.characters import sprites
from ilbrawl.ui import theme

INK = theme.INK


def draw_shape(surf, shape, cx, cy, r, color):
    color = tuple(color[:3])
    if shape == "star":
        theme.draw_star(surf, (cx, cy), r, color)
    elif shape == "rocket":
        body = [(cx, cy - r), (cx + r * 0.42, cy - r * 0.2), (cx + r * 0.42, cy + r * 0.55), (cx - r * 0.42, cy + r * 0.55),
                (cx - r * 0.42, cy - r * 0.2)]
        for s in (-1, 1):
            fin = [(cx + s * r * 0.42, cy + r * 0.1), (cx + s * r * 0.8, cy + r * 0.7), (cx + s * r * 0.42, cy + r * 0.55)]
            pygame.draw.polygon(surf, INK, fin)
            pygame.draw.polygon(surf, theme.darken(color, 0.2), fin)
        pygame.draw.polygon(surf, INK, [(x, y + 2) for x, y in body])
        pygame.draw.polygon(surf, (235, 235, 245), body)
        pygame.draw.circle(surf, INK, (int(cx), int(cy - r * 0.1)), int(r * 0.24))
        pygame.draw.circle(surf, (120, 200, 255), (int(cx), int(cy - r * 0.1)), int(r * 0.17))
        flame = [(cx - r * 0.25, cy + r * 0.55), (cx, cy + r * 1.0), (cx + r * 0.25, cy + r * 0.55)]
        pygame.draw.polygon(surf, color, flame)
    elif shape == "diamond":
        theme.draw_gem_icon(surf, (cx, cy), r, color)
    elif shape == "lightning":
        pts = [(cx + r * 0.2, cy - r), (cx - r * 0.5, cy + r * 0.1), (cx - r * 0.05, cy + r * 0.1), (cx - r * 0.25, cy + r),
               (cx + r * 0.5, cy - r * 0.15), (cx + r * 0.05, cy - r * 0.15)]
        pygame.draw.polygon(surf, INK, [(x + 2, y + 2) for x, y in pts])
        pygame.draw.polygon(surf, color, pts)
    elif shape == "heart":
        rr = int(r * 0.5)
        for s in (-1, 1):
            pygame.draw.circle(surf, INK, (int(cx + s * r * 0.42), int(cy - r * 0.2)), rr + 3)
        pygame.draw.polygon(surf, INK, [(cx - r * 0.95, cy - r * 0.05), (cx, cy + r * 0.95), (cx + r * 0.95, cy - r * 0.05)])
        for s in (-1, 1):
            pygame.draw.circle(surf, color, (int(cx + s * r * 0.42), int(cy - r * 0.2)), rr)
        pygame.draw.polygon(surf, color, [(cx - r * 0.88, cy - r * 0.05), (cx, cy + r * 0.82), (cx + r * 0.88, cy - r * 0.05)])
    elif shape == "planet":
        pygame.draw.circle(surf, INK, (int(cx), int(cy)), int(r * 0.66))
        pygame.draw.circle(surf, color, (int(cx), int(cy)), int(r * 0.6))
        pygame.draw.ellipse(surf, INK, (cx - r, cy - r * 0.22, r * 2, r * 0.44), 5)
        pygame.draw.ellipse(surf, theme.YELLOW, (cx - r, cy - r * 0.22, r * 2, r * 0.44), 3)
    elif shape == "crown":
        w = r * 1.7
        x0 = cx - w / 2
        pts = [(x0, cy + r * 0.5), (x0, cy - r * 0.4), (x0 + w * 0.25, cy), (cx, cy - r * 0.7), (x0 + w * 0.75, cy),
               (x0 + w, cy - r * 0.4), (x0 + w, cy + r * 0.5)]
        pygame.draw.polygon(surf, INK, [(x, y + 3) for x, y in pts])
        pygame.draw.polygon(surf, color, pts)
    elif shape == "flame":
        pts = [(cx, cy - r), (cx + r * 0.6, cy), (cx + r * 0.5, cy + r * 0.6), (cx, cy + r * 0.85),
               (cx - r * 0.5, cy + r * 0.6), (cx - r * 0.6, cy)]
        pygame.draw.polygon(surf, INK, [(x, y + 3) for x, y in pts])
        pygame.draw.polygon(surf, color, pts)
        inner = [(cx, cy - r * 0.2), (cx + r * 0.3, cy + r * 0.3), (cx, cy + r * 0.65), (cx - r * 0.3, cy + r * 0.3)]
        pygame.draw.polygon(surf, theme.YELLOW, inner)


def draw_profile_icon(surf, rect, icon_id, gd, bg=True):
    rect = pygame.Rect(rect)
    if bg:
        pygame.draw.rect(surf, INK, rect.inflate(6, 6), border_radius=14)
        pygame.draw.rect(surf, (48, 56, 70), rect, border_radius=12)
    if icon_id and icon_id.startswith("char:"):
        cid = icon_id[5:]
        if cid in gd.characters:
            por = sprites.portrait(gd.characters[cid]["style"], rect.w + 10, key=(cid, None))
            surf.blit(por, (rect.centerx - por.get_width() // 2, rect.centery - por.get_height() // 2 + 2))
            return
    for c in gd.cosmetics.get("icons", []):
        if c["id"] == icon_id:
            draw_shape(surf, c["shape"], rect.centerx, rect.centery, rect.w * 0.34, c["color"])
            return
    theme.draw_star(surf, rect.center, rect.w * 0.34)


def name_color(gd, cid):
    for c in gd.cosmetics.get("name_colors", []):
        if c["id"] == cid:
            return tuple(c["color"])
    return (255, 255, 255)
