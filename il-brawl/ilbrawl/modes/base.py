"""Base class for game modes."""
import math

from ilbrawl.config import TILE


class GameMode:
    team_based = True

    def __init__(self, world, cfg):
        self.world = world
        self.cfg = cfg
        self.duration = cfg.get("duration", 150)
        self.respawn_time = cfg.get("respawn")
        self.banner = None          # (text_key, params, seconds_left) for HUD announcements
        self.banner_t = 0.0

    # ------------------------------------------------------------ overridable
    def setup(self):
        pass

    def allow_respawn(self):
        return self.respawn_time is not None

    def spawn_point(self, b):
        tm = self.world.map
        key = "1" if b.team == 0 else "2"
        pts = tm.spawns.get(key) or tm.spawns.get("S") or [(tm.pw / 2, tm.ph / 2)]
        team = [o for o in self.world.brawlers if o.team == b.team]
        idx = team.index(b) if b in team else 0
        return pts[idx % len(pts)]

    def on_death(self, victim, killer):
        if self.allow_respawn():
            victim.respawn_timer = self.respawn_time

    def update(self, dt):
        if self.banner_t > 0:
            self.banner_t -= dt
            if self.banner_t <= 0:
                self.banner = None

    def check_end(self):
        return None

    def time_left(self):
        return max(0.0, self.duration - self.world.time) if self.duration else None

    def hud(self):
        return {}

    def score_of(self, b):
        return b.stats.kills

    def final_score_text(self):
        return ""

    # ------------------------------------------------------------ helpers
    def announce(self, key, seconds=2.2, **params):
        self.banner = (key, params)
        self.banner_t = seconds

    @staticmethod
    def team_outcome(winner, teams=(0, 1)):
        if winner is None:
            return {t: "draw" for t in teams}
        return {t: ("win" if t == winner else "loss") for t in teams}

    def alive_on_team(self, team):
        return [b for b in self.world.brawlers if b.team == team and b.alive]

    @staticmethod
    def dist(a, x, y):
        return math.hypot(a.x - x, a.y - y)


TILE_PX = TILE
