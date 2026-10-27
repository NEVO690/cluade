"""BONK COINS: a purely virtual in-game currency (no real money anywhere)."""

import time
import uuid


class InsufficientFunds(Exception):
    pass


class CurrencyManager:
    LEDGER_SIZE = 50

    def __init__(self, store):
        self.store = store  # SaveManager; data is read through it on every call

    @property
    def wallet(self):
        return self.store.data["wallet"]

    @property
    def balance(self):
        return self.wallet["coins"]

    def _record(self, amount, reason, tx_id):
        w = self.wallet
        w["ledger"].append({"id": tx_id, "amount": amount, "reason": reason, "time": int(time.time())})
        del w["ledger"][:-self.LEDGER_SIZE]
        w["processed"].append(tx_id)
        del w["processed"][:-200]

    def already_processed(self, tx_id):
        return tx_id in self.wallet["processed"]

    def earn(self, amount, reason, tx_id=None):
        """Add coins.  A transaction id that was already applied is ignored (returns False)."""
        amount = int(amount)
        if amount < 0:
            raise ValueError("earn() needs a positive amount")
        tx_id = tx_id or uuid.uuid4().hex
        if self.already_processed(tx_id):
            return False
        if amount:
            self.wallet["coins"] += amount
        self._record(amount, reason, tx_id)
        return True

    def spend(self, amount, reason, tx_id=None):
        amount = int(amount)
        if amount < 0:
            raise ValueError("spend() needs a positive amount")
        tx_id = tx_id or uuid.uuid4().hex
        if self.already_processed(tx_id):
            return False
        if self.wallet["coins"] < amount:
            raise InsufficientFunds("need %d coins, have %d" % (amount, self.wallet["coins"]))
        self.wallet["coins"] -= amount
        self._record(-amount, reason, tx_id)
        return True
