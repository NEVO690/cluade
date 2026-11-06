"""Trophy road: milestone rewards unlocked by your highest trophy count."""
import pygame

from ilbrawl import config
from ilbrawl.characters import sprites
from ilbrawl.engine.scene import Scene
from ilbrawl.menus.main_menu import reward_text
from ilbrawl.ui import icons, text, theme
from ilbrawl.ui.widgets import Button, Group, ScrollPanel

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H
STEP = 210


class TrophyRoadScene(Scene):
    def build(self):
        self.widgets = []
        self.add_header("road.title")
        p = self.game.profile
        road = p.trophy_road()
        self.panel = self.add(ScrollPanel((0, 120, VW, 520), horizontal=True))
        n = len(road)
        self.content_w = 260 + n * STEP + 200
        self.panel.content_size = self.content_w
        self.panel.draw_content = self._draw_track
        claimable = p.claimable_road()
        for i, m in enumerate(road):
            x = self._node_x(i)
            g = self.panel.add(Group((x - 90, 60, 180, 420), lambda s, r, i=i, m=m: self._draw_node(s, r, i, m)))
            if i in claimable:
                g.add(Button((0, 0, 160, 58), self.tr("missions.claim"), lambda i=i: self.claim(i), theme.GREEN, 22), 10, 340)
        # scroll to current progress
        hx = self._x_for_trophies(p.data["highest_trophies"])
        self.panel.scroll_to(max(0, hx - VW / 2), True)

    def _node_x(self, i):
        x = 260 + i * STEP
        return self.content_w - x if self.rtl else x

    def _x_for_trophies(self, t):
        road = self.game.profile.trophy_road()
        prev_t, prev_x = 0, 100
        for i, m in enumerate(road):
            x = 260 + i * STEP
            if t < m["trophies"]:
                f = (t - prev_t) / max(1, m["trophies"] - prev_t)
                v = prev_x + (x - prev_x) * f
                return self.content_w - v if self.rtl else v
            prev_t, prev_x = m["trophies"], x
        v = prev_x + 120
        return self.content_w - v if self.rtl else v

    def _draw_track(self, canvas, off):
        p = self.game.profile
        y = 240
        x0 = (100 if not self.rtl else self.content_w - 100) - off
        x1 = (self.content_w - 100 if not self.rtl else 100) - off
        pygame.draw.line(canvas, theme.INK, (x0, y + 3), (x1, y + 3), 26)
        pygame.draw.line(canvas, (44, 50, 62), (x0, y), (x1, y), 20)
        hx = self._x_for_trophies(p.data["highest_trophies"]) - off
        pygame.draw.line(canvas, theme.TROPHY, (x0, y), (hx, y), 20)
        pygame.draw.line(canvas, theme.lighten(theme.TROPHY, 0.4), (x0, y - 5), (hx, y - 5), 5)
        theme.draw_trophy(canvas, (hx, y - 38), 18)
        s = text.render(str(p.data["highest_trophies"]), 22, theme.WHITE, True, 3, rtl=False)
        canvas.blit(s, (hx - s.get_width() // 2, y + 18))

    def _draw_node(self, surf, r, i, m):
        p = self.game.profile
        reached = p.data["highest_trophies"] >= m["trophies"]
        claimed = i in p.data["trophy_road_claimed"]
        cx = r.centerx
        y = r.y + 180
        pygame.draw.circle(surf, theme.INK, (cx, y + 2), 20)
        pygame.draw.circle(surf, theme.TROPHY if reached else (78, 84, 96), (cx, y), 16)
        text.draw(surf, str(m["trophies"]), (cx, r.y + 140), 20, theme.TROPHY if reached else theme.TEXT_DIM, "center",
                  "middle", rtl=False)
        card = pygame.Rect(r.x + 10, r.y + 222, r.w - 20, 110)
        rew = m["reward"]
        is_char = rew["type"] == "character"
        col = theme.RARITY_COLORS.get(self.game.data.characters.get(rew.get("id"), {}).get("rarity"), theme.PURPLE) \
            if is_char else theme.PANEL_BORDER
        theme.draw_panel(surf, card, (30, 36, 46) if not claimed else (24, 27, 34), col, 14, True, 3)
        if is_char:
            st = self.game.data.characters[rew["id"]]["style"]
            por = sprites.portrait(st, 96, key=(rew["id"], None))
            surf.blit(por, (card.centerx - 48, card.y - 30))
        else:
            ic = pygame.Rect(card.centerx - 32, card.y + 8, 64, 64)
            (icons.coin if rew["type"] == "coins" else icons.gem)(surf, ic)
        text.draw(surf, reward_text(self, rew), (card.centerx, card.bottom - 20), 16, theme.WHITE, "center", "middle",
                  max_width=card.w - 8)
        if claimed:
            icons.check(surf, pygame.Rect(card.right - 40, card.y - 14, 44, 44))
        elif not reached:
            theme.draw_lock(surf, (card.right - 18, card.y + 6), 14)

    def claim(self, i):
        r = self.game.profile.claim_road(i)
        if r:
            self.game.audio.play("unlock" if r["type"] == "character" else "reward")
            self.game.toasts.push(self.tr("road.claimed", reward=reward_text(self, r)), theme.GREEN)
            keep = self.panel.target
            self.build()
            self.panel.scroll_to(keep, True)

    def draw_content(self, surf):
        self.draw_header(surf)
        text.draw(surf, self.tr("road.subtitle"), (VW // 2, VH - 50), 20, theme.TEXT_DIM, "center", "middle")
