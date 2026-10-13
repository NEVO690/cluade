"""Write the edit as a Final Cut Pro 7 XML sequence that Adobe Premiere Pro imports
(File > Import) as an editable 1080x1920 sequence:

  V1  footage shots (cuts on the beat, Speed / Time Remap, Scale keyframes = zooms)
  V2  white flash frames (Opacity keyframes 100 -> 0)
  V3  opening title (Opacity keyframes: fade in / fade out)
  V4  watermark, 30 % opacity, entire duration
  A1  music, trimmed so the drop lands on the first montage cut
  A2  synthesized SFX stem (riser, impact, whooshes)

Not representable in this XML and therefore only baked into the rendered MP4:
camera shake, motion blur, glow, colour grade, chroma hit and grain.

Re-export with your own media location so Premiere links automatically:
  python3 tools/export_premiere.py output/<name>_timeline.json "D:/Edits/spiderman_edit"
"""
import json
import sys
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape


def _url(path):
    p = str(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p                     # Windows drive letters: /D:/...
    return "file://localhost" + quote(p, safe="/:")


def _rate(fps):
    return f"<rate><timebase>{int(round(fps))}</timebase><ntsc>FALSE</ntsc></rate>"


class Files:
    def __init__(self, media_root):
        self.root = media_root
        self.ids = {}

    def ref(self, rel, fps, dur_frames, w=None, h=None, audio=False):
        if rel in self.ids:
            return f'<file id="{self.ids[rel]}"/>'
        fid = f"file-{len(self.ids) + 1}"
        self.ids[rel] = fid
        media = ""
        if w:
            media += (f"<video><samplecharacteristics><width>{w}</width><height>{h}</height>"
                      f"</samplecharacteristics></video>")
        if audio:
            media += ("<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate>"
                      "</samplecharacteristics><channelcount>2</channelcount></audio>")
        return (f'<file id="{fid}"><name>{escape(Path(rel).name)}</name>'
                f"<pathurl>{_url(self.root / rel)}</pathurl>{_rate(fps)}"
                f"<duration>{dur_frames}</duration><media>{media}</media></file>")


def _param(pid, name, lo, hi, value=None, keys=None):
    body = f"<parameterid>{pid}</parameterid><name>{name}</name><valuemin>{lo}</valuemin><valuemax>{hi}</valuemax>"
    if keys:
        body += "".join(f"<keyframe><when>{w}</when><value>{v:.2f}</value></keyframe>" for w, v in keys)
    else:
        body += f"<value>{value}</value>"
    return f"<parameter>{body}</parameter>"


def _effect(name, eid, params):
    return (f"<filter><effect><name>{name}</name><effectid>{eid}</effectid>"
            f"<effectcategory>motion</effectcategory><effecttype>motion</effecttype>"
            f"<mediatype>video</mediatype>{''.join(params)}</effect></filter>")


def _speed(pct):
    return _effect("Time Remap", "timeremap", [
        _param("variablespeed", "variablespeed", 0, 1, 0),
        _param("speed", "speed", -100000, 100000, f"{pct:.2f}"),
        "<parameter><parameterid>reverse</parameterid><name>reverse</name><value>FALSE</value></parameter>",
        "<parameter><parameterid>frameblending</parameterid><name>frameblending</name><value>TRUE</value></parameter>",
    ])


ZOOM_START_END = {   # (start, end) multipliers matching build_edit.zoom_expr
    "opening": (1.0, 1.10), "punch": (1.20, 1.0), "punch_small": (1.10, 1.0),
    "ramp": (1.16, 1.05), "push": (1.0, 1.08), "hero": (1.02, 1.12),
}


def export(cfg, tl, project_root, out_dir, media_root=None):
    media_root = Path(media_root) if media_root else Path(project_root)
    F, W, H = tl["fps"], tl["width"], tl["height"]
    total = tl["total_frames"]
    files = Files(media_root)
    clip_id = [0]

    def clipitem(name, start, end, in_f, out_f, file_xml, filters="", media_dur=None, audio=False):
        clip_id[0] += 1
        src = ("<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>"
               if audio else "")
        return (f'<clipitem id="clipitem-{clip_id[0]}"><name>{escape(name)}</name>'
                f"<enabled>TRUE</enabled><duration>{media_dur or out_f}</duration>{_rate(F)}"
                f"<start>{start}</start><end>{end}</end><in>{in_f}</in><out>{out_f}</out>"
                f"{file_xml}{src}{filters}</clipitem>")

    from build_edit import probe   # local import: avoids a cycle at module load

    # ---- V1: footage --------------------------------------------------------
    v1 = []
    for i, s in enumerate(tl["shots"]):
        info = probe(Path(project_root) / s["file"])
        media_frames = int(info["dur"] * F)
        cover = max(W / info["w"], H / info["h"]) * 100 * 1.10      # fill 9:16 + overscan
        z0, z1 = ZOOM_START_END[s["zoom"]]
        pos, src_t = s["start"], s["src_in"]
        for j, (pdur, speed) in enumerate(s["parts"]):
            frames = int(round(pdur * F)) if j < len(s["parts"]) - 1 else s["end"] - pos
            in_f = int(round(src_t * F))
            out_f = in_f + max(1, int(round(frames * speed)))
            # keyframe times are in the clip's media frames (in point based)
            frac0 = (pos - s["start"]) / (s["end"] - s["start"])
            frac1 = (pos + frames - s["start"]) / (s["end"] - s["start"])
            za, zb = z0 + (z1 - z0) * frac0, z0 + (z1 - z0) * frac1
            motion = _effect("Basic Motion", "basic", [
                _param("scale", "Scale", 0, 1000, keys=[(in_f, cover * za), (out_f, cover * zb)])])
            fx = motion + (_speed(speed * 100) if abs(speed - 1) > 1e-6 else "")
            name = f"{i:02d}_{s['kind']}" + (f"_part{j + 1}" if len(s["parts"]) > 1 else "")
            v1.append(clipitem(name, pos, pos + frames, in_f, out_f,
                               files.ref(s["file"], F, media_frames, info["w"], info["h"]),
                               fx, media_frames))
            pos += frames
            src_t += frames / F * speed

    # ---- V2: flashes --------------------------------------------------------
    v2 = []
    flash_len = int(round(0.12 * F)) + 1
    for s in tl["shots"]:
        if s.get("flash"):
            op = _effect("Opacity", "opacity", [
                _param("opacity", "opacity", 0, 100, keys=[(0, 100), (flash_len, 0)])])
            v2.append(clipitem("flash", s["start"], s["start"] + flash_len, 0, flash_len,
                               files.ref("output/premiere_assets/flash_white.png", F, total, W, H),
                               op, total))

    # ---- V3: title / V4: watermark -----------------------------------------
    ti = cfg["title"]
    t0, t1 = int(round(ti["start"] * F)), int(round(ti["end"] * F))
    fade_in, fade_out = int(0.6 * F), int(0.45 * F)
    title_fx = _effect("Opacity", "opacity", [_param("opacity", "opacity", 0, 100, keys=[
        (0, 0), (fade_in, 100), (t1 - t0 - fade_out, 100), (t1 - t0, 0)])])
    v3 = [clipitem("title: " + " ".join(ti["lines"]), t0, t1, 0, t1 - t0,
                   files.ref("output/premiere_assets/title.png", F, total, W, H), title_fx, total)]
    wm_fx = _effect("Opacity", "opacity", [
        _param("opacity", "opacity", 0, 100, f"{cfg['watermark']['opacity'] * 100:.0f}")])
    v4 = [clipitem("watermark: " + cfg["watermark"]["text"], 0, total, 0, total,
                   files.ref("output/premiere_assets/watermark.png", F, total, W, H), wm_fx, total)]

    # ---- audio ---------------------------------------------------------------
    m_in = int(round(tl["music_offset"] * F))
    a1 = [clipitem("music", 0, total, m_in, m_in + total,
                   files.ref(cfg["music"]["file"], F, m_in + total + F * 60, audio=True),
                   "", m_in + total + F * 60, audio=True)]
    a2 = [clipitem("sfx", 0, total, 0, total,
                   files.ref("output/premiere_assets/sfx.wav", F, total, audio=True),
                   "", total, audio=True)]

    def track(items):
        return "<track>" + "".join(items) + "<enabled>TRUE</enabled><locked>FALSE</locked></track>"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">'
        f'<sequence id="sequence-1"><name>{escape(tl["project_name"])}</name>'
        f"<duration>{total}</duration>{_rate(F)}"
        "<timecode><string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat>"
        f"{_rate(F)}</timecode><media><video><format><samplecharacteristics>{_rate(F)}"
        f"<width>{W}</width><height>{H}</height><anamorphic>FALSE</anamorphic>"
        "<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>"
        "</samplecharacteristics></format>"
        + track(v1) + track(v2) + track(v3) + track(v4) +
        "</video><audio><numOutputChannels>2</numOutputChannels><format><samplecharacteristics>"
        "<depth>16</depth><samplerate>48000</samplerate></samplecharacteristics></format>"
        + track(a1) + track(a2) +
        "</audio></media></sequence></xmeml>\n"
    )
    dst = Path(out_dir) / f"{tl['project_name']}_Premiere.xml"
    dst.write_text(xml)
    return dst


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    root = Path(__file__).resolve().parent.parent
    tl_path = Path(sys.argv[1])
    timeline = json.loads(tl_path.read_text())
    cfg_name = "placeholder_config.json" if timeline["project_name"].startswith("PREVIEW") else "edit_config.json"
    config = json.loads((root / cfg_name).read_text())
    media = sys.argv[2] if len(sys.argv) > 2 else None
    print(export(config, timeline, root, tl_path.parent, media))
