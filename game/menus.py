"""Menu scenes: loading, main menu, characters, shop, upgrades, missions,
events, achievements and settings."""
import math
import random

import pygame

from . import settings as S
from .camera import Camera
from .characters import draw_runner, build_look, draw_board
from .collectibles import CollectibleRenderer
from .render import Renderer
from .scenery import zone_colors
from .shop import SHOP_TABS
from .ui import (Button, Slider, Scroller, panel, progress_bar, blit_center, gradient_rect, currency_bar,
                 draw_wrapped, wrap_text)
from .utils import fmt_int, shade, lerp_color, clamp, WARNINGS
from .world import World

KEY_ACTIONS = [("left", "Move left"), ("right", "Move right"), ("jump", "Jump"), ("slide", "Slide / Roll"),
               ("board", "Use board"), ("pause", "Pause")]


class Scene:
    title = ""

    def __init__(self, app):
        self.app = app
        self.buttons = []
        self.widgets = []
        self.t = 0.0

    def enter(self, **kw):
        pass

    def handle(self, event):
        for w in self.buttons + self.widgets:
            if w.handle(event, self.app):
                return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.back()
            return True
        return False

    def back(self):
        self.app.audio.play("back")
        self.app.change_scene("menu")

    def update(self, dt):
        self.t += dt
        for w in self.buttons + self.widgets:
            w.update(dt)

    def draw_background(self, surf):
        surf.blit(gradient_rect((S.SCREEN_W, S.SCREEN_H), (28, 34, 72), (10, 12, 26)), (0, 0))
        # animated diagonal stripes for a "mobile game" feel
        off = (self.t * 30) % 80
        for i in range(-2, 22):
            x = i * 80 + off
            pygame.draw.polygon(surf, (24, 30, 64), [(x, 0), (x + 30, 0), (x - 170, S.SCREEN_H), (x - 200, S.SCREEN_H)])

    def draw_header(self, surf, title):
        a = self.app.assets
        pygame.draw.rect(surf, (12, 14, 32), (0, 0, S.SCREEN_W, 84))
        pygame.draw.line(surf, S.UI_ACCENT, (0, 84), (S.SCREEN_W, 84), 3)
        surf.blit(a.text(title, 44, (255, 255, 255), shadow=True), (110, 16))
        currency_bar(surf, a, S.SCREEN_W - 20, 20, self.app.economy.coins, self.app.economy.gems)
        back = getattr(self, "_back_btn", None)
        if back is not None and back in self.buttons:
            back.draw(surf, a)

    def back_button(self):
        self._back_btn = Button((20, 14, 74, 56), "", self.back, "dark", icon="back", sound="back")
        return self._back_btn

    def draw_buttons(self, surf):
        for b in self.buttons:
            b.draw(surf, self.app.assets)
        for w in self.widgets:
            w.draw(surf, self.app.assets)


# ---------------------------------------------------------------------------
class LoadingScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        specs = [("menu", {"tempo": 100, "root": 57, "scale": "major", "progression": [1, 6, 4, 5],
                           "style": "chill", "lead": "triangle"})]
        specs += [(z["id"], z["music"]) for z in app.data.zones]
        self.steps = app.audio.load_steps(specs)
        self.total = len(specs) + 1
        self.done = 0
        self.label = "Starting"
        self.finished = False

    def update(self, dt):
        super().update(dt)
        if self.finished:
            return
        try:
            self.label = next(self.steps)
            self.done += 1
        except StopIteration:
            self.finished = True
            self.app.change_scene("menu")

    def draw(self, surf):
        self.draw_background(surf)
        a = self.app.assets
        blit_center(surf, a.text("SUBWAY SURFER", 76, S.UI_ACCENT, shadow=True), (S.SCREEN_W // 2, 260))
        blit_center(surf, a.text("CITY", 96, (255, 255, 255), shadow=True), (S.SCREEN_W // 2, 345))
        progress_bar(surf, (S.SCREEN_W // 2 - 260, 450, 520, 22), self.done / max(1, self.total), S.UI_ACCENT_2)
        blit_center(surf, a.text(f"Building the city... {self.label}", 22, S.UI_TEXT_DIM), (S.SCREEN_W // 2, 500))


# ---------------------------------------------------------------------------
class MainMenu(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.world = None
        self.cam = Camera()
        self.renderer = Renderer(app.screen, self.cam)
        self.crender = CollectibleRenderer(app.assets, app.data)
        self.cam_z = 0.0
        self.popup = None
        self.popup_buttons = []
        self.wave_timer = 2.0

    def enter(self, **kw):
        app = self.app
        app.audio.play_music("menu")
        q = app.settings.quality
        self.world = World(app.data, q, app.progression.unlocked_zone_ids(), app.assets, event=app.events.active(),
                           seed=random.randrange(1 << 30), spawn_obstacles=False, sprites=app.sprites)
        self.cam_z = 0.0
        self._build()
        if app.daily.available():
            self._open_daily()
        for w in WARNINGS[:3]:
            app.toasts.push(w, "gear", S.UI_BAD, 6.0)
        del WARNINGS[:]

    def _build(self):
        app = self.app
        go = app.change_scene
        x0 = 60
        self.buttons = [
            Button((x0, 250, 380, 96), "PLAY", lambda: go("game"), "primary", icon="play", size=48),
        ]
        items = [("CHARACTERS", "characters", "character"), ("SHOP", "shop", "cart"), ("MISSIONS", "missions", "mission"),
                 ("UPGRADES", "upgrades", "upgrade"), ("EVENTS", "events", "event"), ("ACHIEVEMENTS", "achievements", "trophy"),
                 ("SETTINGS", "settings", "gear")]
        badges = {"events": app.events.claimable_count() or None}
        for i, (label, scene, icon) in enumerate(items):
            col, row = i % 2, i // 2
            w = 186
            b = Button((x0 + col * (w + 8), 362 + row * 70, w, 60), label, (lambda s=scene: go(s)), "dark", icon=icon,
                       size=20, badge=badges.get(scene))
            self.buttons.append(b)
        self.buttons.append(Button((S.SCREEN_W - 90, 96, 70, 60), "", self._open_daily, "ghost", icon="calendar",
                                   badge="!" if app.daily.available() else None))

    def _open_daily(self):
        self.popup = "daily"
        cx = S.SCREEN_W // 2
        avail = self.app.daily.available()
        self.popup_buttons = [
            Button((cx - 150, 560, 300, 70), "CLAIM" if avail else "COME BACK TOMORROW", self._claim_daily,
                   "good" if avail else "dark", size=28 if avail else 20, enabled=avail),
            Button((cx + 330, 140, 56, 56), "X", self._close_popup, "danger", size=26, sound="back"),
        ]

    def _close_popup(self):
        self.popup = None
        self.popup_buttons = []
        self._build()

    def _claim_daily(self):
        res = self.app.daily.claim()
        if res:
            day, reward, lines = res
            self.app.audio.play("unlock")
            self.app.toasts.push(f"Day {day} reward: " + ", ".join(lines), "calendar", S.UI_GOOD, 4)
        self._close_popup()

    def handle(self, event):
        if self.popup:
            for b in self.popup_buttons:
                if b.handle(event, self.app):
                    return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._close_popup()
            return True
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.app.audio.play("button")
                self.app.change_scene("game")
                return True
            if event.key == pygame.K_ESCAPE:
                self.app.quit()
                return True
        for b in self.buttons:
            if b.handle(event, self.app):
                return True
        return False

    def update(self, dt):
        super().update(dt)
        for b in self.popup_buttons:
            b.update(dt)
        self.cam_z += dt * 11.0
        self.cam.x = math.sin(self.t * 0.2) * 1.5 + 1.0
        self.cam.y = S.CAMERA_HEIGHT + 0.5
        self.cam.z = self.cam_z
        self.world.update(dt, self.cam_z + 6, self.cam_z, self.app.settings.quality["draw_distance"])
        self.wave_timer -= dt
        if self.wave_timer < -2.5:
            self.wave_timer = random.uniform(4, 7)

    def draw(self, surf):
        app = self.app
        a = app.assets
        r = self.renderer
        r.surface = surf
        za, zb, t = self.world.schedule.zone_at(self.cam.z + 30)
        col = zone_colors(za, zb, t)
        q = app.settings.quality
        r.begin(col["fog"], q["draw_distance"], q.get("glow", True))
        app.sky.draw(surf, self.cam, za, zb, t)
        self.world.draw_ground(r, self.cam)
        self.world.draw(r, self.crender, self.cam.z)
        r.flush()
        ev = app.events.active()
        if ev:
            surf.fill(lerp_color((255, 255, 255), ev["theme"]["tint"], ev["theme"]["tint_strength"]), special_flags=pygame.BLEND_MULT)
        # darken left side for readability
        shade_l = gradient_rect((560, S.SCREEN_H), (10, 12, 30), (10, 12, 30))
        shade_l.set_alpha(150)
        surf.blit(shade_l, (0, 0))
        # title
        bob = math.sin(self.t * 2) * 4
        title = a.text("SUBWAY SURFER", 62, S.UI_ACCENT, shadow=True)
        title2 = a.text("CITY", 92, (255, 255, 255), shadow=True)
        surf.blit(title, (60, 40 + bob))
        surf.blit(title2, (60, 100 + bob))
        # level + currencies
        prog = app.progression
        lvl_rect = pygame.Rect(S.SCREEN_W - 560, 20, 200, 44)
        pygame.draw.rect(surf, (12, 14, 30), lvl_rect, border_radius=22)
        surf.blit(a.icon("star", 34, S.UI_ACCENT), (lvl_rect.x + 6, lvl_rect.y + 5))
        surf.blit(a.text(f"LV {prog.level}", 24, (255, 255, 255)), (lvl_rect.x + 46, lvl_rect.y + 4))
        progress_bar(surf, (lvl_rect.x + 46, lvl_rect.y + 30, 140, 8), prog.progress, S.UI_GOOD, radius=4)
        currency_bar(surf, a, S.SCREEN_W - 20, 20, app.economy.coins, app.economy.gems)
        # character preview
        look = build_look(app.data, app.save["character"], app.save["outfit"])
        pose = "wave" if self.wave_timer < 0 else "idle"
        cx, cy = 900, 600
        pygame.draw.ellipse(surf, (0, 0, 0), (cx - 110, cy - 18, 220, 36))
        board = app.data.item(app.save["board"])
        if board:
            draw_board(surf, cx - 150, cy - 30, 150, board)
        draw_runner(surf, cx, cy, 230, look, pose, 0, self.t, "front")
        ch = app.data.character(app.save["character"])
        name = a.text(ch["name"].upper(), 34, (255, 255, 255), shadow=True)
        blit_center(surf, name, (cx, cy + 40))
        emote = app.data.item(app.save["emote"])
        if emote and emote.get("text") and pose == "wave":
            txt = a.text(emote["text"], 26, (30, 30, 40))
            rect = pygame.Rect(0, 0, txt.get_width() + 24, txt.get_height() + 12)
            rect.midbottom = (cx + 120, cy - 440)
            pygame.draw.rect(surf, (255, 255, 255), rect, border_radius=14)
            blit_center(surf, txt, rect.center)
        # best score + event banner
        surf.blit(a.text(f"BEST  {fmt_int(app.save['best_score'])}", 24, S.UI_TEXT_DIM), (64, 212))
        if ev:
            br = pygame.Rect(S.SCREEN_W - 380, 170, 360, 60)
            pygame.draw.rect(surf, ev["theme"]["banner_2"], br, border_radius=16)
            pygame.draw.rect(surf, ev["theme"]["banner"], br, 3, border_radius=16)
            surf.blit(a.icon("token", 40, ev["currency"]["color"]), (br.x + 10, br.y + 10))
            surf.blit(a.text(ev["name"].upper(), 22, (255, 255, 255)), (br.x + 60, br.y + 8))
            surf.blit(a.text(f"{app.events.days_left(ev)} days left - tap EVENTS", 16, S.UI_TEXT_DIM), (br.x + 60, br.y + 34))
        self.draw_buttons(surf)
        if self.popup == "daily":
            self._draw_daily(surf)

    def _draw_daily(self, surf):
        a = self.app.assets
        layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        layer.fill((5, 6, 18, 180))
        surf.blit(layer, (0, 0))
        cx = S.SCREEN_W // 2
        panel(surf, (cx - 420, 120, 840, 540), S.UI_PANEL, radius=30, border=S.UI_ACCENT)
        blit_center(surf, a.text("DAILY REWARDS", 50, S.UI_ACCENT, shadow=True), (cx, 180))
        daily = self.app.daily
        today_day = daily.next_day() if daily.available() else int(self.app.save["daily_reward"].get("day", 1))
        claimed_today = not daily.available()
        for i in range(7):
            day = i + 1
            col = i % 4
            row = i // 4
            w, h = 180, 150
            x = cx - 390 + col * 196 + (98 if row == 1 else 0)
            y = 230 + row * 165
            rect = pygame.Rect(x, y, w, h)
            if day < today_day or (day == today_day and claimed_today):
                c, border = (40, 90, 60), S.UI_GOOD
            elif day == today_day:
                c, border = (90, 70, 20), S.UI_ACCENT
            else:
                c, border = (36, 42, 76), (70, 80, 120)
            pulse = 1 + (0.03 * math.sin(self.t * 6) if day == today_day and not claimed_today else 0)
            r2 = rect.inflate(int(w * (pulse - 1)), int(h * (pulse - 1)))
            panel(surf, r2, c, radius=16, border=border, shadow=False)
            blit_center(surf, a.text(f"DAY {day}", 22, (255, 255, 255)), (r2.centerx, r2.y + 20))
            reward = self.app.data.daily_rewards[i]
            icon = "gem" if reward.get("gems") else "coin" if reward.get("coins") else "board"
            blit_center(surf, a.icon(icon, 54), (r2.centerx, r2.y + 70))
            txt = self.app.economy.reward_text(reward)
            lines = wrap_text(a, txt, 16, w - 16)
            for k, ln in enumerate(lines[:2]):
                blit_center(surf, a.text(ln, 16, (255, 255, 255)), (r2.centerx, r2.y + 112 + k * 18))
            if day < today_day or (day == today_day and claimed_today):
                blit_center(surf, a.text("CLAIMED", 18, S.UI_GOOD), (r2.centerx, r2.y + 44))
        for b in self.popup_buttons:
            b.draw(surf, a)


# ---------------------------------------------------------------------------
class CharactersScene(Scene):
    def enter(self, **kw):
        ids = [c["id"] for c in self.app.data.characters]
        cur = self.app.save["character"]
        self.index = ids.index(cur) if cur in ids else 0
        self._build()

    def _build(self):
        self.buttons = [self.back_button(),
                        Button((50, 340, 80, 80), "<", lambda: self._move(-1), "dark", size=40),
                        Button((600, 340, 80, 80), ">", lambda: self._move(1), "dark", size=40)]
        ch = self.app.data.characters[self.index]
        eco = self.app.economy
        item = self.app.data.item(ch["id"])
        if eco.owned("characters", ch["id"]):
            if eco.equipped("characters") == ch["id"]:
                b = Button((S.SCREEN_W // 2 + 140, 590, 300, 76), "SELECTED", None, "dark", enabled=False)
            else:
                b = Button((S.SCREEN_W // 2 + 140, 590, 300, 76), "SELECT", self._select, "good")
        elif eco.item_locked_by_level(item):
            b = Button((S.SCREEN_W // 2 + 140, 590, 300, 76), f"LEVEL {ch['unlock_level']}", None, "dark", icon="lock", enabled=False)
        else:
            icon = "gem" if ch["currency"] == "gems" else "coin"
            b = Button((S.SCREEN_W // 2 + 140, 590, 300, 76), fmt_int(ch["price"]), self._buy, "primary", icon=icon,
                       enabled=eco.can_afford(ch["price"], ch["currency"]))
        self.buttons.append(b)

    def _move(self, d):
        self.index = (self.index + d) % len(self.app.data.characters)
        self._build()

    def _select(self):
        ch = self.app.data.characters[self.index]
        self.app.economy.equip("characters", ch["id"])
        self.app.save.save()
        self.app.audio.play("unlock")
        self._build()

    def _buy(self):
        ch = self.app.data.characters[self.index]
        ok, msg = self.app.economy.purchase(self.app.data.item(ch["id"]))
        if ok:
            self.app.economy.equip("characters", ch["id"])
            self.app.save.save()
            self.app.audio.play("buy")
            self.app.achievements.check()
        self.app.toasts.push(msg, "character", S.UI_GOOD if ok else S.UI_BAD)
        self._build()

    def handle(self, event):
        if super().handle(event):
            return True
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_LEFT, pygame.K_a):
                self._move(-1)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self._move(1)
            elif event.key == pygame.K_RETURN:
                self._select() if self.app.economy.owned("characters", self.app.data.characters[self.index]["id"]) else self._buy()
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for i, rect in enumerate(self._thumb_rects()):
                if rect.collidepoint(event.pos):
                    self.index = i
                    self.app.audio.play("button")
                    self._build()
        return False

    def _thumb_rects(self):
        n = len(self.app.data.characters)
        size = 64
        total = n * (size + 10)
        x0 = S.SCREEN_W // 2 - total // 2
        return [pygame.Rect(x0 + i * (size + 10), 100, size, size) for i in range(n)]

    def draw(self, surf):
        self.draw_background(surf)
        a = self.app.assets
        app = self.app
        ch = app.data.characters[self.index]
        eco = app.economy
        for i, rect in enumerate(self._thumb_rects()):
            c = app.data.characters[i]
            sel = i == self.index
            pygame.draw.rect(surf, (60, 70, 120) if sel else (30, 36, 66), rect, border_radius=14)
            pygame.draw.rect(surf, S.UI_ACCENT if sel else (70, 80, 120), rect, 3, border_radius=14)
            draw_runner(surf, rect.centerx, rect.bottom - 4, 32, build_look(app.data, c["id"]), "idle", 0, 0, "front")
            if not eco.owned("characters", c["id"]):
                surf.blit(a.icon("lock", 22), (rect.right - 24, rect.bottom - 24))
        # preview
        cx = 365
        pygame.draw.ellipse(surf, (0, 0, 0), (cx - 110, 610, 220, 36))
        outfit = app.save["outfit"] if eco.owned("characters", ch["id"]) else None
        look = build_look(app.data, ch["id"], outfit)
        draw_runner(surf, cx, 628, 240, look, "cheer" if eco.equipped("characters") == ch["id"] else "idle", 0, self.t,
                    "front")
        # info panel
        px = S.SCREEN_W // 2 + 60
        panel(surf, (px, 190, 520, 380), S.UI_PANEL, radius=24)
        surf.blit(a.text(ch["name"].upper(), 52, S.UI_ACCENT, shadow=True), (px + 30, 210))
        draw_wrapped(surf, a, ch.get("description", ""), 22, S.UI_TEXT, (px + 30, 280, 460, 80))
        pygame.draw.rect(surf, (30, 36, 70), (px + 24, 360, 472, 110), border_radius=16)
        surf.blit(a.text("SPECIAL ABILITY", 20, S.UI_ACCENT_2), (px + 40, 372))
        draw_wrapped(surf, a, ch["ability"].get("desc", "-"), 26, (255, 255, 255), (px + 40, 402, 440, 60))
        status = ("Owned" if eco.owned("characters", ch["id"]) else
                  f"Unlocks at level {ch['unlock_level']}" if eco.item_locked_by_level(app.data.item(ch["id"])) else
                  f"Price: {fmt_int(ch['price'])} {ch['currency']}")
        surf.blit(a.text(status, 22, S.UI_TEXT_DIM), (px + 30, 500))
        self.draw_buttons(surf)
        self.draw_header(surf, "CHARACTERS")


# ---------------------------------------------------------------------------
class ShopScene(Scene):
    CARD_W, CARD_H = 380, 170

    def enter(self, **kw):
        self.tab = kw.get("tab", getattr(self, "tab", "characters"))
        self.scroller = Scroller((40, 170, S.SCREEN_W - 80, S.SCREEN_H - 190))
        self._build()

    def _build(self):
        self.buttons = [self.back_button()]
        x = 40
        for key, label in SHOP_TABS:
            w = 186
            self.buttons.append(Button((x, 100, w, 54), label, (lambda k=key: self._set_tab(k)),
                                       "primary" if key == self.tab else "ghost", size=20))
            x += w + 14
        self.entries = self.app.shop.entries(self.tab)
        rows = (len(self.entries) + 2) // 3
        self.scroller.content_h = rows * (self.CARD_H + 16)
        self.scroller.offset = clamp(self.scroller.offset, 0, self.scroller.max_offset)

    def _set_tab(self, key):
        self.tab = key
        self.scroller.offset = 0
        self._build()

    def _card_rect(self, i):
        col, row = i % 3, i // 3
        return pygame.Rect(self.scroller.rect.x + col * (self.CARD_W + 20),
                           self.scroller.rect.y + row * (self.CARD_H + 16) - int(self.scroller.offset),
                           self.CARD_W, self.CARD_H)

    def _action_rect(self, card):
        return pygame.Rect(card.right - 170, card.bottom - 58, 156, 46)

    def handle(self, event):
        if super().handle(event):
            return True
        if self.scroller.handle(event):
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.scroller.rect.collidepoint(event.pos):
            for i, e in enumerate(self.entries):
                card = self._card_rect(i)
                if self._action_rect(card).collidepoint(event.pos) and e.action:
                    ok, msg = self.app.shop.act(e)
                    self.app.audio.play("buy" if ok else "error")
                    self.app.toasts.push(msg, e.icon, S.UI_GOOD if ok else S.UI_BAD)
                    if ok:
                        self.app.achievements.check()
                    self._build()
                    return True
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            keys = [k for k, _ in SHOP_TABS]
            i = keys.index(self.tab) + (1 if event.key == pygame.K_RIGHT else -1)
            self._set_tab(keys[i % len(keys)])
        return False

    def draw(self, surf):
        self.draw_background(surf)
        a = self.app.assets
        eco = self.app.economy
        surf.set_clip(self.scroller.rect.inflate(10, 6))
        mouse = pygame.mouse.get_pos()
        for i, e in enumerate(self.entries):
            card = self._card_rect(i)
            if card.bottom < self.scroller.rect.y - 10 or card.y > self.scroller.rect.bottom:
                continue
            border = S.UI_GOOD if e.equipped else S.UI_ACCENT if card.collidepoint(mouse) else (70, 80, 120)
            panel(surf, card, (36, 42, 78), radius=18, border=border, shadow=False)
            ib = pygame.Rect(card.x + 14, card.y + 14, 96, 96)
            pygame.draw.rect(surf, (24, 28, 54), ib, border_radius=16)
            self._draw_preview(surf, e, ib)
            surf.blit(a.text(e.name, 24, (255, 255, 255)), (card.x + 124, card.y + 14))
            draw_wrapped(surf, a, e.desc, 15, S.UI_TEXT_DIM, (card.x + 124, card.y + 46, card.w - 136, 60), bold=False,
                         max_lines=3)
            scol = S.UI_GOOD if e.equipped or e.owned else S.UI_TEXT_DIM
            surf.blit(a.text(e.status or "", 18, scol), (card.x + 16, card.bottom - 46))
            ar = self._action_rect(card)
            if e.action in ("buy", "upgrade"):
                afford = eco.can_afford(e.price, e.currency)
                base = S.UI_ACCENT if afford else (90, 90, 110)
                pygame.draw.rect(surf, shade(base, 0.6), ar.move(0, 4), border_radius=16)
                pygame.draw.rect(surf, base, ar, border_radius=16)
                ic = a.icon("gem" if e.currency == "gems" else "coin", 30)
                t = a.text(fmt_int(e.price), 22, (40, 30, 10) if afford else (200, 200, 210))
                surf.blit(ic, (ar.x + 10, ar.centery - 15))
                surf.blit(t, (ar.x + 46, ar.centery - t.get_height() // 2))
            elif e.action == "equip":
                pygame.draw.rect(surf, (30, 110, 70), ar.move(0, 4), border_radius=16)
                pygame.draw.rect(surf, S.UI_GOOD, ar, border_radius=16)
                blit_center(surf, a.text("EQUIP", 22, (255, 255, 255)), ar.center)
        surf.set_clip(None)
        self.scroller.draw_bar(surf)
        self.draw_buttons(surf)
        self.draw_header(surf, "SHOP")

    def _draw_preview(self, surf, e, rect):
        a = self.app.assets
        if e.category == "characters":
            draw_runner(surf, rect.centerx, rect.bottom - 6, 48, build_look(self.app.data, e.id), "idle", 0, self.t, "front")
            return
        if e.category == "boards":
            draw_board(surf, rect.centerx, rect.centery, 110, e.item)
            return
        blit_center(surf, a.icon(e.icon, 72, e.color), rect.center)


# ---------------------------------------------------------------------------
class UpgradesScene(Scene):
    def enter(self, **kw):
        self._build()

    def _build(self):
        self.buttons = [self.back_button()]
        self.rows = [p for p in self.app.data.powerups if p.get("upgradeable")]
        for i, pu in enumerate(self.rows):
            cost = self.app.economy.upgrade_cost(pu["id"])
            y = 110 + i * 116
            if cost is None:
                b = Button((S.SCREEN_W - 300, y + 24, 240, 64), "MAXED", None, "dark", enabled=False)
            else:
                b = Button((S.SCREEN_W - 300, y + 24, 240, 64), fmt_int(cost), (lambda p=pu["id"]: self._upgrade(p)),
                           "primary", icon="coin", enabled=self.app.economy.can_afford(cost))
            self.buttons.append(b)

    def _upgrade(self, pid):
        ok, msg = self.app.economy.buy_upgrade(pid)
        self.app.audio.play("unlock" if ok else "error")
        self.app.toasts.push(msg, "upgrade", S.UI_GOOD if ok else S.UI_BAD)
        self._build()

    def draw(self, surf):
        self.draw_background(surf)
        a = self.app.assets
        eco = self.app.economy
        for i, pu in enumerate(self.rows):
            y = 110 + i * 116
            panel(surf, (40, y, S.SCREEN_W - 80, 106), (36, 42, 78), radius=20)
            pygame.draw.rect(surf, (24, 28, 54), (56, y + 10, 86, 86), border_radius=16)
            blit_center(surf, a.icon(pu["icon"], 66, pu["color"]), (99, y + 53))
            surf.blit(a.text(pu["name"], 30, (255, 255, 255)), (160, y + 12))
            lvl = eco.upgrade_level(pu["id"])
            durs = pu["durations"]
            cur = durs[min(lvl, len(durs) - 1)]
            nxt = durs[min(lvl + 1, len(durs) - 1)]
            info = f"{pu['desc']}  Duration: {cur:g}s" + (f"  ->  {nxt:g}s" if lvl + 1 < len(durs) else "")
            surf.blit(a.text(info, 20, S.UI_TEXT_DIM), (160, y + 50))
            max_lvl = len(durs)
            for k in range(max_lvl):
                r = pygame.Rect(160 + k * 52, y + 78, 44, 14)
                pygame.draw.rect(surf, pu["color"] if k <= lvl else (30, 34, 60), r, border_radius=7)
            surf.blit(a.text(f"LV {lvl + 1}", 22, pu["color"]), (160 + max_lvl * 52 + 10, y + 72))
        self.draw_buttons(surf)
        self.draw_header(surf, "UPGRADES")


# ---------------------------------------------------------------------------
class MissionsScene(Scene):
    def enter(self, **kw):
        self.tab = "regular"
        self.app.missions.ensure_daily()
        self._build()

    def _build(self):
        self.buttons = [self.back_button()]
        tabs = [("regular", "MISSIONS"), ("daily", "DAILY"), ("event", "EVENT")]
        for i, (k, label) in enumerate(tabs):
            self.buttons.append(Button((40 + i * 200, 100, 186, 54), label, (lambda key=k: self._set(key)),
                                       "primary" if k == self.tab else "ghost", size=22))

    def _set(self, k):
        self.tab = k
        self._build()

    def draw(self, surf):
        self.draw_background(surf)
        a = self.app.assets
        mm = self.app.missions
        if self.tab == "regular":
            missions = mm.regular_active()
            sub = f"Completed: {mm.regular_done_count()} / {len(self.app.data.missions_regular)}"
        elif self.tab == "daily":
            missions = mm.daily()
            sub = "New daily missions every day!"
        else:
            missions = mm.event_missions()
            ev = self.app.events.active()
            sub = f"{ev['name']} event missions" if ev else "No event is running right now"
        surf.blit(a.text(sub, 22, S.UI_TEXT_DIM), (660, 116))
        y = 176
        for m in missions:
            done = mm.is_completed(m)
            prog = mm.progress(m)
            panel(surf, (40, y, 760, 110), (36, 42, 78), radius=20, border=S.UI_GOOD if done else None)
            blit_center(surf, a.icon("mission", 56, S.UI_GOOD if done else S.UI_ACCENT), (90, y + 55))
            surf.blit(a.text(m.desc, 26, (255, 255, 255)), (136, y + 14))
            mode = "in one run" if m.mode == "run" else "total"
            progress_bar(surf, (136, y + 56, 440, 18), 1.0 if done else prog / m.target, S.UI_GOOD if done else S.UI_ACCENT_2)
            ptxt = "DONE!" if done else f"{fmt_int(min(prog, m.target))} / {fmt_int(m.target)} ({mode})"
            surf.blit(a.text(ptxt, 18, S.UI_TEXT_DIM), (136, y + 80))
            rw = a.text(self.app.economy.reward_text(m.reward), 20, S.UI_ACCENT)
            surf.blit(rw, (790 - rw.get_width() - 10, y + 56))
            y += 122
        if not missions:
            blit_center(surf, a.text("Nothing here yet - keep running!", 28, S.UI_TEXT_DIM), (420, 360))
        # level panel
        prog = self.app.progression
        panel(surf, (830, 176, 410, 500), S.UI_PANEL, radius=24)
        surf.blit(a.text(f"LEVEL {prog.level}", 40, S.UI_ACCENT, shadow=True), (856, 196))
        progress_bar(surf, (856, 252, 360, 20), prog.progress, S.UI_GOOD)
        xp_txt = "MAX LEVEL" if prog.level >= S.MAX_LEVEL else f"{fmt_int(prog.xp)} / {fmt_int(prog.xp_needed)} XP"
        surf.blit(a.text(xp_txt, 20, S.UI_TEXT_DIM), (856, 280))
        surf.blit(a.text("COMING UP", 22, S.UI_ACCENT_2), (856, 320))
        yy = 352
        for lvl, things in prog.upcoming_unlocks(4):
            surf.blit(a.text(f"Lv {lvl}", 22, (255, 255, 255)), (856, yy))
            for t in things[:2]:
                surf.blit(a.text(t if len(t) < 34 else t[:32] + "..", 17, S.UI_TEXT_DIM), (930, yy + 3))
                yy += 22
            yy += 12
        self.draw_buttons(surf)
        self.draw_header(surf, "MISSIONS")


# ---------------------------------------------------------------------------
class EventsScene(Scene):
    def enter(self, **kw):
        self._build()

    def _build(self):
        self.buttons = [self.back_button()]
        ev = self.app.events.active()
        self.event = ev
        if ev:
            n = len(ev["rewards"])
            for i in range(n):
                x, y = self._node_pos(i, n)
                st = self.app.events.reward_status(ev, i)
                if st == "ready":
                    self.buttons.append(Button((x - 60, y + 74, 120, 44), "CLAIM", (lambda k=i: self._claim(k)), "good", size=20))

    def _node_pos(self, i, n):
        x0, x1 = 120, S.SCREEN_W - 120
        return int(x0 + (x1 - x0) * (i / max(1, n - 1))), 330

    def _claim(self, i):
        lines = self.app.events.claim(self.event, i)
        if lines:
            self.app.audio.play("unlock")
            self.app.toasts.push("Event reward: " + ", ".join(lines), "event", S.UI_GOOD, 4)
        self._build()

    def draw(self, surf):
        self.draw_background(surf)
        a = self.app.assets
        ev = self.event
        em = self.app.events
        if ev:
            th = ev["theme"]
            banner = pygame.Rect(40, 100, S.SCREEN_W - 80, 130)
            surf.blit(gradient_rect(banner.size, th["banner"], th["banner_2"], 24), banner.topleft)
            pygame.draw.rect(surf, (255, 255, 255), banner, 3, border_radius=24)
            surf.blit(a.text(ev["name"].upper(), 48, (255, 255, 255), shadow=True), (70, 112))
            draw_wrapped(surf, a, ev["desc"], 20, (255, 255, 255), (72, 170, 760, 50))
            tok = em.tokens(ev)
            surf.blit(a.icon("token", 56, ev["currency"]["color"]), (S.SCREEN_W - 330, 120))
            surf.blit(a.text(f"{fmt_int(tok)}", 44, (255, 255, 255), shadow=True), (S.SCREEN_W - 266, 120))
            surf.blit(a.text(ev["currency"]["name"], 20, (255, 255, 255)), (S.SCREEN_W - 266, 170))
            surf.blit(a.text(f"{em.days_left(ev)} days left", 20, (255, 255, 255)), (S.SCREEN_W - 330, 196))
            # reward track
            n = len(ev["rewards"])
            pts = [self._node_pos(i, n) for i in range(n)]
            if n > 1:
                pygame.draw.line(surf, (60, 66, 100), pts[0], pts[-1], 10)
                frac_x = pts[0][0]
                for i, rw in enumerate(ev["rewards"]):
                    if tok >= rw["tokens"]:
                        frac_x = pts[i][0]
                pygame.draw.line(surf, ev["currency"]["color"], pts[0], (frac_x, pts[0][1]), 10)
            for i, rw in enumerate(ev["rewards"]):
                x, y = pts[i]
                st = em.reward_status(ev, i)
                col = S.UI_GOOD if st == "claimed" else ev["currency"]["color"] if st == "ready" else (80, 86, 120)
                pygame.draw.circle(surf, (20, 22, 40), (x, y), 44)
                pygame.draw.circle(surf, col, (x, y), 44, 5)
                item = self.app.data.item(rw["reward"].get("item", "")) if rw["reward"].get("item") else None
                icon = "gift" if not item else {"boards": "board", "outfits": "outfit", "trails": "trail",
                                                 "emotes": "emote", "effects": "effect"}.get(item["category"], "star")
                if icon == "gift":
                    icon = "gem" if rw["reward"].get("gems") else "coin"
                blit_center(surf, a.icon(icon, 50), (x, y))
                blit_center(surf, a.text(f"{rw['tokens']}", 20, (255, 255, 255)), (x, y - 62))
                label = self.app.economy.reward_text(rw["reward"])
                blit_center(surf, a.text(label if len(label) < 24 else label[:22] + "..", 15, S.UI_TEXT_DIM), (x, y + 58))
                if st == "claimed":
                    blit_center(surf, a.text("CLAIMED", 18, S.UI_GOOD), (x, y + 92))
            # event missions
            surf.blit(a.text("EVENT MISSIONS", 26, S.UI_ACCENT), (40, 470))
            y = 506
            mm = self.app.missions
            for m in mm.event_missions():
                done = mm.is_completed(m)
                panel(surf, (40, y, 600, 58), (36, 42, 78), radius=14, shadow=False, border=S.UI_GOOD if done else None)
                surf.blit(a.text(m.desc, 20, (255, 255, 255)), (60, y + 6))
                progress_bar(surf, (60, y + 34, 360, 12), 1 if done else mm.progress(m) / m.target, S.UI_GOOD)
                rt = a.text(self.app.economy.reward_text(m.reward), 16, S.UI_ACCENT)
                surf.blit(rt, (440, y + 30))
                y += 66
        else:
            blit_center(surf, a.text("No event is running right now", 40, (255, 255, 255)), (S.SCREEN_W // 2, 200))
            blit_center(surf, a.text("Check back soon - the city always finds a reason to party!", 22, S.UI_TEXT_DIM),
                        (S.SCREEN_W // 2, 250))
        # upcoming
        x = 680
        surf.blit(a.text("UPCOMING EVENTS", 26, S.UI_ACCENT_2), (x, 470))
        y = 506
        for start, e in em.upcoming()[:3]:
            panel(surf, (x, y, 560, 58), (30, 34, 62), radius=14, shadow=False)
            surf.blit(a.text(e["name"], 22, (255, 255, 255)), (x + 20, y + 6))
            surf.blit(a.text(f"Starts {start.strftime('%b %d')}", 18, S.UI_TEXT_DIM), (x + 20, y + 32))
            y += 66
        self.draw_buttons(surf)
        self.draw_header(surf, "EVENTS")


# ---------------------------------------------------------------------------
class AchievementsScene(Scene):
    def enter(self, **kw):
        self.buttons = [self.back_button()]
        self.app.achievements.check()
        self.scroller = Scroller((40, 140, S.SCREEN_W - 80, S.SCREEN_H - 150))
        n = len(self.app.data.achievements)
        self.scroller.content_h = ((n + 1) // 2) * 112

    def handle(self, event):
        if super().handle(event):
            return True
        return self.scroller.handle(event)

    def draw(self, surf):
        self.draw_background(surf)
        a = self.app.assets
        ach = self.app.achievements
        done = sum(1 for x in self.app.data.achievements if ach.is_unlocked(x["id"]))
        surf.blit(a.text(f"Unlocked {done} / {len(self.app.data.achievements)}", 24, S.UI_TEXT_DIM), (44, 100))
        surf.set_clip(self.scroller.rect)
        for i, x in enumerate(self.app.data.achievements):
            col, row = i % 2, i // 2
            w = (self.scroller.rect.w - 20) // 2
            rect = pygame.Rect(self.scroller.rect.x + col * (w + 20), self.scroller.rect.y + row * 112 - int(self.scroller.offset), w, 100)
            if rect.bottom < 130 or rect.y > S.SCREEN_H:
                continue
            unlocked = ach.is_unlocked(x["id"])
            panel(surf, rect, (40, 70, 60) if unlocked else (36, 42, 78), radius=18, shadow=False,
                  border=S.UI_ACCENT if unlocked else None)
            blit_center(surf, a.icon(x.get("icon", "trophy"), 60, S.UI_ACCENT if unlocked else (110, 110, 140)),
                        (rect.x + 50, rect.centery))
            surf.blit(a.text(x["name"], 24, (255, 255, 255)), (rect.x + 96, rect.y + 10))
            surf.blit(a.text(x["desc"], 17, S.UI_TEXT_DIM, bold=False), (rect.x + 96, rect.y + 40))
            progress_bar(surf, (rect.x + 96, rect.y + 70, 260, 12), 1 if unlocked else ach.progress(x), S.UI_GOOD)
            rt = a.text(self.app.economy.reward_text(x["reward"]), 16, S.UI_ACCENT)
            surf.blit(rt, (rect.right - rt.get_width() - 16, rect.y + 66))
        surf.set_clip(None)
        self.scroller.draw_bar(surf)
        self.draw_buttons(surf)
        self.draw_header(surf, "ACHIEVEMENTS")


# ---------------------------------------------------------------------------
class SettingsScene(Scene):
    def enter(self, **kw):
        self.back_to = kw.get("back", "menu")
        self.capture = None
        self.confirm_reset = False
        self._build()

    def back(self):
        self.app.audio.play("back")
        self.app.settings.save()
        if self.back_to == "game":
            self.app.change_scene("game", resume=True)
        else:
            self.app.change_scene("menu")

    def _build(self):
        st = self.app.settings
        self.buttons = [self.back_button()]
        x = 380
        self.widgets = [
            Slider((x, 140, 340, 14), st["music_volume"], self._music),
            Slider((x, 200, 340, 14), st["sfx_volume"], self._sfx),
            Slider((x, 500, 340, 14), clamp((st["swipe_threshold"] - 15) / 85, 0, 1), self._swipe),
        ]
        q = st["graphics_quality"]
        for i, level in enumerate(("low", "medium", "high")):
            self.buttons.append(Button((x + i * 116, 240, 108, 50), level.upper(), (lambda l=level: self._quality(l)),
                                       "primary" if q == level else "ghost", size=20))
        self.buttons.append(Button((x, 310, 166, 50), "WINDOWED", lambda: self._fullscreen(False),
                                   "primary" if not st["fullscreen"] else "ghost", size=20))
        self.buttons.append(Button((x + 174, 310, 166, 50), "FULLSCREEN", lambda: self._fullscreen(True),
                                   "primary" if st["fullscreen"] else "ghost", size=20))
        self.buttons.append(Button((x, 380, 166, 50), "VSYNC ON" if st["vsync"] else "VSYNC OFF", self._vsync,
                                   "primary" if st["vsync"] else "ghost", size=20))
        self.buttons.append(Button((x + 174, 380, 166, 50), "FPS ON" if st["show_fps"] else "FPS OFF", self._fps,
                                   "primary" if st["show_fps"] else "ghost", size=20))
        # key bindings
        for i, (action, label) in enumerate(KEY_ACTIONS):
            keys = st["keys"].get(action, [])
            text = "PRESS A KEY..." if self.capture == action else " / ".join(k.upper() for k in keys[:3])
            self.buttons.append(Button((1000, 130 + i * 66, 240, 52), text, (lambda a=action: self._capture(a)),
                                       "secondary" if self.capture == action else "ghost", size=18))
        self.buttons.append(Button((870, 540, 370, 50), "RESET KEYS", self._reset_keys, "dark", size=20))
        self.buttons.append(Button((870, 606, 370, 56), "CONFIRM RESET?" if self.confirm_reset else "RESET PROGRESS",
                                   self._reset_progress, "danger", size=20))

    def _music(self, v):
        self.app.settings["music_volume"] = round(v, 2)
        self.app.audio.apply_volume()

    def _sfx(self, v):
        self.app.settings["sfx_volume"] = round(v, 2)

    def _swipe(self, v):
        self.app.settings["swipe_threshold"] = int(15 + v * 85)

    def _quality(self, level):
        self.app.settings["graphics_quality"] = level
        self._build()

    def _fullscreen(self, on):
        if self.app.settings["fullscreen"] != on:
            self.app.settings["fullscreen"] = on
            self.app.apply_display()
        self._build()

    def _vsync(self):
        self.app.settings["vsync"] = not self.app.settings["vsync"]
        self.app.toasts.push("VSync applies after restarting the game", "gear", S.UI_ACCENT_2)
        self._build()

    def _fps(self):
        self.app.settings["show_fps"] = not self.app.settings["show_fps"]
        self._build()

    def _capture(self, action):
        self.capture = action
        self._build()

    def _reset_keys(self):
        self.app.settings["keys"] = {k: list(v) for k, v in self.app.data.default_settings["keys"].items()}
        self.app.rebuild_keymap()
        self._build()

    def _reset_progress(self):
        if not self.confirm_reset:
            self.confirm_reset = True
            self._build()
            return
        self.app.reset_progress()
        self.confirm_reset = False
        self.app.toasts.push("Progress reset - a fresh start!", "retry", S.UI_BAD)
        self._build()

    def handle(self, event):
        if self.capture and event.type == pygame.KEYDOWN:
            name = pygame.key.name(event.key)
            if event.key != pygame.K_ESCAPE:
                keys = [name] + [k for k in self.app.settings["keys"].get(self.capture, []) if k != name][:1]
                # a key can only belong to one action
                for act, lst in self.app.settings["keys"].items():
                    if act != self.capture and name in lst:
                        lst.remove(name)
                self.app.settings["keys"][self.capture] = keys
                self.app.settings.mark_dirty()
                self.app.rebuild_keymap()
                self.app.audio.play("button")
            self.capture = None
            self._build()
            return True
        return super().handle(event)

    def draw(self, surf):
        self.draw_background(surf)
        a = self.app.assets
        st = self.app.settings
        panel(surf, (40, 100, 760, 590), S.UI_PANEL, radius=24)
        labels = [("Music Volume", 128, f"{int(st['music_volume'] * 100)}%"),
                  ("SFX Volume", 188, f"{int(st['sfx_volume'] * 100)}%"),
                  ("Graphics Quality", 250, ""), ("Display", 320, ""), ("Options", 390, ""),
                  ("Swipe Sensitivity", 488, f"{st['swipe_threshold']} px")]
        for text, y, val in labels:
            surf.blit(a.text(text, 26, (255, 255, 255)), (70, y))
            if val:
                surf.blit(a.text(val, 22, S.UI_TEXT_DIM), (740, y + 4))
        surf.blit(a.text("Touch / mouse: swipe to move, jump and slide.", 18, S.UI_TEXT_DIM), (70, 540))
        surf.blit(a.text("Double-tap to use a board. F3 toggles debug info.", 18, S.UI_TEXT_DIM), (70, 566))
        surf.blit(a.text(f"Version {S.VERSION}", 18, S.UI_TEXT_DIM), (70, 640))
        panel(surf, (830, 100, 430, 590), S.UI_PANEL, radius=24)
        surf.blit(a.text("CONTROLS", 26, S.UI_ACCENT), (856, 104))
        for i, (action, label) in enumerate(KEY_ACTIONS):
            surf.blit(a.text(label, 20, (255, 255, 255)), (856, 144 + i * 66))
        self.draw_buttons(surf)
        self.draw_header(surf, "SETTINGS")
