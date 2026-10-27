"""A running BONK! AI SHOWDOWN on this computer: GameManager + 3D views + HUD + effects.

The session never decides game rules itself; it feeds player input into the
GameManager and draws whatever the simulation says happened.
"""

import random

from ..ai import make_bot
from ..ai.bot_difficulty import mixed_lineup
from ..game.game_manager import GameManager, GameSettings, Participant
from ..game.game_state import GameState, Outcome
from ..sim.character import IDLE_COMMAND
from .input import Gamepad, KeyboardMouse, frame_to_command
from .render.camera import FollowCamera
from .render.character_view import CharacterView
from .render.course_view import CourseView
from .render.effects import Effects

BOT_NAMES = [
    "Wobblebean", "Sir Bonkalot", "Jellyjump", "Noodle", "Captain Splat", "Bumbles", "Zippy",
    "Puddingpop", "Boing Boing", "Marshmallow", "Turbo Toast", "Wigglewort", "Gumdrop", "Doodlebug",
    "Fizzlepop", "Kerplunk", "Sprinkles", "Bouncy Bob", "Twinkletoes", "Pogo", "Biscuit", "Muffin Top",
    "Dizzy Dot", "Hopscotch", "Flapjack", "Squishy", "Bubbles", "Pickle", "Tater Tot", "Wombat",
]


class HumanController:
    """Feeds the latest player input to the simulation."""

    def __init__(self):
        self.cmd = IDLE_COMMAND

    def command(self, ch, rnd):
        return self.cmd


class ShowConfig:
    def __init__(self, map_ids, bot_count=15, difficulty="MIXED", seed=None, mode="ai_showdown"):
        self.map_ids = list(map_ids)
        self.bot_count = bot_count
        self.difficulty = difficulty
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.mode = mode

    def lineup(self, profile):
        rng = random.Random(self.seed)
        names = rng.sample(BOT_NAMES, k=min(self.bot_count, len(BOT_NAMES)))
        diffs = (mixed_lineup(self.bot_count, rng) if self.difficulty == "MIXED"
                 else [self.difficulty] * self.bot_count)
        skins = [s.id for s in profile.catalog.ordered()]
        parts = [Participant("you", profile.name, profile.skins.equipped, False,
                             self.difficulty, profile.titles.equipped_name())]
        for i in range(self.bot_count):
            parts.append(Participant("bot%d" % i, names[i % len(names)], rng.choice(skins), True, diffs[i]))
        return parts


class GameSession:
    LOCAL = "you"

    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.profile = app.profile
        maps = [app.maps.get(m) for m in config.map_ids]
        self.participants = config.lineup(self.profile)
        self.human = HumanController()
        rng = random.Random(config.seed + 7)

        def factory(part, ch, rnd):
            if part.id == self.LOCAL:
                return self.human
            return make_bot(part.difficulty, random.Random(rng.random()), rnd.world)

        self.gm = GameManager(maps, self.participants, factory,
                              GameSettings(countdown=4.0, round_start=1.0, round_end=3.2),
                              seed=config.seed, local_player_id=self.LOCAL, mode=config.mode)
        self.gm.add_listener(self._on_game_event)
        self.paused = False
        self.course_view = None
        self.views = {}
        self.effects = Effects(app.render, font=app.theme.font("title"))
        self.camera = FollowCamera(app.camera, app.camLens)
        self.camera.distance = self.profile.settings["camera_distance"]
        self.keyboard = KeyboardMouse(app, self.profile.settings)
        self.gamepad = Gamepad(app)
        self.spectate_id = None
        self.banner = None  # (text, sub, color, time_left)
        self.events_log = []
        self.reward_summary = None
        self.finished = False
        self._fell_shown = set()
        self.titles = {p.id: p.title for p in self.participants}
        self.sun = app.sun

    def start(self):
        self.app.screens.reset_to("hud", session=self)
        self.keyboard.capture_mouse(True)
        self.app.sounds.play_music("music_race")
        self.gm.start()

    # ------------------------------------------------------------------ round visuals
    def _build_round(self):
        if self.course_view is not None:
            self.course_view.destroy()
        for v in self.views.values():
            v.destroy()
        self.views.clear()
        self.effects.clear()
        rnd = self.gm.round
        self.course_view = CourseView(self.app, rnd.map, rnd.world)
        catalog = self.profile.catalog
        font = self.app.theme.font("bold")
        for ch in rnd.characters:
            part = self.gm.participants[ch.id]
            v = CharacterView(self.app.loader, catalog.get(part.skin_id), self.app.render, part.name,
                              is_local=(ch.id == self.LOCAL), title=part.title, font=font)
            self.views[ch.id] = v
        me = rnd.by_id(self.LOCAL)
        target = me if me is not None else rnd.characters[0]
        self.camera.world = rnd.world
        self.camera.snap(target.x, target.y, target.z, yaw=0.0)
        self._fell_shown.clear()

    # ------------------------------------------------------------------ events from the game
    def _on_game_event(self, kind, data):
        if kind == "state":
            self._on_state(data)
        elif kind == "round_events":
            for ev in data:
                self._on_round_event(*ev)
        elif kind == "results":
            self.app.screens.get("hud").show_round_results(self.gm.history[-1])
        elif kind == "local_report":
            pass

    def _on_state(self, st):
        gm = self.gm
        hud = self.app.screens.get("hud")
        if st == GameState.COUNTDOWN:
            self._build_round()
            rnd = gm.round
            sub = ("FINAL ROUND - first to the finish wins!" if rnd.is_final else
                   "Top %d of %d qualify" % (rnd.qualify_count, len(rnd.characters)))
            hud.round_intro(gm.round_index + 1, gm.total_rounds, rnd.map, sub)
        elif st == GameState.ROUND_START:
            hud.flash("GO!", "", "secondary", 1.0, big=True)
            self.app.sounds.play("go")
        elif st == GameState.ROUND_END:
            res = gm.round.result_for(self.LOCAL)
            if res is None:
                hud.flash("ROUND OVER", "", "muted", 3.0)
            elif res.outcome == Outcome.WINNER:
                hud.flash("YOU WIN!", "Champion of the show", "secondary", 3.0, big=True)
                self.app.sounds.play("victory")
            elif res.outcome == Outcome.QUALIFIED:
                hud.flash("QUALIFIED!", "On to the next round", "success", 3.0, big=True)
                self.app.sounds.play("finish")
            else:
                hud.flash("ELIMINATED", "Better luck next time", "danger", 3.0, big=True)
                self.app.sounds.play("eliminated")
        elif st == GameState.GAME_OVER:
            self._finish()

    def _on_round_event(self, kind, cid, data):
        rnd = self.gm.round
        ch = rnd.by_id(cid)
        if ch is None:
            return
        local = cid == self.LOCAL
        near = self._near_camera(ch)
        snd = self.app.sounds
        fx = self.effects
        if kind == "jump" and (local or near):
            snd.play("jump", 1.0 if local else 0.35)
        elif kind == "land" and data and data > 6.0:
            fx.dust(ch.x, ch.y, ch.z, 6)
            if local:
                snd.play("land", 0.8)
        elif kind == "bonk":
            fx.popup(ch.x, ch.y, ch.z + 1.8, "BONK!", "#ffd23f")
            fx.stars(ch.x, ch.y, ch.z + 1.4)
            if local or near:
                snd.play("bonk", 1.0 if local else 0.5)
        elif kind == "hit":
            fx.stars(ch.x, ch.y, ch.z + 1.0, 12)
            if local:
                self.camera.add_shake(0.5)
                snd.play("hit")
            elif near:
                snd.play("hit", 0.35)
        elif kind == "bounce" and (local or near):
            snd.play("bounce", 1.0 if local else 0.4)
        elif kind == "fall":
            fx.splash(ch.x, ch.y, self.course_view.void_z + 0.2, self.course_view.map.theme.get("void", "#ff6fb5"))
            if local:
                snd.play("splash")
                self.app.screens.get("hud").flash("OOPS!", "Respawning..." if rnd.world.fall_rule == "respawn"
                                                  else "", "danger", 1.2)
        elif kind == "checkpoint" and local:
            snd.play("checkpoint")
            self.app.screens.get("hud").toast("Checkpoint %d" % data)
        elif kind == "finish":
            fx.confetti(ch.x, ch.y, ch.z + 1.0, 50 if local else 15)
            if local:
                snd.play("finish")
                self.app.screens.get("hud").flash("FINISHED! #%d" % data, "", "success", 2.5, big=True)
            self.app.screens.get("hud").feed("%s finished #%d" % (ch.name, data), "success")
        elif kind == "eliminated":
            self.app.screens.get("hud").feed("%s was eliminated" % ch.name, "danger")
            if local:
                self.app.screens.get("hud").flash("ELIMINATED", "You fell off the course", "danger", 2.5, big=True)
                snd.play("eliminated")
        elif kind == "obstacle_cleared" and local:
            pass

    def _near_camera(self, ch, dist=14.0):
        cam = self.app.camera.getPos()
        return (cam.x - ch.x) ** 2 + (cam.y - ch.y) ** 2 < dist * dist

    # ------------------------------------------------------------------ per frame
    @property
    def local_char(self):
        rnd = self.gm.round
        return rnd.by_id(self.LOCAL) if rnd else None

    def focus_char(self):
        rnd = self.gm.round
        if rnd is None:
            return None
        me = rnd.by_id(self.LOCAL)
        if me is not None and not self.gm.local_out and not (me.eliminated and me.elim_reason == "fell"):
            return me
        # Spectating: follow the chosen player, default to the leader.
        alive = [c for c in rnd.standings() if not c.eliminated]
        if self.spectate_id is None or rnd.by_id(self.spectate_id) is None \
                or rnd.by_id(self.spectate_id).eliminated:
            self.spectate_id = alive[0].id if alive else rnd.characters[0].id
        return rnd.by_id(self.spectate_id)

    def cycle_spectate(self, step):
        rnd = self.gm.round
        if rnd is None:
            return
        alive = [c for c in rnd.standings() if not c.eliminated]
        if not alive:
            return
        ids = [c.id for c in alive]
        idx = ids.index(self.spectate_id) if self.spectate_id in ids else 0
        self.spectate_id = ids[(idx + step) % len(ids)]

    def set_paused(self, flag):
        self.paused = flag
        self.keyboard.capture_mouse(not flag)

    def update(self, dt):
        gm = self.gm
        if self.finished:
            return
        frame = self.keyboard.poll(dt) if not self.paused else None
        pad = self.gamepad.poll(dt) if not self.paused else None
        if pad is not None and (abs(pad.forward) + abs(pad.strafe) > 0 or pad.jump or pad.look_x or pad.look_y):
            frame = pad
        if frame is not None:
            self.camera.rotate(frame.look_x, frame.look_y)
            self.human.cmd = frame_to_command(frame, self.camera)
        else:
            self.human.cmd = IDLE_COMMAND
        if not self.paused:
            gm.update(dt)
        rnd = gm.round
        if rnd is None or self.course_view is None:
            return
        alpha = gm.interp_alpha if not self.paused else 1.0
        for ch in rnd.characters:
            v = self.views.get(ch.id)
            if v is not None:
                v.sync(ch, alpha, 0.0 if self.paused else dt)
                part = self.gm.participants[ch.id]
                skin = self.profile.catalog.get(part.skin_id)
                if skin.effect and ch.speed > 3.0 and v.visible and not self.paused and \
                        self.effects.rng.random() < dt * 14:
                    self.effects.trail(ch.x, ch.y, ch.z, skin.effect)
        t_vis = rnd.t - 2 * 1 / 60.0 + alpha / 60.0
        self.course_view.update(max(0.0, t_vis), dt, self.app.camera.getPos())
        focus = self.focus_char()
        if focus is not None:
            v = self.views.get(focus.id)
            pos = v.root.getPos() if v is not None else (focus.x, focus.y, focus.z)
            self.camera.update(pos[0], pos[1], pos[2], focus.grounded, dt)
            # Shadow camera follows the action.
            self.sun.setPos(pos[0] + 10, pos[1] - 6, pos[2] + 25)
            self.sun.lookAt(pos[0], pos[1], pos[2])
        for cid, v in self.views.items():
            v.show_tag(cid != (focus.id if focus else None) or self.gm.local_out)
        if not self.paused:
            self.effects.update(dt)

    # ------------------------------------------------------------------ ending
    def leave(self):
        """Quit from the pause menu or after being eliminated."""
        if self.gm.state != GameState.GAME_OVER:
            self.gm.abort()
        if not self.finished:
            self._finish()

    def _finish(self):
        if self.finished:
            return
        self.finished = True
        self.keyboard.capture_mouse(False)
        report = self.gm.local_report
        summary = None
        if report is not None:
            summary = self.profile.apply_match_report(report, self.gm.total_rounds)
        self.reward_summary = summary
        champion = self.gm.champion_id
        champ_name = self.gm.participants[champion].name if champion else None
        won = bool(report and report.won)
        self.app.end_session(self, report, summary, champ_name, won)

    def destroy(self):
        if self.course_view is not None:
            self.course_view.destroy()
        for v in self.views.values():
            v.destroy()
        self.views.clear()
        self.effects.destroy()

