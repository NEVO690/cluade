"""In-match inventory: pickaxe + five item slots, ammo reserves."""
from __future__ import annotations

from dataclasses import dataclass, field

from combat.weapons import Armory, WeaponInstance

SLOTS = 5


@dataclass
class ConsumableStack:
    cid: str
    count: int


Item = WeaponInstance | ConsumableStack


@dataclass
class MatchInventory:
    armory: Armory
    slots: list[Item | None] = field(default_factory=lambda: [None] * SLOTS)
    ammo: dict[str, int] = field(default_factory=dict)
    selected: int = 0            # 0 = pickaxe, 1..5 = slots

    @property
    def current(self) -> Item | None:
        return None if self.selected == 0 else self.slots[self.selected - 1]

    def select(self, index: int) -> bool:
        if 0 <= index <= SLOTS and index != self.selected:
            self.selected = index
            return True
        return False

    def cycle(self, step: int) -> None:
        order = [0] + [i + 1 for i in range(SLOTS) if self.slots[i] is not None]
        if self.selected not in order:
            self.selected = 0
        self.selected = order[(order.index(self.selected) + step) % len(order)]

    def free_slot(self) -> int | None:
        for i, s in enumerate(self.slots):
            if s is None:
                return i
        return None

    def add_ammo(self, kind: str, amount: int) -> int:
        cap = self.armory.ammo[kind]["max"]
        have = self.ammo.get(kind, 0)
        taken = max(0, min(amount, cap - have))
        self.ammo[kind] = have + taken
        return taken

    def add_consumable(self, cid: str, count: int) -> int:
        """Merge into an existing stack first, then a free slot. Returns how many were taken."""
        cap = self.armory.consumables[cid].stack
        taken = 0
        for s in self.slots:
            if isinstance(s, ConsumableStack) and s.cid == cid and s.count < cap:
                n = min(count - taken, cap - s.count)
                s.count += n
                taken += n
        while taken < count:
            i = self.free_slot()
            if i is None:
                break
            n = min(count - taken, cap)
            self.slots[i] = ConsumableStack(cid, n)
            taken += n
        return taken

    def add_weapon(self, weapon: WeaponInstance) -> tuple[bool, Item | None]:
        """Put a weapon in a free slot, or swap with the held slot. Returns (taken, dropped item)."""
        i = self.free_slot()
        if i is not None:
            self.slots[i] = weapon
            if self.selected == 0:
                self.selected = i + 1
            return True, None
        if self.selected == 0:
            return False, None
        dropped = self.slots[self.selected - 1]
        self.slots[self.selected - 1] = weapon
        return True, dropped

    def remove_current(self) -> Item | None:
        if self.selected == 0:
            return None
        item = self.slots[self.selected - 1]
        self.slots[self.selected - 1] = None
        self.selected = 0
        return item

    def weapons(self) -> list[tuple[int, WeaponInstance]]:
        return [(i + 1, s) for i, s in enumerate(self.slots) if isinstance(s, WeaponInstance)]

    def consumables(self) -> list[tuple[int, ConsumableStack]]:
        return [(i + 1, s) for i, s in enumerate(self.slots) if isinstance(s, ConsumableStack)]

    def total_loot(self) -> list[Item]:
        return [s for s in self.slots if s is not None]
