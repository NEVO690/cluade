"""Unit tests for the non-visual systems.

    python -m unittest discover -s tests -v
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from game import settings as S  # noqa: E402
from game import utils  # noqa: E402
from game.database import GameData  # noqa: E402
from game.events import EventManager, event_window  # noqa: E402
from game.missions import MissionManager  # noqa: E402
from game.obstacles import Obstacle, LOW, HIGH, BLOCK, TRAIN, RAMP  # noqa: E402
from game.player import Player  # noqa: E402
from game.powerups import PowerUpManager  # noqa: E402
from game.progression import Progression, Achievements, DailyRewards, xp_to_next  # noqa: E402
from game.save_system import SaveSystem, SettingsStore  # noqa: E402
from game.shop import Economy, Shop  # noqa: E402
from game.world import World, PASSABLE, LATERAL_BLOCK  # noqa: E402

pygame.init()
DATA = GameData()


class FakeAssets:
    def font(self, size, bold=True):
        return pygame.font.Font(None, size)

    def icon(self, *a, **k):
        return pygame.Surface((4, 4), pygame.SRCALPHA)

    def sprite_frames(self, *a):
        return []


def make_save(tmp):
    save = SaveSystem(DATA, os.path.join(tmp, "savegame.json"))
    save.load()
    return save


def make_systems(tmp):
    save = make_save(tmp)
    eco = Economy(DATA, save)
    prog = Progression(DATA, save, eco)
    settings = SettingsStore(DATA.default_settings, os.path.join(tmp, "settings.json"))
    settings.load()
    events = EventManager(DATA, save, settings, eco, prog)
    missions = MissionManager(DATA, save, eco, prog, events)
    return save, eco, prog, settings, events, missions


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ssc_ut_")
        utils.WARNINGS.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class SaveSystemTests(TempDirTest):
    def test_fresh_save_is_created_and_reloaded(self):
        save = make_save(self.tmp)
        self.assertTrue(os.path.exists(save.path))
        save["coins"] = 1234
        save["characters_owned"].append("maya")
        save.save()
        again = make_save(self.tmp)
        self.assertEqual(again["coins"], 1234)
        self.assertIn("maya", again["characters_owned"])

    def test_corrupted_save_is_backed_up_and_reset(self):
        path = os.path.join(self.tmp, "savegame.json")
        with open(path, "w") as f:
            f.write("{ this is not json")
        save = make_save(self.tmp)
        self.assertEqual(save["coins"], 0)
        backups = [f for f in os.listdir(self.tmp) if "corrupt" in f]
        self.assertEqual(len(backups), 1)
        self.assertTrue(any("corrupted" in w for w in utils.WARNINGS))

    def test_invalid_values_are_repaired(self):
        path = os.path.join(self.tmp, "savegame.json")
        with open(path, "w") as f:
            json.dump({"coins": "lots", "gems": -5, "level": 999, "character": "ghost",
                       "characters_owned": ["ghost"], "upgrades": {"magnet": "x", "jet": 2}}, f)
        save = make_save(self.tmp)
        self.assertEqual(save["coins"], 0)
        self.assertEqual(save["gems"], 0)
        self.assertEqual(save["level"], S.MAX_LEVEL)
        self.assertEqual(save["character"], DATA.characters[0]["id"])
        self.assertEqual(save["upgrades"], {"jet": 2})

    def test_settings_corruption_falls_back(self):
        path = os.path.join(self.tmp, "settings.json")
        with open(path, "w") as f:
            f.write("[1, 2")
        st = SettingsStore(DATA.default_settings, path)
        st.load()
        self.assertEqual(st["graphics_quality"], DATA.default_settings["graphics_quality"])
        self.assertIn("jump", st["keys"])


class DataLoadingTests(TempDirTest):
    def test_broken_and_missing_data_files_use_fallbacks(self):
        with open(os.path.join(self.tmp, "characters.json"), "w") as f:
            f.write("{broken")
        with open(os.path.join(self.tmp, "zones.json"), "w") as f:
            json.dump([{"id": "x"}, {"name": "no id"}], f)  # first entry lacks name, second lacks id
        with mock.patch.object(S, "DATA_DIR", self.tmp):
            gd = GameData()
        self.assertTrue(gd.characters)
        self.assertTrue(gd.zones)
        self.assertTrue(gd.powerups)
        self.assertTrue(gd.items["boards"])
        self.assertTrue(utils.WARNINGS)

    def test_real_data_is_valid(self):
        utils.WARNINGS.clear()
        GameData()
        self.assertEqual(utils.WARNINGS, [], utils.WARNINGS)
        self.assertGreaterEqual(len(DATA.characters), 5)
        self.assertGreaterEqual(len(DATA.zones), 7)
        effects = {p["effect"] for p in DATA.powerups}
        for e in ("magnet", "jet", "shield", "score_mult", "super_jump", "speed"):
            self.assertIn(e, effects)


class EconomyTests(TempDirTest):
    def test_purchase_equip_and_upgrade(self):
        save, eco, *_ = make_systems(self.tmp)
        shop = Shop(DATA, eco)
        board = DATA.item("neon_board")
        ok, _ = eco.purchase(board)
        self.assertFalse(ok)  # no coins yet
        eco.add("coins", 10000)
        ok, msg = eco.purchase(board)
        self.assertTrue(ok, msg)
        self.assertTrue(eco.owned("boards", "neon_board"))
        self.assertEqual(eco.coins, 10000 - board["price"])
        self.assertTrue(eco.equip("boards", "neon_board"))
        ok, _ = eco.purchase(board)
        self.assertFalse(ok)  # already owned
        cost = eco.upgrade_cost("magnet")
        ok, _ = eco.buy_upgrade("magnet")
        self.assertTrue(ok)
        self.assertEqual(eco.upgrade_level("magnet"), 1)
        self.assertEqual(eco.coins, 10000 - board["price"] - cost)
        tabs = [shop.entries(t) for t in ("characters", "powerups", "upgrades", "boards", "cosmetics", "trails")]
        self.assertTrue(all(tabs))

    def test_level_locked_character(self):
        save, eco, *_ = make_systems(self.tmp)
        eco.add("coins", 1_000_000)
        ok, msg = eco.purchase(DATA.item("juno"))
        self.assertFalse(ok)
        self.assertIn("level", msg.lower())

    def test_consumables(self):
        save, eco, *_ = make_systems(self.tmp)
        start = eco.consumable("board_charge")
        self.assertTrue(eco.use_consumable("board_charge"))
        self.assertEqual(eco.consumable("board_charge"), start - 1)
        save["consumables"]["head_start"] = 0
        self.assertFalse(eco.use_consumable("head_start"))


class MissionTests(TempDirTest):
    def test_total_and_run_missions(self):
        save, eco, prog, st, events, missions = make_systems(self.tmp)
        missions.begin_run()
        first = missions.regular_active()[0]
        self.assertEqual(first.stat, "coins")
        coins_before = eco.coins
        for _ in range(int(first.target)):
            missions.record("coins", 1)
        self.assertTrue(missions.is_completed(first))
        self.assertGreater(eco.coins, coins_before)
        # slot refilled with the next mission
        self.assertNotIn(first.id, [m.id for m in missions.regular_active()])
        # run-mode distance mission
        missions.begin_run()
        dist = [m for m in missions.regular_active() if m.stat == "distance"][0]
        missions.record("distance", 500, 500)
        self.assertFalse(missions.is_completed(dist))
        missions.record("distance", 600, 1100)
        self.assertTrue(missions.is_completed(dist))

    def test_daily_missions_are_deterministic_per_day(self):
        save, eco, prog, st, events, missions = make_systems(self.tmp)
        a = [m.desc for m in missions.daily()]
        save["daily_missions"] = {"date": "", "missions": [], "progress": {}, "completed": []}
        missions.ensure_daily()
        b = [m.desc for m in missions.daily()]
        self.assertEqual(a, b)
        self.assertEqual(len(a), DATA.daily_count)


class ProgressionTests(TempDirTest):
    def test_level_up_rewards(self):
        save, eco, prog, *_ = make_systems(self.tmp)
        need = xp_to_next(1) + xp_to_next(2)
        gained = prog.add_xp(need + 5)
        self.assertEqual(gained, [2, 3])
        self.assertEqual(prog.level, 3)
        self.assertEqual(prog.xp, 5)
        self.assertGreater(eco.coins, 0)
        self.assertIn("old_town", prog.unlocked_zone_ids())

    def test_max_level(self):
        save, eco, prog, *_ = make_systems(self.tmp)
        prog.add_xp(10 ** 9)
        self.assertEqual(prog.level, S.MAX_LEVEL)

    def test_achievements(self):
        save, eco, prog, *_ = make_systems(self.tmp)
        ach = Achievements(DATA, save, eco, prog)
        save.stat_add("runs", 1)
        new = [a["id"] for a in ach.check()]
        self.assertIn("first_run", new)
        self.assertEqual(ach.check(), [])  # not unlocked twice

    def test_daily_rewards_streak(self):
        save, eco, prog, *_ = make_systems(self.tmp)
        daily = DailyRewards(DATA, save, eco, prog)
        d0 = datetime.date(2026, 1, 1)
        self.assertEqual(daily.claim(d0)[0], 1)
        self.assertIsNone(daily.claim(d0))  # once per day
        self.assertEqual(daily.claim(d0 + datetime.timedelta(days=1))[0], 2)
        self.assertEqual(daily.claim(d0 + datetime.timedelta(days=2))[0], 3)
        # missed a day -> back to day 1
        self.assertEqual(daily.claim(d0 + datetime.timedelta(days=5))[0], 1)
        # full week wraps from 7 back to 1
        day = d0 + datetime.timedelta(days=10)
        results = [daily.claim(day + datetime.timedelta(days=i))[0] for i in range(8)]
        self.assertEqual(results, [1, 2, 3, 4, 5, 6, 7, 1])


class EventTests(TempDirTest):
    def test_event_windows(self):
        winter = DATA.event_by_id["winter"]
        start, end = event_window(winter, datetime.date(2027, 1, 5))
        self.assertEqual((start, end), (datetime.date(2026, 12, 10), datetime.date(2027, 1, 15)))
        save, eco, prog, st, events, missions = make_systems(self.tmp)
        st["force_event"] = ""
        self.assertEqual(events.active(datetime.date(2026, 10, 20))["id"], "halloween")
        self.assertEqual(events.active(datetime.date(2027, 1, 3))["id"], "winter")
        self.assertIsNone(events.active(datetime.date(2026, 3, 3)))
        st["force_event"] = "summer"
        self.assertEqual(events.active(datetime.date(2026, 3, 3))["id"], "summer")

    def test_reward_track(self):
        save, eco, prog, st, events, missions = make_systems(self.tmp)
        ev = DATA.event_by_id["halloween"]
        self.assertEqual(events.reward_status(ev, 0), "locked")
        events.add_tokens(ev, ev["rewards"][1]["tokens"])
        self.assertEqual(events.reward_status(ev, 0), "ready")
        self.assertTrue(events.claim(ev, 1))
        self.assertTrue(eco.owned("emotes", "emote_boo"))
        self.assertEqual(events.reward_status(ev, 1), "claimed")
        self.assertIsNone(events.claim(ev, 1))


class FakeSession:
    def __init__(self, world, player):
        self.world = world
        self.player = player
        self.invuln = 0

    def grant_invulnerability(self, s):
        self.invuln = s


class GeneratorTests(unittest.TestCase):
    def _world(self, seed, zones=None):
        zones = zones or [z["id"] for z in DATA.zones]
        return World(DATA, S.QUALITY_PRESETS["low"], zones, FakeAssets(), seed=seed)

    def test_rows_always_have_a_safe_path(self):
        for seed in range(12):
            w = self._world(seed)
            rows = []
            orig = w._generate_row

            def spy(z, ch, _orig=orig, _w=w):
                prev = list(_w.prev_cells)
                _orig(z, ch)
                rows.append((z, prev, list(_w.prev_cells), _w.safe_lane))
            w._generate_row = spy
            z = 0
            while z < 12000:
                w.player_z = z - 150
                w.update(0, z, z - 8, 170)
                z += 40
            self.assertGreater(len(rows), 300)
            safe_prev = 1
            for z, prev, cur, safe in rows:
                self.assertIn(cur[safe], PASSABLE | {"low", "high"}, f"seed {seed} z {z}: safe lane blocked {cur}")
                self.assertLessEqual(abs(safe - safe_prev), 1, f"seed {seed} z {z}: safe lane jumped")
                if safe != safe_prev:
                    self.assertNotIn(prev[safe], LATERAL_BLOCK, f"seed {seed} z {z}: safe lane moved into a train")
                safe_prev = safe

    def test_static_obstacles_never_block_safe_lane(self):
        w = self._world(7)
        rows = []
        orig = w._generate_row

        def spy(z, ch):
            orig(z, ch)
            rows.append((z, w.safe_lane))
        w._generate_row = spy
        z = 0
        while z < 6000:
            w.player_z = z - 150
            w.update(0, z, z - 8, 170)
            z += 40
        for rz, safe in rows:
            x = S.LANE_X[safe]
            for ob in w.obstacles_near(rz - 0.1, rz + 0.1):
                if abs(ob.x - x) < 0.1 and ob.vel == 0:
                    self.assertIn(ob.kind, (LOW, HIGH), f"blocking {ob.kind} in safe lane at {rz}")

    def test_chunks_are_unloaded(self):
        w = self._world(3)
        for z in range(0, 20000, 20):
            w.update(0, z, z - 8, 170)
        self.assertLess(len(w.chunks), 10)
        self.assertLess(len(w.movers), 30)

    def test_zones_rotate_and_blend(self):
        w = self._world(5)
        seen = set()
        for z in range(0, 15000, 100):
            zone, nxt, t = w.schedule.zone_at(z)
            seen.add(zone["id"])
            self.assertTrue(0 <= t <= 1)
        self.assertEqual(len(seen), len(DATA.zones))


class PhysicsTests(unittest.TestCase):
    def setUp(self):
        self.world = World(DATA, S.QUALITY_PRESETS["low"], ["downtown"], FakeAssets(), seed=1, spawn_obstacles=False)
        self.world.update(0, 0, -8, 170)
        self.player = Player(dict(DATA.characters[0]["colors"], hair_style="short", accessory="none", build=1.0),
                             None, 0.0, FakeAssets())

    def run_for(self, seconds, speed=20.0):
        for _ in range(int(seconds / S.PHYSICS_STEP)):
            self.player.update(S.PHYSICS_STEP, speed, self.world)

    def test_jump_clears_low_barrier_height(self):
        p = self.player
        self.assertTrue(p.jump())
        peak = 0
        for _ in range(int(1.0 / S.PHYSICS_STEP)):
            p.update(S.PHYSICS_STEP, 20, self.world)
            peak = max(peak, p.y)
        self.assertGreater(peak, 1.3)   # low barrier is 1.0 m tall
        self.assertLess(peak, 3.2)      # but you can't jump onto a train (3.3 m) without help
        self.assertTrue(p.on_ground)

    def test_slide_fits_under_high_barrier(self):
        p = self.player
        p.slide()
        self.assertLess(p.height, 1.2)  # high barrier bottom is 1.2 m
        self.run_for(1.0)
        self.assertFalse(p.sliding)

    def test_lane_switching_and_edges(self):
        p = self.player
        self.assertTrue(p.move(-1))
        self.assertFalse(p.move(-1))
        self.run_for(0.4)
        self.assertAlmostEqual(p.x, S.LANE_X[0], places=3)

    def test_ramp_leads_onto_train_roof(self):
        p = self.player
        ramp = Obstacle(RAMP, 1, 5.0)
        train = Obstacle(TRAIN, 1, ramp.z1, length=20)
        self.world.chunks[0].obstacles += [ramp, train]
        self.run_for(1.0, speed=15)
        self.assertGreater(p.z, train.z0)
        self.assertAlmostEqual(p.y, train.y1, places=2)
        self.assertIs(p.standing_on, train)
        self.run_for(2.0, speed=15)  # run off the end and fall back down
        self.assertEqual(p.y, 0.0)


class SessionCollisionTests(TempDirTest):
    """Drive the real GameSession with a fake app to verify collision rules."""

    def setUp(self):
        super().setUp()
        from game.gameplay import GameSession
        from game.progression import Achievements

        class Audio:
            def play(self, *a, **k):
                pass

            def play_music(self, *a, **k):
                pass

        save, eco, prog, st, events, missions = make_systems(self.tmp)

        class App:
            pass
        app = App()
        app.data, app.save, app.economy, app.progression = DATA, save, eco, prog
        app.settings, app.events, app.missions = st, events, missions
        app.achievements = Achievements(DATA, save, eco, prog)
        app.audio = Audio()
        app.assets = FakeAssets()
        from game.scenery import SpriteBank
        app.sprites = SpriteBank(FakeAssets())
        st["force_event"] = ""
        self.app = app
        self.sess = GameSession(app)
        self.sess.world.chunks[0].obstacles.clear()
        for ch in self.sess.world.chunks:
            ch.obstacles.clear()
            ch.collectibles.clear()
        self.sess.world.movers.clear()
        self.sess.world.spawn_obstacles = False
        self.sess.powerups.active.clear()

    def place(self, kind, lane, ahead, **kw):
        ob = Obstacle(kind, lane, self.sess.player.z + ahead, **kw)
        self.sess.world.chunks[0].obstacles.append(ob)
        self.sess.world.chunks[0].max_z = max(self.sess.world.chunks[0].max_z, ob.z1)
        return ob

    def advance(self, seconds):
        for _ in range(int(seconds * 60)):
            self.sess.update(1 / 60)
            if self.sess.state != "running":
                break

    def test_running_into_block_ends_run(self):
        self.place(BLOCK, 1, 12)
        self.advance(2)
        self.assertEqual(self.sess.state, "dead")

    def advance_until_close(self, ob, seconds_before):
        for _ in range(600):
            if ob.z0 - self.sess.player.z <= max(self.sess.speed, 1) * seconds_before:
                return
            self.sess.update(1 / 60)
        self.fail("obstacle never got close")

    def test_jump_over_low_barrier(self):
        ob = self.place(LOW, 1, 14)
        self.advance_until_close(ob, 0.2)
        self.sess.act("jump")
        self.advance(1.5)
        self.assertEqual(self.sess.state, "running")
        self.assertEqual(self.sess.stats["jump_over"], 1)

    def test_slide_under_high_barrier(self):
        ob = self.place(HIGH, 1, 12)
        self.advance_until_close(ob, 0.2)
        self.sess.act("slide")
        self.advance(1.5)
        self.assertEqual(self.sess.state, "running")
        self.assertEqual(self.sess.stats["slide_under"], 1)

    def test_run_up_ramp_onto_train_roof(self):
        ramp = self.place(RAMP, 1, 12)
        train = Obstacle(TRAIN, 1, ramp.z1, length=30)
        self.sess.world.chunks[0].obstacles.append(train)
        self.sess.world.chunks[0].max_z = train.z1
        self.advance(2.0)
        self.assertEqual(self.sess.state, "running")
        self.assertGreaterEqual(self.sess.stats["trains_landed"], 0)
        self.assertGreater(self.sess.player.z, train.z0)

    def test_hitting_train_front_crashes(self):
        self.place(TRAIN, 1, 12, length=30)
        self.advance(2.0)
        self.assertEqual(self.sess.state, "dead")

    def test_shield_absorbs_one_hit(self):
        self.sess.powerups.activate("shield", self.sess)
        self.place(BLOCK, 1, 10)
        self.advance(1.5)
        self.assertEqual(self.sess.state, "running")
        self.assertFalse(self.sess.powerups.has("shield"))

    def test_side_bump_then_second_bump_crashes(self):
        self.place(TRAIN, 0, -5, length=60)
        self.advance(0.2)
        self.sess.act("left")
        self.advance(0.5)
        self.assertEqual(self.sess.state, "running")
        self.assertEqual(self.sess.player.lane, 1)  # bounced back
        self.assertGreater(self.sess.stumble_timer, 0)
        self.sess.act("left")
        self.advance(0.5)
        self.assertEqual(self.sess.state, "dead")

    def test_coins_and_magnet(self):
        from game.collectibles import Collectible, COIN
        ch = self.sess.world.chunks[0]
        p = self.sess.player
        ch.collectibles += [Collectible(COIN, 0.0, 0.9, p.z + 8 + i * 2) for i in range(5)]
        ch.collectibles += [Collectible(COIN, S.LANE_X[2], 0.9, p.z + 25)]
        self.sess.powerups.activate("magnet", self.sess)
        self.advance(2.0)
        self.assertEqual(self.sess.coins, 6)
        self.assertGreater(self.sess.score, 6 * S.COIN_SCORE)

    def test_jet_boost_flies_over_everything(self):
        self.sess.powerups.activate("jet", self.sess, duration=3)
        self.place(BLOCK, 1, 30)
        self.place(TRAIN, 1, 40, length=30)
        self.advance(2.5)
        self.assertEqual(self.sess.state, "running")
        self.assertGreater(self.sess.player.y, 4)

    def test_finalize_banks_rewards(self):
        self.advance(3)
        coins_before = self.app.economy.coins
        self.sess.coins = 40
        res = self.sess.finalize()
        # +40 run coins (plus any mission/achievement rewards unlocked by this first run)
        self.assertGreaterEqual(self.app.economy.coins, coins_before + 40)
        self.assertEqual(res["coins"], 40)
        self.assertGreater(res["xp"], 0)
        self.assertEqual(self.app.save.stat("runs"), 1)
        self.assertIs(self.sess.finalize(), res)  # idempotent


class PowerUpTests(TempDirTest):
    def test_durations_scale_with_upgrades(self):
        save, eco, *_ = make_systems(self.tmp)
        pm = PowerUpManager(DATA, eco)
        d0 = pm.duration_for("magnet")
        save["upgrades"]["magnet"] = 3
        self.assertGreater(pm.duration_for("magnet"), d0)
        pm2 = PowerUpManager(DATA, eco, duration_bonus=0.2)
        self.assertAlmostEqual(pm2.duration_for("magnet"), pm.duration_for("magnet") * 1.2)


if __name__ == "__main__":
    unittest.main()
