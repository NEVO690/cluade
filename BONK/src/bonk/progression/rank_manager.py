"""Local competitive rank from Rank Points (RP).

RP change after each show by fixed, published rules (data/progression.json):
win, reaching the final, qualified rounds, early elimination and quitting,
scaled by bot difficulty for positive changes.  Nothing is random.

This is the *local* (offline vs bots) rank.  Online ranking lives on the
game server and only counts server-verified results.
"""


class RankManager:
    def __init__(self, store, ranks_def):
        self.store = store
        self.d = ranks_def
        self.tiers = ranks_def["tiers"]

    @property
    def points(self):
        return self.store.data["rank"]["points"]

    def tier_for(self, points):
        current = self.tiers[0]
        for t in self.tiers:
            if points >= t["min_points"]:
                current = t
        return current

    @property
    def tier(self):
        return self.tier_for(self.points)

    def order(self, tier_id):
        for i, t in enumerate(self.tiers):
            if t["id"] == tier_id:
                return i
        return -1

    def next_tier(self):
        idx = self.order(self.tier["id"])
        return self.tiers[idx + 1] if idx + 1 < len(self.tiers) else None

    def points_for_report(self, report, total_rounds):
        rules = self.d["points"]
        if report.quit_early:
            return int(rules["quit"])
        delta = rules["per_round_qualified"] * report.rounds_qualified
        if report.won:
            delta += rules["win"]
        elif report.rounds_played >= total_rounds and total_rounds > 1:
            delta += rules["reached_final"]
        if report.rounds_played == 1 and report.rounds_qualified == 0 and total_rounds > 1:
            delta += rules["first_round_out"]
        if delta > 0:
            mult = self.d["difficulty_multiplier"].get(report.difficulty or "MIXED", 1.0)
            delta = int(round(delta * mult))
        return int(delta)

    def apply(self, delta):
        """Apply an RP change.  Returns (old_tier_id, new_tier_id)."""
        r = self.store.data["rank"]
        old = self.tier["id"]
        r["points"] = max(0, r["points"] + int(delta))
        r["peak_points"] = max(r["peak_points"], r["points"])
        return old, self.tier["id"]
