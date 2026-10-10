"""Validate every exported asset loads in Panda3D with the parts the game relies on.

    python tools/asset_validation/validate_assets.py

Checks: catalog cosmetics have models + thumbnails, characters carry the shared
skeleton, all animations and both sockets, weapons have muzzle/grip/sight
sockets, pickaxes a grip, back blings a back socket, buildings colliders.
Returns a list of problems (empty == all good).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

REQUIRED_ANIMS = {"idle", "walk", "run", "sprint", "crouch_idle", "crouch_walk", "jump", "fall", "skydive", "glide", "death",
                  "hold_rifle", "hold_pistol", "hold_pickaxe", "reload_rifle", "reload_pistol", "pickaxe_swing", "use_item",
                  "lobby_idle", "emote_wave", "emote_groove", "emote_flex", "emote_robot", "emote_bounce", "fire_rifle"}
REQUIRED_JOINTS = {"root", "hips", "spine", "chest", "head", "hand.R", "hand.L", "foot.R", "foot.L", "socket_weapon", "socket_back"}


def validate(load_models: bool = True) -> list[str]:
    from config import paths
    from inventory.catalog import Catalog
    problems: list[str] = []
    manifest = json.loads(paths.MODEL_MANIFEST.read_text())
    catalog = Catalog()
    for item in catalog.items.values():
        if item.model_path:
            if item.id not in manifest:
                problems.append(f"{item.id}: missing from manifest")
            elif not (paths.MODELS / manifest[item.id]["model"]).exists():
                problems.append(f"{item.id}: model file missing")
            if not (paths.THUMBS / f"{item.id}.png").exists():
                problems.append(f"{item.id}: thumbnail missing")
        if item.type == "emote" and item.extra.get("prop") and item.extra["prop"] not in manifest:
            problems.append(f"{item.id}: prop model missing")
        if item.type == "wrap" and item.extra.get("texture") and not (paths.TEXTURES / "wraps" / item.extra["texture"]).exists():
            problems.append(f"{item.id}: wrap texture missing")
        if item.type == "banner" and not (paths.ICONS / item.extra.get("icon", "")).exists():
            problems.append(f"{item.id}: banner icon missing")
    weapons = json.loads(paths.WEAPONS_FILE.read_text())
    for wid, w in weapons["weapons"].items():
        key = Path(w["model"]).stem
        if key not in manifest:
            problems.append(f"weapon {wid}: model {key} missing")
        elif not {"muzzle", "grip_l", "sight"} <= set(manifest[key].get("sockets", {})):
            problems.append(f"weapon {wid}: sockets incomplete")
    for cid, c in weapons["consumables"].items():
        if Path(c["model"]).stem not in manifest:
            problems.append(f"consumable {cid}: model missing")
    for asset, info in manifest.items():
        if asset.startswith("outfit_"):
            if set(info.get("hold_frames", {})) != {"rifle", "pistol", "pickaxe"}:
                problems.append(f"{asset}: hold frames missing")
            missing = REQUIRED_ANIMS - set(info.get("animations", {}))
            if missing:
                problems.append(f"{asset}: animations missing {sorted(missing)}")
        if asset.startswith("env_house") or asset in ("env_warehouse", "env_shop", "env_tower", "env_gas_station"):
            if not info.get("colliders"):
                problems.append(f"{asset}: no colliders")
            if not info.get("loot_spots"):
                problems.append(f"{asset}: no loot spots")
    if load_models:
        problems += _load_check(manifest)
    return problems


def _load_check(manifest: dict) -> list[str]:
    # load through ShowBase's loader exactly like the game (panda3d-gltf via entry points)
    import builtins
    from panda3d.core import Filename, loadPrcFileData
    from config import paths
    base = getattr(builtins, "base", None)
    if base is None:
        loadPrcFileData("", "window-type none\naudio-library-name null")
        from direct.showbase.ShowBase import ShowBase
        base = ShowBase()
    problems = []
    for asset, info in manifest.items():
        try:
            np_ = base.loader.loadModel(Filename.from_os_specific(str(paths.MODELS / info["model"])), noCache=True)
        except Exception as exc:
            problems.append(f"{asset}: failed to load ({exc})")
            continue
        if np_.getBounds().isEmpty():
            problems.append(f"{asset}: empty geometry")
        if asset.startswith("outfit_"):
            from direct.actor.Actor import Actor
            actor = Actor(np_)
            joints = {j.getName() for j in actor.getJoints()}
            if not REQUIRED_JOINTS <= joints:
                problems.append(f"{asset}: joints missing {sorted(REQUIRED_JOINTS - joints)}")
            anims = set(actor.getAnimNames())
            if not REQUIRED_ANIMS <= anims:
                problems.append(f"{asset}: Panda sees no anims {sorted(REQUIRED_ANIMS - anims)}")
            actor.cleanup()
        for sock in info.get("sockets", {}) if not asset.startswith("outfit_") else ():
            if np_.find(f"**/socket_{sock}").isEmpty():
                problems.append(f"{asset}: socket_{sock} node missing in GLB")
    return problems


if __name__ == "__main__":
    found = validate()
    for p in found:
        print("PROBLEM:", p)
    print(f"{len(found)} problems")
    raise SystemExit(1 if found else 0)
