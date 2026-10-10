"""Objective checks on the generated audio (nobody can listen in CI)."""
import wave

import numpy as np
import pytest

from config import paths

REQUIRED = ["shot_ar", "shot_smg", "shot_shotgun", "shot_sniper", "shot_pistol", "shot_ion", "reload", "equip", "swing",
            "pickaxe_hit", "hit_marker", "headshot", "shield_break", "elim", "pickup", "chest_open", "crate_break", "jump",
            "land", "glider_deploy", "wind_loop", "ship_loop", "storm_loop", "heal_loop", "heal_done", "ui_click", "ui_hover",
            "ui_purchase", "ui_error", "notify", "victory", "defeat", "level_up"]


def _read(path):
    with wave.open(str(path)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        return data, w.getframerate(), w.getnchannels()


@pytest.mark.parametrize("name", REQUIRED)
def test_sfx_is_audible_not_clipped_and_short(name):
    data, rate, channels = _read(paths.SFX / f"{name}.wav")
    assert channels == 1 and rate == 22050
    assert 0.03 < len(data) / rate < 5.0
    peak = np.abs(data).max()
    rms = np.sqrt(np.mean(data ** 2))
    assert 0.2 < peak <= 0.999, f"{name} peak {peak:.2f}"          # audible, not hard-clipped
    assert rms > 0.01, f"{name} is nearly silent"
    clipped = np.mean(np.abs(data) > 0.995)
    assert clipped < 0.002, f"{name} clips on {clipped:.1%} of samples"
    assert abs(data[-1]) < 0.2 or name.endswith("_loop")             # no click at the end


def test_loops_wrap_without_a_big_click():
    for name in ("wind_loop", "ship_loop", "storm_loop", "heal_loop"):
        data, _, _ = _read(paths.SFX / f"{name}.wav")
        assert abs(data[0] - data[-1]) < 0.35, name


def test_gunshots_are_distinct():
    spectra = {}
    for name in ("shot_ar", "shot_smg", "shot_shotgun", "shot_sniper", "shot_pistol", "shot_ion"):
        data, rate, _ = _read(paths.SFX / f"{name}.wav")
        mag = np.abs(np.fft.rfft(data[: rate // 4], n=rate // 2))
        spectra[name] = mag / (np.linalg.norm(mag) + 1e-9)
    names = list(spectra)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            sim = float(spectra[names[i]] @ spectra[names[j]])
            assert sim < 0.985, f"{names[i]} and {names[j]} sound almost identical ({sim:.3f})"


def test_music_tracks_exist_and_play_long_enough():
    for name in ("lobby_theme", "battle_theme", "results_theme"):
        f = paths.MUSIC / f"{name}.ogg"
        assert f.exists() and f.stat().st_size > 50_000, name


def test_music_decodes_with_the_game_audio_stack():
    from panda3d.core import Filename, MovieAudio
    for name in ("lobby_theme", "battle_theme", "results_theme"):
        cursor = MovieAudio.get(Filename.from_os_specific(str(paths.MUSIC / f"{name}.ogg"))).open()
        assert cursor is not None and cursor.length() >= 15, name
        assert cursor.audioRate() >= 22050 and cursor.audioChannels() >= 1, name
        from panda3d.core import Datagram
        dg = Datagram()
        cursor.readSamples(4000, dg)
        assert dg.getLength() >= 4000 * 2 * cursor.audioChannels(), name
