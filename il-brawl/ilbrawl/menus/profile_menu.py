"""Player profile: name, icon, title and colour, statistics and match history."""
import pygame

from ilbrawl import config
from ilbrawl.characters import sprites
from ilbrawl.engine.scene import Scene
from ilbrawl.menus.main_menu import map_display_name
from ilbrawl.ui import cosmetic_art, text, theme
from ilbrawl.ui.widgets import Button, Group, ScrollPanel, Selector, TabBar, TextInput

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H


class ProfileScene(Scene):
    def __init__(self, game, tab=0):
        self.tab = tab
        super().__init__(game)

    def build(self):
        self.widgets = []
        self.add_header("profile.title")
        self.add(TabBar((160, 88, VW - 320, 52), [self.tr("profile.tab.overview"), self.tr("profile.tab.stats"),
                                                  self.tr("profile.tab.history")], self.tab, self.set_tab, self.rtl,
                        theme.CYAN))
        if self.tab == 0:
            self._build_overview()
        elif self.tab == 2:
            self._build_history()

    def set_tab(self, i):
        self._commit_name()
        self.tab = i
        self.build()

    def _commit_name(self):
        if getattr(self, "name_input", None) is not None and self.tab == 0:
            self.set_name(self.name_input.value)

    def back(self):
        self._commit_name()
        super().back()

    # ------------------------------------------------------------ overview
    def _build_overview(self):
        p = self.game.profile
        gd = self.game.data
        x = self.X(420, 800)
        self.name_input = self.add(TextInput((x, 186, 800, 54), p.data["name"], 16, self.set_name, 26))
        self.name_input.placeholder = self.tr("profile.default_name")
        owned = p.data["cosmetics_owned"]
        titles = [c["id"] for c in gd.cosmetics.get("titles", []) if c["id"] in owned]
        self.titles = titles
        self.add(Selector((x if not self.rtl else x + 420, 290, 380, 48), [self.tr("cosmetic.%s" % t) for t in titles],
                          titles.index(p.data["title"]) if p.data["title"] in titles else 0, self.set_title, theme.PURPLE))
        colors = [c["id"] for c in gd.cosmetics.get("name_colors", []) if c["id"] in owned]
        self.colors = colors
        self.add(Selector((x + 420 if not self.rtl else x, 290, 380, 48), [self.tr("cosmetic.%s" % c) for c in colors],
                          colors.index(p.data["name_color"]) if p.data["name_color"] in colors else 0, self.set_color,
                          theme.PINK))
        # icon picker
        icons_owned = ["char:%s" % c for c in gd.char_order if p.is_unlocked(c)] + \
                      [c["id"] for c in gd.cosmetics.get("icons", []) if c["id"] in owned]
        self.icon_panel = self.add(ScrollPanel((x, 390, 800, 96), horizontal=True))
        n = len(icons_owned)
        cw = 88
        self.icon_panel.content_size = max(800, n * cw + 8)
        for i, ic in enumerate(icons_owned):
            pos = i * cw + 8
            if self.rtl:
                pos = self.icon_panel.content_size - pos - 80
            b = self.icon_panel.add(Button((pos, 6, 80, 80), "", lambda ic=ic: self.set_icon(ic), (48, 56, 70), radius=12,
                                           icon=lambda s, r, ic=ic: cosmetic_art.draw_profile_icon(s, r.inflate(10, 10), ic, gd, False)))
            b.selected = ic == p.data["icon"]
        if self.rtl:
            self.icon_panel.scroll_to(self.icon_panel.max_offset(), True)

    def set_name(self, v):
        v = v.strip()[:16]
        p = self.game.profile
        if v != p.data["name"]:
            p.data["name"] = v
            p.save()

    def set_title(self, i):
        self.game.profile.data["title"] = self.titles[i]
        self.game.profile.save()

    def set_color(self, i):
        self.game.profile.data["name_color"] = self.colors[i]
        self.game.profile.save()

    def set_icon(self, ic):
        self._commit_name()
        self.game.profile.data["icon"] = ic
        self.game.profile.save()
        self.build()

    def _draw_overview(self, surf):
        p = self.game.profile
        gd = self.game.data
        card = self.R(30, 160, 360, 520)
        theme.draw_panel(surf, card, (32, 38, 48), theme.CYAN, 20)
        ir = pygame.Rect(0, 0, 150, 150)
        ir.center = (card.centerx, card.y + 100)
        cosmetic_art.draw_profile_icon(surf, ir, p.data["icon"], gd)
        text.draw(surf, p.display_name(self.game.i18n), (card.centerx, card.y + 196), 30,
                  cosmetic_art.name_color(gd, p.data["name_color"]), "center", "middle", outline=3, max_width=card.w - 20)
        text.draw(surf, self.tr("cosmetic.%s" % p.data["title"]), (card.centerx, card.y + 232), 18, theme.YELLOW, "center",
                  "middle")
        rows = [(self.tr("profile.level"), p.data["level"]), (self.tr("profile.trophies"), p.total_trophies()),
                (self.tr("profile.highest"), p.data["highest_trophies"]),
                (self.tr("profile.characters"), "%d/%d" % (len(p.data["unlocked"]), len(gd.char_order))),
                (self.tr("profile.since"), p.data.get("created", ""))]
        for i, (k, v) in enumerate(rows):
            y = card.y + 280 + i * 44
            text.draw(surf, k, (card.x + 24 if not self.rtl else card.right - 24, y), 19, theme.TEXT_DIM, "start")
            text.draw(surf, str(v), (card.right - 24 if not self.rtl else card.x + 24, y), 19, theme.WHITE, "end", rtl=False)
        x = self.X(420, 800)
        lx = x if not self.rtl else x + 800
        text.draw(surf, self.tr("profile.name"), (lx, 158), 18, theme.TEXT_DIM, "start")
        text.draw(surf, self.tr("profile.title_label"), (lx if not self.rtl else lx, 262), 18, theme.TEXT_DIM, "start")
        text.draw(surf, self.tr("profile.color_label"), (x + 420 if not self.rtl else x + 380, 262), 18, theme.TEXT_DIM,
                  "start")
        text.draw(surf, self.tr("profile.icon_label"), (lx, 362), 18, theme.TEXT_DIM, "start")
        text.draw(surf, self.tr("profile.more_in_shop"), (lx, 506), 16, theme.YELLOW, "start")

    # ------------------------------------------------------------ stats
    def _draw_stats(self, surf):
        p = self.game.profile
        st = p.data["stats"]
        gd = self.game.data
        items = [("matches", st["matches"]), ("wins", st["wins"]), ("losses", st["losses"]), ("draws", st["draws"]),
                 ("kills", st["kills"]), ("deaths", st["deaths"]), ("damage", "{:,}".format(st["damage"])),
                 ("healing", "{:,}".format(st["healing"])), ("supers", st["supers"]),
                 ("gems_collected", st["gems_collected"]), ("goals", st["goals"]), ("solo_wins", st["solo_wins"]),
                 ("best_kills", st["best_kills"]), ("playtime", "%d:%02d" % (int(st["playtime"]) // 3600,
                                                                               int(st["playtime"]) % 3600 // 60))]
        winrate = int(100 * st["wins"] / st["matches"]) if st["matches"] else 0
        items.insert(2, ("winrate", "%d%%" % winrate))
        cols = 3
        cw, chh = 380, 62
        x0 = (VW - cols * cw - (cols - 1) * 16) // 2
        for i, (k, v) in enumerate(items):
            c, r = i % cols, i // cols
            if self.rtl:
                c = cols - 1 - c
            rect = pygame.Rect(x0 + c * (cw + 16), 160 + r * (chh + 10), cw, chh)
            theme.draw_panel(surf, rect, (30, 36, 46), theme.PANEL_BORDER, 14, False, 2)
            text.draw(surf, self.tr("stats.%s" % k), (rect.x + 18 if not self.rtl else rect.right - 18, rect.centery), 19,
                      theme.TEXT_DIM, "start", "middle", max_width=cw - 140)
            text.draw(surf, str(v), (rect.right - 18 if not self.rtl else rect.x + 18, rect.centery), 24, theme.WHITE,
                      "end", "middle", rtl=False)
        y = 160 + ((len(items) + cols - 1) // cols) * (chh + 10) + 10
        text.draw(surf, self.tr("stats.by_mode"), (self.X(x0), y), 22, theme.YELLOW, "start")
        for i, mid in enumerate(gd.mode_order):
            mm = st["mode_matches"].get(mid, 0)
            mw = st["mode_wins"].get(mid, 0)
            rect = pygame.Rect(x0 + (i if not self.rtl else 4 - i) * 236, y + 34, 226, 60)
            theme.draw_panel(surf, rect, theme.darken(tuple(gd.modes[mid]["color"]), 0.5), tuple(gd.modes[mid]["color"]),
                             12, False, 2)
            text.draw(surf, self.tr("mode.%s.name" % mid), (rect.centerx, rect.y + 16), 16, theme.WHITE, "center",
                      "middle", max_width=rect.w - 10)
            text.draw(surf, self.tr("stats.wins_of", w=mw, m=mm), (rect.centerx, rect.y + 42), 15, theme.TEXT_DIM,
                      "center", "middle")

    # ------------------------------------------------------------ history
    def _build_history(self):
        p = self.game.profile
        hist = p.data["history"]
        self.hist_panel = self.add(ScrollPanel((80, 160, VW - 160, VH - 176)))
        W = VW - 160
        for i, h in enumerate(hist):
            self.hist_panel.add(Group((6, 6 + i * 74, W - 12, 66), lambda s, r, h=h: self._draw_hist(s, r, h)))
        self.hist_panel.content_size = 12 + len(hist) * 74

    def _draw_hist(self, surf, r, h):
        gd = self.game.data
        col = {"win": theme.GREEN, "loss": theme.RED, "draw": theme.GREY}[h["outcome"]]
        theme.draw_panel(surf, r, (30, 36, 46), col, 14, False, 3)
        por = sprites.portrait(gd.characters[h["char"]]["style"], 66, key=(h["char"], None))
        surf.blit(por, (r.x + 6 if not self.rtl else r.right - 72, r.y))
        tx = r.x + 84 if not self.rtl else r.right - 84
        res = self.tr("results.rank", n=h["rank"]) if h.get("rank") else self.tr("results.%s" % h["outcome"])
        text.draw(surf, res, (tx, r.y + 8), 22, col, "start")
        sub = "%s • %s" % (self.tr("mode.%s.name" % h["mode"]), map_display_name(self, h["map"]))
        text.draw(surf, sub, (tx, r.y + 38), 15, theme.TEXT_DIM, "start", max_width=480)
        ex = r.right - 24 if not self.rtl else r.x + 24
        sign = "+" if h["trophies"] > 0 else ""
        text.draw(surf, "%s%d" % (sign, h["trophies"]), (ex, r.y + 10), 22, theme.TROPHY, "end", rtl=False)
        text.draw(surf, self.tr("results.kills_short", n=h["kills"]) + "   " + h["date"], (ex, r.y + 40), 14,
                  theme.TEXT_DIM, "end")

    def draw_content(self, surf):
        self.draw_header(surf)
        if self.tab == 0:
            self._draw_overview(surf)
        elif self.tab == 1:
            self._draw_stats(surf)
        elif not self.game.profile.data["history"]:
            text.draw(surf, self.tr("profile.no_history"), (VW // 2, 380), 24, theme.TEXT_DIM, "center", "middle")
