"""Render every character animation at several frames into one contact-sheet image.

Verifies the Blender -> glTF -> Panda3D pipeline (model, skeleton, animations).
    xvfb-run -a python tools/render_character_sheet.py out.png
"""

import os
import sys

from panda3d.core import AmbientLight, DirectionalLight, PNMImage, loadPrcFileData

loadPrcFileData("", "win-size 260 300\naudio-library-name null\nsync-video false\nframebuffer-multisample 1\nmultisamples 4")

from direct.actor.Actor import Actor  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MODEL = os.path.join(ROOT, "assets", "models", "bonk_character.glb")


def main(out):
    base = ShowBase()
    base.setBackgroundColor(0.85, 0.9, 1.0, 1)
    base.render.setShaderAuto()
    actor = Actor(MODEL)
    actor.reparentTo(base.render)
    print("animations:", sorted(actor.getAnimNames()))
    print("joints:", [j.getName() for j in actor.getJoints()])
    print("geom nodes:", [n.getName() for n in actor.findAllMatches("**/+GeomNode")])
    sun = DirectionalLight("sun")
    sun.setColor((1.0, 0.95, 0.9, 1))
    sn = base.render.attachNewNode(sun)
    sn.setHpr(30, -40, 0)
    base.render.setLight(sn)
    amb = AmbientLight("amb")
    amb.setColor((0.45, 0.45, 0.55, 1))
    base.render.setLight(base.render.attachNewNode(amb))
    # Three-quarter view from the front-right.
    base.disableMouse()
    base.camera.setPos(2.6, 3.6, 1.4)
    base.camera.lookAt(0, 0, 0.8)
    base.camLens.setFov(40)

    anims = ["Idle", "Walk", "Run", "Jump", "Fall", "Land", "Victory", "Elimination"]
    cols = 4
    w, h = base.win.getXSize(), base.win.getYSize()
    sheet = PNMImage(w * cols, h * len(anims))
    for row, name in enumerate(anims):
        n = actor.getNumFrames(name)
        for c in range(cols):
            frame = int(round(c * (n - 1) / (cols - 1)))
            actor.pose(name, frame)
            base.graphicsEngine.renderFrame()
            base.graphicsEngine.renderFrame()
            img = PNMImage()
            base.win.getScreenshot(img)
            sheet.copySubImage(img, c * w, row * h)
        print("%-12s frames=%d" % (name, n))
    sheet.write(out)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "character_sheet.png")
