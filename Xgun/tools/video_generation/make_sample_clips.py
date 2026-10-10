"""Render the bundled sample clips for the TIKTOK tab from the game's own assets.

    python tools/video_generation/make_sample_clips.py

Needs an OpenGL context (use xvfb-run on headless Linux) and ffmpeg on PATH.
Clips are original renders of Xgun characters and the island (720x1280 @ 30 fps).
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "assets" / "videos" / "samples"
W, H, FPS = 540, 960, 30

CLIPS = [
    {"file": "groove_check.mp4", "title": "Groove check on the Neon stage #emote", "creator": "xgun_studio",
     "caption": "New season, new moves. Which emote are you equipping? #neontide #groove", "kind": "stage",
     "outfit": "outfit_vex_runner", "backpack": "backpack_boombox", "anim": "emote_groove", "secs": 6},
    {"file": "ronin_flex.mp4", "title": "Ember Ronin victory flex", "creator": "dropzone_dani",
     "caption": "Legendary drip only. #emberronin #victory", "kind": "stage", "outfit": "outfit_ember_ronin",
     "backpack": "backpack_ember_quiver", "anim": "emote_flex", "secs": 5},
    {"file": "boombox_bounce.mp4", "title": "Boombox Bounce is in the shop", "creator": "loot_llama",
     "caption": "Bounce bounce bounce #boombox #emote", "kind": "stage", "outfit": "outfit_volt_brawler",
     "backpack": "backpack_jet_canister", "anim": "emote_bounce", "prop": "prop_boombox", "secs": 6},
    {"file": "island_flyover.mp4", "title": "Xgun Island flyover", "creator": "glide_guru",
     "caption": "Neon Plaza from above. Where do you drop? #map #dropspot", "kind": "island", "secs": 8},
    {"file": "robot_sentinel.mp4", "title": "Nova Sentinel does the Robot", "creator": "xgun_studio",
     "caption": "Beep boop. Tier 20 of the free pass. #novasentinel #robot", "kind": "stage", "outfit": "outfit_nova_sentinel",
     "backpack": "backpack_crystal_core", "anim": "emote_robot", "secs": 6},
    {"file": "phoenix_glide.mp4", "title": "Phoenix Wings glide test", "creator": "glide_guru",
     "caption": "Smoothest glider in the game? #glider #phoenix", "kind": "glide", "outfit": "outfit_frost_warden",
     "glider": "glider_phoenix", "secs": 6},
]


def main():
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required to encode the sample clips")
    os.environ.setdefault("XGUN_NO_AUDIO", "1")
    from panda3d.core import (AmbientLight, DirectionalLight, Filename, FrameBufferProperties, GraphicsOutput, PointLight,
                              Texture, WindowProperties, loadPrcFileData)
    loadPrcFileData("", f"win-size {W} {H}\naudio-library-name null\nsync-video #f\ntextures-power-2 none")
    from direct.showbase.ShowBase import ShowBase
    import simplepbr
    from config.settings import Settings
    from game.assets import AssetLibrary
    from game.character_view import CharacterAvatar

    base = ShowBase()
    simplepbr.init(msaa_samples=4, use_emission_maps=True, enable_fog=True)
    base.disableMouse()
    base.settings = Settings()
    base.shaders_ok = True
    assets = AssetLibrary(base)
    base.assets = assets
    OUT.mkdir(parents=True, exist_ok=True)
    music = ROOT / "assets" / "audio" / "music" / "lobby_theme.ogg"
    index = []
    for n, clip in enumerate(CLIPS):
        tmp = Path(tempfile.mkdtemp())
        scene = base.render.attachNewNode("scene")
        lights = []

        def light(node):
            np_ = scene.attachNewNode(node)
            base.render.setLight(np_)
            lights.append(np_)
            return np_

        key = DirectionalLight("key")
        key.setColor((2.6, 2.4, 2.3, 1))
        light(key).setHpr(150, -35, 0)
        amb = AmbientLight("amb")
        amb.setColor((0.4, 0.4, 0.5, 1))
        light(amb)
        frames = clip["secs"] * FPS
        world = None
        if clip["kind"] in ("stage",):
            base.setBackgroundColor(0.03, 0.03, 0.08, 1)
            stage = assets.model("env_lobby_stage")
            stage.reparentTo(scene)
            rim = PointLight("rim")
            rim.setColor((3, 1.2, 4.5, 1))
            rim.setAttenuation((1, 0, 0.08))
            light(rim).setPos(-2.5, -2.5, 3)
            av = CharacterAvatar(assets, {"outfit": clip["outfit"], "backpack": clip.get("backpack")}, scene)
            av.play(clip["anim"])
            av.show_prop(clip.get("prop"))
        else:
            from world.island import build_island
            from world.world_view import WorldView
            base.setBackgroundColor(0.6, 0.72, 0.9, 1)
            from panda3d.core import Fog
            fog = Fog("f")
            fog.setColor(0.72, 0.78, 0.88)
            fog.setExpDensity(0.0011)
            base.render.setFog(fog)
            layout = build_island(7)
            world = WorldView(base, layout)
            for _ in world.build():
                pass
            av = None
            if clip["kind"] == "glide":
                av = CharacterAvatar(assets, {"outfit": clip["outfit"], "glider": clip["glider"]}, scene)
                av.play("glide")
                av.show_glider(True)
        for f in range(frames):
            t = f / FPS
            if clip["kind"] == "stage":
                a = math.radians(-25 + t * 12)
                base.camera.setPos(math.sin(a) * 4.2, math.cos(a) * 4.2, 1.35)
                base.camera.lookAt(0, 0, 1.0)
                av.actor.pose(clip["anim"], int(t * 30) % av.actor.getNumFrames(clip["anim"]))
            elif clip["kind"] == "island":
                a = math.radians(30 + t * 9)
                base.camera.setPos(math.cos(a) * 160, math.sin(a) * 160, 95 - t * 4)
                base.camera.lookAt(0, 10, 25)
            else:
                p = layout.pois[2]
                x, y, z = p.x - 60 + t * 12, p.y - 80 + t * 14, p.height + 70 - t * 4
                av.root.setPos(x, y, z)
                av.root.setH(-40)
                av.actor.pose("glide", int(t * 30) % 40)
                base.camera.setPos(x + 4, y - 7, z + 2.2)
                base.camera.lookAt(x, y, z + 1.3)
            base.taskMgr.step()
            base.taskMgr.step()
            base.win.saveScreenshot(Filename.from_os_specific(str(tmp / f"f{f:04d}.png")))
        out = OUT / clip["file"]
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(tmp / "f%04d.png")]
        if music.exists():
            cmd += ["-ss", str(n * 5), "-i", str(music), "-shortest", "-c:a", "aac", "-b:a", "96k"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", "-preset", "medium", "-vf", f"scale={W}:{H}",
                "-movflags", "+faststart", str(out)]
        subprocess.run(cmd, check=True)
        shutil.rmtree(tmp)
        if av is not None:
            av.destroy()
        if world is not None:
            world.destroy()
        base.render.clearLight()
        base.render.clearFog()
        scene.removeNode()
        index.append({k: clip[k] for k in ("file", "title", "creator", "caption")})
        print("clip", out.name, out.stat().st_size // 1024, "KB", flush=True)
    (OUT / "samples.json").write_text(json.dumps(index, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
