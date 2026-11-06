"""Character selection: portraits grid, stats, abilities, unlock status, upgrades and skins."""
import math

import pygame

from ilbrawl import config
from ilbrawl.characters import sprites
from ilbrawl.config import TILE
from ilbrawl.engine.scene import Scene
from ilbrawl.menus.main_menu import skin_name
from ilbrawl.ui import icons, text, theme
from ilbrawl.ui.widgets import Button, Dialog, ProgressBar, ScrollPanel, Selector

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H


def attack_power(c):
    a = c["attack"]
    n = a.get("count", 1) if a["type"] in ("spread", "flame", "burst") else 1
    return a["damage"] * n


def stat_values(c):
    """Normalized 0..1 stats for the bars."""
    return {
        "health": c["hp"] / 6500,
        "damage": attack_power(c) / 1700,
        "speed": (c["speed"] - 150) / 80,
        "range": c["attack"].get("range", 2) / 11,
        "reload": (2.3 - c["reload"]) / 1.5,
    }


class CharCard(Button):
    def __init__(self, rect, scene, cid):
        super().__init__(rect, "", lambda: scene.select(cid), theme.PANEL, sound="click")
        self.scene = scene
        self.cid = cid

    def draw(self, surf):
        sc = self.scene
        gd = sc.game.data
        p = sc.game.profile
        c = gd.characters[self.cid]
        unlocked = p.is_unlocked(self.cid)
        r = self.rect.inflate(int(self.anim * 6), int(self.anim * 6))
        rc = theme.RARITY_COLORS[c["rarity"]]
        sel = sc.current == self.cid
        if sel:
            pulse = 0.5 + 0.5 * math.sin(sc.t * 6)
            pygame.draw.rect(surf, theme.lerp_color(theme.YELLOW, theme.WHITE, pulse * 0.5), r.inflate(12, 12), 5,
                             border_radius=20)
        theme.draw_panel(surf, r, theme.darken(rc, 0.45) if unlocked else (36, 38, 44), rc if unlocked else theme.GREY,
                         16, True, 3)
        style = gd.skin_style(self.cid, p.selected_skin(self.cid))
        por = sprites.portrait(style, 104, key=(self.cid, p.selected_skin(self.cid)))
        if not unlocked:
            por = por.copy()
            por.set_alpha(110)
        surf.blit(por, (r.centerx - 52, r.y + 2))
        text.draw(surf, sc.tr("char.%s.name" % self.cid), (r.centerx, r.bottom - 34), 18, theme.WHITE, "center", "middle",
                  max_width=r.w - 10)
        if unlocked:
            theme.draw_trophy(surf, (r.centerx - 16, r.bottom - 13), 7)
            text.draw(surf, str(p.char_trophies(self.cid)), (r.centerx - 6, r.bottom - 12), 14, theme.TROPHY, "left",
                      "middle", rtl=False)
            lx = r.x + 16 if not sc.rtl else r.right - 16
            text.draw(surf, str(p.char_level(self.cid)), (lx, r.y + 16), 15, theme.WHITE, "center", "middle", rtl=False)
        else:
            theme.draw_lock(surf, (r.centerx, r.y + 56), 20)


class CharacterSelectScene(Scene):
    def __init__(self, game):
        self.current = game.profile.data["selected_char"]
        self.anim = 0.0
        self.scroll_keep = 0
        super().__init__(game)

    def build(self):
        self.widgets = []
        self.add_header("chars.title")
        gd = self.game.data
        p = self.game.profile
        grid_x = 20 if not self.rtl else VW - 20 - 600
        self.grid = self.add(ScrollPanel((grid_x, 96, 600, VH - 110)))
        cols = 4
        cw, ch = 140, 150
        for i, cid in enumerate(gd.char_order):
            col, row = i % cols, i // cols
            if self.rtl:
                col = cols - 1 - col
            self.grid.add(CharCard((8 + col * (cw + 8), 8 + row * (ch + 10), cw, ch), self, cid))
        self.grid.content_size = 16 + ((len(gd.char_order) + cols - 1) // cols) * (ch + 10)
        self.grid.scroll_to(self.scroll_keep, True)
        # detail panel buttons
        px = self.X(640, 620)
        c = gd.characters[self.current]
        unlocked = p.is_unlocked(self.current)
        if unlocked:
            sel = p.data["selected_char"] == self.current
            self.add(Button((px + 330, VH - 92, 270, 70),
                            self.tr("chars.selected") if sel else self.tr("chars.select"),
                            self.choose, theme.GREEN if not sel else theme.GREY, 26, enabled=not sel))
            cost = p.upgrade_cost(self.current)
            if cost is not None:
                self.add(Button((px + 20, VH - 92, 290, 70), self.tr("chars.upgrade"), self.upgrade, theme.ORANGE, 22,
                                sublabel=lambda cost=cost: "%d %s" % (cost, self.tr("common.coins")),
                                enabled=p.data["coins"] >= cost))
            else:
                self.add(Button((px + 20, VH - 92, 290, 70), self.tr("chars.max_level"), None, theme.GREY, 22,
                                enabled=False))
            owned = [None] + [s for s in p.data["skins_owned"] if gd.skins.get(s, {}).get("char") == self.current]
            if len(owned) > 1:
                cur = p.selected_skin(self.current)
                names = [self.tr("chars.default_skin") if s is None else skin_name(self, s) for s in owned]
                self.skin_list = owned
                self.add(Selector((px + 330, 540, 270, 44), names, owned.index(cur) if cur in owned else 0,
                                  self.set_skin))
        else:
            u = c["unlock"]
            if u["type"] == "trophies":
                self.add(Button((px + 20, VH - 92, 580, 70), self.tr("chars.unlock_road", n=u["value"]), self.goto_road,
                                theme.PURPLE, 22))
            else:
                self.add(Button((px + 20, VH - 92, 580, 70), self.tr("chars.unlock_shop"), self.goto_shop, theme.ORANGE,
                                22, sublabel="%d %s" % (u["value"], self.tr("common." + u["type"]))))

    def select(self, cid):
        if cid != self.current:
            self.current = cid
            self.anim = 0.0
            self.game.audio.play("whoosh", 0.6)
            self.scroll_keep = self.grid.target
            self.build()

    def choose(self):
        self.game.profile.data["selected_char"] = self.current
        self.game.profile.save()
        self.game.audio.play("reward")
        self.anim = 0.0
        self.scroll_keep = self.grid.target
        self.build()

    def upgrade(self):
        p = self.game.profile
        cost = p.upgrade_cost(self.current)

        def do():
            if p.upgrade_character(self.current):
                self.game.audio.play("levelup")
                self.game.toasts.push(self.tr("chars.upgraded", name=self.tr("char.%s.name" % self.current),
                                              n=p.char_level(self.current)), theme.GREEN)
                self.anim = 0.0
                self.scroll_keep = self.grid.target
                self.build()

        self.open_dialog(Dialog(self.tr("chars.upgrade"), self.tr("chars.upgrade_body", n=p.char_level(self.current) + 1,
                                                                 cost=cost),
                                [(self.tr("common.cancel"), theme.GREY, None), (self.tr("common.confirm"), theme.GREEN, do)]))

    def set_skin(self, idx):
        p = self.game.profile
        s = self.skin_list[idx]
        if s is None:
            p.data["skin_selected"].pop(self.current, None)
        else:
            p.data["skin_selected"][self.current] = s
        p.save()
        self.anim = 0.0

    def goto_road(self):
        from ilbrawl.menus.trophy_road import TrophyRoadScene
        self.game.push(TrophyRoadScene(self.game))

    def goto_shop(self):
        from ilbrawl.menus.shop_menu import ShopScene
        self.game.push(ShopScene(self.game, tab=2))

    def on_resume(self):
        self.scroll_keep = self.grid.target
        super().on_resume()

    def update(self, dt):
        super().update(dt)
        self.anim = min(1.0, self.anim + dt * 2.5)

    def draw_content(self, surf):
        self.draw_header(surf)
        gd = self.game.data
        p = self.game.profile
        cid = self.current
        c = gd.characters[cid]
        px = self.X(640, 620)
        panel = pygame.Rect(px, 96, 620, VH - 110)
        rc = theme.RARITY_COLORS[c["rarity"]]
        theme.draw_panel(surf, panel, (26, 31, 40), rc, 20, True, 4)
        # hero with selection bounce
        k = self.anim
        bounce = math.sin(min(1.0, k * 1.6) * math.pi) * 22 * (1 - k * 0.5)
        hx = panel.x + 120 if not self.rtl else panel.right - 120
        hy = panel.y + 150 - bounce
        pygame.draw.ellipse(surf, theme.INK, (hx - 86, panel.y + 214, 172, 40))
        pygame.draw.ellipse(surf, theme.darken(rc, 0.3), (hx - 82, panel.y + 212, 164, 34))
        style = gd.skin_style(cid, p.selected_skin(cid))
        sprites.draw_brawler(surf, style, hx, hy, 60 + 6 * (1 - k), math.sin(self.t) * 0.5 + 0.3, self.t, self.t * 4,
                             False, 0, 0)
        # name & badges
        tx = panel.x + 240 if not self.rtl else panel.right - 240
        text.draw(surf, self.tr("char.%s.name" % cid), (tx, panel.y + 18), 40, theme.WHITE, "start", outline=3)
        bx = tx
        for label, col in ((self.tr("rarity.%s" % c["rarity"]), rc), (self.tr("class.%s" % c["class"]),
                                                                       theme.CLASS_COLORS[c["class"]])):
            s = text.render(label, 16, theme.WHITE, True, 2)
            w = s.get_width() + 22
            r = pygame.Rect(bx if not self.rtl else bx - w, panel.y + 72, w, 28)
            pygame.draw.rect(surf, theme.INK, r.inflate(4, 4), border_radius=14)
            pygame.draw.rect(surf, col, r, border_radius=12)
            surf.blit(s, (r.x + 11, r.y + (28 - s.get_height()) // 2))
            bx = bx + w + 10 if not self.rtl else bx - w - 10
        if p.is_unlocked(cid):
            text.draw(surf, "%s %d   " % (self.tr("common.level"), p.char_level(cid)), (tx, panel.y + 112), 18,
                      theme.CYAN, "start")
        else:
            text.draw(surf, self.tr("chars.locked"), (tx, panel.y + 112), 18, theme.RED, "start")
        text.draw_wrapped(surf, self.tr("char.%s.desc" % cid),
                          (panel.x + 240 if not self.rtl else panel.x + 20, panel.y + 140, 360, 80), 16, theme.TEXT_DIM,
                          "start", False, 0, 3, 4)
        # stats
        sv = stat_values(c)
        lvl_mult = 1 + gd.level_bonus * (p.char_level(cid) - 1)
        raw = {"health": int(c["hp"] * lvl_mult), "damage": int(attack_power(c) * lvl_mult), "speed": c["speed"],
               "range": c["attack"].get("range", 2), "reload": self.tr("unit.sec", n="%.1f" % c["reload"])}
        y = panel.y + 268
        sx = panel.x + 24 if not self.rtl else panel.right - 24 - 290
        for i, key in enumerate(("health", "damage", "speed", "range", "reload")):
            yy = y + i * 30
            lx = sx if not self.rtl else sx + 290
            text.draw(surf, self.tr("stat.%s" % key), (lx, yy), 16, theme.WHITE, "start", max_width=110)
            bar = pygame.Rect(sx + 116 if not self.rtl else sx + 40, yy + 3, 134, 12)
            ProgressBar.draw(surf, bar, max(0.08, sv[key]), theme.CLASS_COLORS[c["class"]], rtl=self.rtl)
            vx = sx + 290 if not self.rtl else sx
            text.draw(surf, str(raw[key]), (vx, yy), 15, theme.YELLOW, "right" if not self.rtl else "left", rtl=False)
        # abilities
        ax = panel.x + 330 if not self.rtl else panel.x + 20
        for i, (kind, col) in enumerate((("attack", theme.ORANGE), ("super", theme.YELLOW))):
            r = pygame.Rect(ax, panel.y + 262 + i * 76 + (0 if i == 0 else 0), 270, 68)
            if kind == "super":
                r.y = panel.y + 262 + 76
            theme.draw_panel(surf, r, (22, 26, 34), col, 12, False, 2)
            label = self.tr("chars.%s_label" % kind) + ": " + self.tr("char.%s.%s" % (cid, kind))
            text.draw(surf, label, (r.x + 10 if not self.rtl else r.right - 10, r.y + 6), 16, col, "start",
                      max_width=r.w - 20)
            text.draw_wrapped(surf, self.tr("char.%s.%s_desc" % (cid, kind)), (r.x + 8, r.y + 28, r.w - 16, 40), 13,
                              theme.WHITE, "start", False, 0, 2, 2)
        if not p.is_unlocked(cid):
            u = c["unlock"]
            msg = self.tr("chars.req_%s" % u["type"], n=u.get("value", 0))
            text.draw(surf, msg, (panel.centerx, VH - 112), 17, theme.YELLOW, "center", "middle")
        elif len([s for s in p.data["skins_owned"] if gd.skins.get(s, {}).get("char") == cid]) == 0:
            text.draw(surf, self.tr("chars.no_skins"), (ax + 135, 548), 14, theme.TEXT_DIM, "center", "middle",
                      max_width=270)
        else:
            text.draw(surf, self.tr("chars.skin"), (ax + 135, 524), 14, theme.TEXT_DIM, "center", "middle")
