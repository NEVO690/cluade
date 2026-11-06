"""TEAM SURVIVAL: rounds of elimination without respawns; first team to win 2 rounds wins."""
from ilbrawl.modes.base import GameMode


class TeamSurvival(GameMode):
    def setup(self):
        self.duration = 0
        self.round = 1
        self.wins = [0, 0]
        self.round_time = self.cfg.get("round_time", 75)
        self.round_clock = 0.0
        self.to_win = self.cfg.get("rounds_to_win", 2)
        self.pause = 0.0
        self.max_rounds = 5
        self.rounds_played = 0
        self.announce("hud.round", 2.0, n=1)

    def allow_respawn(self):
        return False

    def on_death(self, victim, killer):
        pass

    def _team_hp(self, team):
        return sum(b.hp_frac for b in self.world.brawlers if b.team == team and b.alive)

    def update(self, dt):
        super().update(dt)
        if self.pause > 0:
            self.pause -= dt
            if self.pause <= 0 and not self._decided():
                self.round += 1
                self.round_clock = 0.0
                self.world.reset_round()
                self.announce("hud.round", 2.0, n=self.round)
                self.world.emit("round_start", n=self.round)
            return
        self.round_clock += dt
        a0, a1 = self.alive_on_team(0), self.alive_on_team(1)
        winner = "none"
        if not a0 and not a1:
            winner = None
        elif not a1:
            winner = 0
        elif not a0:
            winner = 1
        elif self.round_clock >= self.round_time:
            h0, h1 = self._team_hp(0), self._team_hp(1)
            winner = 0 if h0 > h1 + 0.01 else 1 if h1 > h0 + 0.01 else None
        if winner != "none":
            if winner is not None:
                self.wins[winner] += 1
            self.world.emit("round_over", winner=winner)
            self.announce("hud.round_won" if winner is not None else "hud.round_draw", 2.0,
                          team=winner if winner is not None else -1)
            self.pause = 2.5
            self.rounds_played += 1

    def _decided(self):
        return max(self.wins) >= self.to_win or self.rounds_played >= self.max_rounds

    def check_end(self):
        if self.pause <= 0 and self._decided():
            w0, w1 = self.wins
            win = 0 if w0 > w1 else 1 if w1 > w0 else None
            return {"winner": win, "outcome": self.team_outcome(win)}
        return None

    def time_left(self):
        return max(0.0, self.round_time - self.round_clock)

    def hud(self):
        return {"type": "rounds", "a": self.wins[0], "b": self.wins[1], "round": self.round,
                "alive_a": len(self.alive_on_team(0)), "alive_b": len(self.alive_on_team(1))}

    def final_score_text(self):
        return "%d - %d" % tuple(self.wins)
