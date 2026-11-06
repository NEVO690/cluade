"""Main game engine: window, scene stack, event routing, scaling and the frame loop."""
import os
import traceback

import pygame

from ilbrawl import config
from ilbrawl.audio import audio as audio_mod
from ilbrawl.data_loader import GameData
from ilbrawl.engine import assets as assets_mod
from ilbrawl.localization import i18n as i18n_mod
from ilbrawl.progression.profile import Profile
from ilbrawl.save.save_manager import SaveManager
from ilbrawl.settings.settings import Settings
from ilbrawl.ui import text, theme
from ilbrawl.ui.toast import Toasts

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H


class Game:
    def __init__(self):
        pygame.init()
        self.save_manager = SaveManager()
        self.settings = Settings(self.save_manager)
        self.i18n = i18n_mod.I18n(self.settings["language"])
        i18n_mod.set_instance(self.i18n)
        self.window = None
        self.scale = 1.0
        self.offset = (0, 0)
        self.apply_display()
        self.assets = assets_mod.Assets()
        assets_mod.set_instance(self.assets)
        self.audio = audio_mod.AudioManager(self.settings)
        audio_mod.set_instance(self.audio)
        self.data = GameData.load()
        self.profile = Profile(self.save_manager, self.data)
        self.canvas = pygame.Surface((VW, VH))
        self.scenes = []
        self.toasts = Toasts()
        self.clock = pygame.time.Clock()
        self.running = True
        self.mouse_pos = (0, 0)
        self.fade = 0.0
        self.fps = 60.0
        self.time = 0.0

    # ------------------------------------------------------------ display
    def apply_display(self):
        w, h = self.settings["resolution"]
        flags = 0
        if self.settings["fullscreen"]:
            flags |= pygame.FULLSCREEN
            try:
                sizes = pygame.display.get_desktop_sizes()
                if sizes:
                    w, h = sizes[0]
            except (pygame.error, AttributeError):
                pass
        else:
            flags |= pygame.RESIZABLE
        try:
            self.window = pygame.display.set_mode((w, h), flags)
        except pygame.error:
            self.window = pygame.display.set_mode((1280, 720))
        pygame.display.set_caption(config.GAME_TITLE)
        self._set_icon()
        self._compute_scale()

    def _set_icon(self):
        try:
            icon = pygame.Surface((64, 64), pygame.SRCALPHA)
            pts = [(6, 10), (32, 2), (58, 10), (54, 44), (32, 62), (10, 44)]
            pygame.draw.polygon(icon, theme.INK, pts)
            pygame.draw.polygon(icon, (64, 148, 255), [(12, 14), (32, 8), (52, 14), (49, 42), (32, 56), (15, 42)])
            pygame.draw.rect(icon, theme.WHITE, (20, 18, 7, 28))
            pygame.draw.rect(icon, theme.WHITE, (32, 18, 7, 28))
            pygame.draw.rect(icon, theme.WHITE, (32, 39, 14, 7))
            pygame.display.set_icon(icon)
        except pygame.error:
            pass

    def _compute_scale(self):
        ww, wh = self.window.get_size()
        self.scale = min(ww / VW, wh / VH)
        sw, sh = int(VW * self.scale), int(VH * self.scale)
        self.offset = ((ww - sw) // 2, (wh - sh) // 2)

    def to_virtual(self, pos):
        x = (pos[0] - self.offset[0]) / self.scale
        y = (pos[1] - self.offset[1]) / self.scale
        return (int(x), int(y))

    # ------------------------------------------------------------ scenes
    @property
    def scene(self):
        return self.scenes[-1] if self.scenes else None

    def push(self, scene):
        self.scenes.append(scene)
        self.fade = 1.0
        scene.on_enter()

    def replace(self, scene):
        if self.scenes:
            self.scenes.pop().on_exit()
        self.push(scene)

    def pop(self):
        if len(self.scenes) > 1:
            self.scenes.pop().on_exit()
            self.fade = 1.0
            self.scene.on_resume()

    def pop_to_root(self):
        while len(self.scenes) > 1:
            self.scenes.pop().on_exit()
        self.fade = 1.0
        self.scene.on_resume()

    def set_language(self, code):
        if self.i18n.set_language(code):
            self.settings.set("language", code)
            text._cache.clear()
            for s in self.scenes:
                s.on_language_changed()

    def quit(self):
        self.profile.save()
        self.settings.save()
        self.running = False

    # ------------------------------------------------------------ loop
    def _translate_event(self, e):
        if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            d = dict(e.__dict__)
            d["pos"] = self.to_virtual(e.pos)
            ne = pygame.event.Event(e.type, d)
            if e.type == pygame.MOUSEBUTTONDOWN and e.button in (4, 5):
                return None  # legacy wheel buttons; MOUSEWHEEL handles scrolling
            if e.type == pygame.MOUSEBUTTONUP and e.button in (4, 5):
                return None
            return ne
        if e.type == pygame.MOUSEWHEEL:
            d = dict(e.__dict__)
            d["vpos"] = self.mouse_pos
            return pygame.event.Event(e.type, d)
        return e

    def step(self, dt):
        self.time += dt
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.quit()
                return
            if e.type == pygame.VIDEORESIZE and not self.settings["fullscreen"]:
                try:
                    self.window = pygame.display.set_mode((max(480, e.w), max(270, e.h)), pygame.RESIZABLE)
                except pygame.error:
                    pass
                self._compute_scale()
                continue
            if e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                self.settings.set("fullscreen", not self.settings["fullscreen"])
                self.apply_display()
                continue
            e = self._translate_event(e)
            if e is None:
                continue
            if hasattr(e, "pos") and e.type == pygame.MOUSEMOTION:
                self.mouse_pos = e.pos
            if self.scene:
                self.scene.handle_event(e)
        if not self.running:
            return
        self.mouse_pos = self.to_virtual(pygame.mouse.get_pos())
        scene = self.scene
        if scene:
            scene.update(dt)
        self.toasts.update(dt)
        self.fade = max(0.0, self.fade - dt * 4)
        self.render()

    def render(self):
        c = self.canvas
        if self.scene:
            self.scene.draw(c)
        self.toasts.draw(c)
        if self.fade > 0:
            shade = pygame.Surface((VW, VH), pygame.SRCALPHA)
            shade.fill((14, 8, 36, int(255 * self.fade)))
            c.blit(shade, (0, 0))
        if self.settings["show_fps"]:
            text.draw(c, "FPS %d" % self.fps, (8, VH - 26), 16, theme.WHITE, "left", rtl=False)
        self.window.fill((0, 0, 0))
        sw, sh = int(VW * self.scale), int(VH * self.scale)
        if (sw, sh) == (VW, VH):
            self.window.blit(c, self.offset)
        else:
            self.window.blit(pygame.transform.smoothscale(c, (sw, sh)), self.offset)
        pygame.display.flip()

    def run(self):
        from ilbrawl.menus.splash import SplashScene
        self.push(SplashScene(self))
        while self.running:
            ms = self.clock.tick(config.FPS_CAP)
            self.fps = self.clock.get_fps()
            dt = min(0.05, ms / 1000.0)
            try:
                self.step(dt)
            except Exception:  # never lose progress to an unexpected error
                self._log_crash()
                self.profile.save()
                raise
        self.profile.save()
        pygame.quit()

    def _log_crash(self):
        try:
            os.makedirs(config.LOG_DIR, exist_ok=True)
            with open(os.path.join(config.LOG_DIR, "crash.log"), "a", encoding="utf-8") as f:
                f.write(traceback.format_exc() + "\n")
        except OSError:
            pass
