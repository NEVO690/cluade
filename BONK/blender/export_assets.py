"""Build and export every BONK! 3D asset with Blender.

Run with either
    blender -b -P blender/export_assets.py                (Blender application)
    python blender/export_assets.py                       (pip install bpy)

Writes into assets/models/:
    bonk_character.glb      rigged character + 8 animations
    bonk_character.json     animation metadata used by the game
    acc_<name>.glb          skin accessories
    prop_<name>.glb         course props
    bonk_character.blend    editable source scene (for artists)
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402

from bonk_mesh import clear_scene, export_glb  # noqa: E402
from create_animations import build_actions  # noqa: E402
from create_character import BONES, DEFAULT_COLORS, build_character  # noqa: E402
from create_props import ACCESSORIES, PROPS  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "assets", "models")


def export_character():
    clear_scene()
    rig, meshes = build_character()
    meta = build_actions(rig)
    path = os.path.join(OUT, "bonk_character.glb")
    export_glb(path, [rig] + meshes, animations=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "bonk_character.blend"), compress=True)
    info = {
        "model": "bonk_character.glb",
        "generated_by": "blender/export_assets.py (Blender %s)" % bpy.app.version_string,
        "height": 1.45,
        "bones": list(BONES.keys()),
        "material_zones": {"body": "Bonk_Body", "accent": "Bonk_Accent", "visor": "Bonk_Visor",
                           "eyes": "Bonk_Eyes"},
        "default_colors": DEFAULT_COLORS,
        "accessory_joint": "head",
        "accessory_joint_rest": list(BONES["head"][0]),
        "animations": meta,
    }
    with open(os.path.join(OUT, "bonk_character.json"), "w") as fh:
        json.dump(info, fh, indent=2)
    print("character exported:", path, "animations:", ", ".join(meta))


def export_static(prefix, table):
    for name, fn in table.items():
        clear_scene()
        objs = fn()
        path = os.path.join(OUT, "%s_%s.glb" % (prefix, name))
        export_glb(path, objs)
        print("exported", path)


def main():
    os.makedirs(OUT, exist_ok=True)
    export_character()
    export_static("acc", ACCESSORIES)
    export_static("prop", PROPS)


if __name__ == "__main__":
    main()
