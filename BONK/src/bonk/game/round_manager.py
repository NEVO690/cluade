"""One round on one course: runs the fixed-tick simulation and enforces the rules."""

import random

from ..sim import constants as C
from ..sim.character import IDLE_COMMAND, MoveState
from ..sim.physics import resolve_character_pairs, step_character
from .game_state import Outcome


class RoundResultEntry:
    def __init__(self, ch, outcome, place, reason):
        self.id = ch.id
        self.name = ch.name
        self.is_bot = ch.is_bot
        self.outcome = outcome
        self.place = place  # 1-based position within this round
        self.reason = reason  # finished / fell / timeout / best_progress / last_standing / left
        self.time = ch.finish_time
        self.progress = round(ch.best_progress, 1)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "bot": self.is_bot, "outcome": self.outcome,
                "place": self.place, "reason": self.reason, "time": self.time,
                "progress": self.progress}


class RoundSimulation:
    """Owns a fresh CourseWorld and the characters taking part in this round.

    Controllers are objects with ``command(character, round_sim) -> InputCommand``.
    """

    def __init__(self, loaded_map, characters, controllers, qualify_count, is_final, seed=0):
        self.map = loaded_map
        self.world = loaded_map.build_world()
        self.characters = list(characters)
        self.controllers = controllers
        self.qualify_count = max(1, int(qualify_count))
        self.is_final = is_final
        self.rng = random.Random(seed)
        self.seed = seed
        self.t = 0.0  # course clock (obstacles move from the very first tick)
        self.race_time = 0.0  # starts at GO
        self.controls_enabled = False
        self.over = False
        self.end_reason = None
        self.results = []
        self.finish_order = []
        self.events = []  # (kind, character_id, data) produced this tick
        self.tick_count = 0
        self._seg_hint = {}
        self._place_at_start()

    # ------------------------------------------------------------------ setup
    def _place_at_start(self):
        order = list(self.characters)
        self.rng.shuffle(order)
        spawns = self.map.spawn_points(len(order))
        for i, ch in enumerate(order):
            ch.reset_for_round()
            ch.slot = i
            x, y, z = spawns[i]
            ch.place_at(x, y, z + 0.01, 0.0)
            ch.grounded = True
            _, ch.ground = self.world.ground_probe(x, y, z + 0.5, 2.0)
            self._seg_hint[ch.id] = 0

    def controller_for(self, ch):
        return self.controllers.get(ch.id)

    # ------------------------------------------------------------------ queries
    @property
    def alive(self):
        return [c for c in self.characters if c.alive]

    def by_id(self, cid):
        for c in self.characters:
            if c.id == cid:
                return c
        return None

    def standings(self):
        """Live order: finishers first, then the furthest along; eliminated last."""
        def key(c):
            if c.finished:
                return (0, c.finish_place, 0.0)
            if c.eliminated:
                return (2, -(c.eliminated_at or 0.0), -c.best_progress)
            return (1, 0, -c.progress)
        return sorted(self.characters, key=key)

    @property
    def time_left(self):
        return max(0.0, self.world.time_limit - self.race_time)

    # ------------------------------------------------------------------ simulation
    def start_race(self):
        self.controls_enabled = True

    def tick(self, dt=C.DT):
        self.events.clear()
        world = self.world
        world.update(self.t, dt)
        for ch in self.characters:
            ch.events.clear()
        for ch in self.characters:
            if not ch.active or ch.eliminated:
                continue
            if ch.respawn_timer > 0.0:
                ch.respawn_timer -= dt
                if ch.respawn_timer <= 0.0:
                    self._respawn(ch)
                continue
            if self.controls_enabled and not ch.finished and not self.over:
                ctrl = self.controllers.get(ch.id)
                cmd = ctrl.command(ch, self) if ctrl is not None else IDLE_COMMAND
            else:
                cmd = IDLE_COMMAND
            step_character(ch, cmd, world, self.t, dt)
        resolve_character_pairs(self.characters)
        if not self.over:
            for ch in self.characters:
                if ch.active and not ch.eliminated and ch.respawn_timer <= 0.0:
                    self._apply_rules(ch)
        for ch in self.characters:
            for kind, data in ch.events:
                self.events.append((kind, ch.id, data))
        self.t += dt
        self.tick_count += 1
        if self.controls_enabled and not self.over:
            self.race_time += dt
            self._check_end()

    # ------------------------------------------------------------------ rules
    def _apply_rules(self, ch):
        w = self.world
        if w.out_of_bounds(ch.x, ch.y, ch.z):
            self._on_fall(ch)
            return
        # Progress along the course (alternative routes share the same distance scale).
        s, seg, _, cost = w.route.project(ch.x, ch.y, ch.z, self._seg_hint.get(ch.id, 0), 4)
        self._seg_hint[ch.id] = seg
        for alt in getattr(w, "alt_routes", ()):
            s2, _, _, cost2 = alt.project(ch.x, ch.y, ch.z)
            if cost2 < cost:
                s, cost = s2, cost2
        ch.progress = s
        ch.best_progress = max(ch.best_progress, s)
        if ch.finished:
            return
        if ch.grounded:
            cp = w.checkpoint_at(ch.x, ch.y, ch.z)
            if cp is not None and cp.index > ch.checkpoint:
                ch.checkpoint = cp.index
                ch.events.append(("checkpoint", cp.index))
        elif w.obstacle_zones:
            for z in w.obstacle_zones:
                if z.id not in ch._zones_cleared and z.contains(ch.x, ch.y, ch.z):
                    ch._zones_cleared.add(z.id)
                    ch.stat_obstacles += 1
                    ch.events.append(("obstacle_cleared", z.data.get("kind")))
        if self.controls_enabled and w.finish.contains(ch.x, ch.y, ch.z):
            self._on_finish(ch)

    def _on_fall(self, ch):
        ch.stat_falls += 1
        ch.events.append(("fall", None))
        if self.world.fall_rule == "eliminate":
            self._eliminate(ch, "fell")
        else:
            ch.respawn_timer = C.RESPAWN_DELAY
            ch.vx = ch.vy = ch.vz = 0.0
            ch.state = MoveState.RESPAWNING

    def _respawn(self, ch):
        cp = self.world.checkpoints[min(ch.checkpoint, len(self.world.checkpoints) - 1)]
        # Pick the free spawn spot closest to the course centre.
        spots = cp.spawns
        best = None
        for k in range(len(spots)):
            x, y, z = spots[(ch.slot + k) % len(spots)]
            if all((o.x - x) ** 2 + (o.y - y) ** 2 > 1.0 for o in self.characters
                   if o is not ch and o.active and not o.eliminated):
                best = (x, y, z)
                break
        x, y, z = best or spots[ch.slot % len(spots)]
        ch.place_at(x, y, z + 0.05, cp.yaw)
        ch.respawn_timer = 0.0
        ch.start_respawn_grace()
        ch.state = MoveState.IDLE
        ch.events.append(("respawn", cp.index))

    def _on_finish(self, ch):
        ch.finished = True
        ch.finish_time = round(self.race_time, 2)
        self.finish_order.append(ch)
        ch.finish_place = len(self.finish_order)
        ch.vx *= 0.3
        ch.vy *= 0.3
        ch.state = MoveState.VICTORY
        ch.events.append(("finish", ch.finish_place))

    def _eliminate(self, ch, reason):
        ch.eliminated = True
        ch.eliminated_at = self.race_time
        ch.elim_reason = reason
        ch.state = MoveState.ELIMINATED
        ch.vx = ch.vy = 0.0
        ch.events.append(("eliminated", reason))

    def remove_participant(self, cid, reason="left"):
        """A player disconnected or quit: they are out of this round immediately."""
        ch = self.by_id(cid)
        if ch is None or ch.eliminated or ch.finished:
            return
        self._eliminate(ch, reason)
        self.controllers.pop(cid, None)
        if not self.over:
            self._check_end()

    def _check_end(self):
        running = [c for c in self.characters if c.active and not c.finished and not c.eliminated]
        if self.is_final and self.finish_order:
            self._close("winner")
        elif len(self.finish_order) >= self.qualify_count:
            self._close("quota")
        elif not running:
            self._close("all_out")
        elif self.race_time >= self.world.time_limit:
            self._close("time")

    def force_end(self, reason="aborted"):
        if not self.over:
            self._close(reason)

    # ------------------------------------------------------------------ results
    def _close(self, reason):
        self.over = True
        self.end_reason = reason
        finishers = list(self.finish_order)
        others = [c for c in self.characters if not c.finished]
        survivors = sorted([c for c in others if not c.eliminated],
                           key=lambda c: -c.best_progress)
        fallen = sorted([c for c in others if c.eliminated],
                        key=lambda c: (-(c.eliminated_at or 0.0), -c.best_progress))
        results = []
        qualified_ids = set()
        if self.is_final:
            if finishers:
                winner, why = finishers[0], "finished"
            elif survivors:
                winner, why = survivors[0], "best_progress"
            else:
                left_ok = [c for c in fallen if c.elim_reason != "left"]
                winner, why = (left_ok or fallen)[0], "last_standing"
            qualified_ids.add(winner.id)
            results.append(RoundResultEntry(winner, Outcome.WINNER, 1, why))
        else:
            qualified = finishers[: self.qualify_count]
            if not qualified:
                # Nobody reached the line: the furthest survivors advance so the show
                # can never end up with zero players.
                pool = survivors or [c for c in fallen if c.elim_reason != "left"] or fallen
                qualified = pool[: max(1, min(self.qualify_count, len(pool)))]
            for i, c in enumerate(qualified):
                qualified_ids.add(c.id)
                results.append(RoundResultEntry(c, Outcome.QUALIFIED, i + 1,
                                                "finished" if c.finished else "best_progress"))
        rest = [c for c in finishers + survivors + fallen if c.id not in qualified_ids]
        for c in rest:
            if not c.eliminated:
                c.eliminated = True
                c.eliminated_at = self.race_time
                c.elim_reason = "timeout" if not c.finished else "late"
            reason_txt = c.elim_reason or "timeout"
            results.append(RoundResultEntry(c, Outcome.ELIMINATED, len(results) + 1, reason_txt))
        for c in self.characters:
            if c.id in qualified_ids:
                c.celebrate = True
                c.state = MoveState.VICTORY
            elif c.respawn_timer <= 0.0:
                c.state = MoveState.ELIMINATED
        self.results = results

    def result_for(self, cid):
        for r in self.results:
            if r.id == cid:
                return r
        return None
