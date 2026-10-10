"""Playable match: wires the simulation to input, camera, rendering, audio and HUD."""
from __future__ import annotations

import math
import random

from panda3d.core import (AmbientLight, DirectionalLight, Fog, NodePath, OrthographicLens, PerspectiveLens, Vec3,
                          WindowProperties)

from combat.weapons import WeaponInstance, direction
from game.character_view import CharacterAvatar
from game.effects import Effects
from game.entities import ControlInput
from game.match import TICK, MatchSim
from inventory.match_inventory import ConsumableStack
from ui import theme as T
from ui.hud import HUD
from ui.widgets import Button, Modal, frame, text

SHOULDER = Vec3(0.55, -3.1, 0.35)
ADS_OFFSET = Vec3(0.6, -2.1, 0.22)
AIR_OFFSET = Vec3(0.0, -7.0, 2.0)
AVATAR_RANGE = 260.0

PICKAXES = ["pickaxe_iron_pick", "pickaxe_spray_hook", "pickaxe_frostbite", "pickaxe_gearbreaker", "pickaxe_circuit_splitter",
            "pickaxe_dragonfang"]
OUTFITS = ["outfit_vex_runner", "outfit_tidal_drifter", "outfit_glitch_medic", "outfit_volt_brawler", "outfit_frost_warden",
           "outfit_nova_sentinel", "outfit_ember_ronin"]
BACKPACKS = ["backpack_daypack", "backpack_explorer_roll", "backpack_crystal_core", "backpack_boombox", "backpack_jet_canister",
             "backpack_ember_quiver", None]
GLIDERS = ["glider_wing_sail", "glider_patchwork", "glider_kite_ray", "glider_delta_jet", "glider_phoenix"]


def random_loadout(rng: random.Random) -> dict:
    """Bots wear random cosmetics — purely visual, no gameplay effect."""
    return {"outfit": rng.choice(OUTFITS), "backpack": rng.choice(BACKPACKS), "pickaxe": rng.choice(PICKAXES),
            "glider": rng.choice(GLIDERS)}


class MatchScreen:
    def __init__(self, app, loadout: dict, player_name: str, on_exit):
        self.app = app
        self.loadout = loadout
        self.on_exit = on_exit
        s = app.settings
        rng = random.Random()
        bot_loadouts = [random_loadout(rng) for _ in range(s.bot_count)]
        self.sim = MatchSim(bot_count=s.bot_count, difficulty=s.bot_difficulty, player_name=player_name,
                            player_loadout=loadout, layout=app.island, bot_loadouts=bot_loadouts)
        self.player = self.sim.player
        self.accum = 0.0
        self.cam_yaw = self.sim.ship.heading
        self.cam_pitch = -10.0
        self.keys: dict[str, bool] = {}
        self.pressed: set[str] = set()
        self.crouch_toggle = False
        self.avatars: dict[int, CharacterAvatar] = {}
        self.item_nodes: dict[int, NodePath] = {}
        self.container_nodes: dict[int, tuple] = {}
        self.paused = None
        self.finished = False
        self.result_shown = False
        self.spectate = None
        self.footstep_t = 0.0
        self.scoped = False
        self.fps_avg = 60.0

    # ----------------------------------------------------------- setup
    def start(self):
        app = self.app
        self.root = app.render.attachNewNode("match")
        self.effects = Effects(app, self.root)
        from game.build_view import BuildView
        self.build_view = BuildView(app, self.root)
        self._lights()
        self.hud = HUD(app, self.sim)
        self.wrap_tex = None
        wrap = self.loadout.get("wrap")
        if wrap and wrap != "wrap_none":
            from config import paths
            self.wrap_tex = app.assets.texture(paths.TEXTURES / "wraps" / f"{wrap}.png")
        self.ship = app.assets.model("env_dropship")
        self.ship.reparentTo(self.root)
        for c in self.sim.containers:
            self._make_container(c)
        self._bind()
        app.audio.play_music("battle_theme")
        app.camLens.setFov(app.settings.fov)
        app.camLens.setNearFar(0.15, 3000)
        self.hud.show_message("DROP SHIP LAUNCHED", "Press SPACE to jump  •  M for map", 5)
        app.taskMgr.add(self._task, "match-update")

    def _lights(self):
        app = self.app
        sun = DirectionalLight("sun")
        sun.setColor((3.0, 2.85, 2.6, 1))
        self.sun = self.root.attachNewNode(sun)
        self.sun.setHpr(35, -48, 0)
        if app.settings.shadows and app.shaders_ok:
            sun.setShadowCaster(True, 2048 if app.settings.quality == "High" else 1024, 2048 if app.settings.quality == "High" else 1024)
            lens = OrthographicLens()
            lens.setFilmSize(90, 90)
            lens.setNearFar(-200, 200)
            sun.setLens(lens)
        amb = AmbientLight("amb")
        amb.setColor((0.42, 0.46, 0.58, 1))
        self.amb = self.root.attachNewNode(amb)
        app.render.setLight(self.sun)
        app.render.setLight(self.amb)
        fog = Fog("haze")
        fog.setColor(0.72, 0.78, 0.88)
        fog.setExpDensity(1.15 / app.settings.view_distance)   # simplepbr uses exponential fog
        self.fog = app.render.attachNewNode(fog)
        app.render.setFog(fog)

    def _bind(self):
        app = self.app
        for key in ("w", "a", "s", "d", "shift", "space", "e", "c", "control", "mouse1", "mouse3", "r"):
            app.accept(key, self._key, [key, True])
            app.accept(key + "-up", self._key, [key, False])
        for i in range(6):
            app.accept(str(i + 1), self._press, [f"slot{i}"])
        for k in ("wheel_up", "wheel_down", "m", "b", "escape", "f3", "tab", "q"):
            app.accept(k, self._press, [k])
        self._capture_mouse(True)

    def _key(self, key, down):
        self.keys[key] = down
        if down:
            self.pressed.add(key)

    def _press(self, name):
        self.pressed.add(name)

    def _window(self):
        from panda3d.core import GraphicsWindow
        win = self.app.win
        return win if isinstance(win, GraphicsWindow) else None   # offscreen buffers have no mouse

    def _capture_mouse(self, capture: bool):
        self.mouse_captured = capture
        win = self._window()
        if win is None:
            return
        props = WindowProperties()
        props.setCursorHidden(capture)
        props.setMouseMode(WindowProperties.M_confined if capture else WindowProperties.M_absolute)
        win.requestProperties(props)
        self._center_mouse()

    def _center_mouse(self):
        win = self._window()
        if win is None:
            return
        self.cx, self.cy = win.getXSize() // 2, win.getYSize() // 2
        win.movePointer(0, self.cx, self.cy)

    # ----------------------------------------------------------- per frame
    def _task(self, task):
        dt = min(0.1, self.app.clock.getDt())
        if dt > 0:
            self.fps_avg += (1 / dt - self.fps_avg) * 0.05
        if self.paused is None:
            self._mouse_look()
        inp = self._gather_input()
        if self.paused is None and not self.sim.over:
            self.accum += dt
            steps = 0
            while self.accum >= TICK and steps < 5:
                self.accum -= TICK
                inputs = {self.player.id: inp} if self.player.alive else {}
                self.sim.step(TICK, inputs)
                inp.fire_pressed = inp.jump = inp.deploy = inp.reload = False
                inp.select = None
                inp.cycle = 0
                inp.emote = None
                inp.build_toggle = inp.build_material_next = False
                inp.build_piece = None
                self._events(self.sim.drain_events())
                steps += 1
        alpha = self.accum / TICK
        self._update_visuals(alpha, dt)
        self._update_camera(alpha)
        self.effects.update(dt)
        self.effects.storm_wall(self.sim.storm)
        self.build_view.sync(self.sim.builds)
        pl = self.player
        if pl.alive and pl.build_mode and pl.state == "ground":
            spot, _ = self.sim.can_place(pl, pl.build_piece)
            from game import building as B
            shown = spot or B.target_for(pl.build_piece, pl.x, pl.y, pl.z, pl.yaw, pl.pitch)
            self.build_view.show_ghost(pl.build_piece, shown, spot is not None)
        else:
            self.build_view.show_ghost(None, None, False)
        target = self.spectate if self.spectate is not None else self.player
        prompt = self.sim.interact_prompt(self.player) if self.player.alive and self.player.state == "ground" else None
        frac = self.player.interact_timer / self.sim.armory.loot["chest_open_time"] if self.player.interact_target and \
            self.player.interact_target[0] == "container" else 0.0
        spread = 0.0
        cur = self.player.inventory.current
        if isinstance(cur, WeaponInstance):
            spread = (cur.wdef.spread_ads if self.player.aiming else cur.wdef.spread_hip) + self.player.bloom
        self.hud.update(target, prompt, frac, spread, self.scoped, self.fps_avg if self.app.settings.show_fps else None)
        cam = self.app.camera.getPos(self.app.render)
        self.app.world_view.update((cam.x, cam.y), self.app.settings.view_distance, self.effects.time)
        self._audio_loops()
        if self.sim.over and not self.finished:
            self._finish()
        if not self.player.alive and not self.result_shown and self.sim.time - self.player.death_time > 2.5:
            self._show_death_panel()
        self.pressed.clear()
        return task.cont

    def _mouse_look(self):
        win = self._window()
        if win is None or not self.mouse_captured:
            return
        md = win.getPointer(0)
        dx, dy = md.getX() - self.cx, md.getY() - self.cy
        if abs(dx) > 400 or abs(dy) > 400:  # focus change / first frame
            dx = dy = 0
        sens = self.app.settings.mouse_sensitivity * 0.12
        if self.player.aiming:
            sens *= self.app.settings.ads_sensitivity
            if self.scoped:
                sens *= 0.4
        self.cam_yaw -= dx * sens
        self.cam_pitch += (dy if self.app.settings.invert_y else -dy) * sens
        self.cam_pitch = max(-80, min(70, self.cam_pitch))
        win.movePointer(0, self.cx, self.cy)

    def _gather_input(self) -> ControlInput:
        k = self.keys
        p = self.pressed
        inp = getattr(self, "_inp", None) or ControlInput()
        self._inp = inp
        if self.paused is not None:
            inp.move_x = inp.move_y = 0
            inp.fire = inp.aim = inp.sprint = False
            if "escape" in p:
                self._resume()
            return inp
        inp.move_y = (1 if k.get("w") else 0) - (1 if k.get("s") else 0)
        inp.move_x = (1 if k.get("d") else 0) - (1 if k.get("a") else 0)
        inp.sprint = bool(k.get("shift"))
        if "c" in p:
            self.crouch_toggle = not self.crouch_toggle
        inp.crouch = self.crouch_toggle or bool(k.get("control"))
        if inp.sprint:
            self.crouch_toggle = False
        inp.fire = bool(k.get("mouse1"))
        inp.fire_pressed = inp.fire_pressed or "mouse1" in p
        inp.aim = bool(k.get("mouse3"))
        inp.interact = bool(k.get("e"))
        inp.reload = inp.reload or "r" in p
        inp.jump = inp.jump or "space" in p
        inp.deploy = inp.deploy or "space" in p
        if "q" in p:
            inp.build_toggle = True
        if self.player.build_mode and not inp.build_toggle:
            # in build mode the number keys pick pieces / material, the wheel cycles pieces
            pieces = ("wall", "floor", "ramp")
            for i, piece in enumerate(pieces):
                if f"slot{i}" in p:
                    inp.build_piece = piece
            if "slot3" in p:
                inp.build_material_next = True
            if "wheel_up" in p or "wheel_down" in p:
                cur = pieces.index(self.player.build_piece)
                inp.build_piece = pieces[(cur + (1 if "wheel_down" in p else -1)) % 3]
        else:
            for i in range(6):
                if f"slot{i}" in p:
                    inp.select = i
            if "wheel_up" in p:
                inp.cycle = -1
            if "wheel_down" in p:
                inp.cycle = 1
        if "b" in p:
            emote_id = self.loadout.get("emote", "emote_wave")
            item = self.app.services.catalog.items.get(emote_id)
            inp.emote = item.extra.get("animation", "emote_wave") if item else "emote_wave"
        if "m" in p:
            self.hud.toggle_big_map(self.player)
        if "f3" in p:
            self.app.settings.show_fps = not self.app.settings.show_fps
        if "escape" in p:
            self._pause()
        yaw, pitch = self._aim_angles()
        inp.yaw, inp.pitch = yaw, pitch
        return inp

    def _aim_angles(self):
        """Aim from the character's eye toward whatever is under the crosshair."""
        p = self.player
        if p.state != "ground":
            return self.cam_yaw, self.cam_pitch
        cam = self.app.camera
        origin = cam.getPos(self.app.render)
        fwd = self.app.render.getRelativeVector(cam, Vec3(0, 1, 0))
        hit = self.sim.collision.raycast((origin.x, origin.y, origin.z), (fwd.x, fwd.y, fwd.z), 600)
        dist = hit.distance if hit else 400.0
        dist = max(dist, 4.0)
        tx, ty, tz = origin.x + fwd.x * dist, origin.y + fwd.y * dist, origin.z + fwd.z * dist
        ex, ey, ez = p.eye
        dx, dy, dz = tx - ex, ty - ey, tz - ez
        yaw = math.degrees(math.atan2(-dx, dy))
        pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
        return yaw, pitch

    # ----------------------------------------------------------- visuals
    def _avatar(self, c) -> CharacterAvatar:
        av = self.avatars.get(c.id)
        if av is None:
            av = CharacterAvatar(self.app.assets, c.loadout, self.root)
            self.avatars[c.id] = av
        return av

    def _held_for(self, c):
        if c.build_mode:
            return None, "none"
        cur = c.inventory.current
        if isinstance(cur, WeaponInstance):
            return "weapon_" + cur.wdef.id, cur.wdef.hold
        if isinstance(cur, ConsumableStack):
            return "item_" + cur.cid, "item"
        return c.loadout.get("pickaxe", "pickaxe_iron_pick"), "pickaxe"

    def _update_visuals(self, alpha: float, dt: float):
        sim = self.sim
        cam = self.app.camera.getPos(self.app.render)
        ship_pos = sim.ship.position()
        self.ship.setPos(*ship_pos)
        self.ship.setH(sim.ship.heading)
        if sim.ship.finished:
            self.ship.setPos(ship_pos[0], ship_pos[1], ship_pos[2] + (sim.time - sim.ship.duration) * 8)
            if sim.time > sim.ship.duration + 20:
                self.ship.hide()
        for c in sim.combatants:
            visible = c.state not in ("bus",) and not (c.state == "dead" and sim.time - c.death_time > 6)
            x = c.prev[0] + (c.x - c.prev[0]) * alpha
            y = c.prev[1] + (c.y - c.prev[1]) * alpha
            z = c.prev[2] + (c.z - c.prev[2]) * alpha
            far = math.hypot(x - cam.x, y - cam.y) > AVATAR_RANGE
            if not visible or (far and c is not self.player):
                if c.id in self.avatars:
                    self.avatars[c.id].root.hide()
                continue
            av = self._avatar(c)
            av.root.show()
            av.root.setPos(x, y, z)
            av.root.setH(c.yaw)
            av.root.setP(0)
            aiming_pose = c.state == "ground" and c.alive and not c.emote and c.use_timer <= 0
            av.aim_pitch(c.pitch if aiming_pose else None)
            if c.state == "dead":
                if av._current["lower"] != "death":
                    av.hold(None)
                    av.show_glider(False)
                    av.play("death", loop=False)
                fade = max(0.0, 1 - (sim.time - c.death_time - 4.5) / 1.5)
                av.root.setAlphaScale(fade)
                continue
            if c.state == "skydive":
                av.hold(None)
                av.play("skydive")
                av.root.setP(-55 if c.vz < -45 else -30)
                continue
            if c.state == "glide":
                av.hold(None)
                av.show_glider(True)
                av.play("glide")
                continue
            av.show_glider(False)
            if c.emote:
                av.hold(None)
                av.play(c.emote)
                av.show_prop("prop_boombox" if c.emote == "emote_bounce" else None)
                continue
            av.show_prop(None)
            held, kind = self._held_for(c)
            av.hold(held, kind, self.wrap_tex if c is self.player else None)
            speed = math.hypot(c.vx, c.vy)
            if not c.on_ground:
                lower = "fall"
            elif c.crouching:
                lower = "crouch_walk" if speed > 0.5 else "crouch_idle"
            elif speed > 6.5:
                lower = "sprint"
            elif speed > 3.5:
                lower = "run"
            elif speed > 0.5:
                lower = "walk"
            else:
                lower = "idle"
            upper = {"rifle": "hold_rifle", "pistol": "hold_pistol", "pickaxe": "hold_pickaxe", "item": "use_item",
                     "none": lower}[kind]
            if c.use_timer > 0:
                upper = "use_item"
            if c.action == "swing":
                av.one_shot("pickaxe_swing", 1.6)
            elif c.action == "reload":
                av.one_shot("reload_pistol" if kind == "pistol" else "reload_rifle",
                            1.3 / max(0.5, c.reload_timer) if c.reload_timer else 1.0)
            elif c.action == "fire" and kind == "rifle":
                av.one_shot("fire_rifle", 1.5)
            rate = max(0.6, min(1.4, speed / 5.0)) if lower in ("walk", "run", "sprint") else 1.0
            av.set_lower(lower, rate)
            av.set_upper(upper)
            if c is self.player:
                self._footsteps(c, speed, dt)
        # loot
        for iid, it in list(sim.items.items()):
            node = self.item_nodes.get(iid)
            if node is None:
                node = self._make_item(it)
            if math.hypot(it.x - cam.x, it.y - cam.y) > 160:
                node.hide()
            else:
                node.show()
                spin = node.find("spin")
                spin.setH(self.effects.time * 60 % 360)
                spin.setZ(0.25 + 0.06 * math.sin(self.effects.time * 3 + iid))
        for iid in [i for i in self.item_nodes if i not in sim.items]:
            self.item_nodes.pop(iid).removeNode()
        for c in sim.containers:
            parts = self.container_nodes.get(c.id)
            if parts is None:
                continue
            node, lid, glow = parts
            if c.opened:
                if c.kind == "crate":
                    node.hide()
                elif lid is not None:
                    f = min(1.0, (sim.time - c.open_time) / 0.3)
                    lid.setP(-105 * f)
                if glow is not None:
                    glow.hide()

    def _make_item(self, it) -> NodePath:
        node = self.root.attachNewNode(f"item{it.id}")
        node.setPos(it.x, it.y, it.z)
        spin = node.attachNewNode("spin")
        if it.kind == "weapon":
            m = self.app.assets.model("weapon_" + it.payload.wdef.id)
            m.setR(90)
            color = T.RARITY[it.payload.rarity]
        elif it.kind == "consumable":
            m = self.app.assets.model("item_" + it.payload.cid)
            m.setScale(1.4)
            color = T.RARITY[self.sim.armory.consumables[it.payload.cid].rarity]
        else:
            m = self.app.assets.model("env_ammo_box")
            m.setScale(0.55)
            ac = self.sim.armory.ammo[it.payload[0]]["color"]
            m.setColorScale(ac[0] * 1.2, ac[1] * 1.2, ac[2] * 1.2, 1)
            color = (*ac, 1)
        m.reparentTo(spin)
        g = self.effects.beam((0, 0, 0), color)
        g.reparentTo(node)
        g.setPos(0, 0, 0.1)
        self.item_nodes[it.id] = node
        return node

    def _make_container(self, c):
        assets = self.app.assets
        node = self.root.attachNewNode(f"cont{c.id}")
        node.setPos(c.x, c.y, c.z)
        node.setH(c.heading)
        lid = glow = None
        if c.kind == "chest":
            assets.model("env_loot_chest").reparentTo(node)
            lid = assets.model("env_loot_chest_lid")
            hinge = node.attachNewNode("hinge")
            hinge.setPos(0, -0.3, 0.45)
            lid.reparentTo(hinge)
            lid.setPos(0, -0.3, 0)
            lid = hinge
            glow = self.effects.beam((0, 0, 0), (1, 0.85, 0.3, 1))
            glow.reparentTo(node)
            glow.setPos(0, 0, 0.5)
            glow.setScale(1.6)
        elif c.kind == "ammo_box":
            assets.model("env_ammo_box").reparentTo(node)
        else:
            assets.model("env_supply_crate").reparentTo(node)
        self.container_nodes[c.id] = (node, lid, glow)

    def _footsteps(self, c, speed, dt):
        if not c.on_ground or speed < 1.0 or c.state != "ground":
            return
        self.footstep_t -= dt * speed / 2.2
        if self.footstep_t <= 0:
            self.footstep_t = 1.0
            self.app.audio.play(f"step{random.randrange(4)}", 0.45 if not c.crouching else 0.2)

    # ----------------------------------------------------------- camera
    def _update_camera(self, alpha: float):
        app = self.app
        target = self.player
        if not self.player.alive:
            killer = self.sim.combatants[self.player.killer] if self.player.killer is not None else None
            if killer is not None and killer.alive:
                self.spectate = killer
                target = killer
            elif self.spectate is not None and self.spectate.alive:
                target = self.spectate
            else:
                alive = self.sim.alive
                self.spectate = alive[0] if alive else None
                target = self.spectate or self.player
        c = target
        x = c.prev[0] + (c.x - c.prev[0]) * alpha
        y = c.prev[1] + (c.y - c.prev[1]) * alpha
        z = c.prev[2] + (c.z - c.prev[2]) * alpha
        aiming = c is self.player and c.aiming and c.state == "ground"
        cur = c.inventory.current
        zoom = cur.wdef.zoom if aiming and isinstance(cur, WeaponInstance) else 1.0
        self.scoped = aiming and isinstance(cur, WeaponInstance) and cur.wdef.category == "sniper"
        self.hud.set_scoped(self.scoped)
        if c.state == "bus":
            offset = Vec3(0, -26, 8)
            pivot = Vec3(x, y, z)
        elif c.state in ("skydive", "glide"):
            offset = AIR_OFFSET
            pivot = Vec3(x, y, z + 1.4)
        else:
            offset = ADS_OFFSET if aiming else SHOULDER
            pivot = Vec3(x, y, z + (1.15 if c.crouching else 1.55))
        yaw, pitch = (self.cam_yaw, self.cam_pitch) if c is self.player else (c.yaw, c.pitch - 8)
        rig = app.render.attachNewNode("tmp")
        rig.setPos(pivot)
        rig.setHpr(yaw, pitch, 0)
        desired = app.render.getRelativePoint(rig, offset)
        rig.removeNode()
        # pull the camera in front of walls / terrain
        d = desired - pivot
        dist = d.length()
        if dist > 0.01:
            dn = d / dist
            hit = self.sim.collision.raycast((pivot.x, pivot.y, pivot.z), (dn.x, dn.y, dn.z), dist + 0.3)
            if hit:
                desired = pivot + dn * max(0.3, hit.distance - 0.3)
        app.camera.setPos(desired)
        app.camera.setHpr(yaw, pitch, 0)
        fov = app.settings.fov / zoom
        current = app.camLens.getFov()[0]
        app.camLens.setFov(current + (fov - current) * 0.25)
        # keep the shadow frustum around the camera
        self.sun.setPos(desired.x, desired.y, 0)

    # ----------------------------------------------------------- events
    def _events(self, events):
        sim = self.sim
        me = self.player.id
        audio = self.app.audio
        listener = tuple(self.app.camera.getPos(self.app.render))
        for e in events:
            t = e["type"]
            who = e.get("who")
            if t == "shot":
                c = sim.combatants[who]
                origin = e["origin"]
                muzzle = origin
                av = self.avatars.get(who)
                if av is not None and av.held is not None and not av.root.isHidden():
                    m = av.held.find("**/socket_muzzle")
                    if not m.isEmpty():
                        mp = m.getPos(self.app.render)
                        muzzle = (mp.x, mp.y, mp.z)
                for end in e["ends"][:6]:
                    self.effects.tracer(muzzle, end, e["tracer"])
                    if who == me and not e["damage"]:
                        self.effects.impact(end, size=0.15)
                self.effects.muzzle(muzzle, e["tracer"])
                audio.play(e["sound"], 1.0 if who == me else 0.85, pos=None if who == me else origin, listener=listener)
            elif t == "hit":
                if e["who"] == me and e["victim"] != me:
                    self.hud.hit(e["head"])
                    self.effects.damage_number(e["pos"], e["damage"], e["head"], sim.combatants[e["victim"]].shield > 0 or e["shield_broken"])
                    audio.play("headshot" if e["head"] else "hit_marker", 0.8)
                    if e["shield_broken"]:
                        audio.play("shield_break", 0.7)
                if e["victim"] == me:
                    self.hud.hurt()
            elif t == "elim":
                victim = sim.combatants[e["victim"]]
                killer = sim.combatants[e["killer"]] if e["killer"] is not None else None
                if killer is not None and killer is not victim:
                    msg = f"{killer.name}  eliminated  {victim.name}"
                elif e["source"] == "storm":
                    msg = f"{victim.name} was lost in the storm"
                else:
                    msg = f"{victim.name} was eliminated"
                color = T.GOLD if e["killer"] == me else (T.RED if e["victim"] == me else T.TEXT)
                self.hud.add_feed(msg, color)
                if e["killer"] == me and e["victim"] != me:
                    self.hud.show_message("ELIMINATED", victim.name, 2.0)
                    audio.play("elim")
                    self.effects.sparkle(victim.eye)
                if e["victim"] == me:
                    audio.play("defeat", 0.8)
                    self.hud.show_message(f"#{victim.placement}", f"Eliminated by {killer.name}" if killer and killer is not victim
                                          else "You were eliminated", 4)
            elif t == "swing" and who == me:
                audio.play("swing", 0.7)
                if e["hit"]:
                    audio.play("pickaxe_hit", 0.8)
            elif t == "build":
                audio.play("build_place", 0.9 if who == me else 0.7, pos=None if who == me else listener, listener=listener)
            elif t == "build_destroyed":
                audio.play("build_break", 0.8)
            elif t == "harvest" and who == me:
                audio.play("harvest", 0.7)
                self.hud.show_notice(f"+{e['amount']} {e['material']}", 0.8)
            elif t in ("crate_break",):
                c = sim.containers[e["id"]]
                self.effects.sparkle((c.x, c.y, c.z + 0.6), (0.3, 1, 0.9, 1))
                audio.play("crate_break", pos=(c.x, c.y, c.z), listener=listener)
            elif t == "open":
                c = sim.containers[e["id"]]
                self.effects.sparkle((c.x, c.y, c.z + 0.6))
                audio.play("chest_open" if e["kind"] == "chest" else "equip", pos=(c.x, c.y, c.z), listener=listener)
            elif who == me:
                if t == "pickup":
                    audio.play("pickup", 0.8)
                    if e["kind"] != "ammo":
                        self.hud.show_notice("+ " + e["label"], 1.5)
                elif t == "reload":
                    audio.play("reload", 0.8)
                elif t == "equip":
                    audio.play("equip", 0.6)
                elif t == "dry_fire":
                    audio.play("dry_fire")
                    self.hud.show_notice("Out of ammo", 1.0)
                elif t == "jump":
                    audio.play("ui_swoosh")
                    self.hud.show_message("", "SPACE to deploy your glider early", 3)
                elif t == "deploy":
                    audio.play("glider_deploy")
                elif t == "land":
                    audio.play("land")
                    self.hud.show_message("", "Loot up! Chests glow gold. [E] interact", 3)
                elif t == "jump_ground":
                    audio.play("jump", 0.6)
                elif t == "use_done":
                    audio.play("shield_done" if "shield" in e["item"] else "heal_done")
                elif t == "notice":
                    self.hud.show_notice(e["text"])
            if t == "storm_shrinking":
                self.hud.show_message("THE STORM IS CLOSING", "Move to the safe zone", 3)
                audio.play("notify")
            elif t == "match_over":
                pass

    def _audio_loops(self):
        p = self.player
        audio = self.app.audio
        ship_d = math.dist(self.sim.ship.position(), tuple(self.app.camera.getPos(self.app.render)))
        audio.loop("ship_loop", max(0.0, 0.6 - ship_d / 400) if not self.sim.ship.finished or ship_d < 300 else 0.0)
        audio.loop("wind_loop", 0.7 if p.state == "skydive" else (0.35 if p.state == "glide" else 0.0))
        inside = self.sim.storm.distance_inside(p.x, p.y)
        audio.loop("storm_loop", 0.7 if inside < 0 else max(0.0, 0.4 - inside / 60))
        audio.loop("heal_loop", 0.5 if p.use_timer > 0 else 0.0)

    # ----------------------------------------------------------- flow
    def _pause(self):
        if self.paused is not None:
            return
        self._capture_mouse(False)
        self.paused = Modal(self.app, "PAUSED", "Offline match against AI bots. The match keeps no history if you leave "
                            "early — leaving counts as an elimination.",
                            [("Leave Match", self._leave, ()), ("Resume", self._resume, ())])

    def _resume(self):
        if self.paused is not None:
            try:
                self.paused.close()
            except Exception:
                pass
        self.paused = None
        self._capture_mouse(True)

    def _leave(self):
        self.paused = None
        if self.player.alive:
            self.player.placement = len(self.sim.alive)
        self._exit()

    def _show_death_panel(self):
        self.result_shown = True
        self._capture_mouse(False)
        p = self.player
        killer = self.sim.combatants[p.killer].name if p.killer is not None and p.killer != p.id else "the storm"
        root = self.app.a2dBottomCenter.attachNewNode("death")
        root.setPos(0, 0, 0.35)
        frame(root, -0.7, 0.7, -0.16, 0.16, T.PANEL)
        text(root, f"#{p.placement} of {len(self.sim.combatants)}", (0, 0.06), 0.06, T.TEXT, "black", "center")
        text(root, f"Eliminated by {killer}  •  {p.stats.eliminations} eliminations  •  Spectating",
             (0, -0.01), 0.032, T.TEXT_DIM, "semibold", "center")
        self.death_panel = root
        Button(root, "RETURN TO LOBBY", self._exit, pos=(0, -0.09), size=(0.5, 0.08), color=T.PRIMARY, hover=T.PRIMARY_HOVER)

    def _finish(self):
        self.finished = True
        if self.sim.winner == self.player.id:
            self._capture_mouse(False)
            self.app.audio.play("victory")
            self.hud.show_message("VICTORY ROYALE", f"{self.player.stats.eliminations} eliminations", 30)
            root = self.app.a2dBottomCenter.attachNewNode("win")
            root.setPos(0, 0, 0.3)
            Button(root, "CONTINUE", self._exit, pos=(0, 0), size=(0.5, 0.09), color=T.PRIMARY, hover=T.PRIMARY_HOVER)
            self.death_panel = root
            self.player.emote = "emote_flex"
            self.player.emote_timer = 30

    def _exit(self):
        summary = self.sim.summary_for(self.player)
        self.on_exit(summary)

    def destroy(self):
        app = self.app
        app.taskMgr.remove("match-update")
        app.ignoreAll()
        self._capture_mouse(False)
        app.audio.stop_loops()
        for av in self.avatars.values():
            av.destroy()
        self.hud.destroy()
        self.effects.destroy()
        self.build_view.destroy()
        if getattr(self, "death_panel", None) is not None:
            self.death_panel.removeNode()
        if self.paused is not None:
            self.paused.close()
        app.render.clearLight()
        app.render.clearFog()
        self.root.removeNode()
