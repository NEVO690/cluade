"""Sound effects (2D and positional) and music with volume settings."""
from __future__ import annotations

import logging
import random

from panda3d.core import AudioSound

from game.assets import fn

log = logging.getLogger(__name__)


class AudioManager:
    def __init__(self, app):
        self.app = app
        self.settings = app.settings
        self.enabled = app.sfxManagerList and app.sfxManagerList[0].isValid()
        self._sounds: dict[str, list[AudioSound]] = {}
        self._loops: dict[str, AudioSound] = {}
        self.music: AudioSound | None = None
        self.music_name = None
        self._fade_task = None

    def _load(self, name: str) -> AudioSound | None:
        path = self.app.assets.sound_path(name)
        if path is None:
            return None
        try:
            return self.app.loader.loadSfx(fn(path))
        except Exception as exc:  # pragma: no cover
            log.warning("Sound %s failed: %s", name, exc)
            return None

    def _voice(self, name: str) -> AudioSound | None:
        pool = self._sounds.setdefault(name, [])
        for s in pool:
            if s.status() != AudioSound.PLAYING:
                return s
        if len(pool) < 6:
            s = self._load(name)
            if s is not None:
                pool.append(s)
                return s
        return pool[0] if pool else None

    @property
    def sfx_volume(self) -> float:
        return self.settings.master_volume * self.settings.sfx_volume

    def play(self, name: str, volume: float = 1.0, rate: float = 1.0, *, pos=None, listener=None) -> None:
        if not self.enabled:
            return
        if pos is not None and listener is not None:
            dx, dy, dz = pos[0] - listener[0], pos[1] - listener[1], pos[2] - listener[2]
            dist = (dx * dx + dy * dy + dz * dz) ** 0.5
            if dist > 260:
                return
            volume *= max(0.0, 1.0 - dist / 260) ** 1.6
            rate *= random.uniform(0.96, 1.04)
        s = self._voice(name)
        if s is None:
            return
        s.setVolume(min(1.0, volume * self.sfx_volume))
        s.setPlayRate(rate)
        s.play()

    def loop(self, name: str, volume: float) -> None:
        if not self.enabled:
            return
        s = self._loops.get(name)
        if s is None:
            s = self._load(name)
            if s is None:
                return
            s.setLoop(True)
            self._loops[name] = s
        s.setVolume(min(1.0, volume * self.sfx_volume))
        if volume > 0.001 and s.status() != AudioSound.PLAYING:
            s.play()
        elif volume <= 0.001 and s.status() == AudioSound.PLAYING:
            s.stop()

    def stop_loops(self) -> None:
        for s in self._loops.values():
            s.stop()

    def play_music(self, name: str | None) -> None:
        if name == self.music_name:
            return
        if self.music is not None:
            self.music.stop()
        self.music_name = name
        self.music = None
        if not name or not self.app.musicManager.isValid():
            return
        path = self.app.assets.sound_path(name)
        if path is None:
            return
        self.music = self.app.loader.loadMusic(fn(path))
        self.music.setLoop(True)
        self.refresh_volume()
        self.music.play()

    def refresh_volume(self) -> None:
        if self.music is not None:
            self.music.setVolume(self.settings.master_volume * self.settings.music_volume * 0.7)
