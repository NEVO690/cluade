"""Asset loading with graceful fallbacks so missing files never crash the game."""
import os

import pygame

from ilbrawl import config

_FONT_FILES = {
    False: ["DejaVuSans.ttf"],
    True: ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf"],
}
# Windows system fonts that cover Hebrew, Arabic and Cyrillic
_SYSTEM_FALLBACKS = [
    r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahomabd.ttf", r"C:\Windows\Fonts\tahoma.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


class Assets:
    def __init__(self):
        self._fonts = {}
        self._images = {}
        self._font_path = {True: self._find_font(True), False: self._find_font(False)}

    @staticmethod
    def _find_font(bold):
        for name in _FONT_FILES[bold]:
            p = os.path.join(config.FONT_DIR, name)
            if os.path.exists(p):
                return p
        for p in _SYSTEM_FALLBACKS:
            if os.path.exists(p):
                return p
        return None  # pygame default font

    def font(self, size, bold=True):
        key = (int(size), bool(bold))
        f = self._fonts.get(key)
        if f is None:
            try:
                f = pygame.font.Font(self._font_path[bool(bold)], int(size))
            except (OSError, pygame.error, TypeError):
                f = pygame.font.Font(None, int(size))
            self._fonts[key] = f
        return f

    def image(self, rel_path, fallback_size=(32, 32)):
        if rel_path in self._images:
            return self._images[rel_path]
        path = os.path.join(config.ASSET_DIR, rel_path)
        try:
            img = pygame.image.load(path).convert_alpha()
        except (OSError, pygame.error, FileNotFoundError):
            img = pygame.Surface(fallback_size, pygame.SRCALPHA)
            img.fill((255, 0, 255, 160))
        self._images[rel_path] = img
        return img


_INSTANCE = None


def set_instance(a):
    global _INSTANCE
    _INSTANCE = a


def get():
    return _INSTANCE
