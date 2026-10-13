"""Generate clearly-labeled PLACEHOLDER media so the edit pipeline can be tested
before the real Spider-Man: Brand New Day footage and licensed music arrive.

Everything here is synthesized locally (no third-party content):
  placeholders/opening.mp4, placeholders/clip01..06.mp4  - 1920x1080 @ 24 fps
  placeholders/placeholder_beat.wav                       - 140 BPM phonk-style beat
  placeholder_config.json                                 - config pointing at them
"""
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "placeholders"
SR = 44100
BPM = 140.0
BUILD_BARS = 8          # drop lands at bar 9 -> 8 * 4 beats
TOTAL_BARS = 22
FONT = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"

CLIPS = [
    ("opening", "OPENING SCENE", "0x0b1a3a", "0x7a0a12", 14.0),
    ("clip01", "MONTAGE CLIP 01", "0xc0101c", "0x101a60", 7.0),
    ("clip02", "MONTAGE CLIP 02", "0x0f6aa8", "0x050505", 7.0),
    ("clip03", "MONTAGE CLIP 03", "0xd9480f", "0x2b0a3d", 7.0),
    ("clip04", "MONTAGE CLIP 04", "0x1b998b", "0x200508", 7.0),
    ("clip05", "MONTAGE CLIP 05", "0x8e0e8e", "0x0a2a12", 7.0),
    ("clip06", "MONTAGE CLIP 06", "0xe8c547", "0x15151f", 7.0),
]


def make_clip(name, label, c0, c1, dur):
    dst = OUT / f"{name}.mp4"
    vf = (
        f"drawgrid=w=160:h=160:t=2:c=white@0.12,"
        # moving "subject" so zooms / shake / motion blur are visible
        f"drawbox=x='860+520*sin(2*PI*t/2.7)':y='440+300*sin(2*PI*t/1.9)':w=200:h=200:c=white@0.85:t=fill,"
        f"drawtext=fontfile={FONT}:text='PLACEHOLDER':fontsize=40:fontcolor=white@0.8:"
        f"x=(w-tw)/2:y=h/2-110,"
        f"drawtext=fontfile={FONT}:text='{label}':fontsize=58:fontcolor=white:"
        f"borderw=4:bordercolor=black@0.6:x=(w-tw)/2:y=h/2-50,"
        f"drawtext=fontfile={FONT}:text='%{{pts\\:hms}}':fontsize=44:fontcolor=white@0.8:"
        f"x=(w-tw)/2:y=h/2+40"
    )
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i",
        f"gradients=s=1920x1080:r=24:c0={c0}:c1={c1}:speed=0.03:d={dur}",
        "-vf", vf, "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(dst),
    ], check=True)


def env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(t / max(attack, 1e-4), 1.0) * np.exp(-t / decay)


def synth_beat():
    beat = 60.0 / BPM
    total = TOTAL_BARS * 4 * beat
    n = int(total * SR) + SR
    mix = np.zeros(n)
    rng = np.random.default_rng(7)
    drop_t = BUILD_BARS * 4 * beat

    def add(sig, t, gain=1.0):
        i = int(t * SR)
        j = min(n, i + len(sig))
        mix[i:j] += gain * sig[: j - i]

    def tone(freq, dur, attack=0.002, decay=0.15, shape="sq"):
        m = int(dur * SR)
        t = np.arange(m) / SR
        ph = 2 * np.pi * freq * t
        s = np.sign(np.sin(ph)) * 0.5 + np.sin(ph) * 0.5 if shape == "sq" else np.sin(ph)
        return s * env(m, attack, decay)

    def cowbell(freq, dur=0.22):
        return 0.6 * tone(freq, dur, decay=0.09) + 0.4 * tone(freq * 1.48, dur, decay=0.07)

    def kick808(dur=0.9):
        m = int(dur * SR)
        t = np.arange(m) / SR
        f = 45 + 110 * np.exp(-t * 28)
        s = np.sin(2 * np.pi * np.cumsum(f) / SR)
        return np.tanh(2.2 * s * np.exp(-t / 0.45))

    def hat(dur=0.05):
        m = int(dur * SR)
        return rng.standard_normal(m) * env(m, 0.0005, 0.012) * 0.5

    def clap(dur=0.2):
        m = int(dur * SR)
        return rng.standard_normal(m) * env(m, 0.001, 0.05) * 0.9

    melody = [0, 3, 7, 3, 10, 7, 3, 0, 0, 3, 7, 12, 10, 7, 5, 3]
    root = 466.16  # Bb4

    for b in range(int(TOTAL_BARS * 4)):
        t0 = b * beat
        dropped = t0 >= drop_t
        # cowbell melody on 8ths, quieter in the build
        for k in range(2):
            step = (b * 2 + k) % len(melody)
            f = root * 2 ** (melody[step] / 12)
            add(cowbell(f), t0 + k * beat / 2, 0.42 if dropped else 0.22)
        # hats on 16ths
        for k in range(4):
            add(hat(), t0 + k * beat / 4, 0.35 if dropped else 0.18)
        if dropped:
            if b % 4 in (0, 2):
                add(kick808(), t0, 0.95)
            if b % 4 == 1:
                add(kick808(0.5), t0 + beat / 2, 0.8)
            if b % 2 == 1:
                add(clap(), t0, 0.7)
        elif b >= (BUILD_BARS - 2) * 4 and b < BUILD_BARS * 4 - 1:
            # snare roll accelerating into the drop
            subdiv = 2 if b < (BUILD_BARS - 1) * 4 else 4
            for k in range(subdiv):
                add(clap(0.1), t0 + k * beat / subdiv, 0.25 + 0.4 * (b - (BUILD_BARS - 2) * 4) / 8)

    # silence gap of one beat right before the drop (classic phonk tension)
    gap0, gap1 = int((drop_t - beat) * SR), int(drop_t * SR)
    mix[gap0:gap1] *= 0.05

    mix = np.tanh(mix * 0.9)
    mix /= np.max(np.abs(mix)) + 1e-9
    stereo = np.stack([mix, mix], axis=1) * 0.89
    pcm = (stereo * 32767).astype(np.int16)
    with wave.open(str(OUT / "placeholder_beat.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return drop_t


def main():
    OUT.mkdir(exist_ok=True)
    for c in CLIPS:
        make_clip(*c)
    drop_t = synth_beat()
    cfg = json.loads((ROOT / "edit_config.json").read_text())
    cfg["project_name"] = "PREVIEW_PLACEHOLDER_Nexo_SpiderMan_Edit"
    cfg["music"]["file"] = "placeholders/placeholder_beat.wav"
    cfg["opening"]["file"] = "placeholders/opening.mp4"
    for i, clip in enumerate(cfg["montage_clips"], start=1):
        clip["file"] = f"placeholders/clip{i:02d}.mp4"
    (ROOT / "placeholder_config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"placeholders written; synthesized drop at {drop_t:.3f}s (140 BPM)")


if __name__ == "__main__":
    main()
