"""SOLO SURVIVAL: free-for-all, no respawns, closing poison cloud, power cubes from boxes."""
from ilbrawl.combat import damage as dmg
from ilbrawl.config import TILE
from ilbrawl.modes.base import GameMode


class SoloSurvival(GameMode):
    team_based = False

    def setup(self):
        self.ranks = {}
        tm = self.world.map
        self.safe = [0.0, 0.0, float(tm.pw), float(tm.ph)]
        self.poison_start = self.cfg.get("poison_start", 30)
        self.shrink_time = self.cfg.get("poison_shrink_time", 120)
        self.dps = self.cfg.get("poison_dps", 450)
        self.final_half = TILE * 2.5
        self.warned = False

    def spawn_point(self, b):
        pts = self.world.map.spawns.get("S") or [(100, 100)]
        idx = self.world.brawlers.index(b)
        return pts[idx % len(pts)]

    def allow_respawn(self):
        return False

    def on_death(self, victim, killer):
        alive = [b for b in self.world.brawlers if b.alive]
        self.ranks[victim.id] = len(alive) + 1
        self.world.scatter("cube", victim.x, victim.y, max(1, victim.cubes), 120)

    def update(self, dt):
        super().update(dt)
        w = self.world
        tm = w.map
        t = w.time - self.poison_start
        if t > -5 and not self.warned:
            self.warned = True
            self.announce("hud.poison_warning", 3.0)
        if t > 0:
            f = min(1.0, t / self.shrink_time)
            cx, cy = tm.pw / 2, tm.ph / 2
            hw = cx - (cx - self.final_half) * f
            hh = cy - (cy - self.final_half) * f
            self.safe = [cx - hw, cy - hh, cx + hw, cy + hh]
            for b in w.brawlers:
                if b.alive and not self.in_safe(b.x, b.y):
                    dmg.apply_damage(w, None, b, self.dps * dt * (1 + 0.5 * f))

    def in_safe(self, x, y):
        s = self.safe
        return s[0] <= x <= s[2] and s[1] <= y <= s[3]

    def check_end(self):
        w = self.world
        alive = [b for b in w.brawlers if b.alive]
        player = w.player
        if len(alive) <= 1 or (player is not None and not player.alive) or w.time >= self.duration:
            ranks = dict(self.ranks)
            # survivors ranked by remaining health
            alive.sort(key=lambda b: -b.hp_frac)
            for i, b in enumerate(alive):
                ranks[b.id] = i + 1
            outcome = {}
            for b in w.brawlers:
                r = ranks.get(b.id, len(w.brawlers))
                outcome[b.team] = "win" if r <= 3 else "loss"
            return {"winner": alive[0].team if alive else None, "ranks": ranks, "outcome": outcome}
        return None

    def hud(self):
        return {"type": "solo", "alive": len([b for b in self.world.brawlers if b.alive]),
                "total": len(self.world.brawlers), "safe": list(self.safe),
                "poison_in": max(0.0, self.poison_start - self.world.time)}

    def score_of(self, b):
        return b.stats.kills

    def final_score_text(self):
        return ""
