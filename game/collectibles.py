"""Collectibles: coins, gems, event tokens and power-up pickups."""
import math

import pygame

from . import settings as S
from .utils import shade

COIN, GEM, TOKEN, POWERUP = "coin", "gem", "token", "powerup"


class Collectible:
    __slots__ = ("kind", "x", "y", "z", "value", "alive", "magnet", "phase")

    def __init__(self, kind, x, y, z, value=None):
        self.kind = kind
        self.x = x
        self.y = y
        self.z = z
        self.value = value  # power-up id for POWERUP
        self.alive = True
        self.magnet = False
        self.phase = (z * 0.37) % math.tau

    def update_magnet(self, px, py, pz, dt):
        """Fly toward the player (used by the coin magnet)."""
        k = min(1.0, dt * 12.0)
        self.x += (px - self.x) * k
        self.y += (py - self.y) * k
        self.z += (pz + 0.6 - self.z) * k


class CollectibleRenderer:
    """Draws collectibles; caches power-up bubble sprites."""

    def __init__(self, assets, gamedata):
        self.assets = assets
        self.gamedata = gamedata
        self._bubbles = {}
        self.time = 0.0
        self.token_color = (255, 160, 40)

    def bubble(self, pid):
        surf = self._bubbles.get(pid)
        if surf is None:
            pu = self.gamedata.powerup_by_id.get(pid)
            color = pu["color"] if pu else (255, 255, 255)
            size = 128
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*shade(color, 0.5), 230), (64, 64), 62)
            pygame.draw.circle(surf, (*color, 255), (64, 64), 56)
            pygame.draw.circle(surf, (255, 255, 255, 200), (64, 64), 60, 4)
            icon = self.assets.icon(pu["icon"] if pu else "star", 76, (255, 255, 255))
            surf.blit(icon, (64 - 38, 64 - 38))
            pygame.draw.ellipse(surf, (255, 255, 255, 110), (30, 16, 40, 22))
            self._bubbles[pid] = surf
        return surf

    def queue(self, r, c):
        if not c.alive or not r.visible_range(c.z - 0.2, c.z + 0.2):
            return
        if c.kind == POWERUP:
            bob = math.sin(self.time * 3 + c.phase) * 0.15
            r.billboard(("pu", c.value), self.bubble(c.value), c.x, c.y + bob, c.z, 1.2, anchor="center")
            r.glow(c.x, c.y + bob, c.z + 0.05, 1.3, (120, 120, 120))
        else:
            r.queue(c.z, self._draw_flat, r, c)

    def _draw_flat(self, r, c):
        cam = r.cam
        dz = c.z - cam.z
        if dz < S.NEAR_PLANE:
            return
        s = cam.focal / dz
        sx = cam.hx + (c.x - cam.x) * s
        sy = cam.hy - (c.y - cam.y) * s
        surf = r.surface
        spin = math.cos(self.time * 4.0 + c.phase)
        if c.kind == COIN:
            rad = 0.32 * s
            if rad < 1.2:
                return
            w = max(1.5, abs(spin) * rad)
            edge = r.fog((200, 140, 20), dz)
            face = r.fog(S.COIN_COLOR, dz)
            pygame.draw.ellipse(surf, edge, (sx - w - 1, sy - rad - 1, w * 2 + 2, rad * 2 + 2))
            pygame.draw.ellipse(surf, face, (sx - w * 0.82, sy - rad * 0.82, w * 1.64, rad * 1.64))
            if rad > 5 and w > 3:
                pygame.draw.ellipse(surf, r.fog((255, 245, 180), dz), (sx - w * 0.25, sy - rad * 0.55, w * 0.5, rad * 1.1))
        elif c.kind == GEM:
            rad = 0.42 * s
            if rad < 1.5:
                return
            w = max(2, abs(spin) * rad)
            col = r.fog(S.GEM_COLOR, dz)
            pygame.draw.polygon(surf, r.fog((40, 120, 200), dz),
                                [(sx, sy - rad * 1.1), (sx + w * 1.1, sy - rad * 0.2), (sx, sy + rad * 1.2), (sx - w * 1.1, sy - rad * 0.2)])
            pygame.draw.polygon(surf, col, [(sx, sy - rad), (sx + w, sy - rad * 0.2), (sx, sy + rad), (sx - w, sy - rad * 0.2)])
            pygame.draw.line(surf, (230, 255, 255), (sx - w * 0.6, sy - rad * 0.2), (sx + w * 0.6, sy - rad * 0.2), 1)
            if r.glow_enabled:
                r.draw_glow(c.x, c.y, c.z, 0.9, (40, 90, 110))
        elif c.kind == TOKEN:
            rad = 0.4 * s
            if rad < 1.5:
                return
            w = max(2, abs(spin) * rad)
            col = r.fog(self.token_color, dz)
            pygame.draw.ellipse(surf, r.fog(shade(self.token_color, 0.6), dz), (sx - w - 1, sy - rad - 1, w * 2 + 2, rad * 2 + 2))
            pygame.draw.ellipse(surf, col, (sx - w * 0.85, sy - rad * 0.85, w * 1.7, rad * 1.7))
            if w > 4:
                pts = []
                for i in range(10):
                    rr = rad * (0.55 if i % 2 == 0 else 0.25)
                    a = -math.pi / 2 + i * math.pi / 5
                    pts.append((sx + math.cos(a) * rr * (w / rad), sy + math.sin(a) * rr))
                pygame.draw.polygon(surf, r.fog((255, 255, 255), dz), pts)
