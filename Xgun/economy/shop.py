"""XON Shop with a deterministic daily rotation.

The rotation is derived from the calendar date so every launch on the same
day shows the same storefront, and a future online service could compute
the identical rotation server-side.
"""
from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass

from economy.wallet import InsufficientFunds, Wallet
from inventory.catalog import Catalog, CosmeticItem
from inventory.locker import Locker

FEATURED_COUNT = 2
DAILY_COUNT = 6


class PurchaseError(Exception):
    pass


@dataclass
class Storefront:
    date: dt.date
    featured: list[CosmeticItem]
    daily: list[CosmeticItem]

    @property
    def all(self) -> list[CosmeticItem]:
        return self.featured + self.daily

    def seconds_until_refresh(self, moment: dt.datetime | None = None) -> int:
        moment = moment or dt.datetime.now()
        tomorrow = dt.datetime.combine(moment.date() + dt.timedelta(days=1), dt.time())
        return int((tomorrow - moment).total_seconds())


class Shop:
    def __init__(self, catalog: Catalog, wallet: Wallet, locker: Locker):
        self.catalog = catalog
        self.wallet = wallet
        self.locker = locker

    def storefront(self, date: dt.date | None = None) -> Storefront:
        date = date or dt.date.today()
        rng = random.Random(date.toordinal() * 7919)
        pool = sorted(self.catalog.shop_items(), key=lambda i: i.id)
        big = [i for i in pool if i.type in ("outfit", "glider") or i.rarity in ("epic", "legendary")]
        featured = rng.sample(big, min(FEATURED_COUNT, len(big)))
        rest = [i for i in pool if i not in featured]
        daily = rng.sample(rest, min(DAILY_COUNT, len(rest)))
        daily.sort(key=lambda i: (-self.catalog.rarity(i).order, i.name))
        return Storefront(date, featured, daily)

    def can_buy(self, account_id: int, item_id: str) -> tuple[bool, str]:
        item = self.catalog.get(item_id)
        if not item.purchasable:
            return False, "This item can't be bought with XON."
        if self.locker.owns(account_id, item_id):
            return False, "Already owned."
        if self.wallet.balance(account_id) < item.price:
            return False, f"Not enough XON (need {item.price:,})."
        return True, ""

    def purchase(self, account_id: int, item_id: str, *, require_in_rotation: bool = True,
                 date: dt.date | None = None) -> int:
        """Buy an item. Returns the new balance. Atomic: never charges without granting."""
        item = self.catalog.get(item_id)
        if require_in_rotation and item not in self.storefront(date).all:
            raise PurchaseError(f"{item.name} isn't in today's shop.")
        ok, reason = self.can_buy(account_id, item_id)
        if not ok:
            raise PurchaseError(reason)
        with self.wallet.db.transaction():
            try:
                balance = self.wallet.debit(account_id, item.price, f"Bought {item.name}", item_id=item.id)
            except InsufficientFunds as exc:
                raise PurchaseError(str(exc)) from exc
            self.locker.grant(account_id, item.id, "shop")
        return balance
