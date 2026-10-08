"""Audio manager: sound effects + crossfading zone music.

Lookup order for every sound ``name``:
  1. ``assets/sounds/<name>.wav|.ogg|.mp3`` (your own file, if present)
  2. procedurally synthesised placeholder (see synth.py)

Music for a track id (zone id or ``menu``):
  1. ``assets/music/<id>.ogg|.wav|.mp3``
  2. cached synthesised loop in ``cache/music/<id>.wav``
  3. freshly synthesised loop (then cached)

If the audio device cannot be opened the game keeps running silently.
"""
import os
import wave

import pygame

from . import settings as S
from .synth import Synth, np
from .utils import log, warn

SFX_NAMES = ("jump", "land", "coin", "gem", "token", "powerup", "jet", "hit", "stumble", "slide",
             "whoosh", "button", "back", "buy", "error", "game_over", "unlock", "achievement",
             "mission", "level_up", "shield_break", "board", "countdown", "go", "smash")

# Bump to invalidate cached music after changing the synthesiser.
MUSIC_CACHE_VERSION = 2


def _find_file(folder, name):
    for ext in (".ogg", ".wav", ".mp3"):
        p = os.path.join(folder, name + ext)
        if os.path.isfile(p):
            return p
    return None


class AudioManager:
    def __init__(self, settings_store):
        self.settings = settings_store
        self.enabled = False
        self.sounds = {}
        self.music = {}
        self.current_track = None
        self._music_channel_idx = 0
        self._channels = []
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 512)
            freq, _size, channels = pygame.mixer.get_init()
            pygame.mixer.set_num_channels(24)
            pygame.mixer.set_reserved(2)
            self._channels = [pygame.mixer.Channel(0), pygame.mixer.Channel(1)]
            self.synth = Synth(freq, channels)
            self.enabled = True
        except (pygame.error, TypeError) as e:
            warn(f"Audio device unavailable - playing without sound ({e})")
            self.synth = None

    # ------------------------------------------------------------------
    # Loading (called step by step from the loading screen)
    # ------------------------------------------------------------------
    def load_steps(self, music_specs):
        """Yield human readable step names while loading; lets the loading screen animate."""
        if not self.enabled:
            return
        for name in SFX_NAMES:
            self._load_sfx(name)
        yield "Sound effects"
        for track_id, spec in music_specs:
            yield f"Music: {track_id}"
            self._load_music(track_id, spec)

    def _load_sfx(self, name):
        path = _find_file(S.SOUNDS_DIR, name)
        if path:
            try:
                self.sounds[name] = pygame.mixer.Sound(path)
                return
            except pygame.error as e:
                warn(f"Could not load sound {os.path.basename(path)}: {e} - using generated sound")
        try:
            data = self.synth.make_sfx(name)
            if np is not None:
                peak = float(np.max(np.abs(data))) if len(data) else 0.0
                if peak > 0.9:
                    data = data * (0.9 / peak)
            self.sounds[name] = pygame.mixer.Sound(buffer=self.synth.to_bytes(data))
        except Exception as e:  # never let a synth problem stop the game
            log.error("Failed to synthesise sound %s: %s", name, e)

    def _load_music(self, track_id, spec):
        path = _find_file(S.MUSIC_DIR, track_id)
        if path:
            try:
                self.music[track_id] = pygame.mixer.Sound(path)
                return
            except pygame.error as e:
                warn(f"Could not load music {os.path.basename(path)}: {e} - using generated music")
        if np is None:
            return  # pure-python music synthesis would be too slow; play without music
        cache_dir = os.path.join(S.CACHE_DIR, "music")
        cache = os.path.join(cache_dir, f"{track_id}_v{MUSIC_CACHE_VERSION}_{self.synth.rate}.wav")
        if os.path.isfile(cache):
            try:
                self.music[track_id] = pygame.mixer.Sound(cache)
                return
            except pygame.error:
                pass
        try:
            seed = sum(ord(c) for c in track_id) * 31
            left, right = self.synth.make_music(spec, seed=seed)
            raw = self.synth.to_bytes_stereo(left, right)
            self.music[track_id] = pygame.mixer.Sound(buffer=raw)
            try:
                os.makedirs(cache_dir, exist_ok=True)
                with wave.open(cache, "wb") as w:
                    w.setnchannels(self.synth.channels)
                    w.setsampwidth(2)
                    w.setframerate(self.synth.rate)
                    w.writeframes(raw)
            except OSError as e:
                log.warning("Could not cache music %s: %s", track_id, e)
        except Exception as e:
            log.error("Failed to synthesise music %s: %s", track_id, e)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------
    def play(self, name, volume=1.0):
        if not self.enabled:
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        try:
            ch = snd.play()
            if ch is not None:
                ch.set_volume(max(0.0, min(1.0, volume * self.settings["sfx_volume"])))
        except pygame.error:
            pass

    def play_music(self, track_id, fade_ms=1200):
        if not self.enabled or track_id == self.current_track:
            return
        snd = self.music.get(track_id)
        old = self._channels[self._music_channel_idx]
        old.fadeout(fade_ms)
        self.current_track = track_id
        if snd is None:
            return
        self._music_channel_idx = 1 - self._music_channel_idx
        ch = self._channels[self._music_channel_idx]
        ch.set_volume(self.settings["music_volume"] * 0.7)
        ch.play(snd, loops=-1, fade_ms=fade_ms)

    def stop_music(self, fade_ms=600):
        if not self.enabled:
            return
        for ch in self._channels:
            ch.fadeout(fade_ms)
        self.current_track = None

    def pause_music(self, paused):
        if not self.enabled:
            return
        for ch in self._channels:
            if paused:
                ch.pause()
            else:
                ch.unpause()

    def apply_volume(self):
        if not self.enabled:
            return
        self._channels[self._music_channel_idx].set_volume(self.settings["music_volume"] * 0.7)
