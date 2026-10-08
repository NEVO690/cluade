"""Procedural audio: every sound effect and every zone's music loop is
synthesised at start-up, so the game ships with zero copyrighted audio.

numpy is used when available (fast). Without numpy, sound effects are still
generated with pure Python and music is skipped.
"""
import array
import math
import random

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised only without numpy
    np = None

SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "pentatonic": [0, 2, 4, 7, 9, 12, 14],
}


def midi_freq(n):
    return 440.0 * 2 ** ((n - 69) / 12.0)


# ---------------------------------------------------------------------------
# Pure python fallback for sound effects
# ---------------------------------------------------------------------------
def _py_sfx(rate, parts):
    """parts: list of (start, dur, f0, f1, wave, vol, noise)."""
    total = max(s + d for s, d, *_ in parts)
    n = int(total * rate)
    buf = [0.0] * n
    rnd = random.Random(3)
    for start, dur, f0, f1, wave, vol, noise in parts:
        i0 = int(start * rate)
        cnt = int(dur * rate)
        phase = 0.0
        for i in range(cnt):
            t = i / max(1, cnt)
            f = f0 + (f1 - f0) * t
            phase += f / rate
            if noise:
                v = rnd.uniform(-1, 1)
            elif wave == "square":
                v = 1.0 if (phase % 1.0) < 0.5 else -1.0
            elif wave == "saw":
                v = 2.0 * (phase % 1.0) - 1.0
            else:
                v = math.sin(2 * math.pi * phase)
            env = min(1.0, i / (0.004 * rate + 1)) * (1.0 - t) ** 1.5
            j = i0 + i
            if j < n:
                buf[j] += v * vol * env
    return buf


class Synth:
    def __init__(self, rate=44100, channels=2):
        self.rate = rate
        self.channels = channels

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------
    def to_bytes(self, mono):
        """Float mono signal (-1..1) -> int16 interleaved bytes for the mixer."""
        if np is not None:
            sig = np.clip(np.asarray(mono, dtype=np.float32), -1.0, 1.0)
            pcm = (sig * 32000).astype(np.int16)
            if self.channels == 2:
                pcm = np.repeat(pcm, 2)
            return pcm.tobytes()
        arr = array.array("h")
        for v in mono:
            s = int(max(-1.0, min(1.0, v)) * 32000)
            arr.append(s)
            if self.channels == 2:
                arr.append(s)
        return arr.tobytes()

    def to_bytes_stereo(self, left, right):
        sig = np.stack([np.clip(left, -1, 1), np.clip(right, -1, 1)], axis=1)
        pcm = (sig * 32000).astype(np.int16)
        if self.channels == 1:
            pcm = pcm.mean(axis=1).astype(np.int16)
        return pcm.tobytes()

    # ------------------------------------------------------------------
    # numpy building blocks
    # ------------------------------------------------------------------
    def _t(self, dur):
        return np.arange(int(dur * self.rate), dtype=np.float32) / self.rate

    def osc(self, freq, dur, wave="sine", freq_end=None, duty=0.5):
        n = int(dur * self.rate)
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        if freq_end is None:
            f = np.full(n, freq, dtype=np.float32)
        else:
            f = np.geomspace(max(freq, 1), max(freq_end, 1), n).astype(np.float32)
        phase = np.cumsum(f) / self.rate
        frac = phase % 1.0
        if wave == "square":
            return np.where(frac < duty, 1.0, -1.0).astype(np.float32)
        if wave == "saw":
            return (2.0 * frac - 1.0).astype(np.float32)
        if wave == "triangle":
            return (4.0 * np.abs(frac - 0.5) - 1.0).astype(np.float32)
        return np.sin(2 * np.pi * phase).astype(np.float32)

    def noise(self, dur, seed=1):
        rng = np.random.default_rng(seed)
        return rng.uniform(-1, 1, int(dur * self.rate)).astype(np.float32)

    def env(self, n, attack=0.005, decay=None, curve=1.6):
        """Attack then a power-curve decay to zero across the remaining samples."""
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        a = max(1, int(attack * self.rate))
        e = np.ones(n, dtype=np.float32)
        a = min(a, n)
        e[:a] = np.linspace(0, 1, a)
        rest = n - a
        if rest > 0:
            e[a:] = np.linspace(1, 0, rest) ** curve
        return e

    def lowpass(self, sig, amount=4):
        if amount <= 1:
            return sig
        k = np.ones(amount, dtype=np.float32) / amount
        return np.convolve(sig, k, mode="same").astype(np.float32)

    @staticmethod
    def mix(*parts):
        n = max(len(p) for p in parts)
        out = np.zeros(n, dtype=np.float32)
        for p in parts:
            out[:len(p)] += p
        return out

    def seq(self, notes):
        """notes: list of (start, signal) -> mixed signal."""
        n = max(int(s * self.rate) + len(sig) for s, sig in notes)
        out = np.zeros(n, dtype=np.float32)
        for s, sig in notes:
            i = int(s * self.rate)
            out[i:i + len(sig)] += sig
        return out

    # ------------------------------------------------------------------
    # Sound effects
    # ------------------------------------------------------------------
    def make_sfx(self, name):
        if np is None:
            return self._py_fallback(name)
        if name == "jump":
            s = self.osc(260, 0.16, "square", 720, duty=0.3) * 0.35
            return s * self.env(len(s), 0.003, curve=1.2)
        if name == "land":
            s = self.osc(140, 0.09, "sine", 60) * 0.6 + self.lowpass(self.noise(0.09), 8) * 0.25
            return s * self.env(len(s), 0.002)
        if name == "coin":
            a = self.osc(1318, 0.05, "square", duty=0.25) * 0.22
            b = self.osc(1976, 0.2, "square", duty=0.25) * 0.22
            return self.seq([(0, a * self.env(len(a), 0.001, curve=0.5)), (0.045, b * self.env(len(b), 0.001))])
        if name == "gem":
            notes = [(i * 0.05, self.osc(midi_freq(84 + n), 0.18, "triangle") * 0.3) for i, n in enumerate([0, 4, 7, 12])]
            return self.seq([(s, x * self.env(len(x), 0.002)) for s, x in notes])
        if name == "token":
            notes = [(i * 0.06, self.osc(midi_freq(79 + n), 0.16, "sine") * 0.35) for i, n in enumerate([0, 5, 9])]
            return self.seq([(s, x * self.env(len(x), 0.002)) for s, x in notes])
        if name == "powerup":
            notes = [(i * 0.055, self.osc(midi_freq(64 + n), 0.14, "square", duty=0.4) * 0.2)
                     for i, n in enumerate([0, 4, 7, 12, 16, 19])]
            return self.seq([(s, x * self.env(len(x), 0.002, curve=1.0)) for s, x in notes])
        if name == "jet":
            n = self.lowpass(self.noise(0.9, 4), 6) * 0.45
            s = self.osc(90, 0.9, "saw", 240) * 0.15
            sig = n + s
            e = np.minimum(1, np.linspace(0, 4, len(sig))) * np.linspace(1, 0, len(sig)) ** 0.7
            return sig * e
        if name == "hit":
            n = self.lowpass(self.noise(0.5, 7), 3) * 0.7
            b = self.osc(160, 0.5, "sine", 40) * 0.8
            sig = n + b
            return sig * self.env(len(sig), 0.001, curve=2.2)
        if name == "stumble":
            n = self.lowpass(self.noise(0.22, 9), 10) * 0.6
            b = self.osc(110, 0.22, "square", 70, duty=0.5) * 0.25
            sig = n + b
            return sig * self.env(len(sig), 0.001, curve=1.8)
        if name == "slide":
            n = self.lowpass(self.noise(0.32, 11), 14) * 0.5
            return n * self.env(len(n), 0.03, curve=1.2)
        if name == "whoosh":
            n = self.lowpass(self.noise(0.14, 13), 6) * 0.28
            e = np.sin(np.linspace(0, np.pi, len(n)))
            return n * e
        if name in ("button", "click"):
            s = self.osc(880, 0.045, "square", 660, duty=0.3) * 0.2
            return s * self.env(len(s), 0.001)
        if name == "back":
            s = self.osc(520, 0.06, "square", 330, duty=0.3) * 0.2
            return s * self.env(len(s), 0.001)
        if name == "buy":
            a = self.osc(988, 0.08, "square", duty=0.25) * 0.2
            b = self.osc(1480, 0.3, "triangle") * 0.3
            return self.seq([(0, a * self.env(len(a), 0.001)), (0.07, b * self.env(len(b), 0.001))])
        if name == "error":
            s = self.osc(150, 0.25, "square", duty=0.5) * 0.2
            return s * self.env(len(s), 0.002, curve=0.8)
        if name == "game_over":
            notes = [(i * 0.18, self.osc(midi_freq(n), 0.35, "triangle") * 0.4) for i, n in enumerate([67, 63, 60, 55])]
            return self.seq([(s, x * self.env(len(x), 0.004, curve=1.3)) for s, x in notes])
        if name in ("unlock", "achievement", "mission", "level_up"):
            base = {"unlock": 72, "achievement": 76, "mission": 74, "level_up": 69}[name]
            seqn = [0, 4, 7, 12] if name != "mission" else [0, 7, 12]
            notes = [(i * 0.09, self.osc(midi_freq(base + n), 0.3 if i == len(seqn) - 1 else 0.14, "square", duty=0.35) * 0.18)
                     for i, n in enumerate(seqn)]
            return self.seq([(s, x * self.env(len(x), 0.003, curve=1.2)) for s, x in notes])
        if name == "shield_break":
            n = self.noise(0.4, 15)
            hp = n - self.lowpass(n, 6)
            sig = hp * 0.6 + self.osc(1800, 0.4, "sine", 600) * 0.2
            return sig * self.env(len(sig), 0.001, curve=2.0)
        if name == "board":
            s = self.osc(200, 0.35, "saw", 600) * 0.15 + self.lowpass(self.noise(0.35, 17), 5) * 0.2
            return s * self.env(len(s), 0.02, curve=1.0)
        if name == "countdown":
            s = self.osc(660, 0.12, "square", duty=0.4) * 0.2
            return s * self.env(len(s), 0.002, curve=0.7)
        if name == "go":
            s = self.osc(1320, 0.3, "square", duty=0.4) * 0.2
            return s * self.env(len(s), 0.002, curve=1.0)
        if name == "smash":
            n = self.lowpass(self.noise(0.35, 19), 2) * 0.6
            b = self.osc(220, 0.35, "square", 80) * 0.2
            sig = n + b
            return sig * self.env(len(sig), 0.001, curve=2.4)
        s = self.osc(440, 0.1) * 0.2
        return s * self.env(len(s))

    def _py_fallback(self, name):
        table = {
            "jump": [(0, 0.15, 260, 720, "square", 0.3, False)],
            "coin": [(0, 0.05, 1318, 1318, "square", 0.2, False), (0.045, 0.2, 1976, 1976, "square", 0.2, False)],
            "hit": [(0, 0.45, 0, 0, "", 0.6, True), (0, 0.45, 160, 40, "sine", 0.6, False)],
            "powerup": [(i * 0.06, 0.12, midi_freq(64 + n), midi_freq(64 + n), "square", 0.18, False)
                        for i, n in enumerate([0, 4, 7, 12])],
            "game_over": [(i * 0.18, 0.3, midi_freq(n), midi_freq(n), "sine", 0.35, False)
                          for i, n in enumerate([67, 63, 60, 55])],
        }
        parts = table.get(name, [(0, 0.06, 800, 600, "square", 0.18, False)])
        return _py_sfx(self.rate, parts)

    # ------------------------------------------------------------------
    # Music
    # ------------------------------------------------------------------
    def make_music(self, spec, seed=0, bars=8):
        """Return (left, right) float arrays for a seamless loop."""
        tempo = float(spec.get("tempo", 116))
        root = int(spec.get("root", 57))
        scale = SCALES.get(spec.get("scale", "major"), SCALES["major"])
        prog = spec.get("progression", [1, 5, 6, 4]) or [1, 5, 6, 4]
        style = spec.get("style", "pop")
        lead_wave = spec.get("lead", "square")
        rnd = random.Random(seed)

        beat = 60.0 / tempo
        bar = beat * 4
        total = bar * bars
        n = int(total * self.rate)
        left = np.zeros(n + self.rate, dtype=np.float32)
        right = np.zeros(n + self.rate, dtype=np.float32)

        def add(sig, start, pan=0.0, gain=1.0):
            i = int(start * self.rate)
            j = min(len(left), i + len(sig))
            seg = sig[:j - i] * gain
            left[i:j] += seg * (1 - max(0, pan))
            right[i:j] += seg * (1 + min(0, pan))

        def degree_note(deg, octave=0):
            deg -= 1
            o, d = divmod(deg, len(scale))
            return root + scale[d] + 12 * (o + octave)

        # --- drums -----------------------------------------------------
        kick = self.osc(150, 0.28, "sine", 45)
        kick *= self.env(len(kick), 0.001, curve=2.0)
        snare = self.lowpass(self.noise(0.2, 21), 2) * 0.6 + self.osc(190, 0.2, "triangle") * 0.3
        snare *= self.env(len(snare), 0.001, curve=2.5)
        hat_n = self.noise(0.05, 23)
        hat = (hat_n - self.lowpass(hat_n, 4)) * self.env(len(hat_n), 0.001, curve=3.0)

        drum_gain = {"pop": 0.55, "folk": 0.35, "industrial": 0.7, "sea": 0.3, "synthwave": 0.55,
                     "epic": 0.65, "chill": 0.3}.get(style, 0.5)
        for b in range(bars):
            t0 = b * bar
            for q in range(4):
                tq = t0 + q * beat
                if style in ("industrial", "epic", "synthwave", "pop") or q in (0, 2):
                    add(kick, tq, 0, drum_gain)
                if q in (1, 3):
                    add(snare, tq, 0.1, drum_gain * (0.8 if style != "sea" else 0.4))
                for e in range(2 if style != "industrial" else 4):
                    step = beat / (2 if style != "industrial" else 4)
                    add(hat, tq + e * step, -0.3, drum_gain * (0.35 if e % 2 else 0.22))

        # --- bass + pads ---------------------------------------------------
        for b in range(bars):
            deg = int(prog[b % len(prog)])
            t0 = b * bar
            bass_note = midi_freq(degree_note(deg, -2))
            pattern = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5] if style in ("synthwave", "industrial") else [0, 1.5, 2, 3]
            for p in pattern:
                dur = beat * (0.45 if len(pattern) == 8 else 0.9)
                w = "saw" if style in ("synthwave", "industrial", "epic") else "triangle"
                s = self.lowpass(self.osc(bass_note, dur, w), 6) * 0.32
                add(s * self.env(len(s), 0.004, curve=1.0), t0 + p * beat, 0)
            chord = [degree_note(deg + k, 0) for k in (0, 2, 4)]
            pad = np.zeros(int(bar * self.rate), dtype=np.float32)
            for note in chord:
                f = midi_freq(note)
                pad += self.osc(f, bar, "saw") * 0.05 + self.osc(f * 1.005, bar, "saw") * 0.05
            pad = self.lowpass(pad, 18 if style != "synthwave" else 10)
            e = np.minimum(1, np.linspace(0, 6, len(pad))) * np.minimum(1, np.linspace(6, 0, len(pad)))
            add(pad * e, t0, 0.3 * (1 if b % 2 else -1), 0.9 if style in ("sea", "chill") else 0.7)

        # --- lead melody ------------------------------------------------
        phrase = []
        for _ in range(2):
            bar_notes = []
            t = 0.0
            while t < 4:
                length = rnd.choice([0.5, 0.5, 1.0, 1.0, 1.5, 0.25 * 2])
                if t + length > 4:
                    length = 4 - t
                rest = rnd.random() < 0.2
                bar_notes.append((t, length, None if rest else rnd.randint(0, 7)))
                t += length
            phrase.append(bar_notes)
        lead_gain = 0.16 if lead_wave in ("square", "saw") else 0.22
        for b in range(bars):
            if b % 4 == 0 and style in ("sea", "chill"):
                continue
            deg = int(prog[b % len(prog)])
            for (t, length, step) in phrase[b % 2]:
                if step is None:
                    continue
                note = degree_note(deg + step, 1)
                s = self.osc(midi_freq(note), length * beat * 0.95, lead_wave, duty=0.35)
                if lead_wave == "saw":
                    s = self.lowpass(s, 5)
                s *= self.env(len(s), 0.01, curve=1.2)
                add(s, b * bar + t * beat, 0.15, lead_gain)
                # simple echo
                add(s, b * bar + t * beat + beat * 0.75, -0.4, lead_gain * 0.35)

        # wrap the tail (echo/decay) back to the start for a seamless loop
        tail_l = left[n:].copy()
        tail_r = right[n:].copy()
        left = left[:n]
        right = right[:n]
        left[:len(tail_l)] += tail_l
        right[:len(tail_r)] += tail_r
        peak = max(float(np.max(np.abs(left))), float(np.max(np.abs(right))), 1e-6)
        g = 0.85 / peak
        return np.tanh(left * g * 1.1) * 0.9, np.tanh(right * g * 1.1) * 0.9
