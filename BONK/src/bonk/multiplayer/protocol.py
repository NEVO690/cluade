"""BONK! network protocol: newline-delimited JSON over TCP.

Client -> server messages (all validated by `validate_client_message`):
  hello        {name, skin, version}
  list_rooms   {}
  create_room  {name, bots, max_players}
  join_room    {room}
  leave_room   {}
  ready        {ready}
  start_game   {}                       host only
  inp          {seq, mx, my, j, w}      movement wish; never a position
  ping         {ts}

Server -> client messages:
  welcome, error, rooms, room, game_state, snap, events, tiles, results,
  game_over, player_left, pong

The server is authoritative: clients only send *inputs*.  Positions, finish
order, eliminations, winners and rewards are computed on the server.
"""

import json
import math

PROTOCOL_VERSION = 1
DEFAULT_PORT = 7777
MAX_LINE = 8192  # bytes per client message
SNAPSHOT_HZ = 20
MAX_INPUTS_PER_SECOND = 90

# type -> {field: (python types, required)}
CLIENT_SCHEMAS = {
    "hello": {"name": (str, True), "skin": (str, False), "version": (int, True)},
    "list_rooms": {},
    "create_room": {"name": (str, False), "bots": (int, False), "max_players": (int, False)},
    "join_room": {"room": (str, True)},
    "leave_room": {},
    "ready": {"ready": (bool, True)},
    "start_game": {},
    "inp": {"seq": (int, True), "mx": ((int, float), True), "my": ((int, float), True), "j": (bool, True),
            "w": (bool, False)},
    "ping": {"ts": ((int, float), False)},
}


class ProtocolError(ValueError):
    pass


def encode(msg):
    return (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")


def decode_line(line):
    if len(line) > MAX_LINE:
        raise ProtocolError("message too long")
    try:
        msg = json.loads(line.decode("utf-8") if isinstance(line, bytes) else line)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProtocolError("invalid JSON: %s" % exc) from exc
    if not isinstance(msg, dict) or not isinstance(msg.get("t"), str):
        raise ProtocolError("message must be an object with a 't' field")
    return msg


def validate_client_message(msg):
    """Raise ProtocolError unless `msg` is a well-formed client message."""
    t = msg.get("t")
    schema = CLIENT_SCHEMAS.get(t)
    if schema is None:
        raise ProtocolError("unknown message type %r" % t)
    for field, (types, required) in schema.items():
        if field not in msg:
            if required:
                raise ProtocolError("%s: missing field %s" % (t, field))
            continue
        v = msg[field]
        if isinstance(v, bool) and types is not bool:  # bool is an int subclass in Python
            raise ProtocolError("%s.%s: wrong type" % (t, field))
        if not isinstance(v, types):
            raise ProtocolError("%s.%s: wrong type" % (t, field))
        if isinstance(v, float) and not math.isfinite(v):
            raise ProtocolError("%s.%s: not a finite number" % (t, field))
    extra = set(msg) - set(schema) - {"t"}
    if extra:
        raise ProtocolError("%s: unexpected fields %s" % (t, sorted(extra)))
    return msg


def clean_name(name, default="Player"):
    name = "".join(ch for ch in str(name) if ch.isprintable()).strip()[:16]
    return name or default


def pack_char(ch):
    """Compact per-character snapshot row."""
    flags = (1 if ch.grounded else 0) | (2 if ch.finished else 0) | (4 if ch.eliminated else 0) | \
            (8 if ch.celebrate else 0) | (16 if ch.grace > 0 else 0)
    return [ch.id, round(ch.x, 3), round(ch.y, 3), round(ch.z, 3), round(ch.yaw, 3), round(ch.vx, 2),
            round(ch.vy, 2), round(ch.vz, 2), ch.state, flags, round(ch.progress, 1),
            ch.finish_place or 0, ch.elim_reason or ""]


def unpack_char(row, ch):
    (_, ch.x, ch.y, ch.z, ch.yaw, ch.vx, ch.vy, ch.vz, ch.state, flags, ch.progress, place, reason) = row
    ch.grounded = bool(flags & 1)
    ch.finished = bool(flags & 2)
    ch.eliminated = bool(flags & 4)
    ch.celebrate = bool(flags & 8)
    ch.grace = 0.5 if flags & 16 else 0.0
    ch.finish_place = place or None
    ch.elim_reason = reason or None
    return ch
