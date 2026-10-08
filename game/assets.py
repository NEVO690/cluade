"""Asset manager: fonts, images and icons with graceful fallbacks.

Real art can be dropped into ``assets/`` at any time:

* ``assets/fonts/main.ttf``            - UI font (any .ttf works)
* ``assets/images/icons/<name>.png``   - replaces a procedural icon
* ``assets/images/characters/<id>/<pose>_<n>.png`` - character sprite frames
  (poses: run, jump, slide, idle) - see README.

Missing files are never fatal: procedural placeholders are used instead.
"""
import os

import pygame

from . import settings as S
from .icons import draw_icon
from .utils import log, warn


class Assets:
    def __init__(self):
        self._fonts = {}
        self._images = {}
        self._missing = set()
        self._icons = {}
        self._text_cache = {}
        self._font_path = self._find_font()
        self._sprite_frames = {}

    # ------------------------------------------------------------------
    # Fonts & text
    # ------------------------------------------------------------------
    def _find_font(self):
        try:
            files = sorted(f for f in os.listdir(S.FONTS_DIR) if f.lower().endswith((".ttf", ".otf")))
        except OSError:
            return None
        if "main.ttf" in files:
            return os.path.join(S.FONTS_DIR, "main.ttf")
        return os.path.join(S.FONTS_DIR, files[0]) if files else None

    def font(self, size, bold=True):
        key = (size, bold)
        f = self._fonts.get(key)
        if f is None:
            f = None
            if self._font_path:
                try:
                    f = pygame.font.Font(self._font_path, size)
                except (OSError, pygame.error) as e:
                    warn(f"Could not load font {os.path.basename(self._font_path)}: {e}")
                    self._font_path = None
            if f is None:
                # pygame's bundled default font is always available.
                f = pygame.font.Font(None, int(size * 1.25))
                f.set_bold(bold)
            self._fonts[key] = f
        return f

    def text(self, text, size, color=(255, 255, 255), bold=True, shadow=False):
        key = (text, size, color, bold, shadow)
        surf = self._text_cache.get(key)
        if surf is None:
            if len(self._text_cache) > 1500:
                self._text_cache.clear()
            font = self.font(size, bold)
            main = font.render(str(text), True, color)
            if shadow:
                off = max(1, size // 14)
                sh = font.render(str(text), True, (0, 0, 0))
                sh.set_alpha(150)
                surf = pygame.Surface((main.get_width() + off, main.get_height() + off), pygame.SRCALPHA)
                surf.blit(sh, (off, off))
                surf.blit(main, (0, 0))
            else:
                surf = main
            self._text_cache[key] = surf
        return surf

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------
    def image(self, rel_path):
        if rel_path in self._images:
            return self._images[rel_path]
        if rel_path in self._missing:
            return None
        path = os.path.join(S.IMAGES_DIR, rel_path)
        img = None
        if os.path.isfile(path):
            try:
                img = pygame.image.load(path)
                img = img.convert_alpha() if pygame.display.get_surface() else img
            except (pygame.error, OSError) as e:
                warn(f"Could not load image {rel_path}: {e} - using placeholder")
                img = None
        if img is None:
            self._missing.add(rel_path)
            return None
        self._images[rel_path] = img
        return img

    def icon(self, name, size, color=None):
        key = (name, size, color)
        surf = self._icons.get(key)
        if surf is None:
            img = self.image(f"icons/{name}.png")
            if img is not None:
                surf = pygame.transform.smoothscale(img, (size, size))
            else:
                try:
                    surf = draw_icon(name, size, color)
                except (pygame.error, ValueError, TypeError) as e:
                    log.error("Icon %s failed: %s", name, e)
                    surf = pygame.Surface((size, size), pygame.SRCALPHA)
            self._icons[key] = surf
        return surf

    def sprite_frames(self, character_id, pose):
        """Return a list of sprite frames for a character pose, or [] if none exist."""
        key = (character_id, pose)
        frames = self._sprite_frames.get(key)
        if frames is None:
            frames = []
            for i in range(16):
                img = self.image(f"characters/{character_id}/{pose}_{i}.png")
                if img is None:
                    break
                frames.append(img)
            self._sprite_frames[key] = frames
        return frames
