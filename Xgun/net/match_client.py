"""Client side of an online match.

``MatchConnection`` owns the socket (a reader thread queues incoming
messages). ``ClientMatch`` is a ``MatchSim`` that never simulates: it is
built from the server's seed so the island, drop ship and containers match,
and each tick it sends the local player's input and applies the server's
state diffs, so ``MatchScreen`` renders it exactly like an offline match.
"""
from __future__ import annotations

import logging
import queue
import re
import socket
import threading

from game.match import MatchSim
from net import protocol as P

log = logging.getLogger(__name__)
_ASSET_ID = re.compile(r"^[a-z0-9_]{1,48}$")


def _clean_loadout(lo) -> dict:
    """Other players' cosmetics come off the network: only accept plain asset ids."""
    return {k: v for k, v in (lo or {}).items() if isinstance(v, str) and _ASSET_ID.match(v)} if isinstance(lo, dict) else {}


class ConnectionFailed(Exception):
    pass


class MatchConnection:
    def __init__(self, host: str, port: int, name: str, loadout: dict, timeout: float = 5.0):
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as exc:
            raise ConnectionFailed(f"Couldn't reach {host}:{port} ({exc.strerror or exc}).") from exc
        sock.settimeout(None)
        self.conn = P.LineSocket(sock)
        self.inbox: queue.Queue = queue.Queue()
        self.closed = False
        self.conn.send({"t": "hello", "v": P.PROTOCOL_VERSION, "name": name, "loadout": loadout})
        threading.Thread(target=self._reader, name="xgun-net-reader", daemon=True).start()

    def _reader(self) -> None:
        try:
            while True:
                msg = self.conn.recv()
                if msg is None:
                    break
                self.inbox.put(msg)
        except (OSError, ValueError) as exc:
            log.info("Connection closed: %s", exc)
        self.inbox.put({"t": "closed"})

    def poll(self) -> list[dict]:
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out

    def wait_for(self, kind: str, timeout: float = 10.0) -> dict:
        """Blocking helper for tests and tools."""
        import time
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                msg = self.inbox.get(timeout=max(0.01, end - time.monotonic()))
            except queue.Empty:
                break
            if msg.get("t") == kind:
                return msg
            if msg.get("t") in ("error", "closed"):
                raise ConnectionFailed(msg.get("msg", "Disconnected from the server."))
        raise ConnectionFailed(f"Timed out waiting for '{kind}'.")

    def send(self, msg: dict) -> bool:
        if self.closed:
            return False
        try:
            self.conn.send(msg)
            return True
        except OSError:
            self.closed = True
            return False

    def close(self) -> None:
        if not self.closed:
            self.send({"t": "bye"})
            self.closed = True
            self.conn.close()


class ClientMatch(MatchSim):
    networked = True

    def __init__(self, conn: MatchConnection, start: dict, layout=None):
        super().__init__(seed=start["seed"], bot_count=start["bots"], difficulty=start["difficulty"],
                         humans=[(str(n)[:24], _clean_loadout(lo)) for n, lo in start["humans"]], layout=layout,
                         bot_loadouts=[_clean_loadout(lo) for lo in start["bot_loadouts"]], storm_time_scale=start.get("storm_time_scale", 1.0))
        if P.containers_fingerprint(self) != start["fingerprint"]:
            raise ConnectionFailed("This copy of the island doesn't match the server's. Make sure both PCs run the "
                                   "same Xgun version.")
        self.conn = conn
        self.brains = {}                          # the server runs every bot
        self.items.clear()                        # ground items arrive with the first snapshot
        self.player = self.combatants[start["you"]]
        self.lost = False
        self.pending: list[dict] = []
        self.conn.send({"t": "ready"})

    def step(self, dt, inputs) -> None:
        inp = inputs.get(self.player.id)
        if inp is not None and not self.lost:
            self.conn.send({"t": "in", "d": P.input_to_wire(inp)})
        for msg in self.conn.poll():
            t = msg.get("t")
            if t == "s":
                self.pending.append(msg)
            elif t in ("closed", "error") and not self.over:
                self.lost = True
                self.events.append({"type": "notice", "who": self.player.id, "text": "Connection to the server lost"})
        # one snapshot per tick keeps motion smooth; catch up when we fall behind (diffs can't be skipped)
        n = min(len(self.pending), 1 if len(self.pending) <= 3 else len(self.pending) - 2)
        for msg in self.pending[:n]:
            P.apply(self, msg["d"])
            self.events.extend(msg["e"])
        del self.pending[:n]
        if n == 0:                                # nothing new: hold still instead of re-interpolating
            for c in self.combatants:
                c.prev = (c.x, c.y, c.z)

    def close(self) -> None:
        self.conn.close()
