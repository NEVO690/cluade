"""Screen switching with a back stack and a quick fade."""

from direct.gui.DirectGui import DirectFrame
from direct.interval.IntervalGlobal import LerpColorScaleInterval


class Screen:
    """Base class.  Subclasses build widgets in build() under self.root."""

    name = "screen"
    uses_menu_scene = True  # show the 3D character diorama behind this screen
    music = "music_menu"

    def __init__(self, app):
        self.app = app
        self.theme = app.theme
        self.root = None

    def ensure_built(self):
        if self.root is None:
            self.root = DirectFrame(parent=self.app.aspect2d, frameColor=(0, 0, 0, 0))
            self.build()
            self.root.hide()

    def rebuild(self):
        if self.root is not None:
            self.root.destroy()
            self.root = None
        self.ensure_built()

    def build(self):
        pass

    def on_show(self, **kwargs):
        pass

    def on_hide(self):
        pass

    def update(self, dt):
        pass

    def on_escape(self):
        """Return True if handled."""
        return False


class ScreenManager:
    def __init__(self, app):
        self.app = app
        self.screens = {}
        self.current = None
        self.stack = []
        self.overlays = []

    def register(self, screen):
        self.screens[screen.name] = screen

    def get(self, name):
        return self.screens[name]

    def show(self, name, push=True, **kwargs):
        scr = self.screens[name]
        if self.current is not None and self.current is not scr:
            self.current.on_hide()
            if self.current.root is not None:
                self.current.root.hide()
            if push:
                self.stack.append(self.current.name)
                del self.stack[:-12]
        scr.ensure_built()
        scr.root.show()
        scr.root.setColorScale(1, 1, 1, 0)
        LerpColorScaleInterval(scr.root, 0.14, (1, 1, 1, 1), (1, 1, 1, 0)).start()
        self.current = scr
        self.app.on_screen_changed(scr)
        scr.on_show(**kwargs)
        return scr

    def back(self, default="main"):
        target = self.stack.pop() if self.stack else default
        while target == (self.current.name if self.current else None) and self.stack:
            target = self.stack.pop()
        self.show(target, push=False)

    def reset_to(self, name, **kwargs):
        self.stack.clear()
        return self.show(name, push=False, **kwargs)

    def update(self, dt):
        if self.current is not None:
            self.current.update(dt)

    def escape(self):
        if self.current is not None and self.current.on_escape():
            return
        if self.current is not None and self.current.name not in ("main", "splash", "hud"):
            self.back()
