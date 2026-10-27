"""The 3D diorama behind the menus: your character on a turntable in the sky."""

import math

from .character_view import CharacterModel, model_file
from .model_utils import srgb_fix
from .procgeom import MeshBuilder, hex_color, shade, sky_dome


class MenuScene:
    def __init__(self, base, skin):
        self.base = base
        self.root = base.render.attachNewNode("menu_scene")
        sky = sky_dome(hex_color("#5b3df5"), hex_color("#ff9ad5"), hex_color("#ffb3e0"))
        sky.reparentTo(self.root)
        sky.setBin("background", 0)
        sky.setDepthWrite(False)
        sky.setLightOff(1)
        sky.setShaderOff(1)
        sky.setTwoSided(True)
        mb = MeshBuilder("turntable")
        mb.cylinder(0, 0, -0.6, 0.0, 1.6, hex_color("#ffd23f"), segs=40, top_color=hex_color("#ffe27a"))
        mb.cylinder(0, 0, -1.4, -0.6, 1.25, shade(hex_color("#8a5cff"), 1.0), segs=40)
        plat = mb.node()
        plat.reparentTo(self.root)
        self.platform = plat
        clouds = srgb_fix(base.loader.loadModel(model_file("prop_cloud.glb")))
        for i, (x, y, z, s) in enumerate(((-9, 14, -3, 2.2), (10, 18, -1, 2.8), (-14, 30, 3, 3.5),
                                          (16, 34, 6, 3.0), (3, 40, -6, 4.0))):
            cn = clouds.instanceTo(self.root)
            cn.setPos(x, y, z)
            cn.setScale(s)
        self.trophy = srgb_fix(base.loader.loadModel(model_file("prop_trophy.glb")))
        self.trophy.reparentTo(self.root)
        self.trophy.setPos(-2.6, 2.5, -1.4)
        self.trophy.setScale(0.01)
        self.trophy.hide()
        self.model = CharacterModel(base.loader, skin, self.root)
        self.model.actor.loop("Idle")
        self.spin = 200.0
        self.anim_state = "IDLE"
        self.focus = (0.0, 0.0)  # screen offset of the character (x shift)
        self.t = 0.0
        self.root.hide()

    def set_skin(self, skin):
        if self.model.skin is not skin:
            self.model.apply_skin(skin)

    def celebrate(self):
        self.anim_state = "VICTORY"
        self.t = 0.0

    def show(self, offset_x=1.3):
        self.root.show()
        self.focus = (offset_x, 0.0)

    def hide(self):
        self.root.hide()

    def update(self, dt):
        if self.root.isHidden():
            return
        self.t += dt
        # Face the camera (at -Y) and sway gently so the outfit is seen from several sides.
        self.spin = 180.0 + math.sin(self.t * 0.6) * 38.0
        self.model.actor.setH(self.spin)
        self.platform.setH(self.t * 10.0)
        self.model.update_anim(self.anim_state, 0.0, dt)
        if self.anim_state == "VICTORY" and self.t > 4.0:
            self.anim_state = "IDLE"
        # Looking at a point left of the character puts it on the right side of the screen.
        ox = self.focus[0]
        cam = self.base.camera
        cam.setPos(-ox, -6.4, 1.9 + math.sin(self.t * 0.4) * 0.06)
        cam.lookAt(-ox, 0, 0.95)
        if self.anim_state == "VICTORY":
            self.trophy.show()
            self.trophy.setScale(min(1.0, self.trophy.getSx() + dt * 3))
        elif not self.trophy.isHidden():
            self.trophy.setScale(max(0.01, self.trophy.getSx() - dt * 3))
            if self.trophy.getSx() <= 0.011:
                self.trophy.hide()
