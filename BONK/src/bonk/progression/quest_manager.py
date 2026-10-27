"""Daily quests.

A "day" is the local calendar date.  To stop clock tricks from paying out
again and again:
  * the newest timestamp ever seen is stored; the effective time is never
    earlier than that, so turning the clock *back* never produces a new day;
  * a day's quests are generated from the date, so re-rolling the same day
    gives the same quests, and a day whose rewards were claimed is remembered;
  * rewards are paid through a transaction id unique to (day, quest), which
    the wallet refuses to process twice.

Limitation (documented in the README): without a server, moving the clock
*forward* does unlock the next day's quests early.  Each calendar day can still
only be claimed once.
"""

import datetime
import hashlib
import random
import time


class QuestManager:
    def __init__(self, store, quest_def, clock=time.time):
        self.store = store
        self.d = quest_def
        self.templates = {t["id"]: t for t in quest_def["templates"]}
        self.clock = clock

    @property
    def _q(self):
        return self.store.data["quests"]

    @property
    def active(self):
        return self._q["active"]

    def effective_now(self):
        now = float(self.clock())
        q = self._q
        if now > q["highest_seen"]:
            q["highest_seen"] = now
        return max(now, q["highest_seen"])

    @staticmethod
    def day_key(ts):
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

    def refresh(self):
        """Roll new quests if a new day started.  Returns True if they changed."""
        day = self.day_key(self.effective_now())
        q = self._q
        if q["day"] is not None and day <= q["day"]:
            return False  # same day, or the clock went backwards
        q["day"] = day
        q["active"] = self._generate(day)
        return True

    def _generate(self, day):
        seed = int(hashlib.sha256(("bonk-quests-" + day).encode()).hexdigest()[:12], 16)
        rng = random.Random(seed)
        picks = rng.sample(list(self.templates.values()), k=min(self.d["per_day"], len(self.templates)))
        out = []
        for t in picks:
            lo, hi = t["n"]
            n = rng.randint(lo, hi)
            out.append({"id": "%s:%s" % (day, t["id"]), "template": t["id"], "text": t["text"].format(n=n),
                        "stat": t["stat"], "target": n, "progress": 0, "coins": t["coins"], "xp": t["xp"],
                        "claimed": False})
        return out

    def record(self, deltas, streak):
        """Advance quest progress from one show's stat deltas.  Returns quests that just completed."""
        done = []
        for q in self._q["active"]:
            if q["claimed"] or q["progress"] >= q["target"]:
                continue
            if q["stat"] == "streak":
                q["progress"] = min(q["target"], max(q["progress"], streak))
            else:
                q["progress"] = min(q["target"], q["progress"] + int(deltas.get(q["stat"], 0)))
            if q["progress"] >= q["target"]:
                done.append(q)
        return done

    def claimable(self):
        return [q for q in self._q["active"] if q["progress"] >= q["target"] and not q["claimed"]]
