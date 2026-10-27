"""BONK! application: window, lighting, profile, screens and the main loop."""

import logging
import sys

from panda3d.core import (AmbientLight, AntialiasAttrib, ClockObject, CullFaceAttrib, DirectionalLight,
                          RenderState, loadPrcFileData)

from .. import VERSION
from ..maps.map_manager import MapManager
from ..paths import ASSETS_DIR
from ..progression.profile import PlayerProfile
from ..save.save_manager import SaveManager

log = logging.getLogger(__name__)


def configure_engine(settings, headless_shots=False):
    w, h = (int(v) for v in settings.get("resolution", "1280x720").split("x"))
    prc = [
        "window-title BONK!",
        "win-size %d %d" % (w, h),
        "fullscreen %s" % ("#t" if settings.get("fullscreen") else "#f"),
        "framebuffer-multisample 1",
        "multisamples 4",
        "sync-video #t",
        "textures-power-2 none",
        "show-frame-rate-meter %s" % ("#t" if settings.get("show_fps") else "#f"),
        "audio-library-name p3openal_audio",
        "model-cache-dir",
        "notify-level-glgsg error",
        "notify-level-gobj error",
    ]
    if headless_shots:
        prc.append("sync-video #f")
    loadPrcFileData("bonk", "\n".join(p for p in prc if p))


from direct.showbase.ShowBase import ShowBase  # noqa: E402  (after PRC configuration)


class BonkApp(ShowBase):
    def __init__(self, profile=None, autoplay=None):
        self.profile = profile or PlayerProfile(SaveManager())
        ShowBase.__init__(self)
        self.disableMouse()
        self.setBackgroundColor(0.09, 0.06, 0.23, 1)
        self.render.setShaderAuto()
        self.render.setAntialias(AntialiasAttrib.MMultisample)
        self.camLens.setFov(68)
        self.camLens.setNearFar(0.2, 900)
        self.maps = MapManager()
        if self.maps.errors:
            for name, err in self.maps.errors.items():
                log.error("map %s skipped: %s", name, err)
        self._setup_lights()

        from .audio import SoundBank
        from .render.menu_scene import MenuScene
        from .ui.screen_manager import ScreenManager
        from .ui.screens import register_all
        from .ui.theme import Theme
        from .ui.widgets import Toasts, set_sound_bank

        self.theme = Theme(self.loader)
        self.sounds = SoundBank(self, self.profile.settings)
        set_sound_bank(self.sounds)
        self.toasts = Toasts(self.aspect2d, self.theme)
        self.menu_scene = MenuScene(self, self.profile.catalog.get(self.profile.skins.equipped))
        self.session = None
        self.last_result = None
        self.net = None  # multiplayer client (screens/multiplayer.py)
        self.screens = ScreenManager(self)
        register_all(self)
        self.accept("escape", self.screens.escape)
        self.accept("window-event", self._on_window_event)
        self.taskMgr.add(self._update, "bonk-update")
        self.autoplay = autoplay
        for w in self.profile.store.warnings:
            self.toasts.show(w, "danger", 5.0)
        self.screens.show("splash", push=False)

    # ------------------------------------------------------------------ lighting
    def _setup_lights(self):
        sun = DirectionalLight("sun")
        sun.setColor((0.95, 0.9, 0.82, 1))
        if self.profile.settings.get("shadows", True):
            sun.setShadowCaster(True, 2048, 2048)
            sun.getLens().setFilmSize(44, 44)
            sun.getLens().setNearFar(5, 80)
            # Render back faces into the shadow map: removes self-shadowing stripes ("acne").
            sun.setInitialState(RenderState.make(CullFaceAttrib.makeReverse()))
        self.sun = self.render.attachNewNode(sun)
        self.sun.setPos(10, -6, 25)
        self.sun.lookAt(0, 0, 0)
        self.render.setLight(self.sun)
        amb = AmbientLight("ambient")
        amb.setColor((0.48, 0.46, 0.58, 1))
        self.render.setLight(self.render.attachNewNode(amb))

    def apply_shadow_setting(self):
        node = self.sun.node()
        if self.profile.settings.get("shadows", True):
            node.setShadowCaster(True, 2048, 2048)
        else:
            node.setShadowCaster(False)

    def _on_window_event(self, win):
        if win is not None and win == self.win and hasattr(win, "getProperties"):
            props = win.getProperties()
            if not props.getOpen():
                self.quit()

    # ------------------------------------------------------------------ screens
    def on_screen_changed(self, screen):
        if screen.uses_menu_scene and self.session is None:
            self.menu_scene.set_skin(self.profile.catalog.get(self.profile.skins.equipped))
            self.menu_scene.show(getattr(screen, "scene_offset", 1.3))
        else:
            self.menu_scene.hide()
        if screen.music:
            self.sounds.play_music(screen.music)

    # ------------------------------------------------------------------ sessions
    def start_show(self, config):
        from .session import GameSession
        self.screens.show("loading", push=False, text="Building the course...")

        def go(task):
            self.menu_scene.hide()
            self.session = GameSession(self, config)
            self.session.start()
            return task.done

        self.taskMgr.doMethodLater(0.05, go, "start-show")

    def end_session(self, session, report, summary, champion_name, won):
        self.last_result = {"report": report, "summary": summary, "champion": champion_name, "won": won,
                            "standings": [(p, session.gm.participants[i].name, i == session.LOCAL)
                                          for p, i in sorted(session.gm.final_standings)],
                            "history": session.gm.history, "total_rounds": session.gm.total_rounds}
        self.end_session_cleanup(session, "victory" if won else "results")

    # ------------------------------------------------------------------ online sessions
    def start_net_session(self, first_state_msg):
        from .net_session import NetSession
        self.menu_scene.hide()
        self.session = NetSession(self, self.net)
        self.session.start(first_state_msg)

    def end_net_session(self, session, report, summary, champion, won, msg):
        self.last_result = {"report": report, "summary": summary, "champion": champion, "won": won,
                            "standings": [(s["place"], s["name"], s["id"] == session.LOCAL)
                                          for s in msg["standings"]],
                            "leaderboard": msg.get("leaderboard"), "online": True}
        self.end_session_cleanup(session, "victory" if won else "results")

    def abort_net_session(self, session):
        self.end_session_cleanup(session, "multiplayer")

    def end_session_cleanup(self, session, next_screen):
        def cleanup(task):
            session.destroy()
            if self.session is session:
                self.session = None
            self.screens.reset_to(next_screen)
            return task.done

        self.taskMgr.doMethodLater(0.01, cleanup, "end-session")

    # ------------------------------------------------------------------ loop
    def _update(self, task):
        dt = min(ClockObject.getGlobalClock().getDt(), 0.1)
        if self.session is not None:
            self.session.update(dt)
        else:
            self.menu_scene.update(dt)
        if self.net is not None:
            self.net.poll()
        self.screens.update(dt)
        self.toasts.update(dt)
        if self.autoplay is not None:
            self.autoplay.update(dt)
        return task.cont

    def quit(self):
        try:
            self.profile.save()
        finally:
            if self.net is not None:
                self.net.close()
            self.userExit()


def run(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    argv = argv if argv is not None else sys.argv[1:]
    profile = PlayerProfile(SaveManager())
    configure_engine(profile.settings)
    autoplay = None
    if "--autoplay" in argv:
        from .autoplay import AutoPlay
        autoplay = AutoPlay(argv)
    app = BonkApp(profile, autoplay)
    if autoplay is not None:
        autoplay.attach(app)
    log.info("BONK! %s started (assets: %s)", VERSION, ASSETS_DIR)
    app.run()

