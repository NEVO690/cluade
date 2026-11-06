"""Stacked, animated pop-up notifications."""
import pygame

from ilbrawl import config
from ilbrawl.ui import text, theme


class Toasts:
    def __init__(self):
        self.items = []  # [message, color, time_left, total]

    def push(self, message, color=theme.GREEN, duration=2.6):
        self.items.append([message, color, duration, duration])
        self.items = self.items[-4:]

    def update(self, dt):
        for it in self.items:
            it[2] -= dt
        self.items = [it for it in self.items if it[2] > 0]

    def draw(self, surf):
        y = 92
        for msg, col, left, total in self.items:
            age = total - left
            a = min(1.0, age * 6, left * 3)
            s = text.render(msg, 22, theme.WHITE, True, 2)
            w = s.get_width() + 48
            r = pygame.Rect(0, 0, w, 50)
            r.center = (config.VIRTUAL_W // 2, int(y - (1 - min(1.0, age * 6)) * 20))
            panel = pygame.Surface(r.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, theme.INK, panel.get_rect(), border_radius=25)
            pygame.draw.rect(panel, col, panel.get_rect().inflate(-6, -6), border_radius=22)
            panel.blit(s, (24, (r.h - s.get_height()) // 2))
            panel.set_alpha(int(255 * a))
            surf.blit(panel, r.topleft)
            y += 58
