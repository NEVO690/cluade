"""Animated intro with the IL Brawl logo."""
import math

import pygame

from ilbrawl import config
from ilbrawl.engine.scene import Scene
from ilbrawl.ui import logo, text, theme

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H


class SplashScene(Scene):
    show_currency = False

    def on_event(self, e):
        if e.type in (pygame.MOUSEBUTTONUP, pygame.KEYDOWN) and self.t > 0.4:
            self._go()

    def update(self, dt):
        super().update(dt)
        if self.t > 2.6:
            self._go()

    def _go(self):
        from ilbrawl.menus.main_menu import MainMenuScene
        self.game.replace(MainMenuScene(self.game))

    def draw_content(self, surf):
        k = min(1.0, self.t / 0.6)
        ease = 1 - (1 - k) ** 3
        scale = 0.5 + 0.6 * ease + 0.04 * math.sin(self.t * 6) * (1 - k)
        logo.draw_logo(surf, (VW // 2, VH // 2 - 30), scale, self.t)
        if self.t > 0.8:
            a = min(1.0, (self.t - 0.8) * 2)
            col = theme.lerp_color(theme.BG_BOTTOM, theme.WHITE, a)
            text.draw(surf, self.tr("splash.tagline"), (VW // 2, VH // 2 + 110), 28, col, "center", "middle", outline=3)
        text.draw(surf, "v" + config.VERSION, (VW - 12, VH - 10), 14, theme.TEXT_DIM, "right", "bottom", rtl=False)
