"""Animated character avatar with equipped cosmetics.

Used by the lobby preview, the locker, and every combatant in a match. The
outfit Actor plays locomotion on its lower body and weapon holds on its upper
body (Panda3D subparts); full-body animations (emotes, skydive, glide,
death) drive both parts.
"""
from __future__ import annotations

from direct.actor.Actor import Actor
from panda3d.core import NodePath, Quat

from game.assets import AssetLibrary, apply_wrap, fn

FULL_BODY = {"skydive", "glide", "death", "fall", "jump", "lobby_idle", "emote_wave", "emote_groove", "emote_flex",
             "emote_robot", "emote_bounce", "use_item"}


def _quat(wxyz) -> Quat:
    return Quat(*wxyz)


class CharacterAvatar:
    def __init__(self, assets: AssetLibrary, loadout: dict, parent: NodePath, *, wraps: dict | None = None,
                 show_backpack: bool = True):
        self.assets = assets
        self.loadout = dict(loadout)
        self.root = parent.attachNewNode("avatar")
        self.wraps = wraps or {}
        outfit = self.loadout.get("outfit", "outfit_vex_runner")
        path = assets.model_file(outfit)
        if path is None or not path.exists():
            outfit = "outfit_vex_runner"
            path = assets.model_file(outfit)
        self.outfit = outfit
        self.info = assets.info(outfit)
        self.actor = Actor(fn(path))
        self.actor.reparentTo(self.root)
        self.actor.makeSubpart("upper", ["spine"])
        self.actor.makeSubpart("lower", ["root"], ["spine"])
        self.anims = set(self.actor.getAnimNames())
        self._current = {"upper": None, "lower": None}
        self._oneshot = None
        # joint conversion: glTF bones are rotated -90 degrees about X relative to Blender's bone frame
        fix = Quat()
        fix.setHpr((0, 90, 0))
        self.weapon_socket = self.actor.exposeJoint(None, "modelRoot", "socket_weapon").attachNewNode("weapon_fix")
        self.weapon_socket.setQuat(fix)
        self.back_socket = self.actor.exposeJoint(None, "modelRoot", "socket_back").attachNewNode("back_fix")
        self.back_socket.setQuat(fix)
        self.held = None
        self.held_id = None
        self.hold_kind = "none"
        self.backpack = None
        self.glider = None
        self.prop = None
        if show_backpack:
            self.set_backpack(self.loadout.get("backpack"))

    # -- cosmetics ------------------------------------------------------
    def set_backpack(self, item_id: str | None) -> None:
        if self.backpack is not None:
            self.backpack.removeNode()
            self.backpack = None
        if item_id:
            self.backpack = self.assets.model(item_id)
            self.backpack.reparentTo(self.back_socket)

    def hold(self, asset_id: str | None, kind: str = "rifle", wrap_tex=None) -> None:
        """Put a weapon / pickaxe / consumable in the right hand."""
        if asset_id == self.held_id and kind == self.hold_kind:
            return
        if self.held is not None:
            self.held.removeNode()
            self.held = None
        self.held_id = asset_id
        self.hold_kind = kind if asset_id else "none"
        if not asset_id:
            return
        self.held = self.assets.model(asset_id)
        self.held.reparentTo(self.weapon_socket)
        frame = self.info.get("hold_frames", {}).get("pickaxe" if kind == "pickaxe" else kind)
        if frame and kind != "rifle":
            # level the item inside the hand for this hold pose
            self.held.setQuat(_quat(frame["quat"]).conjugate())
        if kind == "pickaxe":
            self.held.setP(self.held.getP() - 20)
        if kind == "item":
            self.held.setScale(0.8)
            self.held.setPos(0, 0.05, -0.05)
        if wrap_tex is not None and kind in ("rifle", "pistol"):
            apply_wrap(self.held, wrap_tex)

    def show_glider(self, show: bool) -> None:
        if show and self.glider is None:
            self.glider = self.assets.model(self.loadout.get("glider", "glider_wing_sail"))
            self.glider.reparentTo(self.actor)
            self.glider.setPos(0, 0.12, 2.12)
        elif not show and self.glider is not None:
            self.glider.removeNode()
            self.glider = None

    def show_prop(self, prop_id: str | None) -> None:
        if self.prop is not None:
            self.prop.removeNode()
            self.prop = None
        if prop_id:
            self.prop = self.assets.model(prop_id)
            self.prop.reparentTo(self.root)
            self.prop.setPos(0.0, 0.9, 0.13)
            self.prop.setH(180)

    # -- animation ------------------------------------------------------
    def play(self, lower: str, upper: str | None = None, *, rate: float = 1.0, loop: bool = True) -> None:
        """Loop/play animations; ``upper`` defaults to ``lower`` (full body)."""
        upper = upper or lower
        self._oneshot = None
        for part, name in (("lower", lower), ("upper", upper)):
            if name not in self.anims:
                continue
            if self._current[part] == name:
                self.actor.setPlayRate(rate, name, partName=part)
                continue
            self._current[part] = name
            self.actor.setPlayRate(rate, name, partName=part)
            if loop:
                self.actor.loop(name, partName=part)
            else:
                self.actor.play(name, partName=part)

    def set_lower(self, name: str, rate: float = 1.0) -> None:
        self._loop_part("lower", name, rate)

    def set_upper(self, name: str) -> None:
        """Loop a hold pose on the upper body unless a one-shot (reload, swing...) is still playing."""
        if self._oneshot and self._current["upper"] == self._oneshot:
            ctl = self.actor.getAnimControl(self._oneshot, partName="upper")
            if ctl is not None and ctl.isPlaying():
                return
            self._oneshot = None
        self._loop_part("upper", name, 1.0)

    def _loop_part(self, part: str, name: str, rate: float) -> None:
        if name not in self.anims:
            return
        if self._current[part] != name:
            self._current[part] = name
            self.actor.loop(name, partName=part)
        self.actor.setPlayRate(rate, name, partName=part)

    def one_shot(self, upper: str, rate: float = 1.0) -> None:
        if upper in self.anims:
            self._oneshot = upper
            self._current["upper"] = upper
            self.actor.setPlayRate(rate, upper, partName="upper")
            self.actor.play(upper, partName="upper")

    def destroy(self) -> None:
        self.actor.cleanup()
        self.root.removeNode()
