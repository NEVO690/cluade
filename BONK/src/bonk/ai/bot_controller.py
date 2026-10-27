"""Bot brain: produces an InputCommand every tick, exactly like a human player would.

Two layers:
  * planning (every `decision_interval` seconds): where am I on the route, which
    line to take, is a hammer / piston about to swing through my path, should
    I wait?
  * reflexes (every tick): edge ahead -> find a landing and jump, hurdle ahead
    -> jump, sweeping bar about to hit -> jump, standing on a vanishing tile ->
    keep moving.

Difficulty only changes these behaviours (see bot_difficulty.py); a bot is
never faster than a player and never moves except through the physics.
"""

import math

from ..sim import constants as C
from ..sim.character import InputCommand
from .bot_navigation import UP_REACH, Sensors

STOP = InputCommand()


class BotController:
    def __init__(self, profile, rng, world):
        self.p = profile
        self.rng = rng
        self.world = world
        self.sensors = Sensors(world)
        self.routes = [world.route] + list(getattr(world, "alt_routes", []))
        self.route = world.route
        self.lane = rng.uniform(-1.0, 1.0) * profile.lane_noise  # preferred line, -1..1 of width
        self.zig_phase = rng.uniform(0.0, 6.28)
        self.next_plan = 0.0
        self.move = (0.0, 1.0)  # current wish direction
        self.walk = False
        self.wait_until = -1.0
        self.wait_reason = None
        self.edge_wait_since = None
        self.hesitate_until = -1.0
        self.jump_plan = None
        self.commit = None  # (solid, until_t): landing we decided to jump to
        self.jump_cooldown_until = -1.0
        self.awareness = {}  # hazard id -> did this bot "notice" it this encounter
        self.misjudged = {}  # edge key -> bool
        self.edge_jitter = {}
        self.best_s = -1.0
        self.last_gain_t = 0.0
        self.last_pos = None
        self.s = 0.0
        self.seg_hint = 0
        self._press_jump_next = False
        self.notice_tiles = True
        self.debug = ""

    # ================================================================ entry point
    def command(self, ch, rnd):
        t = rnd.t
        pos = (ch.x, ch.y, ch.z)
        if self.last_pos is not None and (abs(pos[0] - self.last_pos[0]) + abs(pos[1] - self.last_pos[1])) > 3.0:
            self._reset_after_teleport(t)  # respawned at a checkpoint
        self.last_pos = pos

        if not ch.grounded:
            return self._air_control(ch)
        if self.jump_plan is not None:
            self.jump_plan = None
            self.next_plan = t  # just landed: look around again

        if t >= self.next_plan:
            self._plan(ch, rnd, t)
            jitter = self.rng.uniform(0.7, 1.3)
            self.next_plan = t + self.p.decision_interval * jitter
        return self._reflexes(ch, rnd, t)

    # ================================================================ planning
    def _localize(self, ch):
        best = None
        for r in self.routes:
            hint = self.seg_hint if r is self.route else 0
            s, seg, lat, cost = r.project(ch.x, ch.y, ch.z, hint, None)
            if best is None or cost < best[4] - 0.5:
                best = (r, s, seg, lat, cost)
        self.route, self.s, self.seg_hint = best[0], best[1], best[2]
        return best[3]

    def _plan(self, ch, rnd, t):
        p = self.p
        rng = self.rng
        self._localize(ch)
        s = self.s
        # ---- progress / stuck detection
        if s > self.best_s + 0.5:
            self.best_s = s
            self.last_gain_t = t
        stuck_for = t - self.last_gain_t
        if stuck_for > 3.0 and self.wait_until < t and self.edge_wait_since is None:
            self.lane = rng.uniform(-1.0, 1.0)
            self.last_gain_t = t - 1.5  # try again in 1.5 s if still stuck
            self.jump_cooldown_until = -1.0
            self._press_jump_next = True

        # ---- hesitation (mostly EASY bots)
        if p.hesitation_chance > 0 and rng.random() < p.hesitation_chance * p.decision_interval:
            h, solid, safe = self.sensors.ground(ch.x, ch.y, ch.z)
            if safe and solid is not None and not solid.moving:
                self.hesitate_until = t + rng.uniform(0.3, 0.9)

        # ---- pick a line through the course
        look = p.lookahead
        fx, fy, fz, dx, dy, width, _ = self.route.frame_at(s + look)
        nx, ny = -dy, dx  # left normal
        if p.zigzag > 0:
            zig = math.sin(t * 2.1 + self.zig_phase) * p.zigzag
        else:
            zig = 0.0
        if rng.random() < 0.08 * p.lane_noise:
            self.lane = max(-1.0, min(1.0, self.lane + rng.uniform(-0.6, 0.6)))
        preferred = self.lane * max(0.0, width - 0.6) + zig
        notice_tiles = rng.random() < p.tile_safety
        self.notice_tiles = notice_tiles
        speed = max(ch.speed, C.RUN_SPEED * 0.8)
        horizon = look / speed + 0.4
        candidates = [preferred]
        steps = 6
        for k in range(steps + 1):
            candidates.append(-width + 2.0 * width * k / steps)
        best = None
        others = [o for o in rnd.characters if o is not None and o.alive and o.id != ch.id]
        for lat in candidates:
            lat = max(-width, min(width, lat))
            px, py = fx + nx * lat, fy + ny * lat
            cost = abs(lat - preferred) * 0.35
            h, solid, safe = self.sensors.ground(px, py, fz, up=UP_REACH, down=1.5, t=t + horizon * 0.8,
                                                 horizon=0.5)
            if h is None:
                cost += 6.0
            elif notice_tiles and not safe:
                cost += 4.0
            # Halfway point: avoid lines that cross holes we could just walk around.
            mx_, my_ = (ch.x + px) * 0.5, (ch.y + py) * 0.5
            hm, sm, safe_m = self.sensors.ground(mx_, my_, ch.z, up=UP_REACH, down=1.5)
            if hm is None:
                cost += 1.5
            elif notice_tiles and not safe_m:
                cost += 1.5
            for o in others:
                ddx, ddy = o.x - px, o.y - py
                if ddx * ddx + ddy * ddy < 1.3:
                    cost += 0.6 * (1.0 - p.aggression)
            if best is None or cost < best[0]:
                best = (cost, lat, px, py)
        _, lat, tx, ty = best
        # Keep the chosen line (lane persistence) unless it was only noise.
        if width > 0.6:
            self.lane = max(-1.0, min(1.0, (lat - zig) / max(0.6, width - 0.6)))

        # ---- aggression: CHAOTIC bots like to shove people
        if p.aggression > 0 and rng.random() < p.aggression * 0.25:
            for o in others:
                ddx, ddy = o.x - ch.x, o.y - ch.y
                if 0.5 < ddx * ddx + ddy * ddy < 6.0 and ddy * dy + ddx * dx > 0:
                    tx, ty = o.x, o.y
                    break

        mdx, mdy = tx - ch.x, ty - ch.y
        ml = math.hypot(mdx, mdy)
        if ml < 1e-3:
            mdx, mdy, ml = dx, dy, 1.0
        self.move = (mdx / ml, mdy / ml)
        self.walk = rng.random() < p.walk_chance

        # ---- hazard timing (hammers, pistons): wait for a gap if needed
        self.wait_until = -1.0
        self.wait_reason = None
        hazards = self.sensors.hazards_ahead(ch.x, ch.y, 9.0)
        timed = []
        for hz in hazards:
            if hz.kind == "sweeper":
                continue  # handled by the jump reflex
            if hz.id not in self.awareness or t - self.awareness[hz.id][1] > 6.0:
                self.awareness[hz.id] = (rng.random() < p.hazard_awareness, t)
            if self.awareness[hz.id][0]:
                timed.append(hz)
        if timed:
            ux, uy = self.move
            run = C.WALK_SPEED if self.walk else C.RUN_SPEED
            tau = Sensors.path_danger(timed, ch.x, ch.y, ch.z, ux, uy, run, t, horizon=1.3)
            if tau is not None:
                wait = None
                w = 0.2
                while w <= p.patience + 1e-6:
                    if (not Sensors.point_danger(timed, ch.x, ch.y, ch.z, t, w)
                            and Sensors.path_danger(timed, ch.x, ch.y, ch.z, ux, uy, run, t + w,
                                                    horizon=1.3) is None):
                        wait = w
                        break
                    w += 0.2
                if wait is not None:
                    self.wait_until = t + wait
                    self.wait_reason = "hazard"
                elif Sensors.point_danger(timed, ch.x, ch.y, ch.z, t, 0.6):
                    # Standing here is not safe either: back off along the route.
                    self.move = (-ux, -uy)
                    self.wait_until = t + 0.3
                    self.wait_reason = "retreat"
        self.debug = "plan s=%.1f lat=%.1f wait=%s" % (s, lat, self.wait_reason)

    # ================================================================ reflexes
    def _reflexes(self, ch, rnd, t):
        p = self.p
        rng = self.rng
        sensors = self.sensors
        mx, my = self.move
        jump = False

        if self._press_jump_next:
            self._press_jump_next = False
            h, _, safe = sensors.ground(ch.x + mx * 2.5, ch.y + my * 2.5, ch.z, down=0.5)
            if t >= self.jump_cooldown_until and h is not None and safe:
                jump = True

        standing_h, standing_on, standing_safe = sensors.ground(ch.x, ch.y, ch.z, down=0.3)
        on_warning = standing_on is not None and standing_on.kind == "tile" and not standing_safe

        # Waiting for a hammer / piston window, or hesitating.
        if not on_warning and (self.wait_until > t or self.hesitate_until > t):
            if self.wait_reason == "retreat":
                return InputCommand(mx, my, False, False)
            return self._hold_position(ch, standing_on)

        # ---- committed to a landing? look along that direction
        committed = None
        if self.commit is not None and self.commit[1] > t and standing_on is not self.commit[0]:
            committed = sensors.landing_on(self.commit[0], ch.x, ch.y, ch.z, ch.speed, t)
            if committed is not None:
                ax, ay = committed[0] - ch.x, committed[1] - ch.y
                al = math.hypot(ax, ay) or 1.0
                mx, my = ax / al, ay / al
        if committed is None:
            self.commit = None

        # ---- edge ahead?
        edge = sensors.edge_distance(ch.x, ch.y, ch.z, mx, my, max_dist=1.4, speed=ch.speed,
                                     tile_aware=self.notice_tiles)
        if edge is not None:
            key = (round(ch.x / 2.0), round(ch.y / 2.0))
            if key not in self.misjudged:
                self.misjudged[key] = rng.random() < p.misjudge_chance
                self.edge_jitter[key] = rng.uniform(-p.jump_jitter, p.jump_jitter)
            if self.misjudged[key]:
                return InputCommand(mx, my, False, False)  # didn't see it coming
            landing = committed or sensors.find_landing(
                ch.x, ch.y, ch.z, mx, my, ch.speed, t, route=self.route, s_now=self.s,
                horizon=0.3 if self.notice_tiles else -5.0, min_dist=max(0.5, edge),
                exclude=standing_on,
                others=[(o.x, o.y) for o in rnd.characters if o is not ch and o.alive
                        and abs(o.y - ch.y) < 7.0])
            if landing is not None:
                if committed is None:
                    self.commit = (landing[3], t + 1.0)
                lx, ly, lz, lsolid, dist = landing
                ax, ay = lx - ch.x, ly - ch.y
                al = math.hypot(ax, ay) or 1.0
                mx, my = ax / al, ay / al
                self.move = (mx, my)
                edge2 = sensors.edge_distance(ch.x, ch.y, ch.z, mx, my, max_dist=1.4, speed=ch.speed,
                                              tile_aware=self.notice_tiles) or 1.4
                trigger = 0.38 + self.edge_jitter.get(key, 0.0)
                along = ch.vx * mx + ch.vy * my
                if (edge2 <= max(0.12, trigger) and along > C.RUN_SPEED * 0.55) or edge2 <= 0.2 \
                        or (edge2 <= 0.45 and along > 1.5 and dist < 3.2):
                    if t >= self.jump_cooldown_until:
                        jump = True
                        self.jump_plan = (lx, ly, lz)
                        self.jump_cooldown_until = t + 0.3
                        self.edge_wait_since = None
                        self.commit = None
                return InputCommand(mx, my, jump, False)
            # Nowhere to land yet (ferry away, tile gone): wait near the edge.
            if self.edge_wait_since is None:
                self.edge_wait_since = t
            if t - self.edge_wait_since > p.patience * 2.5 + 2.0:
                self.edge_wait_since = None
                self.lane = rng.uniform(-1.0, 1.0)
                self.next_plan = t
            if standing_on is not None and standing_on.moving:
                return self._hold_position(ch, standing_on)
            # Slide along the edge back toward the middle of the course, if that is solid.
            fx, fy, _, rdx, rdy, _, _ = self.route.frame_at(self.s + 1.0)
            cx, cy = fx - ch.x, fy - ch.y
            cl = math.hypot(cx, cy)
            if cl > 0.8:
                cx, cy = cx / cl, cy / cl
                if sensors.edge_distance(ch.x, ch.y, ch.z, cx, cy, max_dist=0.6) is None:
                    return InputCommand(cx, cy, False, True)
            if edge < 0.9:
                return self._hold_position(ch, standing_on, back_from=(mx, my) if edge < 0.5 else None)
        else:
            self.edge_wait_since = None

        # ---- hurdle / wall ahead
        wd, wh = sensors.wall_ahead(ch.x, ch.y, ch.z, mx, my, 1.6)
        if wd is not None:
            if wh <= UP_REACH:
                key = ("w", round(ch.x), round(ch.y))
                if key not in self.edge_jitter:
                    self.edge_jitter[key] = rng.uniform(-p.jump_jitter, p.jump_jitter)
                if wd <= 0.9 + self.edge_jitter[key] and t >= self.jump_cooldown_until:
                    jump = True
                    self.jump_cooldown_until = t + 0.35
            elif wd < 0.8:
                self.next_plan = t  # real wall: pick another line now
                self.lane = -self.lane if abs(self.lane) > 0.2 else rng.choice((-1.0, 1.0))

        # ---- sweeping bars: jump just before the bar arrives
        if not jump and t >= self.jump_cooldown_until:
            for hz in sensors.world.hazards_near(ch.y, 9.0):
                if hz.kind != "sweeper":
                    continue
                if hz.id not in self.awareness or t - self.awareness[hz.id][1] > 4.0:
                    self.awareness[hz.id] = (rng.random() < p.hazard_awareness, t)
                if not self.awareness[hz.id][0]:
                    continue
                sp = max(ch.speed, 1.0)
                tau = Sensors.path_danger([hz], ch.x, ch.y, ch.z, ch.vx / sp, ch.vy / sp, ch.speed, t,
                                          horizon=0.45, step=0.02, margin=0.08)
                if tau is not None and tau <= p.sweeper_lead + rng.uniform(-0.04, 0.04) * (1 + p.jump_jitter * 4):
                    jump = True
                    self.jump_cooldown_until = t + 0.4
                    break

        # ---- chaotic hops (only where it is safe to land)
        if not jump and p.random_jump_rate > 0 and rng.random() < p.random_jump_rate * C.DT:
            h, _, safe = sensors.ground(ch.x + mx * 3.0, ch.y + my * 3.0, ch.z, down=0.4)
            if h is not None and safe and t >= self.jump_cooldown_until:
                jump = True
                self.jump_cooldown_until = t + 0.5

        if jump:
            self.jump_plan = self.jump_plan or (ch.x + mx * 3.0, ch.y + my * 3.0, ch.z)
        return InputCommand(mx, my, jump, self.walk and not on_warning and not jump)

    def _hold_position(self, ch, standing_on, back_from=None):
        """Stand still; on a moving platform stay near its middle; step back from an edge."""
        if standing_on is not None and standing_on.moving:
            dx, dy = standing_on.cx - ch.x, standing_on.cy - ch.y
            d = math.hypot(dx, dy)
            if d > 0.35:
                return InputCommand(dx / d * 0.6, dy / d * 0.6, False, True)
            return STOP
        if back_from is not None:
            return InputCommand(-back_from[0] * 0.5, -back_from[1] * 0.5, False, True)
        return STOP

    def _air_control(self, ch):
        """Feather the jump: steer so we are over the landing spot when we come down."""
        if self.jump_plan is None:
            return InputCommand(self.move[0], self.move[1], False, False)
        lx, ly, lz = self.jump_plan
        disc = ch.vz * ch.vz + 2.0 * C.GRAVITY * (ch.z - lz)
        t_land = (ch.vz + math.sqrt(disc)) / C.GRAVITY if disc > 0.0 else 0.15
        t_land = max(t_land, 0.08)
        vx, vy = (lx - ch.x) / t_land, (ly - ch.y) / t_land
        mx, my = vx / C.RUN_SPEED, vy / C.RUN_SPEED
        m = math.hypot(mx, my)
        if m > 1.0:
            mx, my = mx / m, my / m
        return InputCommand(mx, my, False, False)

    def _reset_after_teleport(self, t):
        self.jump_plan = None
        self.commit = None
        self.wait_until = -1.0
        self.edge_wait_since = None
        self.next_plan = t
        self.last_gain_t = t
        self.best_s = -1.0
        self.seg_hint = 0
