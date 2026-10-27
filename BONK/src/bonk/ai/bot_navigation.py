"""Bot perception: probing the course the same way a player looks at it.

Bots only *read* the world here (ground under a point, walls ahead, where a
moving platform or hammer will be in a moment).  They never move themselves
directly; all movement goes through the normal InputCommand -> physics path.
"""

import math

from ..sim import constants as C

UP_REACH = C.MAX_JUMP_HEIGHT - 0.2  # highest ledge a bot will try to jump onto


class Sensors:
    def __init__(self, world):
        self.world = world
        self.movers = [s for s in world.solids if s.moving and s.kind != "pusher"]
        self.pushers = [s for s in world.solids if s.kind == "pusher"]

    # ---------------------------------------------------------------- ground
    def ground(self, x, y, z_ref, up=C.STEP_HEIGHT + 0.05, down=1.2, t=None, horizon=0.0):
        """Walkable height near z_ref at (x, y).

        Moving platforms are evaluated at time `t` (prediction) when given.
        Returns (height, solid, safe) or (None, None, False).
        """
        world = self.world
        best_h, best_s = None, None
        top_limit, low_limit = z_ref + up, z_ref - down
        r = 0.15
        for s in world.solids_near(y, 1.0):
            if s.moving and t is not None and s.kind != "pusher":
                px, py, pz = s.position_at(t)
                minx, maxx, miny, maxy = px - s.hx, px + s.hx, py - s.hy, py + s.hy
                top = pz + s.hz
            else:
                if not s.is_solid():
                    continue
                minx, maxx, miny, maxy = s.minx, s.maxx, s.miny, s.maxy
                top = None
            if x < minx - r or x > maxx + r or y < miny - r or y > maxy + r:
                continue
            if s.kind == "pusher":
                continue  # never stand on a piston on purpose
            if top is None:
                top = s.top_at(min(max(x, minx), maxx), min(max(y, miny), maxy))
            if low_limit <= top <= top_limit and (best_h is None or top > best_h):
                best_h, best_s = top, s
        if best_s is None:
            return None, None, False
        tt = self.world.t if t is None else t
        return best_h, best_s, best_s.is_safe(tt, horizon)

    def edge_distance(self, x, y, z, dx, dy, max_dist=2.0, step=0.2, speed=None, tile_aware=False):
        """Distance along (dx, dy) until there is no ground under the feet (None = no edge).

        With tile_aware, a tile that will have vanished by the time we get there
        counts as a hole.
        """
        sp = max(speed or C.RUN_SPEED, 2.0)
        d = step
        while d <= max_dist + 1e-6:
            # A ledge we can jump onto is not an edge (the hurdle reflex handles it).
            h, s, safe = self.ground(x + dx * d, y + dy * d, z, up=UP_REACH, down=0.6,
                                     horizon=d / sp + 0.25)
            if h is None or (tile_aware and not safe):
                return d
            d += step
        return None

    def find_landing(self, x, y, z, dx, dy, speed, t, max_fan_deg=35, min_dist=0.8,
                     route=None, s_now=0.0, horizon=0.4, exclude=None, others=()):
        """Search for somewhere to jump to in a fan around (dx, dy).

        Returns (lx, ly, lz, solid, distance) of the best landing or None.
        Moving platforms are checked at the moment the bot would land there.
        """
        run_speed = max(speed, C.RUN_SPEED * 0.9)
        max_d = C.max_jump_distance(1.0, run_speed)
        base = math.atan2(dy, dx)
        fan = [0]
        for k in range(1, int(max_fan_deg / 7) + 1):
            fan += [k * 7, -k * 7]
        best = None
        for deg in fan:
            a = base + math.radians(deg)
            ux, uy = math.cos(a), math.sin(a)
            d = min_dist
            while d <= max_d:
                px, py = x + ux * d, y + uy * d
                t_land = t + d / run_speed
                h, s, safe = self.ground(px, py, z, up=UP_REACH, down=3.5, t=t_land,
                                         horizon=horizon + d / run_speed)
                if h is None or s is exclude:
                    d += 0.25
                    continue
                drop = z - h
                if d + 0.35 > C.max_jump_distance(drop, run_speed):
                    break  # out of reach at this height; further points are worse
                if not safe:
                    d += 0.25
                    continue
                gain = d
                if route is not None:
                    s_land, _, _, _ = route.project(px, py, h)
                    gain = s_land - s_now
                    if gain < 0.5:
                        break  # would not move us forward
                lx, ly = self._landing_point(s, px, py, ux, uy, h, t_land)
                score = gain - abs(deg) * 0.03 - max(0.0, -drop) * 0.4 - max(0.0, drop - 0.5) * 1.5
                for ox, oy in others:  # someone already standing there: likely to be shoved off
                    if (ox - lx) ** 2 + (oy - ly) ** 2 < 1.4:
                        score -= 2.5
                if best is None or score > best[0]:
                    best = (score, (lx, ly, h, s, d))
                break
        return best[1] if best else None

    def landing_on(self, solid, x, y, z, speed, t, horizon=0.4):
        """Re-evaluate a committed landing on `solid`.  Returns the same tuple as find_landing."""
        run_speed = max(speed, C.RUN_SPEED * 0.9)
        if solid.moving:
            cx, cy, cz = solid.position_at(t + 0.4)
            top = cz + solid.hz
        else:
            if not solid.is_solid():
                return None
            cx, cy, top = solid.cx, solid.cy, solid.maxz
        dx, dy = cx - x, cy - y
        d = math.hypot(dx, dy)
        if d < 1e-3:
            return None
        ux, uy = dx / d, dy / d
        t_land = t + d / run_speed
        if not solid.is_safe(t, horizon + d / run_speed):
            return None
        if d - min(solid.hx, solid.hy) > C.max_jump_distance(z - top, run_speed) + 0.3:
            return None
        lx, ly = self._landing_point(solid, cx - ux * min(solid.hx, solid.hy), cy - uy * min(solid.hx, solid.hy),
                                     ux, uy, top, t_land)
        return lx, ly, top, solid, d

    def _landing_point(self, solid, px, py, ux, uy, h, t_land):
        """Where to aim inside the platform found at (px, py)."""
        if solid.moving:
            cx, cy, _ = solid.position_at(t_land)
        else:
            cx, cy = solid.cx, solid.cy
        if min(solid.hx, solid.hy) < 1.5:
            return cx, cy  # small platform / tile: the middle is the safest spot
        # Large platform: a metre past the near edge, but never beyond the far side.
        for extra in (1.0, 0.6, 0.3):
            lx, ly = px + ux * extra, py + uy * extra
            h2, _, _ = self.ground(lx, ly, h, up=0.1, down=0.2, t=t_land + 0.1)
            if h2 is not None:
                return lx, ly
        return px, py

    # ---------------------------------------------------------------- walls
    def wall_ahead(self, x, y, z, dx, dy, dist=1.8):
        """(distance, height_above_feet) of a blocking solid ahead, or (None, None)."""
        d, s, top = self.world.wall_probe(x, y, z, dx, dy, dist)
        if d is None or s.kind == "pusher":
            return None, None
        return d, top - z

    # ---------------------------------------------------------------- hazards
    def hazards_ahead(self, x, y, dist=8.0):
        hz = [h for h in self.world.hazards_near(y + dist * 0.5, dist * 0.5 + 3.0)]
        for p in self.pushers:
            if p.miny - 4.0 < y + dist and p.maxy + 4.0 > y - 2.0:
                hz.append(p)
        return hz

    @staticmethod
    def path_danger(hazards, x, y, z, dx, dy, speed, t, horizon=1.2, step=0.1, margin=0.25):
        """First time (s) at which running straight would touch a hazard, or None."""
        tau = 0.0
        while tau <= horizon + 1e-6:
            px, py = x + dx * speed * tau, y + dy * speed * tau
            for h in hazards:
                if h.danger_at(px, py, z, t + tau, margin):
                    return tau
            tau += step
        return None

    @staticmethod
    def point_danger(hazards, x, y, z, t, duration, step=0.1, margin=0.25):
        tau = 0.0
        while tau <= duration + 1e-6:
            for h in hazards:
                if h.danger_at(x, y, z, t + tau, margin):
                    return True
            tau += step
        return False
