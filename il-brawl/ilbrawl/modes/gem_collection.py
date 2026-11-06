"""GEM COLLECTION: grab gems from the central mine; hold the target count through a countdown to win."""
import math

from ilbrawl.gameplay.entities import Pickup
from ilbrawl.modes.base import GameMode


class GemCollection(GameMode):
    def setup(self):
        tm = self.world.map
        self.mines = tm.gem_mines or [(tm.pw / 2, tm.ph / 2)]
        self.spawn_timer = 3.0
        self.to_win = self.cfg.get("gems_to_win", 10)
        self.countdown_len = self.cfg.get("countdown", 15)
        self.leader = None
        self.countdown = None

    def team_gems(self, team):
        return sum(b.gems for b in self.world.brawlers if b.team == team and b.alive)

    def on_death(self, victim, killer):
        super().on_death(victim, killer)
        if victim.gems:
            self.world.scatter("gem", victim.x, victim.y, victim.gems, 170)
            victim.gems = 0

    def update(self, dt):
        super().update(dt)
        w = self.world
        self.spawn_timer -= dt
        if self.spawn_timer <= 0 and len([p for p in w.pickups if p.kind == "gem"]) < 29:
            self.spawn_timer = self.cfg.get("gem_interval", 7)
            for (mx, my) in self.mines:
                a = w.rng.uniform(0, 2 * math.pi)
                w.pickups.append(Pickup("gem", mx, my, math.cos(a) * 110, math.sin(a) * 110, 0.3))
                w.emit("gem_spawn", x=mx, y=my)
        g0, g1 = self.team_gems(0), self.team_gems(1)
        leader = None
        if g0 >= self.to_win and g0 > g1:
            leader = 0
        elif g1 >= self.to_win and g1 > g0:
            leader = 1
        if leader != self.leader:
            self.leader = leader
            self.countdown = self.countdown_len if leader is not None else None
            if leader is not None:
                self.announce("hud.gem_countdown_start", 2.5)
        elif self.countdown is not None:
            self.countdown -= dt

    def check_end(self):
        if self.countdown is not None and self.countdown <= 0:
            return {"winner": self.leader, "outcome": self.team_outcome(self.leader)}
        if self.world.time >= self.duration:
            g0, g1 = self.team_gems(0), self.team_gems(1)
            win = 0 if g0 > g1 else 1 if g1 > g0 else None
            return {"winner": win, "outcome": self.team_outcome(win)}
        return None

    def hud(self):
        return {"type": "gems", "a": self.team_gems(0), "b": self.team_gems(1), "target": self.to_win,
                "countdown": self.countdown, "leader": self.leader}

    def score_of(self, b):
        return b.stats.gems

    def final_score_text(self):
        return "%d - %d" % (self.team_gems(0), self.team_gems(1))
