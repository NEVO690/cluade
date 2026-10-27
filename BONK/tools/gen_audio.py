"""Synthesises every BONK! sound effect and the two music loops (standard library only).

    python tools/gen_audio.py        -> assets/audio/*.wav
"""

import array
import math
import os
import random
import wave

RATE = 22050
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "audio")


def write(name, samples):
    os.makedirs(OUT, exist_ok=True)
    peak = max(1e-6, max(abs(s) for s in samples))
    k = 0.9 / peak if peak > 0.9 else 1.0
    data = array.array("h", (int(max(-1.0, min(1.0, s * k)) * 32767) for s in samples))
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


def env(t, dur, attack=0.005, release=None):
    release = dur * 0.6 if release is None else release
    if t < attack:
        return t / attack
    if t > dur - release:
        return max(0.0, (dur - t) / release)
    return 1.0


def tone(freq_fn, dur, wave_fn=math.sin, vol=0.6, attack=0.005, release=None):
    out = []
    phase = 0.0
    n = int(dur * RATE)
    for i in range(n):
        t = i / RATE
        phase += 2 * math.pi * freq_fn(t) / RATE
        out.append(wave_fn(phase) * vol * env(t, dur, attack, release))
    return out


def square(p):
    return 0.6 if math.sin(p) >= 0 else -0.6


def tri(p):
    return 2 / math.pi * math.asin(math.sin(p))


def noise(dur, vol=0.5, lp=0.2, seed=1):
    rng = random.Random(seed)
    out, y = [], 0.0
    n = int(dur * RATE)
    for i in range(n):
        y += (rng.uniform(-1, 1) - y) * lp
        out.append(y * vol * env(i / RATE, dur, 0.002))
    return out


def mixdown(*tracks):
    n = max(len(t) for t in tracks)
    out = [0.0] * n
    for tr in tracks:
        for i, s in enumerate(tr):
            out[i] += s
    return out


def seq(*parts):
    out = []
    for p in parts:
        out += p
    return out


def silence(d):
    return [0.0] * int(d * RATE)


def note(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def make_sfx():
    write("jump", tone(lambda t: 320 + 900 * t / 0.18, 0.18, square, 0.35))
    write("land", mixdown(noise(0.12, 0.6, 0.08), tone(lambda t: 120 - 200 * t, 0.12, math.sin, 0.6)))
    write("bonk", mixdown(tone(lambda t: 900 * math.exp(-t * 18) + 180, 0.28, tri, 0.8),
                          tone(lambda t: 1300 * math.exp(-t * 25) + 300, 0.18, math.sin, 0.4)))
    write("hit", mixdown(noise(0.25, 0.8, 0.35, 3), tone(lambda t: 160 - 260 * t, 0.25, square, 0.4)))
    write("fall", tone(lambda t: 900 - 2600 * t, 0.32, tri, 0.5))
    write("splash", mixdown(noise(0.5, 0.7, 0.15, 7), tone(lambda t: 260 - 300 * t, 0.4, math.sin, 0.3)))
    write("beep", tone(lambda t: 660, 0.16, square, 0.35))
    write("go", seq(tone(lambda t: 990, 0.12, square, 0.35), tone(lambda t: 1320, 0.32, square, 0.4)))
    write("checkpoint", seq(tone(lambda t: note(76), 0.08, tri, 0.5), tone(lambda t: note(83), 0.18, tri, 0.5)))
    write("finish", seq(*[tone(lambda t, n=n: note(n), 0.1, square, 0.35) for n in (72, 76, 79, 84)],
                        tone(lambda t: note(88), 0.35, square, 0.4)))
    write("eliminated", seq(tone(lambda t: note(67), 0.18, tri, 0.5), tone(lambda t: note(63), 0.18, tri, 0.5),
                            tone(lambda t: note(58) * (1 - 0.06 * t), 0.5, tri, 0.5)))
    write("victory", seq(*[tone(lambda t, n=n: note(n), d, square, 0.35)
                           for n, d in ((72, 0.12), (72, 0.12), (72, 0.12), (76, 0.3), (74, 0.12), (77, 0.12),
                                        (81, 0.5))]))
    write("click", tone(lambda t: 1500, 0.04, square, 0.25, release=0.03))
    write("hover", tone(lambda t: 2200, 0.025, math.sin, 0.15, release=0.02))
    write("coin", seq(tone(lambda t: note(88), 0.06, square, 0.3), tone(lambda t: note(95), 0.22, square, 0.3)))
    write("error", tone(lambda t: 180, 0.22, square, 0.35))
    write("bounce", tone(lambda t: 250 + 1400 * t / 0.3, 0.3, tri, 0.5))


def make_music(name, bpm, chords, melody_seed, length_bars=8):
    beat = 60.0 / bpm
    total = int(length_bars * 4 * beat * RATE)
    out = [0.0] * total
    rng = random.Random(melody_seed)

    def add(start, samples):
        i0 = int(start * RATE)
        for i, s in enumerate(samples):
            if i0 + i < total:
                out[i0 + i] += s

    for bar in range(length_bars):
        root = chords[bar % len(chords)]
        t0 = bar * 4 * beat
        for b in range(4):  # bass on every beat, octave jump on off-beats
            add(t0 + b * beat, tone(lambda t, n=root - 24: note(n), beat * 0.45, tri, 0.35, release=0.1))
            add(t0 + (b + 0.5) * beat, tone(lambda t, n=root - 12: note(n), beat * 0.3, tri, 0.25, release=0.08))
            add(t0 + b * beat, noise(0.05, 0.35 if b % 2 else 0.5, 0.6, bar * 4 + b))  # hats / kick
        scale = [0, 2, 4, 7, 9, 12]
        for step in range(8):
            if rng.random() < 0.75:
                n = root + rng.choice(scale)
                add(t0 + step * beat / 2, tone(lambda t, n=n: note(n), beat * 0.42, square, 0.16, release=0.12))
    write(name, out)


if __name__ == "__main__":
    make_sfx()
    make_music("music_menu", 112, [60, 65, 57, 62], 4)
    make_music("music_race", 138, [62, 62, 67, 69], 9)
    print("audio written to", os.path.abspath(OUT))
