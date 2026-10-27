"""Non-blocking BONK! network client.  Call `poll()` every frame; no threads needed.

Used by the Panda3D game *and* by the headless multiplayer tests.
"""

import errno
import json
import socket
import time

from .protocol import DEFAULT_PORT, PROTOCOL_VERSION


def parse_address(text, default_port=DEFAULT_PORT):
    text = (text or "").strip()
    if not text:
        return "127.0.0.1", default_port
    if ":" in text:
        host, _, port = text.rpartition(":")
        try:
            return host or "127.0.0.1", int(port)
        except ValueError:
            return host, default_port
    return text, default_port


class NetworkClient:
    STATUS_IDLE, STATUS_CONNECTING, STATUS_ONLINE, STATUS_CLOSED = "idle", "connecting", "online", "closed"

    def __init__(self, name="Player", skin="classic"):
        self.name = name
        self.skin = skin
        self.sock = None
        self.status = self.STATUS_IDLE
        self.error = None
        self._buf = b""
        self._out = b""
        self.player_id = None
        self.rooms = []
        self.room = None
        self.game_state = None  # last game_state message
        self.snapshot = None  # last snap message
        self.prev_snapshot = None
        self.snap_time = 0.0
        self.prev_snap_time = 0.0
        self.tiles = {}  # tile id -> triggered_at
        self.inbox = []  # every message received (consumers drain it)
        self.seq = 0
        self.last_message_time = 0.0
        self.connect_started = 0.0
        self.handlers = []

    # ------------------------------------------------------------------ connection
    def connect(self, address, timeout=5.0):
        host, port = parse_address(address)
        self.close()
        self.error = None
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror as exc:
            self.status = self.STATUS_CLOSED
            self.error = "Unknown host %s (%s)" % (host, exc)
            return False
        family, stype, proto, _, addr = infos[0]
        self.sock = socket.socket(family, stype, proto)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.setblocking(False)
        self.timeout = timeout
        try:
            self.sock.connect(addr)
        except (BlockingIOError, InterruptedError):
            pass
        except OSError as exc:
            if exc.errno not in (errno.EINPROGRESS, errno.EWOULDBLOCK, getattr(errno, "WSAEWOULDBLOCK", -1)):
                self._fail("Could not connect: %s" % exc)
                return False
        self.status = self.STATUS_CONNECTING
        self.connect_started = time.monotonic()
        self.send({"t": "hello", "name": self.name, "skin": self.skin, "version": PROTOCOL_VERSION})
        return True

    def _fail(self, msg):
        self.error = msg
        self.close()

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        if self.status != self.STATUS_IDLE:
            self.status = self.STATUS_CLOSED
        self._buf = b""
        self._out = b""
        self.room = None

    @property
    def online(self):
        return self.status == self.STATUS_ONLINE

    # ------------------------------------------------------------------ io
    def send(self, msg):
        if self.sock is None:
            return False
        self._out += (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
        return True

    def send_input(self, mx, my, jump, walk):
        self.seq += 1
        return self.send({"t": "inp", "seq": self.seq, "mx": round(float(mx), 3), "my": round(float(my), 3),
                          "j": bool(jump), "w": bool(walk)})

    def poll(self):
        """Flush outgoing data and process everything received.  Returns the new messages."""
        if self.sock is None:
            return []
        if self._out:
            try:
                n = self.sock.send(self._out)
                self._out = self._out[n:]
            except (BlockingIOError, InterruptedError):
                pass
            except OSError as exc:
                if self.status == self.STATUS_CONNECTING and exc.errno in (errno.ENOTCONN, errno.EPIPE):
                    if time.monotonic() - self.connect_started > self.timeout:
                        self._fail("Connection timed out")
                    return []
                self._fail("Connection lost: %s" % exc)
                return []
        new = []
        while self.sock is not None:
            try:
                data = self.sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                break
            except OSError as exc:
                if exc.errno in (errno.ENOTCONN,) and self.status == self.STATUS_CONNECTING:
                    break
                self._fail("Connection lost: %s" % exc)
                break
            if not data:
                self._fail("Server closed the connection")
                break
            self._buf += data
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except ValueError:
                continue
            self._handle(msg)
            new.append(msg)
        if self.status == self.STATUS_CONNECTING and time.monotonic() - self.connect_started > self.timeout:
            self._fail("Connection timed out (is the server running?)")
        self.inbox.extend(new)
        del self.inbox[:-500]
        return new

    def _handle(self, msg):
        t = msg.get("t")
        self.last_message_time = time.monotonic()
        if t == "welcome":
            self.status = self.STATUS_ONLINE
            self.player_id = msg["id"]
            self.name = msg.get("name", self.name)
        elif t == "rooms":
            self.rooms = msg["rooms"]
        elif t == "room":
            room = msg["room"]
            self.room = room if any(m["id"] == self.player_id for m in room["members"]) else None
        elif t == "game_state":
            self.game_state = msg
            if msg["state"] == "COUNTDOWN":
                self.tiles = {}
        elif t == "snap":
            self.prev_snapshot, self.prev_snap_time = self.snapshot, self.snap_time
            self.snapshot, self.snap_time = msg, time.monotonic()
            for tid, ta in msg.get("tiles", []):
                self.tiles[tid] = ta
        elif t == "error":
            self.error = msg.get("msg")
        for h in list(self.handlers):
            h(msg)

    # ------------------------------------------------------------------ requests
    def list_rooms(self):
        return self.send({"t": "list_rooms"})

    def create_room(self, name="", bots=6, max_players=16):
        return self.send({"t": "create_room", "name": name, "bots": int(bots), "max_players": int(max_players)})

    def join_room(self, rid):
        return self.send({"t": "join_room", "room": rid})

    def leave_room(self):
        return self.send({"t": "leave_room"})

    def set_ready(self, flag):
        return self.send({"t": "ready", "ready": bool(flag)})

    def start_game(self):
        return self.send({"t": "start_game"})

    @property
    def is_host(self):
        return self.room is not None and self.room.get("host") == self.player_id
