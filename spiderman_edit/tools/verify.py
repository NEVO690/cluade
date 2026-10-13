"""Verify a rendered edit against its timeline.

  python3 tools/verify.py output/<name>.mp4

Checks: format (1080x1920, fps, H.264/AAC), clean full decode, every planned cut
present in the picture at the planned frame, audio drop landing on the drop cut,
watermark visible in every sampled frame.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def sh(cmd, binary=False):
    r = subprocess.run(cmd, capture_output=True, text=not binary)
    return r


def main():
    video = Path(sys.argv[1])
    tl = json.loads(video.with_name(video.stem + "_timeline.json").read_text())
    F, W, H = tl["fps"], tl["width"], tl["height"]
    ok = True

    def check(cond, msg):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + msg)

    # ---- format ---------------------------------------------------------------
    j = json.loads(sh(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
                       str(video)]).stdout)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    a = [s for s in j["streams"] if s["codec_type"] == "audio"]
    num, den = map(int, v["r_frame_rate"].split("/"))
    dur = float(j["format"]["duration"])
    check(v["width"] == W and v["height"] == H, f"resolution {v['width']}x{v['height']}")
    check(abs(num / den - F) < 1e-6, f"frame rate {num / den:g} fps")
    check(v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p", f"video {v['codec_name']} {v['pix_fmt']}")
    check(a and a[0]["codec_name"] == "aac", "audio AAC" if a else "audio stream missing")
    check(20.0 <= dur <= 30.0, f"duration {dur:.2f}s (20-30s)")

    # ---- full decode -----------------------------------------------------------
    r = sh(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"])
    check(r.returncode == 0 and not r.stderr.strip(), "full decode without errors")

    # ---- cuts --------------------------------------------------------------------
    w, h = 54, 96
    raw = sh(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"scale={w}:{h},format=gray",
              "-f", "rawvideo", "-"], binary=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)
    check(len(frames) == tl["total_frames"], f"frame count {len(frames)} == planned {tl['total_frames']}")
    diff = np.r_[0, np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))]
    cuts = [s["start"] for s in tl["shots"][1:]]
    found, offsets = 0, []
    for c in cuts:
        lo, hi = max(1, c - 2), min(len(diff), c + 3)
        k = lo + int(np.argmax(diff[lo:hi]))
        # a cut is a spike well above the shot's typical frame-to-frame motion
        local = np.median(diff[max(1, c - 8):min(len(diff), c + 8)])
        if diff[k] > max(2.5 * local, 3.0):
            found += 1
            offsets.append(k - c)
    exact = sum(1 for o in offsets if o == 0)
    check(found == len(cuts), f"cuts detected {found}/{len(cuts)}")
    check(exact == found, f"cuts on the exact planned frame {exact}/{found}")
    beat = tl["beat_period"]
    drift = [abs((s["start"] / F - tl["drop_video_time"]) / beat * 2
                 - round((s["start"] / F - tl["drop_video_time"]) / beat * 2)) * beat / 2
             for s in tl["shots"][1:]]
    check(max(drift) <= 0.5 / F + 1e-6,
          f"every cut within half a frame of the beat grid (max {max(drift) * 1000:.1f} ms)")

    # ---- audio drop ------------------------------------------------------------------
    sr = 22050
    pcm = np.frombuffer(sh(["ffmpeg", "-v", "error", "-i", str(video), "-ac", "1", "-ar", str(sr),
                            "-f", "f32le", "-"], binary=True).stdout, np.float32)
    hop = 128
    n = len(pcm) // hop
    # crude low-pass (64-tap moving average, ~350 Hz) then energy per hop
    lowp = np.convolve(pcm, np.ones(64) / 64, mode="same")[: n * hop].reshape(n, hop)
    energy = (lowp ** 2).mean(axis=1) + 1e-12
    d = tl["drop_video_time"]
    i0, i1 = int((d - 0.3) * sr / hop), int((d + 0.3) * sr / hop)
    jump = np.log(energy[i0 + 1:i1]) - np.log(energy[i0:i1 - 1])
    onset = (i0 + 1 + int(np.argmax(jump))) * hop / sr
    check(abs(onset - d) <= 1.5 / F,
          f"audio drop onset at {onset:.3f}s vs drop cut {d:.3f}s ({(onset - d) * 1000:+.0f} ms)")

    # ---- watermark ---------------------------------------------------------------------
    png = video.parent / "premiere_assets" / "watermark.png"
    mraw = sh(["ffmpeg", "-v", "error", "-i", str(png), "-vf", "alphaextract,format=gray",
               "-f", "rawvideo", "-"], binary=True).stdout
    mask = np.frombuffer(mraw, np.uint8).reshape(H, W) > 128
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min() - 6, ys.max() + 7, xs.min() - 6, xs.max() + 7
    roi_mask = mask[y0:y1, x0:x1]
    full = sh(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
               f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0},format=gray", "-f", "rawvideo", "-"],
              binary=True).stdout
    rois = np.frombuffer(full, np.uint8).reshape(-1, y1 - y0, x1 - x0).astype(np.float32)
    contrast = rois[:, roi_mask].mean(axis=1) - rois[:, ~roi_mask].mean(axis=1)
    visible = (contrast > 4).mean()
    check(visible > 0.97, f"watermark visible in {visible * 100:.1f}% of frames "
                          f"(min contrast {contrast.min():.1f})")

    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
