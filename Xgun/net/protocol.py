"""Wire format shared by the match server and client.

Messages are JSON objects, one per line, over TCP. The server runs the only
real ``MatchSim``; clients send their ``ControlInput`` every tick and receive
state *diffs* plus the event stream. A client keeps a mirror ``MatchSim``
(same seed, so the island, drop ship and containers line up) whose state is
overwritten from those diffs instead of being simulated.
"""
from __future__ import annotations

import json
import socket
from dataclasses import fields

from combat.weapons import WeaponInstance
from game import building as B
from game.entities import ControlInput, GroundItem, Stats
from inventory.match_inventory import ConsumableStack, MatchInventory
from world.collision import Box

PROTOCOL_VERSION = 1
DEFAULT_MATCH_PORT = 47800
DEFAULT_SOCIAL_PORT = 47801
MAX_LINE = 1 << 20

_INPUT_FIELDS = [f.name for f in fields(ControlInput)]
_INPUT_DEFAULTS = {f.name: f.default for f in fields(ControlInput)}
EDGE_FLAGS = ("fire_pressed", "jump", "deploy", "reload", "build_toggle", "build_material_next")
ONE_SHOT = ("select", "build_piece", "emote")


# ------------------------------------------------------------------ framing
def _json_default(o):
    try:
        return float(o)              # numpy scalars from collision queries
    except (TypeError, ValueError):
        return list(o)


def encode(msg: dict) -> bytes:
    return (json.dumps(msg, separators=(",", ":"), default=_json_default) + "\n").encode("utf-8")


class LineSocket:
    """Blocking newline-delimited JSON over a socket."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = b""
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def send(self, msg: dict) -> None:
        self.sock.sendall(encode(msg))

    def recv(self) -> dict | None:
        """Next message, or None when the peer closed the connection."""
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                return None
            self.buf += chunk
            if len(self.buf) > MAX_LINE:
                raise ValueError("message too large")
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


# ------------------------------------------------------------------ input
def input_to_wire(inp: ControlInput) -> dict:
    out = {}
    for name in _INPUT_FIELDS:
        v = getattr(inp, name)
        if v != _INPUT_DEFAULTS[name]:
            out[name] = round(v, 2) if isinstance(v, float) else v
    return out


def input_from_wire(data: dict) -> ControlInput:
    inp = ControlInput()
    for name, v in data.items():
        if name not in _INPUT_DEFAULTS:
            continue
        default = _INPUT_DEFAULTS[name]
        if isinstance(default, bool):
            v = bool(v)
        elif isinstance(default, float):
            v = float(v)
        elif name == "cycle":
            v = max(-1, min(1, int(v)))
        elif name == "select":
            v = int(v) if v is not None else None
        elif v is not None:
            v = str(v)[:32]
        setattr(inp, name, v)
    return inp


def merge_inputs(older: ControlInput | None, newer: ControlInput) -> ControlInput:
    """Several client ticks can arrive within one server tick: keep presses from all of them."""
    if older is None:
        return newer
    for name in EDGE_FLAGS:
        if getattr(older, name):
            setattr(newer, name, True)
    for name in ONE_SHOT:
        if getattr(newer, name) is None:
            setattr(newer, name, getattr(older, name))
    newer.cycle = newer.cycle or older.cycle
    return newer


def held_only(inp: ControlInput) -> ControlInput:
    """Repeat a late client's last input without its one-shot presses."""
    copy = ControlInput(**{n: getattr(inp, n) for n in _INPUT_FIELDS})
    for name in EDGE_FLAGS:
        setattr(copy, name, False)
    for name in ONE_SHOT:
        setattr(copy, name, None)
    copy.cycle = 0
    return copy


# ------------------------------------------------------------------ state
_C_FLOATS3 = ("x", "y", "z", "vx", "vy", "vz")
_C_FLOATS2 = ("yaw", "pitch", "health", "shield", "fire_cooldown", "bloom", "reload_timer", "use_timer",
              "interact_timer", "emote_timer", "death_time", "last_damage_time", "storm_tick", "landed_time")
_C_PLAIN = ("state", "on_ground", "crouching", "sprinting", "aiming", "moving", "use_slot", "emote", "placement",
            "killer", "action", "build_mode", "build_piece", "build_material")


def _item_payload(kind, payload):
    if kind == "weapon":
        return {"w": payload.wdef.id, "r": payload.rarity, "m": payload.in_mag, "u": payload.uid}
    if kind == "consumable":
        return {"c": payload.cid, "n": payload.count}
    return [payload[0], payload[1]]


def _payload_from(kind, data, armory):
    if kind == "weapon":
        return WeaponInstance(armory.weapons[data["w"]], data["r"], data["m"], data["u"])
    if kind == "consumable":
        return ConsumableStack(data["c"], data["n"])
    return (data[0], data[1])


def _inventory(inv: MatchInventory) -> dict:
    return {"s": [None if s is None else
                  _item_payload("weapon" if isinstance(s, WeaponInstance) else "consumable", s) for s in inv.slots],
            "a": dict(inv.ammo), "sel": inv.selected}


def _combatant_state(c) -> dict:
    d = {k: round(getattr(c, k), 3) for k in _C_FLOATS3}
    d.update({k: round(getattr(c, k), 2) for k in _C_FLOATS2})
    d.update({k: getattr(c, k) for k in _C_PLAIN})
    d["it"] = list(c.interact_target) if c.interact_target else None
    d["mat"] = dict(c.materials)
    d["st"] = {f.name: round(getattr(c.stats, f.name), 2) for f in fields(Stats)}
    d["inv"] = _inventory(c.inventory)
    return d


def snapshot(sim) -> dict:
    """Everything a client needs, as plain JSON-able dicts keyed by section and id."""
    st = sim.storm
    return {
        "g": {0: {"time": round(sim.time, 4), "ship_t": round(sim.ship.t, 4), "over": sim.over, "winner": sim.winner,
                  "storm": [st.phase, round(st.center[0], 2), round(st.center[1], 2), round(st.radius, 2),
                            round(st.target_center[0], 2), round(st.target_center[1], 2), st.target_radius,
                            st.shrinking, round(st.timer, 3), st.dps, round(st._start_center[0], 2),
                            round(st._start_center[1], 2), round(st._start_radius, 2)]}},
        "c": {c.id: _combatant_state(c) for c in sim.combatants},
        "i": {i.id: {"k": i.kind, "x": round(i.x, 2), "y": round(i.y, 2), "z": round(i.z, 2),
                     "t": round(i.spawn_time, 2), "p": _item_payload(i.kind, i.payload)} for i in sim.items.values()},
        "k": {k.id: {"o": k.opened, "hp": round(k.hp, 1), "ot": round(k.open_time, 2)} for k in sim.containers},
        "b": {p.id: {"kind": p.kind, "mat": p.material, "ix": p.ix, "iy": p.iy, "z": round(p.z, 3), "d": p.direction,
                     "own": p.owner, "hp": round(p.hp, 1), "max": p.max_hp} for p in sim.builds.values()},
    }


def diff(prev: dict | None, cur: dict) -> dict:
    """Changed fields only. A removed id maps to None; a new id carries every field."""
    out = {}
    for section, entries in cur.items():
        before = (prev or {}).get(section, {})
        changes = {}
        for key, fields_ in entries.items():
            old = before.get(key)
            if old is None:
                changes[key] = fields_
            else:
                delta = {f: v for f, v in fields_.items() if old.get(f) != v}
                if delta:
                    changes[key] = delta
        for key in before:
            if key not in entries:
                changes[key] = None
        if changes:
            out[section] = changes
    return out


def apply(sim, d: dict) -> None:
    """Overwrite a client-side mirror ``MatchSim`` with a server diff."""
    for c in sim.combatants:
        c.prev = (c.x, c.y, c.z)
    g = d.get("g", {}).get("0") or d.get("g", {}).get(0)
    if g:
        if "time" in g:
            sim.time = g["time"]
        if "ship_t" in g:
            sim.ship.t = g["ship_t"]
        if "over" in g:
            sim.over = g["over"]
        if "winner" in g:
            sim.winner = g["winner"]
        if "storm" in g:
            st = sim.storm
            (st.phase, cx, cy, st.radius, tx, ty, st.target_radius, st.shrinking, st.timer, st.dps,
             sx, sy, st._start_radius) = g["storm"]
            st.center, st.target_center, st._start_center = (cx, cy), (tx, ty), (sx, sy)
    for key, f in d.get("c", {}).items():
        c = sim.combatants[int(key)]
        for k, v in f.items():
            if k == "it":
                c.interact_target = tuple(v) if v else None
            elif k == "mat":
                c.materials = dict(v)
            elif k == "st":
                c.stats = Stats(**v)
                c.stats.eliminations, c.stats.damage = int(c.stats.eliminations), int(c.stats.damage)
            elif k == "inv":
                inv = c.inventory
                inv.slots = [None if s is None else _payload_from("weapon" if "w" in s else "consumable", s, sim.armory)
                             for s in v["s"]]
                inv.ammo = dict(v["a"])
                inv.selected = v["sel"]
            else:
                setattr(c, k, v)
    for key, f in d.get("i", {}).items():
        iid = int(key)
        if f is None:
            sim.items.pop(iid, None)
            continue
        item = sim.items.get(iid)
        if item is None:
            sim.items[iid] = GroundItem(iid, f["k"], _payload_from(f["k"], f["p"], sim.armory), f["x"], f["y"], f["z"],
                                        f["t"])
            continue
        if "p" in f:
            item.payload = _payload_from(item.kind, f["p"], sim.armory)
        item.x, item.y, item.z = f.get("x", item.x), f.get("y", item.y), f.get("z", item.z)
    for key, f in d.get("k", {}).items():
        k = sim.containers[int(key)]
        if f.get("o") and not k.opened and k.kind == "crate" and k.box_index >= 0:
            sim.collision.disable(k.box_index)
        k.opened = f.get("o", k.opened)
        k.hp = f.get("hp", k.hp)
        k.open_time = f.get("ot", k.open_time)
    for key, f in d.get("b", {}).items():
        pid = int(key)
        piece = sim.builds.get(pid)
        if f is None:
            if piece is not None:
                for idx in piece.boxes:
                    sim.collision.disable(idx)
                sim._build_keys.pop(piece.key, None)
                del sim.builds[pid]
            continue
        if piece is None:
            piece = B.BuildPiece(pid, f["kind"], f["mat"], f["ix"], f["iy"], f["z"], f["d"], f["own"], f["hp"], f["max"])
            for center, size in B.piece_boxes(piece.kind, piece.ix, piece.iy, piece.z, piece.direction):
                piece.boxes.append(sim.collision.add(Box.from_center(center, size, "build", pid)))
            sim.builds[pid] = piece
            sim._build_keys[piece.key] = pid
        else:
            piece.hp = f.get("hp", piece.hp)


def containers_fingerprint(sim) -> list:
    """Lets a client check that its mirror built the same containers as the server."""
    return [len(sim.containers), round(sum(k.x + 2 * k.y + 3 * k.z for k in sim.containers), 1)]
