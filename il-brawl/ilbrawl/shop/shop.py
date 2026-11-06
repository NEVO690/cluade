"""In-game shop using fictional currencies only (coins and gems)."""
import random

from ilbrawl.progression.profile import today_str


def _price_scaled(price, factor):
    return {k: max(1, int(round(v * factor))) for k, v in price.items()}


class Shop:
    def __init__(self, profile):
        self.profile = profile
        self.gd = profile.gd
        self.refresh_daily()

    # ------------------------------------------------------------ catalog
    def character_items(self):
        out = []
        for cid in self.gd.char_order:
            c = self.gd.characters[cid]
            u = c["unlock"]
            if u["type"] in ("coins", "gems"):
                out.append({"kind": "character", "id": cid, "price": {u["type"]: u["value"]},
                            "owned": self.profile.is_unlocked(cid)})
        return out

    def skin_items(self):
        return [{"kind": "skin", "id": s["id"], "char": s["char"], "price": s["price"],
                 "owned": s["id"] in self.profile.data["skins_owned"]}
                for s in self.gd.skins.values()]

    def cosmetic_items(self):
        out = []
        owned = self.profile.data["cosmetics_owned"]
        for group in ("icons", "titles", "name_colors"):
            for c in self.gd.cosmetics.get(group, []):
                if sum(c["price"].values()) == 0:
                    continue
                out.append({"kind": "cosmetic", "group": group, "id": c["id"], "price": c["price"],
                            "owned": c["id"] in owned, "def": c})
        return out

    def coin_items(self):
        return [{"kind": "coins", "id": p["id"], "amount": p["coins"], "price": p["price"], "owned": False}
                for p in self.gd.shop.get("coin_packs", [])]

    def special_items(self):
        out = []
        bought = self.profile.data["shop"]["bought_once"]
        for o in self.gd.shop.get("special_offers", []):
            out.append({"kind": "bundle", "id": o["id"], "contents": o["contents"], "price": o["price"],
                        "once": o.get("once", False), "owned": o.get("once", False) and o["id"] in bought})
        return out

    # ------------------------------------------------------------ daily offers
    def refresh_daily(self):
        sd = self.profile.data["shop"]
        today = today_str()
        if sd.get("date") == today and sd.get("daily_offers"):
            return
        rng = random.Random("shop-" + today)
        disc = 1.0 - self.gd.shop.get("daily_discount", 0.3)
        offers = [{"kind": "gift", "id": "daily_gift", "contents": [{"type": "coins", "amount": 30}],
                   "price": {}}]
        pool = [s for s in self.skin_items()]
        pool += [c for c in self.character_items()]
        rng.shuffle(pool)
        for item in pool[: self.gd.shop.get("daily_offer_count", 3) - 1]:
            item = dict(item)
            item["price"] = _price_scaled(item["price"], disc)
            item["discount"] = int(round((1 - disc) * 100))
            offers.append(item)
        coin = dict(rng.choice(self.coin_items()))
        coin["amount"] = int(coin["amount"] * 1.3)
        coin["bonus"] = 30
        offers.append(coin)
        sd["date"] = today
        sd["daily_offers"] = [{k: v for k, v in o.items() if k != "owned"} for o in offers]
        sd["bought_daily"] = []
        self.profile.save()

    def daily_items(self):
        sd = self.profile.data["shop"]
        out = []
        for i, o in enumerate(sd["daily_offers"]):
            o = dict(o)
            o["daily_index"] = i
            already = i in sd["bought_daily"]
            if o["kind"] == "character":
                already = already or self.profile.is_unlocked(o["id"])
            elif o["kind"] == "skin":
                already = already or o["id"] in self.profile.data["skins_owned"]
            o["owned"] = already
            out.append(o)
        return out

    # ------------------------------------------------------------ purchase
    def can_buy(self, item):
        """Return (ok, reason_key)."""
        if item.get("owned"):
            return False, "shop.owned"
        if item["kind"] == "skin":
            ch = self.gd.skins[item["id"]]["char"]
            if not self.profile.is_unlocked(ch):
                return False, "shop.need_character"
        if not self.profile.can_afford(item["price"]):
            return False, "shop.not_enough"
        return True, None

    def buy(self, item):
        ok, reason = self.can_buy(item)
        if not ok:
            return False, reason
        self.profile.spend(item["price"])
        k = item["kind"]
        p = self.profile
        if k == "character":
            p.unlock_character(item["id"])
        elif k == "skin":
            p.grant({"type": "skin", "id": item["id"]})
            p.data["skin_selected"][self.gd.skins[item["id"]]["char"]] = item["id"]
        elif k == "cosmetic":
            p.grant({"type": "cosmetic", "id": item["id"]})
        elif k == "coins":
            p.data["coins"] += item["amount"]
        elif k in ("bundle", "gift"):
            for r in item["contents"]:
                p.grant(r)
            if item.get("once"):
                p.data["shop"]["bought_once"].append(item["id"])
        if "daily_index" in item:
            p.data["shop"]["bought_daily"].append(item["daily_index"])
        p.save()
        return True, None
