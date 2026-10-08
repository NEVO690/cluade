"""End-to-end UI test: drives the real App with synthetic mouse/keyboard events.

    python -m unittest tests.test_ui_flow -v
"""
import os
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from game import settings as S  # noqa: E402


class UIFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ssc_ui_")
        cls._old_save_dir = S.SAVE_DIR
        S.SAVE_DIR = cls.tmp
        import game.main as gm
        cls.app = gm.App()
        cls.app.settings["force_event"] = "halloween"
        while cls.app.scene_name == "loading":
            cls.app.step(1 / 60)
        cls.frames(cls, 30)

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown()
        S.SAVE_DIR = cls._old_save_dir
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    def frames(self, n):
        for _ in range(n):
            self.app.step(1 / 60)

    def click(self, pos):
        pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
        self.settle()

    def settle(self):
        """Run frames until any scene fade transition has finished (input is ignored while fading)."""
        self.frames(2)
        for _ in range(120):
            if self.app._fade_dir == 0:
                break
            self.app.step(1 / 60)

    def key(self, k):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0))
        self.settle()
        self.frames(16)

    def button(self, text):
        for b in self.app.scene.buttons:
            if b.text == text:
                return b
        self.fail(f"button {text!r} not found in {self.app.scene_name}: {[b.text for b in self.app.scene.buttons]}")

    # ------------------------------------------------------------------
    def test_full_flow(self):
        app = self.app
        self.assertEqual(app.scene_name, "menu")
        menu = app.scene
        if menu.popup == "daily":
            self.click(menu.popup_buttons[0].rect.center)  # CLAIM
            self.assertFalse(app.daily.available())
        self.assertIsNone(menu.popup)

        # visit every menu screen and come back with the back button
        for label, scene in (("SEASON PASS", "season"), ("LOCKER", "locker"), ("SHOP", "shop"), ("MISSIONS", "missions"),
                             ("UPGRADES", "upgrades"), ("EVENTS", "events"), ("ACHIEVEMENTS", "achievements"),
                             ("SETTINGS", "settings")):
            self.click(self.button(label).rect.center)
            self.assertEqual(app.scene_name, scene)
            self.frames(5)
            self.click(app.scene._back_btn.rect.center)
            self.assertEqual(app.scene_name, "menu")

        # buy a board in the locker with coins we give ourselves
        app.economy.add("coins", 5000)
        self.click(self.button("LOCKER").rect.center)
        locker = app.scene
        self.click(self.button("Boards").rect.center)
        idx = [e.id for e in locker.entries].index("neon_board")
        card = locker._card_rect(idx)
        self.click(locker._action_rect(card).center)
        self.assertTrue(app.economy.owned("boards", "neon_board"))
        self.assertEqual(app.economy.equipped("boards"), "neon_board")
        self.click(locker._back_btn.rect.center)

        # limited-time shop offers: Vex for 900 coins
        if app.offers.active():
            app.economy.add("coins", 900)
            self.click(self.button("SHOP").rect.center)
            shop = app.scene
            self.assertEqual(shop.tab, "offers")
            buy = [b for b in shop.buttons if b.text == "" and b.style == "primary"][0]
            self.click(buy.rect.center)
            self.assertTrue(app.economy.owned("characters", "vex"))
            self.click(shop._back_btn.rect.center)

        # buy the premium season pass and claim its tier-1 character (only while a season runs)
        if app.season.current():
            app.economy.add("coins", 10000)
            app.season.add_points(1200)
            self.click(self.button("SEASON PASS").rect.center)
            self.assertEqual(app.scene_name, "season")
            self.click(self.button("PREMIUM  10,000").rect.center)
            season = app.season.current()
            self.assertTrue(app.season.has_premium(season))
            card = app.scene._card_rect(0, "premium")
            self.click(card.center)
            self.assertTrue(app.economy.owned("characters", "kira"))
            self.click(app.scene._back_btn.rect.center)

        # upgrade the magnet
        self.click(self.button("UPGRADES").rect.center)
        before = app.economy.upgrade_level("magnet")
        self.click(app.scene.buttons[1].rect.center)
        self.assertEqual(app.economy.upgrade_level("magnet"), before + 1)
        self.click(app.scene._back_btn.rect.center)

        # play: move, jump, slide
        self.click(self.button("PLAY").rect.center)
        self.assertEqual(app.scene_name, "game")
        game = app.scene
        sess = game.session
        self.frames(30)
        self.key(pygame.K_LEFT)
        self.assertEqual(sess.player.lane, 0)
        self.key(pygame.K_d)
        self.assertEqual(sess.player.lane, 1)
        self.key(pygame.K_SPACE)
        self.assertGreaterEqual(sess.stats["jumps"], 1)
        self.frames(60)
        self.key(pygame.K_DOWN)
        self.assertGreaterEqual(sess.stats["slides"], 1)

        # swipe with the mouse
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(640, 500), button=1))
        pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=(760, 505), rel=(120, 5), buttons=(1, 0, 0)))
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(760, 505), button=1))
        self.frames(3)
        self.assertEqual(sess.player.lane, 2)

        # pause via the HUD button, open settings, come back, resume
        self.click(game.hud.pause_rect.center)
        self.assertEqual(game.mode, "paused")
        self.click(self.button("SETTINGS").rect.center)
        self.assertEqual(app.scene_name, "settings")
        self.click(app.scene._back_btn.rect.center)
        self.assertEqual(app.scene_name, "game")
        self.assertIs(app.scene.session, sess)
        self.assertEqual(game.mode, "paused")
        self.click(self.button("RESUME").rect.center)
        self.frames(200)
        self.assertEqual(game.mode, "play")

        # force a crash and go through game over
        sess.app.economy.save["consumables"]["revive_key"] = 0
        sess.powerups.clear(sess)
        sess._die()
        self.frames(120)
        self.assertEqual(game.mode, "over")
        self.assertIsNotNone(sess.result)
        self.click(self.button("RETRY").rect.center)
        self.assertIsNot(game.session, sess)
        self.assertEqual(game.mode, "play")
        self.frames(30)
        game.pause()
        self.click(self.button("QUIT").rect.center)
        self.assertEqual(app.scene_name, "menu")

        # save on disk reflects the purchases
        app.save.save()
        import json
        with open(os.path.join(self.tmp, "savegame.json")) as f:
            data = json.load(f)
        self.assertIn("neon_board", data["boards_owned"])
        self.assertGreaterEqual(data["stats"]["runs"], 2)

    def test_settings_widgets(self):
        app = self.app
        app.change_scene("settings")
        self.settle()
        sc = app.scene
        self.click(self.button("LOW").rect.center)
        self.assertEqual(app.settings["graphics_quality"], "low")
        self.click(self.button("MEDIUM").rect.center)
        # drag the music slider to the far left
        sl = sc.widgets[0]
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(sl.rect.x + 2, sl.rect.centery), button=1))
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(sl.rect.x + 2, sl.rect.centery), button=1))
        self.frames(3)
        self.assertLess(app.settings["music_volume"], 0.05)
        # rebind jump to J
        jump_btn = [b for b in sc.buttons if "SPACE" in b.text][0]
        self.click(jump_btn.rect.center)
        self.key(pygame.K_j)
        self.assertEqual(app.settings["keys"]["jump"][0], "j")
        self.assertEqual(app.key_action(pygame.K_j), "jump")
        self.click(self.button("RESET KEYS").rect.center)
        self.assertEqual(app.key_action(pygame.K_SPACE), "jump")
        self.click(sc._back_btn.rect.center)
        self.assertEqual(app.scene_name, "menu")


if __name__ == "__main__":
    unittest.main()
