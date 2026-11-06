"""In-game map editor: paint tiles, mirror symmetry, choose theme and modes, validate, save, test."""
import json
import os
import re
import time

import pygame

from ilbrawl import config
from ilbrawl.engine.scene import Scene
from ilbrawl.maps.thumbnail import MARK_COLORS, tile_color
from ilbrawl.ui import icons, text, theme
from ilbrawl.ui.widgets import Button, Dialog, Selector, TextInput, Toggle

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H
PALETTE = [".", "#", "B", "C", "X", "W", "P", "1", "2", "S", "G", "O", "Z", "A", "R"]
SIZES = [("team", 31, 19), ("solo", 35, 25)]
SWAP = {"1": "2", "2": "1", "A": "R", "R": "A"}


def validate(tiles, modes):
    """Return a list of locale keys describing problems (empty = valid)."""
    flat = "".join(tiles)
    errs = []
    if not modes:
        errs.append("editor.err_no_mode")
    team_modes = [m for m in modes if m != "solo_survival"]
    if team_modes and (flat.count("1") < 1 or flat.count("2") < 1):
        errs.append("editor.err_team_spawns")
    if "solo_survival" in modes and flat.count("S") < 2:
        errs.append("editor.err_solo_spawns")
    if "gem_collection" in modes and "G" not in flat:
        errs.append("editor.err_gem")
    if "goal_rush" in modes and ("O" not in flat or "A" not in flat or "R" not in flat):
        errs.append("editor.err_goal")
    if "zone_control" in modes and "Z" not in flat:
        errs.append("editor.err_zone")
    return errs


class MapEditorScene(Scene):
    show_currency = False

    def __init__(self, game):
        self.size_idx = 0
        self.theme_ids = sorted(game.data.themes.keys()) or ["meadow"]
        self.theme_idx = self.theme_ids.index("meadow") if "meadow" in self.theme_ids else 0
        self.brush = "#"
        self.mirror = True
        self.modes = {"team_survival"}
        self.name = ""
        self.map_id = None
        self.painting = 0
        self.load_idx = -1
        self._new_tiles()
        super().__init__(game)

    def _new_tiles(self):
        _, w, h = SIZES[self.size_idx]
        self.tiles = [["."] * w for _ in range(h)]

    # ------------------------------------------------------------ layout
    @property
    def grid_rect(self):
        h = len(self.tiles)
        w = len(self.tiles[0])
        cell = int(min(800 / w, 560 / h))
        gw, gh = cell * w, cell * h
        x = self.X(24, gw)
        return pygame.Rect(x, 100, gw, gh), cell

    def build(self):
        self.widgets = []
        self.add_header("editor.title")
        px = self.X(852, 404)
        # palette
        for i, t in enumerate(PALETTE):
            col, row = i % 8, i // 8
            if self.rtl:
                col = 7 - col
            b = self.add(Button((px + col * 50, 96 + row * 54, 46, 46), "", lambda t=t: self.set_brush(t), theme.PANEL,
                                radius=8, icon=lambda s, r, t=t: self._tile_icon(s, r, t)))
            b.selected = t == self.brush
        self.add(Selector((px, 212, 404, 44), [self.tr("theme.%s" % t) for t in self.theme_ids], self.theme_idx,
                          self.set_theme))
        self.add(Selector((px, 266, 404, 44), [self.tr("editor.size_%s" % s[0]) for s in SIZES], self.size_idx,
                          self.set_size, theme.BLUE))
        self.add(Toggle((px + (0 if not self.rtl else 404 - 64), 322, 64, 34), self.mirror, self.set_mirror, self.rtl))
        # mode toggles
        for i, mid in enumerate(self.game.data.mode_order):
            col, row = i % 2, i // 2
            if self.rtl:
                col = 1 - col
            b = self.add(Button((px + col * 206, 366 + row * 44, 198, 38), self.tr("mode.%s.name" % mid),
                                lambda m=mid: self.toggle_mode(m), theme.PURPLE if mid in self.modes else theme.GREY, 14,
                                radius=10))
            b.selected = mid in self.modes
        self.name_input = self.add(TextInput((px, 504, 404, 42), self.name, 20, self.set_name, 20))
        self.name_input.placeholder = self.tr("editor.untitled")
        bw = 128
        btns = [("editor.new", theme.RED, self.ask_new), ("editor.load", theme.BLUE, self.load_next),
                ("editor.save", theme.GREEN, self.save)]
        for i, (k, c, cb) in enumerate(btns):
            idx = (2 - i) if self.rtl else i
            self.add(Button((px + idx * (bw + 10), 558, bw, 50), self.tr(k), cb, c, 20))
        self.add(Button((px, 622, 404, 58), self.tr("editor.test"), self.test, theme.YELLOW, 26, icon=icons.play))

    def _tile_icon(self, s, r, t):
        th = self.game.data.themes.get(self.theme_ids[self.theme_idx], {})
        inner = pygame.Rect(r).inflate(-4, -4)
        if t in MARK_COLORS:
            s.fill(tuple(th.get("floor_a", (130, 200, 100))), inner)
            pygame.draw.circle(s, MARK_COLORS[t], inner.center, inner.w // 3)
            text.draw(s, t, inner.center, 14, theme.WHITE, "center", "middle", rtl=False)
        else:
            s.fill(tile_color(t, th), inner)
            if t == "P":
                pygame.draw.rect(s, (90, 255, 140), inner.inflate(-20, -20))
            if t == ".":
                text.draw(s, "·", inner.center, 18, theme.INK, "center", "middle", outline=0, rtl=False)

    # ------------------------------------------------------------ actions
    def set_brush(self, t):
        self.brush = t
        self._keep_name()
        self.build()

    def set_theme(self, i):
        self.theme_idx = i

    def set_size(self, i):
        self.size_idx = i
        self._new_tiles()
        if i == 1:
            self.modes = {"solo_survival"}
        elif "solo_survival" in self.modes:
            self.modes = {"team_survival"}
        self._keep_name()
        self.build()

    def set_mirror(self, v):
        self.mirror = v

    def toggle_mode(self, mid):
        if mid in self.modes:
            self.modes.discard(mid)
        else:
            self.modes.add(mid)
        self._keep_name()
        self.build()

    def set_name(self, v):
        self.name = v.strip()

    def _keep_name(self):
        if hasattr(self, "name_input"):
            self.name = self.name_input.value.strip()

    def ask_new(self):
        def do():
            self._new_tiles()
            self.map_id = None
            self.name = ""
            self.build()
        self.open_dialog(Dialog(self.tr("editor.new"), self.tr("editor.new_body"),
                                [(self.tr("common.cancel"), theme.GREY, None), (self.tr("common.confirm"), theme.RED, do)]))

    def load_next(self):
        self.game.data.reload_maps()
        customs = sorted([m for m in self.game.data.maps.values() if m.get("custom")], key=lambda m: m["id"])
        if not customs:
            self.game.toasts.push(self.tr("editor.no_custom"), theme.RED)
            return
        self.load_idx = (self.load_idx + 1) % len(customs)
        m = customs[self.load_idx]
        rows = m["tiles"]
        w = max(len(r) for r in rows)
        self.size_idx = 1 if (w, len(rows)) == (35, 25) else 0
        self.tiles = [list(r.ljust(w, ".")) for r in rows]
        self.modes = set(m.get("modes", []))
        self.name = m.get("name", m["id"])
        self.map_id = m["id"]
        if m.get("theme") in self.theme_ids:
            self.theme_idx = self.theme_ids.index(m["theme"])
        self.build()
        self.game.toasts.push(self.tr("editor.loaded", name=self.name), theme.BLUE)

    def _map_data(self):
        self._keep_name()
        name = self.name or self.tr("editor.untitled")
        if not self.map_id:
            slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "map"
            self.map_id = "custom_%s_%d" % (slug[:20], int(time.time()) % 100000)
        return {"id": self.map_id, "name": name, "theme": self.theme_ids[self.theme_idx],
                "modes": [m for m in self.game.data.mode_order if m in self.modes],
                "tiles": ["".join(r) for r in self.tiles]}

    def save(self, quiet=False):
        data = self._map_data()
        errs = validate(data["tiles"], data["modes"])
        if errs:
            self.open_dialog(Dialog(self.tr("editor.invalid"), "\n".join(self.tr(e) for e in errs),
                                    [(self.tr("common.ok"), theme.BLUE, None)], height=340))
            return False
        os.makedirs(config.CUSTOM_MAPS_DIR, exist_ok=True)
        path = os.path.join(config.CUSTOM_MAPS_DIR, data["id"] + ".json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        except OSError:
            self.game.toasts.push(self.tr("editor.save_failed"), theme.RED)
            return False
        self.game.data.reload_maps()
        if not quiet:
            self.game.audio.play("reward")
            self.game.toasts.push(self.tr("editor.saved", name=data["name"]), theme.GREEN)
        return True

    def test(self):
        if not self.save(quiet=True):
            return
        mode = [m for m in self.game.data.mode_order if m in self.modes][0]
        from ilbrawl.gameplay.battle_scene import BattleScene
        self.game.push(BattleScene(self.game, mode, self.map_id, self.game.profile.data["selected_char"]))

    # ------------------------------------------------------------ painting
    def _paint(self, pos, erase=False):
        gr, cell = self.grid_rect
        if not gr.collidepoint(pos):
            return
        x = (pos[0] - gr.x) // cell
        y = (pos[1] - gr.y) // cell
        h, w = len(self.tiles), len(self.tiles[0])
        t = "." if erase else self.brush
        cells = [(x, y, t)]
        if self.mirror:
            if SIZES[self.size_idx][0] == "team":
                cells.append((w - 1 - x, y, SWAP.get(t, t)))
            else:
                cells += [(w - 1 - x, y, t), (x, h - 1 - y, t), (w - 1 - x, h - 1 - y, t)]
        for cx, cy, tt in cells:
            if 0 <= cx < w and 0 <= cy < h:
                self.tiles[cy][cx] = tt

    def on_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
            gr, _ = self.grid_rect
            if gr.collidepoint(e.pos):
                self.painting = e.button
                self._paint(e.pos, e.button == 3)
        elif e.type == pygame.MOUSEMOTION and self.painting:
            self._paint(e.pos, self.painting == 3)
        elif e.type == pygame.MOUSEBUTTONUP:
            self.painting = 0
        else:
            super().on_event(e)

    def draw_content(self, surf):
        self.draw_header(surf)
        gr, cell = self.grid_rect
        th = self.game.data.themes.get(self.theme_ids[self.theme_idx], {})
        pygame.draw.rect(surf, theme.INK, gr.inflate(8, 8), border_radius=6)
        fa = tuple(th.get("floor_a", (130, 200, 100)))
        fb = tuple(th.get("floor_b", (120, 190, 90)))
        for y, row in enumerate(self.tiles):
            for x, c in enumerate(row):
                r = pygame.Rect(gr.x + x * cell, gr.y + y * cell, cell, cell)
                surf.fill(fa if (x + y) % 2 == 0 else fb, r)
                if c in MARK_COLORS:
                    pygame.draw.circle(surf, MARK_COLORS[c], r.center, cell // 2 - 2)
                    if cell >= 20:
                        text.draw(surf, c, r.center, 12, theme.WHITE, "center", "middle", outline=2, rtl=False)
                elif c != ".":
                    surf.fill(tile_color(c, th), r.inflate(-2, -2))
                    if c == "P":
                        pygame.draw.rect(surf, (90, 255, 140), r.inflate(-cell // 2, -cell // 2))
        if self.mirror:
            if SIZES[self.size_idx][0] == "team":
                mx = gr.x + gr.w // 2
                pygame.draw.line(surf, theme.YELLOW, (mx, gr.y), (mx, gr.bottom), 1)
            else:
                pygame.draw.line(surf, theme.YELLOW, (gr.centerx, gr.y), (gr.centerx, gr.bottom), 1)
                pygame.draw.line(surf, theme.YELLOW, (gr.x, gr.centery), (gr.right, gr.centery), 1)
        mp = self.game.mouse_pos
        if gr.collidepoint(mp):
            x = (mp[0] - gr.x) // cell
            y = (mp[1] - gr.y) // cell
            pygame.draw.rect(surf, theme.WHITE, (gr.x + x * cell, gr.y + y * cell, cell, cell), 2)
        px = self.X(852, 404)
        text.draw(surf, self.tr("editor.mirror"), (px + 76 if not self.rtl else px + 404 - 76, 339), 18, theme.WHITE,
                  "start", "middle")
        text.draw(surf, self.tr("editor.tile.%s" % ("floor" if self.brush == "." else self.brush)),
                  (self.X(24), gr.bottom + 14), 18, theme.YELLOW, "start")
        text.draw(surf, self.tr("editor.help"), (self.X(24), gr.bottom + 40), 15, theme.TEXT_DIM, "start",
                  max_width=gr.w)
