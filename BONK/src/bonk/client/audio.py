"""Sound effects and music.  Missing audio hardware or files never stop the game."""

import logging
import os

from panda3d.core import Filename

from ..paths import AUDIO_DIR

log = logging.getLogger(__name__)

SFX = ("jump", "land", "bonk", "hit", "fall", "splash", "beep", "go", "checkpoint", "finish",
       "eliminated", "victory", "click", "hover", "coin", "error", "bounce")


class SoundBank:
    def __init__(self, base, settings):
        self.base = base
        self.settings = settings
        self.sounds = {}
        self.music = {}
        self.current_music = None
        self.enabled = base.sfxManagerList and base.sfxManagerList[0].isValid()
        for name in SFX:
            self.sounds[name] = self._load(name, music=False)
        for name in ("music_menu", "music_race"):
            self.music[name] = self._load(name, music=True)
        self.apply_volumes()

    def _load(self, name, music):
        path = os.path.join(AUDIO_DIR, name + ".wav")
        if not os.path.exists(path):
            log.warning("missing sound %s", path)
            return None
        try:
            loader = self.base.loader.loadMusic if music else self.base.loader.loadSfx
            snd = loader(Filename.fromOsSpecific(path))
            if music and snd is not None:
                snd.setLoop(True)
            return snd
        except Exception as exc:
            log.warning("could not load %s: %s", path, exc)
            return None

    def apply_volumes(self):
        master = self.settings.get("master_volume", 0.8)
        if self.base.sfxManagerList:
            self.base.sfxManagerList[0].setVolume(master * self.settings.get("sfx_volume", 0.9))
        if self.base.musicManager:
            self.base.musicManager.setVolume(master * self.settings.get("music_volume", 0.6))

    def play(self, name, volume=1.0, rate=1.0):
        snd = self.sounds.get(name)
        if snd is None:
            return
        snd.setVolume(volume)
        snd.setPlayRate(rate)
        snd.play()

    def play_music(self, name):
        if self.current_music == name:
            return
        for key, m in self.music.items():
            if m is not None and key != name:
                m.stop()
        m = self.music.get(name)
        if m is not None:
            m.play()
        self.current_music = name
