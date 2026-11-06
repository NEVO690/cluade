"""Player account: currencies, trophies, levels, unlocks, stats, history and rewards."""
import datetime

from ilbrawl.progression import achievements, missions

STARTERS = ["nova", "rocko", "pip"]


def today_str(offset_days=0):
    return (datetime.date.today() + datetime.timedelta(days=offset_days)).isoformat()


def default_profile():
    return {
        "version": 1,
        "name": "",
        "icon": "char:nova",
        "title": "title_rookie",
        "name_color": "color_white",
        "xp": 0,
        "level": 1,
        "coins": 150,
        "gems": 20,
        "trophies": {},
        "highest_trophies": 0,
        "unlocked": list(STARTERS),
        "char_levels": {},
        "skins_owned": [],
        "skin_selected": {},
        "cosmetics_owned": ["icon_star", "title_rookie", "color_white"],
        "selected_char": "nova",
        "selected_mode": "gem_collection",
        "selected_map": {},
        "trophy_road_claimed": [],
        "daily": {"last_claim": "", "streak": 0},
        "missions": {"date": "", "list": []},
        "achievements": {},
        "shop": {"date": "", "daily_offers": [], "bought_daily": [], "bought_once": []},
        "stats": {
            "matches": 0, "wins": 0, "losses": 0, "draws": 0, "kills": 0, "deaths": 0,
            "damage": 0, "healing": 0, "supers": 0, "gems_collected": 0, "goals": 0,
            "solo_wins": 0, "best_kills": 0, "playtime": 0.0,
            "mode_matches": {}, "mode_wins": {}, "char_matches": {},
        },
        "history": [],
        "created": today_str(),
    }


class Profile:
    FILE = "profile"

    def __init__(self, save_manager, data):
        self.sm = save_manager
        self.gd = data
        self.data = self.sm.load(self.FILE, default_profile())
        self._sanitize()
        missions.ensure_daily(self)
        self.save()

    # ------------------------------------------------------------ persistence
    def _sanitize(self):
        d = self.data
        d["unlocked"] = [c for c in d.get("unlocked", []) if c in self.gd.characters] or list(STARTERS)
        for c in STARTERS:
            if c not in d["unlocked"]:
                d["unlocked"].append(c)
        if d.get("selected_char") not in d["unlocked"]:
            d["selected_char"] = d["unlocked"][0]
        if d.get("selected_mode") not in self.gd.modes:
            d["selected_mode"] = self.gd.mode_order[0]
        d["coins"] = max(0, int(d.get("coins", 0)))
        d["gems"] = max(0, int(d.get("gems", 0)))
        for k in list(d["trophies"]):
            if k not in self.gd.characters:
                del d["trophies"][k]

    def save(self):
        return self.sm.save(self.FILE, self.data)

    def reset(self):
        self.data = default_profile()
        missions.ensure_daily(self)
        self.save()

    # ------------------------------------------------------------ queries
    def display_name(self, i18n):
        return self.data["name"] or i18n.t("profile.default_name")

    def total_trophies(self):
        return sum(self.data["trophies"].values())

    def char_trophies(self, cid):
        return self.data["trophies"].get(cid, 0)

    def is_unlocked(self, cid):
        return cid in self.data["unlocked"]

    def char_level(self, cid):
        return self.data["char_levels"].get(cid, 1)

    def selected_skin(self, cid):
        s = self.data["skin_selected"].get(cid)
        return s if s in self.data["skins_owned"] else None

    def selected_map(self, mode_id):
        maps = self.gd.maps_for_mode(mode_id)
        mid = self.data["selected_map"].get(mode_id)
        ids = [m["id"] for m in maps]
        if mid in ids:
            return mid
        return ids[0] if ids else None

    def xp_for_next(self):
        table = self.gd.progression.get("xp_per_level", [0, 100])
        lvl = self.data["level"]
        if lvl < len(table):
            return table[lvl] - table[lvl - 1]
        return self.gd.progression.get("xp_per_level_after", 250)

    def upgrade_cost(self, cid):
        lvl = self.char_level(cid)
        if lvl >= self.gd.max_level:
            return None
        return self.gd.upgrade_costs[lvl]

    # ------------------------------------------------------------ currency
    def can_afford(self, price):
        return all(self.data.get(k, 0) >= v for k, v in price.items())

    def spend(self, price):
        if not self.can_afford(price):
            return False
        for k, v in price.items():
            self.data[k] -= v
        return True

    def grant(self, reward):
        """Apply a reward dict {'type': coins|gems|xp|character|skin|cosmetic, ...}; returns description tuple."""
        t = reward.get("type")
        if t in ("coins", "gems"):
            self.data[t] += int(reward["amount"])
        elif t == "xp":
            self.add_xp(int(reward["amount"]))
        elif t == "character":
            self.unlock_character(reward["id"])
        elif t == "skin":
            if reward["id"] not in self.data["skins_owned"]:
                self.data["skins_owned"].append(reward["id"])
                ch = self.gd.skins[reward["id"]]["char"]
                if ch not in self.data["unlocked"]:
                    self.unlock_character(ch)
        elif t == "cosmetic":
            if reward["id"] not in self.data["cosmetics_owned"]:
                self.data["cosmetics_owned"].append(reward["id"])
        return reward

    def unlock_character(self, cid):
        if cid in self.gd.characters and cid not in self.data["unlocked"]:
            self.data["unlocked"].append(cid)
            return True
        return False

    def upgrade_character(self, cid):
        cost = self.upgrade_cost(cid)
        if cost is None or not self.is_unlocked(cid):
            return False
        if not self.spend({"coins": cost}):
            return False
        self.data["char_levels"][cid] = self.char_level(cid) + 1
        self.save()
        return True

    def add_xp(self, amount):
        levels = 0
        self.data["xp"] += amount
        while self.data["xp"] >= self.xp_for_next():
            self.data["xp"] -= self.xp_for_next()
            self.data["level"] += 1
            levels += 1
            self.grant(self.gd.progression.get("level_up_reward", {"type": "gems", "amount": 5}))
        return levels

    # ------------------------------------------------------------ daily reward
    def daily_reward_available(self):
        return self.data["daily"]["last_claim"] != today_str()

    def daily_reward_day(self):
        """0-based index into the 7-day cycle of the reward that would be claimed now."""
        d = self.data["daily"]
        streak = d["streak"] if d["last_claim"] == today_str(-1) else 0
        if d["last_claim"] == today_str():
            streak = d["streak"] - 1
        table = self.gd.progression.get("daily_rewards", [])
        return streak % max(1, len(table))

    def claim_daily_reward(self):
        if not self.daily_reward_available():
            return None
        d = self.data["daily"]
        streak = d["streak"] + 1 if d["last_claim"] == today_str(-1) else 1
        table = self.gd.progression.get("daily_rewards", [{"type": "coins", "amount": 50}])
        reward = table[(streak - 1) % len(table)]
        self.grant(reward)
        d["last_claim"] = today_str()
        d["streak"] = streak
        self.save()
        return reward

    # ------------------------------------------------------------ trophy road
    def trophy_road(self):
        return self.gd.progression.get("trophy_road", [])

    def claimable_road(self):
        return [i for i, m in enumerate(self.trophy_road())
                if self.data["highest_trophies"] >= m["trophies"] and i not in self.data["trophy_road_claimed"]]

    def claim_road(self, index):
        if index not in self.claimable_road():
            return None
        reward = self.trophy_road()[index]["reward"]
        self.grant(reward)
        self.data["trophy_road_claimed"].append(index)
        self.save()
        return reward

    # ------------------------------------------------------------ match results
    def trophy_change(self, result):
        tc = self.gd.progression.get("trophy_changes", {})
        if result.get("rank"):
            table = tc.get("solo", [10, 7, 4, 0, -2, -4])
            delta = table[min(len(table) - 1, result["rank"] - 1)]
        else:
            delta = tc.get("team", {}).get(result["outcome"], 0)
        cur = self.char_trophies(result["char"])
        # higher trophy counts earn slightly less and lose slightly more
        if delta > 0 and cur > 400:
            delta = max(3, delta - (cur - 400) // 200)
        if delta < 0 and cur > 400:
            delta -= min(4, (cur - 400) // 250)
        return max(-cur, delta)

    def apply_match_result(self, result):
        d = self.data
        st = d["stats"]
        p = result["player"]
        outcome = result["outcome"]
        mode = result["mode"]
        summary = {"trophies": 0, "coins": 0, "xp": 0, "levels": 0, "missions": [], "achievements": [],
                   "road": [], "outcome": outcome, "rank": result.get("rank")}
        # trophies
        delta = self.trophy_change(result)
        cid = result["char"]
        before_high = d["highest_trophies"]
        d["trophies"][cid] = self.char_trophies(cid) + delta
        d["highest_trophies"] = max(d["highest_trophies"], self.total_trophies())
        summary["trophies"] = delta
        summary["road"] = [i for i, m in enumerate(self.trophy_road())
                           if before_high < m["trophies"] <= d["highest_trophies"]]
        # currency + xp
        mr = self.gd.progression.get("match_rewards", {}).get(outcome, {"coins": 8, "xp": 10})
        coins = mr["coins"] + min(10, p.get("kills", 0) * 2)
        xp = mr["xp"] + min(20, p.get("kills", 0) * 3)
        d["coins"] += coins
        summary["coins"] = coins
        summary["xp"] = xp
        summary["levels"] = self.add_xp(xp)
        # stats
        st["matches"] += 1
        st["wins"] += outcome == "win"
        st["losses"] += outcome == "loss"
        st["draws"] += outcome == "draw"
        st["kills"] += p.get("kills", 0)
        st["deaths"] += p.get("deaths", 0)
        st["damage"] += int(p.get("damage", 0))
        st["healing"] += int(p.get("healing", 0))
        st["supers"] += p.get("supers", 0)
        st["gems_collected"] += p.get("gems", 0)
        st["goals"] += p.get("goals", 0)
        st["playtime"] += result.get("duration", 0)
        if mode == "solo_survival" and result.get("rank") == 1:
            st["solo_wins"] += 1
        st["best_kills"] = max(st["best_kills"], p.get("kills", 0))
        st["mode_matches"][mode] = st["mode_matches"].get(mode, 0) + 1
        if outcome == "win":
            st["mode_wins"][mode] = st["mode_wins"].get(mode, 0) + 1
        st["char_matches"][cid] = st["char_matches"].get(cid, 0) + 1
        # history (newest first, capped)
        d["history"].insert(0, {
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "mode": mode, "map": result["map"],
            "char": cid, "outcome": outcome, "rank": result.get("rank"), "trophies": delta,
            "kills": p.get("kills", 0), "damage": int(p.get("damage", 0)),
        })
        del d["history"][30:]
        summary["missions"] = missions.apply_result(self, result)
        summary["achievements"] = achievements.newly_claimable(self)
        self.save()
        return summary
