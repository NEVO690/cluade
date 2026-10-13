"""Beat grid + beat-drop detection with numpy only.

  python3 tools/beats.py music/track.mp3

Tempo comes from autocorrelation of a spectral-flux onset envelope, the beat
phase from the grid offset that best lines up with onsets, and the drop is the
beat where low-end (kick/808) energy jumps hardest relative to what came before.
"""
import subprocess
import sys

import numpy as np

SR = 22050
HOP = 256
WIN = 2048


def load_mono(path, sr=SR):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
         "-f", "f32le", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def stft_mag(y, win_len):
    """Centered frames: row i describes the audio around i * HOP / SR."""
    y = np.pad(y, win_len // 2)
    win = np.hanning(win_len).astype(np.float32)
    n = 1 + max(0, (len(y) - win_len) // HOP)
    idx = np.arange(win_len)[None, :] + HOP * np.arange(n)[:, None]
    return np.abs(np.fft.rfft(y[idx] * win, axis=1))


def analyze(path, bpm_hint=None, drop_hint=None):
    y = load_mono(path)
    dur = len(y) / SR
    fps = SR / HOP
    mag = stft_mag(y, WIN)
    freqs = np.fft.rfftfreq(WIN, 1 / SR)

    # short window for onset timing precision
    logmag = np.log1p(100 * stft_mag(y, 512))
    flux = np.maximum(0, np.diff(logmag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, mode="same")   # local mean removal
    onset = np.maximum(flux, 0)
    onset /= onset.max() + 1e-9

    # ---- tempo ---------------------------------------------------------
    if bpm_hint:
        bpm = float(bpm_hint)
    else:
        ac = np.correlate(onset, onset, mode="full")[len(onset) - 1:]
        lags = np.arange(len(ac))
        with np.errstate(divide="ignore"):
            bpms = 60 * fps / lags
        valid = (bpms >= 70) & (bpms <= 190)
        prior = np.exp(-0.5 * (np.log2(np.where(valid, bpms, 1) / 130.0) / 0.9) ** 2)
        score = np.where(valid, ac * prior, -np.inf)
        lag = int(np.argmax(score))
        if 1 <= lag < len(ac) - 1:     # parabolic refinement
            a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
            denom = a - 2 * b + c
            lag = lag + (0.5 * (a - c) / denom if denom else 0)
        bpm = 60 * fps / lag
    period = 60 * fps / bpm   # frames per beat

    # ---- phase ---------------------------------------------------------
    best, best_off = -1, 0.0
    for off in np.arange(0, period, 0.25):
        pos = np.arange(off, len(onset) - 1, period)
        val = np.interp(pos, np.arange(len(onset)), onset).sum()
        if val > best:
            best, best_off = val, off
    grid = np.arange(best_off, len(onset), period)
    # refine tempo + phase: least-squares fit of the grid to nearby onset peaks
    win = int(0.06 * fps)
    ks, ts = [], []
    for k, g in enumerate(grid):
        lo, hi = max(0, int(g) - win), min(len(onset), int(g) + win + 1)
        if hi - lo < 3:
            continue
        j = lo + int(np.argmax(onset[lo:hi]))
        if onset[j] > 0.2:
            ks.append(k)
            ts.append(j)
    if len(ks) >= 8 and not bpm_hint:
        slope, icpt = np.polyfit(ks, ts, 1)
        period, best_off = slope, icpt % slope
        bpm = 60 * fps / period
        grid = np.arange(best_off, len(onset), period)
    beat_times = grid / fps

    # ---- drop ----------------------------------------------------------
    low = mag[:, (freqs >= 20) & (freqs <= 160)]
    bass = (low ** 2).sum(axis=1)
    full = (mag ** 2).sum(axis=1)
    k = max(1, int(0.04 * fps))   # light smoothing: keep onsets sharp
    bass = np.convolve(bass, np.ones(k) / k, mode="same")
    full = np.convolve(full, np.ones(k) / k, mode="same")
    eps = 1e-6 * (bass.mean() + 1e-12)
    feps = 1e-6 * (full.mean() + 1e-12)

    def ratio(sig, i, span, e):
        pre = sig[max(0, i - span):i].mean() if i > 0 else e
        return np.log((sig[i:i + span].mean() + e) / (pre + e))

    def drop_score(t):
        i = int(t * fps)
        long_, short = int(2.0 * fps), int(0.3 * fps)
        return (ratio(bass, i, long_, eps) + ratio(bass, i, short, eps)
                + 0.5 * ratio(full, i, long_, feps) + 0.5 * ratio(full, i, short, feps)
                + 0.3 * np.log(bass[i:i + long_].mean() / (bass.mean() + 1e-12) + 1e-6))

    if drop_hint is not None:
        drop = float(beat_times[np.argmin(np.abs(beat_times - drop_hint))])
        drop = drop if abs(drop - drop_hint) < 0.08 else float(drop_hint)
    else:
        cands = [t for t in beat_times if 4.0 <= t <= dur - 14.0]
        if not cands:
            cands = [t for t in beat_times if 1.0 <= t <= dur - 4.0]
        drop = float(max(cands, key=drop_score))

    return {"bpm": float(bpm), "beat_period": 60.0 / bpm, "beats": beat_times.tolist(),
            "drop": drop, "duration": dur}


if __name__ == "__main__":
    r = analyze(sys.argv[1])
    print(f"duration {r['duration']:.2f}s  bpm {r['bpm']:.2f}  drop {r['drop']:.3f}s  "
          f"first beats {[round(b, 3) for b in r['beats'][:4]]}")
