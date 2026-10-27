"""HUD, pause, victory and results screens."""

import math

from direct.gui.DirectGui import DirectFrame

from ....game.game_state import GameState, Outcome
from ..theme import c
from ..widgets import Button, label, panel
from .common import BaseScreen


class HudScreen(BaseScreen):
    name = "hud"
    uses_menu_scene = False
    music = None

    def build(self):
        th = self.theme
        self.session = None
        top = panel(self.root, th, (-0.5, 0.5, -0.08, 0.08), "dark", 0.6, 0.06, shadow=False, pos=(0, 0, 0.88))
        self.round_lab = label(top, th, "", (0, 0.015), 0.04, "muted", "bold")
        self.time_lab = label(top, th, "", (0, -0.05), 0.05, "text", "title")
        self.qual = panel(self.root, th, (-0.32, 0.32, -0.07, 0.07), "dark", 0.6, 0.06, shadow=False,
                          pos=(-1.35, 0, 0.86))
        self.qual_lab = label(self.qual, th, "", (0, -0.018), 0.045, "secondary", "bold")
        self.pos_frame = panel(self.root, th, (-0.25, 0.25, -0.1, 0.1), "dark", 0.6, 0.06, shadow=False,
                               pos=(1.42, 0, 0.82))
        self.pos_lab = label(self.pos_frame, th, "", (0, -0.035), 0.1, "text", "title")
        self.pos_sub = label(self.pos_frame, th, "POSITION", (0, 0.055), 0.025, "muted", "bold")
        # Course progress strip with one dot per player.
        self.strip = DirectFrame(parent=self.root, frameColor=c("dark", 0.5), frameSize=(-0.012, 0.012, -0.5, 0.5),
                                 pos=(1.65, 0, -0.1))
        self.dots = {}
        self.banner = label(self.root, th, "", (0, 0.25), 0.16, "secondary", "title")
        self.banner_sub = label(self.root, th, "", (0, 0.12), 0.055, "text", "bold")
        self.banner_t = 0.0
        self.banner_big = False
        self.count_lab = label(self.root, th, "", (0, -0.05), 0.3, "secondary", "title")
        self.intro = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        self.feed_items = []
        self.toast_lab = label(self.root, th, "", (0, 0.55), 0.05, "accent", "bold")
        self.toast_t = 0.0
        self.hint = label(self.root, th, "WASD move  SPACE jump  SHIFT walk  MOUSE/Q/E camera  ESC pause",
                          (-1.65, -0.94), 0.03, "muted", "body", "left")
        self.spec_lab = label(self.root, th, "", (0, -0.78), 0.045, "text", "bold")
        self.results = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        self.results.hide()

    def on_show(self, session=None, **kw):
        if session is not None:
            self.session = session
            for d in self.dots.values():
                d.destroy()
            self.dots = {}
            self.results.hide()

    # ------------------------------------------------------------------ messages
    def round_intro(self, n, total, loaded_map, sub):
        self.intro.destroy()
        self.intro = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        p = panel(self.intro, self.theme, (-0.9, 0.9, -0.22, 0.22), "panel", 0.92, 0.1, pos=(0, 0, 0.42))
        label(p, self.theme, "ROUND %d / %d" % (n, total), (0, 0.12), 0.045, "muted", "bold")
        label(p, self.theme, loaded_map.name, (0, 0.02), 0.09, "secondary", "title")
        rule = ("Fall = back to the last checkpoint" if loaded_map.fall_rule == "respawn"
                else "Fall once and you are OUT")
        label(p, self.theme, sub, (0, -0.08), 0.045, "text", "bold")
        label(p, self.theme, rule, (0, -0.15), 0.036, "accent", "body")
        self.intro_t = 3.6
        self.results.hide()
        for d in self.dots.values():
            d.destroy()
        self.dots = {}

    def flash(self, text, sub, color, duration, big=False):
        self.banner["text"] = text
        self.banner["text_fg"] = c(color)
        self.banner_sub["text"] = sub
        self.banner_t = duration
        self.banner_big = big

    def toast(self, text):
        self.toast_lab["text"] = text
        self.toast_t = 1.8

    def feed(self, text, color="text"):
        lab = label(self.root, self.theme, text, (-1.65, 0.6), 0.035, color, "bold", "left")
        self.feed_items.insert(0, [lab, 4.0])
        for it in self.feed_items[6:]:
            it[0].destroy()
        del self.feed_items[6:]

    # ------------------------------------------------------------------ round results overlay
    def show_round_results(self, history_entry):
        s = self.session
        map_id, results = history_entry
        self.results.destroy()
        self.results = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0.45), frameSize=(-3, 3, -1.2, 1.2))
        th = self.theme
        p = panel(self.results, th, (-1.0, 1.0, -0.78, 0.78), "panel", 0.95, 0.1)
        m = self.session.app.maps.get(map_id)
        label(p, th, "ROUND RESULTS", (0, 0.66), 0.08, "secondary", "title")
        label(p, th, m.name, (0, 0.585), 0.04, "muted", "bold")
        cols = 2
        per_col = 9
        for i, r in enumerate(results[: cols * per_col]):
            col, row = divmod(i, per_col)
            x = -0.92 + col * 0.95
            y = 0.48 - row * 0.085
            out = r.outcome == Outcome.ELIMINATED
            me = r.id == s.LOCAL
            color = "danger" if out else ("secondary" if r.outcome == Outcome.WINNER else "success")
            bg = DirectFrame(parent=p, frameColor=c("primary" if me else "dark", 0.55 if me else 0.35),
                             frameSize=(0, 0.88, -0.035, 0.035), pos=(x, 0, y))
            bg.setTransparency(1)
            label(bg, th, "%d." % r.place, (0.06, -0.012), 0.035, "muted", "bold", "right")
            label(bg, th, r.name[:16], (0.09, -0.012), 0.035, "text", "bold", "left")
            tag = {"winner": "WINNER", "qualified": "QUALIFIED", "eliminated": "OUT"}[r.outcome]
            if r.time is not None:
                tag += "  %.1fs" % r.time
            label(bg, th, tag, (0.86, -0.012), 0.03, color, "bold", "right")
        local_out = s.gm.local_out
        if local_out and not s.gm.round.is_final:
            label(p, th, "You were eliminated. Watch the rest of the show or head back.", (0, -0.55), 0.04,
                  "text", "body")
            Button(p, th, "SPECTATE", (-0.3, -0.67), (0.5, 0.1), self._continue, color="blue")
            Button(p, th, "LEAVE SHOW", (0.3, -0.67), (0.5, 0.1), self._leave, color="danger")
        else:
            Button(p, th, "CONTINUE", (0, -0.67), (0.6, 0.11), self._continue, color="primary")
        self.results.show()
        self.session.keyboard.capture_mouse(False)

    def _continue(self):
        self.results.hide()
        if self.session is not None:
            self.session.keyboard.capture_mouse(True)
            self.session.gm.continue_after_results()

    def _leave(self):
        self.results.hide()
        if self.session is not None:
            self.session.leave()

    # ------------------------------------------------------------------ per frame
    def update(self, dt):
        s = self.session
        if s is None or s.gm.round is None:
            return
        gm = s.gm
        rnd = gm.round
        self.round_lab["text"] = "ROUND %d/%d  -  %s" % (gm.round_index + 1, gm.total_rounds, rnd.map.name)
        if gm.state == GameState.COUNTDOWN:
            remaining = gm.settings.countdown - gm.state_time
            n = int(math.ceil(remaining))
            self.count_lab["text"] = str(n) if 0 < n <= 3 else ""
            if getattr(self, "_last_count", None) != n and 0 < n <= 3:
                s.app.sounds.play("beep")
            self._last_count = n
            self.time_lab["text"] = "%d:%02d" % divmod(int(rnd.world.time_limit), 60)
        else:
            self.count_lab["text"] = ""
            tl = rnd.time_left
            self.time_lab["text"] = "%d:%02d" % divmod(int(math.ceil(tl)), 60)
            self.time_lab["text_fg"] = c("danger") if tl < 15 else c("text")
        if rnd.is_final:
            self.qual_lab["text"] = "FINAL - WIN IT!"
        else:
            self.qual_lab["text"] = "QUALIFIED %d / %d" % (len(rnd.finish_order), rnd.qualify_count)
        me = rnd.by_id(s.LOCAL)
        standings = rnd.standings()
        if me is not None and not gm.local_out:
            place = standings.index(me) + 1
            self.pos_lab["text"] = "#%d" % place
            self.pos_frame.show()
            self.spec_lab["text"] = ""
        else:
            self.pos_frame.hide()
            f = s.focus_char()
            self.spec_lab["text"] = ("SPECTATING  %s   (A / D to switch)" % f.name) if f else ""
        # progress dots
        length = max(1.0, rnd.world.route.length)
        for ch in rnd.characters:
            d = self.dots.get(ch.id)
            if d is None:
                col = c("secondary") if ch.id == s.LOCAL else c("text", 0.8)
                size = 0.025 if ch.id == s.LOCAL else 0.014
                d = DirectFrame(parent=self.strip, frameColor=col, frameSize=(-size, size, -size, size),
                                frameTexture=self.theme.rounded(1.0, 0.5, 0.0))
                d.setTransparency(1)
                self.dots[ch.id] = d
            frac = max(0.0, min(1.0, ch.progress / length))
            d.setZ(-0.5 + frac)
            d.setAlphaScale(0.3 if ch.eliminated else 1.0)
        # banners
        if self.banner_t > 0:
            self.banner_t -= dt
            a = min(1.0, self.banner_t / 0.3)
            self.banner.setAlphaScale(a)
            self.banner_sub.setAlphaScale(a)
        else:
            self.banner["text"] = ""
            self.banner_sub["text"] = ""
        if getattr(self, "intro_t", 0) > 0:
            self.intro_t -= dt
            self.intro.setAlphaScale(min(1.0, self.intro_t / 0.4))
            if self.intro_t <= 0:
                self.intro.hide()
        if self.toast_t > 0:
            self.toast_t -= dt
            self.toast_lab.setAlphaScale(min(1.0, self.toast_t / 0.3))
        else:
            self.toast_lab["text"] = ""
        keep = []
        for i, it in enumerate(self.feed_items):
            it[1] -= dt
            if it[1] <= 0:
                it[0].destroy()
                continue
            it[0].setZ(0.6 - i * 0.055)
            it[0].setAlphaScale(min(1.0, it[1]))
            keep.append(it)
        self.feed_items = keep
        # spectate switching
        if gm.local_out and s.keyboard is not None:
            left, right = s.keyboard.pressed("left"), s.keyboard.pressed("right")
            if left and not getattr(self, "_l", False):
                s.cycle_spectate(-1)
            if right and not getattr(self, "_r", False):
                s.cycle_spectate(1)
            self._l, self._r = left, right

    def on_escape(self):
        if self.session is not None and not self.results.isHidden():
            return True
        if self.session is not None:
            self.app.screens.show("pause", session=self.session)
        return True


class PauseScreen(BaseScreen):
    name = "pause"
    uses_menu_scene = False
    music = None

    def build(self):
        th = self.theme
        DirectFrame(parent=self.root, frameColor=(0.05, 0.02, 0.15, 0.6), frameSize=(-3, 3, -1.2, 1.2))
        p = panel(self.root, th, (-0.55, 0.55, -0.5, 0.5), "panel", 0.95, 0.1)
        label(p, th, "PAUSED", (0, 0.36), 0.1, "secondary", "title")
        self.note = label(p, th, "", (0, 0.26), 0.035, "muted", "body")
        Button(p, th, "RESUME", (0, 0.12), (0.7, 0.12), self._resume, color="primary")
        Button(p, th, "SETTINGS", (0, -0.03), (0.7, 0.1), lambda: self.app.screens.show("settings"),
               color="panel_hi")
        Button(p, th, "LEAVE SHOW", (0, -0.17), (0.7, 0.1), self._leave, color="danger")
        label(p, th, "Leaving counts as a quit: no win, small rank penalty.", (0, -0.33), 0.03, "muted", "body",
              wordwrap=30)

    def on_show(self, session=None, **kw):
        self.session = session or self.app.session
        if self.session is not None:
            self.session.set_paused(True)
            self.note["text"] = "The show is frozen while you are paused."

    def _resume(self):
        if self.session is not None:
            self.session.set_paused(False)
        self.app.screens.show("hud", push=False)

    def _leave(self):
        s = self.session
        if s is not None:
            s.set_paused(False)
            s.paused = True
            s.leave()

    def on_escape(self):
        self._resume()
        return True


class VictoryScreen(BaseScreen):
    name = "victory"
    scene_offset = 0.0
    music = None

    def build(self):
        th = self.theme
        self.title = label(self.root, th, "VICTORY!", (0, 0.62), 0.24, "secondary", "title")
        label(self.root, th, "YOU WON THE SHOW!", (0, 0.47), 0.07, "text", "title")
        self.t = 0.0
        Button(self.root, th, "SEE REWARDS", (0, -0.8), (0.7, 0.12), lambda: self.app.screens.reset_to("results"),
               color="primary")

    def on_show(self, **kw):
        self.t = 0.0
        self.app.menu_scene.celebrate()
        self.app.sounds.play("victory")

    def update(self, dt):
        self.t += dt
        self.title.setScale(1.0 + 0.05 * math.sin(self.t * 5))
        self.title.setR(math.sin(self.t * 2.3) * 3)


class ResultsScreen(BaseScreen):
    """Final standings + everything earned (coins, XP, level ups, rank, titles, quests, achievements)."""

    name = "results"
    scene_offset = 2.0

    def build(self):
        self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))

    def on_show(self, **kw):
        th = self.theme
        self.holder.destroy()
        self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        res = self.app.last_result or {}
        rep = res.get("report")
        summ = res.get("summary")
        h = self.holder
        if rep is not None and rep.won:
            head, col = "CHAMPION!", "secondary"
        elif rep is not None and rep.quit_early:
            head, col = "LEFT THE SHOW", "muted"
        else:
            head, col = ("FINISHED #%d" % rep.placement) if rep and rep.placement else "SHOW OVER", "accent"
        label(h, th, head, (-0.75, 0.78), 0.12, col, "title")
        if res.get("champion"):
            label(h, th, "Show winner: %s" % res["champion"], (-0.75, 0.68), 0.045, "text", "bold")
        # Left: rounds & standings
        p = panel(h, th, (-0.85, 0.85, -0.55, 0.55), "panel", 0.92, 0.08, pos=(-0.75, 0, 0.05))
        label(p, th, "YOUR ROUNDS", (-0.78, 0.46), 0.042, "muted", "bold", "left")
        y = 0.38
        for r in (rep.rounds if rep else []):
            m = self.app.maps.maps.get(r["map_id"])
            txt = "%s  -  %s%s" % (m.name if m else r["map_id"], r["outcome"].upper(),
                                   ("  (%.1fs)" % r["time"]) if r.get("time") else "")
            label(p, th, txt, (-0.78, y), 0.038, "success" if r["outcome"] != "eliminated" else "danger",
                  "bold", "left")
            y -= 0.065
        if rep:
            stats = "Jumps %d   Obstacles cleared %d   Falls %d   Hits taken %d   Bonks %d" % (
                rep.jumps, rep.obstacles_cleared, rep.falls, rep.hits, rep.bonks)
            label(p, th, stats, (-0.78, y - 0.02), 0.03, "muted", "body", "left", wordwrap=52)
        label(p, th, "FINAL STANDINGS", (-0.78, -0.02), 0.042, "muted", "bold", "left")
        for i, (place, name, me) in enumerate((res.get("standings") or [])[:10]):
            col_i, row = divmod(i, 5)
            label(p, th, "%d. %s" % (place, name[:14]), (-0.78 + col_i * 0.82, -0.1 - row * 0.075), 0.036,
                  "secondary" if me else "text", "bold", "left")
        # Right: rewards
        q = panel(h, th, (-0.62, 0.62, -0.7, 0.7), "panel", 0.92, 0.08, pos=(1.05, 0, 0.05))
        label(q, th, "REWARDS", (0, 0.6), 0.06, "secondary", "title")
        y = 0.5
        if summ is None:
            label(q, th, "No rewards for this show.", (0, y), 0.04, "muted", "body")
        else:
            if not summ.saved:
                label(q, th, "WARNING: progress could not be saved to disk!", (0, y), 0.035, "danger", "bold")
                y -= 0.06
            for text, amount in summ.coins[:7]:
                label(q, th, text[:30], (-0.56, y), 0.034, "text", "body", "left")
                label(q, th, "+%d" % amount, (0.56, y), 0.036, "secondary", "bold", "right")
                y -= 0.055
            label(q, th, "BONK COINS  +%d" % summ.total_coins, (0, y - 0.01), 0.048, "secondary", "title")
            y -= 0.09
            label(q, th, "XP  +%d" % summ.total_xp, (0, y), 0.048, "accent", "title")
            y -= 0.08
            for lvl, coins in summ.levels_gained:
                label(q, th, "LEVEL UP!  Level %d  (+%d coins)" % (lvl, coins), (0, y), 0.038, "success", "bold")
                y -= 0.055
            sign = "+" if summ.rank_delta >= 0 else ""
            rank_txt = "RANK  %s%d RP" % (sign, summ.rank_delta) if not res.get("online") else \
                "Online show: local rank unchanged"
            if summ.rank_before != summ.rank_after:
                rank_txt += "   %s -> %s" % (summ.rank_before, summ.rank_after)
            label(q, th, rank_txt, (0, y), 0.04, "blue", "bold")
            y -= 0.07
            defs = self.app.profile.titles.defs
            for t in summ.new_titles:
                label(q, th, "NEW TITLE: %s" % defs[t]["name"], (0, y), 0.036, "purple", "bold")
                y -= 0.05
            adefs = self.app.profile.achievements.defs
            for aid, coins in summ.achievements:
                label(q, th, "ACHIEVEMENT: %s (+%d)" % (adefs[aid]["name"], coins), (0, y), 0.033, "success",
                      "bold")
                y -= 0.05
            for qd in summ.quests_completed:
                label(q, th, "QUEST DONE: %s" % qd["text"], (0, y), 0.033, "accent", "bold")
                y -= 0.05
        lb = res.get("leaderboard")
        if lb:
            label(h, th, "SERVER LEADERBOARD (verified online results)", (-0.75, -0.62), 0.036, "secondary", "bold")
            label(h, th, "   ".join("%d. %s %dpts" % (i + 1, r["name"], r["points"]) for i, r in enumerate(lb[:5])),
                  (-0.75, -0.68), 0.032, "text", "body", wordwrap=70)
        if res.get("online"):
            Button(h, th, "BACK TO ROOM", (-1.05, -0.85), (0.6, 0.11),
                   lambda: self.app.screens.reset_to("multiplayer"), color="blue")
        else:
            Button(h, th, "PLAY AGAIN", (-1.05, -0.85), (0.6, 0.11), self._again, color="primary")
        Button(h, th, "MAIN MENU", (-0.4, -0.85), (0.55, 0.11), lambda: self.app.screens.reset_to("main"),
               color="panel_hi")
        if summ is not None and summ.total_coins:
            self.app.sounds.play("coin")

    def _again(self):
        s = self.app.profile.settings
        from ...session import ShowConfig
        res = self.app.last_result or {}
        rep = res.get("report")
        maps = self.app.maps.show_playlist()
        if rep is not None and rep.mode == "quick_play" and rep.rounds:
            maps = [rep.rounds[0]["map_id"]]
        self.app.start_show(ShowConfig(maps, s["bot_count"], s["bot_difficulty"],
                                       mode=rep.mode if rep else "ai_showdown"))

