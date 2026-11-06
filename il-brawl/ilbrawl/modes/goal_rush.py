"""GOAL RUSH: carry or throw the energy orb into the enemy goal."""
from ilbrawl.modes.base import GameMode


class GoalRush(GameMode):
    def setup(self):
        tm = self.world.map
        home = tm.orb_spawns[0] if tm.orb_spawns else (tm.pw / 2, tm.ph / 2)
        self.world.spawn_orb(*home)
        self.goals = [0, 0]
        self.to_win = self.cfg.get("goals_to_win", 2)
        self.pause = 0.0
        self.last_scorer = None

    def update(self, dt):
        super().update(dt)
        w = self.world
        if self.pause > 0:
            self.pause -= dt
            if self.pause <= 0 and max(self.goals) < self.to_win:
                w.reset_round()
                w.emit("round_start", n=0)
            return
        o = w.orb
        g = w.map.goal_team_at(o.x, o.y)
        if g is not None:
            scoring_team = 1 - g      # 'A' belongs to team 0, so team 1 scores there
            self.goals[scoring_team] += 1
            scorer = o.carrier
            if scorer is None:
                cands = [b for b in w.brawlers if b.team == scoring_team and b.id == o.block_id]
                scorer = cands[0] if cands else None
            if scorer is not None and scorer.team == scoring_team:
                scorer.stats.goals += 1
            self.last_scorer = scorer
            if o.carrier:
                o.carrier.carrying_orb = False
                o.carrier = None
            o.vx = o.vy = 0.0
            o.x, o.y = o.home
            w.emit("goal", team=scoring_team)
            self.announce("hud.goal", 2.4, team=scoring_team)
            self.pause = 2.5

    def check_end(self):
        if max(self.goals) >= self.to_win and self.pause <= 0.1:
            win = 0 if self.goals[0] > self.goals[1] else 1
            return {"winner": win, "outcome": self.team_outcome(win)}
        if self.world.time >= self.duration and self.pause <= 0:
            g0, g1 = self.goals
            win = 0 if g0 > g1 else 1 if g1 > g0 else None
            return {"winner": win, "outcome": self.team_outcome(win)}
        return None

    def hud(self):
        o = self.world.orb
        holder = o.carrier.team if o and o.carrier else None
        return {"type": "goals", "a": self.goals[0], "b": self.goals[1], "target": self.to_win, "holder": holder}

    def score_of(self, b):
        return b.stats.goals

    def final_score_text(self):
        return "%d - %d" % tuple(self.goals)
