"""Synthesize every Xgun sound effect and music loop (original, procedural).

    python tools/audio_generation/generate_audio.py

Writes WAV effects to assets/audio/sfx and music to assets/audio/music
(OGG when ffmpeg is available, WAV otherwise).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SFX = ROOT / "assets" / "audio" / "sfx"
MUSIC = ROOT / "assets" / "audio" / "music"
SR = 22050
rng = np.random.default_rng(1234)


def t(sec, sr=SR):
    return np.arange(int(sec * sr)) / sr


def env(n, attack=0.002, decay=0.2, sr=SR, curve=3.0):
    x = np.arange(n) / sr
    a = np.clip(x / max(attack, 1e-4), 0, 1)
    d = np.exp(-np.maximum(0, x - attack) / max(decay, 1e-4) * curve / 3)
    return a * d


def noise(n):
    return rng.uniform(-1, 1, n)


def lowpass(x, cutoff, sr=SR):
    a = np.exp(-2 * np.pi * cutoff / sr)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def lp_fast(x, cutoff, sr=SR):
    """FFT brick-ish low-pass (fast for long buffers)."""
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    spec *= 1 / (1 + (freqs / cutoff) ** 4)
    return np.fft.irfft(spec, len(x))


def hp_fast(x, cutoff, sr=SR):
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    spec *= 1 / (1 + (cutoff / np.maximum(freqs, 1)) ** 4)
    return np.fft.irfft(spec, len(x))


def tone(freq, sec, kind="sine", sr=SR):
    tt = t(sec, sr)
    f = np.full_like(tt, freq) if np.isscalar(freq) else freq
    ph = 2 * np.pi * np.cumsum(f) / sr
    if kind == "sine":
        return np.sin(ph)
    if kind == "square":
        return np.sign(np.sin(ph)) * 0.6
    if kind == "saw":
        return ((ph / (2 * np.pi)) % 1) * 2 - 1
    if kind == "tri":
        return 2 * np.abs(((ph / (2 * np.pi)) % 1) * 2 - 1) - 1
    raise ValueError(kind)


def norm(x, peak=0.9):
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


def write(path: Path, x, sr=SR):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1 if data.ndim == 1 else 2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


# ------------------------------------------------------------------ sfx
def gunshot(body_hz, length, crack=0.5, boom=0.6, tail=0.25):
    n = int(length * SR)
    crack_part = hp_fast(noise(n), 1800) * env(n, 0.0005, 0.03) * crack
    body = lp_fast(noise(n), body_hz * 6) * env(n, 0.001, 0.08) * 1.0
    thump = tone(np.linspace(body_hz * 1.6, body_hz * 0.6, n), length) * env(n, 0.001, 0.09) * boom
    rumble = lp_fast(noise(n), 400) * env(n, 0.01, tail) * 0.5
    return norm(crack_part + body + thump + rumble)


def build_sfx():
    s = {}
    s["shot_ar"] = gunshot(110, 0.45)
    s["shot_smg"] = gunshot(150, 0.3, crack=0.7, boom=0.4, tail=0.12)
    s["shot_shotgun"] = gunshot(70, 0.9, crack=0.4, boom=1.0, tail=0.5)
    s["shot_sniper"] = norm(gunshot(80, 1.4, crack=0.9, boom=0.9, tail=0.8) +
                            0.25 * lp_fast(noise(int(1.4 * SR)), 900) * env(int(1.4 * SR), 0.2, 0.9))
    s["shot_pistol"] = gunshot(170, 0.35, crack=0.8, boom=0.5, tail=0.1)
    n = int(0.5 * SR)
    zap = tone(np.linspace(2400, 300, n), 0.5, "saw") * env(n, 0.001, 0.15)
    s["shot_ion"] = norm(lp_fast(zap, 5000) + 0.4 * tone(np.linspace(900, 120, n), 0.5) * env(n, 0.001, 0.2) +
                         0.2 * hp_fast(noise(n), 3000) * env(n, 0.001, 0.03))
    s["dry_fire"] = norm(hp_fast(noise(int(0.08 * SR)), 2500) * env(int(0.08 * SR), 0.0005, 0.01)) * 0.6

    def click(at, total, hz=3000, amp=1.0):
        out = np.zeros(int(total * SR))
        k = int(at * SR)
        m = int(0.04 * SR)
        out[k:k + m] += hp_fast(noise(m), hz) * env(m, 0.0005, 0.01) * amp
        return out
    s["reload"] = norm(click(0.05, 1.0, 1500) + click(0.45, 1.0, 2500, 0.8) + click(0.8, 1.0, 1800))
    s["equip"] = norm(click(0.0, 0.3, 2000) + click(0.12, 0.3, 3500, 0.6)) * 0.7
    n = int(0.35 * SR)
    s["swing"] = norm(lp_fast(noise(n), 1200) * np.sin(np.linspace(0, np.pi, n)) ** 2) * 0.6
    n = int(0.3 * SR)
    s["pickaxe_hit"] = norm(tone(np.linspace(900, 500, n), 0.3, "tri") * env(n, 0.001, 0.06) + hp_fast(noise(n), 1500) * env(n, 0.0005, 0.02))
    n = int(0.12 * SR)
    s["hit_marker"] = norm(tone(1800, 0.12) * env(n, 0.001, 0.03) + tone(2700, 0.12) * env(n, 0.001, 0.02) * 0.5) * 0.7
    n = int(0.3 * SR)
    s["headshot"] = norm(tone(2400, 0.3) * env(n, 0.001, 0.08) + tone(3600, 0.3) * env(n, 0.001, 0.12) * 0.6 +
                         tone(1200, 0.3, "tri") * env(n, 0.001, 0.05) * 0.4) * 0.8
    n = int(0.6 * SR)
    s["shield_break"] = norm(hp_fast(noise(n), 2000) * env(n, 0.001, 0.2) * 0.6 +
                             sum(tone(f, 0.6) * env(n, 0.001, 0.3) for f in (1320, 1760, 2093)) * 0.3)
    n = int(0.9 * SR)
    s["elim"] = norm(sum(tone(f, 0.9, "tri") * env(n, 0.005, 0.6) * (0.6 ** i) for i, f in enumerate((523, 659, 784, 1046))))
    n = int(0.25 * SR)
    s["pickup"] = norm(tone(np.linspace(600, 1200, n), 0.25, "tri") * env(n, 0.002, 0.12)) * 0.6
    n = int(1.4 * SR)
    sparkle = sum(tone(f, 1.4) * env(n, 0.005 + i * 0.05, 0.6) * 0.5 for i, f in enumerate((880, 1109, 1319, 1760, 2217)))
    s["chest_open"] = norm(sparkle + click(0.0, 1.4, 900, 1.2) * 0.8)
    n = int(2.0 * SR)
    s["chest_hum"] = norm(sum(tone(f * (1 + 0.003 * np.sin(t(2.0) * 6)), 2.0) for f in (440, 554, 659)) * 0.3) * 0.4
    n = int(0.7 * SR)
    s["crate_break"] = norm(lp_fast(noise(n), 1800) * env(n, 0.001, 0.25) + tone(np.linspace(160, 60, n), 0.7) * env(n, 0.001, 0.2))
    for i in range(4):
        n = int(0.16 * SR)
        s[f"step{i}"] = norm(lp_fast(noise(n), 500 + i * 120) * env(n, 0.002, 0.05)) * 0.5
    n = int(0.25 * SR)
    s["jump"] = norm(lp_fast(noise(n), 900) * env(n, 0.005, 0.08)) * 0.4
    s["land"] = norm(lp_fast(noise(int(0.3 * SR)), 300) * env(int(0.3 * SR), 0.001, 0.1) +
                     tone(np.linspace(120, 50, int(0.3 * SR)), 0.3) * env(int(0.3 * SR), 0.001, 0.08)) * 0.8
    n = int(0.8 * SR)
    s["glider_deploy"] = norm(hp_fast(noise(n), 400) * env(n, 0.005, 0.25) * np.linspace(1, 0.3, n) +
                              click(0.05, 0.8, 1200, 1.0))
    n = int(4.0 * SR)
    wind = lp_fast(noise(n), 700) * (0.6 + 0.4 * np.sin(t(4.0) * 2 * np.pi * 0.5))
    s["wind_loop"] = norm(wind) * 0.6
    hum = sum(tone(f, 4.0, "saw") for f in (55, 55.5, 110.3)) + lp_fast(noise(n), 200) * 0.6
    s["ship_loop"] = norm(lp_fast(hum, 800)) * 0.6
    storm = lp_fast(noise(n), 300) * 0.8 + sum(tone(f * (1 + 0.01 * np.sin(t(4.0) * 2)), 4.0, "saw") * 0.12 for f in (73, 110, 146))
    s["storm_loop"] = norm(lp_fast(storm, 1200)) * 0.7
    n = int(1.0 * SR)
    s["heal_loop"] = norm(sum(tone(f, 1.0) * (0.5 + 0.5 * np.sin(t(1.0) * 2 * np.pi * 4)) for f in (660, 990))) * 0.35
    n = int(0.7 * SR)
    s["heal_done"] = norm(sum(tone(f, 0.7) * env(n, 0.005 + i * 0.06, 0.3) for i, f in enumerate((660, 880, 1320)))) * 0.7
    n = int(0.6 * SR)
    s["shield_done"] = norm(sum(tone(f, 0.6, "tri") * env(n, 0.005 + i * 0.05, 0.3) for i, f in enumerate((523, 784, 1046, 1568)))) * 0.7
    n = int(0.06 * SR)
    s["ui_click"] = norm(tone(1400, 0.06, "tri") * env(n, 0.001, 0.015)) * 0.5
    n = int(0.05 * SR)
    s["ui_hover"] = norm(tone(2200, 0.05) * env(n, 0.001, 0.01)) * 0.25
    n = int(0.9 * SR)
    s["ui_purchase"] = norm(sum(tone(f, 0.9, "tri") * env(n, 0.005 + i * 0.07, 0.4) for i, f in enumerate((784, 988, 1175, 1568))) +
                            hp_fast(noise(n), 5000) * env(n, 0.001, 0.2) * 0.15)
    n = int(0.3 * SR)
    s["ui_error"] = norm(tone(180, 0.3, "square") * env(n, 0.002, 0.15)) * 0.5
    n = int(0.45 * SR)
    s["notify"] = norm(tone(988, 0.45) * env(n, 0.002, 0.15) + tone(1319, 0.45) * env(n, 0.12, 0.2)) * 0.6
    n = int(0.35 * SR)
    s["ui_swoosh"] = norm(hp_fast(noise(n), 1200) * np.sin(np.linspace(0, np.pi, n)) ** 3) * 0.35
    n = int(2.5 * SR)
    s["victory"] = norm(sum(tone(f, 2.5, "saw") * env(n, 0.01 + i * 0.12, 1.2) * 0.4 for i, f in enumerate((392, 523, 659, 784, 1046))))
    s["victory"] = norm(lp_fast(s["victory"], 3500))
    n = int(2.0 * SR)
    s["defeat"] = norm(lp_fast(sum(tone(f, 2.0, "saw") * env(n, 0.02 + i * 0.25, 1.0) for i, f in enumerate((392, 349, 311, 262))), 1500))
    n = int(1.2 * SR)
    s["level_up"] = norm(sum(tone(f, 1.2, "tri") * env(n, 0.005 + i * 0.08, 0.5) for i, f in enumerate((523, 659, 784, 1046, 1319))))
    for name, data in s.items():
        write(SFX / f"{name}.wav", data)
    return len(s)


# ----------------------------------------------------------------- music
MSR = 32000


def note_hz(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def synth_track(bpm, bars, chords, bass_pat, lead, drums, sr=MSR, swing=0.0, pad_level=0.22):
    beat = 60.0 / bpm
    total = int(bars * 4 * beat * sr)
    out = np.zeros(total)

    def add(start, sig):
        i = int(start * sr)
        j = min(total, i + len(sig))
        if i < total:
            out[i:j] += sig[: j - i]

    def tt(sec):
        return np.arange(int(sec * sr)) / sr

    def env_m(n, a, d):
        x = np.arange(n) / sr
        return np.clip(x / a, 0, 1) * np.exp(-x / d)

    for bar in range(bars):
        chord = chords[bar % len(chords)]
        t0 = bar * 4 * beat
        # pad
        dur = 4 * beat
        n = int(dur * sr)
        pad = sum(np.sin(2 * np.pi * note_hz(m) * tt(dur) * (1 + 0.002 * k)) for k, m in enumerate(chord))
        pad *= np.clip(np.arange(n) / (0.3 * sr), 0, 1) * np.clip((n - np.arange(n)) / (0.3 * sr), 0, 1)
        add(t0, pad * pad_level / len(chord))
        # bass
        for step, semis in enumerate(bass_pat):
            if semis is None:
                continue
            st = t0 + step * beat / 2
            d = beat / 2 * 0.9
            n = int(d * sr)
            f = note_hz(chord[0] - 12 + semis)
            sig = (((f * tt(d)) % 1) * 2 - 1)
            sig = lp_fast(sig, 600, sr) * env_m(n, 0.005, d * 0.8)
            add(st, sig * 0.35)
        # arpeggio lead
        for step in range(8):
            if lead[(bar * 8 + step) % len(lead)] is None:
                continue
            idx = lead[(bar * 8 + step) % len(lead)]
            m = chord[idx % len(chord)] + 12 * (1 + idx // len(chord))
            st = t0 + step * beat / 2 + (swing * beat / 2 if step % 2 else 0)
            d = beat / 2
            n = int(d * sr)
            sig = np.sign(np.sin(2 * np.pi * note_hz(m) * tt(d))) * 0.5 + np.sin(2 * np.pi * note_hz(m) * 2 * tt(d)) * 0.3
            add(st, lp_fast(sig, 2500, sr) * env_m(n, 0.003, d * 0.5) * 0.12)
        # drums
        for step in range(16):
            st = t0 + step * beat / 4
            hit = drums[step % len(drums)]
            if "k" in hit:
                d = 0.25
                n = int(d * sr)
                f = np.linspace(140, 45, n)
                add(st, np.sin(2 * np.pi * np.cumsum(f) / sr) * env_m(n, 0.001, 0.12) * 0.7)
            if "s" in hit:
                d = 0.2
                n = int(d * sr)
                add(st, (hp_fast(rng.uniform(-1, 1, n), 1500, sr) * 0.6 + np.sin(2 * np.pi * 190 * tt(d)) * 0.3) * env_m(n, 0.001, 0.06) * 0.45)
            if "h" in hit:
                d = 0.05
                n = int(d * sr)
                add(st, hp_fast(rng.uniform(-1, 1, n), 7000, sr) * env_m(n, 0.0005, 0.015) * 0.18)
    return norm(out, 0.8)


def build_music():
    lobby = synth_track(112, 16, [[57, 60, 64, 67], [53, 57, 60, 64], [48, 52, 55, 59], [55, 59, 62, 65]],
                        [0, None, 0, 12, None, 0, 7, None],
                        [0, 2, 4, 2, 1, 3, 4, 3, 0, 2, 4, 5, 4, 2, 1, None],
                        ["k", "h", "h", "h", "s", "h", "k", "h", "k", "h", "h", "h", "s", "h", "h", "hk"], swing=0.08)
    battle = synth_track(128, 16, [[50, 53, 57, 60], [46, 50, 53, 57], [48, 52, 55, 58], [45, 49, 52, 55]],
                         [0, 0, 12, 0, 0, 7, 0, 10],
                         [0, None, 2, None, 3, None, 2, 1, None, 0, None, 2, 4, None, 3, None],
                         ["k", "h", "h", "k", "s", "h", "k", "h", "k", "h", "kh", "h", "s", "h", "h", "h"], pad_level=0.15)
    results = synth_track(96, 8, [[60, 64, 67, 71], [57, 60, 64, 67], [53, 57, 60, 64], [55, 59, 62, 67]],
                          [0, None, None, None, 7, None, None, None],
                          [0, 1, 2, 3, 2, 1, None, None], ["k", "h", "h", "h", "s", "h", "h", "h"] * 2, pad_level=0.3)
    tracks = {"lobby_theme": lobby, "battle_theme": battle, "results_theme": results}
    ff = shutil.which("ffmpeg")
    for name, data in tracks.items():
        wav = MUSIC / f"{name}.wav"
        write(wav, data, MSR)
        if ff:
            subprocess.run([ff, "-loglevel", "error", "-y", "-i", str(wav), "-c:a", "libvorbis", "-q:a", "4",
                            str(MUSIC / f"{name}.ogg")], check=True)
            wav.unlink()
    return len(tracks)


if __name__ == "__main__":
    which = sys.argv[1:] or ["sfx", "music"]
    if "sfx" in which:
        print("sfx:", build_sfx())
    if "music" in which:
        print("music:", build_music())
