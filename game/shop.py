"""Economy (coins, gems, ownership, rewards) and the shop catalogue.

There are NO real-money purchases: coins are earned by running and gems by
missions, achievements, levels, daily rewards and rare pickups.
"""
from .save_system import OWNERSHIP_KEYS
from .utils import fmt_int

CURRENCIES = ("coins", "gems")

SHOP_TABS = [
    ("characters", "Characters"),
    ("powerups", "Power-Ups"),
    ("upgrades", "Upgrades"),
    ("boards", "Boards"),
    ("cosmetics", "Cosmetics"),
    ("trails", "Trails"),
]

CATEGORY_ICONS = {"characters": "character", "boards": "board", "outfits": "outfit", "trails": "trail",
                  "effects": "effect", "emotes": "emote", "consumables": "cart"}


class Economy:
    def __init__(self, gamedata, save):
        self.gamedata = gamedata
        self.save = save
        self.listeners = []  # callables(kind, data) for UI notifications

    def notify(self, kind, data):
        for fn in self.listeners:
            try:
                fn(kind, data)
            except Exception:  # a broken listener must never break the economy
                pass

    # ------------------------------------------------------------------
    # Currency
    # ------------------------------------------------------------------
    @property
    def coins(self):
        return self.save["coins"]

    @property
    def gems(self):
        return self.save["gems"]

    def add(self, currency, amount):
        if currency in CURRENCIES and amount:
            self.save[currency] = max(0, int(self.save[currency] + amount))

    def can_afford(self, price, currency="coins"):
        return self.save.get(currency, 0) >= price

    def spend(self, price, currency="coins"):
        if price < 0 or currency not in CURRENCIES or not self.can_afford(price, currency):
            return False
        self.save[currency] = self.save[currency] - price
        return True

    # ------------------------------------------------------------------
    # Ownership
    # ------------------------------------------------------------------
    def owned(self, category, item_id):
        if category == "consumables":
            return False
        key = OWNERSHIP_KEYS.get(category)
        return bool(key) and item_id in self.save[key[0]]

    def unlock(self, category, item_id):
        key = OWNERSHIP_KEYS.get(category)
        if key and item_id not in self.save[key[0]]:
            self.save[key[0]].append(item_id)
            self.save.mark_dirty()
            return True
        return False

    def equipped(self, category):
        key = OWNERSHIP_KEYS.get(category)
        return self.save[key[1]] if key else None

    def equip(self, category, item_id):
        if not self.owned(category, item_id):
            return False
        self.save[OWNERSHIP_KEYS[category][1]] = item_id
        return True

    def item_locked_by_level(self, item):
        return item.get("category") == "characters" and self.save["level"] < item.get("unlock_level", 1)

    def purchase(self, item):
        """Buy a character/cosmetic/consumable. Returns (ok, message)."""
        cat = item.get("category")
        if item.get("event_only"):
            return False, "Event reward only"
        if cat != "consumables" and self.owned(cat, item["id"]):
            return False, "Already owned"
        if self.item_locked_by_level(item):
            return False, f"Reach level {item['unlock_level']}"
        price, cur = item.get("price", 0), item.get("currency", "coins")
        if not self.spend(price, cur):
            return False, f"Not enough {cur}"
        if cat == "consumables":
            self.add_consumable(item["id"], 1)
        else:
            self.unlock(cat, item["id"])
        self.save.mark_dirty()
        self.save.save()
        return True, f"Bought {item['name']}!"

    # ------------------------------------------------------------------
    # Consumables
    # ------------------------------------------------------------------
    def consumable(self, cid):
        return self.save["consumables"].get(cid, 0)

    def add_consumable(self, cid, n=1):
        self.save["consumables"][cid] = self.consumable(cid) + n
        self.save.mark_dirty()

    def use_consumable(self, cid):
        if self.consumable(cid) <= 0:
            return False
        self.save["consumables"][cid] -= 1
        self.save.mark_dirty()
        return True

    # ------------------------------------------------------------------
    # Upgrades
    # ------------------------------------------------------------------
    def upgrade_level(self, pid):
        return self.save["upgrades"].get(pid, 0)

    def upgrade_cost(self, pid):
        pu = self.gamedata.powerup_by_id.get(pid)
        if not pu or not pu.get("upgradeable"):
            return None
        lvl = self.upgrade_level(pid)
        costs = pu["upgrade_costs"]
        return costs[lvl] if lvl < len(costs) else None

    def max_upgrade_level(self, pid):
        pu = self.gamedata.powerup_by_id.get(pid)
        return len(pu["upgrade_costs"]) if pu else 0

    def buy_upgrade(self, pid):
        cost = self.upgrade_cost(pid)
        if cost is None:
            return False, "Max level"
        if not self.spend(cost, "coins"):
            return False, "Not enough coins"
        self.save["upgrades"][pid] = self.upgrade_level(pid) + 1
        self.save.mark_dirty()
        self.save.save()
        return True, f"Upgraded to level {self.upgrade_level(pid) + 1}!"

    # ------------------------------------------------------------------
    # Rewards (shared by missions, achievements, levels, daily, events)
    # ------------------------------------------------------------------
    def grant(self, reward, progression=None):
        if not reward:
            return []
        lines = []
        if reward.get("coins"):
            self.add("coins", reward["coins"])
            lines.append(f"+{fmt_int(reward['coins'])} coins")
        if reward.get("gems"):
            self.add("gems", reward["gems"])
            lines.append(f"+{reward['gems']} gems")
        for cid, n in reward.get("consumable", {}).items():
            if n > 0:
                self.add_consumable(cid, n)
                item = self.gamedata.item(cid)
                lines.append(f"+{n} {item['name'] if item else cid}")
        if reward.get("item"):
            item = self.gamedata.item(reward["item"])
            if item and self.unlock(item["category"], item["id"]):
                lines.append(f"Unlocked {item['name']}")
            elif item:
                bonus = 500
                self.add("coins", bonus)
                lines.append(f"{item['name']} (owned) +{bonus} coins")
        if reward.get("xp") and progression is not None:
            progression.add_xp(reward["xp"])
            lines.append(f"+{reward['xp']} XP")
        self.save.mark_dirty()
        return lines

    def reward_text(self, reward):
        parts = []
        if reward.get("coins"):
            parts.append(f"{fmt_int(reward['coins'])} coins")
        if reward.get("gems"):
            parts.append(f"{reward['gems']} gems")
        if reward.get("xp"):
            parts.append(f"{reward['xp']} XP")
        for cid, n in reward.get("consumable", {}).items():
            item = self.gamedata.item(cid)
            parts.append(f"{n}x {item['name'] if item else cid}")
        if reward.get("item"):
            item = self.gamedata.item(reward["item"])
            parts.append(item["name"] if item else reward["item"])
        return ", ".join(parts) if parts else "-"


class ShopEntry:
    """A display-ready row for the shop UI."""
    __slots__ = ("id", "name", "desc", "price", "currency", "icon", "color", "category", "owned", "equipped",
                 "action", "status", "item", "locked")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


class Shop:
    def __init__(self, gamedata, economy):
        self.gamedata = gamedata
        self.economy = economy

    def entries(self, tab):
        eco = self.economy
        gd = self.gamedata
        out = []
        if tab == "characters":
            for c in gd.characters:
                item = gd.item(c["id"])
                out.append(self._item_entry(item, "character", c["colors"]["shirt"]))
        elif tab in ("boards", "trails"):
            for it in gd.items[tab]:
                if it.get("event_only") and not eco.owned(tab, it["id"]):
                    continue
                color = it["colors"]["deck"] if tab == "boards" else it.get("color", (255, 255, 255))
                out.append(self._item_entry(it, CATEGORY_ICONS[tab], color))
        elif tab == "cosmetics":
            for cat in ("outfits", "effects", "emotes"):
                for it in gd.items[cat]:
                    if it.get("event_only") and not eco.owned(cat, it["id"]):
                        continue
                    color = it.get("colors", {}).get("shirt") or it.get("color") or (255, 200, 80)
                    out.append(self._item_entry(it, CATEGORY_ICONS[cat], color))
        elif tab == "powerups":
            for it in gd.items["consumables"]:
                n = eco.consumable(it["id"])
                out.append(ShopEntry(id=it["id"], name=it["name"], desc=it["desc"], price=it["price"],
                                     currency=it["currency"], icon=it.get("icon", "cart"), color=(255, 200, 60),
                                     category="consumables", owned=False, equipped=False, action="buy",
                                     status=f"Owned: {n}", item=it, locked=False))
        elif tab == "upgrades":
            for pu in gd.powerups:
                if not pu.get("upgradeable"):
                    continue
                lvl = eco.upgrade_level(pu["id"])
                cost = eco.upgrade_cost(pu["id"])
                dur = pu["durations"][min(lvl, len(pu["durations"]) - 1)]
                out.append(ShopEntry(id=pu["id"], name=pu["name"], desc=f"{pu['desc']} ({dur:g}s)",
                                     price=cost or 0, currency="coins", icon=pu["icon"], color=pu["color"],
                                     category="upgrades", owned=cost is None, equipped=False,
                                     action="upgrade" if cost is not None else None,
                                     status=f"Level {lvl + 1}/{eco.max_upgrade_level(pu['id']) + 1}",
                                     item=pu, locked=False))
        return out

    def _item_entry(self, item, icon, color):
        eco = self.economy
        cat = item["category"]
        owned = eco.owned(cat, item["id"])
        equipped = owned and eco.equipped(cat) == item["id"]
        locked = eco.item_locked_by_level(item)
        if equipped:
            action, status = None, "Equipped"
        elif owned:
            action, status = "equip", "Owned"
        elif item.get("event_only"):
            action, status = None, "Event reward"
        elif locked:
            action, status = None, f"Level {item['unlock_level']}"
        else:
            action, status = "buy", "Not owned"
        desc = item.get("desc") or item.get("description", "")
        if cat == "characters":
            desc = f"{item.get('description', '')} Ability: {item['ability'].get('desc', '')}"
        elif cat == "boards":
            desc = f"{item.get('desc', '')} Perk: {item['perk'].get('desc', '')}"
        return ShopEntry(id=item["id"], name=item["name"], desc=desc, price=item.get("price", 0),
                         currency=item.get("currency", "coins"), icon=icon, color=color, category=cat,
                         owned=owned, equipped=equipped, action=action, status=status, item=item, locked=locked)

    def act(self, entry):
        """Perform the entry's action. Returns (ok, message)."""
        eco = self.economy
        if entry.action == "buy":
            ok, msg = eco.purchase(entry.item)
            if ok and entry.category not in ("consumables",):
                eco.equip(entry.category, entry.id)
            return ok, msg
        if entry.action == "equip":
            eco.equip(entry.category, entry.id)
            eco.save.save()
            return True, f"Equipped {entry.name}"
        if entry.action == "upgrade":
            return eco.buy_upgrade(entry.id)
        return False, entry.status or ""
