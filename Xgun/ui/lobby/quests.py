"""QUESTS tab: daily quests and long-term milestones."""
from __future__ import annotations

import datetime as dt

from ui import theme as T
from ui.lobby.common import Tab, header, icon
from ui.widgets import ProgressBar, frame, image, text


class QuestsTab(Tab):
    def build(self):
        r = self.root
        prog = self.svc.progression
        acc = self.account.id
        header(r, "QUESTS", "Daily quests refresh at midnight. Progress is saved after every match.")
        now = dt.datetime.now()
        left = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time()) - now
        text(r, f"DAILY  •  resets in {left.seconds // 3600}h {left.seconds % 3600 // 60}m", (-1.62, 0.52), 0.035, T.ACCENT, "black")
        for i, q in enumerate(prog.daily_quests(acc)):
            y = 0.4 - i * 0.16
            box = frame(r, -1.65, 0.0, y - 0.065, y + 0.065, T.PANEL)
            text(box, q.text, (-1.6, y + 0.012), 0.034, T.GREEN if q.complete else T.TEXT, "bold")
            pb = ProgressBar(box, (-1.6, y - 0.035), (1.1, 0.014), T.GREEN if q.complete else T.PRIMARY)
            pb.set(q.progress / q.target)
            text(box, f"{q.progress}/{q.target}", (-0.42, y - 0.045), 0.026, T.TEXT_DIM, "bold", "right")
            text(box, f"+{q.xp} XP  +{q.xon} XON", (-0.04, y + 0.012), 0.028, T.GOLD, "bold", "right")
            if q.complete:
                image(box, icon("check"), (-0.1, y - 0.035), (0.04, 0.04))
        text(r, "MILESTONES", (-1.62, -0.28), 0.035, T.GOLD, "black")
        for i, m in enumerate(prog.milestones(acc)):
            col, row = i % 2, i // 2
            x0 = -1.65 + col * 0.84
            y = -0.38 - row * 0.15
            box = frame(r, x0, x0 + 0.8, y - 0.06, y + 0.06, T.PANEL)
            text(box, m["text"], (x0 + 0.03, y + 0.012), 0.028, T.GREEN if m["claimed"] else T.TEXT, "bold")
            pb = ProgressBar(box, (x0 + 0.03, y - 0.03), (0.55, 0.012), T.GREEN if m["claimed"] else T.ACCENT)
            pb.set(m["progress"] / m["target"])
            rw = m["reward"]
            label = f"{rw['amount']} XON" if rw["type"] == "xon" else self.svc.catalog.get(rw["item_id"]).name
            text(box, label, (x0 + 0.77, y - 0.04), 0.022, T.GOLD, "bold", "right")
