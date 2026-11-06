"""Daily missions, achievements and the daily login reward calendar."""
import pygame

from ilbrawl import config
from ilbrawl.engine.scene import Scene
from ilbrawl.menus.main_menu import reward_text
from ilbrawl.progression import achievements, missions
from ilbrawl.ui import icons, text, theme
from ilbrawl.ui.widgets import Button, Group, ProgressBar, ScrollPanel, TabBar

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H


class MissionsScene(Scene):
    def __init__(self, game, tab=0):
        self.tab = tab
        super().__init__(game)

    def build(self):
        self.widgets = []
        self.add_header("missions.title")
        p = self.game.profile
        tabs = self.add(TabBar((160, 88, VW - 320, 52), [self.tr("missions.tab.daily"), self.tr("missions.tab.achievements"),
                                                         self.tr("missions.tab.rewards")], self.tab, self.set_tab, self.rtl,
                               theme.GREEN))
        tabs.badges = [lambda: missions.claimable_count(p), lambda: achievements.claimable_count(p),
                       lambda: p.daily_reward_available()]
        self.panel = self.add(ScrollPanel((60, 156, VW - 120, VH - 170)))
        if self.tab == 0:
            self._build_missions()
        elif self.tab == 1:
            self._build_achievements()
        else:
            self._build_rewards()

    def set_tab(self, i):
        self.tab = i
        self.build()

    # ------------------------------------------------------------ missions
    def _build_missions(self):
        p = self.game.profile
        missions.ensure_daily(p)
        W = self.panel.rect.w
        for i, m in enumerate(p.data["missions"]["list"]):
            g = self.panel.add(Group((10, 10 + i * 140, W - 20, 124), lambda s, r, m=m: self._draw_mission(s, r, m)))
            done = m["progress"] >= m["target"]
            bx = W - 20 - 210 if not self.rtl else 0
            if m["claimed"]:
                g.add(Button((0, 0, 190, 64), self.tr("missions.claimed"), None, theme.GREY, 20, enabled=False),
                      bx + 10, 30)
            else:
                g.add(Button((0, 0, 190, 64), self.tr("missions.claim"), lambda i=i: self.claim_mission(i),
                             theme.GREEN if done else theme.GREY, 22, enabled=done), bx + 10, 30)
        self.panel.content_size = 20 + 3 * 140

    def _draw_mission(self, surf, r, m):
        theme.draw_panel(surf, r, (30, 36, 46), theme.GREEN if m["progress"] >= m["target"] else theme.PANEL_BORDER, 16)
        desc = missions.describe(m, self.game.i18n)
        tx = r.x + 24 if not self.rtl else r.right - 24
        text.draw(surf, desc, (tx, r.y + 16), 24, theme.WHITE, "start", max_width=r.w - 290)
        bar = pygame.Rect(r.x + 24 if not self.rtl else r.x + 240, r.y + 62, r.w - 290, 22)
        ProgressBar.draw(surf, bar, m["progress"] / m["target"], theme.GREEN, rtl=self.rtl,
                         label="%d / %d" % (m["progress"], m["target"]))
        rew = "%s  •  %s" % (self.tr("reward.coins", n=m["coins"]), self.tr("reward.xp", n=m["xp"]))
        text.draw(surf, rew, (tx, r.y + 92), 16, theme.YELLOW, "start")

    def claim_mission(self, i):
        m = missions.claim(self.game.profile, i)
        if m:
            self.game.audio.play("reward")
            self.game.toasts.push(self.tr("missions.reward_got", coins=m["coins"], xp=m["xp"]), theme.GREEN)
            self.build()

    # ------------------------------------------------------------ achievements
    def _build_achievements(self):
        p = self.game.profile
        W = self.panel.rect.w
        ents = achievements.entries(p)
        for i, e in enumerate(ents):
            a, tier, nxt, val, ok, reward = e
            g = self.panel.add(Group((10, 10 + i * 112, W - 20, 100), lambda s, r, e=e: self._draw_ach(s, r, e)))
            bx = W - 20 - 200 if not self.rtl else 0
            if nxt is None:
                g.add(Button((0, 0, 180, 58), self.tr("missions.complete"), None, theme.GREY, 18, enabled=False), bx + 10, 21)
            else:
                g.add(Button((0, 0, 180, 58), self.tr("missions.claim"), lambda aid=a["id"]: self.claim_ach(aid),
                             theme.CYAN if ok else theme.GREY, 20, enabled=ok, sublabel="%d %s" % (reward, self.tr("common.gems"))),
                      bx + 10, 21)
        self.panel.content_size = 20 + len(ents) * 112

    def _draw_ach(self, surf, r, e):
        a, tier, nxt, val, ok, reward = e
        theme.draw_panel(surf, r, (30, 36, 46), theme.CYAN if ok else theme.PANEL_BORDER, 16)
        tiers = len(a["thresholds"])
        sx = r.x + 30 if not self.rtl else r.right - 30
        for i in range(tiers):
            x = sx + (i * 26 if not self.rtl else -i * 26)
            theme.draw_star(surf, (x, r.y + 26), 11, theme.YELLOW if i < tier else (78, 84, 96))
        tx = r.x + 24 + tiers * 26 + 10 if not self.rtl else r.right - 24 - tiers * 26 - 10
        text.draw(surf, self.tr("ach.%s.name" % a["id"]), (tx, r.y + 12), 22, theme.WHITE, "start", max_width=r.w - 400)
        goal = nxt if nxt is not None else a["thresholds"][-1]
        text.draw(surf, self.tr("ach.%s.desc" % a["id"], n="{:,}".format(goal)), (r.x + 24 if not self.rtl else r.right - 24, r.y + 44), 15, theme.TEXT_DIM, "start", max_width=r.w - 260)
        bar = pygame.Rect(r.x + 24 if not self.rtl else r.x + 230, r.y + 70, r.w - 254, 16)
        ProgressBar.draw(surf, bar, min(1.0, val / max(1, goal)), theme.CYAN, rtl=self.rtl,
                         label="{:,} / {:,}".format(min(val, goal), goal), label_size=12)

    def claim_ach(self, aid):
        g = achievements.claim(self.game.profile, aid)
        if g:
            self.game.audio.play("reward")
            self.game.toasts.push(self.tr("reward.gems", n=g), theme.CYAN)
            keep = self.panel.target
            self.build()
            self.panel.scroll_to(keep, True)

    # ------------------------------------------------------------ daily rewards
    def _build_rewards(self):
        p = self.game.profile
        W = self.panel.rect.w
        g = self.panel.add(Group((0, 0, W, 420), self._draw_calendar))
        avail = p.daily_reward_available()
        g.add(Button((0, 0, 320, 80), self.tr("daily.claim") if avail else self.tr("daily.claimed_today"),
                     self.claim_daily, theme.GREEN if avail else theme.GREY, 28, enabled=avail), W // 2 - 160, 300)
        self.panel.content_size = 420

    def _draw_calendar(self, surf, r):
        p = self.game.profile
        table = self.game.data.progression["daily_rewards"]
        today = p.daily_reward_day()
        avail = p.daily_reward_available()
        text.draw(surf, self.tr("daily.subtitle"), (r.centerx, r.y + 20), 24, theme.WHITE, "center")
        n = len(table)
        cw, gap = 138, 14
        x0 = r.centerx - (n * cw + (n - 1) * gap) // 2
        for i, rew in enumerate(table):
            idx = (n - 1 - i) if self.rtl else i
            cr = pygame.Rect(x0 + idx * (cw + gap), r.y + 80, cw, 180)
            claimed = i < today or (i == today and not avail)
            current = i == today and avail
            col = theme.GREEN if current else (theme.GREY if claimed else theme.PANEL_BORDER)
            theme.draw_panel(surf, cr, (30, 36, 46) if not claimed else (24, 27, 34), col, 16, True, 4 if current else 3)
            text.draw(surf, self.tr("daily.day", n=i + 1), (cr.centerx, cr.y + 22), 18, theme.WHITE, "center", "middle")
            ic = pygame.Rect(cr.centerx - 34, cr.y + 48, 68, 68)
            (icons.coin if rew["type"] == "coins" else icons.gem)(surf, ic)
            text.draw(surf, "x%d" % rew["amount"], (cr.centerx, cr.y + 140), 22, theme.YELLOW, "center", "middle", rtl=False)
            if claimed:
                icons.check(surf, pygame.Rect(cr.right - 44, cr.y + 4, 40, 40))

    def claim_daily(self):
        r = self.game.profile.claim_daily_reward()
        if r:
            self.game.audio.play("reward")
            self.game.toasts.push(self.tr("daily.claimed", reward=reward_text(self, r)), theme.GREEN)
            self.build()

    def draw_content(self, surf):
        self.draw_header(surf)
