import unittest

from helpers import FakeClock, report, temp_profile, win_report


class XPTests(unittest.TestCase):
    def setUp(self):
        self.p, _ = temp_profile()

    def test_level_curve(self):
        self.assertEqual(self.p.xp.xp_to_next(1), 100)
        self.assertEqual(self.p.xp.xp_to_next(2), 140)

    def test_xp_levels_up_and_pays_once(self):
        gained = self.p.xp.add_xp(250)  # 100 to L2, 140 to L3, 10 left
        self.assertEqual([lvl for lvl, _ in gained], [2, 3])
        self.assertEqual(self.p.xp.level, 3)
        self.assertEqual(self.p.xp.xp, 10)
        self.assertTrue(all(c > 0 for _, c in gained))

    def test_max_level_cap(self):
        self.p.xp.add_xp(10_000_000)
        self.assertEqual(self.p.xp.level, 50)
        self.assertEqual(self.p.xp.xp_to_next(), 0)

    def test_match_gives_xp(self):
        s = self.p.apply_match_report(win_report(), 3, "m")
        self.assertGreater(s.total_xp, 300)
        self.assertGreater(self.p.xp.level, 1)


class RankTests(unittest.TestCase):
    def setUp(self):
        self.p, _ = temp_profile()

    def test_tiers(self):
        r = self.p.ranks
        self.assertEqual(r.tier_for(0)["id"], "ROOKIE")
        self.assertEqual(r.tier_for(100)["id"], "BRONZE")
        self.assertEqual(r.tier_for(449)["id"], "SILVER")
        self.assertEqual(r.tier_for(2000)["id"], "BONK LEGEND")

    def test_points_rules_are_deterministic(self):
        r = self.p.ranks
        win = win_report()
        self.assertEqual(r.points_for_report(win, 3), r.points_for_report(win, 3))
        self.assertEqual(r.points_for_report(win, 3), 30 + 60)  # 3 qualified rounds + win
        hard = win_report()
        hard.difficulty = "HARD"
        self.assertEqual(r.points_for_report(hard, 3), 135)
        out_r1 = report(rounds=[{"map_id": "starter_run", "outcome": "eliminated", "time": None}])
        self.assertEqual(r.points_for_report(out_r1, 3), -10)
        quit = report(quit_early=True)
        self.assertEqual(r.points_for_report(quit, 3), -15)

    def test_points_never_negative(self):
        self.p.ranks.apply(-500)
        self.assertEqual(self.p.ranks.points, 0)


class TitleTests(unittest.TestCase):
    def setUp(self):
        self.p, _ = temp_profile()

    def test_titles_need_conditions(self):
        with self.assertRaises(PermissionError):
            self.p.titles.equip("crown_chaser")
        self.assertNotIn("crown_chaser", self.p.titles.unlocked)

    def test_titles_unlock_from_play(self):
        s = self.p.apply_match_report(win_report(), 3, "m1")
        self.assertIn("rookie_runner", s.new_titles)
        self.assertIn("first_bonk", s.new_titles)
        self.assertIn("speed_demon", s.new_titles)  # 23.0 s on Starter Run
        self.assertNotIn("crown_chaser", self.p.titles.unlocked)
        self.p.apply_match_report(win_report(), 3, "m2")
        self.p.apply_match_report(win_report(), 3, "m3")
        self.assertIn("crown_chaser", self.p.titles.unlocked)
        self.assertIn("unstoppable", self.p.titles.unlocked)
        self.p.titles.equip("crown_chaser")
        self.assertEqual(self.p.titles.equipped_name(), "CROWN CHASER")

    def test_rank_title(self):
        self.p.ranks.apply(2000)
        self.p.refresh_unlocks()
        self.assertIn("bonk_legend", self.p.titles.unlocked)


class AchievementTests(unittest.TestCase):
    def test_progress_and_single_reward(self):
        p, _ = temp_profile()
        p.apply_match_report(win_report(), 3, "m1")
        self.assertIn("first_steps", p.achievements.completed_ids())
        self.assertIn("champion", p.achievements.completed_ids())
        st = p.stat_view()
        self.assertEqual(p.achievements.progress("veteran", st), 1)
        bal = p.currency.balance
        p.refresh_unlocks()  # re-evaluating must not pay again
        self.assertEqual(p.currency.balance, bal)


class QuestTests(unittest.TestCase):
    def test_daily_quests_and_clock_tamper(self):
        clock = FakeClock(1_800_000_000.0)
        p, _ = temp_profile(clock)
        day1 = [q["id"] for q in p.quests.active]
        self.assertEqual(len(day1), 3)
        # Moving the clock backwards never creates a new day.
        clock.t -= 5 * 86400
        self.assertFalse(p.quests.refresh())
        self.assertEqual([q["id"] for q in p.quests.active], day1)
        # A real new day rolls new quests.
        clock.t = 1_800_000_000.0 + 86400
        self.assertTrue(p.quests.refresh())
        self.assertNotEqual([q["id"] for q in p.quests.active], day1)

    def test_quest_rewards_paid_once(self):
        clock = FakeClock()
        p, _ = temp_profile(clock)
        for q in p.quests.active:
            q["template"], q["stat"], q["target"], q["progress"] = "play_games", "games_played", 1, 0
        s = p.apply_match_report(report(), 3, "m1")
        self.assertEqual(len(s.quests_completed), 3)
        bal = p.currency.balance
        s2 = p.apply_match_report(report(), 3, "m2")
        self.assertEqual(s2.quests_completed, [])
        self.assertTrue(all(q["claimed"] for q in p.quests.active))
        self.assertLess(p.currency.balance - bal, 100)  # only normal match coins


class StatsTests(unittest.TestCase):
    def test_streaks_and_best_times(self):
        p, _ = temp_profile()
        p.apply_match_report(win_report(), 3, "a")
        p.apply_match_report(win_report(), 3, "b")
        self.assertEqual(p.stats["current_streak"], 2)
        p.apply_match_report(report(), 3, "c")
        self.assertEqual(p.stats["current_streak"], 0)
        self.assertEqual(p.stats["best_streak"], 2)
        self.assertEqual(p.stats["best_times"]["starter_run"], 23.0)
        self.assertEqual(p.stats["map_finishes"]["vanishing_tiles"], 2)


if __name__ == "__main__":
    unittest.main()
