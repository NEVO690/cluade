"""Game mode and map selection."""
import pygame

from ilbrawl import config
from ilbrawl.engine.scene import Scene
from ilbrawl.maps.thumbnail import thumbnail
from ilbrawl.menus.main_menu import map_display_name
from ilbrawl.ui import icons, text, theme
from ilbrawl.ui.widgets import Button, ScrollPanel

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H


class ModeCard(Button):
    def __init__(self, rect, scene, mode_id):
        super().__init__(rect, "", lambda: scene.pick_mode(mode_id), theme.PANEL)
        self.scene = scene
        self.mode_id = mode_id

    def draw(self, surf):
        sc = self.scene
        m = sc.game.data.modes[self.mode_id]
        col = tuple(m["color"])
        sel = sc.game.profile.data["selected_mode"] == self.mode_id
        r = self.rect.inflate(int(self.anim * 6), int(self.anim * 6))
        if sel:
            pygame.draw.rect(surf, theme.YELLOW, r.inflate(12, 12), 5, border_radius=22)
        theme.draw_panel(surf, r, theme.darken(col, 0.4), col, 18, True, 4)
        ic = pygame.Rect(0, 0, 76, 76)
        ic.center = (r.centerx, r.y + 56)
        icons.mode_icon(surf, ic, self.mode_id)
        text.draw(surf, sc.tr("mode.%s.name" % self.mode_id), (r.centerx, r.y + 110), 21, theme.WHITE, "center", "middle",
                  max_width=r.w - 14)
        text.draw_wrapped(surf, sc.tr("mode.%s.desc" % self.mode_id), (r.x + 10, r.y + 130, r.w - 20, 70), 13,
                          theme.TEXT_DIM, "center", False, 0, 2, 4)


class MapCard(Button):
    def __init__(self, rect, scene, mode_id, mapdef):
        super().__init__(rect, "", lambda: scene.pick_map(mapdef["id"]), theme.PANEL)
        self.scene = scene
        self.mode_id = mode_id
        self.mapdef = mapdef

    def draw(self, surf):
        sc = self.scene
        r = self.rect.inflate(int(self.anim * 6), int(self.anim * 6))
        sel = sc.game.profile.selected_map(self.mode_id) == self.mapdef["id"]
        if sel:
            pygame.draw.rect(surf, theme.YELLOW, r.inflate(10, 10), 5, border_radius=18)
        theme.draw_panel(surf, r, (28, 34, 44), theme.PANEL_BORDER, 14, True, 3)
        th = thumbnail(self.mapdef, sc.game.data.themes, 6)
        scale = min((r.w - 16) / th.get_width(), (r.h - 50) / th.get_height())
        img = pygame.transform.smoothscale(th, (int(th.get_width() * scale), int(th.get_height() * scale)))
        surf.blit(img, (r.centerx - img.get_width() // 2, r.y + 8))
        text.draw(surf, map_display_name(sc, self.mapdef["id"]), (r.centerx, r.bottom - 22), 18, theme.WHITE, "center",
                  "middle", max_width=r.w - 12)
        if self.mapdef.get("custom"):
            text.draw(surf, sc.tr("modes.custom"), (r.x + 10 if not sc.rtl else r.right - 10, r.y + 10), 13, theme.YELLOW,
                      "start")


class ModesScene(Scene):
    def build(self):
        self.widgets = []
        self.add_header("modes.title")
        gd = self.game.data
        order = gd.mode_order
        n = len(order)
        w, gap = 228, 14
        x0 = (VW - (n * w + (n - 1) * gap)) // 2
        for i, mid in enumerate(order):
            idx = (n - 1 - i) if self.rtl else i
            self.add(ModeCard((x0 + idx * (w + gap), 96, w, 206), self, mid))
        mode = self.game.profile.data["selected_mode"]
        maps = gd.maps_for_mode(mode)
        self.maps_panel = self.add(ScrollPanel((30, 356, VW - 60, 230), horizontal=True))
        cw = 250
        for i, m in enumerate(maps):
            x = 8 + i * (cw + 14)
            if self.rtl:
                x = max(len(maps) * (cw + 14) + 8, VW - 60) - x - cw
            self.maps_panel.add(MapCard((x, 10, cw, 206), self, mode, m))
        self.maps_panel.content_size = max(len(maps) * (cw + 14) + 16, VW - 60)
        if self.rtl:
            self.maps_panel.scroll_to(self.maps_panel.max_offset(), True)
        self.add(Button(self.R(30, VH - 104, 280, 76), self.tr("modes.editor"), self.open_editor, theme.CYAN, 22,
                        icon=icons.editor))
        self.add(Button(self.R(VW - 330, VH - 110, 300, 88), self.tr("menu.play"), self.play, theme.YELLOW, 40,
                        icon=icons.play))

    def pick_mode(self, mid):
        p = self.game.profile
        if p.data["selected_mode"] != mid:
            p.data["selected_mode"] = mid
            p.save()
            self.build()

    def pick_map(self, map_id):
        p = self.game.profile
        p.data["selected_map"][p.data["selected_mode"]] = map_id
        p.save()

    def play(self):
        p = self.game.profile
        mode = p.data["selected_mode"]
        map_id = p.selected_map(mode)
        if map_id:
            from ilbrawl.gameplay.battle_scene import BattleScene
            self.game.replace(BattleScene(self.game, mode, map_id, p.data["selected_char"]))

    def open_editor(self):
        from ilbrawl.maps.map_editor import MapEditorScene
        self.game.push(MapEditorScene(self.game))

    def on_resume(self):
        self.game.data.reload_maps()
        super().on_resume()

    def draw_content(self, surf):
        self.draw_header(surf)
        text.draw(surf, self.tr("modes.choose_map"), (self.X(36), 322), 24, theme.WHITE, "start", outline=3)
