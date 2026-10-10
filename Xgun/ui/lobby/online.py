"""Online match waiting room: host or join a server, see who's in, start."""
from __future__ import annotations

import logging
import socket

from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectGui import DirectFrame

from net import protocol as P
from ui import theme as T
from ui.widgets import Button, frame, text

log = logging.getLogger(__name__)


def lan_address() -> str:
    """This PC's LAN address (no packet is sent: UDP connect only picks a route)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def parse_address(value: str) -> tuple[str, int]:
    value = value.strip() or "127.0.0.1"
    host, _, port = value.rpartition(":") if value.count(":") == 1 else (value, "", "")
    if not host:
        host, port = value, ""
    try:
        return host, int(port) if port else P.DEFAULT_MATCH_PORT
    except ValueError:
        raise ValueError("The port after ':' must be a number.") from None


class OnlineLobby:
    def __init__(self, app, conn, server=None):
        self.app = app
        self.conn = conn
        self.server = server
        self.host = False
        self.root = app.aspect2d.attachNewNode("online-lobby")
        self.root.setBin("gui-popup", 40)
        DirectFrame(parent=self.root, frameSize=(-4, 4, -2, 2), frameColor=(0, 0, 0, 0.7), state=DGG.NORMAL)
        w, h = 1.3, 0.95
        frame(self.root, -w / 2, w / 2, -h / 2, h / 2, T.PANEL_LIGHT)
        DirectFrame(parent=self.root, frameSize=(-w / 2, w / 2, h / 2 - 0.008, h / 2), frameColor=T.PRIMARY)
        text(self.root, "ONLINE LOBBY", (0, h / 2 - 0.1), 0.06, T.TEXT, "black", "center")
        where = f"Friends join with  {lan_address()}:{server.port}" if server else "Waiting for the host to start"
        self.info = text(self.root, where, (0, h / 2 - 0.17), 0.034, T.ACCENT, "bold", "center")
        text(self.root, "Same network: use the address above. Over the internet the host must forward TCP port "
             f"{server.port if server else P.DEFAULT_MATCH_PORT}.", (0, h / 2 - 0.23), 0.026, T.TEXT_MUTED, "regular",
             "center", wrap=46)
        self.players = text(self.root, "Connecting...", (-0.55, 0.12), 0.036, T.TEXT, "semibold", wrap=30)
        self.count = text(self.root, "", (0.55, 0.12), 0.03, T.TEXT_DIM, "bold", "right")
        self.start_btn = Button(self.root, "START MATCH", self._start, pos=(0.3, -h / 2 + 0.1), size=(0.5, 0.09),
                                color=T.GOLD, hover=(1, 0.86, 0.45, 1), text_color=(0.1, 0.07, 0.0, 1), font="black")
        self.start_btn.set_enabled(False)
        Button(self.root, "LEAVE", self.leave, pos=(-0.3, -h / 2 + 0.1), size=(0.4, 0.09))
        app.taskMgr.add(self._poll, "online-lobby")

    def _poll(self, task):
        for msg in self.conn.poll():
            t = msg.get("t")
            if t == "lobby":
                self.host = bool(msg.get("host"))
                names = msg["players"]
                self.players.setText("\n".join(n + ("   (host)" if i == 0 else "") for i, n in enumerate(names)))
                bots = max(0, msg.get("bots", 0) - len(names) + 1)
                self.count.setText(f"{len(names)} player{'s' if len(names) != 1 else ''} + {bots} bots")
                self.start_btn.set_enabled(self.host)
                if not self.host:
                    self.start_btn.set_text("HOST STARTS")
            elif t == "start":
                self._close()
                self.app.start_online_match(self.conn, msg, self.server)
                return task.done
            elif t in ("error", "closed"):
                self.app.toasts.show(msg.get("msg", "Disconnected from the server."), "error", 4)
                self.leave()
                return task.done
        return task.cont

    def _start(self):
        if self.host:
            self.conn.send({"t": "start"})
            self.start_btn.set_enabled(False)
            self.start_btn.set_text("STARTING...")

    def leave(self):
        self.conn.close()
        if self.server is not None:
            self.server.stop()
            self.server = None
        self._close()

    def _close(self):
        self.app.taskMgr.remove("online-lobby")
        if self.root is not None:
            self.start_btn.destroy()
            self.root.removeNode()
            self.root = None
        if getattr(self.app, "online_lobby", None) is self:
            self.app.online_lobby = None
