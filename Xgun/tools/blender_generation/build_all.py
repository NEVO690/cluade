"""Generate every Xgun 3D asset with Blender.

Usage (either works):
    blender --background --python tools/blender_generation/build_all.py -- [categories] [--no-render]
    python3.11 tools/blender_generation/build_all.py [categories] [--no-render]   # with the `bpy` module

Categories: characters pickaxes backpacks gliders props weapons items environment textures
(default: all). Writes .blend sources to assets/blender/, game-ready .glb files
to assets/models/, Cycles thumbnails to assets/ui/thumbs/ and updates
assets/models/manifest.json.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402,F401  (must be imported before bmesh/mathutils users)

from xgb import core  # noqa: E402

ALL = ["textures", "characters", "pickaxes", "backpacks", "gliders", "props", "weapons", "items", "environment"]


def _args() -> tuple[list[str], bool, list[str]]:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    render = "--no-render" not in argv
    only = [a.split("=", 1)[1] for a in argv if a.startswith("--only=")]
    cats = [a for a in argv if not a.startswith("--")] or ALL
    unknown = set(cats) - set(ALL)
    if unknown:
        raise SystemExit(f"Unknown categories: {', '.join(sorted(unknown))}")
    return cats, render, only


def main() -> None:
    cats, render, only = _args()
    started = time.time()
    entries: dict[str, dict] = {}

    def run(asset_id, fn):
        if only and asset_id not in only:
            return
        t = time.time()
        entries[asset_id] = fn()
        e = entries[asset_id]
        print(f"[xgun] {asset_id:32s} {e.get('triangles', 0):7d} tris {e.get('bytes', 0) // 1024:6d} KB "
              f"{time.time() - t:5.1f}s", flush=True)

    if "textures" in cats:
        from xgb import extras
        extras.build_textures()
        print("[xgun] textures written", flush=True)
    if "characters" in cats:
        from xgb.characters import build_outfit
        from xgb.outfits import OUTFITS
        for oid in OUTFITS:
            run(oid, lambda oid=oid: build_outfit(oid, render))
    from xgb import gear
    if "pickaxes" in cats:
        for pid, fn in gear.PICKAXES.items():
            run(pid, lambda pid=pid, fn=fn: gear.build_rigid("pickaxes", pid, fn, render, yaw=60, pitch=10, margin=1.0))
    if "backpacks" in cats:
        for bid, fn in gear.BACKPACKS.items():
            run(bid, lambda bid=bid, fn=fn: gear.build_rigid("backpacks", bid, fn, render, yaw=150, pitch=15))
    if "gliders" in cats:
        for gid, fn in gear.GLIDERS.items():
            run(gid, lambda gid=gid, fn=fn: gear.build_rigid("gliders", gid, fn, render, yaw=20, pitch=25, margin=1.0))
    if "props" in cats:
        for pid, fn in gear.PROPS.items():
            run(pid, lambda pid=pid, fn=fn: gear.build_rigid("props", pid, fn, render, yaw=200, pitch=15))
    if "weapons" in cats or "items" in cats:
        from xgb import weapons
        if "weapons" in cats:
            for wid in weapons.WEAPONS:
                run(wid, lambda wid=wid: weapons.build_weapon(wid, render))
        if "items" in cats:
            for iid in weapons.ITEMS:
                run(iid, lambda iid=iid: weapons.build_item(iid, render))
    if "environment" in cats:
        from xgb import environment
        for eid, fn in environment.ENVIRONMENT.items():
            run(eid, lambda eid=eid, fn=fn: environment.build_env(eid, fn, render))
    core.update_manifest(entries)
    print(f"[xgun] built {len(entries)} assets in {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
