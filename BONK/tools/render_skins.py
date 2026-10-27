"""Render every skin (colours + Blender accessory) side by side: visual check of the skin system.

    xvfb-run -a python tools/render_skins.py skins.png
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from panda3d.core import AmbientLight, DirectionalLight, loadPrcFileData  # noqa: E402

loadPrcFileData("", "win-size 1500 360\naudio-library-name null\nframebuffer-multisample 1\nmultisamples 4")

from direct.showbase.ShowBase import ShowBase  # noqa: E402

from bonk.client.render.character_view import CharacterModel  # noqa: E402
from bonk.cosmetics.skin_definitions import SkinCatalog  # noqa: E402


def main(out):
    base = ShowBase()
    base.setBackgroundColor(0.55, 0.78, 1.0, 1)
    base.render.setShaderAuto()
    sun = base.render.attachNewNode(DirectionalLight("sun"))
    sun.node().setColor((0.95, 0.92, 0.85, 1))
    sun.setHpr(20, -45, 0)
    base.render.setLight(sun)
    amb = base.render.attachNewNode(AmbientLight("amb"))
    amb.node().setColor((0.5, 0.5, 0.6, 1))
    base.render.setLight(amb)
    cat = SkinCatalog()
    skins = cat.ordered()
    for i, skin in enumerate(skins):
        m = CharacterModel(base.loader, skin, base.render)
        m.actor.setPos((i - (len(skins) - 1) / 2) * 1.35, 0, 0)
        m.actor.setH(-10)
        m.actor.pose("Idle", 0)
        print("%-12s %-10s accessory=%s" % (skin.id, skin.rarity, skin.accessory))
    base.disableMouse()
    base.camera.setPos(0, 14, 1.6)
    base.camera.lookAt(0, 0, 0.95)
    base.camLens.setFov(52)
    for _ in range(3):
        base.graphicsEngine.renderFrame()
    base.win.saveScreenshot(out)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "skins.png")
