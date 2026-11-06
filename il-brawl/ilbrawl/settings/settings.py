"""Player settings with persistence."""
from ilbrawl import config

DEFAULT_CONTROLS = {
    "up": "w",
    "down": "s",
    "left": "a",
    "right": "d",
    "attack": "space",
    "super": "e",
    "autoaim": "q",
}

DEFAULTS = {
    "language": config.DEFAULT_LANGUAGE,
    "music_volume": 0.6,
    "sfx_volume": 0.8,
    "graphics": "high",          # low / medium / high
    "fullscreen": False,
    "resolution": [1280, 720],
    "ai_difficulty": "normal",   # easy / normal / hard / expert
    "show_fps": False,
    "screen_shake": True,
    "controls": dict(DEFAULT_CONTROLS),
}

GRAPHICS_LEVELS = ["low", "medium", "high"]
DIFFICULTIES = ["easy", "normal", "hard", "expert"]


class Settings:
    FILE = "settings"

    def __init__(self, save_manager):
        self.sm = save_manager
        self.data = self.sm.load(self.FILE, DEFAULTS)
        self._validate()

    def _validate(self):
        d = self.data
        if d.get("language") not in config.LANGUAGES:
            d["language"] = config.DEFAULT_LANGUAGE
        if d.get("graphics") not in GRAPHICS_LEVELS:
            d["graphics"] = "high"
        if d.get("ai_difficulty") not in DIFFICULTIES:
            d["ai_difficulty"] = "normal"
        for k in ("music_volume", "sfx_volume"):
            try:
                d[k] = max(0.0, min(1.0, float(d[k])))
            except (TypeError, ValueError):
                d[k] = DEFAULTS[k]
        res = d.get("resolution")
        if not (isinstance(res, list) and len(res) == 2 and all(isinstance(v, int) and v > 200 for v in res)):
            d["resolution"] = [1280, 720]
        controls = d.get("controls") or {}
        for k, v in DEFAULT_CONTROLS.items():
            if not isinstance(controls.get(k), str):
                controls[k] = v
        d["controls"] = controls

    def __getitem__(self, k):
        return self.data[k]

    def get(self, k, default=None):
        return self.data.get(k, default)

    def set(self, k, v, save=True):
        self.data[k] = v
        if save:
            self.save()

    def save(self):
        return self.sm.save(self.FILE, self.data)

    def reset_controls(self):
        self.data["controls"] = dict(DEFAULT_CONTROLS)
        self.save()
