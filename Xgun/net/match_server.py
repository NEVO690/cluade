"""Authoritative online match server.

Players connect over TCP, wait in a lobby, and the host (first player) starts
the match. The server then runs the only real ``MatchSim`` at 30 Hz with bots
filling the remaining slots, applies each player's ``ControlInput`` and
broadcasts state diffs + events. A player who disconnects mid-match is taken
over by a bot.

Run a dedicated server with:  python -m net.match_server --port 47800
"""
from __future__ import annotations

import argparse
import logging
import random
import socket
import threading
import time

from game.match import TICK, MatchSim
from net import protocol as P

log = logging.getLogger("xgun.server")
MAX_PLAYERS = 16


class _Client:
    def __init__(self, conn: P.LineSocket, addr):
        self.conn = conn
        self.addr = addr
        self.name = "Player"
        self.loadout: dict = {}
        self.cid: int | None = None          # combatant id once the match runs
        self.pending = None                  # merged input not yet consumed
        self.last = None                     # last input (repeated while packets are late)
        self.alive = True
        self.ready = False
        self.lock = threading.Lock()

    def send(self, msg: dict) -> bool:
        if not self.alive:
            return False
        try:
            with self.lock:
                self.conn.send(msg)
            return True
        except OSError:
            self.alive = False
            return False


class MatchServer:
    def __init__(self, host: str = "0.0.0.0", port: int = P.DEFAULT_MATCH_PORT, *, bot_count: int = 19,
                 difficulty: str = "Normal", seed: int | None = None, autostart: int = 0, layout=None,
                 storm_time_scale: float = 1.0):
        self.bot_count = bot_count
        self.difficulty = difficulty
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.autostart = autostart           # start once this many players joined (0 = host decides)
        self.layout = layout
        self.storm_time_scale = storm_time_scale
        self.clients: list[_Client] = []
        self.lock = threading.Lock()
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.sim: MatchSim | None = None
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((host, port))
        self.listener.listen(MAX_PLAYERS)
        self.port = self.listener.getsockname()[1]
        self.status = "lobby"

    # -------------------------------------------------------------- lifecycle
    def serve_in_background(self) -> threading.Thread:
        t = threading.Thread(target=self.serve_forever, name="xgun-match-server", daemon=True)
        t.start()
        return t

    def serve_forever(self) -> None:
        threading.Thread(target=self._accept_loop, daemon=True).start()
        if self.layout is None:
            from world.island import build_island
            self.layout = build_island(7)
        while not self.started.wait(0.2):
            if self.stopped.is_set():
                return
        try:
            self._run_match()
        except Exception:
            log.exception("Match server crashed")
        finally:
            self.stop()

    def stop(self) -> None:
        self.stopped.set()
        self.status = "closed"
        try:
            self.listener.close()
        except OSError:
            pass
        for c in list(self.clients):
            c.alive = False
            c.conn.close()

    # -------------------------------------------------------------- lobby
    def _accept_loop(self) -> None:
        while not self.stopped.is_set():
            try:
                sock, addr = self.listener.accept()
            except OSError:
                return
            sock.settimeout(10)
            threading.Thread(target=self._client_loop, args=(_Client(P.LineSocket(sock), addr),), daemon=True).start()

    def _client_loop(self, client: _Client) -> None:
        try:
            hello = client.conn.recv()
            if not hello or hello.get("t") != "hello":
                return
            if hello.get("v") != P.PROTOCOL_VERSION:
                client.send({"t": "error", "msg": "This server runs a different Xgun version."})
                return
            with self.lock:
                if self.started.is_set():
                    client.send({"t": "error", "msg": "The match has already started."})
                    return
                if len(self.clients) >= MAX_PLAYERS:
                    client.send({"t": "error", "msg": "The server is full."})
                    return
                client.name = str(hello.get("name", "Player"))[:24] or "Player"
                taken = {c.name for c in self.clients}
                base, n = client.name, 2
                while client.name in taken:
                    client.name = f"{base[:21]} {n}"
                    n += 1
                loadout = hello.get("loadout") or {}
                client.loadout = {k: str(v) for k, v in loadout.items() if isinstance(k, str) and v is not None}
                self.clients.append(client)
            client.conn.sock.settimeout(None)
            log.info("%s joined from %s", client.name, client.addr[0])
            self._broadcast_lobby()
            if self.autostart and len(self.clients) >= self.autostart:
                self.start_match()
            while True:
                msg = client.conn.recv()
                if msg is None:
                    break
                t = msg.get("t")
                if t == "in" and client.cid is not None:
                    inp = P.input_from_wire(msg.get("d", {}))
                    with self.lock:
                        client.pending = P.merge_inputs(client.pending, inp)
                elif t == "ready":
                    client.ready = True
                elif t == "start" and self.clients and self.clients[0] is client:
                    self.start_match()
                elif t == "bye":
                    break
        except (OSError, ValueError) as exc:
            log.info("Connection from %s dropped: %s", client.addr[0], exc)
        finally:
            client.alive = False
            self._drop(client)

    def _drop(self, client: _Client) -> None:
        with self.lock:
            if client not in self.clients:
                return
            if not self.started.is_set():
                self.clients.remove(client)
            elif self.sim is not None and client.cid is not None:
                self.sim.hand_to_bot(client.cid, self.difficulty)
        client.conn.close()
        log.info("%s left", client.name)
        if not self.started.is_set():
            self._broadcast_lobby()

    def _broadcast_lobby(self) -> None:
        with self.lock:
            names = [c.name for c in self.clients]
            clients = list(self.clients)
        for i, c in enumerate(clients):
            c.send({"t": "lobby", "players": names, "host": i == 0, "bots": self.bot_count})

    def start_match(self) -> None:
        with self.lock:
            if self.started.is_set() or not self.clients:
                return
            self.started.set()

    # -------------------------------------------------------------- match
    def _run_match(self) -> None:
        from game.loadouts import random_loadout
        while self.layout is None:
            time.sleep(0.05)
        with self.lock:
            clients = [c for c in self.clients if c.alive]
            self.clients = clients
        rng = random.Random(self.seed)
        humans = [(c.name, c.loadout) for c in clients]
        bots = max(0, self.bot_count - len(humans) + 1)
        bot_loadouts = [random_loadout(rng) for _ in range(bots)]
        self.sim = sim = MatchSim(seed=self.seed, bot_count=bots, difficulty=self.difficulty, humans=humans,
                                  layout=self.layout, bot_loadouts=bot_loadouts, storm_time_scale=self.storm_time_scale)
        self.status = "running"
        start = {"t": "start", "seed": self.seed, "bots": bots, "difficulty": self.difficulty, "humans": humans,
                 "bot_loadouts": bot_loadouts, "storm_time_scale": self.storm_time_scale,
                 "fingerprint": P.containers_fingerprint(sim)}
        for i, c in enumerate(clients):
            c.cid = i
            c.send({**start, "you": i})
        log.info("Match started: %d players + %d bots (seed %d)", len(humans), bots, self.seed)
        wait_until = time.perf_counter() + 90.0     # everyone loads the island before the drop ship leaves
        while time.perf_counter() < wait_until and not self.stopped.is_set() and \
                not all(c.ready or not c.alive for c in clients):
            time.sleep(0.05)
        last_state = None
        next_tick = time.perf_counter()
        end_at = None
        while not self.stopped.is_set():
            inputs = {}
            with self.lock:
                for c in clients:
                    if c.cid is None or not c.alive:
                        continue
                    if c.pending is not None:
                        inputs[c.cid] = c.pending
                        c.last, c.pending = c.pending, None
                    elif c.last is not None:
                        inputs[c.cid] = P.held_only(c.last)
                sim.step(TICK, inputs)
                events = sim.drain_events()
                state = P.snapshot(sim)
            msg = {"t": "s", "d": P.diff(last_state, state), "e": events}
            last_state = state
            for c in clients:
                c.send(msg)
            if sim.over and end_at is None:
                end_at = time.perf_counter() + 3.0
                self.status = "finished"
            if end_at is not None and time.perf_counter() > end_at:
                break
            if not any(c.alive for c in clients) and end_at is None:
                log.info("Every player left; closing the match")
                break
            next_tick += TICK
            delay = next_tick - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            elif delay < -0.5:                    # fell behind (debugger, slow PC): don't spiral
                next_tick = time.perf_counter()
        for c in clients:
            c.send({"t": "end"})


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Xgun dedicated match server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=P.DEFAULT_MATCH_PORT)
    ap.add_argument("--bots", type=int, default=19, help="total opponents; players replace bots")
    ap.add_argument("--difficulty", default="Normal", choices=["Easy", "Normal", "Hard"])
    ap.add_argument("--players", type=int, default=0, help="start automatically when this many players joined")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        server = MatchServer(args.host, args.port, bot_count=args.bots, difficulty=args.difficulty,
                             autostart=args.players)
        log.info("Listening on port %d. The first player to join is the host and starts the match.", server.port)
        server.serve_forever()
        log.info("Match finished, opening a new lobby")


if __name__ == "__main__":
    main()
