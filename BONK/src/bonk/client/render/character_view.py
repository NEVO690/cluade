"""Visual representation of one Character: the Blender-made Actor, its skin and name tag."""

import json
import math
import os

from direct.actor.Actor import Actor
from panda3d.core import (Filename, LMatrix4f, Material, NodePath, TextNode, TransparencyAttrib)

from ...paths import MODELS_DIR
from .animation_controller import AnimationController
from .model_utils import srgb_fix
from .procgeom import hex_color

_META = None


def character_meta():
    global _META
    if _META is None:
        with open(os.path.join(MODELS_DIR, "bonk_character.json"), "r", encoding="utf-8") as fh:
            _META = json.load(fh)
    return _META


def model_file(name):
    return Filename.fromOsSpecific(os.path.join(MODELS_DIR, name))


class CharacterModel:
    """Actor + skin.  Used in-game and for the 3D previews in the locker / shop."""

    _template = None

    def __init__(self, loader, skin, parent):
        meta = character_meta()
        if CharacterModel._template is None:
            CharacterModel._template = loader.loadModel(model_file(meta["model"]))
        self.loader = loader
        self.actor = Actor(CharacterModel._template.copyTo(NodePath()))
        self.actor.reparentTo(parent)
        self.actor.setTwoSided(False, 1)  # single-sided: clean shadows (see course_view.srgb_fix)
        self.anim = AnimationController(self.actor, meta["animations"])
        self.accessory = None
        self.head = self.actor.exposeJoint(None, "modelRoot", meta["accessory_joint"])
        self._head_rest = self._joint_rest(meta["accessory_joint"])
        self.skin = None
        self.spin_nodes = []
        self.apply_skin(skin)

    def _joint_rest(self, name):
        # Read before any animation is bound: the net transform is still the rest pose.
        for j in self.actor.getJoints(jointName=name):
            m = LMatrix4f()
            j.getNetTransform(m)
            m.invertInPlace()
            return m
        return LMatrix4f.identMat()

    def apply_skin(self, skin):
        self.skin = skin
        zones = character_meta()["material_zones"]
        for zone, node_name in zones.items():
            np_ = self.actor.find("**/" + node_name)
            if np_.isEmpty():
                continue
            mat = Material(node_name + "_skin")
            col = hex_color(skin.colors[zone])
            mat.setBaseColor(col)
            mat.setDiffuse(col)
            mat.setAmbient(col)
            mat.setRoughness(0.15 if zone == "visor" else 0.5)
            mat.setSpecular((0.35, 0.35, 0.35, 1) if zone == "visor" else (0.12, 0.12, 0.12, 1))
            mat.setShininess(60 if zone == "visor" else 18)
            if zone == "eyes" or (skin.glow and zone == "accent"):
                mat.setEmission((col[0] * 0.9, col[1] * 0.9, col[2] * 0.9, 1))
            np_.setMaterial(mat, 1)
            np_.setColor(col, 1)
        if self.accessory is not None:
            self.accessory.removeNode()
            self.accessory = None
            self.spin_nodes = []
        if skin.accessory:
            acc = self.loader.loadModel(model_file("acc_%s.glb" % skin.accessory))
            srgb_fix(acc)
            acc.reparentTo(self.head)
            acc.setMat(self._head_rest)
            self.accessory = acc
            prop = acc.find("**/Propeller")
            if not prop.isEmpty():
                self.spin_nodes.append(prop)

    def update_anim(self, state, speed, dt):
        self.anim.update(state, speed, dt)
        for n in self.spin_nodes:
            n.setH(n.getH() + dt * 900.0)

    def destroy(self):
        self.actor.cleanup()
        self.actor.removeNode()


class CharacterView:
    """In-game view: follows the simulated Character with interpolation."""

    def __init__(self, loader, skin, parent, name, is_local=False, title=None, font=None):
        self.root = parent.attachNewNode("char_view")
        self.model = CharacterModel(loader, skin, self.root)
        self.is_local = is_local
        self.tag = self._make_tag(name, title, is_local, font)
        self.shadow = None
        self.visible = True
        self.yaw = 0.0

    def _make_tag(self, name, title, is_local, font):
        tn = TextNode("tag")
        tn.setText(name if not title else "%s\n\1title\1%s\2" % (name, title))
        tn.setAlign(TextNode.ACenter)
        if font is not None:
            tn.setFont(font)
        tn.setTextColor((1, 0.9, 0.3, 1) if is_local else (1, 1, 1, 1))
        tn.setShadow(0.06, 0.06)
        tn.setShadowColor(0, 0, 0, 0.6)
        tn.setCardColor(0, 0, 0, 0.25)
        tn.setCardAsMargin(0.25, 0.25, 0.1, 0.05)
        tn.setCardDecal(True)
        np_ = self.root.attachNewNode(tn)
        np_.setScale(0.26)
        np_.setZ(2.05)
        np_.setBillboardPointEye()
        np_.setLightOff(1)
        np_.setShaderOff(1)
        np_.setDepthWrite(False)
        np_.setBin("fixed", 10)
        np_.setTransparency(TransparencyAttrib.MAlpha)
        return np_

    def show_tag(self, flag):
        if flag:
            self.tag.show()
        else:
            self.tag.hide()

    def sync(self, ch, alpha, dt):
        """Place the model at the interpolated sim position and drive the animation."""
        px, py, pz = getattr(ch, "prev_pos", (ch.x, ch.y, ch.z))
        if abs(px - ch.x) + abs(py - ch.y) + abs(pz - ch.z) > 3.0:
            px, py, pz = ch.x, ch.y, ch.z  # teleport (respawn): no smear
        x = px + (ch.x - px) * alpha
        y = py + (ch.y - py) * alpha
        z = pz + (ch.z - pz) * alpha
        self.root.setPos(x, y, z)
        self.yaw = math.degrees(ch.yaw)
        self.model.actor.setH(self.yaw)
        hidden = ch.state == "RESPAWNING" or (ch.eliminated and ch.elim_reason in ("fell", "left"))
        if hidden and self.visible:
            self.root.hide()
            self.visible = False
        elif not hidden and not self.visible:
            self.root.show()
            self.visible = True
        # Respawn grace: blink.
        if ch.grace > 0.0 and self.visible:
            self.model.actor.setAlphaScale(0.45 if int(ch.grace * 10) % 2 else 1.0)
            self.model.actor.setTransparency(TransparencyAttrib.MAlpha)
        else:
            self.model.actor.clearTransparency()
            self.model.actor.setAlphaScale(1.0)
        self.model.update_anim(ch.state, math.hypot(ch.vx, ch.vy), dt)

    def destroy(self):
        self.model.destroy()
        self.root.removeNode()
