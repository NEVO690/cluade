"""The shop: buying skins with BONK COINS.

Guarantees:
  * you cannot buy without enough coins or before meeting the unlock rules;
  * buying something you already own never charges again (double clicks are safe);
  * the purchase is only reported as successful after it was saved to disk;
    if saving fails the coins and the skin are rolled back.
"""

from dataclasses import dataclass

from .currency_manager import InsufficientFunds


@dataclass
class PurchaseResult:
    ok: bool
    code: str  # purchased / already_owned / insufficient_funds / locked / unknown_item / busy / save_failed
    message: str
    balance: int


class ShopManager:
    def __init__(self, profile):
        self.profile = profile
        self._busy = False

    def price_of(self, skin_id):
        return self.profile.catalog.get(skin_id).price

    def can_afford(self, skin_id):
        return self.profile.currency.balance >= self.price_of(skin_id)

    def purchase(self, skin_id):
        prof = self.profile
        bal = prof.currency.balance
        if self._busy:
            return PurchaseResult(False, "busy", "Purchase already in progress.", bal)
        if skin_id not in prof.catalog:
            return PurchaseResult(False, "unknown_item", "That item does not exist.", bal)
        skin = prof.catalog.get(skin_id)
        if prof.skins.is_owned(skin_id):
            return PurchaseResult(False, "already_owned", "You already own %s." % skin.name, bal)
        reasons = prof.unmet_skin_requirements(skin_id)
        if reasons:
            return PurchaseResult(False, "locked", "Locked: " + "; ".join(reasons), bal)
        if bal < skin.price:
            return PurchaseResult(False, "insufficient_funds",
                                  "Not enough BONK COINS (%d more needed)." % (skin.price - bal), bal)
        self._busy = True
        tx_id = "buy:%s" % skin_id  # one purchase per skin, ever
        try:
            try:
                prof.currency.spend(skin.price, "Bought %s" % skin.name, tx_id)
            except InsufficientFunds:
                return PurchaseResult(False, "insufficient_funds", "Not enough BONK COINS.", bal)
            prof.skins.grant(skin_id)
            prof.refresh_unlocks()
            if not prof.save():
                # Undo everything so the UI never shows an unsaved purchase.
                w = prof.store.data["wallet"]
                w["coins"] = bal
                if w["ledger"] and w["ledger"][-1]["id"] == tx_id:
                    w["ledger"].pop()
                if tx_id in w["processed"]:
                    w["processed"].remove(tx_id)
                prof.skins.revoke(skin_id)
                return PurchaseResult(False, "save_failed",
                                      "Could not save the purchase; nothing was charged.", bal)
            return PurchaseResult(True, "purchased", "Purchased %s!" % skin.name, prof.currency.balance)
        finally:
            self._busy = False
