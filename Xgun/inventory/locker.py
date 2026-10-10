"""Cosmetic ownership and equipped loadout (the Locker)."""
from __future__ import annotations

from inventory.catalog import Catalog, CosmeticItem
from save_system.database import Database, now


class LockerError(ValueError):
    pass


class Locker:
    def __init__(self, db: Database, catalog: Catalog):
        self.db = db
        self.catalog = catalog

    def grant_defaults(self, account_id: int) -> None:
        with self.db.transaction():
            for item in self.catalog.defaults():
                self.grant(account_id, item.id, "default")
                self.db.execute("INSERT OR IGNORE INTO loadout(account_id, slot, item_id) VALUES (?, ?, ?)",
                                (account_id, item.type, item.id))

    def grant(self, account_id: int, item_id: str, source: str) -> bool:
        """Give an item. Returns False if it was already owned."""
        self.catalog.get(item_id)  # validates the id
        cur = self.db.execute(
            "INSERT OR IGNORE INTO owned_items(account_id, item_id, source, acquired_at) VALUES (?, ?, ?, ?)",
            (account_id, item_id, source, now()))
        return cur.rowcount > 0

    def owns(self, account_id: int, item_id: str) -> bool:
        return self.db.one("SELECT 1 FROM owned_items WHERE account_id = ? AND item_id = ?",
                           (account_id, item_id)) is not None

    def owned_ids(self, account_id: int) -> set[str]:
        return {r["item_id"] for r in self.db.all("SELECT item_id FROM owned_items WHERE account_id = ?",
                                                  (account_id,))}

    def owned(self, account_id: int, item_type: str | None = None) -> list[CosmeticItem]:
        owned = self.owned_ids(account_id)
        types = [item_type] if item_type else self.catalog.slots
        return [i for t in types for i in self.catalog.by_type(t) if i.id in owned]

    def equip(self, account_id: int, item_id: str) -> None:
        item = self.catalog.get(item_id)
        if not self.owns(account_id, item_id):
            raise LockerError(f"You don't own {item.name} yet.")
        self.db.execute("INSERT INTO loadout(account_id, slot, item_id) VALUES (?, ?, ?) "
                        "ON CONFLICT(account_id, slot) DO UPDATE SET item_id = excluded.item_id",
                        (account_id, item.type, item_id))

    def equipped(self, account_id: int) -> dict[str, str]:
        rows = self.db.all("SELECT slot, item_id FROM loadout WHERE account_id = ?", (account_id,))
        loadout = {r["slot"]: r["item_id"] for r in rows if r["item_id"] in self.catalog.items}
        for item in self.catalog.defaults():
            loadout.setdefault(item.type, item.id)
        return loadout
