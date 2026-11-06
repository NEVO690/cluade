"""Audio manager: sound effects and music with volume control.

Works silently when no audio device is available or files are missing.
"""
import os
import random

import pygame

from ilbrawl import config

SOUND_NAMES = [
    "click", "tab", "deny", "buy", "reward", "levelup", "shoot", "shoot_heavy", "laser", "lob", "melee",
    "flame", "hit", "hurt", "explosion", "super", "super_ready", "heal", "death", "gem", "goal",
    "victory", "defeat", "countdown", "go", "capture", "dash", "shield", "unlock", "whoosh",
]
MUSIC = {"menu": "menu_theme.wav", "battle": "battle_theme.wav"}


class AudioManager:
    def __init__(self, settings):
        self.settings = settings
        self.enabled = False
        self.sounds = {}
        self.current_music = None
        self._cooldowns = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(22050, -16, 1, 512)
                pygame.mixer.init()
            pygame.mixer.set_num_channels(24)
            self.enabled = True
        except (pygame.error, NotImplementedError, AttributeError):
            self.enabled = False
        if self.enabled:
            for name in SOUND_NAMES:
                path = os.path.join(config.SOUND_DIR, name + ".wav")
                try:
                    self.sounds[name] = pygame.mixer.Sound(path)
                except (pygame.error, FileNotFoundError, OSError):
                    pass

    def play(self, name, volume=1.0, throttle=0.04):
        if not self.enabled:
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        now = pygame.time.get_ticks() / 1000.0
        if now - self._cooldowns.get(name, -1) < throttle:
            return
        self._cooldowns[name] = now
        try:
            snd.set_volume(max(0.0, min(1.0, volume * self.settings["sfx_volume"] * random.uniform(0.92, 1.0))))
            snd.play()
        except pygame.error:
            pass

    def play_music(self, key):
        if not self.enabled or key == self.current_music:
            return
        fn = MUSIC.get(key)
        if not fn:
            return
        path = os.path.join(config.MUSIC_DIR, fn)
        try:
            pygame.mixer.music.fadeout(300)
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.settings["music_volume"] * 0.7)
            pygame.mixer.music.play(-1, fade_ms=800)
            self.current_music = key
        except (pygame.error, FileNotFoundError, OSError):
            self.current_music = None

    def stop_music(self):
        if self.enabled:
            try:
                pygame.mixer.music.fadeout(400)
            except pygame.error:
                pass
        self.current_music = None

    def apply_volume(self):
        if self.enabled:
            try:
                pygame.mixer.music.set_volume(self.settings["music_volume"] * 0.7)
            except pygame.error:
                pass


_INSTANCE = None


def set_instance(a):
    global _INSTANCE
    _INSTANCE = a


def play(name, volume=1.0, throttle=0.04):
    if _INSTANCE:
        _INSTANCE.play(name, volume, throttle)


def music(key):
    if _INSTANCE:
        _INSTANCE.play_music(key)
