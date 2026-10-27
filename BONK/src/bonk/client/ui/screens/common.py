"""Shared building blocks for screens."""

from direct.gui.DirectGui import DirectFrame

from ..screen_manager import Screen
from ..theme import c
from ..widgets import Button, ProgressBar, label, panel


class BaseScreen(Screen):
    scene_offset = 1.3

    def header(self, title, back=True, coins=True, subtitle=None):
        # Dark strip so the title stays readable over the bright 3D sky.
        strip = DirectFrame(parent=self.root, frameColor=c("bg", 0.72), frameSize=(-3, 3, 0.7, 1.05))
        strip.setTransparency(1)
        label(self.root, self.theme, title, (-1.62, 0.83), 0.1, "text", "title", "left")
        if subtitle:
            label(self.root, self.theme, subtitle, (-1.62, 0.755), 0.04, "muted", "bold", "left")
        if back:
            Button(self.root, self.theme, "< BACK", (-1.45, -0.88), (0.36, 0.1), self.app.screens.back,
                   color="panel_hi", scale=0.045)
        if coins:
            self.coin_badge = CoinBadge(self.root, self.theme, (1.42, 0.86))
            self.coin_badge.set(self.app.profile.currency.balance)

    def refresh_coins(self):
        if getattr(self, "coin_badge", None) is not None:
            self.coin_badge.set(self.app.profile.currency.balance)


class CoinBadge:
    def __init__(self, parent, theme, pos):
        self.frame = panel(parent, theme, (-0.28, 0.28, -0.05, 0.05), "dark", 0.75, 0.05, shadow=False,
                           pos=(pos[0], 0, pos[1]))
        coin = DirectFrame(parent=self.frame, frameColor=c("secondary"), frameSize=(-0.03, 0.03, -0.03, 0.03),
                           frameTexture=theme.rounded(1.0, 0.5, 0.2), pos=(-0.21, 0, 0))
        coin.setTransparency(1)
        label(coin, theme, "B", (0, -0.012), 0.035, "dark", "title", shadow=False)
        self.lab = label(self.frame, theme, "0", (0.2, -0.018), 0.05, "secondary", "bold", "right")

    def set(self, value):
        self.lab["text"] = "{:,}".format(value)


def player_card(parent, theme, profile, pos=(1.05, 0.62), width=1.1):
    """Name, title, level + XP bar, rank and coins."""
    x, y = pos
    w = width / 2
    p = panel(parent, theme, (-w, w, -0.2, 0.2), "panel", 0.88, 0.08, pos=(x, 0, y))
    label(p, theme, profile.name, (-w + 0.05, 0.08), 0.065, "text", "title", "left")
    title = profile.titles.equipped_name()
    label(p, theme, title or "No title equipped", (-w + 0.05, 0.02), 0.035,
          "secondary" if title else "muted", "bold", "left")
    lvl = profile.xp.level
    label(p, theme, "LV %d" % lvl, (-w + 0.05, -0.085), 0.045, "accent", "title", "left")
    ProgressBar(p, theme, (-w + 0.26, w - 0.05, -0.1, -0.06), profile.xp.progress_fraction(), "accent")
    need = profile.xp.xp_to_next()
    label(p, theme, "%d / %d XP" % (profile.xp.xp, need) if need else "MAX LEVEL", (w - 0.05, -0.155), 0.03,
          "muted", "body", "right")
    tier = profile.ranks.tier
    label(p, theme, tier["id"], (w - 0.05, 0.08), 0.045, tier["color"], "title", "right")
    label(p, theme, "%d RP" % profile.ranks.points, (w - 0.05, 0.03), 0.032, "muted", "body", "right")
    return p
