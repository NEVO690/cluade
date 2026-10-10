"""XON wallet: balance plus an append-only transaction ledger."""
from __future__ import annotations

from dataclasses import dataclass

from save_system.database import Database, now

STARTER_GIFT = 1000


class InsufficientFunds(Exception):
    pass


@dataclass
class Transaction:
    id: int
    amount: int
    balance_after: int
    kind: str          # earn / spend / gift
    reason: str
    item_id: str | None
    created_at: float


class Wallet:
    def __init__(self, db: Database):
        self.db = db

    def open(self, account_id: int, starter_gift: int = STARTER_GIFT) -> None:
        with self.db.transaction():
            self.db.execute("INSERT OR IGNORE INTO wallets(account_id, balance) VALUES (?, 0)", (account_id,))
            if starter_gift:
                self.credit(account_id, starter_gift, "Welcome gift", kind="gift")

    def balance(self, account_id: int) -> int:
        return int(self.db.scalar("SELECT balance FROM wallets WHERE account_id = ?", (account_id,), 0))

    def credit(self, account_id: int, amount: int, reason: str, *, kind: str = "earn",
               item_id: str | None = None) -> int:
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
        return self._apply(account_id, int(amount), kind, reason, item_id)

    def debit(self, account_id: int, amount: int, reason: str, *, item_id: str | None = None) -> int:
        if amount <= 0:
            raise ValueError("Debit amount must be positive")
        return self._apply(account_id, -int(amount), "spend", reason, item_id)

    def _apply(self, account_id: int, delta: int, kind: str, reason: str, item_id: str | None) -> int:
        with self.db.transaction():
            current = self.db.scalar("SELECT balance FROM wallets WHERE account_id = ?", (account_id,))
            if current is None:
                self.db.execute("INSERT INTO wallets(account_id, balance) VALUES (?, 0)", (account_id,))
                current = 0
            new_balance = current + delta
            if new_balance < 0:
                raise InsufficientFunds(f"Need {-delta} XON but only {current} available")
            self.db.execute("UPDATE wallets SET balance = ? WHERE account_id = ?", (new_balance, account_id))
            self.db.execute(
                "INSERT INTO transactions(account_id, amount, balance_after, kind, reason, item_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (account_id, delta, new_balance, kind, reason, item_id, now()))
            return new_balance

    def history(self, account_id: int, limit: int = 50) -> list[Transaction]:
        rows = self.db.all("SELECT * FROM transactions WHERE account_id = ? ORDER BY id DESC LIMIT ?",
                           (account_id, limit))
        return [Transaction(r["id"], r["amount"], r["balance_after"], r["kind"], r["reason"], r["item_id"],
                            r["created_at"]) for r in rows]
