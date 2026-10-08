"""Limited-time shop offers (``data/offers.json``).

The offer window opens the first time the player starts this version of the
game and lasts ``duration_days``; when the countdown reaches zero the offers
disappear from the shop.  Each offer can be bought once.

Offer types:
* ``item``  - unlock an item or character (``item`` = id) for the given price
* ``level`` - boost the player straight to ``level`` (granting every level reward)
"""
import datetime


class Offers:
    def __init__(self, gamedata, save, economy, progression):
        self.gamedata = gamedata
        self.save = save
        self.economy = economy
        self.progression = progression

    def _state(self, now=None):
        st = self.save["offers"]
        if not st.get("start"):
            st["start"] = (now or datetime.datetime.now()).isoformat(timespec="seconds")
            self.save.mark_dirty()
        st.setdefault("bought", [])
        return st

    def start(self, now=None):
        try:
            return datetime.datetime.fromisoformat(self._state(now)["start"])
        except ValueError:
            self.save["offers"]["start"] = ""
            return datetime.datetime.fromisoformat(self._state(now)["start"])

    def end(self, now=None):
        return self.start(now) + datetime.timedelta(days=self.gamedata.offer_days)

    def time_left(self, now=None):
        now = now or datetime.datetime.now()
        return max(datetime.timedelta(0), self.end(now) - now)

    def active(self, now=None):
        return bool(self.gamedata.offers) and self.time_left(now) > datetime.timedelta(0)

    def list(self, now=None):
        return list(self.gamedata.offers) if self.active(now) else []

    def status(self, offer):
        """'bought' | 'owned' (already have it) | 'available'"""
        if offer["id"] in self._state()["bought"]:
            return "bought"
        if offer["type"] == "item":
            item = self.gamedata.item(offer["item"])
            if item and self.economy.owned(item["category"], item["id"]):
                return "owned"
        elif offer["type"] == "level" and self.progression.level >= offer["level"]:
            return "owned"
        return "available"

    def available_count(self, now=None):
        return sum(1 for o in self.list(now) if self.status(o) == "available")

    def buy(self, offer, now=None):
        if not self.active(now):
            return False, "This offer has expired"
        st = self.status(offer)
        if st == "bought":
            return False, "Already bought"
        if st == "owned":
            return False, "You already have this"
        if not self.economy.spend(offer["price"], offer["currency"]):
            return False, f"Not enough {self.economy.currency_name(offer['currency'])}"
        self._state()["bought"].append(offer["id"])
        if offer["type"] == "item":
            item = self.gamedata.item(offer["item"])
            self.economy.unlock(item["category"], item["id"])
            self.economy.equip(item["category"], item["id"])
            msg = f"{item['name']} unlocked!"
        else:
            gained = self.progression.boost_to(offer["level"])
            msg = f"Boosted to level {self.progression.level}! (+{len(gained)} levels)"
        self.save.mark_dirty()
        self.save.save()
        return True, msg
