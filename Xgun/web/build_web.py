"""Builds the browser version of Xgun into web/dist (HTML + the GLB models and sounds it uses).

    python web/build_web.py

The page (web/xgun_web.html) is the game; this script injects the gameplay data
(weapons, loot tables, model colliders/loot spots from the asset manifest) and
copies the assets the web build needs next to it.
"""
from __future__ import annotations

import base64
import json
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "web" / "dist"

OUTFITS = ["outfit_vex_runner", "outfit_ember_ronin", "outfit_nova_sentinel", "outfit_tidal_drifter"]
ENV = ["env_house_a", "env_house_b", "env_warehouse", "env_shop", "env_gas_station", "env_tower", "env_tree_oak",
       "env_tree_pine", "env_tree_palm", "env_rock_a", "env_rock_b", "env_bush", "env_car", "env_barrel",
       "env_loot_chest", "env_loot_chest_lid", "env_supply_crate", "env_dropship", "env_streetlamp", "env_fence"]
OTHER = ["weapon_striker_ar", "weapon_hornet_smg", "weapon_breacher_shotgun", "weapon_longshot_sniper",
         "weapon_sidekick_pistol", "weapon_ion_lance", "item_bandage_roll", "item_medkit", "item_shield_cell",
         "item_shield_keg", "glider_wing_sail", "glider_phoenix", "backpack_daypack", "backpack_jet_canister",
         "pickaxe_iron_pick"]
SFX = ["shot_ar", "shot_smg", "shot_shotgun", "shot_sniper", "shot_pistol", "shot_ion", "hit_marker", "headshot",
       "elim", "chest_open", "chest_hum", "pickup", "equip", "reload", "dry_fire", "swing", "pickaxe_hit", "jump",
       "land", "glider_deploy", "heal_done", "shield_done", "shield_break", "step0", "step1", "step2", "step3",
       "storm_loop", "wind_loop", "ship_loop", "notify", "victory", "defeat", "ui_click", "build_place",
       "build_break", "harvest", "crate_break"]
MUSIC = ["battle_theme", "lobby_theme"]


def glb_to_gltf_json(data: bytes) -> str:
    """Binary glTF -> plain glTF JSON with the buffer embedded (artifact hosts serve .json, not .glb)."""
    magic, _version, _length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF", "not a GLB file"
    off, doc, binary = 12, None, b""
    while off < len(data):
        size, kind = struct.unpack_from("<I4s", data, off)
        chunk = data[off + 8: off + 8 + size]
        if kind == b"JSON":
            doc = json.loads(chunk)
        elif kind == b"BIN\0":
            binary = chunk
        off += 8 + size
    doc["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(binary).decode()
    return json.dumps(doc, separators=(",", ":"))


def main() -> None:
    manifest = json.loads((ROOT / "assets/models/manifest.json").read_text(encoding="utf-8"))
    weapons = json.loads((ROOT / "data/gameplay/weapons.json").read_text(encoding="utf-8"))
    loot = json.loads((ROOT / "data/gameplay/loot.json").read_text(encoding="utf-8"))
    models = {}
    for mid in OUTFITS + ENV + OTHER:
        info = manifest[mid]
        models[mid] = {k: info[k] for k in ("model", "bounds", "colliders", "loot_spots", "chest_spots", "hold")
                       if k in info}
        models[mid]["model"] = "models/" + info["model"].replace(".glb", ".json")
    data = {"models": models, "weapons": weapons, "loot": loot, "outfits": OUTFITS}

    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "sfx").mkdir(parents=True)
    (DIST / "music").mkdir()
    for mid, info in models.items():
        src = ROOT / "assets" / info["model"].replace(".json", ".glb")
        dst = DIST / info["model"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(glb_to_gltf_json(src.read_bytes()), encoding="utf-8")
    for name in SFX:
        shutil.copyfile(ROOT / f"assets/audio/sfx/{name}.wav", DIST / f"sfx/{name}.wav")
    for name in MUSIC:
        shutil.copyfile(ROOT / f"assets/audio/music/{name}.ogg", DIST / f"music/{name}.ogg")
    page = (ROOT / "web/xgun_web.html").read_text(encoding="utf-8")
    page = page.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    (DIST / "index.html").write_text(page, encoding="utf-8")
    size = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"web build: {DIST}  ({size / 1048576:.1f} MB, {len(list(DIST.rglob('*.*')))} files)")


if __name__ == "__main__":
    main()
