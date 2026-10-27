"""PlayerProfile: one object the UI talks to for coins, skins, XP, ranks, titles,
quests, achievements, stats and settings.  Turns a MatchReport into rewards."""

import uuid
from dataclasses import dataclass, field

from ..cosmetics.skin_definitions import SkinCatalog
from ..cosmetics.skin_manager import SkinManager
from ..economy.currency_manager import CurrencyManager
from ..economy.shop_manager import ShopManager
from ..save.save_manager import SaveManager, validate_setting
from .achievement_manager import AchievementManager
from .definitions import load_progression
from .quest_manager import QuestManager
from .rank_manager import RankManager
from .title_manager import TitleManager
from .xp_manager import XPManager


@dataclass
class RewardSummary:
    coins: list = field(default_factory=list)  # [(label, amount)]
    xp: list = field(default_factory=list)  # [(label, amount)]
    levels_gained: list = field(default_factory=list)  # [(level, coins)]
    rank_delta: int = 0
    rank_before: str = ""
    rank_after: str = ""
    new_titles: list = field(default_factory=list)
    quests_completed: list = field(default_factory=list)  # quest dicts
    achievements: list = field(default_factory=list)  # [(id, coins)]
    saved: bool = True
    duplicate: bool = False

    @property
    def total_coins(self):
        return sum(a for _, a in self.coins)

    @property
    def total_xp(self):
        return sum(a for _, a in self.xp)


class PlayerProfile:
    def __init__(self, save_manager=None, clock=None):
        self.store = save_manager or SaveManager()
        if self.store.data is None:
            self.store.load()
        self.defs = load_progression()
        self.catalog = SkinCatalog()
        self.currency = CurrencyManager(self.store)
        self.skins = SkinManager(self.store, self.catalog)
        self.shop = ShopManager(self)
        self.xp = XPManager(self.store, self.defs["levels"])
        self.ranks = RankManager(self.store, self.defs["ranks"])
        self.titles = TitleManager(self.store, self.defs["titles"])
        self.achievements = AchievementManager(self.store, self.defs["achievements"])
        kw = {"clock": clock} if clock else {}
        self.quests = QuestManager(self.store, self.defs["quests"], **kw)
        self.quests.refresh()
        self.refresh_unlocks()

    # ------------------------------------------------------------ basics
    @property
    def data(self):
        return self.store.data

    @property
    def stats(self):
        return self.store.data["stats"]

    @property
    def settings(self):
        return self.store.data["settings"]

    @property
    def name(self):
        return self.settings["player_name"]

    def set_setting(self, key, value):
        self.settings[key] = validate_setting(key, value)
        return self.settings[key]

    def save(self):
        return self.store.save()

    def stat_view(self):
        """Stats plus derived values used by achievements/titles."""
        s = dict(self.stats)
        s["skins_owned"] = len(self.skins.owned)
        s["level"] = self.xp.level
        return s

    def unmet_skin_requirements(self, skin_id):
        return self.skins.unmet_requirements(
            skin_id, self.xp.level, self.ranks.tier["id"], self.ranks.order,
            set(self.achievements.completed_ids()))

    def refresh_unlocks(self):
        """Re-check titles and achievements (e.g. after buying a skin).  Pays achievement rewards."""
        new_titles = self.titles.evaluate(self.stat_view(), self.ranks.order, self.ranks.tier["id"])
        payouts = self.achievements.evaluate(self.stat_view())
        for aid, coins in payouts:
            self.currency.earn(coins, "Achievement: %s" % self.achievements.defs[aid]["name"],
                               "ach:%s" % aid)
        return new_titles, payouts

    # ------------------------------------------------------------ match rewards
    def apply_match_report(self, report, total_rounds, match_id=None):
        """Turn a finished show into coins, XP, rank points, quest progress... and save."""
        match_id = match_id or uuid.uuid4().hex
        summary = RewardSummary()
        if match_id in self.data["matches_applied"]:
            summary.duplicate = True
            return summary
        self.quests.refresh()
        rw = self.defs["rewards"]
        c, x = rw["coins"], rw["xp"]

        # -- coins & XP
        if report.quit_early and report.rounds_played == 0:
            summary.coins.append(("Participation", c["quit"]))
            summary.xp.append(("Participation", x["quit"]))
        else:
            summary.coins.append(("Participation", c["participation"]))
            summary.xp.append(("Participation", x["participation"] if not report.quit_early else x["quit"]))
            if report.rounds_qualified:
                summary.coins.append(("Rounds qualified x%d" % report.rounds_qualified,
                                      c["per_round_qualified"] * report.rounds_qualified))
                summary.xp.append(("Rounds qualified x%d" % report.rounds_qualified,
                                   x["per_round_qualified"] * report.rounds_qualified))
            if report.finishes:
                summary.coins.append(("Finish lines x%d" % report.finishes, c["per_finish"] * report.finishes))
                summary.xp.append(("Finish lines x%d" % report.finishes, x["per_finish"] * report.finishes))
            if report.won:
                summary.coins.append(("Show winner!", c["win"]))
                summary.xp.append(("Show winner!", x["win"]))
            elif report.placement and report.placement <= 3 and report.player_count > 3:
                summary.coins.append(("Podium finish", c["podium"]))
            if report.obstacles_cleared:
                summary.xp.append(("Obstacles cleared", min(x["obstacle_cap"],
                                                           x["per_obstacle"] * report.obstacles_cleared)))

        # -- stats
        st = self.stats
        before = dict(st)
        st["games_played"] += 1
        st["rounds_played"] += report.rounds_played
        st["rounds_qualified"] += report.rounds_qualified
        st["finishes"] += report.finishes
        st["jumps"] += report.jumps
        st["obstacles"] += report.obstacles_cleared
        st["falls"] += report.falls
        st["hits"] += report.hits
        st["bonks"] += report.bonks
        if report.won:
            st["wins"] += 1
            st["current_streak"] += 1
        else:
            st["current_streak"] = 0
        st["best_streak"] = max(st["best_streak"], st["current_streak"])
        if report.placement and (st["best_placement"] == 0 or report.placement < st["best_placement"]):
            st["best_placement"] = report.placement
        for r in report.rounds:
            if r.get("time") is not None:
                m = r["map_id"]
                st["map_finishes"][m] = st["map_finishes"].get(m, 0) + 1
                prev = st["best_times"].get(m)
                if prev is None or r["time"] < prev:
                    st["best_times"][m] = r["time"]
        deltas = {k: st[k] - before[k] for k in st if isinstance(st[k], int)}

        # -- rank
        delta = self.ranks.points_for_report(report, total_rounds)
        summary.rank_delta = delta
        summary.rank_before, summary.rank_after = self.ranks.apply(delta)

        # -- quests (paid automatically, once per day+quest)
        for q in self.quests.record(deltas, st["current_streak"]):
            if self.currency.earn(q["coins"], "Quest: %s" % q["text"], "quest:%s" % q["id"]):
                summary.coins.append(("Quest: %s" % q["text"], q["coins"]))
                summary.xp.append(("Quest: %s" % q["text"], q["xp"]))
            q["claimed"] = True
            summary.quests_completed.append(q)

        # -- pay coins & XP
        for label, amount in summary.coins:
            if amount and not label.startswith("Quest:"):
                self.currency.earn(amount, label, "match:%s:%s" % (match_id, label))
        for lvl, coins in self.xp.add_xp(summary.total_xp):
            summary.levels_gained.append((lvl, coins))
            if coins:
                self.currency.earn(coins, "Level %d reward" % lvl, "level:%d" % lvl)

        # -- titles & achievements
        summary.new_titles, summary.achievements = self.refresh_unlocks()
        self.data["matches_applied"].append(match_id)
        del self.data["matches_applied"][:-100]
        summary.saved = self.save()
        return summary
