"""Build the vertical Spider-Man: Brand New Day fan edit.

  python3 tools/build_edit.py                       # real edit  (edit_config.json)
  python3 tools/build_edit.py placeholder_config.json   # placeholder preview

Pipeline
  1. analyze the music: tempo, beat grid, strongest drop
  2. plan the timeline: opening scene + title -> buildup -> montage cut on the beat grid
  3. render every shot (speed ramps, slow-mo, zoom punches, shake, motion blur, flashes)
  4. finishing pass: grade, glow, chroma hit, grain, title, watermark
  5. audio: music aligned so the drop lands on the first montage cut, plus synthesized SFX
  6. write <name>.mp4, <name>_timeline.json and the Premiere XML sequence
"""
import json
import math
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import beats  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OVERSCAN = 1.10          # extra frame around every shot so shake never shows edges
AUDIO_SR = 48000

# Montage after the drop, in beats.  kinds: hit / quick / ramp / slow / hero
PATTERN = (
    [(1, "hit")] * 4 +                                                    # the drop
    [(0.5, "quick"), (0.5, "quick"), (1, "hit"), (2, "ramp")] +
    [(1, "hit"), (1, "hit")] + [(0.5, "quick")] * 4 +
    [(2, "slow"), (2, "ramp")] +
    [(1, "hit")] * 4 +
    [(0.5, "quick")] * 4 + [(1, "hit"), (1, "hit")] +
    [(2, "slow"), (1, "hit"), (1, "hit")] +
    [(0.5, "quick")] * 4 + [(2, "ramp")] +
    [(1, "hit"), (1, "hit"), (2, "ramp")]
)
HERO_BEATS = 4


# --------------------------------------------------------------------------- utils
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"command failed:\n{' '.join(map(str, cmd))}\n{r.stderr[-3000:]}")
    return r


def probe(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(path)])
    j = json.loads(out.stdout)
    s = j["streams"][0]
    num, den = map(int, s["r_frame_rate"].split("/"))
    return {"w": s["width"], "h": s["height"], "fps": num / den,
            "dur": float(j["format"]["duration"])}


# --------------------------------------------------------------------------- plan
def plan_timeline(cfg, music, sources):
    F = cfg["format"]["fps"]
    beat = music["beat_period"]
    want = cfg["music"].get("drop_at_video_time", 9.0)
    drop_v = min(want, music["drop"])
    drop_v = round(drop_v * F) / F                    # drop sits exactly on a frame
    music_offset = music["drop"] - drop_v

    target = cfg.get("target_duration", 27.0)
    bars = max(1, math.floor((target - drop_v) / (4 * beat)))
    while drop_v + bars * 4 * beat > 30.0 and bars > 1:
        bars -= 1
    while drop_v + bars * 4 * beat < 20.0:
        bars += 1
    n_beats = bars * 4

    body = []
    i = 0
    while sum(b for b, _ in body) < n_beats - HERO_BEATS:
        body.append(PATTERN[i % len(PATTERN)] if i < len(PATTERN)
                    else PATTERN[4 + (i - 4) % (len(PATTERN) - 4)])
        i += 1
    while sum(b for b, _ in body) > n_beats - HERO_BEATS:
        b, k = body.pop()
        rest = n_beats - HERO_BEATS - sum(x for x, _ in body)
        if rest > 0:
            body.append((rest, k if rest >= 1 else "quick"))
    body.append((HERO_BEATS, "hero"))

    def frame_at(t):
        return int(round(t * F))

    shots = []
    # opening: iconic scene from frame 0 to the drop
    op = cfg["opening"]
    shots.append({
        "kind": "opening", "file": op["file"], "x_focus": op.get("x_focus", 0.5),
        "start": 0, "end": frame_at(drop_v), "src_in": float(op.get("in", 0.0)),
        "parts": [[drop_v, 1.0]],
        "zoom": "opening", "shake": 0.0, "flash": False, "blur": False,
    })

    clips = cfg["montage_clips"]
    use_count = [0] * len(clips)
    beat_pos = 0.0
    for idx, (nb, kind) in enumerate(body):
        t0 = drop_v + beat_pos * beat
        t1 = drop_v + (beat_pos + nb) * beat
        s, e = frame_at(t0), frame_at(t1)
        dur = (e - s) / F
        downbeat = abs(beat_pos % 4) < 1e-6
        ci = idx % len(clips)
        clip = clips[ci]
        if kind == "hit":
            parts = [[dur, 1.0]]
            zoom, shake, blur = "punch", (26 if beat_pos < 4 else 14), True
        elif kind == "quick":
            parts = [[dur, 1.35]]
            zoom, shake, blur = "punch_small", 9, True
        elif kind == "ramp":
            fast = round(dur * 0.38 * F) / F
            parts = [[fast, 2.4], [dur - fast, 0.45]]
            zoom, shake, blur = "ramp", 12, True
        elif kind == "slow":
            parts = [[dur, 0.45]]
            zoom, shake, blur = "push", 3, False
        else:  # hero
            parts = [[dur, 0.5]]
            zoom, shake, blur = "hero", 2, False
        need = sum(d * sp for d, sp in parts)
        src_dur = sources[clip["file"]]["dur"]
        moments = clip.get("moments") or []
        u = use_count[ci]
        if moments:
            src_in = float(moments[u % len(moments)])
        else:
            frac = (0.13 + u * 0.618) % 1.0
            src_in = frac * max(0.0, src_dur - need - 0.1)
        src_in = max(0.0, min(src_in, max(0.0, src_dur - need - 0.05)))
        use_count[ci] += 1
        shots.append({
            "kind": kind, "file": clip["file"], "x_focus": clip.get("x_focus", 0.5),
            "start": s, "end": e, "src_in": round(src_in, 3), "parts": parts,
            "zoom": zoom, "shake": shake, "blur": blur,
            "flash": downbeat and kind in ("hit", "ramp", "slow", "hero"),
            "beat": beat_pos,
        })
        beat_pos += nb

    total_frames = shots[-1]["end"]
    return {
        "fps": F, "width": cfg["format"]["width"], "height": cfg["format"]["height"],
        "bpm": music["bpm"], "beat_period": beat, "music_drop": music["drop"],
        "drop_video_time": drop_v, "music_offset": music_offset,
        "total_frames": total_frames, "duration": total_frames / F, "shots": shots,
    }


# --------------------------------------------------------------------------- shots
def zoom_expr(zoom, dur):
    d = f"{dur:.4f}"
    return {
        # gentle push-in, then a fast "suck-in" over the last 0.35 s into the drop
        "opening": f"1+0.07*t/{d}+0.30*pow(max(0,(t-({d}-0.35))/0.35),3)",
        "punch": "1+0.20*exp(-t*7)",
        "punch_small": "1+0.10*exp(-t*9)",
        "ramp": f"1+0.16*exp(-t*5)+0.05*t/{d}",
        "push": f"1+0.08*t/{d}",
        "hero": f"1.02+0.10*t/{d}",
    }[zoom]


def shake_expr(amp, axis):
    if amp <= 0:
        return "0"
    f1, f2, p = (13.0, 7.3, 0.0) if axis == "x" else (11.0, 5.9, 1.7)
    decay = "exp(-t*5)" if amp > 6 else "1"
    return f"{amp}*{decay}*(0.7*sin(2*PI*{f1}*t+{p})+0.3*sin(2*PI*{f2}*t))"


def render_shot(shot, cfg, src, path, F, W, H):
    frames = shot["end"] - shot["start"]
    dur = frames / F
    need = sum(d * sp for d, sp in shot["parts"])
    smooth = cfg.get("smooth_slowmo", True)

    # crop the source to 9:16 around x_focus before the expensive scaling
    sw, sh = src["w"], src["h"]
    if sw / sh > W / H:
        cw, ch = int(round(sh * W / H)) // 2 * 2, sh
    else:
        cw, ch = sw, int(round(sw * H / W)) // 2 * 2
    cx = int(min(max(shot["x_focus"] * sw - cw / 2, 0), sw - cw))
    cy = (sh - ch) // 2

    chains, labels = [], []
    pos = 0.0
    n = len(shot["parts"])
    head = "[0:v]" if n == 1 else ""
    if n > 1:
        chains.append("[0:v]split=" + str(n) + "".join(f"[s{i}]" for i in range(n)))
    for i, (pdur, speed) in enumerate(shot["parts"]):
        src_d = pdur * speed
        inp = head or f"[s{i}]"
        c = (f"{inp}trim=start={pos:.4f}:duration={src_d + 0.2:.4f},"
             f"setpts=(PTS-STARTPTS)/{speed}")
        if speed < 0.8 and smooth:
            c += f",minterpolate=fps={F}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
        c += f",fps={F},trim=duration={pdur:.4f},setpts=PTS-STARTPTS"
        chains.append(c + f"[p{i}]")
        labels.append(f"[p{i}]")
        pos += src_d
    if n > 1:
        chains.append("".join(labels) + f"concat=n={n}:v=1:a=0[cat]")
        cur = "[cat]"
    else:
        cur = "[p0]"

    W0, H0 = int(W * OVERSCAN), int(H * OVERSCAN)
    z = zoom_expr(shot["zoom"], dur)
    post = [
        "tpad=stop_mode=clone:stop_duration=1",
        f"crop={cw}:{ch}:{cx}:{cy}",
    ]
    if shot["blur"]:
        post.append("tmix=frames=3:weights='1 2 1'")
    post += [
        f"scale=w='2*trunc({W0}*({z})/2)':h='2*trunc({H0}*({z})/2)':eval=frame:flags=bicubic",
        f"crop={W}:{H}:x='clip((iw-{W})/2+{shake_expr(shot['shake'], 'x')},0,iw-{W})'"
        f":y='clip((ih-{H})/2+{shake_expr(shot['shake'], 'y')},0,ih-{H})'",
    ]
    if shot["flash"]:
        post.append("fade=t=in:st=0:d=0.12:color=white")
    if shot["kind"] == "hero":
        post.append(f"fade=t=out:st={dur - 0.55:.3f}:d=0.55")
    post += ["setsar=1", "format=yuv420p"]
    chains.append(cur + ",".join(post) + "[out]")

    run(["ffmpeg", "-y", "-v", "error",
         "-ss", f"{shot['src_in']:.3f}", "-t", f"{need + 1.0:.3f}", "-i", str(ROOT / shot["file"]),
         "-filter_complex", ";".join(chains), "-map", "[out]",
         "-frames:v", str(frames), "-r", str(F),
         "-c:v", "libx264", "-preset", "fast", "-crf", "12", "-an", str(path)])


# --------------------------------------------------------------------------- audio
def synth_sfx(n, sr, tl):
    """Self-synthesized riser, drop impact and ramp whooshes (no third-party audio)."""
    out = np.zeros(n)
    rng = np.random.default_rng(3)
    drop = tl["drop_video_time"]

    def place(sig, t):
        i = int(t * sr)
        if i < 0:
            sig, i = sig[-i:], 0
        j = min(n, i + len(sig))
        if j > i:
            out[i:j] += sig[: j - i]

    # riser: 1.6 s noise + upward chirp, cut off right at the drop
    rd = 1.6
    m = int(rd * sr)
    t = np.arange(m) / sr
    noise = np.diff(rng.standard_normal(m + 1))           # crude high-pass
    f = 300 * (6.0 ** (t / rd))
    chirp = np.sin(2 * np.pi * np.cumsum(f) / sr)
    shape = (t / rd) ** 2.2
    place((0.10 * noise + 0.12 * chirp) * shape, drop - rd)

    # impact: sub drop + transient + short noisy tail
    m = int(1.6 * sr)
    t = np.arange(m) / sr
    sub = np.sin(2 * np.pi * np.cumsum(38 + 70 * np.exp(-t * 9)) / sr) * np.exp(-t / 0.55)
    hitn = rng.standard_normal(m) * np.exp(-t / 0.035)
    tail = np.convolve(rng.standard_normal(m), np.ones(40) / 40, mode="same") * np.exp(-t / 0.4)
    place(0.85 * sub + 0.35 * hitn + 0.25 * tail, drop)

    # whoosh at the start of every speed ramp
    for s in tl["shots"]:
        if s["kind"] != "ramp":
            continue
        m = int(0.45 * sr)
        t = np.arange(m) / sr
        w = np.convolve(rng.standard_normal(m), np.ones(12) / 12, mode="same")
        envl = np.sin(np.pi * t / 0.45) ** 2
        place(0.35 * w * envl, s["start"] / tl["fps"] - 0.12)
    return out


def build_audio(cfg, tl, music_path, dst, sfx_dst):
    sr = AUDIO_SR
    raw = run_bytes(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, tl['music_offset']):.4f}",
                     "-i", str(music_path), "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"])
    mus = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).astype(np.float64)
    n = int(round(tl["duration"] * sr))
    if len(mus) < n:
        mus = np.vstack([mus, np.zeros((n - len(mus), 2))])
    mus = mus[:n].copy()
    fi, fo = int(0.12 * sr), int(1.0 * sr)
    mus[:fi] *= np.linspace(0, 1, fi)[:, None]
    mus[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
    sfx = (0.55 * synth_sfx(n, sr, tl) if cfg.get("sfx", True) else np.zeros(n))[:, None]
    mix = 0.88 * mus + sfx
    gain = 0.89 / (np.max(np.abs(mix)) + 1e-9)            # -1 dBFS peak
    write_wav(dst, mix * gain, sr)
    write_wav(sfx_dst, np.repeat(sfx * gain, 2, axis=1), sr)   # stem for Premiere A2


def write_wav(path, stereo, sr):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(stereo, -1, 1) * 32767).astype(np.int16).tobytes())


def run_bytes(cmd):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{r.stderr.decode()[-2000:]}")
    return r.stdout


# --------------------------------------------------------------------------- finish
def finishing_filter(cfg, tl, build):
    F, W, H = tl["fps"], tl["width"], tl["height"]
    ti, wm = cfg["title"], cfg["watermark"]
    for i, line in enumerate(ti["lines"]):
        (build / f"title_{i}.txt").write_text(line)
    (build / "watermark.txt").write_text(wm["text"])

    drop = tl["drop_video_time"]
    hits = [s["start"] / F for s in tl["shots"] if s.get("flash")]
    chroma = "+".join(f"between(t,{h:.3f},{h + 0.10:.3f})" for h in hits) or "0"

    t0, t1 = ti["start"], ti["end"]
    p_in = f"clip((t-{t0})/0.6,0,1)"
    alpha = f"'min({p_in}*(2-{p_in}),clip(({t1}-t)/0.45,0,1))'"
    rise = f"(28*pow(1-{p_in},3))"
    size = ti["size"]
    gap = int(size * 1.28)
    y0 = H * 0.42

    g = [
        # grade: punchy contrast, cool shadows / warm highlights, rich suit reds
        "[0:v]eq=contrast=1.10:saturation=1.16:gamma=0.97,"
        "colorbalance=rs=-0.03:gs=0.0:bs=0.06:rh=0.05:gh=0.01:bh=-0.04,"
        "curves=all='0/0.02 0.25/0.21 0.5/0.5 0.78/0.83 1/0.98',split[base][gl]",
        # glow: blurred highlights screened back on top
        "[gl]curves=all='0/0 0.62/0 1/1',gblur=sigma=26[glow]",
        "[base][glow]blend=all_mode=screen:all_opacity=0.32,"
        "vignette=angle=PI/4.6,noise=alls=5:allf=t,"
        f"rgbashift=rh=-9:bh=9:enable='{chroma}'[graded]",
        # darkened backdrop behind the opening title, fades away with it
        f"color=c=black:s={W}x{H}:r={F}:d={t1 + 0.6:.2f},format=yuva420p,"
        f"colorchannelmixer=aa=0.55,fade=t=out:st={t1 - 0.45:.2f}:d=0.6:alpha=1[dim]",
        "[graded][dim]overlay=eof_action=pass:format=auto[v1]",
    ]
    draws = []
    for i in range(len(ti["lines"])):
        draws.append(
            f"drawtext=fontfile={ti['font']}:textfile={build / f'title_{i}.txt'}:"
            f"fontsize={size}:fontcolor=white:alpha={alpha}:"
            f"shadowcolor=black@0.45:shadowx=0:shadowy=3:"
            f"x=(w-tw)/2:y='{y0 + i * gap:.0f}+{rise}':enable='between(t,{t0},{t1})'")
    draws.append(
        f"drawtext=fontfile={wm['font']}:textfile={build / 'watermark.txt'}:"
        f"fontsize={wm['size']}:fontcolor=white:alpha={wm['opacity']}:"
        f"x=(w-tw)/2:y={wm['center_y']}-th/2")
    g.append("[v1]" + ",".join(draws) + ",format=yuv420p[vout]")
    return ";".join(g)


def write_overlays(cfg, tl, out_dir):
    """Transparent PNGs used by the Premiere sequence (title lines + watermark)."""
    W, H = tl["width"], tl["height"]
    ti, wm = cfg["title"], cfg["watermark"]
    size, gap, y0 = ti["size"], int(ti["size"] * 1.28), H * 0.42
    build = out_dir / "build"
    draws = [f"drawtext=fontfile={ti['font']}:textfile={build / f'title_{i}.txt'}:"
             f"fontsize={size}:fontcolor=white:shadowcolor=black@0.45:shadowy=3:"
             f"x=(w-tw)/2:y={y0 + i * gap:.0f}" for i in range(len(ti["lines"]))]
    for name, vf in (("title.png", ",".join(draws)),
                     ("watermark.png",
                      f"drawtext=fontfile={wm['font']}:textfile={build / 'watermark.txt'}:"
                      f"fontsize={wm['size']}:fontcolor=white:x=(w-tw)/2:y={wm['center_y']}-th/2"),
                     ("flash_white.png", "drawbox=c=white:t=fill")):
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"color=c=black@0.0:s={W}x{H},format=rgba", "-vf", vf,
             "-frames:v", "1", str(out_dir / "premiere_assets" / name)])


# --------------------------------------------------------------------------- main
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    reuse = "--reuse-shots" in sys.argv      # keep rendered shots, redo finishing only
    cfg_path = ROOT / (args[0] if args else "edit_config.json")
    cfg = json.loads(cfg_path.read_text())
    name = cfg["project_name"]
    F, W, H = cfg["format"]["fps"], cfg["format"]["width"], cfg["format"]["height"]

    files = [cfg["music"]["file"], cfg["opening"]["file"]] + [c["file"] for c in cfg["montage_clips"]]
    missing = [f for f in files if not (ROOT / f).is_file()]
    for font in (cfg["title"]["font"], cfg["watermark"]["font"]):
        if not Path(font).is_file():
            missing.append(font)
    if missing:
        sys.exit("Missing source files - add them (or fix edit_config.json):\n  "
                 + "\n  ".join(missing))

    print("analyzing music ...")
    music = beats.analyze(ROOT / cfg["music"]["file"], cfg["music"].get("bpm"),
                          cfg["music"].get("drop_time"))
    print(f"  {music['bpm']:.2f} BPM, drop at {music['drop']:.3f}s of the track")

    sources = {f: probe(ROOT / f) for f in files[1:]}
    tl = plan_timeline(cfg, music, sources)
    tl["project_name"] = name
    print(f"  drop lands at {tl['drop_video_time']:.3f}s, total {tl['duration']:.2f}s, "
          f"{len(tl['shots'])} shots")

    out_dir = ROOT / "output"
    build = out_dir / "build"
    if build.exists() and not reuse:
        shutil.rmtree(build)
    build.mkdir(parents=True, exist_ok=True)
    (out_dir / "premiere_assets").mkdir(exist_ok=True)

    seg_list = []
    for i, shot in enumerate(tl["shots"]):
        seg = build / f"shot_{i:02d}_{shot['kind']}.mp4"
        if not (reuse and seg.exists()):
            render_shot(shot, cfg, sources[shot["file"]], seg, F, W, H)
        seg_list.append(f"file '{seg}'")
        print(f"  shot {i:02d} {shot['kind']:<7} frames {shot['start']:>4}-{shot['end']:<4} "
              f"{Path(shot['file']).name} @ {shot['src_in']:.2f}s")
    (build / "concat.txt").write_text("\n".join(seg_list) + "\n")

    print("mixing audio ...")
    audio = build / "mix.wav"
    build_audio(cfg, tl, ROOT / cfg["music"]["file"], audio,
                out_dir / "premiere_assets" / "sfx.wav")

    print("finishing pass ...")
    final = out_dir / f"{name}.mp4"
    run(["ffmpeg", "-y", "-v", "error",
         "-f", "concat", "-safe", "0", "-i", str(build / "concat.txt"), "-i", str(audio),
         "-filter_complex", finishing_filter(cfg, tl, build),
         "-map", "[vout]", "-map", "1:a",
         "-frames:v", str(tl["total_frames"]), "-r", str(F),
         "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k",
         "-movflags", "+faststart", "-shortest", str(final)])

    write_overlays(cfg, tl, out_dir)
    tl_path = out_dir / f"{name}_timeline.json"
    tl_path.write_text(json.dumps(tl, indent=2) + "\n")

    import export_premiere
    xml = export_premiere.export(cfg, tl, ROOT, out_dir)
    print(f"done:\n  {final}\n  {xml}\n  {tl_path}")


if __name__ == "__main__":
    main()
