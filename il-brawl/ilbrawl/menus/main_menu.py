"""Main menu / lobby."""
import math

import pygame

from ilbrawl import config
from ilbrawl.characters import sprites
from ilbrawl.engine.scene import Scene, draw_currency_bar
from ilbrawl.progression import achievements, missions
from ilbrawl.ui import cosmetic_art, icons, logo, text, theme
from ilbrawl.ui.widgets import Button, Dialog, ProgressBar

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H


class MainMenuScene(Scene):
    def build(self):
        self.widgets = []
        p = self.game.profile
        left = [
            ("menu.shop", theme.ORANGE, icons.shop, self.open_shop, None),
            ("menu.missions", theme.GREEN, icons.missions, self.open_missions,
             lambda: missions.claimable_count(p) + achievements.claimable_count(p)),
            ("menu.trophy_road", theme.PURPLE, icons.trophy_road, self.open_road, lambda: len(p.claimable_road())),
            ("menu.daily_reward", theme.PINK, icons.gift, self.daily_reward, lambda: p.daily_reward_available()),
            ("menu.settings", (80, 88, 104), icons.settings, self.open_settings, None),
        ]
        for i, (k, col, ic, cb, badge) in enumerate(left):
            self.add(Button(self.R(24, 168 + i * 82, 230, 68), self.tr(k), cb, col, 21, icon=ic, badge=badge))
        # player card (opens profile)
        self.profile_btn = self.add(Button(self.R(20, 14, 340, 92), "", self.open_profile, (34, 40, 52), radius=18,
                                           sound="click"))
        self.profile_btn.draw = self._draw_profile_card
        # right side
        self.add(Button(self.R(VW - 300, 168, 276, 76), self.tr("menu.characters"), self.open_characters, theme.BLUE, 24,
                        icon=icons.characters))
        self.mode_btn = self.add(Button(self.R(VW - 300, 262, 276, 150), "", self.open_modes, (40, 48, 62), radius=18))
        self.mode_btn.draw = self._draw_mode_button
        self.add(Button(self.R(VW - 300, VH - 140, 276, 112), self.tr("menu.play"), self.play, theme.YELLOW, 48,
                        icon=icons.play, text_color=theme.WHITE))
        self.add(Button(self.R(24, VH - 84, 140, 60), self.tr("menu.quit"), self.ask_quit, theme.RED, 20))
        # clicking the hero opens the character screen
        self.hero_btn = self.add(Button((VW // 2 - 150, 200, 300, 330), "", self.open_characters, theme.BLUE, sound="click"))
        self.hero_btn.draw = lambda s: None

    # ------------------------------------------------------------ actions
    def open_shop(self):
        from ilbrawl.menus.shop_menu import ShopScene
        self.game.push(ShopScene(self.game))

    def open_missions(self):
        from ilbrawl.menus.missions_menu import MissionsScene
        self.game.push(MissionsScene(self.game))

    def open_road(self):
        from ilbrawl.menus.trophy_road import TrophyRoadScene
        self.game.push(TrophyRoadScene(self.game))

    def open_settings(self):
        from ilbrawl.menus.settings_menu import SettingsScene
        self.game.push(SettingsScene(self.game))

    def open_profile(self):
        from ilbrawl.menus.profile_menu import ProfileScene
        self.game.push(ProfileScene(self.game))

    def open_characters(self):
        from ilbrawl.menus.character_select import CharacterSelectScene
        self.game.push(CharacterSelectScene(self.game))

    def open_modes(self):
        from ilbrawl.menus.modes_menu import ModesScene
        self.game.push(ModesScene(self.game))

    def play(self):
        p = self.game.profile
        mode = p.data["selected_mode"]
        map_id = p.selected_map(mode)
        if map_id is None:
            self.game.toasts.push(self.tr("modes.no_maps"), theme.RED)
            return
        from ilbrawl.gameplay.battle_scene import BattleScene
        self.game.push(BattleScene(self.game, mode, map_id, p.data["selected_char"]))

    def daily_reward(self):
        p = self.game.profile
        if not p.daily_reward_available():
            self.open_dialog(Dialog(self.tr("daily.title"), self.tr("daily.come_back"),
                                    [(self.tr("common.ok"), theme.BLUE, None)]))
            return
        day = p.daily_reward_day()
        reward = self.game.data.progression["daily_rewards"][day]

        def claim():
            r = p.claim_daily_reward()
            if r:
                self.game.audio.play("reward")
                self.game.toasts.push(self.tr("daily.claimed", reward=reward_text(self, r)), theme.GREEN)

        self.open_dialog(Dialog(self.tr("daily.title"), self.tr("daily.body", day=day + 1, reward=reward_text(self, reward)),
                                [(self.tr("daily.claim"), theme.GREEN, claim)]))

    def ask_quit(self):
        self.open_dialog(Dialog(self.tr("menu.quit_title"), self.tr("menu.quit_body"),
                                [(self.tr("common.cancel"), theme.GREY, None), (self.tr("menu.quit"), theme.RED, self.game.quit)]))

    def on_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.ask_quit()
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
            self.play()

    # ------------------------------------------------------------ drawing
    def draw_content(self, surf):
        p = self.game.profile
        gd = self.game.data
        draw_currency_bar(surf, p, self.rtl, self.t)
        logo.draw_logo(surf, (VW // 2, 112), 0.42, self.t)
        cid = p.data["selected_char"]
        cdef = gd.characters[cid]
        style = gd.skin_style(cid, p.selected_skin(cid))
        cx, cy = VW // 2, 420
        # platform
        pygame.draw.ellipse(surf, theme.INK, (cx - 150, cy + 70, 300, 70))
        pygame.draw.ellipse(surf, (52, 60, 74), (cx - 144, cy + 66, 288, 62))
        pygame.draw.ellipse(surf, (80, 90, 108), (cx - 120, cy + 70, 240, 44))
        hover = self.hero_btn.hover
        R = 78 + (4 if hover else 0)
        facing = math.sin(self.t * 0.8) * 0.6 + 0.4
        sprites.draw_brawler(surf, style, cx, cy, R, facing, self.t, self.t * 4, False, 0, 0)
        # name plate
        plate = pygame.Rect(0, 0, 300, 74)
        plate.center = (cx, cy + 160)
        theme.draw_panel(surf, plate, (28, 32, 42), theme.RARITY_COLORS[cdef["rarity"]], 16, True, 4)
        text.draw(surf, self.tr("char.%s.name" % cid), (cx, plate.y + 22), 30, theme.WHITE, "center", "middle", outline=3)
        lvl = p.char_level(cid)
        sub = "%s %d" % (self.tr("common.level"), lvl)
        text.draw(surf, sub, (cx + (50 if self.rtl else -50), plate.y + 54), 18, theme.TEXT_DIM, "center", "middle")
        tx = cx + (-46 if self.rtl else 40)
        theme.draw_trophy(surf, (tx, plate.y + 53), 10)
        text.draw(surf, str(p.char_trophies(cid)), (tx + (-16 if self.rtl else 16), plate.y + 54), 18, theme.TROPHY,
                  "right" if self.rtl else "left", "middle", rtl=False)

    def _draw_profile_card(self, surf):
        b = self.profile_btn
        r = b.rect.inflate(int(b.anim * 4), int(b.anim * 4))
        p = self.game.profile
        gd = self.game.data
        theme.draw_panel(surf, r, (32, 38, 48), theme.PANEL_BORDER, 18, True, 3)
        ir = pygame.Rect(0, 0, 66, 66)
        ir.center = (r.x + 46, r.centery) if not self.rtl else (r.right - 46, r.centery)
        cosmetic_art.draw_profile_icon(surf, ir, p.data["icon"], gd)
        tx = r.x + 92 if not self.rtl else r.right - 92
        text.draw(surf, p.display_name(self.game.i18n), (tx, r.y + 10), 24,
                  cosmetic_art.name_color(gd, p.data["name_color"]), "start", outline=2, max_width=170)
        text.draw(surf, self.tr("cosmetic.%s" % p.data["title"]), (tx, r.y + 40), 15, theme.YELLOW, "start", outline=2,
                  max_width=170)
        # level badge + xp bar
        lvl_x = r.right - 40 if not self.rtl else r.x + 40
        theme.draw_star(surf, (lvl_x, r.y + 30), 24, theme.CYAN)
        text.draw(surf, str(p.data["level"]), (lvl_x, r.y + 32), 18, theme.WHITE, "center", "middle", rtl=False)
        need = p.xp_for_next()
        bar = pygame.Rect(0, r.y + 66, 220, 12)
        bar.x = r.x + 92 if not self.rtl else r.right - 92 - 220
        ProgressBar.draw(surf, bar, p.data["xp"] / max(1, need), theme.CYAN, rtl=self.rtl)
        text.draw(surf, "%d/%d" % (p.data["xp"], need), bar.center, 11, theme.WHITE, "center", "middle", outline=2, rtl=False)

    def _draw_mode_button(self, surf):
        b = self.mode_btn
        r = b.rect.inflate(int(b.anim * 6), int(b.anim * 6))
        p = self.game.profile
        mode = p.data["selected_mode"]
        mcol = tuple(self.game.data.modes[mode]["color"])
        theme.draw_panel(surf, r, theme.darken(mcol, 0.45), mcol, 18, True, 4)
        text.draw(surf, self.tr("menu.game_mode"), (r.centerx, r.y + 16), 16, theme.TEXT_DIM, "center", "middle")
        ic = pygame.Rect(0, 0, 64, 64)
        ic.center = (r.x + 50, r.centery + 10) if not self.rtl else (r.right - 50, r.centery + 10)
        icons.mode_icon(surf, ic, mode)
        tx = r.x + 92 if not self.rtl else r.right - 92
        text.draw(surf, self.tr("mode.%s.name" % mode), (tx, r.y + 52), 24, theme.WHITE, "start", outline=3, max_width=170)
        mid = p.selected_map(mode)
        if mid:
            text.draw(surf, self.map_name(mid), (tx, r.y + 88), 17, theme.TEXT_DIM, "start", outline=2, max_width=170)
        text.draw(surf, self.tr("menu.change"), (r.centerx, r.bottom - 18), 15, theme.YELLOW, "center", "middle")

    def map_name(self, mid):
        return map_display_name(self, mid)


def map_display_name(scene, mid):
    m = scene.game.data.maps.get(mid, {})
    if m.get("custom"):
        return m.get("name") or mid
    return scene.tr("map.%s" % mid)


def reward_text(scene, r):
    t = r.get("type")
    if t in ("coins", "gems", "xp"):
        return scene.tr("reward.%s" % t, n=r["amount"])
    if t == "character":
        return scene.tr("reward.character", name=scene.tr("char.%s.name" % r["id"]))
    if t == "skin":
        return scene.tr("reward.skin", name=skin_name(scene, r["id"]))
    if t == "cosmetic":
        return scene.tr("cosmetic.%s" % r["id"])
    return ""


def skin_name(scene, skin_id):
    s = scene.game.data.skins.get(skin_id)
    if not s:
        return skin_id
    return scene.tr("skin.name_fmt", style=scene.tr("skin_style.%s" % s["style"]),
                    name=scene.tr("char.%s.name" % s["char"]))
