# Nexo – Spider-Man: Brand New Day vertical edit

20–30 s vertical (1080x1920, 30 fps) TikTok fan edit. The video opens on the title
**"This is my first edit and I need to cook."** over the iconic opening scene. The
scene then builds up, and a beat-synced montage hits exactly on the music's strongest
drop. The watermark `Nexon AE` (white, 30 %) sits bottom-centre inside the TikTok
safe area for the entire video.

## Status

| Item | State |
|---|---|
| Edit pipeline (plan, render, grade, title, watermark, audio, Premiere XML) | done, verified |
| Placeholder preview render | done: every check passes (`tools/verify.py`) |
| **Spider-Man: Brand New Day footage** | **missing**: must be supplied (see below) |
| **Licensed phonk track** | **missing**: must be supplied |
| Native `.prproj` | not possible here (no Premiere on Linux); a Premiere-importable XML sequence is generated instead |

No film footage was downloaded. Ripping clips from YouTube or TikTok breaks those
platforms' terms and the studios' copyright, and the edit brief rules it out.

## Add your files

```
footage/opening/opening.mp4      the iconic opening scene (>= 10 s)
footage/montage/clip01.mp4 ...   6 action clips (any length, landscape or vertical)
music/track.mp3                  licensed phonk / energetic track (wav/mp3/m4a)
```

Then optionally edit `edit_config.json`:

- `montage_clips[].moments`: start times (seconds) of the best moments in each clip. If you leave this empty, the moments are picked automatically.
- `x_focus` (0–1): the horizontal centre of the vertical crop for landscape footage.
- `music.drop_time` / `music.bpm`: set these to override the automatic detection.
- `opening.in`: where the opening scene starts.
- `watermark.text`: currently `Nexon AE`.

## Build

```bash
python3 tools/build_edit.py                 # -> output/Nexo_SpiderMan_Edit.mp4 (+ XML, timeline)
python3 tools/verify.py output/Nexo_SpiderMan_Edit.mp4
```

Requires `ffmpeg` and Python 3 with `numpy`. To regenerate the placeholder preview, run
`python3 tools/make_placeholders.py && python3 tools/build_edit.py placeholder_config.json`.

## What the edit does

- **Title (0.25–2.9 s):** Inter Display SemiBold, fades in with an ease-out rise over a darkened backdrop, then fades away before the montage.
- **Buildup:** the opening scene plays with a slow push-in, then a fast "suck-in" zoom over the last 0.35 s, with a synthesized riser into the drop.
- **Drop:** the music is aligned so the detected drop lands on the first montage cut, on an exact frame. It comes with a white flash, an RGB-split hit, a sub-bass impact and hard shake.
- **Montage:** cuts on the detected beat grid, on 1, ½ and 2-beat values, with the pattern in `PATTERN` in `tools/build_edit.py`:
  - *hit*: zoom punch, decaying camera shake, motion blur.
  - *quick*: ½-beat cuts at 1.35× speed.
  - *ramp*: 2.4× into 0.45× speed ramp, with a whoosh.
  - *slow*: 0.45× slow motion with optical-flow frame interpolation.
  - *hero*: final 4-beat slow-motion push-in and fade to black.
  - White flash and RGB split on every bar downbeat.
- **Finishing:** contrast and saturation grade, cool shadows and warm highlights, an S-curve, highlight glow, vignette, light grain.
- **Watermark:** drawn last, on every frame, so the grade never tints it.

## Premiere Pro

`output/<name>_Premiere.xml` → **File ▸ Import** in Premiere Pro. This gives you an editable 1080x1920 sequence:

- **V1:** shots on the beat-cut points, with Speed and Scale keyframes for the zooms.
- **V2:** white flashes, with Opacity keyframes.
- **V3:** the title, with fade in and out.
- **V4:** the watermark at 30 %.
- **A1:** the music, trimmed to the drop.
- **A2:** the SFX stem.

Save it as `Nexo_SpiderMan_Edit.prproj` from Premiere. If you move the folder, re-export
with your media path so the clips link automatically:

```bash
python3 tools/export_premiere.py output/Nexo_SpiderMan_Edit_timeline.json "D:/Edits/spiderman_edit"
```

The XML can't carry the shake, motion blur, glow, grade, RGB split or grain. Those
exist only in the rendered MP4; in Premiere you'd add them with Lumetri, Transform
(shutter angle) and similar effects. The XML was generated to the FCP7 XML spec but
could not be opened in Premiere in this environment, so check it after import.
