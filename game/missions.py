"""Missions: regular (sequential) missions, daily missions and event missions.

Every mission tracks one *stat* that gameplay reports through
:meth:`MissionManager.record` (e.g. ``coins``, ``distance``, ``jumps``).

* ``mode: total`` - progress accumulates across runs
* ``mode: run``   - the target must be reached inside a single run
"""
import random

from .utils import today, fmt_int


class Mission:
    __slots__ = ("id", "desc", "stat", "mode", "target", "reward", "group")

    def __init__(self, d, group):
        self.id = d["id"]
        self.desc = d["desc"]
        self.stat = d["stat"]
        self.mode = d.get("mode", "total")
        self.target = d["target"]
        self.reward = d.get("reward", {})
        self.group = group  # "regular" | "daily" | "event"


class MissionManager:
    def __init__(self, gamedata, save, economy, progression, events=None):
        self.gamedata = gamedata
        self.save = save
        self.economy = economy
        self.progression = progression
        self.events = events
        self.run_values = {}
        self.completed_this_run = []
        self.ensure_daily()

    # ------------------------------------------------------------------
    # Daily missions (deterministic per date so everyone gets the same set)
    # ------------------------------------------------------------------
    def ensure_daily(self):
        d = self.save["daily_missions"]
        date = today().isoformat()
        if d.get("date") == date and d.get("missions"):
            return
        rnd = random.Random(date)
        pool = list(self.gamedata.missions_daily_pool)
        rnd.shuffle(pool)
        chosen = []
        for i, m in enumerate(pool[:self.gamedata.daily_count]):
            target = rnd.choice(m["targets"])
            chosen.append({"id": f"{m['id']}_{date}", "desc": m["desc"].replace("{target}", fmt_int(target)),
                           "stat": m["stat"], "mode": m["mode"], "target": target, "reward": m["reward"]})
        self.save["daily_missions"] = {"date": date, "missions": chosen, "progress": {}, "completed": []}
        self.save.mark_dirty()

    # ------------------------------------------------------------------
    # Lists
    # ------------------------------------------------------------------
    def regular_active(self):
        done = set(self.save["missions"]["completed"])
        out = []
        for d in self.gamedata.missions_regular:
            if d["id"] not in done:
                out.append(Mission(d, "regular"))
                if len(out) >= self.gamedata.mission_slots:
                    break
        return out

    def regular_done_count(self):
        return len(self.save["missions"]["completed"])

    def daily(self):
        return [Mission(d, "daily") for d in self.save["daily_missions"]["missions"]]

    def event_missions(self):
        if not self.events:
            return []
        ev = self.events.active()
        if not ev:
            return []
        return [Mission(dict(m, id=f"ev_{ev['id']}_{m['id']}"), "event") for m in ev["missions"]]

    def all_active(self):
        out = [m for m in self.regular_active()]
        out += [m for m in self.daily() if not self.is_completed(m)]
        out += [m for m in self.event_missions() if not self.is_completed(m)]
        return out

    def _store(self, m):
        return self.save["daily_missions"] if m.group == "daily" else self.save["missions"]

    def progress(self, m):
        return self._store(m)["progress"].get(m.id, 0)

    def is_completed(self, m):
        return m.id in self._store(m)["completed"]

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------
    def begin_run(self):
        self.ensure_daily()
        self.run_values = {}
        self.completed_this_run = []
        self._active = self.all_active()

    def record(self, stat, amount=1, run_value=None):
        """Report gameplay progress. ``run_value`` overrides the per-run total (e.g. score)."""
        if run_value is None:
            run_value = self.run_values.get(stat, 0) + amount
        self.run_values[stat] = run_value
        for m in getattr(self, "_active", []):
            if m.stat != stat or self.is_completed(m):
                continue
            store = self._store(m)
            if m.mode == "total":
                store["progress"][m.id] = store["progress"].get(m.id, 0) + amount
            else:
                store["progress"][m.id] = max(store["progress"].get(m.id, 0), run_value)
            if store["progress"][m.id] >= m.target:
                self._complete(m)

    def _complete(self, m):
        store = self._store(m)
        if m.id in store["completed"]:
            return
        store["completed"].append(m.id)
        lines = self.economy.grant(m.reward, self.progression)
        self.completed_this_run.append((m, lines))
        self.save.mark_dirty()
        self.economy.notify("mission", m)
        if m.group == "regular":
            # refill the slot immediately so the next mission starts tracking this run
            self._active = [a for a in self._active if a.id != m.id]
            for nm in self.regular_active():
                if all(nm.id != a.id for a in self._active):
                    self._active.append(nm)
