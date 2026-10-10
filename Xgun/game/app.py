"""The Xgun application: window, renderer, global services and screen flow."""
from __future__ import annotations

import logging
import os
import sys
import time
import traceback

from direct.showbase.ShowBase import ShowBase
from panda3d.core import ClockObject, Filename, WindowProperties, loadPrcFileData

from config import paths
from config.settings import Settings
from game.assets import AssetLibrary, fn
from game.services import Services

log = logging.getLogger("xgun")


def configure_panda(settings: Settings, *, offscreen: bool = False) -> None:
    prc = [
        "window-title Xgun",
        f"win-size {settings.window_width} {settings.window_height}",
        f"fullscreen {'#t' if settings.fullscreen else '#f'}",
        f"sync-video {'#t' if settings.vsync else '#f'}",
        "show-frame-rate-meter #f",
        "textures-power-2 none",
        "hardware-animated-vertices #t",
        "basic-shaders-only #f",
        "audio-library-name " + ("null" if os.environ.get("XGUN_NO_AUDIO") else "p3openal_audio"),
        "model-cache-dir",
        "notify-level-glgsg error",
        "notify-level-device fatal",
        "notify-level-ffmpeg fatal",
    ]
    if offscreen:
        prc.append("window-type offscreen")
    loadPrcFileData("xgun", "\n".join(prc))


class XgunApp(ShowBase):
    def __init__(self, settings: Settings | None = None, services: Services | None = None, *, offscreen: bool = False,
                 autoplay: str | None = None):
        self.settings = settings or Settings.load()
        configure_panda(self.settings, offscreen=offscreen)
        super().__init__()
        self.clock = ClockObject.getGlobalClock()
        self.disableMouse()
        self.setBackgroundColor(0.04, 0.05, 0.1, 1)
        gsg = self.win.getGsg() if self.win else None
        self.shaders_ok = bool(gsg and gsg.getSupportsGlsl())
        self.pbr = None
        if self.shaders_ok:
            try:
                import simplepbr
                quality = self.settings.quality
                self.pbr = simplepbr.init(msaa_samples=4 if quality == "High" else (2 if quality == "Medium" else 0),
                                          enable_shadows=self.settings.shadows, use_emission_maps=True,
                                          enable_fog=True, max_lights=4, use_normal_maps=False, exposure=0.0)
            except Exception as exc:  # pragma: no cover - fall back to fixed function
                log.warning("simplepbr unavailable (%s); using basic shading", exc)
                self.shaders_ok = False
        if not self.shaders_ok:
            log.info("Running without programmable shaders (basic lighting)")
        from ui.theme import Fonts
        from ui.widgets import UI, Toasts, wheel
        self.fonts = Fonts(self.loader)
        UI.app = self
        UI.fonts = self.fonts
        self.assets = AssetLibrary(self)
        from audio.manager import AudioManager
        self.audio = AudioManager(self)
        self.services = services or Services(probe=_probe())
        self.account = self.services.ensure_player()
        self.toasts = Toasts(self)
        self.island = None
        self.world_view = None
        self.screen = None
        self._bind_globals()
        self.autoplay = autoplay
        self.show_lobby()

    # ------------------------------------------------------------- flow
    def _swap(self, screen) -> None:
        if self.screen is not None:
            try:
                self.screen.destroy()
            except Exception:
                log.exception("Error while closing screen")
        self.screen = screen

    def show_lobby(self, tab: str = "PLAY", results=None) -> None:
        from ui.lobby.lobby import LobbyScreen
        self._swap(None)
        self._drop_world()
        self._bind_globals()
        self.screen = LobbyScreen(self, tab)
        if results is not None:
            self.screen.show_results(*results)

    def start_match(self) -> None:
        from ui.loading import LoadingScreen
        self._swap(None)
        self.screen = LoadingScreen(self, self._load_match_steps(), self._enter_match)

    def _load_match_steps(self):
        from world.island import build_island
        from world.world_view import WorldView
        if self.island is None:
            yield "Generating the island", None
            self.island = build_island(7)
        self.world_view = WorldView(self, self.island, self.settings.quality)
        for label, _ in self.world_view.build():
            yield label, None
        yield "Dropping in", None

    def _enter_match(self) -> None:
        from game.match_view import MatchScreen
        loadout = self.services.locker.equipped(self.account.id)
        screen = MatchScreen(self, loadout, self.account.display_name, self.end_match)
        self._swap(screen)
        screen.start()

    def end_match(self, summary) -> None:
        rewards = self.services.progression.apply_match(self.account.id, summary)
        self._swap(None)
        self.show_lobby("PLAY", (summary, rewards))

    def _drop_world(self) -> None:
        if self.world_view is not None:
            self.world_view.destroy()
            self.world_view = None
            # rebuild the collision world next match (crates are destructible)
            self.island = None

    def switch_account(self, account_id: int) -> None:
        self.account = self.services.accounts.set_active(account_id)
        self.show_lobby("PROFILE")

    def _bind_globals(self) -> None:
        self.accept("wheel_up", self._wheel, [1])
        self.accept("wheel_down", self._wheel, [-1])
        self.accept("f12", self.screenshot_to_user)
        self.accept("window-event", self._window_event)

    # ------------------------------------------------------------- misc
    def _wheel(self, direction: int) -> None:
        from ui.widgets import wheel
        if wheel(direction):
            return
        tab = getattr(self.screen, "tab_obj", None)
        if tab is not None and hasattr(tab, "wheel"):
            tab.wheel(direction)

    def apply_settings(self) -> None:
        self.settings.save()
        self.audio.refresh_volume()
        props = WindowProperties()
        props.setFullscreen(self.settings.fullscreen)
        props.setSize(self.settings.window_width, self.settings.window_height)
        if self.win is not None and not self.win.isOfType("GraphicsBuffer"):
            self.win.requestProperties(props)

    def _window_event(self, win):
        if win is self.win and self.screen is not None and hasattr(self.screen, "on_resize"):
            self.screen.on_resize()

    def screenshot_to_user(self) -> None:
        folder = paths.user_dir() / "screenshots"
        folder.mkdir(exist_ok=True)
        name = folder / time.strftime("xgun_%Y%m%d_%H%M%S.png")
        self.win.saveScreenshot(fn(name))
        self.toasts.show(f"Screenshot saved to {name.name}", "success")


def _probe():
    from video.probe import panda_probe
    return panda_probe


def setup_logging() -> None:
    logfile = paths.logs_dir() / "xgun.log"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(logfile, encoding="utf-8"), logging.StreamHandler(sys.stdout)])

    def hook(exc_type, exc, tb):
        logging.getLogger("xgun").critical("Unhandled error:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = hook
