"""MULTIPLAYER screen: connect to a BONK! server, browse/create rooms, ready up and start."""

from direct.gui.DirectGui import DirectEntry, DirectFrame

from ....multiplayer.client import NetworkClient
from ..theme import c
from ..widgets import Button, ScrollList, label, panel
from .common import BaseScreen


class MultiplayerScreen(BaseScreen):
    name = "multiplayer"
    uses_menu_scene = False

    def build(self):
        self.header("MULTIPLAYER", coins=False,
                    subtitle="Real online play through a BONK! server - the server decides every result")
        th = self.theme
        p = panel(self.root, th, (-0.7, 0.7, -0.62, 0.55), "panel", 0.92, 0.08, pos=(-0.85, 0, 0.0))
        label(p, th, "SERVER ADDRESS", (-0.62, 0.45), 0.038, "muted", "bold", "left")
        self.addr = DirectEntry(parent=p, initialText=self.app.profile.settings["server_address"], scale=0.05,
                                width=17, pos=(-0.62, 0, 0.34), frameColor=c("dark", 0.85), text_fg=c("text"),
                                entryFont=th.font("bold"))
        self.connect_btn = Button(p, th, "CONNECT", (-0.3, 0.2), (0.6, 0.1), self._toggle_connect, color="blue")
        self.status = label(p, th, "", (-0.62, 0.07), 0.037, "muted", "bold", "left", wordwrap=33)
        label(p, th, "No public servers are provided.\n"
                     "To play: one player runs  python run_server.py\n"
                     "and everyone connects to that computer's address\n"
                     "(e.g. 192.168.1.20:7777, or 127.0.0.1:7777 locally).\n"
                     "Online rewards come from server-verified results.",
              (0, -0.3), 0.032, "muted", "body")
        self.right = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        self._last_sig = None
        self._prev_state = None

    def on_show(self, **kw):
        self._last_sig = None
        self._refresh(force=True)

    @property
    def net(self):
        return self.app.net

    def _toggle_connect(self):
        if self.net is not None and self.net.status in ("online", "connecting"):
            self.net.close()
            self.app.net = None
            self._refresh(force=True)
            return
        addr = self.addr.get().strip() or "127.0.0.1:7777"
        prof = self.app.profile
        prof.set_setting("server_address", addr)
        prof.save()
        cli = NetworkClient(prof.name, prof.skins.equipped)
        cli.handlers.append(self._on_message)
        self.app.net = cli
        cli.connect(addr)
        self._refresh(force=True)

    def _on_message(self, msg):
        if msg.get("t") == "game_state" and msg.get("state") == "COUNTDOWN" and self.app.session is None:
            self.app.start_net_session(msg)
        elif msg.get("t") == "error":
            self.app.toasts.show(msg.get("msg", "Server error"), "danger", 3.5)

    def update(self, dt):
        self._refresh()

    def _refresh(self, force=False):
        net = self.net
        if net is None:
            sig = ("none",)
        else:
            sig = (net.status, net.error, repr(net.rooms), repr(net.room))
        if sig == self._last_sig and not force:
            return
        self._last_sig = sig
        th = self.theme
        if net is None or net.status in ("idle", "closed"):
            self.status["text"] = "Not connected." + ("\n" + net.error if net is not None and net.error else "")
            self.status["text_fg"] = c("danger" if net is not None and net.error else "muted")
            self.connect_btn.set_text("CONNECT")
            self.connect_btn.set_color("blue")
        elif net.status == "connecting":
            self.status["text"] = "Connecting..."
            self.status["text_fg"] = c("secondary")
            self.connect_btn.set_text("CANCEL")
            self.connect_btn.set_color("danger")
        else:
            self.status["text"] = "Connected as %s" % net.name
            self.status["text_fg"] = c("success")
            self.connect_btn.set_text("DISCONNECT")
            self.connect_btn.set_color("danger")
        self.right.destroy()
        self.right = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        if net is None or not net.online:
            p = panel(self.right, th, (-0.8, 0.8, -0.62, 0.55), "panel", 0.75, 0.08, pos=(0.85, 0, 0))
            label(p, th, "Connect to a server to see its rooms.", (0, 0), 0.042, "muted", "bold")
            return
        if net.room is None:
            self._room_list(net)
        else:
            self._room_view(net)

    def _room_list(self, net):
        th = self.theme
        label(self.right, th, "ROOMS", (0.1, 0.5), 0.05, "secondary", "title", "left")
        Button(self.right, th, "REFRESH", (1.0, 0.52), (0.3, 0.08), net.list_rooms, color="panel_hi", scale=0.032)
        Button(self.right, th, "CREATE ROOM", (1.42, 0.52), (0.42, 0.08), self._create, color="primary",
               scale=0.034)
        lst = ScrollList(self.right, th, (0.05, 1.65, -0.62, 0.43))
        if not net.rooms:
            row = lst.add_row(0.1)
            label(row, th, "No rooms yet - create one!", (0.85, -0.015), 0.04, "muted", "bold")
        for r in net.rooms:
            row = lst.add_row(0.11)
            bg = panel(row, th, (0, lst.width, -0.05, 0.05), "panel", 0.9, 0.04, shadow=False, pos=(0.05, 0, 0))
            label(bg, th, r["name"], (0.04, -0.01), 0.04, "text", "bold", "left")
            label(bg, th, "%d/%d players  +%d bots  host %s" % (r["players"], r["max"], r["bots"], r["host"]),
                  (0.75, -0.012), 0.03, "muted", "body", "left")
            b = Button(bg, th, "JOIN" if r["state"] == "waiting" else "IN GAME", (lst.width - 0.16, 0), (0.24, 0.07),
                       net.join_room, [r["id"]], color="success", scale=0.03)
            b.set_enabled(r["state"] == "waiting" and r["players"] < r["max"])

    def _create(self):
        self.net.create_room("%s's room" % self.net.name, bots=6, max_players=16)

    def _room_view(self, net):
        th = self.theme
        room = net.room
        p = panel(self.right, th, (-0.8, 0.8, -0.62, 0.55), "panel", 0.9, 0.08, pos=(0.85, 0, 0))
        label(p, th, room["name"], (-0.72, 0.45), 0.055, "secondary", "title", "left")
        label(p, th, "Bots added at start: %d  |  max %d players" % (room["bots"], room["max"]), (-0.72, 0.38), 0.032,
              "muted", "body", "left")
        for i, m in enumerate(room["members"]):
            y = 0.28 - i * 0.07
            host = m["id"] == room["host"]
            me = m["id"] == net.player_id
            label(p, th, ("[HOST] " if host else "") + m["name"] + (" (you)" if me else ""), (-0.72, y), 0.04,
                  "secondary" if me else "text", "bold", "left")
            label(p, th, "READY" if (m["ready"] or host) else "not ready", (0.72, y), 0.035,
                  "success" if (m["ready"] or host) else "muted", "bold", "right")
        mine = next(m for m in room["members"] if m["id"] == net.player_id)
        if net.is_host:
            others_ready = all(m["ready"] for m in room["members"] if m["id"] != net.player_id)
            b = Button(p, th, "START SHOW", (0.35, -0.5), (0.6, 0.1), net.start_game, color="primary")
            b.set_enabled(others_ready)
            if not others_ready:
                label(p, th, "Waiting for everyone to be ready", (0.35, -0.39), 0.03, "muted", "body")
        else:
            Button(p, th, "NOT READY" if mine["ready"] else "READY!", (0.35, -0.5), (0.6, 0.1), net.set_ready,
                   [not mine["ready"]], color="panel_hi" if mine["ready"] else "success")
        Button(p, th, "LEAVE ROOM", (-0.4, -0.5), (0.5, 0.1), net.leave_room, color="danger")
