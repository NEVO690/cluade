"""Post-match results and rewards overlay."""
from __future__ import annotations

from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectGui import DirectFrame
from direct.interval.IntervalGlobal import LerpColorScaleInterval

from ui import theme as T
from ui.widgets import Button, frame, image, text


class ResultsPanel:
    def __init__(self, lobby, summary, rewards):
        app = lobby.app
        self.lobby = lobby
        self.root = app.aspect2d.attachNewNode("results")
        self.root.setBin("gui-popup", 40)
        DirectFrame(parent=self.root, frameSize=(-4, 4, -2, 2), frameColor=(0.01, 0.01, 0.04, 0.82), state=DGG.NORMAL)
        won = summary.placement == 1
        title = "VICTORY ROYALE" if won else f"#{summary.placement}"
        text(self.root, title, (0, 0.68), 0.13 if won else 0.16, T.GOLD if won else T.TEXT, "black", "center", shadow=True)
        text(self.root, f"out of {summary.players} players  •  {summary.eliminations} eliminations  •  {summary.damage} damage  •  "
                        f"survived {int(summary.survive_secs // 60)}:{int(summary.survive_secs % 60):02d}",
             (0, 0.56), 0.036, T.TEXT_DIM, "semibold", "center")
        box = frame(self.root, -0.85, 0.85, -0.55, 0.45, T.PANEL)
        text(box, "REWARDS", (-0.78, 0.36), 0.045, T.TEXT, "black")
        y = 0.27
        for line in rewards.lines[:9]:
            text(box, line.label, (-0.78, y), 0.032, T.TEXT, "semibold")
            parts = []
            if line.xp:
                parts.append(f"+{line.xp:,} XP")
            if line.xon:
                parts.append(f"+{line.xon:,} XON")
            text(box, "   ".join(parts), (0.78, y), 0.032, T.GOLD if line.xon else T.ACCENT, "bold", "right")
            y -= 0.06
        DirectFrame(parent=box, frameSize=(-0.8, 0.8, y + 0.025, y + 0.03), frameColor=(1, 1, 1, 0.15))
        text(box, "TOTAL", (-0.78, y - 0.03), 0.038, T.TEXT, "black")
        text(box, f"+{rewards.xp:,} XP     +{rewards.xon:,} XON", (0.78, y - 0.03), 0.038, T.GOLD, "black", "right")
        if rewards.level_after > rewards.level_before:
            text(box, f"LEVEL UP!  {rewards.level_before} → {rewards.level_after}", (0, y - 0.12), 0.045, T.ACCENT, "black", "center")
            app.audio.play("level_up")
        if rewards.unlocked_items:
            names = ", ".join(app.services.catalog.get(i).name for i in rewards.unlocked_items)
            text(box, f"Unlocked: {names}", (0, -0.47), 0.032, T.GREEN, "bold", "center", wrap=48)
        Button(self.root, "CONTINUE", self.close, pos=(0, -0.7), size=(0.5, 0.1), color=T.PRIMARY, hover=T.PRIMARY_HOVER,
               text_scale=0.045)
        self.root.setColorScale(1, 1, 1, 0)
        LerpColorScaleInterval(self.root, 0.3, (1, 1, 1, 1)).start()
        app.audio.play_music("results_theme")
        for item_id in rewards.unlocked_items:
            app.toasts.show(f"New item unlocked: {app.services.catalog.get(item_id).name}", "success", 4)

    def close(self):
        self.root.removeNode()
        self.lobby.app.audio.play_music("lobby_theme")
        self.lobby.refresh_avatar()
        if hasattr(self.lobby.tab_obj, "rebuild"):
            self.lobby.tab_obj.rebuild()
