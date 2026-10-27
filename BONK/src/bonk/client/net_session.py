"""Online show: draws what the authoritative server reports and sends our inputs.

The client keeps a local copy of the course only for drawing (obstacles are
pure functions of the server's course clock; vanishing-tile triggers come
from the server).  It never decides who finished, fell or won.
"""

import time

from ..game.game_state import GameState, Outcome
from ..game.match_report import MatchReport
from ..sim.character import Character
from ..multiplayer.protocol import unpack_char
from .input import Gamepad, KeyboardMouse, frame_to_command
from .render.camera import FollowCamera
from .render.character_view import CharacterView
from .render.course_view import CourseView
from .render.effects import Effects


class _Part:
    def __init__(self, d):
        self.id, self.name, self.skin_id, self.is_bot = d["id"], d["name"], d["skin"], d["bot"]
        self.title = None


class _Result:
    def __init__(self, d):
        self.__dict__.update(d)


class _Settings:
    countdown = 4.0


class RemoteRound:
    """Mirror of the server's RoundSimulation, with the attributes the HUD reads."""

    def __init__(self, loaded_map, participants, alive, qualify, final, time_limit):
        self.map = loaded_map
        self.world = loaded_map.build_world()
        self.world.time_limit = time_limit
        self.characters = [Character(p.id, p.name, p.skin_id, p.is_bot) for p in participants if p.id in alive]
        self._by = {c.id: c for c in self.characters}
        self.qualify_count = qualify
        self.is_final = final
        self.t = 0.0
        self.race_time = 0.0
        self.left = time_limit
        self.finish_order = []
        self.results = []
        sp = loaded_map.spawn_points(len(self.characters))
        for c, (x, y, z) in zip(self.characters, sp):
            c.place_at(x, y, z)
            c.prev_pos = (x, y, z)

    def by_id(self, cid):
        return self._by.get(cid)

    @property
    def time_left(self):
        return self.left

    def standings(self):
        def key(c):
            if c.finished:
                return (0, c.finish_place or 99, 0.0)
            if c.eliminated:
                return (2, 0, -c.progress)
            return (1, 0, -c.progress)
        return sorted(self.characters, key=key)

    def result_for(self, cid):
        for r in self.results:
            if r.id == cid:
                return r
        return None


class RemoteGame:
    """Mirror of the GameManager state for the HUD."""

    def __init__(self):
        self.state = GameState.LOBBY
        self.state_time = 0.0
        self.round_index = 0
        self.total_rounds = 1
        self.round = None
        self.participants = {}
        self.local_out = False
        self.settings = _Settings()
        self.history = []
        self.final_standings = []
        self.champion_id = None
        self.local_report = None

    def continue_after_results(self):
        pass  # the server advances by itself after a few seconds


class NetSession:
    def __init__(self, app, client):
        self.app = app
        self.client = client
        self.profile = app.profile
        self.LOCAL = client.player_id
        self.gm = RemoteGame()
        self.course_view = None
        self.views = {}
        self.effects = Effects(app.render, font=app.theme.font("title"))
        self.camera = FollowCamera(app.camera, app.camLens)
        self.camera.distance = self.profile.settings["camera_distance"]
        self.keyboard = KeyboardMouse(app, self.profile.settings)
        self.gamepad = Gamepad(app)
        self.sun = app.sun
        self.paused = False
        self.finished = False
        self.spectate_id = None
        self.last_input = 0.0
        self.snap_interval = 0.05
        self.auto_driver = None  # autoplay testing: a bot brain steering through normal inputs
        client.handlers.append(self._on_message)

    def start(self, first_state_msg=None):
        self.app.screens.reset_to("hud", session=self)
        self.keyboard.capture_mouse(True)
        self.app.sounds.play_music("music_race")
        if first_state_msg is not None:
            self._on_message(first_state_msg)

    # ------------------------------------------------------------------ messages
    def _on_message(self, msg):
        t = msg.get("t")
        hud = self.app.screens.get("hud")
        gm = self.gm
        if t == "game_state":
            gm.participants = {p["id"]: _Part(p) for p in msg["participants"]}
            gm.round_index = msg["round"]
            gm.total_rounds = msg["total"]
            prev = gm.state
            gm.state = msg["state"]
            gm.state_time = 0.0
            gm.settings.countdown = msg.get("countdown", 4.0)
            if gm.state == GameState.COUNTDOWN and msg["map"]:
                self._build_round(msg)
                rnd = gm.round
                sub = ("FINAL ROUND - first to the finish wins!" if rnd.is_final else
                       "Top %d of %d qualify" % (rnd.qualify_count, len(rnd.characters)))
                hud.round_intro(gm.round_index + 1, gm.total_rounds, rnd.map, sub)
                if self.LOCAL not in msg["alive"]:
                    gm.local_out = True
            elif gm.state == GameState.ROUND_START:
                hud.flash("GO!", "", "secondary", 1.0, big=True)
                self.app.sounds.play("go")
            elif gm.state == GameState.ROUND_END and prev != GameState.ROUND_END:
                me = gm.round.by_id(self.LOCAL) if gm.round else None
                if me is not None and (me.celebrate or me.finished):
                    hud.flash("QUALIFIED!", "Waiting for the others...", "success", 3.0, big=True)
                elif me is not None:
                    hud.flash("ROUND OVER", "", "muted", 3.0, big=True)
        elif t == "snap":
            self._apply_snapshot(msg)
        elif t == "events":
            for kind, cid, data in msg["ev"]:
                self._on_event(kind, cid, data)
        elif t == "results":
            entries = [_Result(r) for r in msg["results"]]
            if gm.round is not None:
                gm.round.results = entries
            gm.history.append((msg["map"], entries))
            mine = next((r for r in entries if r.id == self.LOCAL), None)
            if mine is not None and mine.outcome == Outcome.ELIMINATED:
                gm.local_out = True
            gm.state = GameState.RESULTS
            hud.show_round_results(gm.history[-1])
            hud.toast("Next round starts automatically...")
        elif t == "player_left":
            hud.feed("%s left the show" % msg["name"], "danger")
        elif t == "game_over":
            self._game_over(msg)

    def _build_round(self, msg):
        if self.course_view is not None:
            self.course_view.destroy()
        for v in self.views.values():
            v.destroy()
        self.views.clear()
        self.effects.clear()
        loaded = self.app.maps.get(msg["map"])
        parts = list(self.gm.participants.values())
        rnd = RemoteRound(loaded, parts, set(msg["alive"]), msg["qualify"], msg["final"], msg["time_limit"])
        self.gm.round = rnd
        self.course_view = CourseView(self.app, loaded, rnd.world)
        cat = self.profile.catalog
        font = self.app.theme.font("bold")
        for ch in rnd.characters:
            p = self.gm.participants[ch.id]
            self.views[ch.id] = CharacterView(self.app.loader, cat.get(p.skin_id), self.app.render, p.name,
                                              is_local=ch.id == self.LOCAL, font=font)
        me = rnd.by_id(self.LOCAL)
        tgt = me or rnd.characters[0]
        self.camera.world = rnd.world
        self.camera.snap(tgt.x, tgt.y, tgt.z, 0.0)

    def _apply_snapshot(self, msg):
        rnd = self.gm.round
        if rnd is None:
            return
        rnd.t = msg["ct"]
        rnd.race_time = msg["rt"]
        rnd.left = msg["left"]
        for row in msg["chars"]:
            ch = rnd.by_id(row[0])
            if ch is None:
                continue
            ch.prev_pos = (ch.x, ch.y, ch.z)
            unpack_char(row, ch)
        rnd.finish_order = [rnd.by_id(i) for i in msg.get("fin", []) if rnd.by_id(i)]
        for tile in rnd.world.tiles:
            tile.triggered_at = self.client.tiles.get(tile.id)
        if self.client.prev_snap_time:
            self.snap_interval = max(0.02, min(0.2, self.client.snap_time - self.client.prev_snap_time))
        me = rnd.by_id(self.LOCAL)
        if me is not None and me.eliminated and not self.gm.local_out:
            self.gm.local_out = True

    def _on_event(self, kind, cid, data):
        rnd = self.gm.round
        if rnd is None:
            return
        ch = rnd.by_id(cid)
        if ch is None:
            return
        local = cid == self.LOCAL
        hud = self.app.screens.get("hud")
        if kind == "jump" and local:
            self.app.sounds.play("jump")
        elif kind == "bonk":
            self.effects.popup(ch.x, ch.y, ch.z + 1.8, "BONK!")
            self.effects.stars(ch.x, ch.y, ch.z + 1.4)
            self.app.sounds.play("bonk", 1.0 if local else 0.5)
        elif kind == "hit":
            self.effects.stars(ch.x, ch.y, ch.z + 1.0)
            if local:
                self.camera.add_shake(0.5)
                self.app.sounds.play("hit")
        elif kind == "fall":
            self.effects.splash(ch.x, ch.y, self.course_view.void_z + 0.2, rnd.map.theme.get("void", "#ff6fb5"))
            if local:
                self.app.sounds.play("splash")
        elif kind == "finish":
            self.effects.confetti(ch.x, ch.y, ch.z + 1.0, 50 if local else 15)
            hud.feed("%s finished #%d" % (ch.name, data or 0), "success")
            if local:
                self.app.sounds.play("finish")
                hud.flash("FINISHED! #%d" % (data or 0), "", "success", 2.5, big=True)
        elif kind == "eliminated":
            hud.feed("%s was eliminated" % ch.name, "danger")
            if local:
                hud.flash("ELIMINATED", "", "danger", 2.5, big=True)
                self.app.sounds.play("eliminated")
        elif kind == "checkpoint" and local:
            self.app.sounds.play("checkpoint")

    def _game_over(self, msg):
        gm = self.gm
        gm.state = GameState.GAME_OVER
        gm.final_standings = [(s["place"], s["id"]) for s in msg["standings"]]
        champ = next((s for s in msg["standings"] if s["place"] == 1), None)
        gm.champion_id = champ["id"] if champ else None
        rep_d = msg["reports"].get(self.LOCAL)
        report = MatchReport.from_dict(rep_d) if rep_d else None
        summary = None
        if report is not None:
            summary = self.profile.apply_match_report(report, gm.total_rounds, match_id="online:" + msg["match"])
        self.finished = True
        self.keyboard.capture_mouse(False)
        self.app.end_net_session(self, report, summary, msg.get("champion"), bool(report and report.won), msg)

    # ------------------------------------------------------------------ per frame
    def focus_char(self):
        rnd = self.gm.round
        if rnd is None or not rnd.characters:
            return None
        me = rnd.by_id(self.LOCAL)
        if me is not None and not self.gm.local_out:
            return me
        alive = [c for c in rnd.standings() if not c.eliminated]
        if self.spectate_id is None or rnd.by_id(self.spectate_id) is None:
            self.spectate_id = (alive or rnd.characters)[0].id
        return rnd.by_id(self.spectate_id)

    def _camera_target(self, focus):
        """Where the camera looks: never down into the goo, and it waits while respawning."""
        v = self.views.get(focus.id)
        pos = tuple(v.root.getPos()) if v is not None and v.visible else (focus.x, focus.y, focus.z)
        last = getattr(self, "_last_cam_target", None)
        if focus.state == "RESPAWNING" and last is not None:
            return last
        floor = self.course_view.void_z + 2.0 if self.course_view is not None else -50.0
        pos = (pos[0], pos[1], max(pos[2], floor))
        self._last_cam_target = pos
        return pos

    def cycle_spectate(self, step):
        rnd = self.gm.round
        if rnd is None:
            return
        ids = [c.id for c in rnd.standings() if not c.eliminated] or [c.id for c in rnd.characters]
        idx = ids.index(self.spectate_id) if self.spectate_id in ids else 0
        self.spectate_id = ids[(idx + step) % len(ids)]

    def set_paused(self, flag):
        self.paused = flag  # online: the show keeps running
        self.keyboard.capture_mouse(not flag)

    def update(self, dt):
        if self.finished:
            return
        if self.client.status != "online":
            self.app.toasts.show("Disconnected: %s" % (self.client.error or "connection lost"), "danger", 5.0)
            self.finished = True
            self.keyboard.capture_mouse(False)
            self.app.abort_net_session(self)
            return
        gm = self.gm
        gm.state_time += dt
        frame = None if self.paused else self.keyboard.poll(dt)
        pad = None if self.paused else self.gamepad.poll(dt)
        if pad is not None and (abs(pad.forward) + abs(pad.strafe) > 0 or pad.jump):
            frame = pad
        now = time.monotonic()
        racing = gm.state in (GameState.ROUND_START, GameState.ROUND_ACTIVE)
        if frame is not None:
            self.camera.rotate(frame.look_x, frame.look_y)
        if racing and now - self.last_input >= 1 / 60.0 and (frame is not None or self.auto_driver is not None):
            me = gm.round.by_id(self.LOCAL) if gm.round else None
            if self.auto_driver is not None and me is not None:
                cmd = self.auto_driver(me, gm.round)
            else:
                cmd = frame_to_command(frame, self.camera)
            self.client.send_input(cmd.move_x, cmd.move_y, cmd.jump, cmd.walk)
            self.last_input = now
        rnd = gm.round
        if rnd is None or self.course_view is None:
            return
        alpha = min(1.0, (now - self.client.snap_time) / self.snap_interval) if self.client.snap_time else 1.0
        for ch in rnd.characters:
            v = self.views.get(ch.id)
            if v is not None:
                v.sync(ch, alpha, dt)
        t_vis = rnd.t + min(self.snap_interval, now - self.client.snap_time) if self.client.snap_time else rnd.t
        self.course_view.update(t_vis - self.snap_interval, dt, self.app.camera.getPos())
        focus = self.focus_char()
        if focus is not None:
            pos = self._camera_target(focus)
            self.camera.update(pos[0], pos[1], pos[2], focus.grounded, dt)
            self.sun.setPos(pos[0] + 10, pos[1] - 6, pos[2] + 25)
            self.sun.lookAt(pos[0], pos[1], pos[2])
        for cid, v in self.views.items():
            v.show_tag(cid != (focus.id if focus else None) or gm.local_out)
        self.effects.update(dt)

    def leave(self):
        self.client.leave_room()
        self.finished = True
        self.keyboard.capture_mouse(False)
        self.app.abort_net_session(self)

    def destroy(self):
        if self.client is not None and self._on_message in self.client.handlers:
            self.client.handlers.remove(self._on_message)
        if self.course_view is not None:
            self.course_view.destroy()
        for v in self.views.values():
            v.destroy()
        self.views.clear()
        self.effects.destroy()
