"""Titles: unlocked only when their condition is met; one can be equipped."""


class TitleManager:
    def __init__(self, store, titles_def):
        self.store = store
        self.defs = {t["id"]: t for t in titles_def}
        self.order = [t["id"] for t in titles_def]

    @property
    def _t(self):
        return self.store.data["titles"]

    @property
    def unlocked(self):
        return list(self._t["unlocked"])

    @property
    def equipped(self):
        return self._t["equipped"]

    def equipped_name(self):
        tid = self.equipped
        return self.defs[tid]["name"] if tid in self.defs else None

    def is_unlocked(self, tid):
        return tid in self._t["unlocked"]

    @staticmethod
    def condition_met(cond, stats, rank_order_fn, rank_id):
        if "stat" in cond:
            return stats.get(cond["stat"], 0) >= cond["min"]
        if "best_time" in cond:
            t = stats.get("best_times", {}).get(cond["best_time"])
            return t is not None and t <= cond["max"]
        if "map_finishes" in cond:
            return stats.get("map_finishes", {}).get(cond["map_finishes"], 0) >= cond["min"]
        if "rank" in cond:
            return rank_order_fn(rank_id) >= rank_order_fn(cond["rank"])
        return False

    def evaluate(self, stats, rank_order_fn, rank_id):
        """Unlock every title whose condition is now met.  Returns newly unlocked ids."""
        new = []
        for tid in self.order:
            if tid in self._t["unlocked"]:
                continue
            if self.condition_met(self.defs[tid]["condition"], stats, rank_order_fn, rank_id):
                self._t["unlocked"].append(tid)
                new.append(tid)
        return new

    def equip(self, tid):
        if tid is None:
            self._t["equipped"] = None
            return
        if tid not in self._t["unlocked"]:
            raise PermissionError("title %s is locked" % tid)
        self._t["equipped"] = tid
