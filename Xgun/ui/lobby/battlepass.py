"""BATTLE PASS tab: the free Season 1 reward track."""
from __future__ import annotations

from direct.gui.DirectGui import DirectFrame

from ui import theme as T
from ui.lobby.common import Tab, header, icon, item_thumb
from ui.widgets import ProgressBar, frame, image, text


class BattlePassTab(Tab):
    def build(self):
        r = self.root
        prog = self.svc.progression
        acc = self.account.id
        header(r, "BATTLE PASS", prog.pass_data["note"])
        lvl = prog.level(acc)
        cur, need = prog.level_progress(acc)
        tier = min(lvl, prog.max_tier)
        text(r, prog.pass_data["name"].upper(), (-1.62, 0.52), 0.036, T.ACCENT, "black")
        text(r, f"TIER {tier} / {prog.max_tier}", (-1.62, 0.45), 0.06, T.TEXT, "black")
        bar = ProgressBar(r, (-1.62, 0.39), (0.9, 0.02), T.GOLD)
        bar.set(cur / need if tier < prog.max_tier else 1.0)
        text(r, f"{cur:,} / {need:,} XP to next tier", (-0.7, 0.385), 0.028, T.TEXT_DIM, "bold")
        cat = self.svc.catalog
        cols = 10
        w, h = 0.24, 0.3
        for i, t in enumerate(prog.tiers()):
            col, row = i % cols, i // cols
            x = -1.5 + col * (w + 0.03)
            y = 0.12 - row * (h + 0.08)
            unlocked = prog.tier_claimed(acc, t["tier"])
            reward = t["reward"]
            if reward["type"] == "item":
                item = cat.get(reward["item_id"])
                col_c = T.RARITY[item.rarity]
                name = item.name
                thumb = item_thumb(item)
            else:
                col_c = T.GOLD
                name = f"{reward['amount']} XON"
                thumb = icon("xon")
            box = frame(r, x - w / 2, x + w / 2, y - h / 2, y + h / 2, (col_c[0] * 0.3, col_c[1] * 0.3, col_c[2] * 0.3, 0.92))
            DirectFrame(parent=box, frameSize=(x - w / 2, x + w / 2, y - h / 2, y - h / 2 + 0.008), frameColor=col_c)
            image(box, thumb, (x, y + 0.03), (w * 0.8, h * 0.6))
            text(box, str(t["tier"]), (x - w / 2 + 0.015, y + h / 2 - 0.04), 0.03, T.TEXT, "black")
            text(box, name, (x, y - h / 2 + 0.025), 0.022, T.TEXT, "bold", "center", wrap=10)
            if unlocked:
                image(box, icon("check"), (x + w / 2 - 0.035, y + h / 2 - 0.035), (0.045, 0.045))
            elif t["tier"] > tier:
                box.setColorScale(0.55, 0.55, 0.62, 1)
                image(box, icon("lock"), (x + w / 2 - 0.035, y + h / 2 - 0.035), (0.04, 0.04))
        text(r, "Earn XP from matches, eliminations, survival time and daily quests. Rewards unlock automatically.",
             (-1.62, -0.6), 0.03, T.TEXT_DIM, "semibold")
