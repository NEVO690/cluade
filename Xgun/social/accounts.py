"""Local player accounts.

Xgun currently runs fully offline: every account lives in the local
database. Several accounts can exist on one PC (for testing friends,
follows and comments) and one of them is the *active* account.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from save_system.database import Database, now

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
AVATAR_COLORS = ["#7C4DFF", "#00C2FF", "#FF4D8D", "#FFB020", "#2EE59D", "#FF6B3D", "#B388FF", "#4DD0E1"]


class AccountError(ValueError):
    pass


@dataclass
class Account:
    id: int
    username: str
    display_name: str
    bio: str
    avatar_color: str
    is_demo: bool
    private_account: bool
    allow_comments: bool
    created_at: float

    @classmethod
    def from_row(cls, row) -> "Account":
        return cls(row["id"], row["username"], row["display_name"], row["bio"], row["avatar_color"],
                   bool(row["is_demo"]), bool(row["private_account"]), bool(row["allow_comments"]),
                   row["created_at"])

    @property
    def handle(self) -> str:
        return "@" + self.username


class AccountService:
    def __init__(self, db: Database):
        self.db = db
        self._listeners = []

    def on_created(self, callback) -> None:
        """Register ``callback(account_id)`` run inside the creation transaction."""
        self._listeners.append(callback)

    def create(self, username: str, display_name: str | None = None, *, is_demo: bool = False,
               bio: str = "") -> Account:
        username = username.strip()
        if not USERNAME_RE.match(username):
            raise AccountError("Usernames need 3-16 letters, numbers or underscores.")
        if self.find_by_username(username):
            raise AccountError(f"The username '{username}' is already taken on this PC.")
        display = (display_name or username).strip()[:24] or username
        count = self.db.scalar("SELECT COUNT(*) FROM accounts", default=0)
        with self.db.transaction():
            cur = self.db.execute(
                "INSERT INTO accounts(username, display_name, bio, avatar_color, is_demo, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (username, display, bio[:150], AVATAR_COLORS[count % len(AVATAR_COLORS)], int(is_demo), now()))
            account_id = cur.lastrowid
            self.db.execute("INSERT INTO stats(account_id) VALUES (?)", (account_id,))
            for callback in self._listeners:
                callback(account_id)
        return self.get(account_id)

    def get(self, account_id: int) -> Account:
        row = self.db.one("SELECT * FROM accounts WHERE id = ?", (account_id,))
        if row is None:
            raise AccountError(f"Unknown account {account_id}")
        return Account.from_row(row)

    def find_by_username(self, username: str) -> Account | None:
        row = self.db.one("SELECT * FROM accounts WHERE username = ?", (username.strip(),))
        return Account.from_row(row) if row else None

    def list(self, *, include_demo: bool = True) -> list[Account]:
        sql = "SELECT * FROM accounts" + ("" if include_demo else " WHERE is_demo = 0") + " ORDER BY id"
        return [Account.from_row(r) for r in self.db.all(sql)]

    def search(self, text: str, limit: int = 20) -> list[Account]:
        pattern = f"%{text.strip()}%"
        rows = self.db.all("SELECT * FROM accounts WHERE username LIKE ? OR display_name LIKE ? "
                           "ORDER BY is_demo, username LIMIT ?", (pattern, pattern, limit))
        return [Account.from_row(r) for r in rows]

    def update_profile(self, account_id: int, *, display_name: str | None = None, bio: str | None = None,
                       private_account: bool | None = None, allow_comments: bool | None = None) -> Account:
        acc = self.get(account_id)
        self.db.execute(
            "UPDATE accounts SET display_name = ?, bio = ?, private_account = ?, allow_comments = ? WHERE id = ?",
            ((display_name if display_name is not None else acc.display_name).strip()[:24] or acc.username,
             (bio if bio is not None else acc.bio)[:150],
             int(acc.private_account if private_account is None else private_account),
             int(acc.allow_comments if allow_comments is None else allow_comments),
             account_id))
        return self.get(account_id)

    # -- active account -------------------------------------------------
    @property
    def active_id(self) -> int | None:
        value = self.db.get_state("active_account")
        return int(value) if value else None

    def set_active(self, account_id: int) -> Account:
        account = self.get(account_id)
        self.db.set_state("active_account", str(account_id))
        return account

    def active(self) -> Account:
        if self.active_id is None:
            raise AccountError("No active account")
        return self.get(self.active_id)
