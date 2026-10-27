import json
import math
import os
import random
import tempfile
import unittest

import helpers  # noqa: F401

from bonk.ai import make_bot
from bonk.game.game_manager import GameManager, GameSettings, Participant, qualify_count_for
from bonk.game.game_state import GameState, Outcome
from bonk.game.round_manager import RoundSimulation
from bonk.maps.map_loader import LoadedMap, MapFormatError
from bonk.maps.map_manager import MapManager
from bonk.sim import constants as C
from bonk.sim.character import Character, InputCommand, MoveState
from bonk.sim.obstacles import MovingPlatform, PendulumHammer, Solid, VanishingTile
from bonk.sim.physics import resolve_character_pairs, step_character
from bonk.sim.route import Route, Waypoint
from bonk.sim.world import CourseWorld

MM = MapManager()


def flat_world(extra=()):
    w = CourseWorld("test", "test")
    w.add_solid(Solid("floor", (0, 0, -0.5), (40, 40, 1)))
    for s in extra:
        if isinstance(s, PendulumHammer):
            w.add_hazard(s)
        else:
            w.add_solid(s)
    w.route = Route([Waypoint(0, -10, 0), Waypoint(0, 10, 0)])
    return w


def run(ch, w, cmd, seconds, t0=0.0):
    t = t0
    for _ in range(int(seconds * C.TICK_RATE)):
        w.update(t, C.DT)
        step_character(ch, cmd, w, t, C.DT)
        t += C.DT
    return t


def grounded_char(w, x=0.0, y=0.0):
    ch = Character("c", "c")
    ch.place_at(x, y, 0.0)
    run(ch, w, InputCommand(), 0.1)
    return ch


class MovementTests(unittest.TestCase):
    def test_stands_on_ground(self):
        w = flat_world()
        ch = grounded_char(w)
        self.assertTrue(ch.grounded)
        self.assertAlmostEqual(ch.z, 0.0, places=4)
        self.assertEqual(ch.state, MoveState.IDLE)

    def test_runs_forward_and_walks_slower(self):
        w = flat_world()
        ch = grounded_char(w)
        run(ch, w, InputCommand(0, 1), 1.0)
        self.assertGreater(ch.y, 5.5)
        self.assertEqual(ch.state, MoveState.RUN)
        ch2 = grounded_char(w)
        run(ch2, w, InputCommand(0, 1, walk=True), 1.0)
        self.assertLess(ch2.y, 3.3)
        self.assertEqual(ch2.state, MoveState.WALK)

    def test_strafe_and_backwards(self):
        w = flat_world()
        ch = grounded_char(w)
        run(ch, w, InputCommand(1, 0), 0.5)
        self.assertGreater(ch.x, 2.0)
        run(ch, w, InputCommand(0, -1), 0.5)
        self.assertLess(ch.y, -2.0)

    def test_jump_changes_height_and_lands(self):
        w = flat_world()
        ch = grounded_char(w)
        max_z = 0.0
        t = 0.0
        states = set()
        for i in range(90):
            cmd = InputCommand(jump=(i == 0))
            w.update(t, C.DT)
            step_character(ch, cmd, w, t, C.DT)
            max_z = max(max_z, ch.z)
            states.add(ch.state)
            t += C.DT
        self.assertAlmostEqual(max_z, C.MAX_JUMP_HEIGHT, delta=0.15)
        self.assertTrue(ch.grounded)
        self.assertIn(MoveState.JUMP, states)
        self.assertIn(MoveState.FALL, states)
        self.assertEqual(ch.stat_jumps, 1)

    def test_no_double_jump_and_holding_does_not_repeat(self):
        w = flat_world()
        ch = grounded_char(w)
        t = 0.0
        for i in range(120):  # jump held for 2 seconds, plus extra presses in the air
            cmd = InputCommand(jump=True if i < 60 else (i % 4 == 0))
            w.update(t, C.DT)
            step_character(ch, cmd, w, t, C.DT)
            t += C.DT
        # Held key: one jump.  Presses in the air: ignored until landing (buffer may add one after).
        self.assertLessEqual(ch.stat_jumps, 3)
        ch2 = grounded_char(w)
        run(ch2, w, InputCommand(jump=True), 2.0)
        self.assertEqual(ch2.stat_jumps, 1)

    def test_jump_state_never_on_ground(self):
        w = flat_world()
        ch = grounded_char(w)
        t = 0.0
        for i in range(200):
            w.update(t, C.DT)
            step_character(ch, InputCommand(0, 1, jump=(i % 30 == 0)), w, t, C.DT)
            if ch.grounded:
                self.assertNotEqual(ch.state, MoveState.JUMP)
            t += C.DT

    def test_wall_blocks_and_hurdle_needs_jump(self):
        w = flat_world([Solid("wall", (0, 3, 0.5), (10, 0.6, 1.0))])
        ch = grounded_char(w)
        run(ch, w, InputCommand(0, 1), 2.0)
        self.assertLess(ch.y, 3 - 0.3 - C.CHAR_RADIUS + 0.02)
        # jump over the 1 m wall
        ch2 = grounded_char(w)
        t = 0.0
        for i in range(120):
            w.update(t, C.DT)
            step_character(ch2, InputCommand(0, 1, jump=(ch2.y > 1.2 and ch2.grounded)), w, t, C.DT)
            t += C.DT
        self.assertGreater(ch2.y, 4.0)

    def test_small_step_is_climbed(self):
        w = flat_world([Solid("step", (0, 6, 0.1), (10, 8, 0.2))])  # y 2..10
        ch = grounded_char(w)
        run(ch, w, InputCommand(0, 1), 0.7)
        self.assertGreater(ch.y, 3)
        self.assertAlmostEqual(ch.z, 0.2, places=3)

    def test_falls_off_edge(self):
        w = CourseWorld("t", "t")
        w.add_solid(Solid("plat", (0, 0, -0.5), (4, 4, 1)))
        ch = grounded_char(w)
        run(ch, w, InputCommand(0, 1), 1.5)
        self.assertFalse(ch.grounded)
        self.assertLess(ch.z, -3)

    def test_moving_platform_carries(self):
        mp = MovingPlatform("mp", (0, 0, -0.3), (4, 4, 0.6), (6, 0, 0), period=4.0)
        w = CourseWorld("t", "t")
        w.add_solid(mp)
        w.update(0, 0)
        ch = Character("c", "c")
        ch.place_at(0, 0, 0.0)
        run(ch, w, InputCommand(), 2.0)
        self.assertTrue(ch.grounded)
        self.assertAlmostEqual(ch.x, mp.cx, delta=0.05)
        self.assertGreater(ch.x, 5.0)

    def test_vanishing_tile(self):
        tile = VanishingTile("tile", (0, 0, -0.25), (2, 2, 0.5), warn_time=0.5, gone_time=2.0)
        w = CourseWorld("t", "t")
        w.add_solid(tile)
        ch = Character("c", "c")
        ch.place_at(0, 0, 0.0)
        t = run(ch, w, InputCommand(), 0.3)
        self.assertEqual(tile.state, VanishingTile.WARNING)
        self.assertTrue(ch.grounded)
        t = run(ch, w, InputCommand(), 0.5, t)
        self.assertEqual(tile.state, VanishingTile.GONE)
        self.assertFalse(ch.grounded)
        run(ch, w, InputCommand(), 2.5, t)
        self.assertEqual(tile.state, VanishingTile.SOLID)  # comes back

    def test_hammer_knocks_back_and_stuns(self):
        ham = PendulumHammer("h", (0, 2, 6.8), 5.6, 0.0, 3.0)  # hanging still, head at (0, 2, 1.2)
        w = flat_world([ham])
        ch = grounded_char(w)
        run(ch, w, InputCommand(0, 1), 0.6)
        self.assertGreaterEqual(ch.stat_hits, 1)
        self.assertLess(ch.y, 2.0)

    def test_characters_push_apart_and_head_bonk(self):
        a, b = Character("a", "a"), Character("b", "b")
        a.place_at(0, 0, 0)
        b.place_at(0.3, 0, 0)
        resolve_character_pairs([a, b])
        self.assertGreaterEqual(math.hypot(a.x - b.x, a.y - b.y), 0.3)
        top, bottom = Character("t", "t"), Character("u", "u")
        bottom.place_at(0, 0, 0)
        top.place_at(0.1, 0, 1.3)
        top.vz = -3
        resolve_character_pairs([top, bottom])
        self.assertEqual(top.stat_bonks, 1)
        self.assertGreater(top.vz, 0)

    def test_network_input_is_sanitized(self):
        cmd = InputCommand(float("nan"), 50.0, 1, 0).sanitized()
        self.assertEqual(cmd.move_x, 0.0)
        self.assertLessEqual(math.hypot(cmd.move_x, cmd.move_y), 1.0 + 1e-9)


class RoundRuleTests(unittest.TestCase):
    def make_round(self, map_id, n, quota, final=False, controllers=None):
        chars = [Character("c%d" % i, "C%d" % i) for i in range(n)]
        rnd = RoundSimulation(MM.get(map_id), chars, controllers or {}, quota, final, seed=1)
        return rnd, chars

    def test_spawn_on_ground(self):
        for m in MM.ids():
            rnd, chars = self.make_round(m, 16, 8)
            for _ in range(30):
                rnd.tick()
            for c in chars:
                self.assertTrue(c.grounded, "%s spawned in the air on %s" % (c.id, m))

    def test_no_movement_before_go(self):
        rnd, chars = self.make_round("starter_run", 2, 1)
        y0 = chars[0].y
        for _ in range(60):
            rnd.tick()
        self.assertAlmostEqual(chars[0].y, y0, places=3)
        self.assertFalse(rnd.over)

    def test_fall_respawns_at_checkpoint(self):
        rnd, chars = self.make_round("starter_run", 1, 1)
        rnd.start_race()
        c = chars[0]
        c.place_at(0, 50, 0.1)  # inside checkpoint 1
        for _ in range(10):
            rnd.tick()
        self.assertEqual(c.checkpoint, 1)
        c.place_at(0, 43.5, -11)  # below kill height
        rnd.tick()
        self.assertEqual(c.stat_falls, 1)
        self.assertEqual(c.state, MoveState.RESPAWNING)
        for _ in range(int(C.RESPAWN_DELAY * 60) + 5):
            rnd.tick()
        self.assertFalse(c.eliminated)
        self.assertGreater(c.y, 45)
        self.assertLess(c.y, 62)

    def test_fall_eliminates_on_eliminate_map(self):
        rnd, chars = self.make_round("vanishing_tiles", 2, 1)
        rnd.start_race()
        chars[0].place_at(0, 20, -13)
        rnd.tick()
        self.assertTrue(chars[0].eliminated)
        self.assertFalse(rnd.over)

    def test_everyone_eliminated_never_hangs(self):
        rnd, chars = self.make_round("vanishing_tiles", 3, 1, final=True)
        rnd.start_race()
        for i, c in enumerate(chars):
            c.place_at(0, 20, -13)
            rnd.tick()
        self.assertTrue(rnd.over)
        self.assertEqual(rnd.end_reason, "all_out")
        winners = [r for r in rnd.results if r.outcome == Outcome.WINNER]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].id, chars[-1].id)  # last to fall wins
        self.assertEqual(winners[0].reason, "last_standing")

    def test_nobody_qualifies_still_advances_someone(self):
        rnd, chars = self.make_round("vanishing_tiles", 4, 2, final=False)
        rnd.start_race()
        for c in chars:
            c.place_at(0, 20, -13)
            rnd.tick()
        self.assertTrue(rnd.over)
        q = [r for r in rnd.results if r.outcome == Outcome.QUALIFIED]
        self.assertGreaterEqual(len(q), 1)

    def test_timeout_ends_round(self):
        rnd, chars = self.make_round("starter_run", 3, 2)
        rnd.world.time_limit = 2.0
        rnd.start_race()
        for _ in range(200):
            rnd.tick()
        self.assertTrue(rnd.over)
        self.assertEqual(rnd.end_reason, "time")
        self.assertEqual(len(rnd.results), 3)

    def test_finish_and_quota(self):
        rnd, chars = self.make_round("starter_run", 3, 2)
        rnd.start_race()
        f = rnd.world.finish
        for c in chars[:2]:
            c.place_at((f.minx + f.maxx) / 2, (f.miny + f.maxy) / 2, 1.2)
            rnd.tick()
        self.assertTrue(rnd.over)
        self.assertEqual(rnd.end_reason, "quota")
        self.assertEqual([r.outcome for r in rnd.results[:2]], [Outcome.QUALIFIED] * 2)
        self.assertEqual(rnd.results[2].outcome, Outcome.ELIMINATED)

    def test_disconnect_removes_player(self):
        rnd, chars = self.make_round("starter_run", 2, 1)
        rnd.start_race()
        rnd.remove_participant("c0")
        self.assertTrue(chars[0].eliminated)
        rnd.remove_participant("c1")
        self.assertTrue(rnd.over)

    def test_obstacle_jump_counter(self):
        rnd, chars = self.make_round("starter_run", 1, 1)
        rnd.start_race()
        c = chars[0]
        c.place_at(0, 17.5, 0)
        for _ in range(120):
            rnd.controllers = {"c0": type("K", (), {"command": lambda s, ch, r: InputCommand(0, 1, jump=ch.y > 18.6)})()}
            rnd.tick()
        self.assertGreaterEqual(c.stat_obstacles, 1)


class CourseCompletionTests(unittest.TestCase):
    def test_every_course_is_completed_by_a_bot(self):
        for m in MM.ids():
            for seed in (1, 2):
                ch = Character("b", "bot", is_bot=True)
                rnd = RoundSimulation(MM.get(m), [ch], {}, 1, False, seed=seed)
                rnd.controllers["b"] = make_bot("HARD", random.Random(seed), rnd.world)
                rnd.start_race()
                last = (ch.x, ch.y, ch.z)
                while not rnd.over:
                    rnd.tick()
                    # no teleporting: at most max fall speed per tick, except respawns
                    jump = math.dist(last, (ch.x, ch.y, ch.z))
                    if not any(e[0] == "respawn" for e in rnd.events):
                        self.assertLess(jump, 1.0, "bot moved %.2f m in one tick on %s" % (jump, m))
                    last = (ch.x, ch.y, ch.z)
                self.assertTrue(ch.finished, "HARD bot did not finish %s (seed %d): %s" % (m, seed, rnd.end_reason))
                self.assertLess(ch.finish_time, rnd.world.time_limit)

    def test_bot_commands_are_legal(self):
        rnd = RoundSimulation(MM.get("hammer_havoc"), [Character("b", "b", is_bot=True)], {}, 1, False)
        bot = make_bot("CHAOTIC", random.Random(3), rnd.world)
        rnd.start_race()
        ch = rnd.characters[0]
        for _ in range(600):
            cmd = bot.command(ch, rnd)
            self.assertLessEqual(math.hypot(cmd.move_x, cmd.move_y), 1.0 + 1e-6)
            rnd.controllers["b"] = type("K", (), {"command": lambda s, c, r, cmd=cmd: cmd})()
            rnd.tick()

    def test_lower_route_of_vanishing_tiles_is_completable(self):
        ch = Character("b", "bot", is_bot=True)
        rnd = RoundSimulation(MM.get("vanishing_tiles"), [ch], {}, 1, False, seed=1)
        rnd.controllers["b"] = make_bot("HARD", random.Random(1), rnd.world)
        rnd.start_race()
        ch.place_at(0, 75, -4.4)  # dropped onto the lower floor
        while not rnd.over:
            rnd.tick()
        self.assertTrue(ch.finished, rnd.end_reason)


class ShowTests(unittest.TestCase):
    def test_full_show_reaches_game_over(self):
        rng = random.Random(5)
        parts = [Participant("p%d" % i, "P%d" % i, is_bot=True, difficulty="NORMAL") for i in range(8)]
        gm = GameManager([MM.get(m) for m in MM.show_playlist()], parts,
                         lambda p, c, r: make_bot(p.difficulty, random.Random(rng.random()), r.world),
                         GameSettings(countdown=0.5, round_end=0.2, results_auto=0.1), seed=5,
                         local_player_id="p0")
        seen = []
        gm.add_listener(lambda k, d: seen.append(d) if k == "state" else None)
        gm.start()
        for _ in range(int(600 / (1 / 30.0))):
            gm.update(1 / 30.0)
            if gm.state == GameState.GAME_OVER:
                break
        self.assertEqual(gm.state, GameState.GAME_OVER)
        for st in (GameState.COUNTDOWN, GameState.ROUND_START, GameState.ROUND_ACTIVE,
                   GameState.ROUND_END, GameState.RESULTS, GameState.GAME_OVER):
            self.assertIn(st, seen)
        self.assertIsNotNone(gm.champion_id)
        self.assertEqual(len(gm.final_standings), 8)
        self.assertEqual(sorted(p for p, _ in gm.final_standings), list(range(1, 9)))
        self.assertIsNotNone(gm.local_report)

    def test_illegal_state_change_rejected(self):
        gm = GameManager([MM.get("starter_run")], [Participant("a", "A")], lambda *a: None)
        with self.assertRaises(RuntimeError):
            gm._set_state(GameState.RESULTS)

    def test_quit_produces_report(self):
        gm = GameManager([MM.get("starter_run")], [Participant("a", "A"), Participant("b", "B", is_bot=True)],
                         lambda *a: None, local_player_id="a")
        gm.start()
        gm.update(0.5)
        gm.abort()
        self.assertEqual(gm.state, GameState.GAME_OVER)
        self.assertTrue(gm.local_report.quit_early)

    def test_qualify_counts(self):
        self.assertEqual(qualify_count_for(16, 2), 11)
        self.assertEqual(qualify_count_for(2, 1), 1)
        self.assertEqual(qualify_count_for(1, 1), 1)


class MapFileTests(unittest.TestCase):
    def test_three_maps_load(self):
        self.assertEqual(MM.ids(), ["starter_run", "hammer_havoc", "vanishing_tiles"])
        self.assertEqual(MM.errors, {})

    def test_bad_map_is_rejected_not_crashing(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "broken.json"), "w") as fh:
            fh.write("{oops")
        with open(os.path.join(MM.maps_dir, "starter_run.json")) as fh:
            good = json.load(fh)
        good["id"] = "copy"
        good["elements"].append({"type": "lava_cannon"})
        with open(os.path.join(d, "bad_type.json"), "w") as fh:
            json.dump(good, fh)
        mm = MapManager(d)
        self.assertEqual(mm.maps, {})
        self.assertEqual(len(mm.errors), 2)
        with self.assertRaises(MapFormatError):
            LoadedMap({"id": "x", "name": "x", "spawn": {"x": 0, "y": 0, "top": 0}, "elements": []})


if __name__ == "__main__":
    unittest.main()
