"""SETTINGS screen."""

from direct.gui.DirectGui import DirectFrame, DirectSlider

from ..theme import c
from ..widgets import Button, label, panel
from .common import BaseScreen


class SettingsScreen(BaseScreen):
    name = "settings"
    uses_menu_scene = False

    SLIDERS = [
        ("master_volume", "Master volume", 0.0, 1.0),
        ("sfx_volume", "Sound effects", 0.0, 1.0),
        ("music_volume", "Music", 0.0, 1.0),
        ("mouse_sensitivity", "Mouse sensitivity", 0.2, 3.0),
        ("camera_distance", "Camera distance", 4.0, 12.0),
    ]
    TOGGLES = [
        ("always_run", "Always run (hold SHIFT to walk)"),
        ("invert_y", "Invert camera Y"),
        ("shadows", "Shadows"),
        ("show_fps", "Show FPS counter (restart)"),
        ("fullscreen", "Fullscreen (restart)"),
    ]

    def build(self):
        self.header("SETTINGS", coins=False)
        self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))

    def on_show(self, **kw):
        th = self.theme
        prof = self.app.profile
        s = prof.settings
        self.holder.destroy()
        h = self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        p = panel(h, th, (-0.78, 0.78, -0.62, 0.62), "panel", 0.92, 0.08, pos=(-0.75, 0, 0.0))
        label(p, th, "AUDIO & CONTROLS", (-0.7, 0.52), 0.045, "secondary", "title", "left")
        self.value_labels = {}
        for i, (key, text, lo, hi) in enumerate(self.SLIDERS):
            y = 0.38 - i * 0.2
            label(p, th, text, (-0.7, y + 0.03), 0.04, "text", "bold", "left")
            vl = label(p, th, "", (0.7, y + 0.03), 0.04, "accent", "bold", "right")
            self.value_labels[key] = vl
            sl = DirectSlider(parent=p, range=(lo, hi), value=s[key], pageSize=(hi - lo) / 20, pos=(0, 0, y - 0.04),
                              scale=0.68, frameColor=c("dark", 0.8), frameSize=(-1, 1, -0.02, 0.02),
                              thumb_frameColor=c("primary"), thumb_frameSize=(-0.04, 0.04, -0.05, 0.05),
                              thumb_relief=1)
            sl["command"] = self._slider_changed
            sl["extraArgs"] = [key, sl]
            self._show_value(key, s[key])
        q = panel(h, th, (-0.78, 0.78, -0.62, 0.62), "panel", 0.92, 0.08, pos=(0.85, 0, 0.0))
        label(q, th, "GAMEPLAY & VIDEO", (-0.7, 0.52), 0.045, "secondary", "title", "left")
        self.toggle_btns = {}
        for i, (key, text) in enumerate(self.TOGGLES):
            y = 0.4 - i * 0.12
            label(q, th, text, (-0.7, y - 0.015), 0.038, "text", "bold", "left")
            b = Button(q, th, "", (0.58, y), (0.24, 0.08), self._toggle, [key], scale=0.035)
            self.toggle_btns[key] = b
            self._paint_toggle(key)
        label(q, th, "Resolution (restart)", (-0.7, -0.24), 0.038, "text", "bold", "left")
        self.res_btn = Button(q, th, s["resolution"], (0.5, -0.225), (0.4, 0.08), self._cycle_res, scale=0.035,
                              color="blue")
        label(q, th, "Controls: WASD/arrows move, SPACE jump, SHIFT walk,\nmouse or Q/E camera, ESC pause. "
                     "Gamepads: left stick,\nright stick camera, A jump, B walk.", (0, -0.45), 0.032, "muted",
              "body")
        Button(h, th, "SAVE", (1.35, -0.85), (0.4, 0.11), self._save, color="primary")

    def _show_value(self, key, value):
        if key.endswith("volume"):
            txt = "%d%%" % int(round(value * 100))
        else:
            txt = "%.1f" % value
        self.value_labels[key]["text"] = txt

    def _slider_changed(self, key, slider):
        v = self.app.profile.set_setting(key, float(slider["value"]))
        self._show_value(key, v)
        if key.endswith("volume"):
            self.app.sounds.apply_volumes()

    def _paint_toggle(self, key):
        on = self.app.profile.settings[key]
        b = self.toggle_btns[key]
        b.set_text("ON" if on else "OFF")
        b.set_color("success" if on else "panel_hi")

    def _toggle(self, key):
        prof = self.app.profile
        prof.set_setting(key, not prof.settings[key])
        self._paint_toggle(key)
        if key == "shadows":
            self.app.apply_shadow_setting()

    def _cycle_res(self):
        opts = ["1280x720", "1600x900", "1920x1080", "1024x600"]
        cur = self.app.profile.settings["resolution"]
        nxt = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else opts[0]
        self.app.profile.set_setting("resolution", nxt)
        self.res_btn.set_text(nxt)

    def _save(self):
        if self.app.profile.save():
            self.app.toasts.show("Settings saved", "success")
        else:
            self.app.toasts.show("Could not save settings!", "danger")
        if self.app.session is not None:
            self.app.session.camera.distance = self.app.profile.settings["camera_distance"]

    def on_hide(self):
        self.app.profile.save()
        if self.app.session is not None:
            self.app.session.camera.distance = self.app.profile.settings["camera_distance"]
