"""The battle scene: player input, fixed-step simulation, rendering, audio and pause menu."""
import math
import random

import pygame

from ilbrawl import config
from ilbrawl.engine.scene import Scene
from ilbrawl.gameplay.entities import Intent
from ilbrawl.gameplay.renderer import WorldRenderer
from ilbrawl.gameplay.world import World
from ilbrawl.ui import icons, text, theme
from ilbrawl.ui.hud import HUD
from ilbrawl.ui.widgets import Button, Dialog

STEP = 1.0 / config.SIM_HZ
VW, VH = config.VIRTUAL_W, config.VIRTUAL_H

SOUND_FOR_EVENT = {
    "explosion": "explosion", "death": "death", "super": "super", "pickup": "gem", "goal": "goal",
    "dash": "dash", "heal": None, "capture": "capture", "tile_break": "hit", "respawn": "whoosh",
    "blink": "whoosh", "wall": "hit", "throw": "whoosh", "go": "go", "super_ready": "super_ready",
}


def key_code(name):
    try:
        return pygame.key.key_code(name)
    except (ValueError, AttributeError):
        return None


def build_participants(game, mode_id, char_id):
    gd = game.data
    prof = game.profile
    mode = gd.modes[mode_id]
    names = list(game.i18n.t_list("bot_names"))
    random.shuffle(names)
    roster = [c for c in gd.char_order if c != char_id]
    random.shuffle(roster)
    diff = game.settings["ai_difficulty"]
    lvl = prof.char_level(char_id)
    shift = {"easy": -2, "normal": 0, "hard": 1, "expert": 2}[diff]
    parts = [{"char": char_id, "team": 0, "name": prof.display_name(game.i18n), "is_player": True,
              "level": lvl, "skin": prof.selected_skin(char_id)}]
    n_total = mode["team_size"] * mode["teams"]
    for i in range(1, n_total):
        team = i if mode["team_size"] == 1 else i // mode["team_size"]
        parts.append({"char": roster[i % len(roster)], "team": team, "name": names[i % len(names)] if names else "Bot",
                      "level": max(1, min(gd.max_level, lvl + shift + random.randint(-1, 1)))})
    return parts


class BattleScene(Scene):
    music = "battle"
    show_currency = False

    def __init__(self, game, mode_id, map_id, char_id):
        self.game = game
        gd = game.data
        self.mode_id = mode_id
        self.map_def = gd.maps[map_id]
        parts = build_participants(game, mode_id, char_id)
        diff = game.settings["ai_difficulty"]
        ally = {"easy": "normal", "normal": "normal", "hard": "hard", "expert": "expert"}[diff]
        self.world = World(gd, self.map_def, mode_id, parts, diff, seed=random.random(), ally_difficulty=ally)
        self.renderer = WorldRenderer(self.world, gd.themes, game.settings, game.i18n)
        self.hud = HUD(self.world, game.i18n, game.settings)
        self.paused = False
        self.acc = 0.0
        self.lmb = False
        self.rmb = False
        self.super_queued = False
        self.attack_queued = False
        self.auto_queued = False
        self.end_timer = None
        self.finished = False
        self.last_count = 4
        super().__init__(game)

    # ------------------------------------------------------------ ui
    def build(self):
        self.widgets = []
        self.pause_btn = self.add(Button(self.R(16, 14, 56, 56), "", self.toggle_pause, theme.PURPLE, icon=icons.pause,
                                         radius=14))
        self.pause_widgets = []
        if self.paused:
            cx = VW // 2 - 160
            labels = [("pause.resume", theme.GREEN, self.toggle_pause),
                      ("pause.settings", theme.BLUE, self.open_settings),
                      ("pause.quit", theme.RED, self.confirm_quit)]
            for i, (k, c, cb) in enumerate(labels):
                self.pause_widgets.append(self.add(Button((cx, 260 + i * 92, 320, 72), self.tr(k), cb, c, 28)))

    def toggle_pause(self):
        if self.world.state == "over":
            return
        self.paused = not self.paused
        self.lmb = self.rmb = False
        self.build()

    def open_settings(self):
        from ilbrawl.menus.settings_menu import SettingsScene
        self.game.push(SettingsScene(self.game, in_battle=True))

    def on_resume(self):
        self.renderer.settings = self.game.settings
        self.build()
        self.game.audio.play_music("battle")

    def confirm_quit(self):
        self.open_dialog(Dialog(self.tr("pause.quit_title"), self.tr("pause.quit_body"),
                                [(self.tr("common.cancel"), theme.GREY, None),
                                 (self.tr("pause.quit"), theme.RED, self.forfeit)]))

    def forfeit(self):
        w = self.world
        w.state = "over"
        if w.result is None:
            teams = sorted({b.team for b in w.brawlers})
            ranks = None
            if self.mode_id == "solo_survival":
                alive = len([b for b in w.brawlers if b.alive])
                ranks = {w.player.id: alive}
            w.result = {"winner": None, "outcome": {t: ("loss" if t == w.player.team else "win") for t in teams},
                        "ranks": ranks or {}}
        self.finish()

    # ------------------------------------------------------------ input
    def on_event(self, e):
        c = self.game.settings["controls"]
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.toggle_pause()
                return
            if self.paused:
                return
            if e.key == key_code(c["super"]):
                self.super_queued = True
            elif e.key == key_code(c["attack"]):
                self.attack_queued = True
            elif e.key == key_code(c["autoaim"]):
                self.auto_queued = True
        elif e.type == pygame.MOUSEBUTTONDOWN and not self.paused:
            if e.button == 1:
                self.lmb = True
                self.attack_queued = True
            elif e.button == 3:
                self.rmb = True
        elif e.type == pygame.MOUSEBUTTONUP:
            if e.button == 1:
                self.lmb = False
            elif e.button == 3:
                if self.rmb and not self.paused:
                    self.super_queued = True
                self.rmb = False

    def _intent(self):
        it = Intent()
        keys = pygame.key.get_pressed()
        c = self.game.settings["controls"]

        def down(name):
            k = key_code(c[name])
            return bool(k is not None and keys[k])

        it.mx = (1 if down("right") else 0) - (1 if down("left") else 0)
        it.my = (1 if down("down") else 0) - (1 if down("up") else 0)
        if not (it.mx or it.my):
            # arrow keys always work as a fallback
            it.mx = (1 if keys[pygame.K_RIGHT] else 0) - (1 if keys[pygame.K_LEFT] else 0)
            it.my = (1 if keys[pygame.K_DOWN] else 0) - (1 if keys[pygame.K_UP] else 0)
        ax, ay = self.renderer.screen_to_world(*self.game.mouse_pos)
        it.ax, it.ay = ax, ay
        if self.attack_queued or self.lmb or down("attack"):
            it.attack = True
        if self.auto_queued:
            it.attack = True
            it.autoaim = True
        if self.super_queued:
            it.super = True
        self.attack_queued = self.super_queued = self.auto_queued = False
        return it

    # ------------------------------------------------------------ loop
    def update(self, dt):
        super().update(dt)
        w = self.world
        if self.paused or self.modal:
            return
        self.acc += dt
        steps = 0
        events = []
        while self.acc >= STEP and steps < 5:
            intent = self._intent() if (w.player and w.player.alive) else None
            w.update(STEP, intent)
            events.extend(w.pop_events())
            self.acc -= STEP
            steps += 1
        if steps == 5:
            self.acc = 0.0
        aim = self.renderer.screen_to_world(*self.game.mouse_pos)
        self.renderer.update(dt, events, aim)
        self.hud.on_events(events)
        self.hud.update(dt)
        self._sounds(events)
        if w.state == "countdown":
            n = int(math.ceil(w.countdown))
            if n != self.last_count and n > 0:
                self.last_count = n
                self.game.audio.play("countdown")
        if w.state == "over" and not self.finished:
            if self.end_timer is None:
                self.end_timer = 2.2
                res = w.build_result()
                self.game.audio.play("victory" if res["outcome"] == "win" else "defeat")
            self.end_timer -= dt
            if self.end_timer <= 0:
                self.finish()

    def _sounds(self, events):
        au = self.game.audio
        p = self.world.player
        for e in events:
            ev = e["ev"]
            if ev == "shot":
                who = e.get("who")
                vol = 1.0 if who is p else 0.45
                if not self._near(e):
                    continue
                au.play(e.get("sound", "shoot"), vol if not e.get("quiet") else 0.3)
            elif ev == "damage":
                if e["target"] is p:
                    au.play("hurt", 0.8, 0.08)
                elif e.get("src") is p:
                    au.play("hit", 0.7, 0.06)
            elif ev == "melee" and self._near(e):
                au.play("melee", 0.8)
            elif ev == "heal" and e["target"] is p and e["amount"] > 50:
                au.play("heal", 0.5, 0.4)
            elif ev == "super_ready":
                if e["who"] is p:
                    au.play("super_ready")
            elif ev == "pickup":
                if e.get("who") is p or self._near(e):
                    au.play("gem" if e["item"] != "orb" else "reward", 0.8)
            else:
                snd = SOUND_FOR_EVENT.get(ev)
                if snd and ("x" not in e or self._near(e)):
                    au.play(snd, 0.8)

    def _near(self, e):
        if "x" not in e:
            return True
        cx, cy = self.renderer.cam_x, self.renderer.cam_y
        return abs(e["x"] - cx) < VW * 0.7 and abs(e["y"] - cy) < VH * 0.7

    def finish(self):
        if self.finished:
            return
        self.finished = True
        result = self.world.build_result()
        summary = self.game.profile.apply_match_result(result)
        from ilbrawl.menus.results import ResultsScene
        self.game.replace(ResultsScene(self.game, result, summary))

    # ------------------------------------------------------------ draw
    def draw(self, surf):
        p = self.world.player
        aim = self.renderer.screen_to_world(*self.game.mouse_pos)
        aiming_super = self.rmb and p is not None and p.super_ready
        self.renderer.draw(surf, aim, aiming_super, self.lmb)
        self.hud.draw(surf, aiming_super)
        if self.paused:
            shade = pygame.Surface((VW, VH), pygame.SRCALPHA)
            shade.fill((10, 6, 30, 170))
            surf.blit(shade, (0, 0))
            text.draw(surf, self.tr("pause.title"), (VW // 2, 170), 56, theme.YELLOW, "center", "middle", outline=4)
        for w in self.widgets:
            w.draw(surf)
        if self.modal:
            self.modal.draw(surf)
        if not self.paused and p is not None and p.alive:
            # crosshair
            mx, my = self.game.mouse_pos
            pygame.draw.circle(surf, theme.INK, (mx, my), 11, 4)
            pygame.draw.circle(surf, theme.WHITE, (mx, my), 10, 2)
            pygame.draw.circle(surf, theme.WHITE, (mx, my), 2)
