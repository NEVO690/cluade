"""Long-term achievements with progress and a one-time coin reward."""


class AchievementManager:
    def __init__(self, store, ach_def):
        self.store = store
        self.defs = {a["id"]: a for a in ach_def}
        self.order = [a["id"] for a in ach_def]

    @property
    def _a(self):
        return self.store.data["achievements"]

    def state(self, aid):
        return self._a.get(aid, {"completed": False, "rewarded": False})

    def progress(self, aid, stats):
        a = self.defs[aid]
        return min(a["target"], int(stats.get(a["stat"], 0)))

    def completed_ids(self):
        return [aid for aid in self.order if self.state(aid)["completed"]]

    def evaluate(self, stats):
        """Mark newly completed achievements.  Returns [(id, coin_reward)] to pay out once."""
        payouts = []
        for aid in self.order:
            st = self._a.setdefault(aid, {"completed": False, "rewarded": False})
            if not st["completed"] and stats.get(self.defs[aid]["stat"], 0) >= self.defs[aid]["target"]:
                st["completed"] = True
            if st["completed"] and not st["rewarded"]:
                st["rewarded"] = True
                payouts.append((aid, int(self.defs[aid]["reward"])))
        return payouts
