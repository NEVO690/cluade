"""Reusable DirectGUI widgets in the BONK! style."""

from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel, DirectScrolledFrame
from direct.interval.IntervalGlobal import LerpScaleInterval
from panda3d.core import TextNode, TransparencyAttrib

from .theme import c

_SOUND = {"bank": None}


def set_sound_bank(bank):
    _SOUND["bank"] = bank


def _sfx(name):
    bank = _SOUND["bank"]
    if bank is not None:
        bank.play(name)


def panel(parent, theme, frame, color="panel", alpha=0.92, radius=0.12, shadow=True, pos=(0, 0, 0)):
    """Rounded panel.  frame = (left, right, bottom, top) in parent units."""
    l, r, b, t = frame
    aspect = (r - l) / max(0.01, t - b)
    rad = min(0.45, radius / max(0.01, t - b))
    if shadow:
        DirectFrame(parent=parent, frameColor=(0, 0, 0, 0.35), frameSize=(l + 0.015, r + 0.015, b - 0.02, t - 0.02),
                    frameTexture=theme.rounded(aspect, rad, 0.0), pos=pos).setTransparency(TransparencyAttrib.MAlpha)
    f = DirectFrame(parent=parent, frameColor=c(color, alpha), frameSize=(l, r, b, t),
                    frameTexture=theme.rounded(aspect, rad, 0.12), pos=pos)
    f.setTransparency(TransparencyAttrib.MAlpha)
    return f


def label(parent, theme, text, pos=(0, 0), scale=0.06, color="text", font="body", align="center",
          wordwrap=None, shadow=True):
    al = {"center": TextNode.ACenter, "left": TextNode.ALeft, "right": TextNode.ARight}[align]
    lab = DirectLabel(parent=parent, text=text, text_font=theme.font(font), text_scale=scale,
                      text_fg=c(color) if isinstance(color, str) else color, text_align=al,
                      text_shadow=(0, 0, 0, 0.45) if shadow else None, text_shadowOffset=(0.05, 0.05),
                      text_wordwrap=wordwrap, frameColor=(0, 0, 0, 0), pos=(pos[0], 0, pos[1]))
    return lab


def set_label(lab, text, color=None):
    lab["text"] = text
    if color is not None:
        lab["text_fg"] = c(color) if isinstance(color, str) else color


class Button:
    """Rounded button with hover grow, press squish, click sound and disabled state."""

    def __init__(self, parent, theme, text, pos=(0, 0), size=(0.6, 0.12), command=None, args=None,
                 color="primary", text_color="text", scale=0.055, font="bold", enabled=True, icon=None):
        self.theme = theme
        self.color = color
        self.command = command
        self.args = args or []
        w, h = size
        self.root = DirectFrame(parent=parent, frameColor=(0, 0, 0, 0), pos=(pos[0], 0, pos[1]))
        aspect = w / h
        self.shadow = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0.35),
                                  frameSize=(-w / 2 + 0.01, w / 2 + 0.01, -h / 2 - 0.018, h / 2 - 0.018),
                                  frameTexture=theme.rounded(aspect, 0.45, 0.0))
        self.shadow.setTransparency(TransparencyAttrib.MAlpha)
        self.btn = DirectButton(parent=self.root, text=text, text_font=theme.font(font), text_scale=scale,
                                text_fg=c(text_color), text_pos=(0, -scale * 0.36),
                                text_shadow=(0, 0, 0, 0.35), text_shadowOffset=(0.04, 0.04),
                                frameSize=(-w / 2, w / 2, -h / 2, h / 2), frameColor=c(color),
                                frameTexture=theme.rounded(aspect, 0.45, 0.22),
                                relief=DGG.FLAT, command=self._clicked, pressEffect=0)
        self.btn.setTransparency(TransparencyAttrib.MAlpha)
        self.btn.bind(DGG.ENTER, self._hover, [True])
        self.btn.bind(DGG.EXIT, self._hover, [False])
        self.enabled = True
        self._iv = None
        self.set_enabled(enabled)

    def _hover(self, on, _evt=None):
        if not self.enabled:
            return
        if self._iv is not None:
            self._iv.finish()
        target = 1.06 if on else 1.0
        self._iv = LerpScaleInterval(self.root, 0.08, target)
        self._iv.start()
        if on:
            _sfx("hover")

    def _clicked(self):
        if not self.enabled:
            _sfx("error")
            return
        _sfx("click")
        if self._iv is not None:
            self._iv.finish()
        self.root.setScale(0.94)
        self._iv = LerpScaleInterval(self.root, 0.12, 1.0)
        self._iv.start()
        if self.command:
            self.command(*self.args)

    def set_enabled(self, flag):
        self.enabled = flag
        self.btn["frameColor"] = c(self.color) if flag else c("locked")
        self.btn["text_fg"] = c("text") if flag else (0.8, 0.8, 0.85, 1)

    def set_text(self, text):
        self.btn["text"] = text

    def set_color(self, color):
        self.color = color
        if self.enabled:
            self.btn["frameColor"] = c(color)

    def destroy(self):
        if self._iv is not None:
            self._iv.finish()
        self.root.destroy()

    def hide(self):
        self.root.hide()

    def show(self):
        self.root.show()


class ProgressBar:
    def __init__(self, parent, theme, frame, value=0.0, color="accent", back="dark"):
        l, r, b, t = frame
        self.frame = frame
        aspect = (r - l) / (t - b)
        self.back = DirectFrame(parent=parent, frameColor=c(back, 0.8), frameSize=frame,
                                frameTexture=theme.rounded(aspect, 0.5, 0.0))
        self.back.setTransparency(TransparencyAttrib.MAlpha)
        self.fill = DirectFrame(parent=self.back, frameColor=c(color), frameSize=frame,
                                frameTexture=theme.rounded(aspect, 0.5, 0.25))
        self.fill.setTransparency(TransparencyAttrib.MAlpha)
        self.set(value)

    def set(self, value):
        value = max(0.0, min(1.0, value))
        l, r, b, t = self.frame
        if value <= 0.001:
            self.fill.hide()
            return
        self.fill.show()
        self.fill["frameSize"] = (l, l + (r - l) * value, b, t)

    def destroy(self):
        self.back.destroy()


class ScrollList:
    """Vertical scrolling list; add rows with add_row(height) -> row frame."""

    def __init__(self, parent, theme, frame, row_gap=0.015):
        l, r, b, t = frame
        self.theme = theme
        self.width = r - l - 0.06
        self.sf = DirectScrolledFrame(parent=parent, frameSize=frame, frameColor=(0, 0, 0, 0),
                                      canvasSize=(l, r - 0.06, b, t), scrollBarWidth=0.04,
                                      verticalScroll_frameColor=c("dark", 0.5),
                                      verticalScroll_thumb_frameColor=c("muted", 0.9),
                                      verticalScroll_incButton_frameColor=(0, 0, 0, 0),
                                      verticalScroll_decButton_frameColor=(0, 0, 0, 0),
                                      verticalScroll_incButton_relief=None,
                                      verticalScroll_decButton_relief=None,
                                      horizontalScroll_frameColor=(0, 0, 0, 0),
                                      manageScrollBars=True, autoHideScrollBars=True)
        self.l, self.top = l, t
        self.cursor = t
        self.row_gap = row_gap
        self.rows = []

    @property
    def canvas(self):
        return self.sf.getCanvas()

    def add_row(self, height):
        top = self.cursor
        row = DirectFrame(parent=self.canvas, frameColor=(0, 0, 0, 0), pos=(0, 0, top - height / 2))
        self.cursor -= height + self.row_gap
        self.rows.append(row)
        l, r, b, t = self.sf["frameSize"]
        self.sf["canvasSize"] = (l, r - 0.06, min(b, self.cursor), t)
        self.sf.setCanvasSize()
        return row

    def clear(self):
        for r in self.rows:
            r.destroy()
        self.rows = []
        self.cursor = self.top
        l, r, b, t = self.sf["frameSize"]
        self.sf["canvasSize"] = (l, r - 0.06, b, t)
        self.sf.setCanvasSize()

    def destroy(self):
        self.sf.destroy()


class Toasts:
    """Small notifications stacked at the top of the screen."""

    def __init__(self, parent, theme):
        self.parent = parent
        self.theme = theme
        self.items = []

    def show(self, text, color="panel_hi", duration=2.6):
        f = panel(self.parent, self.theme, (-0.62, 0.62, -0.055, 0.055), color, 0.95, 0.05, shadow=False)
        label(f, self.theme, text, (0, -0.018), 0.045, "text", "bold")
        f.setPos(0, 0, 0.9 - 0.13 * len(self.items))
        self.items.append([f, duration])

    def update(self, dt):
        keep = []
        for i, item in enumerate(self.items):
            item[1] -= dt
            f = item[0]
            if item[1] <= 0:
                f.destroy()
                continue
            f.setAlphaScale(min(1.0, item[1] / 0.4))
            keep.append(item)
        self.items = keep
        for i, (f, _) in enumerate(self.items):
            z = 0.9 - 0.13 * i
            f.setZ(f.getZ() + (z - f.getZ()) * min(1.0, dt * 12))


def tabs(parent, theme, names, active, command, y, x0=-1.2, w=0.42, h=0.09, gap=0.04):
    """Row of tab buttons; returns the list of Buttons."""
    out = []
    for i, (key, text) in enumerate(names):
        b = Button(parent, theme, text, (x0 + i * (w + gap) + w / 2, y), (w, h), command, [key],
                   color="primary" if key == active else "panel_hi", scale=0.04)
        out.append(b)
    return out
