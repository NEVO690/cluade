"""Friend requests and friend lists between local accounts."""
from __future__ import annotations

from dataclasses import dataclass

from save_system.database import Database, now


class FriendError(ValueError):
    pass


@dataclass
class FriendRequest:
    id: int
    from_id: int
    to_id: int
    status: str
    created_at: float


class FriendService:
    def __init__(self, db: Database):
        self.db = db

    def are_friends(self, a: int, b: int) -> bool:
        return self.db.one("SELECT 1 FROM friends WHERE account_id = ? AND friend_id = ?", (a, b)) is not None

    def pending_between(self, a: int, b: int) -> FriendRequest | None:
        row = self.db.one("SELECT * FROM friend_requests WHERE status = 'pending' AND "
                          "((from_id = ? AND to_id = ?) OR (from_id = ? AND to_id = ?))", (a, b, b, a))
        return FriendRequest(**dict(row)) if row else None

    def send_request(self, from_id: int, to_id: int) -> FriendRequest | None:
        """Send a request. If the other player already asked us, this accepts it instead
        and returns None."""
        if from_id == to_id:
            raise FriendError("You can't add yourself.")
        if self.are_friends(from_id, to_id):
            raise FriendError("You're already friends.")
        if self.db.one("SELECT 1 FROM blocks WHERE (blocker_id = ? AND blocked_id = ?) OR "
                       "(blocker_id = ? AND blocked_id = ?)", (from_id, to_id, to_id, from_id)):
            raise FriendError("This player can't be added.")
        existing = self.pending_between(from_id, to_id)
        if existing:
            if existing.from_id == from_id:
                raise FriendError("Request already sent.")
            self.accept(existing.id, from_id)
            return None
        cur = self.db.execute("INSERT INTO friend_requests(from_id, to_id, created_at) VALUES (?, ?, ?)",
                              (from_id, to_id, now()))
        return FriendRequest(cur.lastrowid, from_id, to_id, "pending", now())

    def incoming(self, account_id: int) -> list[FriendRequest]:
        rows = self.db.all("SELECT * FROM friend_requests WHERE to_id = ? AND status = 'pending' ORDER BY id DESC",
                           (account_id,))
        return [FriendRequest(**dict(r)) for r in rows]

    def outgoing(self, account_id: int) -> list[FriendRequest]:
        rows = self.db.all("SELECT * FROM friend_requests WHERE from_id = ? AND status = 'pending' ORDER BY id DESC",
                           (account_id,))
        return [FriendRequest(**dict(r)) for r in rows]

    def _request_for(self, request_id: int, account_id: int) -> FriendRequest:
        row = self.db.one("SELECT * FROM friend_requests WHERE id = ?", (request_id,))
        if row is None or row["status"] != "pending" or row["to_id"] != account_id:
            raise FriendError("That request is no longer available.")
        return FriendRequest(**dict(row))

    def accept(self, request_id: int, account_id: int) -> None:
        req = self._request_for(request_id, account_id)
        with self.db.transaction():
            self.db.execute("UPDATE friend_requests SET status = 'accepted' WHERE id = ?", (request_id,))
            for a, b in ((req.from_id, req.to_id), (req.to_id, req.from_id)):
                self.db.execute("INSERT OR IGNORE INTO friends(account_id, friend_id, created_at) VALUES (?, ?, ?)",
                                (a, b, now()))

    def decline(self, request_id: int, account_id: int) -> None:
        self._request_for(request_id, account_id)
        self.db.execute("UPDATE friend_requests SET status = 'declined' WHERE id = ?", (request_id,))

    def cancel(self, request_id: int, account_id: int) -> None:
        self.db.execute("UPDATE friend_requests SET status = 'cancelled' WHERE id = ? AND from_id = ? "
                        "AND status = 'pending'", (request_id, account_id))

    def remove(self, account_id: int, friend_id: int) -> None:
        self.db.execute("DELETE FROM friends WHERE (account_id = ? AND friend_id = ?) OR "
                        "(account_id = ? AND friend_id = ?)", (account_id, friend_id, friend_id, account_id))

    def friend_ids(self, account_id: int) -> list[int]:
        return [r["friend_id"] for r in self.db.all("SELECT friend_id FROM friends WHERE account_id = ? "
                                                    "ORDER BY created_at DESC", (account_id,))]
