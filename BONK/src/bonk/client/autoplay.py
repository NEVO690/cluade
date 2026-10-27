"""Automated end-to-end run of the real client (used for testing and screenshots).

    python main.py --autoplay [--shots DIR] [--maps id1,id2] [--bots N] [--no-tour] [--timeout S]

* tours every menu screen and saves a screenshot of each;
* starts a show and lets a HARD bot brain steer *your* character through the
  normal input path (no shortcuts in the game rules);
* continues between rounds automatically, waits for the results screen,
  writes autoplay_report.json and exits.
"""

import json
import logging
import os
import random

from panda3d.core import Filename

from ..ai import make_bot
from ..game.game_state import GameState

TOUR = ["main", "modes", "lobby", "maps", "skins", "shop", "profile", "levels", "ranks", "titles", "quests",
        "achievements", "settings", "multiplayer"]


class _ErrorCollector(logging.Handler):
    """Every ERROR logged during the run ends up in the report (nothing is hidden)."""

    def __init__(self, sink):
        super().__init__(logging.ERROR)
        self.sink = sink

    def emit(self, record):
        msg = record.getMessage()
        if record.exc_info:
            msg += " | " + repr(record.exc_info[1])
        self.sink.append(msg)


class AutoHuman:
    """Replaces the keyboard for the local player; uses the bot brain through the same commands."""

    def __init__(self, difficulty="HARD", seed=5):
        self.difficulty = difficulty
        self.rng = random.Random(seed)
        self.bot = None
        self.world = None

    def command(self, ch, rnd):
        if self.world is not rnd.world:
            self.world = rnd.world
            self.bot = make_bot(self.difficulty, random.Random(self.rng.random()), rnd.world)
        return self.bot.command(ch, rnd)


def _arg(argv, name, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


class AutoPlay:
    def __init__(self, argv):
        self.shots = _arg(argv, "--shots")
        self.maps = _arg(argv, "--maps")
        self.bots = int(_arg(argv, "--bots", "7"))
        self.tour = "--no-tour" not in argv
        self.timeout = float(_arg(argv, "--timeout", "900"))
        self.difficulty = _arg(argv, "--difficulty", "NORMAL")
        # Multiplayer autoplay: --mp-host ADDR or --mp-join ADDR, plus --room-file shared path.
        self.mp_host = _arg(argv, "--mp-host")
        self.mp_join = _arg(argv, "--mp-join")
        self.room_file = _arg(argv, "--room-file")
        self.app = None
        self.t = 0.0
        self.phase = "boot"
        self.phase_t = 0.0
        self.tour_index = 0
        self.log = []
        self.shot_count = 0
        self.session_seen = None
        self.game_shots = {}
        self.report = {"screens_visited": [], "states": [], "screenshots": [], "errors": []}

    def attach(self, app):
        self.app = app
        logging.getLogger().addHandler(_ErrorCollector(self.report["errors"]))
        if self.shots:
            os.makedirs(self.shots, exist_ok=True)

    def shot(self, name):
        if not self.shots or self.app.win is None:
            return
        self.shot_count += 1
        path = os.path.join(self.shots, "%02d_%s.png" % (self.shot_count, name))
        self.app.graphicsEngine.renderFrame()
        self.app.win.saveScreenshot(Filename.fromOsSpecific(path))
        self.report["screenshots"].append(os.path.basename(path))

    def _goto(self, phase):
        self.phase = phase
        self.phase_t = 0.0

    def update(self, dt):
        self.t += dt
        self.phase_t += dt
        app = self.app
        if self.t > self.timeout:
            self.report["errors"].append("timeout in phase %s" % self.phase)
            self._finish()
            return
        if self.phase == "boot":
            if self.phase_t > 1.5:
                self.shot("splash")
                app.screens.reset_to("main")
                if self.mp_host or self.mp_join:
                    self._goto("mp_connect")
                else:
                    self._goto("tour" if self.tour else "start")
        elif self.phase == "tour":
            if self.phase_t > 0.8:
                name = TOUR[self.tour_index]
                if app.screens.current.name != name:
                    app.screens.show(name)
                    self.phase_t = 0.3
                    return
                self.shot("screen_" + name)
                self.report["screens_visited"].append(name)
                self.tour_index += 1
                self.phase_t = 0.0
                if self.tour_index >= len(TOUR):
                    app.screens.reset_to("main")
                    self._goto("start")
        elif self.phase.startswith("mp_"):
            self._mp_step()
        elif self.phase == "start":
            if self.phase_t > 0.5:
                from .session import ShowConfig
                ids = self.maps.split(",") if self.maps else app.maps.show_playlist()
                app.start_show(ShowConfig(ids, self.bots, self.difficulty, seed=11,
                                          mode="quick_play" if len(ids) == 1 else "ai_showdown"))
                self._goto("loading")
        elif self.phase == "loading":
            if app.session is not None:
                s = app.session
                s.human.command = AutoHuman().command
                s.gm.add_listener(self._on_game)
                self.session_seen = s
                self._goto("playing")
        elif self.phase == "playing":
            s = app.session
            if s is None:
                self._goto("results")
                return
            gm = s.gm
            hud = app.screens.get("hud")
            key = (gm.round_index, gm.state)
            if key not in self.game_shots:
                self.game_shots[key] = 0.0
            self.game_shots[key] += dt
            el = self.game_shots[key]
            tag = "r%d_%s" % (gm.round_index + 1, gm.state.lower())
            if gm.state == GameState.COUNTDOWN and 1.5 < el <= 1.5 + dt:
                self.shot(tag)
            if gm.state == GameState.ROUND_ACTIVE:
                for at in (4.0, 12.0, 22.0):
                    if at < el <= at + dt:
                        self.shot("%s_%02ds" % (tag, at))
            if gm.state == GameState.ROUND_END and 1.0 < el <= 1.0 + dt:
                self.shot(tag)
            if gm.state == GameState.RESULTS and not hud.results.isHidden():
                if 0.8 < el <= 0.8 + dt:
                    self.shot(tag)
                if el > 1.6:
                    hud._continue()
        elif self.phase == "results":
            if self.phase_t > 2.5:
                cur = app.screens.current.name
                self.shot("final_" + cur)
                if cur == "victory":
                    app.screens.reset_to("results")
                    self.phase_t = 0.0
                    return
                self._finish()

    def _mp_step(self):
        """Drive the MULTIPLAYER screen exactly like a player clicking through it."""
        app = self.app
        scr = app.screens.get("multiplayer")
        if self.phase == "mp_connect" and self.phase_t > 0.5:
            app.screens.show("multiplayer")
            scr.addr.enterText(self.mp_host or self.mp_join)
            scr._toggle_connect()
            self._goto("mp_lobby")
        elif self.phase == "mp_lobby":
            net = app.net
            if net is None or not net.online:
                if self.phase_t > 15:
                    self.report["errors"].append("could not connect: %s" % (net.error if net else None))
                    self._finish()
                return
            if self.mp_host:
                if net.room is None and self.phase_t > 0.5 and not getattr(self, "_created", False):
                    scr._create()
                    self._created = True
                elif net.room is not None:
                    if self.room_file and not os.path.exists(self.room_file):
                        with open(self.room_file, "w") as fh:
                            fh.write(net.room["id"])
                    others = [m for m in net.room["members"] if m["id"] != net.player_id]
                    if others and all(m["ready"] for m in others) and self.phase_t > 1.0:
                        self.shot("mp_room_host")
                        net.start_game()
                        self._goto("mp_wait_game")
            else:
                if net.room is None and self.room_file and os.path.exists(self.room_file):
                    rid = open(self.room_file).read().strip()
                    if rid and not getattr(self, "_joined", False):
                        net.join_room(rid)
                        self._joined = True
                elif net.room is not None and not getattr(self, "_readied", False):
                    net.set_ready(True)
                    self._readied = True
                    self.shot("mp_room_guest")
                    self._goto("mp_wait_game")
        elif self.phase == "mp_wait_game":
            if app.session is not None:
                app.session.auto_driver = AutoHuman().command
                self.session_seen = app.session
                self._goto("mp_playing")
            elif self.phase_t > 30:
                self.report["errors"].append("online show never started")
                self._finish()
        elif self.phase == "mp_playing":
            s = app.session
            if s is None:
                self._goto("results")
                return
            for at in (6.0, 14.0):
                if at < self.phase_t <= at + 1 / 30.0 + 0.02:
                    self.shot("mp_race_%02ds" % at)

    def _on_game(self, kind, data):
        if kind == "state":
            self.report["states"].append(data)

    def _finish(self):
        app = self.app
        s = self.session_seen
        if s is not None and hasattr(s, "client"):
            seen = sorted(c.name for c in (s.gm.round.characters if s.gm.round else []))
            self.report.update({"online": True, "players_seen": seen,
                                "coins_after": app.profile.currency.balance,
                                "final_state": s.gm.state,
                                "rounds_played": [m for m, _ in s.gm.history]})
        elif s is not None:
            gm = s.gm
            rep = gm.local_report
            self.report.update({
                "final_state": gm.state,
                "rounds_played": [m for m, _ in gm.history],
                "champion": gm.participants[gm.champion_id].name if gm.champion_id else None,
                "local_report": rep.to_dict() if rep else None,
                "coins_after": app.profile.currency.balance,
                "level_after": app.profile.xp.level,
                "rank_after": app.profile.ranks.tier["id"],
            })
        out = os.path.join(self.shots or ".", "autoplay_report.json")
        with open(out, "w") as fh:
            json.dump(self.report, fh, indent=2)
        print("AUTOPLAY DONE", json.dumps({k: self.report.get(k) for k in
                                           ("final_state", "rounds_played", "champion", "coins_after",
                                            "level_after", "rank_after", "errors")}))
        app.userExit()
