"""Authoritative BONK! game server (asyncio, TCP, newline-delimited JSON).

    python run_server.py --port 7777

* rooms with a host, ready flags, optional bot fill, 2-16 players;
* the server runs the same GameManager / physics / bot AI as single player
  at 60 Hz and sends snapshots at 20 Hz;
* clients only send inputs, which are type-checked, clamped and rate
  limited; the server decides positions, eliminations and winners;
* disconnects remove the player from the room (and the running round);
* final results are recorded server-side (server_data/results.jsonl) and an
  online leaderboard is kept from verified results only.
"""

import asyncio
import json
import logging
import os
import random
import time
import uuid

from ..ai import make_bot
from ..ai.bot_difficulty import mixed_lineup
from ..game.game_manager import GameManager, GameSettings, Participant
from ..game.game_state import GameState, Outcome
from ..maps.map_manager import MapManager
from ..sim import constants as C
from ..sim.character import IDLE_COMMAND, InputCommand
from .protocol import (MAX_INPUTS_PER_SECOND, MAX_LINE, PROTOCOL_VERSION, SNAPSHOT_HZ, ProtocolError, clean_name,
                       decode_line, encode, pack_char, validate_client_message)

log = logging.getLogger("bonk.server")

BOT_NAMES = ["Bolt", "Wiggles", "Tumble", "Pip", "Jelly", "Zoom", "Bonkers", "Squeak", "Noodle", "Fizz",
             "Bean", "Hopper", "Muffin", "Taffy"]


class NetworkController:
    """Latest validated input from a remote player."""

    def __init__(self):
        self.cmd = IDLE_COMMAND
        self.last_seq = -1

    def command(self, ch, rnd):
        return self.cmd


class ClientConn:
    def __init__(self, server, reader, writer):
        self.server = server
        self.reader = reader
        self.writer = writer
        self.id = "p" + uuid.uuid4().hex[:8]
        self.name = None
        self.skin = "classic"
        self.room = None
        self.ready = False
        self.errors = 0
        self.inputs_window = []
        self.controller = NetworkController()
        self.alive = True
        peer = writer.get_extra_info("peername")
        self.addr = "%s:%s" % peer[:2] if peer else "?"

    def send(self, msg):
        if not self.alive:
            return
        try:
            self.writer.write(encode(msg))
        except Exception:  # connection already broken; cleanup happens in the reader loop
            self.alive = False


class Room:
    def __init__(self, server, rid, name, host, bots, max_players, map_ids, time_limit=None):
        self.server = server
        self.id = rid
        self.name = name
        self.host = host
        self.members = []
        self.bots = bots
        self.max_players = max_players
        self.map_ids = map_ids
        self.time_limit = time_limit
        self.state = "waiting"
        self.gm = None
        self.task = None
        self.tick = 0
        self.tile_seen = {}
        self.match_id = None

    def summary(self):
        return {"id": self.id, "name": self.name, "players": len(self.members), "max": self.max_players,
                "bots": self.bots, "state": self.state, "host": self.host.name if self.host else None}

    def detail(self):
        return {"id": self.id, "name": self.name, "host": self.host.id if self.host else None, "state": self.state,
                "bots": self.bots, "max": self.max_players,
                "members": [{"id": m.id, "name": m.name, "skin": m.skin, "ready": m.ready} for m in self.members]}

    def broadcast(self, msg):
        data = encode(msg)
        for m in list(self.members):
            if m.alive:
                try:
                    m.writer.write(data)
                except Exception:
                    m.alive = False

    # ------------------------------------------------------------------ game
    def start(self):
        rng = random.Random()
        parts = [Participant(m.id, m.name, m.skin, False) for m in self.members]
        n_bots = max(0, min(self.bots, self.max_players - len(self.members)))
        diffs = mixed_lineup(n_bots, rng)
        skins = [s.id for s in self.server.catalog.ordered()] if self.server.catalog else ["classic"]
        for i in range(n_bots):
            parts.append(Participant("bot%d" % i, BOT_NAMES[i % len(BOT_NAMES)] + " (bot)", rng.choice(skins),
                                     True, diffs[i]))
        maps = [self.server.maps.get(m) for m in self.map_ids]
        controllers = {m.id: m.controller for m in self.members}
        for m in self.members:
            m.controller.cmd = IDLE_COMMAND
            m.controller.last_seq = -1

        def factory(part, ch, rnd):
            if part.is_bot:
                return make_bot(part.difficulty, random.Random(rng.random()), rnd.world)
            return controllers.get(part.id)

        self.gm = GameManager(maps, parts, factory, GameSettings(countdown=4.0, round_end=3.0, results_auto=6.0),
                              mode="online")
        self.gm.add_listener(self._on_game_event)
        self.match_id = uuid.uuid4().hex
        self.state = "playing"
        self.gm.start()
        self.server.broadcast_room(self)
        self.task = asyncio.ensure_future(self._run())

    def _participants_msg(self):
        return [{"id": p.id, "name": p.name, "skin": p.skin_id, "bot": p.is_bot}
                for p in self.gm.participants.values()]

    def _on_game_event(self, kind, data):
        gm = self.gm
        if kind == "state":
            rnd = gm.round
            if data == GameState.COUNTDOWN:
                self.tile_seen = {}
                if self.time_limit:
                    rnd.world.time_limit = self.time_limit
            msg = {"t": "game_state", "state": data, "round": gm.round_index, "total": gm.total_rounds,
                   "map": rnd.map.id if rnd else None, "qualify": rnd.qualify_count if rnd else 0,
                   "final": rnd.is_final if rnd else False, "time_limit": rnd.world.time_limit if rnd else 0,
                   "alive": list(gm.alive_ids), "participants": self._participants_msg(),
                   "countdown": gm.settings.countdown}
            self.broadcast(msg)
        elif kind == "round_events":
            evs = [[k, cid, d if isinstance(d, (int, float, str)) or d is None else None] for k, cid, d in data
                   if k in ("jump", "land", "bonk", "hit", "fall", "finish", "eliminated", "checkpoint", "bounce",
                            "respawn")]
            if evs:
                self.broadcast({"t": "events", "ev": evs})
        elif kind == "results":
            map_id, results = data
            self.broadcast({"t": "results", "map": map_id, "results": [r.to_dict() for r in results]})
        elif kind == "game_over":
            self._game_over()

    async def _run(self):
        """Fixed-rate loop: 60 Hz simulation, 20 Hz snapshots."""
        loop = asyncio.get_event_loop()
        last = loop.time()
        snap_every = max(1, int(C.TICK_RATE / SNAPSHOT_HZ))
        try:
            while self.state == "playing" and self.gm is not None:
                await asyncio.sleep(C.DT)
                now = loop.time()
                dt = min(0.25, now - last)
                last = now
                self.gm.update(dt)
                self.tick += 1
                if self.gm is None or self.gm.state == GameState.GAME_OVER:
                    break  # the game-over handler already reset the room
                if self.tick % snap_every == 0:
                    self._send_snapshot()
        except Exception:
            log.exception("room %s crashed", self.id)
            self.broadcast({"t": "error", "code": "server_error", "msg": "Room stopped after a server error."})
        finally:
            if self.state == "playing":
                self._end_room()

    def _send_snapshot(self):
        rnd = self.gm.round
        if rnd is None:
            return
        changed = []
        for tile in rnd.world.tiles:
            ta = tile.triggered_at
            if self.tile_seen.get(tile.id, None) != ta:
                self.tile_seen[tile.id] = ta
                changed.append([tile.id, ta])
        msg = {"t": "snap", "tick": self.tick, "state": self.gm.state, "ct": round(rnd.t, 4),
               "rt": round(rnd.race_time, 2), "left": round(rnd.time_left, 2),
               "fin": [c.id for c in rnd.finish_order],
               "chars": [pack_char(c) for c in rnd.characters if c.active]}
        if changed:
            msg["tiles"] = changed
        self.broadcast(msg)

    def _game_over(self):
        gm = self.gm
        standings = [{"place": p, "id": i, "name": gm.participants[i].name, "bot": gm.participants[i].is_bot}
                     for p, i in sorted(gm.final_standings)]
        reports = {}
        for m in self.members:
            rep = self._report_for(m.id)
            if rep is not None:
                reports[m.id] = rep
        self.server.record_results(self, standings, reports)
        self.broadcast({"t": "game_over", "match": self.match_id, "standings": standings,
                        "champion": gm.participants[gm.champion_id].name if gm.champion_id else None,
                        "reports": reports, "leaderboard": self.server.leaderboard_top(10)})
        self._end_room()

    def _report_for(self, pid):
        """MatchReport for one connected player, computed only from server state."""
        gm = self.gm
        if pid not in gm.characters:
            return None
        ch = gm.characters[pid]
        rounds = []
        for map_id, results in gm.history:
            for r in results:
                if r.id == pid:
                    rounds.append({"map_id": map_id, "outcome": r.outcome, "time": r.time, "place": r.place,
                                   "reason": r.reason})
        won = any(r["outcome"] == Outcome.WINNER for r in rounds)
        return {"mode": "online", "player_count": len(gm.order), "rounds": rounds, "won": won,
                "placement": gm.placement_of(pid), "quit_early": False, "jumps": ch.stat_jumps,
                "obstacles_cleared": ch.stat_obstacles, "falls": ch.stat_falls, "hits": ch.stat_hits,
                "bonks": ch.stat_bonks, "difficulty": "MIXED", "verified_by_server": True}

    def _end_room(self):
        """Back to the waiting state so the same group can play again."""
        for m in self.members:
            m.ready = False
        self.gm = None
        self.state = "waiting"
        self.server.broadcast_room(self)

    def remove_member(self, conn, reason="left"):
        if conn in self.members:
            self.members.remove(conn)
        conn.room = None
        conn.ready = False
        self.broadcast({"t": "player_left", "id": conn.id, "name": conn.name, "reason": reason})
        if self.gm is not None:
            self.gm.remove_participant(conn.id, reason)
        if not self.members:
            if self.task is not None:
                self.task.cancel()
            self.state = "closed"
            self.server.rooms.pop(self.id, None)
            return
        if self.host is conn:
            self.host = self.members[0]
        self.server.broadcast_room(self)


class GameServer:
    def __init__(self, host="0.0.0.0", port=7777, data_dir=None, map_ids=None, time_limit=None):
        self.host = host
        self.port = port
        self.maps = MapManager()
        try:
            from ..cosmetics.skin_definitions import SkinCatalog
            self.catalog = SkinCatalog()
        except Exception:  # skins are cosmetic only; the server works without them
            self.catalog = None
        self.map_ids = map_ids or self.maps.show_playlist()
        self.time_limit = time_limit
        self.clients = {}
        self.rooms = {}
        self.data_dir = data_dir or os.path.join(os.getcwd(), "server_data")
        self.leaderboard = {}
        self._load_leaderboard()
        self.server = None

    # ------------------------------------------------------------------ persistence (server-side only)
    def _lb_path(self):
        return os.path.join(self.data_dir, "online_leaderboard.json")

    def _load_leaderboard(self):
        try:
            with open(self._lb_path(), "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self.leaderboard = data
        except (OSError, ValueError):
            self.leaderboard = {}

    def record_results(self, room, standings, reports):
        os.makedirs(self.data_dir, exist_ok=True)
        entry = {"match": room.match_id, "time": int(time.time()), "room": room.name, "maps": room.map_ids,
                 "standings": standings}
        with open(os.path.join(self.data_dir, "results.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        for pid, rep in reports.items():
            name = next((s["name"] for s in standings if s["id"] == pid), pid)
            row = self.leaderboard.setdefault(name, {"played": 0, "wins": 0, "points": 0})
            row["played"] += 1
            row["wins"] += 1 if rep["won"] else 0
            row["points"] += 60 * rep["won"] + 10 * sum(1 for r in rep["rounds"] if r["outcome"] != "eliminated")
        tmp = self._lb_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.leaderboard, fh, indent=1)
        os.replace(tmp, self._lb_path())

    def leaderboard_top(self, n):
        rows = sorted(self.leaderboard.items(), key=lambda kv: (-kv[1]["points"], kv[0]))[:n]
        return [{"name": k, **v} for k, v in rows]

    # ------------------------------------------------------------------ networking
    async def start(self):
        self.server = await asyncio.start_server(self._handle, self.host, self.port, limit=MAX_LINE * 2)
        sock = self.server.sockets[0].getsockname()
        self.port = sock[1]
        log.info("BONK! server listening on %s:%d (maps: %s)", sock[0], sock[1], ", ".join(self.map_ids))
        return self

    async def serve_forever(self):
        async with self.server:
            await self.server.serve_forever()

    async def stop(self):
        for r in list(self.rooms.values()):
            if r.task is not None:
                r.task.cancel()
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()

    async def _handle(self, reader, writer):
        conn = ClientConn(self, reader, writer)
        self.clients[conn.id] = conn
        log.info("connection %s from %s", conn.id, conn.addr)
        try:
            while conn.alive:
                try:
                    line = await reader.readline()
                except (asyncio.LimitOverrunError, ValueError):
                    conn.send({"t": "error", "code": "too_long", "msg": "Message too long."})
                    break
                if not line:
                    break
                try:
                    msg = validate_client_message(decode_line(line.strip()))
                except ProtocolError as exc:
                    conn.errors += 1
                    conn.send({"t": "error", "code": "bad_message", "msg": str(exc)})
                    if conn.errors > 20:
                        conn.send({"t": "error", "code": "kicked", "msg": "Too many invalid messages."})
                        break
                    continue
                self._dispatch(conn, msg)
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self._disconnect(conn)

    def _disconnect(self, conn):
        conn.alive = False
        self.clients.pop(conn.id, None)
        if conn.room is not None:
            conn.room.remove_member(conn, "disconnected")
        try:
            conn.writer.close()
        except Exception:
            pass
        log.info("connection %s closed", conn.id)

    def _dispatch(self, conn, msg):
        t = msg["t"]
        if t != "hello" and conn.name is None:
            conn.send({"t": "error", "code": "no_hello", "msg": "Say hello first."})
            return
        handler = getattr(self, "_on_" + t)
        handler(conn, msg)

    def _on_hello(self, conn, msg):
        if msg["version"] != PROTOCOL_VERSION:
            conn.send({"t": "error", "code": "version", "msg": "Server speaks protocol %d." % PROTOCOL_VERSION})
            conn.alive = False
            return
        conn.name = clean_name(msg["name"])
        skin = msg.get("skin", "classic")
        conn.skin = skin if (self.catalog is None or skin in self.catalog) else "classic"
        conn.send({"t": "welcome", "id": conn.id, "name": conn.name, "version": PROTOCOL_VERSION,
                   "maps": self.map_ids})
        self._on_list_rooms(conn, msg)

    def _on_list_rooms(self, conn, msg):
        conn.send({"t": "rooms", "rooms": [r.summary() for r in self.rooms.values()]})

    def _on_create_room(self, conn, msg):
        if conn.room is not None:
            conn.room.remove_member(conn)
        rid = "r" + uuid.uuid4().hex[:6]
        name = clean_name(msg.get("name") or (conn.name + "'s room"), "Room")
        bots = max(0, min(14, int(msg.get("bots", 6))))
        maxp = max(2, min(16, int(msg.get("max_players", 16))))
        room = Room(self, rid, name, conn, bots, maxp, list(self.map_ids), self.time_limit)
        self.rooms[rid] = room
        self._join(conn, room)

    def _on_join_room(self, conn, msg):
        room = self.rooms.get(msg["room"])
        if room is None:
            conn.send({"t": "error", "code": "no_room", "msg": "That room does not exist."})
            return
        if room.state != "waiting":
            conn.send({"t": "error", "code": "in_progress", "msg": "That show already started."})
            return
        if len(room.members) >= room.max_players:
            conn.send({"t": "error", "code": "full", "msg": "Room is full."})
            return
        if conn.room is not None:
            conn.room.remove_member(conn)
        self._join(conn, room)

    def _join(self, conn, room):
        room.members.append(conn)
        conn.room = room
        conn.ready = False
        self.broadcast_room(room)

    def _on_leave_room(self, conn, msg):
        if conn.room is not None:
            conn.room.remove_member(conn)
        self._on_list_rooms(conn, msg)

    def _on_ready(self, conn, msg):
        if conn.room is None or conn.room.state != "waiting":
            return
        conn.ready = bool(msg["ready"])
        self.broadcast_room(conn.room)

    def _on_start_game(self, conn, msg):
        room = conn.room
        if room is None or room.host is not conn:
            conn.send({"t": "error", "code": "not_host", "msg": "Only the host can start the show."})
            return
        if room.state != "waiting":
            return
        not_ready = [m.name for m in room.members if not m.ready and m is not room.host]
        if not_ready:
            conn.send({"t": "error", "code": "not_ready", "msg": "Waiting for: " + ", ".join(not_ready)})
            return
        room.start()

    def _on_inp(self, conn, msg):
        room = conn.room
        if room is None or room.gm is None:
            return
        now = time.monotonic()
        w = conn.inputs_window
        w.append(now)
        while w and now - w[0] > 1.0:
            w.pop(0)
        if len(w) > MAX_INPUTS_PER_SECOND:
            return  # flood protection: extra inputs are dropped
        ctrl = conn.controller
        if msg["seq"] <= ctrl.last_seq:
            return  # stale or replayed
        ctrl.last_seq = msg["seq"]
        ctrl.cmd = InputCommand(float(msg["mx"]), float(msg["my"]), bool(msg["j"]), bool(msg.get("w", False))).sanitized()

    def _on_ping(self, conn, msg):
        conn.send({"t": "pong", "ts": msg.get("ts", 0), "server": time.time()})

    def broadcast_room(self, room):
        room.broadcast({"t": "room", "room": room.detail()})
        lobby = {"t": "rooms", "rooms": [r.summary() for r in self.rooms.values()]}
        for c in self.clients.values():
            if c.room is None and c.name is not None:
                c.send(lobby)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="BONK! authoritative game server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=7777)
    ap.add_argument("--maps", default=None, help="comma separated course ids (default: full show)")
    ap.add_argument("--time-limit", type=float, default=None, help="override round time limit (testing)")
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    async def run():
        srv = GameServer(a.host, a.port, a.data_dir, a.maps.split(",") if a.maps else None, a.time_limit)
        await srv.start()
        print("READY %d" % srv.port, flush=True)
        await srv.serve_forever()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
