"""Authoritative battle royale simulation (no rendering).

``MatchSim.step(dt, inputs)`` advances the world at a fixed tick using one
``ControlInput`` per combatant. Everything visual or audible is reported via
``sim.events`` so the renderer, the audio layer, tests — or one day a
network server — can consume the same stream. The local player and the
bots go through exactly the same rules.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from combat.weapons import Armory, WeaponInstance, direction, falloff, spread_direction
from game import building as B
from game.entities import RADIUS, Combatant, Container, ControlInput, GroundItem
from inventory.match_inventory import ConsumableStack, MatchInventory
from progression.rewards import MatchSummary
from world.collision import Box
from world.island import IslandLayout, build_island
from world.storm import Storm

TICK = 1.0 / 30.0
WALK, SPRINT, CROUCH_SPEED = 4.8, 7.4, 2.6
ADS_MULT = 0.62
JUMP_SPEED = 7.0
GRAVITY = 22.0
BUS_ALTITUDE = 230.0
BUS_SPEED = 38.0
DIVE_FALL, DIVE_FAST, DIVE_HORIZ = 40.0, 55.0, 24.0
GLIDE_FALL, GLIDE_HORIZ = 7.5, 15.0
AUTO_DEPLOY = 85.0
MANUAL_DEPLOY = 180.0
PICKUP_RANGE = 2.6
SHIELD_MAX = 100.0


@dataclass
class DropShip:
    start: tuple[float, float]
    end: tuple[float, float]
    t: float = 0.0

    @property
    def length(self) -> float:
        return math.hypot(self.end[0] - self.start[0], self.end[1] - self.start[1])

    @property
    def duration(self) -> float:
        return self.length / BUS_SPEED

    def position(self) -> tuple[float, float, float]:
        f = min(1.0, self.t / self.duration)
        return (self.start[0] + (self.end[0] - self.start[0]) * f, self.start[1] + (self.end[1] - self.start[1]) * f,
                BUS_ALTITUDE)

    @property
    def heading(self) -> float:
        return math.degrees(math.atan2(-(self.end[0] - self.start[0]), self.end[1] - self.start[1]))

    @property
    def finished(self) -> bool:
        return self.t >= self.duration


class MatchSim:
    def __init__(self, *, seed: int | None = None, bot_count: int = 19, difficulty: str = "Normal",
                 player_name: str | None = "Player", player_loadout: dict | None = None, layout: IslandLayout | None = None,
                 storm_time_scale: float = 1.0, bot_loadouts: list[dict] | None = None):
        from bots.brain import BotBrain, bot_names
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.armory = Armory()
        self.layout = layout or build_island(7)
        self.collision = self.layout.collision
        self.terrain = self.layout.terrain
        self.time = 0.0
        self.events: list[dict] = []
        self.over = False
        self.winner: int | None = None
        self.combatants: list[Combatant] = []
        self.items: dict[int, GroundItem] = {}
        self.containers: list[Container] = []
        self.builds: dict[int, B.BuildPiece] = {}
        self._build_keys: dict = {}
        self._next_item = 1
        self._next_build = 1
        self.storm = Storm(self.rng, lambda x, y: self.terrain.is_land(x, y, 1.5), time_scale=storm_time_scale)

        a = self.rng.uniform(0, 2 * math.pi)
        off = self.rng.uniform(-150, 150)
        nx, ny = -math.sin(a), math.cos(a)
        self.ship = DropShip((math.cos(a) * 650 + nx * off, math.sin(a) * 650 + ny * off),
                             (-math.cos(a) * 650 + nx * off, -math.sin(a) * 650 + ny * off))

        names = bot_names(self.rng, bot_count)
        if player_name is not None:
            self._add_combatant(player_name, False, player_loadout or {})
        for i, name in enumerate(names):
            lo = bot_loadouts[i % len(bot_loadouts)] if bot_loadouts else {}
            self._add_combatant(name, True, lo)
        self.brains = {c.id: BotBrain(self, c, difficulty, random.Random(self.seed + c.id)) for c in self.combatants
                       if c.is_bot}
        self.player = next((c for c in self.combatants if not c.is_bot), None)
        self._spawn_loot()

    # ------------------------------------------------------------ setup
    def _add_combatant(self, name, is_bot, loadout) -> Combatant:
        c = Combatant(len(self.combatants), name, is_bot, loadout, MatchInventory(self.armory))
        x, y, z = self.ship.position()
        c.x, c.y, c.z = x, y, z
        c.prev = (x, y, z)
        self.combatants.append(c)
        return c

    def _spawn_loot(self) -> None:
        rng = self.rng
        lay = self.layout
        mix = self.armory.loot["floor_mix"]
        for (x, y, z) in lay.loot_spots:
            if rng.random() < 0.75:
                kind = _weighted(rng, mix)
                self._spawn_random(kind, x + rng.uniform(-0.5, 0.5), y + rng.uniform(-0.5, 0.5), z, "floor")
        for (x, y, z, h) in lay.chest_spots:
            if rng.random() < 0.85:
                self.containers.append(Container(len(self.containers), "chest", x, y, z, h))
        for (x, y, z) in lay.ammo_spots:
            self.containers.append(Container(len(self.containers), "ammo_box", x, y, z, rng.choice((0, 90, 180, 270))))
        for (x, y, z) in lay.crate_spots:
            idx = self.collision.add(Box.from_center((x, y, z + 0.55), (1.1, 1.1, 1.1), "crate", len(self.containers)))
            self.containers.append(Container(len(self.containers), "crate", x, y, z, 0, box_index=idx))

    def _spawn_random(self, kind, x, y, z, table):
        rng = self.rng
        if kind == "weapon":
            w = self.armory.roll_weapon(rng, table)
            self.drop(("weapon", w), x, y, z)
            ammo = w.wdef.ammo
            self.drop(("ammo", (ammo, self.armory.ammo[ammo]["pickup"])), x + 0.6, y, z)
        elif kind == "consumable":
            cid, n = self.armory.roll_consumable(rng)
            self.drop(("consumable", ConsumableStack(cid, n)), x, y, z)
        else:
            ammo = rng.choice(list(self.armory.ammo))
            self.drop(("ammo", (ammo, self.armory.ammo[ammo]["pickup"])), x, y, z)

    def drop(self, entry, x, y, z) -> GroundItem:
        kind, payload = entry
        floor = self.collision.floor_height(x, y, z + 0.5, 0.2)
        item = GroundItem(self._next_item, kind, payload, x, y, floor, self.time)
        self.items[item.id] = item
        self._next_item += 1
        self.events.append({"type": "item_spawn", "item": item.id})
        return item

    # ------------------------------------------------------------ queries
    @property
    def alive(self) -> list[Combatant]:
        return [c for c in self.combatants if c.alive]

    def nearby_items(self, c: Combatant, radius: float = PICKUP_RANGE) -> list[GroundItem]:
        return sorted((i for i in self.items.values() if abs(i.x - c.x) < radius and abs(i.y - c.y) < radius
                       and abs(i.z - c.z) < 2.0 and math.hypot(i.x - c.x, i.y - c.y) < radius),
                      key=lambda i: math.hypot(i.x - c.x, i.y - c.y))

    def nearby_container(self, c: Combatant, radius: float = PICKUP_RANGE) -> Container | None:
        best, bd = None, radius
        for k in self.containers:
            if k.opened or k.kind == "crate":
                continue
            if abs(k.x - c.x) < radius and abs(k.y - c.y) < radius and abs(k.z - c.z) < 2.0:
                d = math.hypot(k.x - c.x, k.y - c.y)
                if d < bd:
                    best, bd = k, d
        return best

    def interact_prompt(self, c: Combatant) -> str | None:
        k = self.nearby_container(c)
        if k:
            return "Open chest" if k.kind == "chest" else "Open ammo box"
        items = [i for i in self.nearby_items(c) if i.kind != "ammo"]
        if items:
            return "Pick up " + self.item_label(items[0])
        return None

    def item_label(self, item: GroundItem) -> str:
        if item.kind == "weapon":
            return f"{item.payload.rarity.title()} {item.payload.name}"
        if item.kind == "consumable":
            return f"{self.armory.consumables[item.payload.cid].name} x{item.payload.count}"
        kind, n = item.payload
        return f"{self.armory.ammo[kind]['name']} x{n}"

    # ------------------------------------------------------------ main loop
    def step(self, dt: float, inputs: dict[int, ControlInput]) -> None:
        if self.over:
            return
        self.time += dt
        if not self.ship.finished:
            self.ship.t += dt
        for e in self.storm.update(dt):
            self.events.append({"type": e})
        for c in self.combatants:
            c.prev = (c.x, c.y, c.z)
            c.action = ""
            if not c.alive:
                continue
            inp = inputs.get(c.id)
            if inp is None and c.id in self.brains:
                inp = self.brains[c.id].think(dt)
            self._update_combatant(c, inp or ControlInput(yaw=c.yaw), dt)
        self._check_end()

    def _update_combatant(self, c: Combatant, inp: ControlInput, dt: float) -> None:
        c.yaw, c.pitch = inp.yaw % 360, max(-85.0, min(85.0, inp.pitch))
        if c.state == "bus":
            x, y, z = self.ship.position()
            c.x, c.y, c.z = x, y, z - 3
            # everyone still aboard is dropped before the ship leaves the island
            if (inp.deploy and self.ship.t > 2.5) or self.ship.t > self.ship.duration * 0.8:
                c.state = "skydive"
                c.vx, c.vy, c.vz = 0.0, 0.0, -10.0
                self.events.append({"type": "jump", "who": c.id})
            return
        c.stats.survive_secs += dt
        if c.state in ("skydive", "glide"):
            self._update_air(c, inp, dt)
        else:
            self._update_ground(c, inp, dt)
            self._update_actions(c, inp, dt)
        self._storm_damage(c, dt)
        if c.z < -40:   # fell out of the world
            self._damage(c, None, 9999, False, "fall")

    def _update_air(self, c: Combatant, inp: ControlInput, dt: float) -> None:
        ground = self.collision.floor_height(c.x, c.y, c.z, RADIUS)
        above = c.z - ground
        if c.state == "skydive":
            if above < AUTO_DEPLOY or (inp.deploy and above < MANUAL_DEPLOY):
                c.state = "glide"
                self.events.append({"type": "deploy", "who": c.id})
            fall = DIVE_FAST if inp.move_y > 0.5 and inp.pitch < -30 else DIVE_FALL
            horiz = DIVE_HORIZ
        else:
            c.stats.glide_secs += dt
            fall, horiz = GLIDE_FALL, GLIDE_HORIZ
        fx, fy, _ = direction(c.yaw, 0)
        rx, ry = fy, -fx
        tx = (fx * inp.move_y + rx * inp.move_x) * horiz
        ty = (fy * inp.move_y + ry * inp.move_x) * horiz
        if c.state == "glide" and inp.move_y <= 0.05 and abs(inp.move_x) < 0.05:
            tx, ty = fx * horiz * 0.35, fy * horiz * 0.35    # gliders always drift forward a little
        blend = min(1.0, dt * 2.5)
        c.vx += (tx - c.vx) * blend
        c.vy += (ty - c.vy) * blend
        c.vz += (-fall - c.vz) * min(1.0, dt * 3.0)
        nx, ny, _ = self.collision.move(c.x, c.y, c.z, c.vx * dt, c.vy * dt, RADIUS, c.height)
        c.x, c.y = _clamp_map(nx, ny)
        c.z += c.vz * dt
        floor = self.collision.floor_height(c.x, c.y, c.z + 1.0, RADIUS)
        if c.z <= floor:
            c.z = floor
            c.state = "ground"
            c.on_ground = True
            c.vz = 0.0
            c.landed_time = self.time
            self.events.append({"type": "land", "who": c.id})

    def _update_ground(self, c: Combatant, inp: ControlInput, dt: float) -> None:
        if inp.crouch != c.crouching:
            if inp.crouch or self.collision.ceiling(c.x, c.y, c.z, RADIUS, 1.3) is None:
                c.crouching = inp.crouch
        busy = c.use_timer > 0 or c.emote is not None
        c.aiming = inp.aim and not busy
        mag = math.hypot(inp.move_x, inp.move_y)
        mx, my = (inp.move_x / mag, inp.move_y / mag) if mag > 1 else (inp.move_x, inp.move_y)
        c.sprinting = inp.sprint and my > 0.3 and not c.crouching and not c.aiming and c.use_timer <= 0
        speed = SPRINT if c.sprinting else (CROUCH_SPEED if c.crouching else WALK)
        if c.aiming:
            speed *= ADS_MULT
        if c.use_timer > 0:
            speed = min(speed, 2.2)
        if self.terrain.height(c.x, c.y) < -0.2:
            speed *= 0.55   # wading
        fx, fy, _ = direction(c.yaw, 0)
        rx, ry = fy, -fx
        tx = (fx * my + rx * mx) * speed
        ty = (fy * my + ry * mx) * speed
        accel = 14.0 if c.on_ground else 3.0
        c.vx += (tx - c.vx) * min(1.0, dt * accel)
        c.vy += (ty - c.vy) * min(1.0, dt * accel)
        c.moving = math.hypot(c.vx, c.vy) > 0.6
        if c.moving and c.emote:
            c.emote = None
        if inp.jump and c.on_ground and not c.crouching:
            c.vz = JUMP_SPEED
            c.on_ground = False
            self.events.append({"type": "jump_ground", "who": c.id})
        nx, ny, _ = self.collision.move(c.x, c.y, c.z, c.vx * dt, c.vy * dt, RADIUS, c.height)
        c.x, c.y = _clamp_map(nx, ny)
        floor = self.collision.floor_height(c.x, c.y, c.z, RADIUS)
        if c.on_ground:
            if floor < c.z - 0.6:          # walked off a ledge
                c.on_ground = False
                c.vz = 0.0
            else:
                c.z = floor
        if not c.on_ground:
            c.vz -= GRAVITY * dt
            c.z += c.vz * dt
            ceil = self.collision.ceiling(c.x, c.y, c.z - c.vz * dt, RADIUS, c.height)
            if ceil is not None and c.z + c.height > ceil and c.vz > 0:
                c.z = ceil - c.height
                c.vz = 0.0
            if c.z <= floor:
                c.z = floor
                c.vz = 0.0
                c.on_ground = True

    # ------------------------------------------------------------ actions
    def _update_actions(self, c: Combatant, inp: ControlInput, dt: float) -> None:
        inv = c.inventory
        c.fire_cooldown = max(0.0, c.fire_cooldown - dt)
        c.bloom = max(0.0, c.bloom - dt * 4.0)
        if inp.emote and c.on_ground and not c.moving:
            c.emote = inp.emote
            c.emote_timer = 8.0
            self.events.append({"type": "emote", "who": c.id, "emote": inp.emote})
        if c.emote:
            c.emote_timer -= dt
            if c.emote_timer <= 0 or inp.fire or inp.select is not None or inp.jump:
                c.emote = None
        changed = False
        if inp.select is not None:
            changed = inv.select(inp.select)
        elif inp.cycle:
            before = inv.selected
            inv.cycle(inp.cycle)
            changed = before != inv.selected
        if changed:
            c.reload_timer = 0.0
            c.use_timer = 0.0
            c.fire_cooldown = max(c.fire_cooldown, 0.25)
            self.events.append({"type": "equip", "who": c.id})

        # reloading
        item = inv.current
        if c.reload_timer > 0:
            c.reload_timer -= dt
            if c.reload_timer <= 0:
                c.reload_timer = 0.0
            if c.reload_timer == 0 and isinstance(item, WeaponInstance):
                need = item.wdef.magazine - item.in_mag
                have = inv.ammo.get(item.wdef.ammo, 0)
                n = min(need, have)
                item.in_mag += n
                inv.ammo[item.wdef.ammo] = have - n
                self.events.append({"type": "reload_done", "who": c.id})
        elif isinstance(item, WeaponInstance) and (inp.reload or (item.in_mag == 0 and inp.fire)):
            if item.in_mag < item.wdef.magazine and inv.ammo.get(item.wdef.ammo, 0) > 0:
                c.reload_timer = self.armory.reload_time(item.wdef, item.rarity)
                c.action = "reload"
                self.events.append({"type": "reload", "who": c.id, "hold": item.wdef.hold})
            elif item.in_mag == 0 and inp.fire_pressed:
                self.events.append({"type": "dry_fire", "who": c.id})

        # consumables
        if c.use_timer > 0:
            c.use_timer -= dt
            if c.use_timer <= 0:
                c.use_timer = 0.0
                self._finish_consumable(c)
        elif isinstance(item, ConsumableStack) and inp.fire_pressed:
            cdef = self.armory.consumables[item.cid]
            if self._can_use(c, cdef):
                c.use_timer = cdef.use_time
                c.use_slot = inv.selected
                c.action = "use"
                self.events.append({"type": "use_start", "who": c.id, "item": item.cid})
            else:
                self._notice(c, "Already at full " + ("shield" if cdef.shield else "health") + " for this item")

        # building
        if inp.build_toggle:
            c.build_mode = not c.build_mode
            c.reload_timer = c.use_timer = 0.0
            self.events.append({"type": "build_mode", "who": c.id, "on": c.build_mode})
        elif c.build_mode and (inp.select is not None or inp.cycle):
            c.build_mode = False                     # picking a weapon leaves build mode
            self.events.append({"type": "build_mode", "who": c.id, "on": False})
        if c.build_mode:
            if inp.build_piece in B.PIECES:
                c.build_piece = inp.build_piece
            if inp.build_material_next:
                i = B.MATERIALS.index(c.build_material)
                c.build_material = B.MATERIALS[(i + 1) % len(B.MATERIALS)]
            if (inp.fire_pressed or inp.fire) and c.fire_cooldown <= 0 and c.emote is None:
                c.fire_cooldown = 0.15
                self.place_piece(c, c.build_piece)
            inp_fire_blocked = True
        else:
            inp_fire_blocked = False

        # firing
        if not inp_fire_blocked and c.reload_timer <= 0 and c.use_timer <= 0 and c.fire_cooldown <= 0 and c.emote is None:
            if item is None and (inp.fire_pressed or inp.fire):
                self._swing(c)
            elif isinstance(item, WeaponInstance) and item.in_mag > 0:
                if inp.fire_pressed or (inp.fire and item.wdef.automatic):
                    self._fire(c, item)

        # interaction (chests take a short hold, items are instant)
        if inp.interact:
            target = self.nearby_container(c)
            if target:
                if c.interact_target != ("container", target.id):
                    c.interact_target = ("container", target.id)
                    c.interact_timer = 0.0
                c.interact_timer += dt
                if c.interact_timer >= self.armory.loot["chest_open_time"]:
                    self._open_container(c, target)
                    c.interact_target = None
            elif c.interact_target is None:
                items = [i for i in self.nearby_items(c) if i.kind != "ammo"]
                if items:
                    self.pickup(c, items[0])
                    c.interact_target = ("item", items[0].id)
        else:
            c.interact_target = None
            c.interact_timer = 0.0
        for it in self.nearby_items(c, 1.6):     # ammo and stackable top-ups are automatic
            if it.kind == "ammo":
                self.pickup(c, it)
            elif it.kind == "consumable" and any(isinstance(s, ConsumableStack) and s.cid == it.payload.cid
                                                 for s in c.inventory.slots) and self.time - it.spawn_time > 1.0:
                self.pickup(c, it)

    def _notice(self, c: Combatant, text: str) -> None:
        if not c.is_bot:
            self.events.append({"type": "notice", "who": c.id, "text": text})

    def _can_use(self, c: Combatant, cdef) -> bool:
        if cdef.heal:
            return c.health < cdef.cap
        return c.shield < cdef.cap

    def _finish_consumable(self, c: Combatant) -> None:
        inv = c.inventory
        if inv.selected != c.use_slot:
            return
        stack = inv.current
        if not isinstance(stack, ConsumableStack):
            return
        cdef = self.armory.consumables[stack.cid]
        before = c.health + c.shield
        if cdef.heal:
            c.health = min(max(c.health, min(cdef.cap, c.health + cdef.heal)), 100.0)
        if cdef.shield:
            c.shield = min(max(c.shield, min(cdef.cap, c.shield + cdef.shield)), SHIELD_MAX)
        c.stats.healed += int(c.health + c.shield - before)
        stack.count -= 1
        if stack.count <= 0:
            inv.slots[inv.selected - 1] = None
            inv.selected = 0
        self.events.append({"type": "use_done", "who": c.id, "item": cdef.id})

    def _fire(self, c: Combatant, w: WeaponInstance) -> None:
        wdef = w.wdef
        w.in_mag -= 1
        c.fire_cooldown = 1.0 / wdef.fire_rate
        c.action = "fire"
        c.emote = None
        base = wdef.spread_ads if c.aiming else wdef.spread_hip
        spread = base + c.bloom
        if c.moving and not c.aiming:
            spread += 0.8
        if not c.on_ground:
            spread += 2.5
        if c.crouching:
            spread *= 0.7
        c.bloom = min(wdef.bloom_max, c.bloom + wdef.bloom)
        origin = c.eye
        dmg = self.armory.damage(wdef, w.rarity)
        ends = []
        total = 0.0
        for _ in range(wdef.pellets):
            d = spread_direction(c.yaw, c.pitch, spread, self.rng)
            end, victim, head, dist = self._trace(c, origin, d, wdef.range)
            ends.append(end)
            if victim is not None:
                amount = dmg * falloff(wdef, dist) * (wdef.headshot if head else 1.0)
                total += self._damage(victim, c, amount, head, wdef.id)
                if wdef.category == "sniper":
                    c.stats.sniper_hits += 1
            elif isinstance(self._last_box, Box) and self._last_box.tag == "crate":
                self._hit_crate(c, self._last_box.owner, dmg * 0.5)
            elif isinstance(self._last_box, Box) and self._last_box.tag == "build":
                self._damage_piece(c, self._last_box.owner, dmg * falloff(wdef, dist) * (1.5 if wdef.category == "shotgun" else 1.0))
        self.events.append({"type": "shot", "who": c.id, "weapon": wdef.id, "origin": origin, "ends": ends,
                            "tracer": wdef.tracer, "sound": wdef.sound, "damage": round(total)})

    def _swing(self, c: Combatant) -> None:
        rate = self.armory.pickaxe["rate"]
        c.fire_cooldown = 1.0 / rate
        c.action = "swing"
        c.emote = None
        origin = c.eye
        d = direction(c.yaw, c.pitch)
        end, victim, head, dist = self._trace(c, origin, d, self.armory.pickaxe["range"])
        hit = False
        if victim is not None:
            self._damage(victim, c, self.armory.pickaxe["damage"], False, "pickaxe")
            hit = True
        elif isinstance(self._last_box, Box) and self._last_box.tag == "crate":
            self._hit_crate(c, self._last_box.owner, self.armory.pickaxe["prop_damage"])
            hit = True
        elif isinstance(self._last_box, Box) and self._last_box.tag == "build":
            self._damage_piece(c, self._last_box.owner, self.armory.pickaxe["prop_damage"])
            hit = True
        elif self._last_box is not None:
            hit = True
            self._harvest(c, self._last_box.tag, end)
        self.events.append({"type": "swing", "who": c.id, "hit": hit, "point": end})

    # ------------------------------------------------------------ building
    def _harvest(self, c: Combatant, tag: str, point) -> None:
        got = B.HARVEST.get(tag)
        if not got:
            return
        material, amount = got
        have = c.materials[material]
        gained = min(amount, B.MAX_MATERIAL - have)
        if gained > 0:
            c.materials[material] = have + gained
            c.stats.pickaxe_hits += 1
            self.events.append({"type": "harvest", "who": c.id, "material": material, "amount": gained, "point": point})

    def can_place(self, c: Combatant, kind: str):
        ix, iy, z, d = B.target_for(kind, c.x, c.y, c.z, c.yaw, c.pitch)
        if c.materials[c.build_material] < B.COST:
            return None, f"Need {B.COST} {c.build_material}"
        if B.piece_key(kind, ix, iy, z, d) in self._build_keys or len(self.builds) >= B.MAX_PIECES:
            return None, "Already built here"
        return (ix, iy, z, d), ""

    def place_piece(self, c: Combatant, kind: str) -> B.BuildPiece | None:
        spot, why = self.can_place(c, kind)
        if spot is None:
            self._notice(c, why)
            return None
        ix, iy, z, d = spot
        c.materials[c.build_material] -= B.COST
        hp = B.HP[c.build_material]
        piece = B.BuildPiece(self._next_build, kind, c.build_material, ix, iy, z, d, c.id, hp, hp)
        self._next_build += 1
        for center, size in B.piece_boxes(kind, ix, iy, z, d):
            piece.boxes.append(self.collision.add(Box.from_center(center, size, "build", piece.id)))
        self.builds[piece.id] = piece
        self._build_keys[piece.key] = piece.id
        c.action = "build"
        self.events.append({"type": "build", "who": c.id, "id": piece.id})
        return piece

    def _damage_piece(self, c: Combatant, piece_id: int, damage: float) -> None:
        piece = self.builds.get(piece_id)
        if piece is None:
            return
        piece.hp -= damage
        self.events.append({"type": "build_hit", "id": piece_id, "who": c.id})
        if piece.hp <= 0:
            for idx in piece.boxes:
                self.collision.disable(idx)
            del self.builds[piece_id]
            self._build_keys.pop(piece.key, None)
            self.events.append({"type": "build_destroyed", "id": piece_id, "who": c.id})

    def _hit_crate(self, c: Combatant, idx: int, damage: float) -> None:
        crate = self.containers[idx]
        if crate.opened:
            return
        crate.hp -= damage
        c.stats.pickaxe_hits += 1
        self.events.append({"type": "crate_hit", "id": idx, "who": c.id})
        if crate.hp <= 0:
            crate.opened = True
            crate.open_time = self.time
            self.collision.disable(crate.box_index)
            w = self.armory.roll_weapon(self.rng, "supply")
            self.drop(("weapon", w), crate.x, crate.y, crate.z + 0.5)
            self.drop(("ammo", (w.wdef.ammo, self.armory.ammo[w.wdef.ammo]["pickup"] * 2)), crate.x + 0.7, crate.y, crate.z + 0.5)
            cid, n = self.armory.roll_consumable(self.rng)
            self.drop(("consumable", ConsumableStack(cid, n)), crate.x - 0.7, crate.y, crate.z + 0.5)
            self.events.append({"type": "crate_break", "id": idx, "who": c.id})

    _last_box: Box | None = None

    def _trace(self, shooter: Combatant, origin, d, max_range):
        """Hitscan against the world and every other combatant."""
        self._last_box = None
        hit = self.collision.raycast(origin, d, max_range)
        limit = hit.distance if hit else max_range
        best, best_t, head = None, limit, False
        ox, oy, oz = origin
        for v in self.combatants:
            if v is shooter or not v.alive or v.state == "bus":
                continue
            if abs(v.x - ox) > limit + 2 or abs(v.y - oy) > limit + 2:
                continue
            res = _ray_vs_character(origin, d, v)
            if res is not None and res[0] < best_t:
                best, best_t, head = v, res[0], res[1]
        if best is None and hit is not None:
            self._last_box = hit.box
        end = (ox + d[0] * best_t, oy + d[1] * best_t, oz + d[2] * best_t)
        return end, best, head, best_t

    def _damage(self, victim: Combatant, attacker: Combatant | None, amount: float, head: bool, source: str) -> float:
        if not victim.alive or amount <= 0:
            return 0.0
        victim.last_damage_time = self.time
        victim.emote = None
        dealt = amount
        shield_broken = False
        if source not in ("storm", "fall") and victim.shield > 0:
            absorbed = min(victim.shield, amount)
            victim.shield -= absorbed
            amount -= absorbed
            shield_broken = victim.shield <= 0
        victim.health -= amount
        if attacker is not None and attacker is not victim:
            attacker.stats.damage += int(round(dealt))
        self.events.append({"type": "hit", "who": attacker.id if attacker else None, "victim": victim.id,
                            "damage": round(dealt), "head": head, "shield_broken": shield_broken, "source": source,
                            "pos": victim.eye})
        if victim.health <= 0:
            self._eliminate(victim, attacker, source)
        return dealt

    def _eliminate(self, victim: Combatant, killer: Combatant | None, source: str) -> None:
        victim.placement = len(self.alive)
        victim.health = 0.0
        victim.state = "dead"
        victim.death_time = self.time
        victim.killer = killer.id if killer else None
        victim.reload_timer = victim.use_timer = 0.0
        if killer is not None and killer is not victim:
            killer.stats.eliminations += 1
        for i, item in enumerate(victim.inventory.total_loot()):
            a = i * 1.3
            kind = "weapon" if isinstance(item, WeaponInstance) else "consumable"
            self.drop((kind, item), victim.x + math.cos(a) * 1.0, victim.y + math.sin(a) * 1.0, victim.z + 0.5)
        for j, (kind, n) in enumerate(victim.inventory.ammo.items()):
            if n > 0:
                a = j * 1.9 + 0.6
                self.drop(("ammo", (kind, n)), victim.x + math.cos(a) * 1.6, victim.y + math.sin(a) * 1.6, victim.z + 0.5)
        victim.inventory.slots = [None] * len(victim.inventory.slots)
        victim.inventory.ammo = {}
        self.events.append({"type": "elim", "victim": victim.id, "killer": killer.id if killer else None,
                            "source": source, "placement": victim.placement})

    def _storm_damage(self, c: Combatant, dt: float) -> None:
        if c.state in ("bus",) or not self.storm.outside(c.x, c.y):
            c.storm_tick = 0.0
            return
        c.storm_tick += dt
        if c.storm_tick >= 1.0:
            c.storm_tick -= 1.0
            self._damage(c, None, self.storm.dps, False, "storm")

    # ------------------------------------------------------------ looting
    def pickup(self, c: Combatant, item: GroundItem) -> bool:
        inv = c.inventory
        if item.id not in self.items:
            return False
        if item.kind == "ammo":
            kind, n = item.payload
            taken = inv.add_ammo(kind, n)
            if taken <= 0:
                return False
            if taken < n:
                item.payload = (kind, n - taken)
            else:
                del self.items[item.id]
        elif item.kind == "consumable":
            taken = inv.add_consumable(item.payload.cid, item.payload.count)
            if taken <= 0:
                self._notice(c, "Inventory full")
                return False
            item.payload.count -= taken
            if item.payload.count <= 0:
                del self.items[item.id]
        else:
            ok, dropped = inv.add_weapon(item.payload)
            if not ok:
                self._notice(c, "Inventory full - select a slot to swap")
                return False
            del self.items[item.id]
            if dropped is not None:
                kind = "weapon" if isinstance(dropped, WeaponInstance) else "consumable"
                self.drop((kind, dropped), c.x, c.y, c.z + 0.5)
        self.events.append({"type": "pickup", "who": c.id, "item": item.id, "kind": item.kind,
                            "label": self.item_label(item)})
        if item.id not in self.items:
            self.events.append({"type": "item_gone", "item": item.id})
        return True

    def _open_container(self, c: Combatant, k: Container) -> None:
        k.opened = True
        k.open_time = self.time
        rng = self.rng
        fx, fy, _ = direction(k.heading, 0)
        if k.kind == "chest":
            c.stats.chests += 1
            w = self.armory.roll_weapon(rng, "chest")
            self.drop(("weapon", w), k.x + fx * 1.2, k.y + fy * 1.2, k.z + 0.5)
            self.drop(("ammo", (w.wdef.ammo, self.armory.ammo[w.wdef.ammo]["pickup"])), k.x + fx * 1.2 + fy * 0.8,
                      k.y + fy * 1.2 - fx * 0.8, k.z + 0.5)
            cid, n = self.armory.roll_consumable(rng)
            self.drop(("consumable", ConsumableStack(cid, n)), k.x + fx * 1.2 - fy * 0.8, k.y + fy * 1.2 + fx * 0.8, k.z + 0.5)
        else:
            for j, kind in enumerate(rng.sample(list(self.armory.ammo), 2)):
                self.drop(("ammo", (kind, self.armory.ammo[kind]["pickup"] * 2)), k.x + fx * 1.0 + (j - 0.5),
                          k.y + fy * 1.0, k.z + 0.3)
        self.events.append({"type": "open", "who": c.id, "id": k.id, "kind": k.kind})

    # ------------------------------------------------------------ end
    def _check_end(self) -> None:
        alive = self.alive
        if len(alive) <= 1 and self.ship.t > 1.0:
            self.over = True
            if alive:
                self.winner = alive[0].id
                alive[0].placement = 1
            self.events.append({"type": "match_over", "winner": self.winner})

    def summary_for(self, c: Combatant) -> MatchSummary:
        placement = c.placement if c.placement else len(self.alive)
        s = c.stats
        return MatchSummary(placement=placement, players=len(self.combatants), eliminations=s.eliminations,
                            damage=s.damage, chests=s.chests, survive_secs=s.survive_secs, healed=s.healed,
                            pickaxe_hits=s.pickaxe_hits, glide_secs=s.glide_secs, sniper_hits=s.sniper_hits,
                            duration=self.time)

    def drain_events(self) -> list[dict]:
        ev, self.events = self.events, []
        return ev


def _weighted(rng, weights: dict) -> str:
    total = sum(weights.values())
    r = rng.uniform(0, total)
    for k, w in weights.items():
        r -= w
        if r <= 0:
            return k
    return next(iter(weights))


def _clamp_map(x: float, y: float, limit: float = 590.0) -> tuple[float, float]:
    return max(-limit, min(limit, x)), max(-limit, min(limit, y))


def _ray_vs_character(origin, d, v: Combatant):
    """Ray vs. a vertical capsule body plus a head sphere. Returns (t, headshot) or None."""
    ox, oy, oz = origin
    dx, dy, dz = d
    head_z = v.z + (1.1 if v.crouching else 1.64)
    hx, hy = v.x - ox, v.y - oy
    hz = head_z - oz
    t = hx * dx + hy * dy + hz * dz
    if t > 0:
        px, py, pz = ox + dx * t - v.x, oy + dy * t - v.y, oz + dz * t - head_z
        if px * px + py * py + pz * pz < 0.19 * 0.19:
            return t, True
    # body: closest approach to vertical axis in 2D, then height check
    a = dx * dx + dy * dy
    if a < 1e-9:
        return None
    b = 2 * (dx * (ox - v.x) + dy * (oy - v.y))
    cc = (ox - v.x) ** 2 + (oy - v.y) ** 2 - 0.42 ** 2
    disc = b * b - 4 * a * cc
    if disc < 0:
        return None
    t1 = (-b - math.sqrt(disc)) / (2 * a)
    if t1 < 0:
        t1 = (-b + math.sqrt(disc)) / (2 * a)
        if t1 < 0:
            return None
    z = oz + dz * t1
    top = v.z + (0.95 if v.crouching else 1.48)
    if v.z <= z <= top:
        return t1, False
    return None
