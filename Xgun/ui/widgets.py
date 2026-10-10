"""Reusable DirectGUI widgets in the Xgun style."""
from __future__ import annotations

import textwrap
from typing import Callable

from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectGui import (DirectButton, DirectEntry, DirectFrame, DirectLabel, DirectScrolledFrame,
                                  DirectSlider, OnscreenImage, OnscreenText)
from direct.interval.IntervalGlobal import LerpColorScaleInterval, LerpScaleInterval, Sequence, Wait, Func
from panda3d.core import NodePath, TextNode, TransparencyAttrib

from ui import theme as T

ALIGN = {"left": TextNode.ALeft, "center": TextNode.ACenter, "right": TextNode.ARight}


class UI:
    """Holds the app-wide UI context (fonts, sounds) used by every widget."""
    app = None
    fonts: T.Fonts | None = None
    scroll_areas: list["ScrollArea"] = []

    @classmethod
    def sound(cls, name: str) -> None:
        if cls.app is not None and getattr(cls.app, "audio", None) is not None:
            cls.app.audio.play(name)


def frame(parent, l, r, b, t, color=T.PANEL, border=None, border_w=0.004, pos=(0, 0, 0)) -> DirectFrame:
    f = DirectFrame(parent=parent, frameSize=(l, r, b, t), frameColor=color, pos=pos)
    if border is not None:  # edges drawn as thin strips on top of the fill
        for fs in ((l, r, t - border_w, t), (l, r, b, b + border_w), (l, l + border_w, b, t), (r - border_w, r, b, t)):
            DirectFrame(parent=f, frameSize=fs, frameColor=border)
    f.setTransparency(TransparencyAttrib.M_alpha)
    return f


def text(parent, value: str, pos=(0, 0), scale=0.05, color=T.TEXT, font: str = "regular", align="left",
         wrap: float | None = None, shadow: bool = False) -> OnscreenText:
    f = getattr(UI.fonts, font) if UI.fonts else None
    return OnscreenText(parent=parent, text=value, pos=pos, scale=scale, fg=color, font=f, align=ALIGN[align],
                        wordwrap=wrap, mayChange=True, shadow=T.SHADOW if shadow else None)


def image(parent, tex, pos=(0, 0), size=(0.2, 0.2), fit: bool = True) -> OnscreenImage | None:
    if tex is None:
        return None
    sx, sy = size
    if fit and tex.getXSize() and tex.getYSize():
        aspect = tex.getOrigFileXSize() / max(1, tex.getOrigFileYSize())
        if aspect > sx / sy:
            sy = sx / aspect
        else:
            sx = sy * aspect
    img = OnscreenImage(parent=parent, image=tex, pos=(pos[0], 0, pos[1]), scale=(sx / 2, 1, sy / 2))
    img.setTransparency(TransparencyAttrib.M_alpha)
    return img


class Button:
    """Flat button with hover/press states, sounds and an optional selected look."""

    def __init__(self, parent, label: str, command: Callable | None = None, *, pos=(0, 0), size=(0.36, 0.09),
                 color=T.PANEL_LIGHT, hover=T.PANEL_HOVER, text_color=T.TEXT, font="bold", text_scale=0.04,
                 border=None, extra_args=(), sound="ui_click", icon=None, align="center", enabled=True):
        w, h = size
        self.command = command
        self.extra_args = extra_args
        self.sound = sound
        self.base_color = color
        self.hover_color = hover
        self.selected = False
        f = getattr(UI.fonts, font) if UI.fonts else None
        tx = {"center": 0, "left": -w / 2 + 0.03 + (h * 0.8 if icon is not None else 0), "right": w / 2 - 0.03}[align]
        self.node = DirectButton(parent=parent, frameSize=(-w / 2, w / 2, -h / 2, h / 2), pos=(pos[0], 0, pos[1]),
                                 frameColor=(color, _shade(color, 0.8), hover, _shade(color, 0.5)), relief=DGG.FLAT,
                                 text=label, text_font=f, text_scale=text_scale, text_fg=text_color,
                                 text_pos=(tx, -text_scale * 0.35), text_align=ALIGN[align], command=self._click,
                                 pressEffect=1, rolloverSound=None, clickSound=None)
        self.node.setTransparency(TransparencyAttrib.M_alpha)
        if border is not None:
            b = DirectFrame(parent=self.node, frameSize=(-w / 2, w / 2, -h / 2, -h / 2 + 0.006), frameColor=border)
            self.underline = b
        else:
            self.underline = None
        self.node.bind(DGG.ENTER, self._enter)
        self.node.bind(DGG.EXIT, self._exit)
        self._anim = None
        self.icon = None
        if icon is not None:
            self.icon = image(self.node, icon, (-w / 2 + h / 2 + 0.01, 0), (h * 0.7, h * 0.7))
        if not enabled:
            self.set_enabled(False)

    def _click(self):
        if self.sound:
            UI.sound(self.sound)
        if self.command:
            self.command(*self.extra_args)

    def _enter(self, _evt=None):
        UI.sound("ui_hover")
        if self._anim:
            self._anim.finish()
        self._anim = LerpScaleInterval(self.node, 0.08, 1.04)
        self._anim.start()

    def _exit(self, _evt=None):
        if self._anim:
            self._anim.finish()
        self._anim = LerpScaleInterval(self.node, 0.08, 1.0)
        self._anim.start()

    def set_text(self, value: str) -> None:
        self.node["text"] = value

    def set_selected(self, selected: bool, color=T.PRIMARY) -> None:
        self.selected = selected
        c = color if selected else self.base_color
        self.node["frameColor"] = (c, _shade(c, 0.8), self.hover_color if not selected else _shade(c, 1.15), _shade(c, 0.5))
        if self.underline is not None:
            self.underline["frameColor"] = T.ACCENT if selected else (0, 0, 0, 0)

    def set_enabled(self, enabled: bool) -> None:
        self.node["state"] = DGG.NORMAL if enabled else DGG.DISABLED
        self.node.setColorScale((1, 1, 1, 1) if enabled else (0.6, 0.6, 0.6, 0.8))

    def destroy(self):
        if self._anim:
            self._anim.finish()
        self.node.destroy()


def _shade(c, k):
    return (min(1, c[0] * k), min(1, c[1] * k), min(1, c[2] * k), c[3])


class Entry:
    def __init__(self, parent, *, pos=(0, 0), width=0.8, initial="", placeholder="", scale=0.04, max_chars=60,
                 command=None, obscured=False):
        self.bg = frame(parent, -0.015, width + 0.015, -0.035, scale + 0.035, T.PANEL_LIGHT, pos=(pos[0], 0, pos[1]))
        self.placeholder = placeholder
        self.max_chars = max_chars
        self.node = DirectEntry(parent=self.bg, scale=scale, width=width / scale, initialText=initial, numLines=1,
                                focus=0, frameColor=(0, 0, 0, 0), text_fg=T.TEXT, entryFont=UI.fonts.regular if UI.fonts else None,
                                command=command, obscured=obscured, focusInCommand=self._focus_in,
                                focusOutCommand=self._focus_out)
        self.hint = text(self.bg, placeholder if not initial else "", (0, 0.004), scale, T.TEXT_MUTED)

    def _focus_in(self):
        self.hint.setText("")

    def _focus_out(self):
        if not self.get():
            self.hint.setText(self.placeholder)

    def get(self) -> str:
        return self.node.get()[: self.max_chars]

    def set(self, value: str) -> None:
        self.node.enterText(value)
        self.hint.setText("" if value else self.placeholder)

    def destroy(self):
        self.bg.destroy()


class ScrollArea:
    """Vertical scroll container with mouse-wheel support."""

    def __init__(self, parent, l, r, b, t, canvas_height: float, color=(0, 0, 0, 0)):
        self.bounds = (l, r, b, t)
        self.node = DirectScrolledFrame(parent=parent, frameSize=(l, r, b, t), canvasSize=(l, r - 0.04, -canvas_height, 0),
                                        frameColor=color, scrollBarWidth=0.025, autoHideScrollBars=True,
                                        verticalScroll_frameColor=(1, 1, 1, 0.04),
                                        verticalScroll_thumb_frameColor=(1, 1, 1, 0.25),
                                        verticalScroll_incButton_frameColor=(0, 0, 0, 0),
                                        verticalScroll_decButton_frameColor=(0, 0, 0, 0),
                                        verticalScroll_incButton_relief=None, verticalScroll_decButton_relief=None,
                                        horizontalScroll_frameColor=(0, 0, 0, 0))
        self.canvas = self.node.getCanvas()
        self.canvas.setZ(t)
        self.top = t
        UI.scroll_areas.append(self)

    def set_height(self, h: float) -> None:
        l, r, b, t = self.bounds
        self.node["canvasSize"] = (l, r - 0.04, -max(h, t - b), 0)
        self.node.setCanvasSize()

    def contains_mouse(self) -> bool:
        if self.node.isEmpty() or self.node.getTop() != UI.app.render2d:
            if self in UI.scroll_areas:   # parent was removed without destroy()
                UI.scroll_areas.remove(self)
            return False
        if UI.app is None or not UI.app.mouseWatcherNode.hasMouse() or self.node.isHidden():
            return False
        m = UI.app.mouseWatcherNode.getMouse()
        p = self.node.getRelativePoint(UI.app.render2d, (m.x, 0, m.y))
        l, r, b, t = self.bounds
        return l <= p.x <= r and b <= p.z <= t

    def scroll(self, direction: int) -> None:
        bar = self.node.verticalScroll
        bar["value"] = max(0.0, min(1.0, bar["value"] + direction * 0.08))

    def destroy(self):
        if self in UI.scroll_areas:
            UI.scroll_areas.remove(self)
        self.node.destroy()


def wheel(direction: int) -> bool:
    for area in reversed(list(UI.scroll_areas)):
        if area.contains_mouse():
            area.scroll(-direction)
            return True
    return False


class ProgressBar:
    def __init__(self, parent, pos=(0, 0), size=(0.6, 0.03), color=T.PRIMARY, back=(1, 1, 1, 0.1)):
        w, h = size
        self.w = w
        self.back = DirectFrame(parent=parent, frameSize=(0, w, -h / 2, h / 2), frameColor=back, pos=(pos[0], 0, pos[1]))
        self.bar = DirectFrame(parent=self.back, frameSize=(0, w, -h / 2, h / 2), frameColor=color)
        self.set(0)

    def set(self, frac: float) -> None:
        self.bar.setSx(max(0.0001, min(1.0, frac)))

    def destroy(self):
        self.back.destroy()


class Toggle:
    def __init__(self, parent, value: bool, command, pos=(0, 0)):
        self.value = value
        self.command = command
        self.btn = Button(parent, "", self._flip, pos=pos, size=(0.16, 0.06), text_scale=0.03)
        self._refresh()

    def _flip(self):
        self.value = not self.value
        self._refresh()
        self.command(self.value)

    def _refresh(self):
        self.btn.set_text("ON" if self.value else "OFF")
        self.btn.set_selected(self.value, T.GREEN if self.value else T.PANEL_LIGHT)

    def destroy(self):
        self.btn.destroy()


class Slider:
    def __init__(self, parent, value: float, lo: float, hi: float, command, pos=(0, 0), width=0.6, fmt="{:.0%}"):
        self.fmt = fmt
        self.command = command
        self.node = DirectSlider(parent=parent, range=(lo, hi), value=value, pos=(pos[0] + width / 2, 0, pos[1]),
                                 scale=(width / 2, 1, 0.5), frameSize=(-1, 1, -0.012, 0.012), frameColor=T.PANEL_HOVER,
                                 thumb_frameSize=(-0.025 * 2 / width, 0.025 * 2 / width, -0.05, 0.05),
                                 thumb_frameColor=T.PRIMARY, thumb_relief=DGG.FLAT, command=self._changed)
        self.label = text(parent, fmt.format(value), (pos[0] + width + 0.05, pos[1] - 0.012), 0.035, T.TEXT_DIM)

    def _changed(self):
        v = self.node["value"]
        self.label.setText(self.fmt.format(v))
        self.command(v)

    def destroy(self):
        self.node.destroy()
        self.label.destroy()


class Toasts:
    """Stacked notifications in the top-right corner."""

    def __init__(self, app):
        self.app = app
        self.items: list[NodePath] = []

    def show(self, message: str, kind: str = "info", duration: float = 3.0) -> None:
        color = {"info": T.PRIMARY, "success": T.GREEN, "error": T.RED, "xon": T.GOLD}.get(kind, T.PRIMARY)
        root = self.app.a2dTopRight.attachNewNode("toast")
        w = 0.82
        lines = textwrap.wrap(message, 38) or [""]
        h = 0.06 + 0.045 * len(lines)
        frame(root, -w, 0, -h, 0, T.PANEL_LIGHT)
        DirectFrame(parent=root, frameSize=(-w, -w + 0.012, -h, 0), frameColor=color)
        text(root, "\n".join(lines), (-w + 0.04, -0.06), 0.035, T.TEXT, "semibold")
        root.setPos(-0.04, 0, -0.2 - sum(0.02 + n.getPythonTag("h") for n in self.items))
        root.setPythonTag("h", h)
        root.setColorScale(1, 1, 1, 0)
        self.items.append(root)
        UI.sound("notify" if kind != "error" else "ui_error")
        Sequence(LerpColorScaleInterval(root, 0.2, (1, 1, 1, 1)), Wait(duration),
                 LerpColorScaleInterval(root, 0.3, (1, 1, 1, 0)), Func(self._remove, root)).start()

    def _remove(self, node: NodePath) -> None:
        if node in self.items:
            self.items.remove(node)
        node.removeNode()
        y = -0.2
        for n in self.items:
            n.setZ(y)
            y -= 0.02 + n.getPythonTag("h")


class Modal:
    """Centered dialog with a dimmed backdrop."""

    def __init__(self, app, title: str, body: str = "", buttons: list[tuple[str, Callable | None, tuple]] | None = None,
                 width=1.1, height=0.62):
        self.app = app
        self.root = app.aspect2d.attachNewNode("modal")
        self.root.setBin("gui-popup", 50)
        DirectFrame(parent=self.root, frameSize=(-4, 4, -2, 2), frameColor=(0, 0, 0, 0.6), state=DGG.NORMAL)
        self.box = frame(self.root, -width / 2, width / 2, -height / 2, height / 2, T.PANEL_LIGHT)
        DirectFrame(parent=self.box, frameSize=(-width / 2, width / 2, height / 2 - 0.008, height / 2), frameColor=T.PRIMARY)
        text(self.box, title, (0, height / 2 - 0.09), 0.055, T.TEXT, "black", "center")
        if body:
            text(self.box, body, (0, height / 2 - 0.17), 0.037, T.TEXT_DIM, "regular", "center", wrap=width / 0.037 * 0.9)
        self.buttons = []
        buttons = buttons or [("OK", None, ())]
        n = len(buttons)
        bw = min(0.36, (width - 0.1) / n - 0.03)
        for i, (label, cmd, args) in enumerate(buttons):
            x = (i - (n - 1) / 2) * (bw + 0.04)
            primary = i == n - 1
            self.buttons.append(Button(self.box, label, self._wrap(cmd, args), pos=(x, -height / 2 + 0.09), size=(bw, 0.085),
                                       color=T.PRIMARY if primary else T.PANEL, hover=T.PRIMARY_HOVER if primary else T.PANEL_HOVER))
        self.root.setScale(0.9)
        self.root.setColorScale(1, 1, 1, 0)
        LerpScaleInterval(self.root, 0.12, 1.0).start()
        LerpColorScaleInterval(self.root, 0.12, (1, 1, 1, 1)).start()

    def _wrap(self, cmd, args):
        def run():
            self.close()
            if cmd:
                cmd(*args)
        return run

    def close(self):
        for b in self.buttons:
            b.destroy()
        self.root.removeNode()
