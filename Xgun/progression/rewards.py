"""Progression: XP, the free battle pass, daily quests, milestones, and the
post-match reward pipeline that ties them together."""
from __future__ import annotations

import datetime as dt
import json
import random
from dataclasses import dataclass, field

from config import paths
from economy.wallet import Wallet
from inventory.catalog import Catalog
from inventory.locker import Locker
from save_system.database import Database, now


@dataclass
class MatchSummary:
    """What the match simulation reports about the local player."""
    placement: int
    players: int
    eliminations: int = 0
    damage: int = 0
    chests: int = 0
    survive_secs: float = 0.0
    healed: int = 0
    pickaxe_hits: int = 0
    glide_secs: float = 0.0
    sniper_hits: int = 0
    duration: float = 0.0

    @property
    def won(self) -> bool:
        return self.placement == 1

    @property
    def top10(self) -> bool:
        return self.placement <= 10


@dataclass
class RewardLine:
    label: str
    xp: int = 0
    xon: int = 0


@dataclass
class MatchRewards:
    lines: list[RewardLine] = field(default_factory=list)
    unlocked_items: list[str] = field(default_factory=list)
    completed_quests: list[str] = field(default_factory=list)
    tiers_reached: list[int] = field(default_factory=list)
    level_before: int = 1
    level_after: int = 1

    @property
    def xp(self) -> int:
        return sum(l.xp for l in self.lines)

    @property
    def xon(self) -> int:
        return sum(l.xon for l in self.lines)


@dataclass
class QuestState:
    id: str
    text: str
    stat: str
    target: int
    progress: int
    xp: int
    xon: int
    claimed: bool

    @property
    def complete(self) -> bool:
        return self.progress >= self.target


def match_xp_and_xon(summary: MatchSummary) -> list[RewardLine]:
    lines = [RewardLine("Match played", xp=150, xon=40)]
    if summary.eliminations:
        lines.append(RewardLine(f"Eliminations x{summary.eliminations}",
                                xp=80 * summary.eliminations, xon=25 * summary.eliminations))
    minutes = int(summary.survive_secs // 60)
    if minutes:
        lines.append(RewardLine(f"Survived {minutes} min", xp=40 * minutes, xon=5 * minutes))
    if summary.won:
        lines.append(RewardLine("Victory Royale", xp=600, xon=300))
    elif summary.placement <= 5:
        lines.append(RewardLine("Top 5", xp=300, xon=120))
    elif summary.top10:
        lines.append(RewardLine("Top 10", xp=150, xon=60))
    return lines


class Progression:
    def __init__(self, db: Database, catalog: Catalog, wallet: Wallet, locker: Locker):
        self.db = db
        self.catalog = catalog
        self.wallet = wallet
        self.locker = locker
        self.pass_data = json.loads(paths.BATTLE_PASS_FILE.read_text(encoding="utf-8"))
        self.quest_data = json.loads(paths.QUESTS_FILE.read_text(encoding="utf-8"))
        self.xp_per_tier = int(self.pass_data["xp_per_tier"])

    # -- levels ---------------------------------------------------------
    def xp(self, account_id: int) -> int:
        return int(self.db.scalar("SELECT xp FROM stats WHERE account_id = ?", (account_id,), 0))

    def level_for_xp(self, xp: int) -> int:
        return 1 + xp // self.xp_per_tier

    def level(self, account_id: int) -> int:
        return self.level_for_xp(self.xp(account_id))

    def level_progress(self, account_id: int) -> tuple[int, int]:
        xp = self.xp(account_id)
        return xp % self.xp_per_tier, self.xp_per_tier

    @property
    def max_tier(self) -> int:
        return max(t["tier"] for t in self.pass_data["tiers"])

    def tiers(self) -> list[dict]:
        return self.pass_data["tiers"]

    def stats(self, account_id: int) -> dict:
        row = self.db.one("SELECT * FROM stats WHERE account_id = ?", (account_id,))
        return dict(row) if row else {}

    # -- reward helpers -------------------------------------------------
    def _claim_once(self, account_id: int, key: str) -> bool:
        cur = self.db.execute("INSERT OR IGNORE INTO reward_claims(account_id, reward_key, claimed_at) "
                              "VALUES (?, ?, ?)", (account_id, key, now()))
        return cur.rowcount > 0

    def is_claimed(self, account_id: int, key: str) -> bool:
        return self.db.one("SELECT 1 FROM reward_claims WHERE account_id = ? AND reward_key = ?",
                           (account_id, key)) is not None

    def _give(self, account_id: int, reward: dict, reason: str, out: MatchRewards | None) -> None:
        if reward["type"] == "xon":
            self.wallet.credit(account_id, int(reward["amount"]), reason)
            if out is not None:
                out.lines.append(RewardLine(reason, xon=int(reward["amount"])))
        elif reward["type"] == "item":
            if self.locker.grant(account_id, reward["item_id"], reason) and out is not None:
                out.unlocked_items.append(reward["item_id"])

    def add_xp(self, account_id: int, amount: int, out: MatchRewards | None = None) -> None:
        with self.db.transaction():
            self.db.execute("UPDATE stats SET xp = xp + ? WHERE account_id = ?", (amount, account_id))
            self.sync_battle_pass(account_id, out)

    def sync_battle_pass(self, account_id: int, out: MatchRewards | None = None) -> None:
        level = self.level(account_id)
        for tier in self.pass_data["tiers"]:
            if tier["tier"] <= level and self._claim_once(account_id, f"bp:{self.pass_data['season']}:{tier['tier']}"):
                if out is not None:
                    out.tiers_reached.append(tier["tier"])
                self._give(account_id, tier["reward"], f"Battle Pass tier {tier['tier']}", out)

    def tier_claimed(self, account_id: int, tier: int) -> bool:
        return self.is_claimed(account_id, f"bp:{self.pass_data['season']}:{tier}")

    # -- quests ---------------------------------------------------------
    @staticmethod
    def period(date: dt.date | None = None) -> str:
        return (date or dt.date.today()).isoformat()

    def daily_quests(self, account_id: int, date: dt.date | None = None) -> list[QuestState]:
        date = date or dt.date.today()
        period = self.period(date)
        rng = random.Random(date.toordinal() * 31 + account_id)
        chosen = rng.sample(self.quest_data["daily"], self.quest_data["daily_count"])
        states = []
        for q in chosen:
            row = self.db.one("SELECT progress, claimed FROM quest_progress WHERE account_id = ? AND quest_id = ? "
                              "AND period = ?", (account_id, q["id"], period))
            states.append(QuestState(q["id"], q["text"].format(target=q["target"]), q["stat"], q["target"],
                                     row["progress"] if row else 0, q["xp"], q["xon"],
                                     bool(row["claimed"]) if row else False))
        return states

    def quests_completed_total(self, account_id: int) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM quest_progress WHERE account_id = ? AND claimed = 1",
                                  (account_id,), 0))

    def milestones(self, account_id: int) -> list[dict]:
        stats = self.stats(account_id)
        stats["quests_done"] = self.quests_completed_total(account_id)
        result = []
        for m in self.quest_data["milestones"]:
            progress = int(stats.get(m["stat"], 0))
            result.append({**m, "progress": min(progress, m["target"]),
                           "claimed": self.is_claimed(account_id, "ms:" + m["id"])})
        return result

    def _sync_milestones(self, account_id: int, out: MatchRewards | None) -> None:
        for m in self.milestones(account_id):
            if m["progress"] >= m["target"] and self._claim_once(account_id, "ms:" + m["id"]):
                self._give(account_id, m["reward"], f"Milestone: {m['text']}", out)

    # -- match pipeline -------------------------------------------------
    def apply_match(self, account_id: int, summary: MatchSummary,
                    date: dt.date | None = None) -> MatchRewards:
        out = MatchRewards(level_before=self.level(account_id))
        with self.db.transaction():
            self.db.execute(
                "UPDATE stats SET matches = matches + 1, wins = wins + ?, top10 = top10 + ?, "
                "eliminations = eliminations + ?, damage_dealt = damage_dealt + ?, "
                "chests_opened = chests_opened + ?, time_alive = time_alive + ? WHERE account_id = ?",
                (int(summary.won), int(summary.top10), summary.eliminations, summary.damage, summary.chests,
                 summary.survive_secs, account_id))

            out.lines.extend(match_xp_and_xon(summary))

            stat_values = {"matches": 1, "eliminations": summary.eliminations, "chests": summary.chests,
                           "damage": summary.damage, "top10": int(summary.top10),
                           "survive_secs": int(summary.survive_secs), "healed": summary.healed,
                           "pickaxe_hits": summary.pickaxe_hits, "glide_secs": int(summary.glide_secs),
                           "sniper_hits": summary.sniper_hits}
            period = self.period(date)
            for quest in self.daily_quests(account_id, date):
                if quest.claimed:
                    continue
                progress = min(quest.target, quest.progress + stat_values.get(quest.stat, 0))
                done = progress >= quest.target
                self.db.execute(
                    "INSERT INTO quest_progress(account_id, quest_id, period, progress, claimed) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(account_id, quest_id, period) DO UPDATE SET progress = excluded.progress, "
                    "claimed = excluded.claimed", (account_id, quest.id, period, progress, int(done)))
                if done:
                    out.completed_quests.append(quest.text)
                    out.lines.append(RewardLine(f"Quest: {quest.text}", xp=quest.xp, xon=quest.xon))

            xon_total = sum(l.xon for l in out.lines)
            xp_total = sum(l.xp for l in out.lines)
            if xon_total:
                self.wallet.credit(account_id, xon_total, f"Match reward (#{summary.placement})")
            self.add_xp(account_id, xp_total, out)
            self._sync_milestones(account_id, out)
            self.db.execute(
                "INSERT INTO match_history(account_id, placement, players, eliminations, damage, xon_earned, "
                "xp_earned, duration, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (account_id, summary.placement, summary.players, summary.eliminations, summary.damage,
                 out.xon, xp_total, summary.duration, now()))
        out.level_after = self.level(account_id)
        return out

    def recent_matches(self, account_id: int, limit: int = 10) -> list[dict]:
        return [dict(r) for r in self.db.all("SELECT * FROM match_history WHERE account_id = ? "
                                             "ORDER BY id DESC LIMIT ?", (account_id, limit))]
