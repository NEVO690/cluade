"""Scene base class with RTL-aware layout helpers and shared menu chrome."""
import math

import pygame

from ilbrawl import config
from ilbrawl.ui import icons, text, theme
from ilbrawl.ui.widgets import Button

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H


class Scene:
    music = "menu"
    show_currency = True

    def __init__(self, game):
        self.game = game
        self.widgets = []
        self.modal = None
        self.t = 0.0
        self.build()

    # ------------------------------------------------------------ helpers
    @property
    def rtl(self):
        return self.game.i18n.rtl

    def tr(self, _key, **kw):
        return self.game.i18n.t(_key, **kw)

    def X(self, x, w=0):
        """Mirror an x coordinate (of an element with width w) for RTL layouts."""
        return VW - x - w if self.rtl else x

    def R(self, x, y, w, h):
        return pygame.Rect(self.X(x, w), y, w, h)

    def add(self, w):
        self.widgets.append(w)
        return w

    # ------------------------------------------------------------ lifecycle
    def build(self):
        self.widgets = []

    def rebuild(self):
        self.build()

    def on_language_changed(self):
        self.rebuild()

    def on_enter(self):
        if self.music:
            self.game.audio.play_music(self.music)

    def on_resume(self):
        """Called when the scene above this one is popped."""
        self.rebuild()
        if self.music:
            self.game.audio.play_music(self.music)

    def on_exit(self):
        pass

    def open_dialog(self, dialog):
        self.modal = dialog

    # ------------------------------------------------------------ loop
    def handle_event(self, e):
        if self.modal:
            self.modal.handle_event(e)
            return
        for w in reversed(self.widgets):
            if w.visible and w.handle_event(e):
                return
        self.on_event(e)

    def on_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.back()

    def back(self):
        if len(self.game.scenes) > 1:
            self.game.pop()

    def update(self, dt):
        self.t += dt
        mp = None if self.modal else self.game.mouse_pos
        for w in list(self.widgets):
            w.update(dt, mp)
        if self.modal:
            self.modal.update(dt, self.game.mouse_pos)
            if self.modal.closed:
                self.modal = None

    def draw(self, surf):
        self.draw_background(surf)
        self.draw_content(surf)
        for w in self.widgets:
            if w.visible:
                w.draw(surf)
        self.draw_overlay(surf)
        if self.modal:
            self.modal.draw(surf)

    def draw_background(self, surf):
        draw_menu_background(surf, self.t)

    def draw_content(self, surf):
        pass

    def draw_overlay(self, surf):
        pass

    # ------------------------------------------------------------ shared chrome
    def add_header(self, title_key):
        self.title_key = title_key
        self.add(Button(self.R(18, 14, 70, 60), "", self.back, theme.RED,
                        icon=lambda s, r: icons.back(s, r, self.rtl), radius=14))

    def draw_header(self, surf):
        text.draw(surf, self.tr(self.title_key), (self.X(104), 24), 40, theme.WHITE, "start", outline=3, max_width=640)
        if self.show_currency:
            draw_currency_bar(surf, self.game.profile, self.rtl, self.t)


_vignette = {}


def vignette(size, strength=170):
    """Cached smooth radial vignette for a cinematic, moody frame."""
    key = (size, strength)
    v = _vignette.get(key)
    if v is None:
        w, h = size
        sw, sh = 96, 54
        small = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for y in range(sh):
            for x in range(sw):
                dx = (x + 0.5) / sw * 2 - 1
                dy = (y + 0.5) / sh * 2 - 1
                d = min(1.0, math.sqrt(dx * dx * 0.9 + dy * dy * 1.1) / 1.25)
                small.set_at((x, y), (0, 0, 0, int(strength * max(0.0, d - 0.35) ** 1.6 / 0.65 ** 1.6)))
        v = pygame.transform.smoothscale(small, (w, h))
        _vignette[key] = v
    return v


def draw_menu_background(surf, t):
    surf.blit(theme.vertical_gradient((VW, VH), theme.BG_TOP, theme.BG_BOTTOM), (0, 0))
    layer = pygame.Surface((VW, VH), pygame.SRCALPHA)
    # faint tactical grid
    for x in range(0, VW, 64):
        pygame.draw.line(layer, (120, 140, 170, 14), (x, 0), (x, VH))
    for y in range(0, VH, 64):
        pygame.draw.line(layer, (120, 140, 170, 14), (0, y), (VW, y))
    # drifting embers / dust
    for i in range(26):
        ph = i * 2.3
        x = (i * 211 + t * (8 + i % 7 * 3)) % (VW + 40) - 20
        y = VH - ((i * 137 + t * (14 + i % 5 * 4)) % (VH + 40)) + 20
        a = int(60 + 60 * math.sin(t * 1.5 + ph))
        col = (230, 150, 70, max(0, a)) if i % 3 == 0 else (200, 210, 220, max(0, a // 2))
        pygame.draw.circle(layer, col, (int(x), int(y)), 1 + i % 3)
    surf.blit(layer, (0, 0))
    surf.blit(vignette((VW, VH)), (0, 0))


def draw_currency_bar(surf, profile, rtl, t=0.0):
    items = [("trophy", profile.total_trophies()), ("coin", profile.data["coins"]), ("gem", profile.data["gems"])]
    w = 138
    x = VW - 20 - w if not rtl else 20
    for kind, val in items:
        r = pygame.Rect(x, 18, w, 44)
        theme.draw_panel(surf, r, theme.darken(theme.PANEL, 0.25), theme.PANEL_BORDER, 22, False, 2)
        icx = r.x + 24 if not rtl else r.right - 24
        if kind == "trophy":
            theme.draw_trophy(surf, (icx, r.centery - 2), 13)
        elif kind == "coin":
            theme.draw_coin(surf, (icx, r.centery), 14)
        else:
            theme.draw_gem_icon(surf, (icx, r.centery), 15)
        tx = r.right - 16 if not rtl else r.x + 16
        text.draw(surf, "{:,}".format(val), (tx, r.centery), 22, theme.WHITE, "right" if not rtl else "left",
                  "middle", rtl=False)
        x += -(w + 10) if not rtl else (w + 10)
