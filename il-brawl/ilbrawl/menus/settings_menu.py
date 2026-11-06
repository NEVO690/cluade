"""Settings: language, audio, graphics, display, AI difficulty and control remapping."""
import pygame

from ilbrawl import config
from ilbrawl.engine.scene import Scene
from ilbrawl.localization import i18n as i18n_mod
from ilbrawl.settings.settings import DIFFICULTIES, GRAPHICS_LEVELS
from ilbrawl.ui import text, theme
from ilbrawl.ui.widgets import Button, Dialog, Selector, Slider, TabBar, Toggle

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H
ACTIONS = ["up", "down", "left", "right", "attack", "super", "autoaim"]


class SettingsScene(Scene):
    show_currency = False

    def __init__(self, game, in_battle=False, tab=0):
        self.in_battle = in_battle
        self.tab = tab
        self.waiting = None
        super().__init__(game)

    def build(self):
        self.widgets = []
        self.add_header("settings.title")
        s = self.game.settings
        self.add(TabBar(self.R(VW - 640, 20, 610, 54), [self.tr("settings.tab.general"), self.tr("settings.tab.controls")], self.tab,
                        self.set_tab, self.rtl, theme.BLUE))
        if self.tab == 0:
            lx = self.X(60, 540)
            rx = self.X(680, 540)
            # language buttons
            for i, code in enumerate(config.LANGUAGES):
                c, r = i % 2, i // 2
                if self.rtl:
                    c = 1 - c
                b = self.add(Button((lx + c * 275, 150 + r * 70, 262, 60), self.game.i18n.language_name(code),
                                    lambda code=code: self.set_lang(code),
                                    theme.GREEN if code == self.game.i18n.lang else theme.PANEL_LIGHT, 22))
                b.selected = code == self.game.i18n.lang
            self.add(Selector((lx, 340, 540, 50), [self.tr("difficulty.%s" % d) for d in DIFFICULTIES],
                              DIFFICULTIES.index(s["ai_difficulty"]), self.set_diff, theme.RED))
            self.add(Selector((lx, 440, 540, 50), [self.tr("graphics.%s" % g) for g in GRAPHICS_LEVELS],
                              GRAPHICS_LEVELS.index(s["graphics"]), self.set_gfx, theme.PURPLE))
            res = [list(r) for r in config.RESOLUTIONS]
            cur = s["resolution"] if s["resolution"] in res else [1280, 720]
            if cur not in res:
                res.append(cur)
            self.res_list = res
            self.add(Selector((lx, 540, 540, 50), ["%d × %d" % tuple(r) for r in res], res.index(cur), self.set_res,
                              theme.BLUE))
            self.add(Toggle((lx + (540 - 80 if not self.rtl else 0), 616, 80, 40), s["fullscreen"], self.set_full, self.rtl))
            # right column
            self.add(Slider((rx + (110 if self.rtl else 0), 170, 430, 30), s["music_volume"], self.set_music, theme.GREEN,
                            self.rtl))
            self.add(Slider((rx + (110 if self.rtl else 0), 270, 430, 30), s["sfx_volume"], self.set_sfx, theme.YELLOW,
                            self.rtl))
            self.add(Toggle((rx + (540 - 80 if not self.rtl else 0), 340, 80, 40), s["show_fps"],
                            lambda v: s.set("show_fps", v), self.rtl))
            self.add(Toggle((rx + (540 - 80 if not self.rtl else 0), 410, 80, 40), s["screen_shake"],
                            lambda v: s.set("screen_shake", v), self.rtl))
            if not self.in_battle:
                self.add(Button((rx, 600, 540, 64), self.tr("settings.reset_progress"), self.ask_reset, theme.RED, 22))
        else:
            c = s["controls"]
            x = self.X(240, 800)
            for i, a in enumerate(ACTIONS):
                y = 110 + i * 68
                label = self.tr("settings.press_key") if self.waiting == a else i18n_mod.key_label(c[a])
                b = self.add(Button((x + (520 if not self.rtl else 0), y, 280, 56), label, lambda a=a: self.wait_key(a),
                                    theme.YELLOW if self.waiting == a else theme.PANEL_LIGHT, 22))
                b.selected = self.waiting == a
            self.add(Button((x, 600, 380, 60), self.tr("settings.reset_controls"), self.reset_controls, theme.ORANGE, 20))

    def set_tab(self, i):
        self.tab = i
        self.waiting = None
        self.build()

    # ------------------------------------------------------------ handlers
    def set_lang(self, code):
        self.game.set_language(code)  # rebuilds every scene instantly

    def set_diff(self, i):
        self.game.settings.set("ai_difficulty", DIFFICULTIES[i])

    def set_gfx(self, i):
        self.game.settings.set("graphics", GRAPHICS_LEVELS[i])

    def set_res(self, i):
        self.game.settings.set("resolution", list(self.res_list[i]))
        if not self.game.settings["fullscreen"]:
            self.game.apply_display()

    def set_full(self, v):
        self.game.settings.set("fullscreen", v)
        self.game.apply_display()

    def set_music(self, v):
        self.game.settings.set("music_volume", round(v, 2), save=False)
        self.game.audio.apply_volume()

    def set_sfx(self, v):
        self.game.settings.set("sfx_volume", round(v, 2), save=False)

    def wait_key(self, action):
        self.waiting = action
        self.build()

    def reset_controls(self):
        self.game.settings.reset_controls()
        self.waiting = None
        self.build()

    def ask_reset(self):
        def do():
            self.game.profile.reset()
            self.game.toasts.push(self.tr("settings.progress_reset"), theme.RED)
        self.open_dialog(Dialog(self.tr("settings.reset_progress"), self.tr("settings.reset_body"),
                                [(self.tr("common.cancel"), theme.GREY, None), (self.tr("common.confirm"), theme.RED, do)]))

    def on_event(self, e):
        if self.waiting and e.type == pygame.KEYDOWN:
            if e.key != pygame.K_ESCAPE:
                name = pygame.key.name(e.key)
                c = self.game.settings["controls"]
                old = c[self.waiting]
                for a, k in c.items():
                    if k == name and a != self.waiting:
                        c[a] = old  # swap to avoid duplicate bindings
                c[self.waiting] = name
                self.game.settings.save()
                self.game.audio.play("click")
            self.waiting = None
            self.build()
            return
        super().on_event(e)

    def back(self):
        self.game.settings.save()
        super().back()

    def draw_content(self, surf):
        text.draw(surf, self.tr(self.title_key), (self.X(104), 24), 36, theme.WHITE, "start", outline=3, max_width=500)
        s = self.game.settings
        if self.tab == 0:
            lx = self.X(60, 540)
            rx = self.X(680, 540)
            sx = lx if not self.rtl else lx + 540
            rsx = rx if not self.rtl else rx + 540
            for y, k in ((120, "settings.language"), (310, "settings.ai_difficulty"), (410, "settings.graphics"),
                         (510, "settings.resolution")):
                text.draw(surf, self.tr(k), (sx, y), 20, theme.TEXT_DIM, "start")
            text.draw(surf, self.tr("settings.fullscreen"), (sx, 636), 22, theme.WHITE, "start", "middle")
            text.draw(surf, self.tr("settings.music"), (rsx, 130), 20, theme.TEXT_DIM, "start")
            text.draw(surf, self.tr("settings.sfx"), (rsx, 230), 20, theme.TEXT_DIM, "start")
            text.draw(surf, self.tr("settings.show_fps"), (rsx, 360), 22, theme.WHITE, "start", "middle")
            text.draw(surf, self.tr("settings.screen_shake"), (rsx, 430), 22, theme.WHITE, "start", "middle")
            text.draw(surf, self.tr("settings.fullscreen_hint"), (rsx, 500), 16, theme.TEXT_DIM, "start", max_width=540)
        else:
            x = self.X(240, 800)
            lx = x if not self.rtl else x + 800
            for i, a in enumerate(ACTIONS):
                y = 110 + i * 68
                text.draw(surf, self.tr("control.%s" % a), (lx, y + 28), 24, theme.WHITE, "start", "middle")
            text.draw(surf, self.tr("settings.mouse_help"), (VW // 2, 690), 17, theme.TEXT_DIM, "center", "middle",
                      max_width=VW - 80)
