"""The match simulation. Pure logic: no pygame, deterministic for a given seed.

The battle scene feeds player input through an Intent, steps the world at a fixed rate
and reads `events` to drive sounds, particles and screen shake.
"""
import math
import random

from ilbrawl.abilities import supers
from ilbrawl.ai.bot import BotController
from ilbrawl.combat import attacks
from ilbrawl.combat import damage as dmg
from ilbrawl.config import TILE
from ilbrawl.gameplay.entities import Brawler, Deployable, Intent, Orb, Pickup, Projectile
from ilbrawl.maps.tilemap import POWERBOX, TileMap
from ilbrawl.modes import create_mode

REGEN_DELAY = 3.0
REGEN_RATE = 0.13


class World:
    def __init__(self, gd, map_def, mode_id, participants, difficulty="normal", seed=None,
                 ally_difficulty=None):
        self.gd = gd
        self.rng = random.Random(seed)
        self.map = TileMap(map_def)
        self.mode_id = mode_id
        self.mode_cfg = gd.modes[mode_id]
        self.time = 0.0
        self.state = "countdown"
        self.countdown = 3.0
        self.events = []
        self.brawlers = []
        self.projectiles = []
        self.deployables = []
        self.areas = []
        self.pickups = []
        self.orb = None
        self.player = None
        self.result = None
        self.difficulty = difficulty
        for p in participants:
            cdef = gd.characters[p["char"]]
            b = Brawler(cdef, p.get("level", 1), p["team"], p["name"], p.get("is_player", False), p.get("skin"),
                        gd.level_bonus)
            if p.get("skin"):
                b.style = gd.skin_style(p["char"], p["skin"])
            if b.is_player:
                self.player = b
            else:
                diff = difficulty if (ally_difficulty is None or self.player is None or b.team != self.player.team) \
                    else ally_difficulty
                b.controller = BotController(self, b, diff, self.rng.random())
            self.brawlers.append(b)
        self.mode = create_mode(mode_id, self, self.mode_cfg)
        self.mode.setup()
        for b in self.brawlers:
            x, y = self.mode.spawn_point(b)
            b.reset_for_spawn(x, y)
            b.spawn_protect = 0.0
            b.facing = 0.0 if x < self.map.pw / 2 else math.pi

    # ------------------------------------------------------------ helpers
    def emit(self, ev, **data):
        data["ev"] = ev
        self.events.append(data)

    def pop_events(self):
        ev, self.events = self.events, []
        return ev

    def add_projectile(self, p):
        self.projectiles.append(p)

    def add_area(self, a):
        self.areas.append(a)

    def add_deployable(self, d):
        self.deployables.append(d)

    def enemies_of(self, b):
        return [o for o in self.brawlers if o.alive and o.team != b.team]

    def allies_of(self, b, include_self=False):
        return [o for o in self.brawlers if o.alive and o.team == b.team and (include_self or o is not b)]

    def damageable_enemies(self, team):
        out = [o for o in self.brawlers if o.alive and o.team != team]
        out += [d for d in self.deployables if d.alive and d.team != team]
        return out

    def is_hidden_from(self, target, team):
        """True when target can't be seen by `team` (bushes / stealth)."""
        if target.team == team:
            return False
        if isinstance(target, Brawler):
            if target.invis_t > 0:
                return not any(o.alive and o.team == team and math.hypot(o.x - target.x, o.y - target.y) < TILE * 1.3
                               for o in self.brawlers)
            if target.reveal_t > 0:
                return False
            if self.map.is_bush_at(target.x, target.y):
                return not any(o.alive and o.team == team and math.hypot(o.x - target.x, o.y - target.y) < TILE * 2.4
                               for o in self.brawlers)
        return False

    def knock(self, target, nx, ny, force):
        if hasattr(target, "kx") and target.alive:
            target.kx += nx * force
            target.ky += ny * force

    def hit_tile(self, tx, ty, amount):
        old = self.map.damage_tile(tx, ty, amount)
        if old:
            cx, cy = (tx + 0.5) * TILE, (ty + 0.5) * TILE
            self.emit("tile_break", x=cx, y=cy, tile=old, tx=tx, ty=ty)
            if old == POWERBOX:
                self.pickups.append(Pickup("cube", cx, cy, 0, 0, 0.3))
        return old

    def explode(self, src, x, y, radius, damage, color, charge=0.0, heal=0.0, is_super=False):
        team = src.team
        for t in self.damageable_enemies(team):
            if math.hypot(t.x - x, t.y - y) <= radius + t.radius:
                dmg.apply_damage(self, src, t, damage, charge)
        if heal:
            for a in self.brawlers:
                if a.alive and a.team == team and math.hypot(a.x - x, a.y - y) <= radius + a.radius:
                    dmg.apply_heal(self, src, a, heal, charge * 0.5 if a is not src else 0)
        dmg.damage_tiles_in_radius(self, x, y, radius * 0.75, damage * (1.5 if is_super else 1.0))
        self.emit("explosion", x=x, y=y, radius=radius, color=color, heal=bool(heal), big=is_super)

    # ------------------------------------------------------------ goal rush orb
    def spawn_orb(self, x, y):
        self.orb = Orb(x, y)

    def throw_orb(self, b, tx, ty):
        o = self.orb
        if o is None or o.carrier is not b:
            return
        a = math.atan2(ty - b.y, tx - b.x)
        b.carrying_orb = False
        o.carrier = None
        o.x, o.y = b.x + math.cos(a) * 26, b.y + math.sin(a) * 26
        o.vx, o.vy = math.cos(a) * 820, math.sin(a) * 820
        o.block_id, o.block_t = b.id, 0.45
        b.facing = a
        self.emit("throw", x=b.x, y=b.y, who=b)

    def drop_orb(self, b):
        o = self.orb
        if o and o.carrier is b:
            o.carrier = None
            b.carrying_orb = False
            o.x, o.y = b.x, b.y
            o.vx, o.vy = self.rng.uniform(-80, 80), self.rng.uniform(-80, 80)
            o.block_id, o.block_t = b.id, 0.6

    def _update_orb(self, dt):
        o = self.orb
        if o is None:
            return
        o.block_t = max(0.0, o.block_t - dt)
        if o.carrier:
            if not o.carrier.alive:
                self.drop_orb(o.carrier)
            else:
                o.x, o.y = o.carrier.x, o.carrier.y
                return
        if o.vx or o.vy:
            steps = 3
            for _ in range(steps):
                nx, ny = o.x + o.vx * dt / steps, o.y + o.vy * dt / steps
                if self.map.point_shot_blocked(nx, o.y) or not (0 < nx < self.map.pw):
                    o.vx = -o.vx * 0.7
                    nx = o.x
                if self.map.point_shot_blocked(nx, ny) or not (0 < ny < self.map.ph):
                    o.vy = -o.vy * 0.7
                    ny = o.y
                o.x, o.y = nx, ny
            f = max(0.0, 1 - 1.8 * dt)
            o.vx *= f
            o.vy *= f
            if math.hypot(o.vx, o.vy) < 12:
                o.vx = o.vy = 0.0
        for b in self.brawlers:
            if not b.alive or b.stun_t > 0:
                continue
            if o.block_t > 0 and b.id == o.block_id:
                continue
            if math.hypot(b.x - o.x, b.y - o.y) < b.radius + o.radius:
                o.carrier = b
                b.carrying_orb = True
                o.vx = o.vy = 0.0
                self.emit("pickup", x=o.x, y=o.y, item="orb", who=b)
                break

    # ------------------------------------------------------------ main update
    def update(self, dt, player_intent=None):
        if self.state == "over":
            return
        if self.state == "countdown":
            self.countdown -= dt
            if self.countdown <= 0:
                self.state = "play"
                self.emit("go")
            return
        self.time += dt
        self.map.update(dt)
        intents = {}
        for b in self.brawlers:
            if not b.alive:
                continue
            if b.is_player:
                intents[b.id] = player_intent or Intent()
            elif b.controller:
                intents[b.id] = b.controller.think(dt)
        for b in self.brawlers:
            self._update_brawler(b, dt, intents.get(b.id))
        self._update_projectiles(dt)
        self._update_deployables(dt)
        for a in self.areas:
            supers.update_area(self, a, dt)
        self.areas = [a for a in self.areas if a.alive]
        self._update_pickups(dt)
        self._update_orb(dt)
        self.mode.update(dt)
        res = self.mode.check_end()
        if res is not None:
            self.state = "over"
            self.result = res
            self.emit("match_over", result=res)

    def _update_brawler(self, b, dt, intent):
        if not b.alive:
            if b.respawn_timer is not None and self.mode.allow_respawn():
                b.respawn_timer -= dt
                if b.respawn_timer <= 0:
                    x, y = self.mode.spawn_point(b)
                    b.reset_for_spawn(x, y)
                    self.emit("respawn", x=x, y=y, who=b)
            return
        # timers
        b.attack_cd = max(0.0, b.attack_cd - dt)
        b.since_hurt += dt
        b.since_attack += dt
        b.reveal_t = max(0.0, b.reveal_t - dt)
        b.hit_flash = max(0.0, b.hit_flash - dt)
        b.attack_anim = max(0.0, b.attack_anim - dt)
        b.spawn_protect = max(0.0, b.spawn_protect - dt)
        for attr in ("slow_t", "stun_t", "shield_t", "invis_t", "rage_t"):
            v = getattr(b, attr)
            if v > 0:
                setattr(b, attr, max(0.0, v - dt))
        if b.slow_t <= 0:
            b.slow_amt = 0.0
        # reload one ammo bar at a time
        if b.ammo < b.ammo_max:
            b.ammo = min(float(b.ammo_max), b.ammo + dt * b.reload_mult / b.reload_time)
        # regeneration out of combat
        if b.since_hurt > REGEN_DELAY and b.since_attack > REGEN_DELAY and b.hp < b.max_hp:
            b.hp = min(b.max_hp, b.hp + b.max_hp * REGEN_RATE * dt)
        # pending burst shots
        if b.burst:
            for shot in b.burst:
                shot[0] -= dt
            for shot in [s for s in b.burst if s[0] <= 0]:
                attacks.fire_burst_shot(self, b, shot[1], shot[2])
            b.burst = [s for s in b.burst if s[0] > 0]
        ox, oy = b.x, b.y
        if b.dash is not None:
            self._update_dash(b, dt)
        elif b.stun_t <= 0 and intent is not None:
            mx, my = intent.mx, intent.my
            m = math.hypot(mx, my)
            if m > 1:
                mx, my = mx / m, my / m
            sp = b.move_speed
            b.x += mx * sp * dt
            b.y += my * sp * dt
            if m > 0.1:
                b.walk_phase += dt * 10
            # aim / actions
            if intent.ax or intent.ay:
                b.facing = math.atan2(intent.ay - b.y, intent.ax - b.x)
            elif m > 0.1:
                b.facing = math.atan2(my, mx)
            if intent.attack:
                tx, ty = intent.ax, intent.ay
                if intent.autoaim:
                    tgt = self.auto_target(b)
                    if tgt is not None:
                        tx, ty = tgt.x, tgt.y
                attacks.fire(self, b, tx, ty)
            if intent.super:
                tx, ty = intent.ax, intent.ay
                if intent.autoaim:
                    tgt = self.auto_target(b, super_range=True)
                    if tgt is not None:
                        tx, ty = tgt.x, tgt.y
                supers.activate(self, b, tx, ty)
        # knockback
        if b.kx or b.ky:
            b.x += b.kx * dt
            b.y += b.ky * dt
            f = max(0.0, 1 - 7 * dt)
            b.kx *= f
            b.ky *= f
            if abs(b.kx) + abs(b.ky) < 5:
                b.kx = b.ky = 0.0
        b.x, b.y = self.map.resolve_circle(b.x, b.y, b.radius)
        if dt > 0:
            b.vx = (b.x - ox) / dt
            b.vy = (b.y - oy) / dt

    def _update_dash(self, b, dt):
        d = b.dash
        step = min(d["left"], d["speed"] * dt)
        nx, ny = b.x + d["dx"] * step, b.y + d["dy"] * step
        tx, ty = self.map.to_tile(nx + d["dx"] * b.radius, ny + d["dy"] * b.radius)
        if self.map.walk_blocked(tx, ty):
            # smash breakable cover, stop at walls
            if self.hit_tile(tx, ty, d["damage"] * 2) is None:
                d["left"] = 0
        b.x, b.y = nx, ny
        d["left"] -= step
        for t in self.damageable_enemies(b.team):
            if t.id in d["hit"]:
                continue
            if math.hypot(t.x - b.x, t.y - b.y) < t.radius + b.radius + 8:
                d["hit"].add(t.id)
                dmg.apply_damage(self, b, t, d["damage"])
                self.knock(t, d["dx"], d["dy"], d["knock"])
        if d["left"] <= 0:
            b.dash = None

    def auto_target(self, b, super_range=False):
        rng = (supers.super_range_tiles(b.sup) * TILE) if super_range else b.attack_range_px
        best, bd = None, rng + TILE
        for t in self.damageable_enemies(b.team):
            if self.is_hidden_from(t, b.team):
                continue
            d = math.hypot(t.x - b.x, t.y - b.y)
            if d < bd:
                best, bd = t, d
        return best

    def _update_projectiles(self, dt):
        tm = self.map
        for p in self.projectiles:
            if not p.alive:
                continue
            p.age += dt
            if p.lob is not None:
                L = p.lob
                L["t"] += dt / L["dur"]
                t = min(1.0, L["t"])
                p.x = L["sx"] + (L["tx"] - L["sx"]) * t
                p.y = L["sy"] + (L["ty"] - L["sy"]) * t
                if L["t"] >= 1.0:
                    p.alive = False
                    self.explode(p.owner, p.x, p.y, p.explode_radius, p.damage, p.color, p.charge, p.heal, p.is_super)
                continue
            if p.returning:
                o = p.owner
                if not o.alive:
                    p.alive = False
                    continue
                dx, dy = o.x - p.x, o.y - p.y
                d = math.hypot(dx, dy)
                if d < o.radius:
                    p.alive = False
                    continue
                p.vx, p.vy = dx / d * p.speed, dy / d * p.speed
            dist = p.speed * dt
            steps = max(1, int(dist / 12) + 1)
            for _ in range(steps):
                if not p.alive:
                    break
                sx, sy = p.vx * dt / steps, p.vy * dt / steps
                nx, ny = p.x + sx, p.y + sy
                if not p.returning and tm.point_shot_blocked(nx, ny):
                    tx, ty = tm.to_tile(nx, ny)
                    if p.breaks_tiles:
                        self.hit_tile(tx, ty, p.damage)
                    if p.bounces > 0:
                        p.bounces -= 1
                        p.hit = set()
                        if tm.point_shot_blocked(nx, p.y):
                            p.vx = -p.vx
                        if tm.point_shot_blocked(p.x, ny):
                            p.vy = -p.vy
                        self.emit("bounce", x=p.x, y=p.y)
                        continue
                    if p.boomerang and not p.returning:
                        p.returning = True
                        p.hit = set()
                        continue
                    p.alive = False
                    self.emit("impact", x=nx, y=ny, color=p.color)
                    break
                p.x, p.y = nx, ny
                p.travelled += math.hypot(sx, sy)
                self._projectile_hits(p)
            if p.alive and not p.returning and p.travelled >= p.max_range:
                if p.boomerang:
                    p.returning = True
                    p.hit = set()
                else:
                    p.alive = False
                    if p.shape in ("bolt", "beam", "star", "orb"):
                        self.emit("fizzle", x=p.x, y=p.y, color=p.color)
        self.projectiles = [p for p in self.projectiles if p.alive]

    def _projectile_hits(self, p):
        for t in self.damageable_enemies(p.team):
            if t.id in p.hit:
                continue
            if (t.x - p.x) ** 2 + (t.y - p.y) ** 2 <= (t.radius + p.radius) ** 2:
                p.hit.add(t.id)
                dmg.apply_damage(self, p.owner, t, p.damage, 0.0 if p.is_super else p.charge)
                if hasattr(t, "slow_t"):
                    if p.slow:
                        t.slow_t = max(t.slow_t, p.slow)
                        t.slow_amt = max(t.slow_amt, 0.35)
                    if p.stun:
                        t.stun_t = max(t.stun_t, p.stun)
                        t.dash = None
                if p.knockback:
                    sp = math.hypot(p.vx, p.vy) or 1
                    self.knock(t, p.vx / sp, p.vy / sp, p.knockback)
                self.emit("impact", x=p.x, y=p.y, color=p.color, hit=True)
                if not p.pierce:
                    p.alive = False
                    return
        if p.heal:
            for a in self.brawlers:
                if a.alive and a.team == p.team and a is not p.owner and a.id not in p.hit:
                    if (a.x - p.x) ** 2 + (a.y - p.y) ** 2 <= (a.radius + p.radius) ** 2:
                        p.hit.add(a.id)
                        dmg.apply_heal(self, p.owner, a, p.heal, p.charge)

    def _update_deployables(self, dt):
        for d in self.deployables:
            if not d.alive:
                continue
            d.life -= dt
            d.timer += dt
            d.hit_flash = max(0.0, d.hit_flash - dt)
            if d.life <= 0 or not d.owner.alive and d.kind == "decoy":
                d.alive = False
                self.emit("destroyed", x=d.x, y=d.y, obj=d)
                continue
            s = d.spec
            if d.kind == "turret":
                if d.timer >= s.get("fire_rate", 0.5):
                    tgt = self._nearest_visible_enemy(d, s.get("attack_range", 7) * TILE)
                    if tgt:
                        d.timer = 0.0
                        a = math.atan2(tgt.y - d.y, tgt.x - d.x)
                        d.facing = a
                        spec = {"type": "single", "speed": 900, "range": s.get("attack_range", 7), "radius": 6,
                                "color": s.get("color", (255, 220, 60)), "shape": "bolt"}
                        p = Projectile(d.owner, d.x, d.y, a, spec, s["damage"] * d.level_mult)
                        self.add_projectile(p)
                        self.emit("shot", x=d.x, y=d.y, angle=a, who=d, sound="shoot", color=spec["color"], quiet=True)
            elif d.kind == "totem":
                for a in self.brawlers:
                    if a.alive and a.team == d.team and math.hypot(a.x - d.x, a.y - d.y) <= s.get("heal_radius", 3) * TILE:
                        dmg.apply_heal(self, d.owner, a, s["heal_per_sec"] * d.level_mult * dt)
            elif d.kind == "decoy":
                if d.timer >= 1.0:
                    tgt = self._nearest_visible_enemy(d, d.owner.attack_range_px)
                    if tgt:
                        d.timer = 0.0
                        a = math.atan2(tgt.y - d.y, tgt.x - d.x)
                        d.facing = a
                        spec = d.owner.attack
                        p = Projectile(d.owner, d.x, d.y, a, spec, spec["damage"] * d.level_mult * s.get("damage_mult", 0.5))
                        p.heal = 0
                        self.add_projectile(p)
                        self.emit("shot", x=d.x, y=d.y, angle=a, who=d, sound="laser", color=spec.get("color"), quiet=True)
        self.deployables = [d for d in self.deployables if d.alive]

    def _nearest_visible_enemy(self, src, rng):
        best, bd = None, rng
        for t in self.brawlers:
            if not t.alive or t.team == src.team or self.is_hidden_from(t, src.team):
                continue
            d = math.hypot(t.x - src.x, t.y - src.y)
            if d < bd and self.map.line_clear(src.x, src.y, t.x, t.y):
                best, bd = t, d
        return best

    def _update_pickups(self, dt):
        tm = self.map
        for pk in self.pickups:
            pk.age += dt
            pk.delay = max(0.0, pk.delay - dt)
            if pk.vx or pk.vy:
                nx, ny = pk.x + pk.vx * dt, pk.y + pk.vy * dt
                if not tm.walk_blocked(*tm.to_tile(nx, ny)):
                    pk.x, pk.y = nx, ny
                else:
                    pk.vx = pk.vy = 0
                f = max(0.0, 1 - 4 * dt)
                pk.vx *= f
                pk.vy *= f
                if abs(pk.vx) + abs(pk.vy) < 4:
                    pk.vx = pk.vy = 0.0
            if pk.delay > 0:
                continue
            for b in self.brawlers:
                if b.alive and math.hypot(b.x - pk.x, b.y - pk.y) < b.radius + 14:
                    pk.alive = False
                    if pk.kind == "gem":
                        b.gems += 1
                        b.stats.gems += 1
                    elif pk.kind == "cube":
                        b.add_cube()
                    self.emit("pickup", x=pk.x, y=pk.y, item=pk.kind, who=b)
                    break
        self.pickups = [p for p in self.pickups if p.alive]

    def scatter(self, kind, x, y, n, speed=160):
        for _ in range(n):
            a = self.rng.uniform(0, 2 * math.pi)
            s = self.rng.uniform(speed * 0.4, speed)
            self.pickups.append(Pickup(kind, x, y, math.cos(a) * s, math.sin(a) * s, 0.5))

    def reset_round(self):
        """Used between rounds / after goals: everybody back to spawn, field cleared."""
        self.projectiles = []
        self.areas = []
        self.deployables = []
        self.map.temp_walls.clear()
        for b in self.brawlers:
            x, y = self.mode.spawn_point(b)
            b.reset_for_spawn(x, y)
            b.spawn_protect = 0.5
            b.super_charge = b.super_charge
            if b.controller:
                b.controller.reset()
        if self.orb:
            self.orb.reset()

    # ------------------------------------------------------------ results
    def build_result(self):
        res = self.result or {}
        p = self.player
        outcome = res.get("outcome", {}).get(p.team, "draw") if p else "draw"
        board = []
        for b in self.brawlers:
            board.append({"name": b.name, "char": b.char_id, "team": b.team, "is_player": b.is_player,
                          "kills": b.stats.kills, "deaths": b.stats.deaths, "damage": int(b.stats.damage),
                          "healing": int(b.stats.healing), "score": self.mode.score_of(b),
                          "rank": res.get("ranks", {}).get(b.id)})
        return {
            "mode": self.mode_id, "map": self.map.id, "outcome": outcome,
            "rank": res.get("ranks", {}).get(p.id) if p and self.mode_id == "solo_survival" else None,
            "char": p.char_id if p else None, "player": p.stats.as_dict() if p else {},
            "scoreboard": board, "duration": self.time, "score_text": self.mode.final_score_text(),
        }
