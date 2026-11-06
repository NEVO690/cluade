"""End-of-match screen: outcome, scoreboard and rewards."""
import math

import pygame

from ilbrawl import config
from ilbrawl.characters import sprites
from ilbrawl.engine.scene import Scene
from ilbrawl.menus.main_menu import map_display_name, reward_text
from ilbrawl.ui import icons, text, theme
from ilbrawl.ui.widgets import Button

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H


class ResultsScene(Scene):
    def __init__(self, game, result, summary):
        self.result = result
        self.summary = summary
        super().__init__(game)
        if summary.get("levels"):
            game.toasts.push(game.i18n.t("results.level_up", n=game.profile.data["level"]), theme.CYAN)
        for i in summary.get("road", []):
            game.toasts.push(game.i18n.t("results.road_reached"), theme.PURPLE)
            break

    def build(self):
        self.widgets = []
        self.add(Button(self.R(VW - 330, VH - 100, 300, 76), self.tr("results.play_again"), self.again, theme.YELLOW, 26,
                        icon=icons.play))
        self.add(Button(self.R(30, VH - 100, 280, 76), self.tr("results.lobby"), self.lobby, theme.BLUE, 24))

    def again(self):
        r = self.result
        from ilbrawl.gameplay.battle_scene import BattleScene
        if r["map"] in self.game.data.maps:
            self.game.replace(BattleScene(self.game, r["mode"], r["map"], r["char"]))
        else:
            self.lobby()

    def lobby(self):
        self.game.pop_to_root() if len(self.game.scenes) > 1 else self._to_main()

    def _to_main(self):
        from ilbrawl.menus.main_menu import MainMenuScene
        self.game.replace(MainMenuScene(self.game))

    def on_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.lobby()

    def draw_content(self, surf):
        r = self.result
        s = self.summary
        gd = self.game.data
        outcome = r["outcome"]
        if r.get("rank"):
            title = self.tr("results.rank", n=r["rank"])
            col = theme.YELLOW if r["rank"] <= 3 else theme.RED
        else:
            title = self.tr("results.%s" % outcome)
            col = {"win": theme.YELLOW, "loss": theme.RED, "draw": theme.TEXT_DIM}[outcome]
        k = min(1.0, self.t * 3)
        size = int(70 + 20 * (1 - k) + 3 * math.sin(self.t * 3))
        text.draw(surf, title, (VW // 2, 60), size, col, "center", "middle", outline=5)
        sub = "%s • %s" % (self.tr("mode.%s.name" % r["mode"]), map_display_name(self, r["map"]))
        if r.get("score_text"):
            sub += "  (%s)" % r["score_text"]
        text.draw(surf, sub, (VW // 2, 112), 20, theme.WHITE, "center", "middle")
        # hero
        hx = self.X(190)
        style = gd.skin_style(r["char"], self.game.profile.selected_skin(r["char"]))
        pygame.draw.ellipse(surf, theme.INK, (hx - 110, 380, 220, 50))
        pygame.draw.ellipse(surf, (66, 76, 92), (hx - 104, 378, 208, 42))
        jump = abs(math.sin(self.t * 4)) * 20 if outcome == "win" else 0
        sprites.draw_brawler(surf, style, hx, 330 - jump, 70, 0.3 if outcome == "win" else 1.4, self.t, 0, False)
        text.draw(surf, self.tr("char.%s.name" % r["char"]), (hx, 452), 26, theme.WHITE, "center", "middle")
        # scoreboard
        board = sorted(r["scoreboard"], key=lambda b: (b["rank"] or 0, b["team"], -b["kills"]))
        if r["mode"] != "solo_survival":
            board = sorted(r["scoreboard"], key=lambda b: (b["team"] != 0, -b["score"], -b["kills"]))
        tb = pygame.Rect(self.X(380, 520), 150, 520, 46 + 46 * len(board))
        theme.draw_panel(surf, tb, (28, 34, 44), theme.PANEL_BORDER, 18)
        cols = [("results.col_player", 0.04), ("results.col_kills", 0.56), ("results.col_damage", 0.72),
                ("results.col_score", 0.9)]

        def cx(f):
            return tb.x + tb.w * f if not self.rtl else tb.right - tb.w * f

        for key, f in cols:
            text.draw(surf, self.tr(key), (cx(f), tb.y + 14), 15, theme.TEXT_DIM, "start" if f < 0.1 else "center")
        for i, b in enumerate(board):
            y = tb.y + 44 + i * 46
            row = pygame.Rect(tb.x + 8, y, tb.w - 16, 40)
            team_col = config.TEAM_COLORS[0 if b["team"] == 0 else 1]
            pygame.draw.rect(surf, theme.darken(team_col, 0.55) if not b["is_player"] else theme.darken(theme.YELLOW, 0.45),
                             row, border_radius=10)
            por = sprites.portrait(gd.characters[b["char"]]["style"], 44, key=(b["char"], None))
            surf.blit(por, (row.x + 2 if not self.rtl else row.right - 46, row.y - 4))
            nx = row.x + 50 if not self.rtl else row.right - 50
            label = b["name"] if not b.get("rank") else "#%d  %s" % (b["rank"], b["name"])
            text.draw(surf, label, (nx, row.centery), 17, theme.WHITE, "start", "middle", max_width=210)
            text.draw(surf, str(b["kills"]), (cx(0.56) + (0 if not self.rtl else 0), row.centery), 18, theme.WHITE, "center",
                      "middle", rtl=False)
            text.draw(surf, "{:,}".format(b["damage"]), (cx(0.72), row.centery), 16, theme.WHITE, "center", "middle",
                      rtl=False)
            text.draw(surf, str(b["score"]), (cx(0.9), row.centery), 18, theme.YELLOW, "center", "middle", rtl=False)
        # rewards
        rp = pygame.Rect(self.X(920, 330), 150, 330, 430)
        theme.draw_panel(surf, rp, (32, 38, 48), theme.YELLOW, 18)
        text.draw(surf, self.tr("results.rewards"), (rp.centerx, rp.y + 24), 24, theme.YELLOW, "center", "middle")
        rows = [(lambda sf, c: theme.draw_trophy(sf, c, 14), ("+" if s["trophies"] > 0 else "") + str(s["trophies"]),
                 theme.TROPHY),
                (lambda sf, c: theme.draw_coin(sf, c, 15), "+%d" % s["coins"], theme.COIN),
                (lambda sf, c: theme.draw_star(sf, c, 16, theme.CYAN), "+%d XP" % s["xp"], theme.CYAN)]
        appear = min(3, int(self.t * 3))
        for i, (ic, val, c) in enumerate(rows[:appear]):
            y = rp.y + 76 + i * 56
            ix = rp.x + 50 if not self.rtl else rp.right - 50
            ic(surf, (ix, y))
            text.draw(surf, val, (rp.right - 40 if not self.rtl else rp.x + 40, y), 30, c, "end", "middle", rtl=False)
        y = rp.y + 250
        p = self.game.profile
        notes = []
        for i in s.get("missions", []):
            m = p.data["missions"]["list"][i]
            from ilbrawl.progression import missions as ms
            notes.append(self.tr("results.mission_done", name=ms.describe(m, self.game.i18n)))
        if s.get("achievements"):
            notes.append(self.tr("results.ach_ready"))
        for i in s.get("road", []):
            notes.append(self.tr("results.road_reward", reward=reward_text(self, p.trophy_road()[i]["reward"])))
        for i, n in enumerate(notes[:4]):
            text.draw_wrapped(surf, n, (rp.x + 16, y + i * 44, rp.w - 32, 44), 14, theme.WHITE, "center", True, 2,
                              max_lines=2)
