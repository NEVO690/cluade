"""In-battle heads-up display: score, timer, super button, kill feed, banners."""
import math

import pygame

from ilbrawl import config
from ilbrawl.characters import sprites
from ilbrawl.localization import i18n as i18n_mod
from ilbrawl.ui import text, theme

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H
BLUE, RED = config.TEAM_COLORS


class HUD:
    def __init__(self, world, i18n, settings):
        self.world = world
        self.i18n = i18n
        self.settings = settings
        self.feed = []   # [text, color, time_left]
        self.t = 0.0
        self.big_text = None
        self.big_t = 0.0

    def tr(self, _k, **kw):
        return self.i18n.t(_k, **kw)

    @property
    def rtl(self):
        return self.i18n.rtl

    def X(self, x, w=0):
        return VW - x - w if self.rtl else x

    def on_events(self, events):
        w = self.world
        for e in events:
            if e["ev"] == "death":
                v, k = e["victim"], e["killer"]
                if k is not None and k is not v:
                    msg = self.tr("hud.kill_feed", killer=k.name, victim=v.name)
                else:
                    msg = self.tr("hud.knocked_out", victim=v.name)
                mine = w.player is not None and v.team == w.player.team
                self.feed.insert(0, [msg, RED if mine else BLUE, 4.0])
                del self.feed[5:]
            elif e["ev"] == "go":
                self.big_text, self.big_t = self.tr("hud.go"), 0.9
            elif e["ev"] == "goal":
                pass

    def update(self, dt):
        self.t += dt
        for f in self.feed:
            f[2] -= dt
        self.feed = [f for f in self.feed if f[2] > 0]
        self.big_t = max(0.0, self.big_t - dt)

    # ------------------------------------------------------------ draw
    def draw(self, surf, aiming_super=False):
        w = self.world
        info = w.mode.hud()
        self._draw_top(surf, info)
        self._draw_feed(surf)
        if w.player:
            self._draw_super_button(surf, w.player, aiming_super)
            self._draw_player_card(surf, w.player)
        self._draw_banner(surf)
        if w.state == "countdown":
            n = int(math.ceil(w.countdown))
            f = w.countdown - int(w.countdown)
            size = int(90 + 50 * f)
            text.draw(surf, str(max(1, n)), (VW // 2, VH // 2 - 40), size, theme.YELLOW, "center", "middle", outline=5,
                      rtl=False)
            text.draw(surf, self.tr("mode.%s.name" % w.mode_id), (VW // 2, VH // 2 + 50), 34, theme.WHITE, "center",
                      "middle", outline=3)
            text.draw(surf, self.tr("mode.%s.goal" % w.mode_id), (VW // 2, VH // 2 + 92), 22, theme.TEXT_DIM, "center",
                      "middle", outline=2, max_width=900)
        if self.big_t > 0:
            s = 1.0 + (0.9 - self.big_t) * 0.6
            text.draw(surf, self.big_text, (VW // 2, VH // 2 - 40), int(110 * s), theme.YELLOW, "center", "middle",
                      outline=6)
        p = w.player
        if p and not p.alive and w.state == "play":
            if p.respawn_timer is not None and w.mode.allow_respawn():
                text.draw(surf, self.tr("hud.respawn_in", n=int(math.ceil(max(0, p.respawn_timer)))),
                          (VW // 2, VH // 2 + 120), 34, theme.WHITE, "center", "middle", outline=3)
            else:
                text.draw(surf, self.tr("hud.spectating"), (VW // 2, VH - 120), 26, theme.WHITE, "center", "middle",
                          outline=3)

    def _timer_text(self):
        tl = self.world.mode.time_left()
        if tl is None:
            return ""
        return "%d:%02d" % (int(tl) // 60, int(tl) % 60)

    def _score_panel(self, surf, left_val, right_val, left_col, right_col, mid_icon=None, sub=None):
        cx = VW // 2
        panel = pygame.Rect(cx - 170, 10, 340, 64)
        theme.draw_panel(surf, panel, (20, 24, 31), theme.PANEL_BORDER, 18, True, 3)
        # our team is shown on the reading-start side
        lx, rx = (panel.right - 50, panel.x + 50) if self.rtl else (panel.x + 50, panel.right - 50)
        text.draw(surf, str(left_val), (lx, panel.centery), 40, left_col, "center", "middle", outline=3, rtl=False)
        text.draw(surf, str(right_val), (rx, panel.centery), 40, right_col, "center", "middle", outline=3, rtl=False)
        if mid_icon:
            mid_icon(surf, (cx, panel.centery - 8))
        text.draw(surf, self._timer_text(), (cx, panel.bottom - 16), 20, theme.WHITE, "center", "middle", rtl=False)
        if sub:
            text.draw(surf, sub, (cx, panel.bottom + 18), 20, theme.YELLOW, "center", "middle", outline=2)

    def _draw_top(self, surf, info):
        w = self.world
        my = w.player.team if w.player else 0
        t = info.get("type")

        def ab(a, b):
            return (a, b) if my == 0 else (b, a)

        if t == "gems":
            a, b = ab(info["a"], info["b"])
            sub = None
            if info.get("countdown") is not None:
                leader_mine = info["leader"] == my
                sub = self.tr("hud.gem_countdown_us" if leader_mine else "hud.gem_countdown_them",
                              n=int(math.ceil(info["countdown"])))
            self._score_panel(surf, a, b, BLUE, RED,
                              lambda s, p: theme.draw_gem_icon(s, p, 13, (184, 100, 255)), sub)
        elif t == "goals":
            a, b = ab(info["a"], info["b"])
            self._score_panel(surf, a, b, BLUE, RED, lambda s, p: pygame.draw.circle(s, theme.YELLOW, p, 11))
        elif t == "zones":
            a, b = ab(info["a"], info["b"])
            self._score_panel(surf, a, b, BLUE, RED, None, None)
            n = len(info["zones"])
            for i, (owner, cap, contested) in enumerate(info["zones"]):
                zx = VW // 2 + (i - (n - 1) / 2) * 34
                col = (200, 200, 210) if owner is None else (BLUE if owner == my else RED)
                pygame.draw.circle(surf, theme.INK, (int(zx), 38), 13)
                pygame.draw.circle(surf, col, (int(zx), 38), 10)
                if contested and int(self.t * 4) % 2:
                    pygame.draw.circle(surf, theme.WHITE, (int(zx), 38), 13, 2)
            # progress bars
            for side, val, col in ((0, info["a"] if my == 0 else info["b"], BLUE), (1, info["b"] if my == 0 else info["a"], RED)):
                bw = 120
                x = VW // 2 - 170 - bw - 12 if (side == 0) != self.rtl else VW // 2 + 170 + 12
                r = pygame.Rect(x, 30, bw, 14)
                pygame.draw.rect(surf, theme.INK, r.inflate(4, 4), border_radius=8)
                pygame.draw.rect(surf, (26, 30, 38), r, border_radius=7)
                fw = int(bw * min(1.0, val / info["target"]))
                if fw:
                    fr = pygame.Rect(r.right - fw if (side == 0) == self.rtl else r.x, r.y, fw, r.h)
                    pygame.draw.rect(surf, col, fr, border_radius=7)
        elif t == "rounds":
            a, b = ab(info["a"], info["b"])
            self._score_panel(surf, a, b, BLUE, RED, None, self.tr("hud.round_n", n=info["round"]))
            # alive pips
            for side, alive, col in ((0, info["alive_a"] if my == 0 else info["alive_b"], BLUE),
                                     (1, info["alive_b"] if my == 0 else info["alive_a"], RED)):
                for i in range(3):
                    base = VW // 2 - 200 - i * 26 if (side == 0) != self.rtl else VW // 2 + 200 + i * 26
                    pygame.draw.circle(surf, theme.INK, (base, 42), 11)
                    pygame.draw.circle(surf, col if i < alive else (70, 60, 90), (base, 42), 8)
        elif t == "solo":
            panel = pygame.Rect(VW // 2 - 130, 10, 260, 64)
            theme.draw_panel(surf, panel, (20, 24, 31), theme.PANEL_BORDER, 18, True, 3)
            text.draw(surf, self.tr("hud.alive", n=info["alive"]), (panel.centerx, panel.y + 22), 26, theme.WHITE,
                      "center", "middle", outline=3)
            if info["poison_in"] > 0:
                sub = self.tr("hud.poison_in", n=int(math.ceil(info["poison_in"])))
                col = theme.GREEN
            else:
                sub = self._timer_text()
                col = theme.WHITE
            text.draw(surf, sub, (panel.centerx, panel.bottom - 17), 19, col, "center", "middle")

    def _draw_feed(self, surf):
        y = 90
        for msg, col, left in self.feed:
            s = text.render(msg, 17, theme.WHITE, True, 2)
            wpx = s.get_width() + 24
            x = VW - 16 - wpx if not self.rtl else 16
            r = pygame.Rect(x, y, wpx, 30)
            a = min(1.0, left)
            panel = pygame.Surface(r.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, tuple(col) + (int(170 * a),), panel.get_rect(), border_radius=10)
            panel.blit(s, (12, (30 - s.get_height()) // 2))
            surf.blit(panel, r.topleft)
            y += 36

    def _draw_banner(self, surf):
        m = self.world.mode
        if not m.banner:
            return
        key, params = m.banner
        params = dict(params)
        my = self.world.player.team if self.world.player else 0
        if "team" in params:
            team = params.pop("team")
            if team == -1:
                params["team"] = ""
            else:
                params["team"] = self.tr("hud.your_team" if team == my else "hud.enemy_team")
                if key in ("hud.goal", "hud.round_won"):
                    key = key + ("_us" if team == my else "_them")
        msg = self.tr(key, **params)
        s = text.render(msg, 44, theme.YELLOW, True, 4)
        r = pygame.Rect(0, 0, s.get_width() + 80, 84)
        r.center = (VW // 2, 190)
        band = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(band, (20, 14, 50, 190), band.get_rect(), border_radius=20)
        surf.blit(band, r.topleft)
        surf.blit(s, (r.centerx - s.get_width() // 2, r.centery - s.get_height() // 2))

    def _draw_super_button(self, surf, p, aiming):
        cx = VW - 90 if not self.rtl else 90
        cy = VH - 90
        r = 52
        charge = p.super_charge
        pygame.draw.circle(surf, theme.INK, (cx, cy + 4), r + 6)
        pygame.draw.circle(surf, (36, 40, 50), (cx, cy), r + 2)
        if charge >= 1:
            pulse = 0.5 + 0.5 * math.sin(self.t * 8)
            col = theme.lerp_color(theme.YELLOW, theme.WHITE, pulse * 0.4)
            pygame.draw.circle(surf, col, (cx, cy), r)
            pygame.draw.circle(surf, theme.ORANGE, (cx, cy), r, 5)
        else:
            if charge > 0:
                pygame.draw.arc(surf, theme.YELLOW, (cx - r, cy - r, r * 2, r * 2), math.pi / 2,
                                math.pi / 2 + charge * 2 * math.pi, 10)
        theme.draw_star(surf, (cx, cy - 4), 22, theme.YELLOW if charge >= 1 else (110, 116, 128))
        keys = self.settings["controls"]
        hint = self.tr("hud.super_hint", key=i18n_mod.key_label(keys["super"]))
        text.draw(surf, hint, (cx, cy + r + 12), 15, theme.WHITE, "center", "middle", max_width=170)
        if aiming:
            pygame.draw.circle(surf, theme.WHITE, (cx, cy), r + 8, 3)

    def _draw_player_card(self, surf, p):
        x = 16 if not self.rtl else VW - 16 - 250
        r = pygame.Rect(x, VH - 84, 250, 68)
        theme.draw_panel(surf, r, (20, 24, 31), theme.PANEL_BORDER, 16, True, 3)
        por = sprites.portrait(p.style, 76, key=(p.char_id, p.skin))
        px = r.x + 2 if not self.rtl else r.right - 78
        surf.blit(por, (px, r.y - 16))
        tx = r.x + 84 if not self.rtl else r.right - 84
        text.draw(surf, self.tr("char.%s.name" % p.char_id), (tx, r.y + 10), 20, theme.WHITE, "start", outline=2)
        bar = pygame.Rect(r.x + 84 if not self.rtl else r.x + 14, r.y + 40, 150, 14)
        pygame.draw.rect(surf, theme.INK, bar.inflate(4, 4), border_radius=8)
        pygame.draw.rect(surf, (40, 28, 28), bar, border_radius=7)
        fw = int(bar.w * p.hp_frac)
        if fw:
            fr = pygame.Rect(bar.right - fw if self.rtl else bar.x, bar.y, fw, bar.h)
            pygame.draw.rect(surf, theme.GREEN, fr, border_radius=7)
        text.draw(surf, "%d" % p.hp, bar.center, 13, theme.WHITE, "center", "middle", rtl=False)
