"""Generates all of IL Brawl's original sound effects and music with pure Python (no dependencies).

Run:  python tools/generate_audio.py
Output: assets/sounds/*.wav and assets/music/*.wav (22.05 kHz, 16-bit mono).
"""
import array
import math
import os
import random
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 22050
rng = random.Random(7)


def osc(kind, phase):
    p = phase % 1.0
    if kind == "sine":
        return math.sin(2 * math.pi * p)
    if kind == "square":
        return 1.0 if p < 0.5 else -1.0
    if kind == "pulse":
        return 1.0 if p < 0.25 else -1.0
    if kind == "saw":
        return 2 * p - 1
    if kind == "tri":
        return 4 * abs(p - 0.5) - 1
    return rng.uniform(-1, 1)


def tone(dur, f0, f1=None, kind="square", vol=0.5, attack=0.005, release=None, vib=0.0, curve=1.0):
    n = int(SR * dur)
    f1 = f0 if f1 is None else f1
    release = dur * 0.6 if release is None else release
    out = [0.0] * n
    phase = 0.0
    for i in range(n):
        t = i / SR
        k = (t / dur) ** curve
        f = f0 + (f1 - f0) * k
        if vib:
            f *= 1 + vib * math.sin(2 * math.pi * 6 * t)
        phase += f / SR
        env = min(1.0, t / attack) if attack > 0 else 1.0
        if t > dur - release:
            env *= max(0.0, (dur - t) / release)
        out[i] = osc(kind, phase) * vol * env
    return out


def noise(dur, vol=0.5, decay=8.0, lp=0.5):
    n = int(SR * dur)
    out = [0.0] * n
    y = 0.0
    for i in range(n):
        t = i / SR
        y += lp * (rng.uniform(-1, 1) - y)
        out[i] = y * vol * math.exp(-decay * t)
    return out


def mix(*tracks, offsets=None):
    offsets = offsets or [0] * len(tracks)
    n = max(int(o * SR) + len(t) for t, o in zip(tracks, offsets))
    out = [0.0] * n
    for t, o in zip(tracks, offsets):
        s = int(o * SR)
        for i, v in enumerate(t):
            out[s + i] += v
    return out


def seq(notes, kind="square", vol=0.4, gap=0.0):
    """notes: list of (freq, dur)."""
    out = []
    for f, d in notes:
        out += tone(d, f, kind=kind, vol=vol, release=d * 0.5) if f else [0.0] * int(SR * d)
        out += [0.0] * int(SR * gap)
    return out


def save(path, data, gain=1.0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    peak = max(1e-6, max(abs(v) for v in data))
    scale = 0.9 / peak * gain
    a = array.array("h", (int(max(-1, min(1, v * scale)) * 32000) for v in data))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(a.tobytes())


def note(n):
    """MIDI note number to Hz."""
    return 440.0 * 2 ** ((n - 69) / 12)


def sfx():
    S = {}
    S["click"] = tone(0.05, 900, 1300, "square", 0.3, release=0.03)
    S["tab"] = tone(0.07, 600, 900, "tri", 0.4)
    S["deny"] = mix(tone(0.12, 220, 160, "square", 0.3), tone(0.12, 233, 170, "square", 0.25), offsets=[0, 0.1])
    S["buy"] = seq([(note(76), 0.06), (note(81), 0.06), (note(88), 0.14)], "square", 0.3)
    S["reward"] = seq([(note(72), 0.07), (note(76), 0.07), (note(79), 0.07), (note(84), 0.2)], "pulse", 0.3)
    S["levelup"] = seq([(note(67), 0.08), (note(72), 0.08), (note(76), 0.08), (note(79), 0.08), (note(84), 0.3)], "square", 0.3)
    S["unlock"] = mix(seq([(note(72), 0.1), (note(79), 0.1), (note(84), 0.1), (note(91), 0.35)], "tri", 0.45),
                      noise(0.6, 0.15, 4, 0.9))
    S["shoot"] = mix(tone(0.09, 900, 300, "square", 0.3, curve=0.5), noise(0.08, 0.3, 30, 0.8))
    S["shoot_heavy"] = mix(tone(0.16, 300, 80, "square", 0.4, curve=0.4), noise(0.2, 0.6, 18, 0.5))
    S["laser"] = tone(0.16, 1800, 400, "saw", 0.3, curve=0.35)
    S["lob"] = tone(0.22, 300, 700, "tri", 0.45)
    S["melee"] = mix(noise(0.14, 0.6, 20, 0.95), tone(0.1, 500, 200, "tri", 0.3))
    S["flame"] = noise(0.22, 0.5, 9, 0.35)
    S["hit"] = mix(noise(0.07, 0.6, 40, 0.7), tone(0.06, 200, 120, "square", 0.3))
    S["hurt"] = mix(tone(0.14, 300, 150, "square", 0.35), noise(0.1, 0.3, 30, 0.6))
    S["explosion"] = mix(noise(0.7, 0.9, 5, 0.25), tone(0.4, 120, 40, "sine", 0.6))
    S["super"] = mix(tone(0.4, 200, 1200, "saw", 0.3, curve=0.6), tone(0.4, 300, 1500, "square", 0.15, curve=0.6))
    S["super_ready"] = seq([(note(84), 0.06), (note(88), 0.06), (note(91), 0.06), (note(96), 0.16)], "pulse", 0.25)
    S["heal"] = seq([(note(79), 0.07), (note(84), 0.1)], "sine", 0.4)
    S["death"] = mix(tone(0.5, 500, 60, "square", 0.35, curve=0.5), noise(0.4, 0.4, 7, 0.4))
    S["gem"] = seq([(note(88), 0.05), (note(95), 0.12)], "tri", 0.45)
    S["goal"] = mix(seq([(note(72), 0.1), (note(76), 0.1), (note(79), 0.1), (note(84), 0.1), (note(88), 0.4)], "square", 0.3),
                    noise(0.9, 0.2, 3, 0.9))
    S["victory"] = seq([(note(72), 0.12), (note(72), 0.12), (note(72), 0.12), (note(76), 0.3), (note(74), 0.12),
                        (note(77), 0.12), (note(79), 0.5)], "square", 0.3)
    S["defeat"] = seq([(note(67), 0.25), (note(66), 0.25), (note(65), 0.25), (note(64), 0.6)], "tri", 0.45)
    S["countdown"] = tone(0.12, note(76), kind="pulse", vol=0.3)
    S["go"] = mix(tone(0.4, note(84), kind="square", vol=0.3), tone(0.4, note(88), kind="square", vol=0.2))
    S["capture"] = seq([(note(76), 0.08), (note(83), 0.18)], "square", 0.3)
    S["dash"] = mix(noise(0.25, 0.5, 10, 0.6), tone(0.25, 200, 80, "saw", 0.3))
    S["shield"] = tone(0.35, 400, 900, "sine", 0.4, vib=0.05)
    S["whoosh"] = noise(0.2, 0.5, 12, 0.3)
    for k, v in S.items():
        save(os.path.join(ROOT, "assets", "sounds", k + ".wav"), v)
    return len(S)


def drum_track(bars, bpm, pattern_kick, pattern_snare, hats=True):
    beat = 60.0 / bpm
    step = beat / 4
    n = int(SR * bars * 4 * beat)
    out = [0.0] * n
    kick = tone(0.18, 140, 45, "sine", 0.9, release=0.15, curve=0.4)
    snare = mix(noise(0.18, 0.6, 18, 0.8), tone(0.1, 220, 180, "tri", 0.3))
    hat = noise(0.04, 0.25, 60, 0.95)
    for b in range(bars):
        for s in range(16):
            t = int(SR * (b * 4 * beat + s * step))
            if s in pattern_kick:
                for i, v in enumerate(kick):
                    if t + i < n:
                        out[t + i] += v
            if s in pattern_snare:
                for i, v in enumerate(snare):
                    if t + i < n:
                        out[t + i] += v
            if hats and s % 2 == 0:
                for i, v in enumerate(hat):
                    if t + i < n:
                        out[t + i] += v * (1.0 if s % 4 == 2 else 0.6)
    return out


def melodic(bars, bpm, chords, melody, bass_kind="tri", lead_kind="pulse", pad_kind="square"):
    beat = 60.0 / bpm
    n = int(SR * bars * 4 * beat)
    out = [0.0] * n

    def put(buf, start):
        s = int(start * SR)
        for i, v in enumerate(buf):
            if s + i < n:
                out[s + i] += v

    for b in range(bars):
        root, kind = chords[b % len(chords)]
        third = root + (4 if kind == "maj" else 3)
        fifth = root + 7
        # bass: root on 1 and 3, fifth on the off-beats
        for i, nn in enumerate([root, root, fifth, root]):
            put(tone(beat * 0.9, note(nn - 12), kind=bass_kind, vol=0.35, release=beat * 0.3), (b * 4 + i) * beat)
        # arpeggio pad
        arp = [root, third, fifth, third + 12, fifth, third, root + 12, fifth]
        for i, nn in enumerate(arp):
            put(tone(beat * 0.45, note(nn + 12), kind=pad_kind, vol=0.07, release=beat * 0.3), (b * 4 + i * 0.5) * beat)
    t = 0.0
    total = bars * 4
    i = 0
    while t < total:
        nn, d = melody[i % len(melody)]
        if nn:
            put(tone(beat * d * 0.95, note(nn), kind=lead_kind, vol=0.16, release=beat * d * 0.4, vib=0.004), t * beat)
        t += d
        i += 1
    return out


def music():
    # Menu theme: brooding and cinematic, A minor, 92 bpm
    bars = 16
    chords = [(57, "min"), (53, "maj"), (48, "maj"), (52, "min")]
    mel = [(69, 2), (72, 1), (71, 1), (69, 1.5), (67, 0.5), (64, 2), (None, 1), (65, 1), (64, 1), (62, 1),
           (64, 2), (None, 2)]
    m = melodic(bars, 92, chords, mel, bass_kind="saw", lead_kind="tri", pad_kind="saw")
    d = drum_track(bars, 92, {0, 10}, {8}, hats=False)
    save(os.path.join(ROOT, "assets", "music", "menu_theme.wav"), mix(m, [v * 0.55 for v in d]), 0.8)
    # Battle theme: tense and driving, D minor, 132 bpm
    chords = [(50, "min"), (46, "maj"), (48, "maj"), (45, "min")]
    mel = [(69, 0.5), (72, 0.5), (76, 0.5), (74, 0.5), (72, 0.5), (71, 0.5), (69, 1), (None, 0.5), (76, 0.5),
           (77, 0.5), (76, 0.5), (74, 0.5), (72, 0.5), (74, 1), (72, 0.5), (71, 0.5), (69, 1.5), (None, 0.5)]
    mel = [(n - 7 if n else None, d) for n, d in mel]
    m = melodic(bars, 132, chords, mel, bass_kind="saw", lead_kind="saw", pad_kind="pulse")
    d = drum_track(bars, 132, {0, 3, 8, 11}, {4, 12})
    save(os.path.join(ROOT, "assets", "music", "battle_theme.wav"), mix(m, [v * 0.7 for v in d]), 0.8)


if __name__ == "__main__":
    print("sfx:", sfx())
    music()
    print("music done")
