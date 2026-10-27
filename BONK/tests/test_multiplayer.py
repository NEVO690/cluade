"""Multiplayer: protocol validation and a real server + two real clients over TCP.

(The three-process version of this check is tools/mp_selftest.py.)
"""

import asyncio
import math
import tempfile
import threading
import time
import unittest

import helpers  # noqa: F401

from bonk.multiplayer.client import NetworkClient, parse_address
from bonk.multiplayer.protocol import (ProtocolError, decode_line, encode, validate_client_message)
from bonk.multiplayer.server import GameServer


class ProtocolTests(unittest.TestCase):
    def test_round_trip(self):
        msg = {"t": "inp", "seq": 1, "mx": 0.5, "my": -1.0, "j": True, "w": False}
        self.assertEqual(validate_client_message(decode_line(encode(msg).strip())), msg)

    def test_rejects_bad_messages(self):
        bad = [
            b"not json",
            b"[1, 2]",
            b'{"no_type": 1}',
            b'{"t": "teleport", "x": 5}',  # unknown type
            b'{"t": "inp", "seq": 1, "mx": 0, "my": 0}',  # missing field
            b'{"t": "inp", "seq": true, "mx": 0, "my": 0, "j": false}',  # bool as int
            b'{"t": "inp", "seq": 1, "mx": "fast", "my": 0, "j": false}',
            b'{"t": "inp", "seq": 1, "mx": 0, "my": 0, "j": false, "x": 100}',  # position smuggling
            b'{"t": "hello", "name": "a", "version": 1, "admin": true}',
            b"x" * 9000,
        ]
        for line in bad:
            with self.assertRaises(ProtocolError, msg=line[:40]):
                validate_client_message(decode_line(line))

    def test_nan_rejected(self):
        with self.assertRaises(ProtocolError):
            validate_client_message({"t": "inp", "seq": 1, "mx": float("nan"), "my": 0, "j": False})

    def test_parse_address(self):
        self.assertEqual(parse_address("10.0.0.5:7800"), ("10.0.0.5", 7800))
        self.assertEqual(parse_address("myhost"), ("myhost", 7777))
        self.assertEqual(parse_address(""), ("127.0.0.1", 7777))


class ServerThread:
    def __init__(self, **kw):
        self.loop = asyncio.new_event_loop()
        self.server = GameServer("127.0.0.1", 0, tempfile.mkdtemp(prefix="bonk_srv_"), **kw)
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.server.start())
        self.ready.set()
        self.loop.run_forever()

    def __enter__(self):
        self.thread.start()
        self.ready.wait(10)
        return self

    def __exit__(self, *exc):
        fut = asyncio.run_coroutine_threadsafe(self.server.stop(), self.loop)
        try:
            fut.result(5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()

    @property
    def addr(self):
        return "127.0.0.1:%d" % self.server.port


def pump(clients, until, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        for c in clients:
            c.poll()
        if until():
            return True
        time.sleep(0.005)
    return False


class LiveServerTests(unittest.TestCase):
    def test_two_clients_full_game(self):
        with ServerThread(map_ids=["starter_run"], time_limit=5.0) as srv:
            a, b = NetworkClient("Alice", "royal"), NetworkClient("Bob")
            a.connect(srv.addr)
            self.assertTrue(pump([a], lambda: a.online), "first client did not connect")
            b.connect(srv.addr)
            self.assertTrue(pump([a, b], lambda: b.online), "second client did not connect")
            a.create_room("test", bots=1, max_players=4)
            self.assertTrue(pump([a, b], lambda: a.room is not None))
            b.join_room(a.room["id"])
            self.assertTrue(pump([a, b], lambda: b.room is not None and len(a.room["members"]) == 2))
            # Guest cannot start; host cannot start before the guest is ready.
            b.start_game()
            self.assertTrue(pump([a, b], lambda: b.error and "host" in b.error))
            a.start_game()
            self.assertTrue(pump([a, b], lambda: a.error and "Waiting" in a.error))
            b.set_ready(True)
            self.assertTrue(pump([a, b], lambda: all(m["ready"] for m in a.room["members"] if m["id"] != a.player_id)))
            a.start_game()
            self.assertTrue(pump([a, b], lambda: a.game_state and b.game_state))
            self.assertEqual(a.game_state["state"], "COUNTDOWN")
            self.assertEqual(len(a.game_state["participants"]), 3)  # 2 humans + 1 bot
            # Both see each other in snapshots.
            self.assertTrue(pump([a, b], lambda: a.snapshot and b.snapshot and
                                 {b.player_id, a.player_id} <= {c[0] for c in a.snapshot["chars"]}))
            # Movement: Bob runs forward; Alice's view of Bob must change.
            self.assertTrue(pump([a, b], lambda: a.game_state["state"] in ("ROUND_START", "ROUND_ACTIVE"), 8))

            def bob_y(snap):
                return next(c[2] for c in snap["chars"] if c[0] == b.player_id)

            y0 = bob_y(a.snapshot)
            end = time.time() + 1.5
            while time.time() < end:
                b.send_input(0, 1, False, False)
                pump([a, b], lambda: False, 0.02)
            self.assertGreater(bob_y(a.snapshot) - y0, 4.0)
            # Server rejects a teleport attempt as an invalid message (no position fields exist).
            b.send({"t": "inp", "seq": 10 ** 6, "mx": 0, "my": 0, "j": False, "x": 999})
            self.assertTrue(pump([a, b], lambda: b.error and "unexpected" in b.error))
            # Round ends by time limit, results and game over with verified reports.
            got = {"a": None, "b": None}
            a.handlers.append(lambda m: got.__setitem__("a", m) if m["t"] == "game_over" else None)
            b.handlers.append(lambda m: got.__setitem__("b", m) if m["t"] == "game_over" else None)
            self.assertTrue(pump([a, b], lambda: got["a"] and got["b"], 25), "no game over")
            self.assertEqual(got["a"]["standings"], got["b"]["standings"])
            self.assertTrue(got["a"]["reports"][a.player_id]["verified_by_server"])
            self.assertEqual(len(got["a"]["standings"]), 3)
            a.close()
            b.close()

    def test_disconnect_mid_game(self):
        with ServerThread(map_ids=["starter_run"], time_limit=6.0) as srv:
            a, b = NetworkClient("Alice"), NetworkClient("Bob")
            a.connect(srv.addr)
            b.connect(srv.addr)
            self.assertTrue(pump([a, b], lambda: a.online and b.online))
            a.create_room("drop", bots=0)
            self.assertTrue(pump([a, b], lambda: a.room is not None))
            b.join_room(a.room["id"])
            self.assertTrue(pump([a, b], lambda: b.room is not None))
            b.set_ready(True)
            self.assertTrue(pump([a, b], lambda: any(m["ready"] for m in a.room["members"])))
            a.start_game()
            self.assertTrue(pump([a, b], lambda: a.snapshot is not None))
            left = []
            a.handlers.append(lambda m: left.append(m) if m["t"] == "player_left" else None)
            b.close()  # abrupt disconnect
            self.assertTrue(pump([a], lambda: left, 5), "host was not told about the disconnect")
            over = []
            a.handlers.append(lambda m: over.append(m) if m["t"] == "game_over" else None)
            self.assertTrue(pump([a], lambda: over, 25), "game did not finish after a disconnect")
            bob = next(s for s in over[0]["standings"] if s["name"] == "Bob")
            self.assertGreater(bob["place"], 1)
            a.close()

    def test_flood_and_replay_are_ignored(self):
        with ServerThread(map_ids=["starter_run"], time_limit=5.0) as srv:
            a = NetworkClient("Alice")
            a.connect(srv.addr)
            self.assertTrue(pump([a], lambda: a.online))
            a.create_room("solo", bots=0)
            self.assertTrue(pump([a], lambda: a.room is not None))
            a.start_game()
            self.assertTrue(pump([a], lambda: a.game_state and a.game_state["state"] == "ROUND_ACTIVE", 10))
            conn = next(iter(srv.server.clients.values()))
            for _ in range(400):  # far above the per-second limit
                a.send_input(1, 0, False, False)
            pump([a], lambda: False, 0.5)
            self.assertLessEqual(conn.controller.last_seq, 120)
            last = conn.controller.last_seq
            a.send({"t": "inp", "seq": 1, "mx": -1, "my": 0, "j": False})  # replayed old sequence
            pump([a], lambda: False, 0.2)
            self.assertEqual(conn.controller.last_seq, last)
            self.assertLessEqual(math.hypot(conn.controller.cmd.move_x, conn.controller.cmd.move_y), 1.0001)
            a.close()


if __name__ == "__main__":
    unittest.main()
