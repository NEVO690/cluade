"""PROFILE, LEVELS, RANKS, TITLES, QUESTS and ACHIEVEMENTS screens."""

import datetime
import time

from direct.gui.DirectGui import DirectEntry, DirectFrame

from ..theme import c
from ..widgets import Button, ProgressBar, ScrollList, label, panel
from .common import BaseScreen, player_card


class ProfileScreen(BaseScreen):
    name = "profile"
    scene_offset = -1.15

    def build(self):
        self.header("PROFILE")
        self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))

    def on_show(self, **kw):
        th = self.theme
        prof = self.app.profile
        self.refresh_coins()
        self.holder.destroy()
        h = self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        player_card(h, th, prof, (0.75, 0.55), 1.5)
        label(h, th, "NAME", (0.05, 0.27), 0.035, "muted", "bold", "left")
        self.entry = DirectEntry(parent=h, initialText=prof.name, scale=0.05, width=12, pos=(0.05, 0, 0.18),
                                 frameColor=c("dark", 0.8), text_fg=c("text"), entryFont=th.font("bold"),
                                 focusOutCommand=self._save_name, command=self._save_name)
        Button(h, th, "SAVE NAME", (1.05, 0.2), (0.34, 0.08), self._save_name, color="blue", scale=0.032)
        st = prof.stats
        rows = [
            ("Shows played", st["games_played"]), ("Shows won", st["wins"]),
            ("Rounds qualified", st["rounds_qualified"]), ("Finish lines", st["finishes"]),
            ("Jumps", st["jumps"]), ("Obstacles cleared", st["obstacles"]), ("Falls", st["falls"]),
            ("Head bonks", st["bonks"]), ("Best win streak", st["best_streak"]),
            ("Best placement", st["best_placement"] or "-"),
        ]
        p = panel(h, th, (-0.75, 0.75, -0.3, 0.3), "panel", 0.9, 0.08, pos=(0.75, 0, -0.25))
        for i, (k, v) in enumerate(rows):
            col, row = divmod(i, 5)
            label(p, th, k, (-0.7 + col * 0.75, 0.2 - row * 0.1), 0.035, "muted", "body", "left")
            label(p, th, str(v), (-0.05 + col * 0.75, 0.2 - row * 0.1), 0.04, "text", "bold", "right")
        bt = prof.stats["best_times"]
        if bt:
            txt = "   ".join("%s %.1fs" % (self.app.maps.maps[m].name if m in self.app.maps.maps else m, t)
                             for m, t in bt.items())
            label(h, th, "Best times: " + txt, (0.75, -0.62), 0.03, "accent", "bold", wordwrap=60)
        for i, (text, scr) in enumerate((("LEVELS", "levels"), ("RANKS", "ranks"), ("TITLES", "titles"),
                                         ("ACHIEVEMENTS", "achievements"))):
            Button(h, th, text, (0.05 + i * 0.4, -0.78), (0.37, 0.1), self.app.screens.show, [scr],
                   color="purple", scale=0.038)

    def _save_name(self, *args):
        prof = self.app.profile
        new = prof.set_setting("player_name", self.entry.get())
        prof.save()
        self.entry.enterText(new)
        self.app.toasts.show("Name saved: %s" % new)


class LevelsScreen(BaseScreen):
    name = "levels"
    uses_menu_scene = False

    def build(self):
        self.header("LEVELS & XP")
        self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))

    def on_show(self, **kw):
        th = self.theme
        prof = self.app.profile
        xp = prof.xp
        self.holder.destroy()
        h = self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        p = panel(h, th, (-1.4, 1.4, -0.22, 0.22), "panel", 0.92, 0.08, pos=(0, 0, 0.45))
        label(p, th, "LEVEL %d" % xp.level, (-1.3, 0.07), 0.1, "accent", "title", "left")
        need = xp.xp_to_next()
        label(p, th, ("%d / %d XP to level %d" % (xp.xp, need, xp.level + 1)) if need else "MAX LEVEL",
              (1.3, 0.09), 0.045, "text", "bold", "right")
        ProgressBar(p, th, (-1.3, 1.3, -0.14, -0.06), xp.progress_fraction(), "accent")
        label(p, th, "Total XP earned: {:,}".format(prof.data["progress"]["total_xp"]), (1.3, 0.02), 0.032,
              "muted", "body", "right")
        label(h, th, "UPCOMING LEVEL REWARDS", (-1.35, 0.13), 0.045, "secondary", "title", "left")
        lst = ScrollList(h, th, (-1.4, 1.4, -0.8, 0.08))
        for lvl in range(max(2, xp.level - 2), min(xp.max_level, xp.level + 12) + 1):
            row = lst.add_row(0.08)
            got = lvl <= xp.level
            bg = panel(row, th, (0, lst.width, -0.037, 0.037), "panel_hi" if lvl == xp.level + 1 else "panel",
                       0.85, 0.03, shadow=False, pos=(-1.4, 0, 0))
            label(bg, th, "Level %d" % lvl, (0.05, -0.013), 0.038, "text", "bold", "left")
            label(bg, th, "%d XP" % xp.xp_to_next(lvl - 1), (1.1, -0.013), 0.034, "muted", "body", "right")
            label(bg, th, "+%d BONK COINS" % xp.level_reward(lvl), (2.0, -0.013), 0.036, "secondary", "bold",
                  "right")
            label(bg, th, "RECEIVED" if got else "", (lst.width - 0.05, -0.013), 0.034, "success", "bold", "right")
        label(h, th, "XP comes from playing, qualifying, finishing, winning, obstacles and quests.",
              (0.3, -0.9), 0.034, "muted", "body")


class RanksScreen(BaseScreen):
    name = "ranks"
    uses_menu_scene = False

    def build(self):
        self.header("RANKS", subtitle="Local rank vs bots - fixed point rules, never random")
        self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))

    def on_show(self, **kw):
        th = self.theme
        r = self.app.profile.ranks
        self.holder.destroy()
        h = self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        cur = r.tier["id"]
        for i, t in enumerate(r.tiers):
            x = -1.4 + i * 0.4
            active = t["id"] == cur
            p = panel(h, th, (-0.18, 0.18, -0.2, 0.2), "panel_hi" if active else "panel", 0.92, 0.06,
                      pos=(x + 0.15, 0, 0.42))
            label(p, th, t["id"], (0, 0.05), 0.034 if len(t["id"]) < 10 else 0.028, t["color"], "title")
            label(p, th, "%d RP" % t["min_points"], (0, -0.06), 0.03, "muted", "bold")
            if active:
                label(p, th, "YOU", (0, -0.15), 0.03, "secondary", "title")
        nxt = r.next_tier()
        p = panel(h, th, (-1.4, 1.4, -0.12, 0.12), "panel", 0.9, 0.06, pos=(0, 0, 0.07))
        if nxt:
            frac = (r.points - r.tier["min_points"]) / float(nxt["min_points"] - r.tier["min_points"])
            label(p, th, "%d RP  -  %d more to %s" % (r.points, nxt["min_points"] - r.points, nxt["id"]),
                  (0, 0.03), 0.045, "text", "bold")
            ProgressBar(p, th, (-1.3, 1.3, -0.08, -0.04), frac, "blue")
        else:
            label(p, th, "%d RP - top rank reached!" % r.points, (0, -0.01), 0.05, "secondary", "title")
        rules = r.d["points"]
        mult = r.d["difficulty_multiplier"]
        txt = ("HOW RANK POINTS WORK\n"
               "Win the show: +%d     Reach the final: +%d     Each round qualified: +%d\n"
               "Out in round 1: %d     Leaving a show early: %d\n"
               "Positive points are scaled by bot difficulty: EASY x%.1f, NORMAL x%.1f, HARD x%.1f, CHAOTIC x%.1f"
               % (rules["win"], rules["reached_final"], rules["per_round_qualified"], rules["first_round_out"],
                  rules["quit"], mult["EASY"], mult["NORMAL"], mult["HARD"], mult["CHAOTIC"]))
        label(h, th, txt, (0, -0.25), 0.038, "text", "body")
        label(h, th, "Online ranking: only results verified by a BONK! server count (see MULTIPLAYER).",
              (0, -0.62), 0.035, "muted", "body")


class TitlesScreen(BaseScreen):
    name = "titles"
    uses_menu_scene = False

    def build(self):
        self.header("TITLES", subtitle="Earn titles by meeting their conditions, then wear one")
        self.list = ScrollList(self.root, self.theme, (-1.5, 1.5, -0.8, 0.65))

    def on_show(self, **kw):
        self.refresh()

    def refresh(self):
        th = self.theme
        prof = self.app.profile
        tm = prof.titles
        rarities = prof.catalog.rarities
        self.list.clear()
        for tid in tm.order:
            d = tm.defs[tid]
            unlocked = tm.is_unlocked(tid)
            row = self.list.add_row(0.12)
            bg = panel(row, th, (0, self.list.width, -0.055, 0.055), "panel" if unlocked else "dark", 0.9, 0.05,
                       shadow=False, pos=(-1.5, 0, 0))
            col = rarities[d["rarity"]].color
            label(bg, th, d["name"], (0.05, 0.0), 0.05, col if unlocked else "locked", "title", "left")
            label(bg, th, d["rarity"] + "  -  " + d["description"], (0.05, -0.042), 0.03, "muted", "body", "left")
            if unlocked:
                eq = tm.equipped == tid
                b = Button(bg, th, "EQUIPPED" if eq else "EQUIP", (self.list.width - 0.2, 0), (0.3, 0.08),
                           self._equip, [tid], color="success" if eq else "blue", scale=0.034)
                b.set_enabled(not eq)
            else:
                label(bg, th, "LOCKED", (self.list.width - 0.2, -0.012), 0.04, "locked", "bold")

    def _equip(self, tid):
        prof = self.app.profile
        prof.titles.equip(tid)
        prof.save()
        self.app.toasts.show("Title equipped: %s" % prof.titles.equipped_name())
        self.refresh()


class QuestsScreen(BaseScreen):
    name = "quests"
    scene_offset = -1.2

    def build(self):
        self.header("DAILY QUESTS")
        self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))

    def on_show(self, **kw):
        th = self.theme
        prof = self.app.profile
        changed = prof.quests.refresh()
        if changed:
            prof.save()
        self.holder.destroy()
        h = self.holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        now = datetime.datetime.fromtimestamp(time.time())
        reset = (datetime.datetime(now.year, now.month, now.day) + datetime.timedelta(days=1)) - now
        hh, rem = divmod(int(reset.total_seconds()), 3600)
        label(h, th, "New quests in %dh %02dm (local time)" % (hh, rem // 60), (0.75, 0.62), 0.04, "muted", "bold")
        for i, q in enumerate(prof.quests.active):
            done = q["progress"] >= q["target"]
            p = panel(h, th, (-0.85, 0.85, -0.13, 0.13), "panel_hi" if done else "panel", 0.9, 0.08,
                      pos=(0.75, 0, 0.38 - i * 0.32))
            label(p, th, q["text"], (-0.78, 0.04), 0.05, "text", "bold", "left")
            label(p, th, "+%d coins   +%d XP" % (q["coins"], q["xp"]), (0.78, 0.04), 0.038, "secondary", "bold",
                  "right")
            ProgressBar(p, th, (-0.78, 0.4, -0.08, -0.04), q["progress"] / float(q["target"]),
                        "success" if done else "accent")
            label(p, th, ("COMPLETED - PAID" if q["claimed"] else "COMPLETE!") if done else
                  "%d / %d" % (q["progress"], q["target"]), (0.78, -0.075), 0.036,
                  "success" if done else "muted", "bold", "right")
        label(h, th, "Rewards are paid automatically when a quest completes.\n"
                     "Offline note: quests follow your computer's clock; turning it back never gives new ones.",
              (0.75, -0.72), 0.032, "muted", "body")


class AchievementsScreen(BaseScreen):
    name = "achievements"
    uses_menu_scene = False

    def build(self):
        self.header("ACHIEVEMENTS")
        self.list = ScrollList(self.root, self.theme, (-1.5, 1.5, -0.8, 0.65))

    def on_show(self, **kw):
        th = self.theme
        prof = self.app.profile
        am = prof.achievements
        stats = prof.stat_view()
        self.list.clear()
        done_n = 0
        for aid in am.order:
            d = am.defs[aid]
            st = am.state(aid)
            done_n += st["completed"]
            row = self.list.add_row(0.13)
            bg = panel(row, th, (0, self.list.width, -0.06, 0.06), "panel_hi" if st["completed"] else "panel", 0.9,
                       0.05, shadow=False, pos=(-1.5, 0, 0))
            label(bg, th, d["name"], (0.05, 0.005), 0.048, "secondary" if st["completed"] else "text", "title",
                  "left")
            label(bg, th, d["description"], (0.05, -0.042), 0.03, "muted", "body", "left")
            prog = am.progress(aid, stats)
            ProgressBar(bg, th, (1.3, 2.3, -0.02, 0.02), prog / float(d["target"]),
                        "success" if st["completed"] else "accent")
            label(bg, th, "%d / %d" % (prog, d["target"]), (2.3, -0.06), 0.028, "muted", "bold", "right")
            label(bg, th, ("DONE  +%d" if st["completed"] else "+%d coins") % d["reward"],
                  (self.list.width - 0.05, -0.012), 0.036, "success" if st["completed"] else "secondary", "bold",
                  "right")
        label(self.root, th, "%d / %d completed" % (done_n, len(am.order)), (1.45, 0.75), 0.04, "accent", "bold",
              "right")
