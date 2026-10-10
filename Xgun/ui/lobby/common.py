"""Shared lobby building blocks: item cards, section headers, tab base class."""
from __future__ import annotations

from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectGui import DirectButton, DirectFrame
from direct.interval.IntervalGlobal import LerpScaleInterval
from panda3d.core import TransparencyAttrib

from config import paths
from ui import theme as T
from ui.widgets import UI, frame, image, text


class Tab:
    def __init__(self, lobby, parent):
        self.lobby = lobby
        self.app = lobby.app
        self.svc = lobby.svc
        self.account = lobby.account
        self.parent = parent
        self.root = parent.attachNewNode(type(self).__name__)
        self.build()

    def build(self):  # pragma: no cover - overridden
        pass

    def rebuild(self):
        self.root.removeNode()
        self.root = self.parent.attachNewNode(type(self).__name__)
        self.build()

    def destroy(self):
        self.root.removeNode()


def header(parent, title: str, subtitle: str = "", pos=(-1.62, 0.7)):
    text(parent, title, pos, 0.085, T.TEXT, "black")
    if subtitle:
        text(parent, subtitle, (pos[0], pos[1] - 0.06), 0.034, T.TEXT_DIM, "semibold")


def icon(name: str):
    return UI.app.assets.texture(paths.ICONS / f"{name}.png", mipmap=True)


class ItemCard:
    """A cosmetic card: rarity gradient, Cycles-rendered thumbnail, name and status line."""

    def __init__(self, parent, item, *, pos=(0, 0), size=(0.36, 0.46), status: str = "", status_color=T.TEXT,
                 on_click=None, selected=False, price: int | None = None):
        w, h = size
        rar = T.RARITY[item.rarity]
        self.item = item
        self.node = DirectButton(parent=parent, frameSize=(-w / 2, w / 2, -h / 2, h / 2), pos=(pos[0], 0, pos[1]),
                                 frameColor=(rar[0] * 0.35, rar[1] * 0.35, rar[2] * 0.35, 0.95), relief=DGG.FLAT,
                                 command=self._click, pressEffect=1, rolloverSound=None, clickSound=None)
        self.node.setTransparency(TransparencyAttrib.M_alpha)
        self.on_click = on_click
        # rarity glow from the bottom
        for i in range(6):
            f = i / 6
            DirectFrame(parent=self.node, frameSize=(-w / 2, w / 2, -h / 2 + h * f * 0.5, -h / 2 + h * (f + 1 / 6) * 0.5),
                        frameColor=(rar[0], rar[1], rar[2], 0.35 * (1 - f)))
        thumb = UI.app.assets.thumb(item.id)
        if thumb is None and item.type == "banner":
            thumb = UI.app.assets.texture(paths.ICONS / item.extra.get("icon", "banner_x.png"))
        if thumb is None and item.type == "wrap" and item.extra.get("texture"):
            thumb = UI.app.assets.texture(paths.TEXTURES / "wraps" / item.extra["texture"])
        if thumb is None and item.type == "emote":
            thumb = icon("play")
        image(self.node, thumb, (0, h * 0.1), (w * 0.86, h * 0.62))
        DirectFrame(parent=self.node, frameSize=(-w / 2, w / 2, -h / 2, -h / 2 + 0.11), frameColor=(0.02, 0.03, 0.07, 0.82))
        DirectFrame(parent=self.node, frameSize=(-w / 2, w / 2, -h / 2 + 0.11, -h / 2 + 0.116), frameColor=rar)
        text(self.node, item.name.upper(), (-w / 2 + 0.02, -h / 2 + 0.062), min(0.03, 0.9 * w / max(8, len(item.name)) * 1.6),
             T.TEXT, "black")
        line = status
        if price is not None:
            image(self.node, UI.app.assets.texture(paths.ICONS / "xon.png"), (-w / 2 + 0.035, -h / 2 + 0.03), (0.032, 0.032))
            line = f"   {price:,}"
            status_color = T.GOLD
        text(self.node, line or item.type_label, (-w / 2 + 0.02, -h / 2 + 0.02), 0.024, status_color, "bold")
        if selected:
            for fs in ((-w / 2, w / 2, h / 2 - 0.006, h / 2), (-w / 2, w / 2, -h / 2, -h / 2 + 0.006),
                       (-w / 2, -w / 2 + 0.006, -h / 2, h / 2), (w / 2 - 0.006, w / 2, -h / 2, h / 2)):
                DirectFrame(parent=self.node, frameSize=fs, frameColor=T.ACCENT)
        self.node.bind(DGG.ENTER, lambda e: (UI.sound("ui_hover"), LerpScaleInterval(self.node, 0.08, 1.04).start()))
        self.node.bind(DGG.EXIT, lambda e: LerpScaleInterval(self.node, 0.08, 1.0).start())

    def _click(self):
        UI.sound("ui_click")
        if self.on_click:
            self.on_click(self.item)
