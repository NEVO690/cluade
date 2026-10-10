"""PLAY tab: start a match, configure the offline opponents, daily overview."""
from __future__ import annotations

from direct.gui.DirectGui import DirectFrame

from ui import theme as T
from ui.lobby.common import Tab
from ui.widgets import Button, ProgressBar, frame, text

DIFFICULTIES = ["Easy", "Normal", "Hard"]
BOT_COUNTS = [9, 19, 29, 39]


class PlayTab(Tab):
    def build(self):
        r = self.root
        s = self.app.settings
        season = self.svc.catalog.season["name"]
        text(r, season.upper(), (-1.62, 0.66), 0.038, T.ACCENT, "bold")
        text(r, "BATTLE\nROYALE", (-1.62, 0.52), 0.13, T.TEXT, "black")
        text(r, "Drop onto Xgun Island, loot up, outlast the storm.", (-1.62, 0.18), 0.037, T.TEXT_DIM, "semibold")

        card = frame(r, -1.65, -0.55, -0.42, 0.1, T.PANEL, pos=(0, 0, 0))
        text(card, "MODE", (-1.6, 0.03), 0.028, T.TEXT_MUTED, "bold")
        text(card, "SOLO  •  OFFLINE", (-1.6, -0.03), 0.045, T.TEXT, "black")
        text(card, "Every opponent is an AI bot (marked BOT). No internet needed.", (-1.6, -0.08), 0.027, T.TEXT_DIM)
        text(card, "OPPONENTS", (-1.6, -0.16), 0.028, T.TEXT_MUTED, "bold")
        self.count_btns = []
        for i, n in enumerate(BOT_COUNTS):
            b = Button(card, f"{n + 1} players", self._set_count, pos=(-1.47 + i * 0.25, -0.22), size=(0.23, 0.065),
                       text_scale=0.026, extra_args=(n,))
            b.set_selected(s.bot_count == n)
            self.count_btns.append((n, b))
        text(card, "BOT DIFFICULTY", (-1.6, -0.3), 0.028, T.TEXT_MUTED, "bold")
        self.diff_btns = []
        for i, d in enumerate(DIFFICULTIES):
            b = Button(card, d, self._set_diff, pos=(-1.47 + i * 0.25, -0.36), size=(0.23, 0.065), text_scale=0.028,
                       extra_args=(d,))
            b.set_selected(s.bot_difficulty == d)
            self.diff_btns.append((d, b))

        self.play_btn = Button(r, "PLAY", self.app.start_match, pos=(-1.1, -0.62), size=(1.1, 0.17), color=T.GOLD,
                               hover=(1, 0.86, 0.45, 1), text_color=(0.1, 0.07, 0.0, 1), font="black", text_scale=0.085,
                               sound="ui_purchase")
        text(r, "W A S D move  •  Mouse aim  •  LMB fire  •  RMB aim  •  E interact  •  1-6 slots  •  B emote  •  M map",
             (-1.62, -0.78), 0.026, T.TEXT_MUTED, "semibold")

        # right column: level + quests snapshot
        acc = self.account.id
        prog = self.svc.progression
        lvl = prog.level(acc)
        cur, need = prog.level_progress(acc)
        panel = frame(r, 0.95, 1.65, -0.05, 0.62, T.PANEL)
        text(panel, f"LEVEL {lvl}", (1.0, 0.54), 0.05, T.TEXT, "black")
        text(panel, f"{cur:,} / {need:,} XP", (1.6, 0.545), 0.028, T.TEXT_DIM, "bold", "right")
        bar = ProgressBar(panel, (1.0, 0.49), (0.6, 0.016), T.PRIMARY)
        bar.set(cur / need)
        text(panel, "TODAY'S QUESTS", (1.0, 0.41), 0.03, T.TEXT_MUTED, "bold")
        for i, q in enumerate(prog.daily_quests(acc)[:4]):
            y = 0.34 - i * 0.1
            text(panel, q.text, (1.0, y), 0.026, T.GREEN if q.complete else T.TEXT, "semibold", wrap=22)
            pb = ProgressBar(panel, (1.0, y - 0.035), (0.6, 0.01), T.GREEN if q.complete else T.ACCENT)
            pb.set(q.progress / q.target)
        stats = prog.stats(acc)
        text(r, f"{stats.get('wins', 0)} WINS   •   {stats.get('matches', 0)} MATCHES   •   {stats.get('eliminations', 0)} ELIMS",
             (1.3, -0.12), 0.028, T.TEXT_DIM, "bold", "center")
        self.app.accept("enter", self.app.start_match)

    def _set_count(self, n):
        self.app.settings.bot_count = n
        self.app.settings.save()
        for v, b in self.count_btns:
            b.set_selected(v == n)

    def _set_diff(self, d):
        self.app.settings.bot_difficulty = d
        self.app.settings.save()
        for v, b in self.diff_btns:
            b.set_selected(v == d)

    def destroy(self):
        self.app.ignore("enter")
        super().destroy()
