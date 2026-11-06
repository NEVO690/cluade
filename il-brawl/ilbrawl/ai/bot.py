"""AI controller for bots (opponents and teammates).

Each tick the bot perceives the world (respecting bushes/stealth), picks a target and an
objective position based on the game mode, then produces an Intent: movement with path
following and strafing, projectile dodging, predictive aiming and situational supers.
"""
import math
import random

from ilbrawl.abilities.supers import super_range_tiles
from ilbrawl.ai.pathfinding import astar
from ilbrawl.config import TILE
from ilbrawl.gameplay.entities import Brawler, Intent

DIFFICULTY = {
    "easy":   {"reaction": 0.55, "aim_err": 0.30, "dodge": 0.10, "fire": 0.45, "lead": 0.0, "super": 0.45,
               "retreat": 0.18, "aggro": 0.8, "strafe": 0.3},
    "normal": {"reaction": 0.33, "aim_err": 0.15, "dodge": 0.35, "fire": 0.75, "lead": 0.5, "super": 0.8,
               "retreat": 0.28, "aggro": 1.0, "strafe": 0.6},
    "hard":   {"reaction": 0.2, "aim_err": 0.07, "dodge": 0.65, "fire": 0.95, "lead": 0.85, "super": 0.95,
               "retreat": 0.33, "aggro": 1.1, "strafe": 0.85},
    "expert": {"reaction": 0.1, "aim_err": 0.025, "dodge": 0.9, "fire": 1.0, "lead": 1.0, "super": 1.0,
               "retreat": 0.38, "aggro": 1.2, "strafe": 1.0},
}


class BotController:
    def __init__(self, world, me, difficulty="normal", seed=0.0):
        self.world = world
        self.me = me
        self.p = DIFFICULTY.get(difficulty, DIFFICULTY["normal"])
        self.rng = random.Random(seed + me.id * 7.31)
        self.reset()

    def reset(self):
        self.decide_t = 0.0
        self.target = None
        self.goal = None
        self.path = []
        self.path_goal = None
        self.path_t = 0.0
        self.dodge_vec = None
        self.dodge_t = 0.0
        self.fire_t = 0.0
        self.strafe_dir = 1 if self.rng.random() < 0.5 else -1
        self.strafe_t = 0.0
        self.stuck_t = 0.0
        self.last_pos = None
        self.role_offset = self.rng.uniform(-1, 1)
        self.mode_state = "objective"
        self.box_target = None

    # ------------------------------------------------------------ perception
    def visible_enemies(self):
        w, me = self.world, self.me
        out = []
        for o in w.damageable_enemies(me.team):
            if isinstance(o, Brawler) and w.is_hidden_from(o, me.team):
                continue
            out.append(o)
        return out

    def _pick_target(self, enemies):
        me = self.me
        rng = (me.attack_range_px + TILE * 3) * self.p["aggro"]
        best, score = None, 1e9
        for e in enemies:
            d = math.hypot(e.x - me.x, e.y - me.y)
            if d > rng:
                continue
            s = d - (1 - e.hp_frac) * TILE * 3
            if not isinstance(e, Brawler):
                s += TILE * (0 if e.kind == "decoy" else 3)
            if e is self.target:
                s -= TILE  # stickiness
            if s < score:
                best, score = e, s
        return best

    # ------------------------------------------------------------ objectives
    def _objective(self, enemies):
        w, me = self.world, self.me
        mode = w.mode_id
        tm = w.map
        home = w.mode.spawn_point(me)
        if me.hp_frac < self.p["retreat"] and any(math.hypot(e.x - me.x, e.y - me.y) < TILE * 6 for e in enemies):
            self.mode_state = "retreat"
            return self._retreat_point(enemies, home)
        self.mode_state = "objective"
        if mode == "gem_collection":
            m = w.mode
            my_gems = m.team_gems(me.team)
            carriers = sorted([b for b in w.allies_of(me, True)], key=lambda b: -b.gems)
            if me.gems >= 3 and carriers and carriers[0] is me and (my_gems >= m.to_win - 2 or me.gems >= 6):
                self.mode_state = "carry"
                return self._safe_point(home, enemies)
            gems = [p for p in w.pickups if p.kind == "gem"]
            if gems:
                g = min(gems, key=lambda p: math.hypot(p.x - me.x, p.y - me.y) + self._enemy_near_penalty(p, enemies))
                return (g.x, g.y)
            mx, my = m.mines[0]
            side = -1 if home[0] < tm.pw / 2 else 1
            return (mx + side * TILE * 2.2, my + self.role_offset * TILE * 2)
        if mode == "solo_survival":
            m = w.mode
            cubes = [p for p in w.pickups if p.kind == "cube"]
            if cubes:
                c = min(cubes, key=lambda p: math.hypot(p.x - me.x, p.y - me.y))
                if math.hypot(c.x - me.x, c.y - me.y) < TILE * 9:
                    return (c.x, c.y)
            cx, cy = tm.pw / 2, tm.ph / 2
            s = m.safe
            margin = TILE * 1.5
            if not (s[0] + margin < me.x < s[2] - margin and s[1] + margin < me.y < s[3] - margin):
                return (cx + self.role_offset * TILE, cy)
            if not enemies or self.target is None:
                box = self._nearest_box()
                if box:
                    self.box_target = box
                    bx, by = (box[0] + 0.5) * TILE, (box[1] + 0.5) * TILE
                    return (bx - TILE * 1.5 if me.x < bx else bx + TILE * 1.5, by)
            alive = [b for b in w.brawlers if b.alive and b is not me]
            if alive:
                t = min(alive, key=lambda b: math.hypot(b.x - me.x, b.y - me.y))
                return (t.x, t.y)
            return (cx, cy)
        if mode == "team_survival":
            alive_e = [b for b in w.brawlers if b.alive and b.team != me.team]
            allies = w.allies_of(me)
            if alive_e:
                t = min(alive_e, key=lambda b: math.hypot(b.x - me.x, b.y - me.y))
                if allies and me.hp_frac < 0.6:
                    ax = sum(a.x for a in allies) / len(allies)
                    ay = sum(a.y for a in allies) / len(allies)
                    return ((ax + t.x) / 2, (ay + t.y) / 2)
                return (t.x, t.y)
            return (tm.pw / 2, tm.ph / 2)
        if mode == "goal_rush":
            o = w.orb
            goal_tiles = tm.goals["R" if me.team == 0 else "A"]
            if goal_tiles:
                gx = sum(t[0] for t in goal_tiles) / len(goal_tiles)
                gy = sum(t[1] for t in goal_tiles) / len(goal_tiles)
                goal_pt = ((gx + 0.5) * TILE, (gy + 0.5) * TILE)
            else:
                goal_pt = (tm.pw if me.team == 0 else 0, tm.ph / 2)
            if o.carrier is me:
                self.mode_state = "carry"
                return goal_pt
            if o.carrier is None:
                mates = [b for b in w.allies_of(me, True)]
                closest = min(mates, key=lambda b: math.hypot(b.x - o.x, b.y - o.y))
                if closest is me or math.hypot(me.x - o.x, me.y - o.y) < TILE * 3:
                    return (o.x, o.y)
                return ((o.x + goal_pt[0]) / 2, o.y + self.role_offset * TILE * 3)
            if o.carrier.team == me.team:
                c = o.carrier
                return (c.x + (goal_pt[0] - c.x) * 0.35, c.y + self.role_offset * TILE * 2)
            self.target = o.carrier
            return (o.carrier.x, o.carrier.y)
        if mode == "zone_control":
            zones = w.mode.zones
            mine = [z for z in zones if z.owner == me.team and not z.contested]
            want = [z for z in zones if z.owner != me.team or z.contested]
            pool = want or mine or zones
            z = min(pool, key=lambda z: math.hypot(z.x - me.x, z.y - me.y) + self.role_offset * TILE * 2)
            ang = self.role_offset * math.pi
            return (z.x + math.cos(ang) * z.radius * 0.45, z.y + math.sin(ang) * z.radius * 0.45)
        return (tm.pw / 2, tm.ph / 2)

    def _enemy_near_penalty(self, p, enemies):
        return sum(TILE * 3 for e in enemies if math.hypot(e.x - p.x, e.y - p.y) < TILE * 3)

    def _nearest_box(self):
        tm, me = self.world.map, self.me
        best, bd = None, TILE * 12
        mt = tm.to_tile(me.x, me.y)
        for (tx, ty) in tm.hp:
            if tm.grid[ty][tx] != "P":
                continue
            d = math.hypot(tx - mt[0], ty - mt[1]) * TILE
            if d < bd:
                best, bd = (tx, ty), d
        return best

    def _retreat_point(self, enemies, home):
        me = self.me
        ex = sum(e.x for e in enemies) / max(1, len(enemies)) if enemies else me.x
        ey = sum(e.y for e in enemies) / max(1, len(enemies)) if enemies else me.y
        dx, dy = me.x - ex, me.y - ey
        d = math.hypot(dx, dy) or 1
        px, py = me.x + dx / d * TILE * 4, me.y + dy / d * TILE * 4
        return ((px + home[0]) / 2, (py + home[1]) / 2)

    def _safe_point(self, home, enemies):
        return (home[0] + (self.world.map.pw / 2 - home[0]) * 0.2, home[1] + self.role_offset * TILE * 2)

    # ------------------------------------------------------------ movement
    def _steer_to(self, gx, gy, dt):
        w, me = self.world, self.me
        tm = w.map
        d = math.hypot(gx - me.x, gy - me.y)
        if d < 10:
            return 0.0, 0.0
        if self._walk_clear(me.x, me.y, gx, gy):
            self.path = []
            return (gx - me.x) / d, (gy - me.y) / d
        goal_t = tm.to_tile(gx, gy)
        self.path_t -= dt
        if self.path_goal != goal_t or self.path_t <= 0 or not self.path:
            self.path = astar(tm, tm.to_tile(me.x, me.y), goal_t)
            self.path_goal = goal_t
            self.path_t = 0.6
            if self.path and self.path[0] == tm.to_tile(me.x, me.y):
                self.path.pop(0)
        while self.path:
            tx, ty = self.path[0]
            wx, wy = (tx + 0.5) * TILE, (ty + 0.5) * TILE
            if math.hypot(wx - me.x, wy - me.y) < TILE * 0.35:
                self.path.pop(0)
                continue
            # skip ahead when the next waypoint is directly reachable
            if len(self.path) > 1:
                nx, ny = (self.path[1][0] + 0.5) * TILE, (self.path[1][1] + 0.5) * TILE
                if self._walk_clear(me.x, me.y, nx, ny):
                    self.path.pop(0)
                    continue
            dd = math.hypot(wx - me.x, wy - me.y)
            return (wx - me.x) / dd, (wy - me.y) / dd
        return (gx - me.x) / d, (gy - me.y) / d

    def _walk_clear(self, x0, y0, x1, y1):
        tm = self.world.map
        r = self.me.radius * 0.9
        d = math.hypot(x1 - x0, y1 - y0) or 1
        px, py = -(y1 - y0) / d * r, (x1 - x0) / d * r
        return (tm.line_clear(x0, y0, x1, y1, shots=False) and tm.line_clear(x0 + px, y0 + py, x1 + px, y1 + py, False)
                and tm.line_clear(x0 - px, y0 - py, x1 - px, y1 - py, False))

    def _incoming(self):
        """Return a sidestep vector if an enemy projectile is about to hit us."""
        me = self.me
        for p in self.world.projectiles:
            if p.team == me.team or p.lob is not None:
                continue
            rx, ry = me.x - p.x, me.y - p.y
            if rx * rx + ry * ry > (TILE * 5) ** 2:
                continue
            sp2 = p.vx * p.vx + p.vy * p.vy
            if sp2 < 1:
                continue
            t = (rx * p.vx + ry * p.vy) / sp2
            if t < 0 or t > 0.6:
                continue
            cx, cy = p.x + p.vx * t - me.x, p.y + p.vy * t - me.y
            if cx * cx + cy * cy < (me.radius + p.radius + 6) ** 2:
                sp = math.sqrt(sp2)
                nx, ny = -p.vy / sp, p.vx / sp
                if nx * -cx + ny * -cy < 0:
                    nx, ny = -nx, -ny
                return nx, ny
        for a in self.world.projectiles:
            if a.lob is not None and a.team != me.team:
                L = a.lob
                if math.hypot(L["tx"] - me.x, L["ty"] - me.y) < a.explode_radius + me.radius:
                    dx, dy = me.x - L["tx"], me.y - L["ty"]
                    d = math.hypot(dx, dy) or 1
                    return dx / d, dy / d
        return None

    # ------------------------------------------------------------ main
    def think(self, dt):
        w, me, p = self.world, self.me, self.p
        it = Intent()
        enemies = self.visible_enemies()
        self.decide_t -= dt
        self.fire_t -= dt
        self.strafe_t -= dt
        if self.decide_t <= 0:
            self.decide_t = p["reaction"] * self.rng.uniform(0.7, 1.3)
            self.target = self._pick_target(enemies)
            self.goal = self._objective(enemies)
        if self.target is not None and (not self.target.alive or self.target not in enemies):
            self.target = None
        if self.strafe_t <= 0:
            self.strafe_t = self.rng.uniform(0.6, 1.6)
            self.strafe_dir = -self.strafe_dir if self.rng.random() < 0.6 else self.strafe_dir

        tgt = self.target
        gx, gy = self.goal if self.goal else (me.x, me.y)
        mx, my = self._steer_to(gx, gy, dt)

        if tgt is not None and self.mode_state not in ("retreat", "carry"):
            d = math.hypot(tgt.x - me.x, tgt.y - me.y)
            rng = me.attack_range_px
            ideal = rng * (0.45 if me.attack["type"] in ("melee", "flame", "spread") else 0.72)
            dx, dy = (tgt.x - me.x) / max(d, 1), (tgt.y - me.y) / max(d, 1)
            objective_pull = 0.35 if w.mode_id in ("zone_control", "gem_collection", "goal_rush") else 0.0
            if d > ideal + TILE * 0.5:
                if self._walk_clear(me.x, me.y, tgt.x, tgt.y):
                    cx, cy = dx, dy
                else:
                    cx, cy = self._steer_to(tgt.x, tgt.y, dt)
            elif d < ideal - TILE:
                cx, cy = -dx, -dy
            else:
                cx, cy = 0.0, 0.0
            sx, sy = -dy * self.strafe_dir * p["strafe"], dx * self.strafe_dir * p["strafe"]
            mx = mx * objective_pull + (cx + sx * 0.6) * (1 - objective_pull)
            my = my * objective_pull + (cy + sy * 0.6) * (1 - objective_pull)

        # dodging
        self.dodge_t -= dt
        if self.dodge_t <= 0:
            self.dodge_vec = None
            v = self._incoming()
            if v is not None and self.rng.random() < p["dodge"]:
                self.dodge_vec = v
                self.dodge_t = 0.3
            else:
                self.dodge_t = p["reaction"] * 0.5
        if self.dodge_vec is not None:
            mx, my = mx * 0.3 + self.dodge_vec[0], my * 0.3 + self.dodge_vec[1]

        # unstick
        if self.last_pos is not None:
            moved = math.hypot(me.x - self.last_pos[0], me.y - self.last_pos[1])
            if moved < 0.5 and (abs(mx) + abs(my)) > 0.3:
                self.stuck_t += dt
            else:
                self.stuck_t = max(0.0, self.stuck_t - dt)
        self.last_pos = (me.x, me.y)
        if self.stuck_t > 0.6:
            self.path_t = 0
            self.path = []
            ang = self.rng.uniform(0, 2 * math.pi)
            mx, my = math.cos(ang), math.sin(ang)
            self.stuck_t = 0.0

        it.mx, it.my = mx, my

        # attacking
        mode = w.mode_id
        if mode == "goal_rush" and w.orb is not None and w.orb.carrier is me:
            self._orb_logic(it)
        elif tgt is not None:
            self._attack_logic(it, tgt)
        elif self.box_target is not None and mode == "solo_survival":
            bx, by = (self.box_target[0] + 0.5) * TILE, (self.box_target[1] + 0.5) * TILE
            if self.box_target not in w.map.hp:
                self.box_target = None
            elif math.hypot(bx - me.x, by - me.y) < me.attack_range_px * 0.9 and me.ammo >= 2 and self.fire_t <= 0:
                it.ax, it.ay = bx, by
                it.attack = True
                self.fire_t = 0.4
        self._super_logic(it, tgt, enemies)
        return it

    def _aim_point(self, tgt):
        me, p = self.me, self.p
        spd = me.attack.get("speed", 800)
        d = math.hypot(tgt.x - me.x, tgt.y - me.y)
        t = d / max(1, spd) * p["lead"]
        vx = getattr(tgt, "vx", 0.0)
        vy = getattr(tgt, "vy", 0.0)
        ax, ay = tgt.x + vx * t, tgt.y + vy * t
        err = self.rng.gauss(0, p["aim_err"])
        ang = math.atan2(ay - me.y, ax - me.x) + err
        dist = math.hypot(ax - me.x, ay - me.y)
        return me.x + math.cos(ang) * dist, me.y + math.sin(ang) * dist

    def _attack_logic(self, it, tgt):
        me, w = self.me, self.world
        d = math.hypot(tgt.x - me.x, tgt.y - me.y)
        it.ax, it.ay = self._aim_point(tgt)
        if self.fire_t > 0 or me.ammo < 1:
            return
        in_range = d <= me.attack_range_px + tgt.radius * 0.5
        lob = me.attack["type"] == "lob"
        if in_range and (lob or w.map.line_clear(me.x, me.y, tgt.x, tgt.y)):
            # keep one bar in reserve unless the fight is close
            if me.ammo < 2 and d > me.attack_range_px * 0.7 and self.p["fire"] >= 0.9 and tgt.hp_frac > 0.3:
                return
            it.attack = True
            self.fire_t = (0.3 + (1 - self.p["fire"]) * 1.0) * self.rng.uniform(0.8, 1.2)

    def _orb_logic(self, it):
        w, me = self.world, self.me
        tm = w.map
        goal_tiles = tm.goals["R" if me.team == 0 else "A"]
        if not goal_tiles:
            return
        gx = (sum(t[0] for t in goal_tiles) / len(goal_tiles) + 0.5) * TILE
        gy = (sum(t[1] for t in goal_tiles) / len(goal_tiles) + 0.5) * TILE
        d = math.hypot(gx - me.x, gy - me.y)
        if d < TILE * 5.5 and tm.line_clear(me.x, me.y, gx, gy):
            it.ax, it.ay = gx, gy + self.rng.uniform(-TILE, TILE) * (1 - self.p["fire"])
            it.attack = True

    def _super_logic(self, it, tgt, enemies):
        me, w, p = self.me, self.world, self.p
        if not me.super_ready or self.rng.random() > p["super"] * 0.25:
            return
        s = me.sup
        t = s["type"]
        rng = super_range_tiles(s) * TILE
        allies = w.allies_of(me, True)
        use = False
        tx, ty = (tgt.x, tgt.y) if tgt is not None else (me.x, me.y)
        if t in ("heal_zone",):
            hurt = [a for a in allies if a.hp_frac < 0.6]
            if hurt:
                a = min(hurt, key=lambda a: a.hp_frac)
                if math.hypot(a.x - me.x, a.y - me.y) < rng:
                    tx, ty = a.x, a.y
                    use = True
        elif t == "shield_aura":
            near = [a for a in allies if math.hypot(a.x - me.x, a.y - me.y) < rng]
            if (me.hp_frac < 0.55 or len(near) >= 2) and enemies:
                use = True
        elif t in ("stealth", "rage"):
            if tgt is not None and math.hypot(tgt.x - me.x, tgt.y - me.y) < me.attack_range_px + TILE * 3:
                use = True
        elif t in ("turret", "heal_totem", "decoy"):
            if tgt is not None or (t == "heal_totem" and any(a.hp_frac < 0.7 for a in allies)):
                tx, ty = me.x, me.y
                if tgt is not None:
                    a = math.atan2(tgt.y - me.y, tgt.x - me.x)
                    tx, ty = me.x + math.cos(a) * TILE * 1.5, me.y + math.sin(a) * TILE * 1.5
                use = True
        elif t == "wall":
            if tgt is not None and me.hp_frac < 0.7:
                a = math.atan2(tgt.y - me.y, tgt.x - me.x)
                tx, ty = me.x + math.cos(a) * TILE * 2, me.y + math.sin(a) * TILE * 2
                use = True
        elif t == "nova_ring":
            if tgt is not None and math.hypot(tgt.x - me.x, tgt.y - me.y) < rng * 0.8:
                use = True
        elif tgt is not None:
            d = math.hypot(tgt.x - me.x, tgt.y - me.y)
            if d < rng:
                if t in ("snipe", "stun_wave", "dash") and not w.map.line_clear(me.x, me.y, tgt.x, tgt.y):
                    use = False
                else:
                    tx, ty = self._aim_point(tgt) if t in ("snipe", "stun_wave") else (tgt.x, tgt.y)
                    use = True
        if use:
            it.super = True
            it.ax, it.ay = tx, ty
