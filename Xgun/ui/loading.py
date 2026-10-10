"""Loading screen that runs a generator of work steps across frames."""
from __future__ import annotations

import random

from direct.gui.DirectGui import DirectFrame

from ui import theme as T
from ui.widgets import ProgressBar, text

TIPS = [
    "Chests glow gold and hum when you're close. Hold E to open them.",
    "Shield Cells stack up to 50 shield; Shield Kegs go all the way to 100.",
    "Crouching tightens your spread. Aiming down sights tightens it even more.",
    "Supply crates break with a few pickaxe hits and hold rare-or-better loot.",
    "The storm deals more damage every phase. Watch the timer under the minimap.",
    "Cosmetics never change gameplay. Wear whatever makes you happy.",
    "Every match earns XON. Spend it in the XON Shop on outfits, gliders and more.",
    "Press M for the full map. The dotted path shows where the drop ship flies.",
    "Press B to play your equipped emote.",
]


class LoadingScreen:
    def __init__(self, app, steps, on_done, subtitle: str = "OFFLINE SOLO  •  YOU vs AI BOTS"):
        self.app = app
        self.steps = steps
        self.on_done = on_done
        self.root = app.aspect2d.attachNewNode("loading")
        DirectFrame(parent=self.root, frameSize=(-3, 3, -2, 2), frameColor=T.BG)
        DirectFrame(parent=self.root, frameSize=(-3, 3, -0.004, 0.004), frameColor=(*T.PRIMARY[:3], 0.25), pos=(0, 0, -0.12))
        text(self.root, "XGUN", (0, 0.15), 0.26, T.TEXT, "black", "center")
        text(self.root, subtitle, (0, 0.03), 0.04, T.ACCENT, "bold", "center")
        self.label = text(self.root, "Loading", (0, -0.32), 0.04, T.TEXT_DIM, "semibold", "center")
        self.bar = ProgressBar(self.root, (-0.6, -0.38), (1.2, 0.016), T.PRIMARY)
        text(self.root, "TIP  " + random.choice(TIPS), (0, -0.6), 0.034, T.TEXT_MUTED, "regular", "center", wrap=40)
        self.count = 0
        self.expected = 9
        app.audio.play_music(None)
        app.taskMgr.doMethodLater(0.05, self._step, "loading-step")

    def _step(self, task):
        try:
            label, _ = next(self.steps)
        except StopIteration:
            self.bar.set(1.0)
            self.app.taskMgr.doMethodLater(0.1, lambda t: self.on_done(), "loading-done")
            return task.done
        self.count += 1
        self.label.setText(label + "...")
        self.bar.set(min(0.95, self.count / self.expected))
        return task.again

    def destroy(self):
        self.app.taskMgr.remove("loading-step")
        self.root.removeNode()
