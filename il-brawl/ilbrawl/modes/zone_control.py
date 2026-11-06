"""ZONE CONTROL: capture zones and hold them to earn points; first to the target wins."""
import math

from ilbrawl.config import TILE
from ilbrawl.modes.base import GameMode

ZONE_RADIUS = TILE * 2.2


class Zone:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.radius = ZONE_RADIUS
        self.cap = 0.0     # -1 (team 2) .. +1 (team 1)
        self.owner = None
        self.contested = False


class ZoneControl(GameMode):
    def setup(self):
        tm = self.world.map
        pts = tm.zones or [(tm.pw / 2, tm.ph / 2)]
        self.zones = [Zone(x, y) for x, y in pts]
        self.points = [0.0, 0.0]
        self.to_win = self.cfg.get("points_to_win", 100)
        self.cap_rate = 1.0 / self.cfg.get("capture_time", 3.0)
        # holding every zone always takes about the same time, whatever the zone count
        n = len(self.zones)
        self.pps = self.cfg.get("points_per_sec", 1.6) * (1.0 if n == 1 else 1.5 / n)

    def update(self, dt):
        super().update(dt)
        w = self.world
        for z in self.zones:
            inside = [b for b in w.brawlers if b.alive and math.hypot(b.x - z.x, b.y - z.y) <= z.radius]
            n0 = sum(1 for b in inside if b.team == 0)
            n1 = sum(1 for b in inside if b.team == 1)
            z.contested = n0 > 0 and n1 > 0
            for b in inside:
                b.stats.zone_time += dt
            if n0 and not n1:
                z.cap = min(1.0, z.cap + self.cap_rate * dt * (1 + 0.25 * (n0 - 1)))
            elif n1 and not n0:
                z.cap = max(-1.0, z.cap - self.cap_rate * dt * (1 + 0.25 * (n1 - 1)))
            prev = z.owner
            if z.cap >= 1.0:
                z.owner = 0
            elif z.cap <= -1.0:
                z.owner = 1
            elif (z.owner == 0 and z.cap < 0) or (z.owner == 1 and z.cap > 0):
                z.owner = None
            if z.owner != prev and z.owner is not None:
                w.emit("capture", team=z.owner, x=z.x, y=z.y)
            if z.owner is not None:
                self.points[z.owner] += self.pps * dt

    def check_end(self):
        p0, p1 = self.points
        if p0 >= self.to_win or p1 >= self.to_win:
            win = 0 if p0 > p1 else 1
            return {"winner": win, "outcome": self.team_outcome(win)}
        if self.world.time >= self.duration:
            win = 0 if p0 > p1 + 0.5 else 1 if p1 > p0 + 0.5 else None
            return {"winner": win, "outcome": self.team_outcome(win)}
        return None

    def hud(self):
        return {"type": "zones", "a": int(self.points[0]), "b": int(self.points[1]), "target": self.to_win,
                "zones": [(z.owner, z.cap, z.contested) for z in self.zones]}

    def score_of(self, b):
        return int(b.stats.zone_time)

    def final_score_text(self):
        return "%d - %d" % (int(self.points[0]), int(self.points[1]))
