"""The show: a sequence of rounds with eliminations, driven by a state machine.

The manager is engine-independent: the Panda3D client, the headless test
harness and the multiplayer server all drive it by calling ``update(dt)``.
"""

import logging
import math
import random

from ..sim import constants as C
from ..sim.character import Character
from .game_state import GameState, Outcome
from .match_report import MatchReport
from .round_manager import RoundSimulation

log = logging.getLogger(__name__)

# Fraction of players that advance from each non-final round, by remaining rounds.
QUALIFY_RATIOS = {2: 0.65, 1: 0.5}


def qualify_count_for(alive, rounds_left_after):
    if alive <= 1:
        return 1
    ratio = QUALIFY_RATIOS.get(rounds_left_after, 0.6)
    return max(1, min(alive - 1, int(math.ceil(alive * ratio))))


class Participant:
    def __init__(self, pid, name, skin_id="classic", is_bot=False, difficulty=None, title=None):
        self.id = pid
        self.name = name
        self.skin_id = skin_id
        self.is_bot = is_bot
        self.difficulty = difficulty
        self.title = title


class GameSettings:
    def __init__(self, countdown=3.0, round_start=0.9, round_end=3.0, results_auto=None,
                 max_frame_steps=8):
        self.countdown = countdown
        self.round_start = round_start  # "GO!" banner time while racing already
        self.round_end = round_end
        self.results_auto = results_auto  # seconds before RESULTS advances by itself (None = wait)
        self.max_frame_steps = max_frame_steps  # avoids a death spiral after a long frame


class GameManager:
    """Runs one show.

    controller_factory(participant, character, round_sim) -> controller, called at the
    start of every round (bots get a fresh brain for every course).
    """

    def __init__(self, maps, participants, controller_factory, settings=None, seed=None,
                 local_player_id=None, mode="ai_showdown"):
        if not maps:
            raise ValueError("a show needs at least one map")
        if not participants:
            raise ValueError("a show needs at least one participant")
        self.maps = list(maps)
        self.participants = {p.id: p for p in participants}
        self.order = [p.id for p in participants]
        self.controller_factory = controller_factory
        self.settings = settings or GameSettings()
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.local_player_id = local_player_id
        self.mode = mode
        self.state = GameState.LOBBY
        self.state_time = 0.0
        self.round_index = -1
        self.round = None  # RoundSimulation
        self.characters = {}
        self.alive_ids = list(self.order)
        self.history = []  # list of (map_id, [RoundResultEntry])
        self.final_standings = []  # list of (place, participant_id)
        self.listeners = []
        self._accum = 0.0
        self.local_report = None
        self.local_out = False  # local player has been eliminated (spectating)
        for p in participants:
            self.characters[p.id] = Character(p.id, p.name, p.skin_id, p.is_bot)

    # ---------------------------------------------------------------- events
    def add_listener(self, fn):
        """fn(kind, data) for 'state', 'round_events', 'results', 'game_over'."""
        self.listeners.append(fn)

    def _emit(self, kind, data=None):
        for fn in list(self.listeners):
            try:
                fn(kind, data)
            except Exception:  # a broken UI callback must not freeze the game loop
                log.exception("game listener failed for %s", kind)

    def _set_state(self, new):
        if new not in GameState.TRANSITIONS[self.state]:
            raise RuntimeError("illegal game state change %s -> %s" % (self.state, new))
        self.state = new
        self.state_time = 0.0
        self._emit("state", new)

    # ---------------------------------------------------------------- flow
    @property
    def total_rounds(self):
        return len(self.maps)

    @property
    def current_map(self):
        return self.maps[self.round_index] if 0 <= self.round_index < len(self.maps) else None

    @property
    def is_final_round(self):
        return self.round_index == len(self.maps) - 1 or len(self.alive_ids) <= 2

    def start(self):
        if self.state != GameState.LOBBY:
            raise RuntimeError("show already started")
        self._begin_round(0)

    def _begin_round(self, index):
        self.round_index = index
        loaded = self.maps[index]
        alive = len(self.alive_ids)
        rounds_left_after = len(self.maps) - index - 1
        final = rounds_left_after == 0 or alive <= 2
        if final and index < len(self.maps) - 1:
            # Too few players left for the remaining rounds: jump to the final course.
            self.round_index = index = len(self.maps) - 1
            loaded = self.maps[index]
        quota = 1 if final else qualify_count_for(alive, rounds_left_after)
        chars = [self.characters[pid] for pid in self.alive_ids]
        self.round = RoundSimulation(loaded, chars, {}, quota, final, seed=self.seed * 31 + index)
        for ch in chars:
            ctrl = self.controller_factory(self.participants[ch.id], ch, self.round)
            if ctrl is not None:
                self.round.controllers[ch.id] = ctrl
        for ch in self.characters.values():
            if ch.id not in self.alive_ids:
                ch.active = False
        self._accum = 0.0
        self._set_state(GameState.COUNTDOWN)

    def continue_after_results(self):
        """Called by the UI ('Continue') or automatically after results_auto seconds."""
        if self.state != GameState.RESULTS:
            return
        if self._show_finished():
            self._finish_show()
        else:
            self._begin_round(self.round_index + 1)

    def _show_finished(self):
        return self.round is not None and self.round.is_final

    def abort(self, reason="quit"):
        """Leave the show early (pause menu -> quit).  Produces a report for the local player."""
        if self.state in (GameState.GAME_OVER, GameState.LOBBY):
            return
        if self.local_player_id and not self.local_out:
            # Leaving while still in the show counts as a quit.
            if self.round is not None:
                self.round.remove_participant(self.local_player_id, "left")
            self._build_local_report(quit_early=True)
        # Already eliminated: the report from the elimination stays as it is.
        self.state = GameState.GAME_OVER
        self._emit("state", GameState.GAME_OVER)

    def remove_participant(self, pid, reason="left"):
        """Disconnect / leave: out of the current round and the rest of the show."""
        if pid in self.alive_ids:
            self.alive_ids.remove(pid)
        if self.round is not None and self.state in (GameState.COUNTDOWN, GameState.ROUND_START,
                                                     GameState.ROUND_ACTIVE):
            self.round.remove_participant(pid, reason)
        elif self.round is not None:
            self.round.controllers.pop(pid, None)

    # ---------------------------------------------------------------- update
    def update(self, dt):
        """Advance real time by dt seconds (any frame rate; simulation is fixed-step)."""
        if self.state in (GameState.LOBBY, GameState.GAME_OVER):
            return
        self.state_time += dt
        st = self.state
        if st in (GameState.COUNTDOWN, GameState.ROUND_START, GameState.ROUND_ACTIVE,
                  GameState.ROUND_END):
            self._run_sim(dt)
        if st == GameState.COUNTDOWN and self.state_time >= self.settings.countdown:
            self.round.start_race()
            self._set_state(GameState.ROUND_START)
        elif st == GameState.ROUND_START:
            if self.round.over:
                self._on_round_over()
            elif self.state_time >= self.settings.round_start:
                self._set_state(GameState.ROUND_ACTIVE)
        elif st == GameState.ROUND_ACTIVE and self.round.over:
            self._on_round_over()
        elif st == GameState.ROUND_END and self.state_time >= self.settings.round_end:
            self._set_state(GameState.RESULTS)
            self._emit("results", self.history[-1])
        elif st == GameState.RESULTS and self.settings.results_auto is not None \
                and self.state_time >= self.settings.results_auto:
            self.continue_after_results()

    def _run_sim(self, dt):
        self._accum += dt
        steps = 0
        while self._accum >= C.DT and steps < self.settings.max_frame_steps:
            self.round.tick(C.DT)
            self._accum -= C.DT
            steps += 1
            if self.round.events:
                self._emit("round_events", list(self.round.events))
            if self.round.over and self.state in (GameState.ROUND_ACTIVE, GameState.ROUND_START):
                break
        if steps == self.settings.max_frame_steps:
            self._accum = 0.0

    @property
    def interp_alpha(self):
        return min(1.0, self._accum / C.DT)

    def _on_round_over(self):
        rnd = self.round
        self.history.append((rnd.map.id, rnd.results))
        qualified = [r.id for r in rnd.results if r.outcome in (Outcome.QUALIFIED, Outcome.WINNER)]
        eliminated = [r for r in rnd.results if r.outcome == Outcome.ELIMINATED]
        # Final placement of the players knocked out this round.
        base = len(qualified)
        for i, r in enumerate(eliminated):
            self.final_standings.append((base + i + 1, r.id))
        self.alive_ids = [pid for pid in self.alive_ids if pid in qualified]
        if rnd.is_final:
            for r in rnd.results:
                if r.outcome == Outcome.WINNER:
                    self.final_standings.append((1, r.id))
        lp = self.local_player_id
        if lp is not None and not self.local_out and lp not in qualified:
            self.local_out = True
            self._build_local_report()
        elif lp is not None and rnd.is_final and lp in qualified:
            self._build_local_report()
        self._set_state(GameState.ROUND_END)

    def _finish_show(self):
        self.final_standings.sort()
        if self.local_player_id is not None and self.local_report is None:
            self._build_local_report()
        self._set_state(GameState.GAME_OVER)
        self._emit("game_over", self.final_standings)

    @property
    def champion_id(self):
        for place, pid in self.final_standings:
            if place == 1:
                return pid
        return None

    def placement_of(self, pid):
        for place, p in self.final_standings:
            if p == pid:
                return place
        return None

    # ---------------------------------------------------------------- reports
    def _build_local_report(self, quit_early=False):
        pid = self.local_player_id
        if pid is None:
            return
        ch = self.characters[pid]
        rounds = []
        for map_id, results in self.history:
            for r in results:
                if r.id == pid:
                    rounds.append({"map_id": map_id, "outcome": r.outcome, "time": r.time,
                                   "place": r.place, "reason": r.reason})
        won = any(r["outcome"] == Outcome.WINNER for r in rounds)
        placement = self.placement_of(pid)
        if placement is None:
            placement = len(self.alive_ids) + 1 if quit_early else (1 if won else None)
        self.local_report = MatchReport(
            mode=self.mode,
            player_count=len(self.order),
            rounds=rounds,
            won=won,
            placement=placement,
            quit_early=quit_early,
            jumps=ch.stat_jumps,
            obstacles_cleared=ch.stat_obstacles,
            falls=ch.stat_falls,
            hits=ch.stat_hits,
            bonks=ch.stat_bonks,
            difficulty=self.participants[pid].difficulty,
        )
        self._emit("local_report", self.local_report)
