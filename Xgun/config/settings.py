"""Player-adjustable settings, persisted as JSON in the user folder."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields

from config import paths

log = logging.getLogger(__name__)

QUALITY_PRESETS = ("Low", "Medium", "High")


@dataclass
class Settings:
    window_width: int = 1600
    window_height: int = 900
    fullscreen: bool = False
    vsync: bool = True
    quality: str = "High"          # Low / Medium / High
    shadows: bool = True
    view_distance: int = 900       # metres
    fov: int = 75
    mouse_sensitivity: float = 1.0
    ads_sensitivity: float = 0.6
    invert_y: bool = False
    master_volume: float = 0.8
    music_volume: float = 0.5
    sfx_volume: float = 0.9
    show_fps: bool = False
    bot_count: int = 19            # opponents in an offline match
    bot_difficulty: str = "Normal" # Easy / Normal / Hard
    autoplay_videos: bool = True
    online_address: str = ""       # last server joined (host[:port])
    social_server: str = ""        # online social server URL ("" = local only)
    social_username: str = ""
    social_token: str = ""         # session token from the social server (the password is never stored)

    @classmethod
    def load(cls) -> "Settings":
        path = paths.settings_file()
        settings = cls()
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                known = {f.name: f.type for f in fields(cls)}
                for key, value in raw.items():
                    if key in known:
                        setattr(settings, key, value)
            except (OSError, ValueError) as exc:
                log.warning("Settings file unreadable, using defaults: %s", exc)
        settings.clamp()
        return settings

    def clamp(self) -> None:
        self.window_width = max(1024, int(self.window_width))
        self.window_height = max(600, int(self.window_height))
        if self.quality not in QUALITY_PRESETS:
            self.quality = "High"
        self.view_distance = int(min(1500, max(300, self.view_distance)))
        self.fov = int(min(100, max(60, self.fov)))
        self.mouse_sensitivity = float(min(3.0, max(0.1, self.mouse_sensitivity)))
        self.ads_sensitivity = float(min(2.0, max(0.1, self.ads_sensitivity)))
        for vol in ("master_volume", "music_volume", "sfx_volume"):
            setattr(self, vol, float(min(1.0, max(0.0, getattr(self, vol)))))
        self.bot_count = int(min(39, max(1, self.bot_count)))
        if self.bot_difficulty not in ("Easy", "Normal", "Hard"):
            self.bot_difficulty = "Normal"

    def save(self) -> None:
        self.clamp()
        paths.settings_file().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
