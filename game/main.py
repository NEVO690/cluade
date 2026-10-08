"""Application bootstrap, main loop and scene management."""
import os
import sys
import time
import traceback

import pygame

from . import settings as S
from .assets import Assets
from .audio import AudioManager
from .database import GameData
from .events import EventManager
from .gameplay import GameScene
from .menus import (LoadingScene, MainMenu, LockerScene, ShopScene, UpgradesScene, MissionsScene,
                    EventsScene, AchievementsScene, SettingsScene, SeasonScene)
from .missions import MissionManager
from .progression import Progression, Achievements, DailyRewards
from .save_system import SaveSystem, SettingsStore
from .scenery import SpriteBank, Sky
from .season import SeasonPass
from .offers import Offers
from .shop import Economy, Shop
from .ui import Toasts
from .utils import log, setup_logging

FADE_TIME = 0.18


class App:
    def __init__(self):
        setup_logging()
        log.info("Starting %s %s (pygame %s, Python %s)", S.TITLE, S.VERSION, pygame.version.ver, sys.version.split()[0])
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
        except pygame.error:
            pass
        pygame.init()
        self.data = GameData()
        self.settings = SettingsStore(self.data.default_settings)
        self.settings.load()
        self.save = SaveSystem(self.data)
        self.save.load()
        self.screen = self._create_window()
        self.clock = pygame.time.Clock()
        self.assets = Assets()
        self.audio = AudioManager(self.settings)
        self.economy = Economy(self.data, self.save)
        self.progression = Progression(self.data, self.save, self.economy)
        self.achievements = Achievements(self.data, self.save, self.economy, self.progression)
        self.daily = DailyRewards(self.data, self.save, self.economy, self.progression)
        self.events = EventManager(self.data, self.save, self.settings, self.economy, self.progression)
        self.economy.events = self.events
        self.season = SeasonPass(self.data, self.save, self.economy, self.progression)
        self.offers = Offers(self.data, self.save, self.economy, self.progression)
        self.missions = MissionManager(self.data, self.save, self.economy, self.progression, self.events)
        self.shop = Shop(self.data, self.economy)
        self.toasts = Toasts(self.assets)
        self.sprites = SpriteBank(self.assets)
        self.sky = Sky()
        self.economy.listeners.append(self._on_economy_event)
        self.rebuild_keymap()
        self.scenes = {
            "loading": LoadingScene(self),
            "menu": MainMenu(self),
            "game": GameScene(self),
            "locker": LockerScene(self),
            "shop": ShopScene(self),
            "upgrades": UpgradesScene(self),
            "missions": MissionsScene(self),
            "events": EventsScene(self),
            "achievements": AchievementsScene(self),
            "settings": SettingsScene(self),
            "season": SeasonScene(self),
        }
        self.scene_name = "loading"
        self.scene = self.scenes["loading"]
        self._pending = None
        self._fade = 0.0
        self._fade_dir = 0
        self.running = True

    # ------------------------------------------------------------------
    # Window
    # ------------------------------------------------------------------
    def _create_window(self):
        flags = pygame.SCALED | pygame.RESIZABLE
        if self.settings["fullscreen"]:
            flags |= pygame.FULLSCREEN
        vsync = 1 if self.settings["vsync"] else 0
        pygame.display.set_caption(S.TITLE)
        try:
            screen = pygame.display.set_mode((S.SCREEN_W, S.SCREEN_H), flags, vsync=vsync)
        except pygame.error as e:
            log.warning("Display mode with vsync=%s failed (%s) - retrying without", vsync, e)
            try:
                screen = pygame.display.set_mode((S.SCREEN_W, S.SCREEN_H), flags)
            except pygame.error:
                screen = pygame.display.set_mode((S.SCREEN_W, S.SCREEN_H))
        try:
            icon = pygame.Surface((32, 32), pygame.SRCALPHA)
            pygame.draw.circle(icon, S.UI_ACCENT, (16, 16), 15)
            pygame.draw.polygon(icon, (30, 30, 40), [(11, 8), (25, 16), (11, 24)])
            pygame.display.set_icon(icon)
        except pygame.error:
            pass
        return screen

    def apply_display(self):
        want = self.settings["fullscreen"]
        is_full = bool(pygame.display.get_surface().get_flags() & pygame.FULLSCREEN)
        if want != is_full:
            try:
                pygame.display.toggle_fullscreen()
            except pygame.error as e:
                log.warning("Fullscreen toggle failed: %s", e)
                self.toasts.push("Fullscreen is not supported here", "gear", S.UI_BAD)

    # ------------------------------------------------------------------
    # Input mapping
    # ------------------------------------------------------------------
    def rebuild_keymap(self):
        self._keymap = {}
        for action, names in self.settings["keys"].items():
            for name in names:
                try:
                    code = pygame.key.key_code(name)
                except (ValueError, pygame.error):
                    log.warning("Unknown key name '%s' for action %s", name, action)
                    continue
                self._keymap.setdefault(code, action)

    def key_action(self, key):
        return self._keymap.get(key)

    # ------------------------------------------------------------------
    # Scenes
    # ------------------------------------------------------------------
    def change_scene(self, name, **kw):
        if name not in self.scenes:
            log.error("Unknown scene %s", name)
            return
        self._pending = (name, kw)
        self._fade_dir = 1

    def _switch(self, name, kw):
        self.scene_name = name
        self.scene = self.scenes[name]
        try:
            self.scene.enter(**kw)
        except Exception:
            log.error("Error entering scene %s:\n%s", name, traceback.format_exc())
            if name != "menu":
                self.scene_name = "menu"
                self.scene = self.scenes["menu"]
                self.scene.enter()

    def _on_economy_event(self, kind, data):
        if kind == "achievement":
            self.toasts.push(f"Achievement: {data['name']}", data.get("icon", "trophy"), S.UI_ACCENT, 3.5)
            self.audio.play("achievement")
        elif kind == "season_tier" and self.scene_name != "game":
            season, tier = data
            self.toasts.push(f"Season Pass tier {tier} reached!", "star", season["color"], 3.5)
        elif kind == "level_up" and self.scene_name != "game":
            level, lines = data
            self.toasts.push(f"LEVEL {level}! " + ", ".join(lines), "star", S.UI_ACCENT, 4.0)
            self.audio.play("level_up")

    def reset_progress(self):
        self.save.data = self.save._fresh()
        self.save.save()
        self.missions.ensure_daily()

    def quit(self):
        self.running = False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def step(self, dt):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            if self._fade_dir == 0:
                self.scene.handle(event)
        if self._fade_dir:
            self._fade += self._fade_dir * dt / FADE_TIME
            if self._fade_dir > 0 and self._fade >= 1.0:
                self._fade = 1.0
                name, kw = self._pending
                self._pending = None
                self._switch(name, kw)
                self._fade_dir = -1
            elif self._fade_dir < 0 and self._fade <= 0.0:
                self._fade = 0.0
                self._fade_dir = 0
        self.scene.update(dt)
        self.toasts.update(dt)
        self.scene.draw(self.screen)
        self.toasts.draw(self.screen)
        if self.settings["show_fps"]:
            fps = self.assets.text(f"{self.clock.get_fps():.0f} FPS", 18, (120, 255, 140), bold=False)
            self.screen.blit(fps, (S.SCREEN_W - fps.get_width() - 10, S.SCREEN_H - 26))
        if self._fade > 0:
            layer = pygame.Surface((S.SCREEN_W, S.SCREEN_H))
            layer.fill((5, 6, 14))
            layer.set_alpha(int(255 * min(1.0, self._fade)))
            self.screen.blit(layer, (0, 0))
        pygame.display.flip()
        self.save.autosave()
        self.settings.autosave(2.0)

    def run(self):
        try:
            while self.running:
                dt = self.clock.tick(S.FPS) / 1000.0
                self.step(min(dt, 0.1))
        finally:
            self.shutdown()

    def shutdown(self):
        try:
            game = self.scenes.get("game") if hasattr(self, "scenes") else None
            sess = getattr(game, "session", None)
            if sess is not None and sess.result is None and sess.time > 1.0:
                sess.finalize()  # closing the window mid-run still banks the coins
        except Exception:
            log.error("Could not bank the current run on exit:\n%s", traceback.format_exc())
        try:
            self.save.save()
            self.settings.save()
        finally:
            pygame.quit()


def show_fatal_error(message):
    """Last-resort error screen so a crash is never silent."""
    try:
        if not pygame.get_init():
            pygame.init()
        screen = pygame.display.get_surface() or pygame.display.set_mode((900, 400))
        font = pygame.font.Font(None, 30)
        screen.fill((30, 10, 20))
        lines = ["RAILBLAZE hit an unexpected error.", "Your progress was saved.",
                 "Details: logs/crash.log", "", message[-80:], "", "Press any key to close."]
        for i, ln in enumerate(lines):
            screen.blit(font.render(ln, True, (255, 230, 230)), (30, 40 + i * 40))
        pygame.display.flip()
        end = time.time() + 30
        while time.time() < end:
            for e in pygame.event.get():
                if e.type in (pygame.QUIT, pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                    return
            time.sleep(0.05)
    except Exception:
        pass


def main():
    app = None
    try:
        app = App()
        app.run()
    except Exception as e:
        tb = traceback.format_exc()
        try:
            os.makedirs(S.LOG_DIR, exist_ok=True)
            with open(os.path.join(S.LOG_DIR, "crash.log"), "w", encoding="utf-8") as f:
                f.write(tb)
        except OSError:
            pass
        log.error("Fatal error:\n%s", tb)
        if app is not None:
            try:
                app.save.save()
            except Exception:
                pass
        show_fatal_error(f"{e.__class__.__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
