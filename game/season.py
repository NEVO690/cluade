"""Season Pass: a 30-day season with 30 tiers, a free track and a premium track.

Defined in ``data/season.json``.  Each season has a start date and a length
in days; a live countdown runs to the end, after which the season closes
(no more points, purchases or claims).  Season points come from runs
(distance, coins, missions) and every ``points_per_tier`` points unlock the
next tier.  The premium track is bought with in-game coins (no real money).

Season-exclusive rewards (``"season_only": "<season id>"`` on an item or a
character) cannot be bought in the shop - only earned through the pass.
"""
import datetime

FREE, PREMIUM = "free", "premium"


class SeasonPass:
    def __init__(self, gamedata, save, economy, progression):
        self.gamedata = gamedata
        self.save = save
        self.economy = economy
        self.progression = progression

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------
    @staticmethod
    def start_dt(season):
        return datetime.datetime.combine(season["start_date"], datetime.time())

    def end_dt(self, season):
        return self.start_dt(season) + datetime.timedelta(days=season["days"])

    def current(self, now=None):
        """The season running right now, or None."""
        now = now or datetime.datetime.now()
        for s in self.gamedata.seasons:
            if self.start_dt(s) <= now < self.end_dt(s):
                return s
        return None

    def latest(self, now=None):
        """Current season, else the most recently ended one (for the 'season ended' screen)."""
        now = now or datetime.datetime.now()
        cur = self.current(now)
        if cur:
            return cur
        past = [s for s in self.gamedata.seasons if self.end_dt(s) <= now]
        return max(past, key=lambda s: s["start_date"]) if past else None

    def next_season(self, now=None):
        now = now or datetime.datetime.now()
        future = [s for s in self.gamedata.seasons if self.start_dt(s) > now]
        return min(future, key=lambda s: s["start_date"]) if future else None

    def time_left(self, season, now=None):
        now = now or datetime.datetime.now()
        return max(datetime.timedelta(0), self.end_dt(season) - now)

    def is_active(self, season, now=None):
        return self.time_left(season, now) > datetime.timedelta(0) and self.start_dt(season) <= (now or datetime.datetime.now())

    @staticmethod
    def format_left(td):
        secs = int(td.total_seconds())
        d, rem = divmod(secs, 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        return f"{d}d {h:02d}:{m:02d}:{s:02d}"

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------
    def state(self, season):
        all_st = self.save["season"]
        st = all_st.get(season["id"])
        if not isinstance(st, dict):
            st = {}
            all_st[season["id"]] = st
        st.setdefault("points", 0)
        st.setdefault("premium", False)
        st.setdefault("claimed_free", [])
        st.setdefault("claimed_premium", [])
        return st

    def points(self, season):
        return self.state(season)["points"]

    def tier(self, season):
        """Number of tiers unlocked (0..len(tiers))."""
        return min(len(season["tiers"]), self.points(season) // season["points_per_tier"])

    def tier_progress(self, season):
        """Fraction towards the next tier (1.0 when everything is unlocked)."""
        if self.tier(season) >= len(season["tiers"]):
            return 1.0
        return (self.points(season) % season["points_per_tier"]) / season["points_per_tier"]

    def run_points(self, season, distance, coins, missions):
        p = season["points"]
        return int(distance * p["per_meter"] + coins * p["per_coin"] + missions * p["per_mission"] + p["per_run"])

    def add_points(self, n, now=None):
        season = self.current(now)
        if season is None or n <= 0:
            return 0
        before = self.tier(season)
        self.state(season)["points"] += int(n)
        self.save.mark_dirty()
        gained = self.tier(season) - before
        if gained:
            self.economy.notify("season_tier", (season, self.tier(season)))
        return gained

    def has_premium(self, season):
        return bool(self.state(season)["premium"])

    def buy_premium(self, now=None):
        season = self.current(now)
        if season is None:
            return False, "The season has ended"
        if self.has_premium(season):
            return False, "Premium already unlocked"
        if not self.economy.spend(season["premium_price"], season["premium_currency"]):
            return False, f"Not enough {self.economy.currency_name(season['premium_currency'])}"
        self.state(season)["premium"] = True
        self.save.mark_dirty()
        self.save.save()
        return True, "Premium Pass unlocked!"

    # ------------------------------------------------------------------
    # Rewards
    # ------------------------------------------------------------------
    def status(self, season, index, track, now=None):
        """'claimed' | 'ready' | 'locked' | 'premium' (needs premium) | 'ended'."""
        st = self.state(season)
        if index in st["claimed_" + track]:
            return "claimed"
        if index >= self.tier(season):
            return "locked"
        if track == PREMIUM and not st["premium"]:
            return "premium"
        if not self.is_active(season, now):
            return "ended"
        return "ready"

    def claim(self, season, index, track, now=None):
        if self.status(season, index, track, now) != "ready":
            return None
        self.state(season)["claimed_" + track].append(index)
        lines = self.economy.grant(season["tiers"][index][track], self.progression)
        self.save.save()
        return lines

    def claim_all(self, season, now=None):
        lines = []
        for i in range(len(season["tiers"])):
            for track in (FREE, PREMIUM):
                got = self.claim(season, i, track, now)
                if got:
                    lines.extend(got)
        return lines

    def claimable_count(self, now=None):
        season = self.current(now)
        if not season:
            return 0
        return sum(1 for i in range(len(season["tiers"])) for t in (FREE, PREMIUM)
                   if self.status(season, i, t, now) == "ready")
