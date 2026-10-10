"""The lobby: animated 3D character on a stage plus the tabbed menu."""
from __future__ import annotations

import datetime as dt
import math

from direct.gui.DirectGui import DirectFrame
from direct.interval.IntervalGlobal import LerpColorScaleInterval, LerpPosInterval, Parallel
from panda3d.core import AmbientLight, DirectionalLight, PointLight, Vec3

from config.branding import SOCIAL_NAME
from game.character_view import CharacterAvatar
from ui import theme as T
from ui.widgets import Button, Modal, ScrollArea, frame, image, text

TABS = ["PLAY", "LOCKER", "XON SHOP", "BATTLE PASS", "TIKTOK", "FRIENDS", "PROFILE", "QUESTS", "SETTINGS"]
# avatar framing per tab: (camera x offset, distance, show avatar, dim backdrop)
FRAMING = {"PLAY": (0.55, 6.2, True, 0.0), "LOCKER": (1.25, 6.6, True, 0.0), "XON SHOP": (1.6, 6.6, False, 0.6),
           "BATTLE PASS": (1.5, 7.2, False, 0.45), "TIKTOK": (0, 6, False, 0.85), "FRIENDS": (1.6, 7.2, True, 0.55),
           "PROFILE": (1.35, 6.8, True, 0.3), "QUESTS": (1.6, 7.2, True, 0.5), "SETTINGS": (0, 6, False, 0.8)}


class LobbyScreen:
    def __init__(self, app, tab: str = "PLAY"):
        self.app = app
        self.svc = app.services
        self.account = app.account
        self.root3d = app.render.attachNewNode("lobby3d")
        self.ui = app.aspect2d.attachNewNode("lobbyui")
        self.content = None
        self.tab_obj = None
        self.tab = None
        self.avatar = None
        self.preview_override = None
        self.drag = None
        self.spin = 0.0
        self._build_scene()
        self._build_bar()
        app.audio.play_music("lobby_theme")
        self.select(tab)
        app.taskMgr.add(self._task, "lobby-update")
        app.accept("mouse1", self._drag_start)
        app.accept("mouse1-up", self._drag_end)

    # ------------------------------------------------------------ 3D scene
    def _build_scene(self):
        app = self.app
        app.camLens.setFov(40)
        app.camLens.setNearFar(0.1, 200)
        app.setBackgroundColor(0.02, 0.025, 0.06, 1)
        cx, dist, _, _ = FRAMING.get(self.__dict__.get("tab") or "PLAY", FRAMING["PLAY"])
        app.camera.setPos(cx, dist, 1.15)
        stage = app.assets.model("env_lobby_stage")
        stage.reparentTo(self.root3d)
        key = DirectionalLight("key")
        key.setColor((2.6, 2.45, 2.3, 1))
        kn = self.root3d.attachNewNode(key)
        kn.setHpr(150, -35, 0)
        rim = PointLight("rim")
        rim.setColor((3, 1.2, 4.5, 1))
        rim.setAttenuation((1, 0, 0.08))
        rn = self.root3d.attachNewNode(rim)
        rn.setPos(-2.5, -2.5, 3.0)
        rim2 = PointLight("rim2")
        rim2.setColor((0.6, 2.4, 3.2, 1))
        rim2.setAttenuation((1, 0, 0.08))
        rn2 = self.root3d.attachNewNode(rim2)
        rn2.setPos(2.5, -2.0, 2.0)
        amb = AmbientLight("amb")
        amb.setColor((0.35, 0.33, 0.45, 1))
        an = self.root3d.attachNewNode(amb)
        for n in (kn, rn, rn2, an):
            self.root3d.setLight(n)
        self.backdrop = DirectFrame(parent=app.render2d, frameSize=(-1, 1, -1, 1), frameColor=(0.02, 0.03, 0.07, 0.0))
        self.backdrop.setBin("background", 5)
        self.backdrop.hide()
        self.refresh_avatar()

    def refresh_avatar(self, override: dict | None = None):
        loadout = dict(self.svc.locker.equipped(self.account.id))
        if override:
            loadout.update(override)
        if self.avatar is not None:
            yaw = self.avatar.root.getH()
            self.avatar.destroy()
        else:
            yaw = 0
        self.avatar = CharacterAvatar(self.app.assets, loadout, self.root3d)
        self.avatar.root.setH(yaw)
        self.avatar.root.setZ(0.04)
        self.avatar.hold(loadout.get("pickaxe"), "pickaxe")
        self.avatar.play("lobby_idle", "hold_pickaxe")
        self.avatar.set_lower("lobby_idle")
        self.loadout = loadout

    def play_emote(self, anim: str, prop: str | None = None):
        if self.avatar is None:
            return
        self.avatar.hold(None)
        self.avatar.show_prop(prop)
        self.avatar.play(anim)
        self.app.taskMgr.doMethodLater(6.0, self._end_emote, "lobby-emote-end")

    def _end_emote(self, task=None):
        if self.avatar is not None:
            self.avatar.show_prop(None)
            self.avatar.hold(self.loadout.get("pickaxe"), "pickaxe")
            self.avatar.play("lobby_idle", "hold_pickaxe")

    def _drag_start(self):
        mw = self.app.mouseWatcherNode
        if mw.hasMouse() and not mw.isOverRegion():
            self.drag = mw.getMouseX()

    def _drag_end(self):
        self.drag = None

    def _task(self, task):
        dt = self.app.clock.getDt()
        mw = self.app.mouseWatcherNode
        if self.drag is not None and mw.hasMouse():
            x = mw.getMouseX()
            self.avatar.root.setH(self.avatar.root.getH() + (x - self.drag) * 180)
            self.drag = x
        cx, dist, _, _ = FRAMING.get(self.tab, FRAMING["PLAY"])
        target = Vec3(cx, dist, 1.15)
        cam = self.app.camera
        cam.setPos(cam.getPos() + (target - cam.getPos()) * min(1.0, dt * 6))
        cam.lookAt(cam.getX(), 0, 1.0)
        if self.tab_obj is not None and hasattr(self.tab_obj, "update"):
            self.tab_obj.update(dt)
        return task.cont

    # ------------------------------------------------------------ top bar
    def _build_bar(self):
        app = self.app
        bar = app.a2dTopLeft.attachNewNode("topbar")
        self.bar = bar
        ratio = app.getAspectRatio()
        width = ratio * 2
        frame(bar, 0, width, -0.14, 0, (0.03, 0.04, 0.09, 0.88))
        DirectFrame(parent=bar, frameSize=(0, width, -0.143, -0.14), frameColor=(*T.PRIMARY[:3], 0.6))
        text(bar, "XGUN", (0.06, -0.093), 0.075, T.TEXT, "black")
        DirectFrame(parent=bar, frameSize=(0.27, 0.278, -0.105, -0.035), frameColor=T.ACCENT)
        self.tab_buttons = {}
        x = 0.34
        for name in TABS:
            w = 0.04 + len(SOCIAL_NAME if name == "TIKTOK" else name) * 0.024
            label = SOCIAL_NAME if name == "TIKTOK" else name
            b = Button(bar, label, self.select, pos=(x + w / 2, -0.07), size=(w, 0.08), color=(0, 0, 0, 0),
                       hover=(1, 1, 1, 0.08), text_scale=0.032, extra_args=(name,), border=(0, 0, 0, 0))
            self.tab_buttons[name] = b
            x += w + 0.01
        right = app.a2dTopRight.attachNewNode("wallet")
        self.right = right
        self.wallet_btn = Button(right, "", self.show_wallet, pos=(-0.62, -0.07), size=(0.34, 0.075), color=(0.1, 0.1, 0.18, 0.9),
                                 hover=(0.2, 0.18, 0.3, 1), text_color=T.GOLD, text_scale=0.034, align="right",
                                 icon=app.assets.texture(_icon_path("xon")))
        self.level_txt = text(right, "", (-0.08, -0.06), 0.032, T.TEXT, "bold", "right")
        self.user_txt = text(right, "", (-0.08, -0.105), 0.026, T.TEXT_DIM, "semibold", "right")
        self.refresh_wallet()

    def refresh_wallet(self):
        bal = self.svc.wallet.balance(self.account.id)
        self.wallet_btn.set_text(f"{bal:,} XON")
        lvl = self.svc.progression.level(self.account.id)
        self.level_txt.setText(f"LEVEL {lvl}")
        self.user_txt.setText(self.account.display_name + "  •  OFFLINE")

    def show_wallet(self):
        history = self.svc.wallet.history(self.account.id, 12)
        lines = []
        for t in history:
            when = dt.datetime.fromtimestamp(t.created_at).strftime("%b %d %H:%M")
            sign = "+" if t.amount > 0 else ""
            lines.append(f"{when}   {sign}{t.amount:,}   {t.reason}")
        body = "\n".join(lines) or "No transactions yet."
        m = Modal(self.app, f"XON WALLET  •  {self.svc.wallet.balance(self.account.id):,} XON",
                  "Earn XON by playing matches, finishing quests and leveling up. No real money is ever used.",
                  [("Close", None, ())], width=1.5, height=1.25)
        text(m.box, body, (-0.68, 0.33), 0.032, T.TEXT, "regular")

    # ------------------------------------------------------------ tabs
    def select(self, name: str):
        if name == self.tab:
            return
        from ui.lobby import tabs
        self.app.taskMgr.remove("lobby-emote-end")
        if self.tab_obj is not None:
            self.tab_obj.destroy()
            self.tab_obj = None
        if self.content is not None:
            self.content.removeNode()
        self.tab = name
        for n, b in self.tab_buttons.items():
            b.set_selected(n == name, (0.25, 0.18, 0.55, 0.9))
        _, _, show_avatar, dim = FRAMING[name]
        if self.avatar is not None:
            self.avatar.root.show() if show_avatar else self.avatar.root.hide()
        self.root3d.show() if dim < 0.79 else self.root3d.hide()
        self.backdrop["frameColor"] = (0.02, 0.03, 0.07, dim)
        self.backdrop.show() if dim > 0 else self.backdrop.hide()
        self.content = self.ui.attachNewNode("content")
        self.content.setColorScale(1, 1, 1, 0)
        self.content.setZ(-0.03)
        Parallel(LerpColorScaleInterval(self.content, 0.18, (1, 1, 1, 1)),
                 LerpPosInterval(self.content, 0.18, (0, 0, 0))).start()
        if self.preview_override:
            self.preview_override = None
            self.refresh_avatar()
        self.tab_obj = tabs.create(name, self, self.content)
        self.app.audio.play("ui_swoosh", 0.6)

    # ------------------------------------------------------------ results
    def show_results(self, summary, rewards):
        from ui.lobby.results import ResultsPanel
        ResultsPanel(self, summary, rewards)
        self.refresh_wallet()

    def destroy(self):
        app = self.app
        app.taskMgr.remove("lobby-update")
        app.taskMgr.remove("lobby-emote-end")
        app.ignore("mouse1")
        app.ignore("mouse1-up")
        if self.tab_obj is not None:
            self.tab_obj.destroy()
        if self.avatar is not None:
            self.avatar.destroy()
        self.backdrop.destroy()
        self.root3d.removeNode()
        self.ui.removeNode()
        self.bar.removeNode()
        self.right.removeNode()
        app.render.clearLight()


def _icon_path(name: str):
    from config import paths
    return paths.ICONS / f"{name}.png"
