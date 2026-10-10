"""Offline AI opponents.

Bots are clearly labelled "BOT" everywhere in the UI. They play by the same
rules as the player: they produce a ``ControlInput`` every tick and the
simulation validates it. Decisions (targets, goals) refresh a few times per
second; steering and aiming run every tick.
"""
from __future__ import annotations

import math
import random

from combat.weapons import WeaponInstance
from game.entities import ControlInput
from inventory.match_inventory import ConsumableStack

BOT_NAMES = ["Kestrel", "Ozzie", "Mira", "Juno", "Pixel", "Rook", "Tango", "Nova", "Cinder", "Wren", "Bishop", "Sable",
             "Echo", "Dart", "Lumen", "Quill", "Basil", "Kit", "Vega", "Rumble", "Fable", "Moss", "Orbit", "Tetra",
             "Sprocket", "Hollis", "Zinnia", "Brick", "Halo", "Pip", "Tundra", "Clover", "Jolt", "Mako", "Nimbus",
             "Ruckus", "Saffron", "Tidus", "Umber", "Vixen"]

SKILL = {  # reaction (s), aim error (deg), view range (m), fire discipline
    "Easy": (0.75, 7.0, 90, 0.55),
    "Normal": (0.45, 3.8, 130, 0.8),
    "Hard": (0.28, 2.0, 170, 1.0),
}


def bot_names(rng: random.Random, count: int) -> list[str]:
    names = rng.sample(BOT_NAMES, min(count, len(BOT_NAMES)))
    while len(names) < count:
        names.append(f"Unit{len(names) + 1}")
    return ["BOT " + n for n in names]


def yaw_to(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(-dx, dy))


def angle_diff(a: float, b: float) -> float:
    return (a - b + 180) % 360 - 180


class BotBrain:
    def __init__(self, sim, me, difficulty: str, rng: random.Random):
        self.sim = sim
        self.me = me
        self.rng = rng
        self.reaction, self.aim_error, self.view_range, self.discipline = SKILL.get(difficulty, SKILL["Normal"])
        self.mode = "bus"
        self.goal: tuple[float, float, float] | None = None
        self.goal_kind = ""
        self.goal_ref = None
        self.target = None
        self.target_seen_at = 0.0
        self.last_enemy_seen = -99.0
        self.decide_timer = rng.uniform(0, 0.3)
        self.jump_at = rng.uniform(4.0, sim.ship.duration * 0.85)
        self.drop_point = self._pick_drop_point()
        self.err = (0.0, 0.0)
        self.err_timer = 0.0
        self.strafe = 1
        self.strafe_timer = 0.0
        self.stuck_check = (me.x, me.y, sim.time)
        self.detour = 0.0
        self.detour_timer = 0.0
        self.yaw = me.yaw
        self.pitch = 0.0
        self.fire_toggle = False
        self.wander = None
        self.door_via = None
        self.ignore: set = set()          # goals that proved unreachable
        self.goal_key = None
        self.goal_since = 0.0
        self.pulse = False
        self.stuck_count = 0
        self.route: list = []
        self._route_goal = None
        self.build_exit = False
        self.last_build = -99.0
        self.harvest_target = None

    # ---------------------------------------------------------- helpers
    def _pick_drop_point(self):
        lay = self.sim.layout
        if self.rng.random() < 0.7:
            p = self.rng.choice(lay.pois)
            a = self.rng.uniform(0, 2 * math.pi)
            d = self.rng.uniform(0, p.radius)
            return (p.x + math.cos(a) * d, p.y + math.sin(a) * d)
        for _ in range(30):
            x, y = self.rng.uniform(-400, 400), self.rng.uniform(-400, 400)
            if self.sim.terrain.is_land(x, y, 2):
                return (x, y)
        return (0.0, 0.0)

    def _turn_toward(self, yaw: float, pitch: float, dt: float, rate: float = 360.0) -> None:
        d = angle_diff(yaw, self.yaw)
        step = rate * dt
        self.yaw += max(-step, min(step, d))
        self.pitch += max(-step, min(step, pitch - self.pitch))

    def _steer(self, inp: ControlInput, tx: float, ty: float, dt: float, stop_dist: float = 1.2) -> float:
        me = self.me
        dx, dy = tx - me.x, ty - me.y
        dist = math.hypot(dx, dy)
        if dist < stop_dist:
            return dist
        want = yaw_to(dx, dy)
        if self.detour_timer > 0:
            self.detour_timer -= dt
            want += self.detour
        self._turn_toward(want, 0.0 if self.target is None else self.pitch, dt, 540)
        inp.move_y = 1.0
        inp.sprint = dist > 12 and self.target is None
        # unstick: if barely moved in a second, detour and hop
        sx, sy, st = self.stuck_check
        if self.sim.time - st > 1.0:
            if math.hypot(me.x - sx, me.y - sy) < 1.2 and me.on_ground:
                # escalate: wider and longer detours, then give up on the destination
                self.stuck_count += 1
                n = min(self.stuck_count, 4)
                side = 1 if self.stuck_count % 2 else -1
                self.detour = side * (60 + 25 * n)
                self.detour_timer = 0.8 + 0.6 * n
                inp.jump = True
                if self.stuck_count >= 5:
                    if self.goal_key is not None:
                        self.ignore.add(self.goal_key)
                    self.goal = None
                    self.wander = None
                    self.door_via = None
                    self.stuck_count = 0
            elif math.hypot(me.x - sx, me.y - sy) > 3.0:
                self.stuck_count = 0
            self.stuck_check = (me.x, me.y, self.sim.time)
        return dist

    def _weapons(self):
        return [(slot, w) for slot, w in self.me.inventory.weapons()
                if w.in_mag > 0 or self.me.inventory.ammo.get(w.wdef.ammo, 0) > 0]

    def _best_weapon_for(self, dist: float):
        pref = {"shotgun": 0, "smg": 1, "assault_rifle": 2, "special": 2, "pistol": 3, "sniper": 5}
        if dist > 90:
            pref = {"sniper": 0, "special": 1, "assault_rifle": 2, "pistol": 4, "smg": 5, "shotgun": 9}
        elif dist > 30:
            pref = {"assault_rifle": 0, "special": 0, "smg": 2, "sniper": 2, "pistol": 3, "shotgun": 8}
        options = self._weapons()
        if not options:
            return None
        return min(options, key=lambda sw: (pref.get(sw[1].wdef.category, 6), -sw[1].rarity_index))

    def _heal_slot(self):
        me = self.me
        for slot, stack in me.inventory.consumables():
            cdef = self.sim.armory.consumables[stack.cid]
            if cdef.heal and me.health < min(cdef.cap, 90):
                return slot
            if cdef.shield and me.shield < cdef.cap - 10:
                return slot
        return None

    # ---------------------------------------------------------- perception
    def _scan(self) -> None:
        me = self.me
        sim = self.sim
        rng_view = self.view_range * (1.8 if any(w.wdef.category == "sniper" for _, w in self._weapons()) else 1.0)
        best, best_d = None, rng_view
        eye = me.eye
        for o in sim.combatants:
            if o is me or not o.alive or o.state in ("bus",):
                continue
            d = math.hypot(o.x - me.x, o.y - me.y)
            if d >= best_d:
                continue
            # field of view ~220 degrees, but always notice very close or recent attackers
            facing = abs(angle_diff(yaw_to(o.x - me.x, o.y - me.y), self.yaw))
            recently_hit = sim.time - me.last_damage_time < 2.0
            if facing > 110 and d > 15 and not recently_hit:
                continue
            if sim.collision.line_of_sight(eye, (o.x, o.y, o.z + 1.3)):
                best, best_d = o, d
        if best is not None:
            if self.target is not best:
                self.target_seen_at = sim.time
            self.target = best
            self.last_enemy_seen = sim.time
        elif self.target is not None and (not self.target.alive or sim.time - self.last_enemy_seen > 3.0):
            self.target = None

    def _choose_goal(self) -> None:
        me, sim = self.me, self.sim
        storm = sim.storm
        inside = storm.distance_inside(me.x, me.y)
        # 1. storm safety
        if inside < 15 or (storm.shrinking and math.hypot(me.x - storm.target_center[0], me.y - storm.target_center[1])
                           > storm.target_radius * 0.9):
            cx, cy = storm.target_center if storm.shrinking else storm.center
            tr = storm.target_radius if storm.shrinking else storm.radius
            a = math.atan2(me.y - cy, me.x - cx)
            r = tr * 0.5
            self.goal = (cx + math.cos(a) * r, cy + math.sin(a) * r, 0.0)
            self.goal_kind = "storm"
            self._set_route(self.goal)
            return
        # 2. loot nearby
        best, best_d = None, 70.0 if len(self._weapons()) < 3 else 35.0
        for k in sim.containers:
            if k.opened or k.kind == "crate" or ("container", k.id) in self.ignore:
                continue
            d = abs(k.x - me.x) + abs(k.y - me.y)
            if d >= best_d or not self._reachable(k.x, k.y, k.z):
                continue
            if d < best_d:
                best, best_d = ("container", k), d
        for it in sim.items.values():
            if it.kind == "ammo" or ("item", it.id) in self.ignore:
                continue
            if abs(it.x - me.x) + abs(it.y - me.y) >= best_d or not self._reachable(it.x, it.y, it.z):
                continue
            if it.kind == "weapon" and not self._wants_weapon(it.payload):
                continue
            if it.kind == "consumable" and me.inventory.free_slot() is None:
                continue
            d = abs(it.x - me.x) + abs(it.y - me.y)
            if d < best_d:
                best, best_d = ("item", it), d
        if best is not None:
            kind, ref = best
            self.goal = (ref.x, ref.y, ref.z)
            self.goal_kind, self.goal_ref = kind, ref
            self._set_route(self.goal)
            return
        # 3. wander toward the safe zone / a POI
        if self.wander is None or math.hypot(self.wander[0] - me.x, self.wander[1] - me.y) < 6:
            cx, cy = storm.target_center
            r = max(20.0, storm.target_radius * 0.7)
            for _ in range(10):
                a = self.rng.uniform(0, 2 * math.pi)
                d = r * math.sqrt(self.rng.random())
                x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
                if sim.terrain.is_land(x, y, 1.5):
                    self.wander = (x, y)
                    break
            else:
                self.wander = (cx, cy)
        self.goal = (self.wander[0], self.wander[1], 0.0)
        self.goal_kind = "wander"
        self._set_route(self.goal)

    # -- multi-floor navigation --------------------------------------------
    def _floor_of(self, x: float, y: float, z: float):
        """(entrance, route floor z) when (x, y, z) is on an upper floor of a building, else (None, None)."""
        for e in self.sim.layout.entrances:
            if z > e.base_z + 1.5 and e.contains(x, y, 0.5):
                for floor_z, _ in e.routes:
                    if abs(floor_z - z) < 1.3:
                        return e, floor_z
                return e, None          # upper level without a known route (roof etc.)
        return None, None

    def _plan(self, tx: float, ty: float, tz: float):
        """Waypoints to reach a target, descending/ascending building routes. None = unreachable."""
        me = self.me
        my_b, my_floor = self._floor_of(me.x, me.y, me.z)
        tg_b, tg_floor = self._floor_of(tx, ty, tz)
        if my_b is not None and my_b is tg_b and my_floor is not None and my_floor == tg_floor:
            return []                                   # same upper floor
        path = []
        if my_b is not None:
            if my_floor is None:
                return None
            pts = next(p for fz, p in my_b.routes if fz == my_floor)
            path += list(reversed(pts))                 # walk back down and out
        if tg_b is not None:
            if tg_floor is None:
                return None
            pts = next(p for fz, p in tg_b.routes if fz == tg_floor)
            path += list(pts)
        elif tz - (me.z if my_b is None else self.sim.terrain.ground(tx, ty)) > 1.6:
            return None                                 # raised spot we have no route for
        return path

    def _committed(self) -> bool:
        """Mid-route toward a still-valid loot goal: keep going (heights on stairs match no floor)."""
        if not self.route or self.goal_kind not in ("item", "container"):
            return False
        ref = self.goal_ref
        valid = (not ref.opened) if self.goal_kind == "container" else ref.id in self.sim.items
        if not valid:
            self.route = []
        return valid

    def _reachable(self, x, y, z) -> bool:
        return self._plan(x, y, z) is not None

    def _set_route(self, goal) -> None:
        key = tuple(round(v, 1) for v in goal) if goal else None
        if key == self._route_goal:
            return                      # keep progress along the current route
        self._route_goal = key
        plan = self._plan(*goal) if goal else None
        self.route = list(plan or [])
        # ground-floor interiors still go through the front door
        self.door_via = None if self.route else self._door_for(goal[0], goal[1])

    def _door_for(self, x: float, y: float):
        me = self.me
        for e in self.sim.layout.entrances:
            x0, y0, x1, y1 = e.footprint
            if x0 < x < x1 and y0 < y < y1 and not (x0 < me.x < x1 and y0 < me.y < y1):
                return e.door
        return None

    def _wants_weapon(self, w: WeaponInstance) -> bool:
        inv = self.me.inventory
        if inv.free_slot() is not None:
            return not any(o.wdef.id == w.wdef.id and o.rarity_index >= w.rarity_index for _, o in inv.weapons())
        return False

    # ---------------------------------------------------------- tick
    def think(self, dt: float) -> ControlInput:
        me, sim = self.me, self.sim
        inp = ControlInput(yaw=self.yaw, pitch=self.pitch)
        if me.state == "bus":
            ship = sim.ship
            sx, sy, _ = ship.position()
            close = math.hypot(sx - self.drop_point[0], sy - self.drop_point[1]) < 160
            if sim.ship.t > 2.6 and (close or sim.ship.t >= self.jump_at):
                inp.deploy = True
            return inp
        if me.state in ("skydive", "glide"):
            dx, dy = self.drop_point[0] - me.x, self.drop_point[1] - me.y
            self._turn_toward(yaw_to(dx, dy), -45 if me.state == "skydive" else 0, dt, 200)
            inp.yaw, inp.pitch = self.yaw, self.pitch
            inp.move_y = 1.0 if math.hypot(dx, dy) > 15 else 0.0
            inp.deploy = me.z - sim.terrain.height(me.x, me.y) < 120 and math.hypot(dx, dy) < 120
            return inp

        self.decide_timer -= dt
        if me.build_mode:
            inp.build_toggle = True             # one wall placed: back to the weapon
            return inp
        engage = self.target is not None and self.target.alive
        if engage and not self._weapons():
            # unarmed: only brawl when cornered, otherwise keep looting
            engage = math.hypot(self.target.x - me.x, self.target.y - me.y) < 6 or sim.time - me.last_damage_time < 1.5
        if self.decide_timer <= 0:
            self.decide_timer = 0.25
            self._scan()
            if not engage and not self._committed():
                self._choose_goal()
                key = (self.goal_kind, getattr(self.goal_ref, "id", None)) if self.goal_kind in ("item", "container") else None
                if key != self.goal_key:
                    self.goal_key, self.goal_since = key, sim.time
                elif key is not None and sim.time - self.goal_since > 12.0:
                    self.ignore.add(key)          # unreachable (walls, other floors): try something else
                    self.goal = None
                    self.goal_key = None
        engage = engage and self.target is not None and self.target.alive
        if engage:
            self._fight(inp, dt)
        else:
            self._peaceful(inp, dt)
        inp.yaw, inp.pitch = self.yaw, self.pitch
        return inp

    def _peaceful(self, inp: ControlInput, dt: float) -> None:
        me, sim = self.me, self.sim
        inv = me.inventory
        cur = inv.current
        # reload or heal when calm
        if isinstance(cur, WeaponInstance) and cur.in_mag < cur.wdef.magazine * 0.5 and inv.ammo.get(cur.wdef.ammo, 0):
            inp.reload = True
        heal = self._heal_slot()
        if heal is not None and sim.time - self.last_enemy_seen > 2.0 and sim.storm.distance_inside(me.x, me.y) > 5:
            if inv.selected != heal:
                inp.select = heal
            elif me.use_timer <= 0:
                inp.fire_pressed = True
            return
        if me.use_timer > 0:
            return
        best = self._best_weapon_for(40)
        if best and inv.selected != best[0] and me.reload_timer <= 0:
            inp.select = best[0]
        if self._harvest(inp, dt):
            return
        if self.goal is None:
            return
        gx, gy, _ = self.goal
        while self.route and math.hypot(self.route[0][0] - me.x, self.route[0][1] - me.y) < 0.8:
            self.route.pop(0)
        if self.route:
            self._steer(inp, self.route[0][0], self.route[0][1], dt, stop_dist=0.3)
            inp.sprint = False
            return
        if self.door_via is not None:
            if math.hypot(self.door_via[0] - me.x, self.door_via[1] - me.y) < 2.0:
                self.door_via = None
            else:
                gx, gy = self.door_via
        dist = self._steer(inp, gx, gy, dt, stop_dist=1.4 if self.goal_kind in ("item", "container") else 4.0)
        if self.goal_kind in ("item", "container") and dist < 2.2 and self.door_via is None:
            inp.move_y = 0.0
            if self.goal_kind == "container":
                inp.interact = True                   # chests need a steady hold
            else:
                self.pulse = not self.pulse           # items are one pickup per press
                inp.interact = self.pulse
            ref = self.goal_ref
            if (self.goal_kind == "container" and ref.opened) or (self.goal_kind == "item" and ref.id not in sim.items):
                self.goal = None
                self.decide_timer = 0.0
        # smash supply crates on the way
        for k in sim.containers:
            if k.kind == "crate" and not k.opened and abs(k.x - me.x) < 2.6 and abs(k.y - me.y) < 2.6:
                self._turn_toward(yaw_to(k.x - me.x, k.y - me.y), -20, dt, 720)
                inp.select = 0
                inp.fire = inp.fire_pressed = True
                inp.move_y = 0.0
                break

    def _harvest(self, inp: ControlInput, dt: float) -> bool:
        """Low on building materials and nothing better to do: chop a nearby tree or rock."""
        from game import building as B
        me, sim = self.me, self.sim
        if sum(me.materials.values()) >= 90 or self.goal_kind in ("item", "container", "storm"):
            self.harvest_target = None
            return False
        if self.harvest_target is None:
            best, bd = None, 9.0
            for b in sim.collision.query(me.x - 9, me.y - 9, me.x + 9, me.y + 9):
                if b.tag in B.HARVEST and b.tag.startswith(("env_tree", "env_rock")) and b.z0 < me.z + 1.5:
                    cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
                    d = math.hypot(cx - me.x, cy - me.y)
                    if d < bd:
                        best, bd = (cx, cy, max(b.x1 - b.x0, b.y1 - b.y0) / 2), d
            if best is None:
                return False
            self.harvest_target = (best, sim.time)
        (tx, ty, r), since = self.harvest_target
        if sim.time - since > 10:
            self.harvest_target = None
            return False
        d = self._steer(inp, tx, ty, dt, stop_dist=r + 1.3)
        if d <= r + 1.4:
            inp.move_y = 0.0
            self._turn_toward(yaw_to(tx - me.x, ty - me.y), -10, dt, 720)
            inp.select = 0 if me.inventory.selected != 0 else None
            inp.fire = True
        return True

    def _fight(self, inp: ControlInput, dt: float) -> None:
        me, sim, t = self.me, self.sim, self.target
        dx, dy = t.x - me.x, t.y - me.y
        dist = math.hypot(dx, dy)
        eye = me.eye
        aim_z = t.z + (0.9 if t.crouching else 1.25)
        want_yaw = yaw_to(dx, dy)
        want_pitch = math.degrees(math.atan2(aim_z - eye[2], max(0.1, dist)))
        self.err_timer -= dt
        if self.err_timer <= 0:
            moving = math.hypot(t.vx, t.vy)
            sigma = self.aim_error * (1 + moving * 0.12) * (1 + max(0, dist - 40) / 120)
            self.err = (self.rng.gauss(0, sigma), self.rng.gauss(0, sigma * 0.6))
            self.err_timer = self.rng.uniform(0.25, 0.5)
        self._turn_toward(want_yaw + self.err[0], want_pitch + self.err[1], dt, 300)

        # weapon choice
        best = self._best_weapon_for(dist)
        inv = me.inventory
        if best is None:
            inp.select = 0
            if dist > 3:
                self._steer(inp, t.x, t.y, dt, 1.5)
        elif inv.selected != best[0] and me.reload_timer <= 0 and me.fire_cooldown <= 0:
            inp.select = best[0]
        cur = inv.current
        from game import building as B
        mats = me.materials
        if sim.time - me.last_damage_time < 0.5 and sim.time - self.last_build > 2.5 and dist > 5 \
                and max(mats.values()) >= B.COST and self.rng.random() < 0.35:
            self.last_build = sim.time
            me.build_material = max(mats, key=mats.get)
            inp.build_toggle = True
            inp.build_piece = "wall"
            inp.fire_pressed = True
            inp.yaw, inp.pitch = want_yaw, 0.0
            return
        on_target = abs(angle_diff(want_yaw, self.yaw)) < 12 + self.aim_error and dist < self.view_range * 2
        ready = sim.time - self.target_seen_at > self.reaction
        if ready and on_target:
            if cur is None:
                if dist < 2.6:
                    inp.fire = inp.fire_pressed = True
            elif isinstance(cur, WeaponInstance):
                inp.aim = dist > 22
                if cur.in_mag == 0:
                    inp.reload = True
                elif cur.wdef.automatic:
                    inp.fire = self.rng.random() < self.discipline
                elif me.fire_cooldown <= 0:
                    inp.fire_pressed = self.rng.random() < self.discipline
            elif isinstance(cur, ConsumableStack):
                inp.select = best[0] if best else 0
        # movement: strafe and keep a preferred distance
        self.strafe_timer -= dt
        if self.strafe_timer <= 0:
            self.strafe = self.rng.choice((-1, 1))
            self.strafe_timer = self.rng.uniform(0.6, 1.8)
            if self.rng.random() < 0.15 and me.on_ground:
                inp.jump = True
        cat = cur.wdef.category if isinstance(cur, WeaponInstance) else "melee"
        preferred = {"shotgun": 6, "smg": 14, "melee": 1.5, "pistol": 18, "assault_rifle": 28, "special": 30,
                     "sniper": 70}.get(cat, 25)
        inp.move_x = self.strafe * 0.8
        inp.move_y = 0.8 if dist > preferred * 1.3 else (-0.6 if dist < preferred * 0.6 else 0.0)
        inp.crouch = cat == "sniper" and dist > 60
        if sim.storm.distance_inside(me.x, me.y) < 5:
            cx, cy = sim.storm.center
            fwd = math.cos(math.radians(yaw_to(cx - me.x, cy - me.y) - self.yaw))
            inp.move_y = 1.0 if fwd > 0 else -1.0
            inp.crouch = False
