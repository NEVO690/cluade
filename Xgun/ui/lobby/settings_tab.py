"""SETTINGS tab: graphics, audio, controls and data."""
from __future__ import annotations

from config import paths
from config.settings import QUALITY_PRESETS
from ui import theme as T
from ui.lobby.common import Tab, header
from ui.widgets import Button, Slider, Toggle, frame, text

RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]


class SettingsTab(Tab):
    def build(self):
        r = self.root
        s = self.app.settings
        header(r, "SETTINGS", "Changes save automatically. Some graphics options apply on the next match or restart.")
        cols = [(-1.62, "GRAPHICS"), (-0.5, "AUDIO"), (0.62, "CONTROLS & GAMEPLAY")]
        for x, title in cols:
            frame(r, x - 0.03, x + 1.05, -0.82, 0.56, T.PANEL)
            text(r, title, (x, 0.48), 0.034, T.ACCENT, "black")
        x = -1.62
        self._label(x, 0.38, "Quality")
        self.q_btns = []
        for i, q in enumerate(QUALITY_PRESETS):
            b = Button(r, q, self._quality, pos=(x + 0.12 + i * 0.25, 0.32), size=(0.23, 0.06), text_scale=0.026, extra_args=(q,))
            b.set_selected(s.quality == q)
            self.q_btns.append((q, b))
        self._label(x, 0.22, "Resolution")
        self.res_btns = []
        for i, (w, h) in enumerate(RESOLUTIONS):
            b = Button(r, f"{w}x{h}", self._res, pos=(x + 0.12 + (i % 2) * 0.37, 0.16 - (i // 2) * 0.07), size=(0.35, 0.06),
                       text_scale=0.024, extra_args=(w, h))
            b.set_selected((s.window_width, s.window_height) == (w, h))
            self.res_btns.append(((w, h), b))
        self._toggle(x, -0.04, "Fullscreen", s.fullscreen, lambda v: self._set("fullscreen", v, apply=True))
        self._toggle(x, -0.13, "Shadows", s.shadows, lambda v: self._set("shadows", v))
        self._toggle(x, -0.22, "V-Sync", s.vsync, lambda v: self._set("vsync", v))
        self._toggle(x, -0.31, "Show FPS (F3)", s.show_fps, lambda v: self._set("show_fps", v))
        self._label(x, -0.42, "View distance")
        Slider(r, s.view_distance, 300, 1500, lambda v: self._set("view_distance", int(v)), pos=(x, -0.48), width=0.7, fmt="{:.0f} m")
        self._label(x, -0.58, "Field of view")
        Slider(r, s.fov, 60, 100, lambda v: self._set("fov", int(v)), pos=(x, -0.64), width=0.7, fmt="{:.0f}°")

        x = -0.5
        for i, (key, label) in enumerate((("master_volume", "Master"), ("music_volume", "Music"), ("sfx_volume", "Effects"))):
            self._label(x, 0.38 - i * 0.16, label)
            Slider(r, getattr(s, key), 0, 1, lambda v, k=key: self._set(k, v, audio=True), pos=(x, 0.32 - i * 0.16), width=0.7)
        self._toggle(x, -0.13, "Autoplay videos", s.autoplay_videos, lambda v: self._set("autoplay_videos", v))

        x = 0.62
        self._label(x, 0.38, "Mouse sensitivity")
        Slider(r, s.mouse_sensitivity, 0.1, 3.0, lambda v: self._set("mouse_sensitivity", v), pos=(x, 0.32), width=0.7,
               fmt="{:.2f}")
        self._label(x, 0.22, "Aim sensitivity")
        Slider(r, s.ads_sensitivity, 0.1, 2.0, lambda v: self._set("ads_sensitivity", v), pos=(x, 0.16), width=0.7, fmt="{:.2f}")
        self._toggle(x, 0.06, "Invert Y", s.invert_y, lambda v: self._set("invert_y", v))
        keys = ["Move  W A S D", "Sprint  Shift", "Jump / Deploy  Space", "Crouch  C (toggle) / Ctrl", "Fire  LMB  •  Aim  RMB",
                "Reload  R  •  Interact  E (hold)", "Slots  1-6 / Wheel", "Emote  B  •  Map  M  •  Pause  Esc",
                "Screenshot  F12"]
        for i, k in enumerate(keys):
            text(r, k, (x, -0.06 - i * 0.055), 0.025, T.TEXT_DIM, "semibold")
        text(r, f"Save data: {paths.user_dir()}", (-1.62, -0.88), 0.022, T.TEXT_MUTED, "regular")

    def _label(self, x, y, label):
        text(self.root, label, (x, y), 0.028, T.TEXT, "bold")

    def _toggle(self, x, y, label, value, cmd):
        self._label(x, y - 0.012, label)
        Toggle(self.root, value, cmd, pos=(x + 0.9, y))

    def _set(self, key, value, *, audio=False, apply=False):
        setattr(self.app.settings, key, value)
        self.app.settings.save()
        if audio:
            self.app.audio.refresh_volume()
        if apply:
            self.app.apply_settings()

    def _quality(self, q):
        self._set("quality", q)
        for v, b in self.q_btns:
            b.set_selected(v == q)
        self.app.toasts.show("Quality changes take full effect after a restart.", "info")

    def _res(self, w, h):
        self.app.settings.window_width, self.app.settings.window_height = w, h
        self.app.apply_settings()
        for v, b in self.res_btns:
            b.set_selected(v == (w, h))
