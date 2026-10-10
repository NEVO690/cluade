"""Build every outfit: shared rig + animations + body + garments -> GLB/.blend."""
from __future__ import annotations

from xgb import core, rig
from xgb.body import finish_character
from xgb.outfits import OUTFITS


def build_outfit(asset_id: str, render: bool = True) -> dict:
    core.reset_scene()
    arm = rig.build_armature("XgunRig")
    hold_frames = rig.add_sockets(arm)
    anims = rig.bake_animations(arm)
    parts = OUTFITS[asset_id]()
    mesh = finish_character(arm, parts, asset_id)
    entry = core.export("characters", asset_id, [arm], animations=True)
    entry.update({"type": "character", "animations": anims, "hold_frames": hold_frames,
                  "sockets": {"weapon": "socket_weapon", "back": "socket_back"},
                  "height": round(max(v.co.z for v in mesh.data.vertices), 3)})
    if render:
        entry["thumb"] = render_outfit(asset_id, arm, mesh)
    return entry


def render_outfit(asset_id, arm, mesh):
    from xgb.previews import render_preview
    return render_preview(asset_id, [mesh], yaw=22, pitch=6, pose_armature=arm, pose_action="lobby_idle",
                          margin=1.02)
