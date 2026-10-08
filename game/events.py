"""Seasonal / limited-time events driven entirely by ``data/events.json``.

An event has a date window (MM-DD, may wrap over new year), a theme
(tint, decor, weather), its own currency that spawns during runs, event
missions and a reward track.  Adding a new event = adding a JSON entry.
For testing, set ``"force_event": "<event id>"`` in ``saves/settings.json``
(or data/settings.json for the default).
"""
import datetime

from .utils import today


def _mmdd(text):
    m, d = (int(x) for x in text.split("-"))
    return m, d


def event_window(event, on):
    """Return (start_date, end_date) of the event occurrence relevant to ``on``."""
    sm, sd = _mmdd(event["start"])
    em, ed = _mmdd(event["end"])

    def mk(year, m, d):
        try:
            return datetime.date(year, m, d)
        except ValueError:  # e.g. 02-29 on a non-leap year
            return datetime.date(year, m, 28)

    wraps = (em, ed) < (sm, sd)
    for year in (on.year - 1, on.year, on.year + 1):
        start = mk(year, sm, sd)
        end = mk(year + 1 if wraps else year, em, ed)
        if start <= on <= end:
            return start, end
    # not active: return the next occurrence
    start = mk(on.year, sm, sd)
    if start < on:
        start = mk(on.year + 1, sm, sd)
    end = mk(start.year + 1 if wraps else start.year, em, ed)
    return start, end


class EventManager:
    def __init__(self, gamedata, save, settings, economy, progression):
        self.gamedata = gamedata
        self.save = save
        self.settings = settings
        self.economy = economy
        self.progression = progression

    def is_active(self, event, on=None):
        on = on or today()
        start, end = event_window(event, on)
        return start <= on <= end

    def active(self, on=None):
        forced = self.settings.get("force_event", "")
        if forced:
            ev = self.gamedata.event_by_id.get(forced)
            if ev:
                return ev
        for ev in self.gamedata.events:
            if self.is_active(ev, on):
                return ev
        return None

    def days_left(self, event, on=None):
        on = on or today()
        _, end = event_window(event, on)
        return max(0, (end - on).days)

    def upcoming(self, on=None):
        on = on or today()
        out = []
        for ev in self.gamedata.events:
            if self.is_active(ev, on):
                continue
            start, _ = event_window(ev, on)
            out.append((start, ev))
        out.sort(key=lambda x: x[0])
        return out

    # ------------------------------------------------------------------
    def _state(self, event):
        evs = self.save["events"]
        st = evs.get(event["id"])
        if not isinstance(st, dict):
            st = {"tokens": 0, "earned": 0, "claimed": []}
            evs[event["id"]] = st
        st.setdefault("tokens", 0)
        st.setdefault("earned", st["tokens"])  # saves from before currencies became spendable
        st.setdefault("claimed", [])
        return st

    def tokens(self, event):
        """Spendable balance (e.g. Candy to buy the Halloween character)."""
        return self._state(event)["tokens"]

    def earned(self, event):
        """Lifetime amount collected - drives the reward track, never goes down."""
        return self._state(event)["earned"]

    def add_tokens(self, event, n):
        st = self._state(event)
        st["tokens"] += n
        st["earned"] += n
        self.save.mark_dirty()

    def spend_tokens(self, event, n):
        st = self._state(event)
        if n < 0 or st["tokens"] < n:
            return False
        st["tokens"] -= n
        self.save.mark_dirty()
        return True

    def reward_status(self, event, index):
        """'claimed' | 'ready' | 'locked'"""
        st = self._state(event)
        if index in st["claimed"]:
            return "claimed"
        if st["earned"] >= event["rewards"][index]["tokens"]:
            return "ready"
        return "locked"

    def claim(self, event, index):
        if self.reward_status(event, index) != "ready":
            return None
        st = self._state(event)
        st["claimed"].append(index)
        lines = self.economy.grant(event["rewards"][index]["reward"], self.progression)
        self.save.save()
        return lines

    def claimable_count(self):
        ev = self.active()
        if not ev:
            return 0
        return sum(1 for i in range(len(ev["rewards"])) if self.reward_status(ev, i) == "ready")
