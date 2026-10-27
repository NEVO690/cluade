"""Splash, main menu, mode select, lobby, map select and loading screens."""

import math
import random

from direct.gui.DirectGui import DirectFrame

from ...session import ShowConfig
from ..theme import c
from ..widgets import Button, label, panel
from .common import BaseScreen, player_card

TIPS = [
    "Hold SHIFT to walk carefully on narrow bridges and tiny pads.",
    "Land on someone's head for a BONK! - it bounces you up and stuns them.",
    "Hammers swing on a rhythm: wait for the gap, then sprint.",
    "Tiles flash before they drop. Never stop on a flashing tile!",
    "Checkpoints save your progress on courses where falling respawns you.",
    "Jump just before a sweeping bar reaches you to hop over it.",
    "Finishing quests and achievements pays out BONK COINS.",
]


class SplashScreen(BaseScreen):
    name = "splash"

    def build(self):
        self.logo = label(self.root, self.theme, "BONK!", (0, 0.05), 0.42, "secondary", "title")
        self.sub = label(self.root, self.theme, "THE OBSTACLE COURSE PARTY", (0, -0.12), 0.06, "text", "bold")
        self.hint = label(self.root, self.theme, "click or press any key", (0, -0.55), 0.05, "muted", "body")
        self.t = 0.0

    def on_show(self, **kw):
        self.t = 0.0
        self.app.accept("mouse1", self._go)
        self.app.accept("space", self._go)
        self.app.accept("enter", self._go)

    def on_hide(self):
        for ev in ("mouse1", "space", "enter"):
            self.app.ignore(ev)

    def _go(self):
        if self.app.screens.current is self:
            self.app.screens.reset_to("main")

    def update(self, dt):
        self.t += dt
        s = 1.0 + 0.04 * math.sin(self.t * 3.0)
        self.logo.setScale(s)
        self.logo.setR(math.sin(self.t * 1.7) * 2.0)
        self.hint.setAlphaScale(0.5 + 0.5 * math.sin(self.t * 4.0))
        if self.t > 6.0:
            self._go()


class MainMenu(BaseScreen):
    name = "main"
    scene_offset = 1.25

    def build(self):
        th = self.theme
        label(self.root, th, "BONK!", (-1.12, 0.6), 0.26, "secondary", "title")
        label(self.root, th, "THE OBSTACLE COURSE PARTY", (-1.12, 0.49), 0.042, "text", "bold")
        items = [
            ("PLAY", self._play, "primary"),
            ("AI SHOWDOWN", lambda: self.app.screens.show("lobby"), "purple"),
            ("MULTIPLAYER", lambda: self.app.screens.show("multiplayer"), "blue"),
            ("SKINS", lambda: self.app.screens.show("skins"), "panel_hi"),
            ("SHOP", lambda: self.app.screens.show("shop"), "panel_hi"),
            ("PROFILE", lambda: self.app.screens.show("profile"), "panel_hi"),
            ("QUESTS", lambda: self.app.screens.show("quests"), "panel_hi"),
            ("SETTINGS", lambda: self.app.screens.show("settings"), "panel_hi"),
            ("QUIT", self.app.quit, "dark"),
        ]
        y = 0.32
        for i, (text, cmd, col) in enumerate(items):
            big = i == 0
            Button(self.root, th, text, (-1.12, y), (0.72, 0.13 if big else 0.1), cmd, color=col,
                   scale=0.065 if big else 0.048)
            y -= 0.16 if big else 0.118
        self.card_holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        self.quest_holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        label(self.root, th, "v0.1  -  WASD move  -  SPACE jump  -  SHIFT walk  -  mouse camera",
              (0.95, -0.95), 0.032, "muted", "body")

    def on_show(self, **kw):
        prof = self.app.profile
        prof.quests.refresh()
        self.card_holder.destroy()
        self.card_holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        player_card(self.card_holder, self.theme, prof, (1.05, 0.66))
        self.quest_holder.destroy()
        self.quest_holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        p = panel(self.quest_holder, self.theme, (-0.55, 0.55, -0.2, 0.2), "panel", 0.85, 0.08,
                  pos=(1.05, 0, -0.62))
        label(p, self.theme, "DAILY QUESTS", (-0.5, 0.12), 0.042, "secondary", "title", "left")
        for i, q in enumerate(prof.quests.active[:3]):
            done = q["progress"] >= q["target"]
            label(p, self.theme, ("[OK] " if done else "") + q["text"], (-0.5, 0.05 - i * 0.075), 0.035,
                  "success" if done else "text", "body", "left")
            label(p, self.theme, "%d/%d" % (q["progress"], q["target"]), (0.5, 0.05 - i * 0.075), 0.035,
                  "muted", "bold", "right")

    def _play(self):
        """PLAY = jump straight into a full AI show with your saved settings."""
        s = self.app.profile.settings
        cfg = ShowConfig(self.app.maps.show_playlist(), s["bot_count"], s["bot_difficulty"])
        self.app.start_show(cfg)


class ModeSelect(BaseScreen):
    name = "modes"

    def build(self):
        self.header("CHOOSE A MODE")
        cards = [
            ("AI SHOWDOWN", "Three rounds against bots.\nQualify, survive, win the crown.", "purple",
             lambda: self.app.screens.show("lobby", mode="show")),
            ("QUICK RACE", "One course of your choice\nagainst bots.", "primary",
             lambda: self.app.screens.show("lobby", mode="single")),
            ("MULTIPLAYER", "Race real players through a\nBONK! server (local network).", "blue",
             lambda: self.app.screens.show("multiplayer")),
        ]
        for i, (title, desc, col, cmd) in enumerate(cards):
            x = -1.0 + i * 1.0
            p = panel(self.root, self.theme, (-0.44, 0.44, -0.42, 0.42), "panel", 0.92, 0.1, pos=(x, 0, 0.05))
            label(p, self.theme, title, (0, 0.27), 0.065, col, "title")
            label(p, self.theme, desc, (0, 0.1), 0.04, "text", "body")
            Button(p, self.theme, "SELECT", (0, -0.28), (0.5, 0.11), cmd, color=col)

    uses_menu_scene = False


class LobbyScreen(BaseScreen):
    """Set up an AI show: bots, difficulty, single course or full show."""

    name = "lobby"
    scene_offset = 1.45

    def build(self):
        self.header("AI SHOWDOWN LOBBY", subtitle="You vs. bots - all bots run on this computer")
        th = self.theme
        self.mode = "show"
        self.map_id = None
        p = panel(self.root, th, (-0.75, 0.75, -0.6, 0.55), "panel", 0.9, 0.08, pos=(-0.85, 0, 0.0))
        self.panel = p
        label(p, th, "FORMAT", (-0.68, 0.45), 0.042, "muted", "bold", "left")
        self.fmt_buttons = [
            Button(p, th, "FULL SHOW", (-0.36, 0.36), (0.6, 0.09), self._set_mode, ["show"], scale=0.04),
            Button(p, th, "QUICK RACE", (0.36, 0.36), (0.6, 0.09), self._set_mode, ["single"], scale=0.04),
        ]
        self.course_label = label(p, th, "", (-0.68, 0.23), 0.04, "text", "bold", "left", wordwrap=33)
        self.course_btn = Button(p, th, "CHOOSE COURSE", (0.42, 0.12), (0.5, 0.08),
                                 lambda: self.app.screens.show("maps"), color="blue", scale=0.035)
        label(p, th, "BOTS", (-0.68, 0.0), 0.042, "muted", "bold", "left")
        Button(p, th, "-", (-0.1, 0.0), (0.1, 0.08), self._bots, [-1], color="panel_hi")
        self.bots_label = label(p, th, "15", (0.05, -0.015), 0.055, "text", "title")
        Button(p, th, "+", (0.2, 0.0), (0.1, 0.08), self._bots, [1], color="panel_hi")
        self.players_label = label(p, th, "", (0.68, -0.015), 0.035, "muted", "body", "right")
        label(p, th, "BOT DIFFICULTY", (-0.68, -0.14), 0.042, "muted", "bold", "left")
        self.diff_buttons = {}
        for i, d in enumerate(("EASY", "NORMAL", "HARD", "CHAOTIC", "MIXED")):
            self.diff_buttons[d] = Button(p, th, d, (-0.56 + i * 0.28, -0.24), (0.26, 0.08), self._diff, [d],
                                          scale=0.03)
        self.diff_desc = label(p, th, "", (-0.68, -0.36), 0.033, "text", "body", "left", wordwrap=42)
        Button(self.root, th, "START!", (-0.85, -0.75), (0.7, 0.13), self._start, color="primary", scale=0.07)
        self.roster = label(self.root, th, "", (-0.85, -0.88), 0.04, "secondary", "bold")

    def on_show(self, mode=None, map_id=None, **kw):
        if mode:
            self.mode = mode
        if map_id:
            self.map_id = map_id
            self.mode = "single"
        self._refresh()

    def _set_mode(self, mode):
        self.mode = mode
        self._refresh()

    def _bots(self, delta):
        s = self.app.profile.settings
        self.app.profile.set_setting("bot_count", s["bot_count"] + delta)
        self._refresh()

    def _diff(self, d):
        self.app.profile.set_setting("bot_difficulty", d)
        self._refresh()

    DESCS = {
        "EASY": "Slow to react, hesitates, misjudges some jumps and often ignores obstacle timing.",
        "NORMAL": "Plans a sensible line, times most obstacles, makes occasional mistakes.",
        "HARD": "Reacts instantly, predicts hammers and tiles, picks precise jump spots.",
        "CHAOTIC": "Weaves, hops for fun and loves to shove people - unpredictable but fair.",
        "MIXED": "A random mix of all four personalities.",
    }

    def _refresh(self):
        s = self.app.profile.settings
        maps = self.app.maps
        if self.mode == "single":
            m = maps.get(self.map_id) if self.map_id in maps.maps else maps.ordered()[0]
            self.map_id = m.id
            self.course_label["text"] = "COURSE: %s\n%s" % (m.name, m.description)
            self.course_btn.show()
        else:
            names = " > ".join(m.name for m in maps.ordered())
            self.course_label["text"] = "3-ROUND SHOW:\n%s" % names
            self.course_btn.hide()
        for b, key in zip(self.fmt_buttons, ("show", "single")):
            b.set_color("primary" if self.mode == key else "panel_hi")
        self.bots_label["text"] = str(s["bot_count"])
        self.players_label["text"] = "%d players total" % (s["bot_count"] + 1)
        for d, b in self.diff_buttons.items():
            b.set_color("purple" if d == s["bot_difficulty"] else "panel_hi")
        self.diff_desc["text"] = self.DESCS[s["bot_difficulty"]]
        self.app.profile.save()
        self.roster["text"] = "%s  +  %d BOTS" % (self.app.profile.name, s["bot_count"])

    def _start(self):
        s = self.app.profile.settings
        ids = [self.map_id] if self.mode == "single" else self.app.maps.show_playlist()
        cfg = ShowConfig(ids, s["bot_count"], s["bot_difficulty"],
                         mode="quick_play" if self.mode == "single" else "ai_showdown")
        self.app.start_show(cfg)


class MapSelect(BaseScreen):
    name = "maps"
    uses_menu_scene = False

    def build(self):
        self.header("CHOOSE A COURSE")
        th = self.theme
        for i, m in enumerate(self.app.maps.ordered()):
            y = 0.45 - i * 0.42
            p = panel(self.root, th, (-1.4, 1.4, -0.18, 0.18), "panel", 0.92, 0.08, pos=(0.05, 0, y))
            theme_col = m.theme.get("accent", "#ffd23f")
            stripe = DirectFrame(parent=p, frameColor=c(theme_col), frameSize=(-1.4, -1.36, -0.18, 0.18))
            stripe.setTransparency(1)
            label(p, th, m.name, (-1.3, 0.07), 0.06, "text", "title", "left")
            rule = "fall = back to checkpoint" if m.fall_rule == "respawn" else "fall = ELIMINATED"
            label(p, th, "%s  |  %s  |  %ds limit" % (m.difficulty.upper(), rule, m.time_limit), (-1.3, 0.0),
                  0.035, "secondary", "bold", "left")
            label(p, th, m.description, (-1.3, -0.08), 0.035, "muted", "body", "left", wordwrap=60)
            Button(p, th, "SELECT", (1.12, 0.0), (0.38, 0.11), self._pick, [m.id], color="primary")

    def _pick(self, map_id):
        self.app.screens.show("lobby", push=False, mode="single", map_id=map_id)


class LoadingScreen(BaseScreen):
    name = "loading"
    uses_menu_scene = False
    music = None

    def build(self):
        DirectFrame(parent=self.root, frameColor=c("bg"), frameSize=(-3, 3, -1.2, 1.2))
        label(self.root, self.theme, "BONK!", (0, 0.25), 0.2, "secondary", "title")
        self.text = label(self.root, self.theme, "Loading...", (0, -0.02), 0.06, "text", "bold")
        self.tip = label(self.root, self.theme, "", (0, -0.6), 0.045, "muted", "body", wordwrap=40)
        self.dots = label(self.root, self.theme, "", (0, -0.15), 0.08, "accent", "title")
        self.t = 0.0

    def on_show(self, text="Loading...", **kw):
        self.text["text"] = text
        self.tip["text"] = "TIP: " + random.choice(TIPS)

    def update(self, dt):
        self.t += dt
        self.dots["text"] = "." * (1 + int(self.t * 4) % 3)
