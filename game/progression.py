"""Player level / XP, level rewards, achievements and daily login rewards."""
from . import settings as S
from .utils import today, parse_date


def xp_to_next(level):
    """XP needed to go from ``level`` to ``level + 1``."""
    return int(200 + 110 * (level - 1) + 8 * (level - 1) ** 2)


class Progression:
    def __init__(self, gamedata, save, economy):
        self.gamedata = gamedata
        self.save = save
        self.economy = economy
        self.pending_level_ups = []  # [(level, reward_lines)] for the UI

    @property
    def level(self):
        return self.save["level"]

    @property
    def xp(self):
        return self.save["xp"]

    @property
    def xp_needed(self):
        return xp_to_next(self.level) if self.level < S.MAX_LEVEL else 0

    @property
    def progress(self):
        return 1.0 if self.level >= S.MAX_LEVEL else min(1.0, self.xp / max(1, self.xp_needed))

    def level_reward(self, level):
        r = dict(self.gamedata.level_rewards.get(level, {}))
        if not r:
            r = {"coins": self.gamedata.coins_per_level * level}
        return r

    def add_xp(self, amount):
        """Add XP, applying every level-up reward. Returns list of levels gained."""
        if amount <= 0:
            return []
        gained = []
        self.save["xp"] = self.xp + int(amount)
        while self.level < S.MAX_LEVEL and self.xp >= xp_to_next(self.level):
            self.save["xp"] = self.xp - xp_to_next(self.level)
            self.save["level"] = self.level + 1
            lines = self.economy.grant(self.level_reward(self.level))
            gained.append(self.level)
            self.pending_level_ups.append((self.level, lines))
            self.economy.notify("level_up", (self.level, lines))
        if self.level >= S.MAX_LEVEL:
            self.save["xp"] = 0
        self.save.mark_dirty()
        return gained

    def boost_to(self, level):
        """Raise the player to ``level`` (granting every level reward on the way)."""
        gained = []
        level = min(level, S.MAX_LEVEL)
        while self.level < level:
            got = self.add_xp(max(1, self.xp_needed - self.xp))
            if not got:
                break
            gained.extend(got)
        return gained

    def unlocked_zone_ids(self):
        return [z["id"] for z in self.gamedata.zones if z["unlock_level"] <= self.level]

    def upcoming_unlocks(self, count=4):
        """Next few things that unlock with levels (for the UI)."""
        out = []
        for lvl in range(self.level + 1, S.MAX_LEVEL + 1):
            things = []
            for z in self.gamedata.zones:
                if z["unlock_level"] == lvl:
                    things.append(f"Zone: {z['name']}")
            for c in self.gamedata.characters:
                if c["unlock_level"] == lvl:
                    things.append(f"Character: {c['name']}")
            if lvl in self.gamedata.level_rewards:
                things.append(self.economy.reward_text(self.gamedata.level_rewards[lvl]))
            if things:
                out.append((lvl, things))
            if len(out) >= count:
                break
        return out


class Achievements:
    """Achievements are checked against lifetime stats stored in the save."""

    def __init__(self, gamedata, save, economy, progression):
        self.gamedata = gamedata
        self.save = save
        self.economy = economy
        self.progression = progression

    def value(self, stat):
        s = self.save
        if stat == "level":
            return s["level"]
        if stat == "best_score":
            return s["best_score"]
        if stat == "best_distance":
            return s["best_distance"]
        if stat == "zones_seen":
            return len(s["zones_seen"])
        if stat == "characters_owned":
            return len(s["characters_owned"])
        return s.stat(stat)

    def is_unlocked(self, aid):
        return bool(self.save["achievements"].get(aid))

    def check(self):
        """Unlock every achievement whose target is reached. Returns newly unlocked defs."""
        new = []
        for a in self.gamedata.achievements:
            if self.is_unlocked(a["id"]):
                continue
            if self.value(a["stat"]) >= a["target"]:
                self.save["achievements"][a["id"]] = today().isoformat()
                self.economy.grant(a["reward"], self.progression)
                new.append(a)
                self.economy.notify("achievement", a)
        if new:
            self.save.mark_dirty()
        return new

    def progress(self, a):
        return min(1.0, self.value(a["stat"]) / a["target"])


class DailyRewards:
    def __init__(self, gamedata, save, economy, progression):
        self.gamedata = gamedata
        self.save = save
        self.economy = economy
        self.progression = progression

    def _state(self):
        return self.save["daily_reward"]

    def next_day(self, on=None):
        """Day number (1..7) the player would claim today."""
        on = on or today()
        st = self._state()
        last = parse_date(st.get("last_claim", ""))
        day = int(st.get("day", 0))
        if last is None or (on - last).days > 1:
            return 1
        return day % 7 + 1

    def available(self, on=None):
        on = on or today()
        last = parse_date(self._state().get("last_claim", ""))
        return last is None or last < on

    def claim(self, on=None):
        on = on or today()
        if not self.available(on):
            return None
        day = self.next_day(on)
        reward = self.gamedata.daily_rewards[day - 1]
        lines = self.economy.grant(reward, self.progression)
        self.save["daily_reward"] = {"last_claim": on.isoformat(), "day": day}
        self.save.save()
        return day, reward, lines
