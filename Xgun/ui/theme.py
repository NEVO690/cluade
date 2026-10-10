"""Xgun visual identity: palette, fonts and shared UI constants."""
from __future__ import annotations

from panda3d.core import SamplerState

from config import paths
from game.assets import fn


def rgba(hex_color: str, a: float = 1.0) -> tuple[float, float, float, float]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)


BG = rgba("#0B0E1A")
PANEL = rgba("#151A2E", 0.92)
PANEL_LIGHT = rgba("#1F2742", 0.95)
PANEL_HOVER = rgba("#2A3458", 0.98)
BORDER = rgba("#323D66")
PRIMARY = rgba("#7C4DFF")
PRIMARY_HOVER = rgba("#9A75FF")
ACCENT = rgba("#00E5FF")
PINK = rgba("#FF3D71")
GOLD = rgba("#FFC94D")
GREEN = rgba("#2EE59D")
RED = rgba("#FF4D5E")
TEXT = rgba("#F2F4FF")
TEXT_DIM = rgba("#9AA3C7")
TEXT_MUTED = rgba("#69739A")
SHADOW = (0, 0, 0, 0.55)
RARITY = {"common": rgba("#9AA5B1"), "uncommon": rgba("#3DDC84"), "rare": rgba("#2F9BFF"), "epic": rgba("#B44CFF"),
          "legendary": rgba("#FF9F1C")}


class Fonts:
    def __init__(self, loader):
        def load(name):
            font = loader.loadFont(fn(paths.FONTS / name).getFullpath())
            font.setPixelsPerUnit(72)
            font.setMinfilter(SamplerState.FT_linear_mipmap_linear)
            font.setPageSize(1024, 1024)
            return font
        self.regular = load("Inter-Regular.otf")
        self.semibold = load("Inter-SemiBold.otf")
        self.bold = load("Inter-Bold.otf")
        self.black = load("Inter-Black.otf")
