"""BONK! visual identity: colours, fonts and generated rounded-rectangle textures."""

import os

from panda3d.core import Filename, PNMImage, SamplerState, Texture

from ...paths import FONTS_DIR
from ..render.procgeom import hex_color

COLORS = {
    "bg": "#170f3a",
    "panel": "#2a1d63",
    "panel_hi": "#3a2a86",
    "primary": "#ff3d8b",
    "secondary": "#ffd23f",
    "accent": "#18e0c8",
    "blue": "#4aa8ff",
    "purple": "#8a5cff",
    "text": "#ffffff",
    "muted": "#c9c2ff",
    "success": "#3fe08a",
    "danger": "#ff4b5c",
    "dark": "#0d0826",
    "locked": "#5d567f",
}


def c(name, alpha=1.0):
    return hex_color(COLORS.get(name, name), alpha)


class Theme:
    def __init__(self, loader):
        self.loader = loader
        self.fonts = {}
        for key, fname in (("title", "Inter-Black.otf"), ("bold", "Inter-ExtraBold.otf"),
                           ("body", "Inter-SemiBold.otf")):
            path = os.path.join(FONTS_DIR, fname)
            font = loader.loadFont(Filename.fromOsSpecific(path).getFullpath()) if os.path.exists(path) else None
            if font is not None:
                font.setPixelsPerUnit(72)
                font.setPageSize(1024, 1024)
            self.fonts[key] = font
        self._tex = {}

    def font(self, key="body"):
        return self.fonts.get(key)

    def rounded(self, aspect, radius=0.32, gradient=0.18, border=0.0):
        """White rounded-rect texture for a frame of width/height = aspect (tinted by frameColor)."""
        key = (round(aspect, 1), radius, gradient, border)
        if key in self._tex:
            return self._tex[key]
        h = 64
        w = max(8, int(h * max(0.2, aspect)))
        img = PNMImage(w, h, 4)
        r = radius * h
        for y in range(h):
            # top of image = row 0 -> brighter at the top
            shade_k = 1.0 - gradient * (y / (h - 1))
            for x in range(w):
                dx = max(r - x, 0, x - (w - 1 - r))
                dy = max(r - y, 0, y - (h - 1 - r))
                d = (dx * dx + dy * dy) ** 0.5
                a = 1.0 if d <= r - 1 else max(0.0, r - d)
                if border > 0 and (d > r - border * h or x < border * h or x > w - 1 - border * h
                                   or y < border * h or y > h - 1 - border * h):
                    k = 1.0
                else:
                    k = shade_k
                img.setXelA(x, y, k, k, k, a)
        tex = Texture("rounded_%s" % (key,))
        tex.load(img)
        tex.setWrapU(SamplerState.WM_clamp)
        tex.setWrapV(SamplerState.WM_clamp)
        tex.setMinfilter(SamplerState.FT_linear)
        tex.setMagfilter(SamplerState.FT_linear)
        self._tex[key] = tex
        return tex
