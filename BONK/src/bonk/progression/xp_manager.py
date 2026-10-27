"""Experience and levels.  Level n -> n+1 needs base_xp + xp_step * (n - 1) XP."""


class XPManager:
    def __init__(self, store, levels_def):
        self.store = store
        self.d = levels_def

    @property
    def _p(self):
        return self.store.data["progress"]

    @property
    def level(self):
        return self._p["level"]

    @property
    def xp(self):
        return self._p["xp"]

    @property
    def max_level(self):
        return int(self.d["max_level"])

    def xp_to_next(self, level=None):
        level = self.level if level is None else level
        if level >= self.max_level:
            return 0
        return int(self.d["base_xp"]) + int(self.d["xp_step"]) * (level - 1)

    def level_reward(self, level):
        coins = int(self.d["coin_reward_base"]) + int(self.d["coin_reward_per_level"]) * level
        coins += int(self.d.get("milestones", {}).get(str(level), 0))
        return coins

    def add_xp(self, amount):
        """Returns a list of (new_level, coin_reward) for every level gained."""
        if amount <= 0:
            return []
        p = self._p
        p["total_xp"] += amount
        if p["level"] >= self.max_level:
            return []
        p["xp"] += amount
        gained = []
        while p["level"] < self.max_level and p["xp"] >= self.xp_to_next(p["level"]):
            p["xp"] -= self.xp_to_next(p["level"])
            p["level"] += 1
            reward = 0
            if p["level"] not in p["rewarded_levels"]:  # each level pays out once, ever
                p["rewarded_levels"].append(p["level"])
                reward = self.level_reward(p["level"])
            gained.append((p["level"], reward))
        if p["level"] >= self.max_level:
            p["xp"] = 0
        return gained

    def progress_fraction(self):
        need = self.xp_to_next()
        return 1.0 if need == 0 else min(1.0, self.xp / need)
