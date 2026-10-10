"""In-match heads-up display."""
from __future__ import annotations

import math

import numpy as np
from direct.gui.DirectGui import DirectFrame
from panda3d.core import LineSegs, NodePath, Texture, TransparencyAttrib

from combat.weapons import WeaponInstance
from inventory.match_inventory import ConsumableStack
from ui import theme as T
from ui.widgets import ProgressBar, frame, image, text
from world.terrain import HALF_EXTENT


def _fmt_time(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


class HUD:
    def __init__(self, app, sim):
        self.app = app
        self.sim = sim
        self.root = app.aspect2d.attachNewNode("hud")
        self.assets = app.assets
        bl, br, tr, tl = app.a2dBottomLeft, app.a2dBottomRight, app.a2dTopRight, app.a2dTopLeft
        self.nodes = []

        # health / shield (bottom left)
        self.vitals = bl.attachNewNode("vitals")
        self.vitals.setPos(0.08, 0, 0.12)
        frame(self.vitals, -0.03, 0.78, -0.05, 0.16, (0.04, 0.05, 0.1, 0.55))
        self.shield_bar = ProgressBar(self.vitals, (0.0, 0.1), (0.6, 0.035), T.ACCENT)
        self.health_bar = ProgressBar(self.vitals, (0.0, 0.03), (0.6, 0.045), T.GREEN)
        self.shield_txt = text(self.vitals, "0", (0.68, 0.088), 0.04, T.ACCENT, "bold")
        self.health_txt = text(self.vitals, "100", (0.68, 0.015), 0.05, T.TEXT, "black")
        self.name_txt = text(self.vitals, "", (0.0, 0.17 - 0.02), 0.032, T.TEXT_DIM, "semibold")
        self.nodes.append(self.vitals)

        # hotbar (bottom right)
        self.hotbar = br.attachNewNode("hotbar")
        self.hotbar.setPos(-0.08, 0, 0.12)
        self.slots = []
        for i in range(6):
            x = -0.13 * (5 - i) - 0.06
            box = frame(self.hotbar, -0.055, 0.055, -0.055, 0.055, (0.05, 0.06, 0.12, 0.7), border=(1, 1, 1, 0.15))
            box.setPos(x, 0, 0)
            key = text(box, str(i + 1), (-0.045, 0.03), 0.025, T.TEXT_DIM, "bold")
            count = text(box, "", (0.048, -0.048), 0.026, T.TEXT, "bold", "right")
            rarity = DirectFrame(parent=box, frameSize=(-0.055, 0.055, -0.055, -0.045), frameColor=(0, 0, 0, 0))
            self.slots.append({"box": box, "count": count, "rarity": rarity, "img": None, "item": "?", "key": key})
        self.ammo_big = text(self.hotbar, "", (-0.38, 0.1), 0.06, T.TEXT, "black", "right")
        self.ammo_small = text(self.hotbar, "", (-0.36, 0.1), 0.035, T.TEXT_DIM, "bold")
        self.weapon_name = text(self.hotbar, "", (-0.06, 0.1), 0.036, T.TEXT, "bold", "right")
        self.nodes.append(self.hotbar)

        # crosshair + hit marker
        self.cross = self.root.attachNewNode("cross")
        self.cross_lines = []
        for _ in range(4):
            self.cross_lines.append(DirectFrame(parent=self.cross, frameSize=(-0.002, 0.002, 0.0, 0.018),
                                                frameColor=(1, 1, 1, 0.85)))
        DirectFrame(parent=self.cross, frameSize=(-0.0025, 0.0025, -0.0025, 0.0025), frameColor=(1, 1, 1, 0.9))
        self.hitmarker = self.root.attachNewNode("hit")
        for a in (45, 135, 225, 315):
            f = DirectFrame(parent=self.hitmarker, frameSize=(-0.003, 0.003, 0.012, 0.03), frameColor=(1, 1, 1, 1))
            f.setR(a)
        self.hitmarker.hide()
        self.hit_time = -9.0
        self.scope = None

        # minimap + match info (top right)
        self.map_root = tr.attachNewNode("minimap")
        self.map_root.setPos(-0.3, 0, -0.32)
        self.map_size = 0.24
        self.map_tex = self._map_texture()
        frame(self.map_root, -0.255, 0.255, -0.255, 0.255, (0.05, 0.06, 0.12, 0.8))
        self.map_clip = self.map_root.attachNewNode("clip")
        from panda3d.core import ScissorEffect
        self.map_clip.setEffect(ScissorEffect.makeNode((-0.25, 0, -0.25), (0.25, 0, 0.25)))
        self.map_img = image(self.map_clip, self.map_tex, (0, 0), (0.48, 0.48), fit=False)
        self.map_overlay = self.map_root.attachNewNode("overlay")
        arrow = LineSegs()
        arrow.setThickness(3)
        arrow.setColor(1, 1, 1, 1)
        arrow.moveTo(0, 0, 0.02)
        arrow.drawTo(-0.012, 0, -0.012)
        arrow.drawTo(0.012, 0, -0.012)
        arrow.drawTo(0, 0, 0.02)
        self.map_arrow = self.map_root.attachNewNode(arrow.create())
        self.info = text(self.map_root, "", (0, -0.31), 0.034, T.TEXT, "bold", "center")
        self.storm_txt = text(self.map_root, "", (0, -0.36), 0.03, T.TEXT_DIM, "semibold", "center")
        self.nodes.append(self.map_root)

        # kill feed (top left)
        self.feed_root = tl.attachNewNode("feed")
        self.feed_root.setPos(0.06, 0, -0.12)
        self.feed: list[tuple[float, object]] = []

        # prompts and notices
        self.prompt = text(self.root, "", (0, -0.42), 0.042, T.TEXT, "bold", "center", shadow=True)
        self.prompt_bar = ProgressBar(self.root, (-0.15, -0.47), (0.3, 0.012), T.ACCENT)
        self.prompt_bar.back.hide()
        self.center_msg = text(self.root, "", (0, 0.45), 0.075, T.TEXT, "black", "center", shadow=True)
        self.sub_msg = text(self.root, "", (0, 0.38), 0.04, T.TEXT_DIM, "semibold", "center", shadow=True)
        self.msg_until = 0.0
        self.notice = text(self.root, "", (0, -0.3), 0.036, T.GOLD, "semibold", "center", shadow=True)
        self.notice_until = 0.0
        self.storm_tint = DirectFrame(parent=self.root, frameSize=(-3, 3, -2, 2), frameColor=(0.45, 0.15, 0.8, 0.0))
        self.storm_tint.setBin("background", 10)
        self.damage_flash = DirectFrame(parent=self.root, frameSize=(-3, 3, -2, 2), frameColor=(1, 0.1, 0.1, 0.0))
        self.damage_flash_t = -9.0
        self.big_map = None
        self.fps = text(app.a2dTopLeft, "", (0.06, -0.06), 0.03, T.TEXT_DIM)

    # ------------------------------------------------------------- map
    def _map_texture(self) -> Texture:
        h = self.sim.terrain.h
        n = h.shape[0]
        img = np.zeros((n, n, 3), np.float32)
        water = h < 0
        sand = (h >= 0) & (h < 4)
        img[water] = (0.1, 0.32, 0.5)
        img[sand] = (0.85, 0.78, 0.55)
        land = h >= 4
        shade = np.clip(h / 60.0, 0, 1)[..., None]
        img[land] = ((0.28, 0.52, 0.25) * (1 - shade) + (0.55, 0.52, 0.45) * shade)[land]
        for p in self.sim.layout.pois:
            yy, xx = np.ogrid[:n, :n]
            cx, cy = (p.x + HALF_EXTENT) / (2 * HALF_EXTENT) * n, (p.y + HALF_EXTENT) / (2 * HALF_EXTENT) * n
            m = (xx - cx) ** 2 + (yy - cy) ** 2 < (p.radius / (2 * HALF_EXTENT) * n * 0.6) ** 2
            img[m] = img[m] * 0.6 + np.array((0.75, 0.75, 0.8)) * 0.4
        data = (np.clip(img, 0, 1) * 255).astype(np.uint8)[::-1]
        tex = Texture("minimap")
        tex.setup2dTexture(n, n, Texture.T_unsigned_byte, Texture.F_rgb8)
        tex.setRamImageAs(np.ascontiguousarray(data[::-1]).tobytes(), "RGB")
        return tex

    def _world_to_map(self, x, y, cx, cy, zoom):
        return ((x - cx) / zoom, (y - cy) / zoom)

    def _update_minimap(self, p):
        zoom_world = 260.0  # metres shown edge to edge
        scale = 0.48 / zoom_world
        # move the full-map image so the player is centred
        full = 2 * HALF_EXTENT * scale
        if self.map_img is not None:
            self.map_img.setScale(full / 2, 1, full / 2)
            self.map_img.setPos(-p.x * scale, 0, -p.y * scale)
        self.map_arrow.setR(-p.yaw)
        self.map_overlay.node().removeAllChildren()
        ls = LineSegs()
        ls.setThickness(2)
        st = self.sim.storm

        def circle(cx, cy, r, color):
            ls.setColor(*color)
            first = True
            for i in range(65):
                a = 2 * math.pi * i / 64
                x = (cx + math.cos(a) * r - p.x) * scale
                y = (cy + math.sin(a) * r - p.y) * scale
                x = max(-0.25, min(0.25, x))
                y = max(-0.25, min(0.25, y))
                if first:
                    ls.moveTo(x, 0, y)
                    first = False
                else:
                    ls.drawTo(x, 0, y)
        circle(st.center[0], st.center[1], st.radius, (0.75, 0.35, 1.0, 1))
        circle(st.target_center[0], st.target_center[1], st.target_radius, (1, 1, 1, 0.9))
        self.map_overlay.attachNewNode(ls.create())

    # ------------------------------------------------------------- feed
    def add_feed(self, message: str, color=T.TEXT) -> None:
        node = text(self.feed_root, message, (0, 0), 0.032, color, "semibold", shadow=True)
        self.feed.append((self.sim.time, node))
        if len(self.feed) > 6:
            self.feed.pop(0)[1].destroy()
        self._layout_feed()

    def _layout_feed(self):
        for i, (_, node) in enumerate(reversed(self.feed)):
            node.setPos(0, -i * 0.045)

    def show_message(self, title: str, sub: str = "", duration: float = 3.0) -> None:
        self.center_msg.setText(title)
        self.sub_msg.setText(sub)
        self.msg_until = self.sim.time + duration

    def show_notice(self, message: str, duration: float = 2.0) -> None:
        self.notice.setText(message)
        self.notice_until = self.sim.time + duration

    def hit(self, head: bool) -> None:
        self.hit_time = self.sim.time
        self.hitmarker.setColor((1, 0.25, 0.25, 1) if head else (1, 1, 1, 1))
        self.hitmarker.show()

    def hurt(self) -> None:
        self.damage_flash_t = self.sim.time

    # ------------------------------------------------------------- update
    def update(self, p, prompt: str | None, interact_frac: float, spread: float, scoped: bool, fps: float | None) -> None:
        sim = self.sim
        self.name_txt.setText(p.name)
        self.health_bar.set(p.health / 100)
        self.shield_bar.set(p.shield / 100)
        self.health_txt.setText(str(int(math.ceil(p.health))))
        self.shield_txt.setText(str(int(math.ceil(p.shield))))
        inv = p.inventory
        for i, slot in enumerate(self.slots):
            item = None if i == 0 else inv.slots[i - 1]
            key = "pickaxe" if i == 0 else (id(item) if item is not None else None)
            if slot["item"] != key:
                slot["item"] = key
                if slot["img"] is not None:
                    slot["img"].destroy()
                    slot["img"] = None
                asset = None
                rarity = None
                if i == 0:
                    asset = p.loadout.get("pickaxe", "pickaxe_iron_pick")
                elif isinstance(item, WeaponInstance):
                    asset = "weapon_" + item.wdef.id
                    rarity = item.rarity
                elif isinstance(item, ConsumableStack):
                    asset = "item_" + item.cid
                    rarity = self.sim.armory.consumables[item.cid].rarity
                if asset:
                    slot["img"] = image(slot["box"], self.assets.thumb(asset), (0, 0.004), (0.1, 0.1))
                slot["rarity"]["frameColor"] = T.RARITY.get(rarity, (0, 0, 0, 0)) if rarity else (0, 0, 0, 0)
            if isinstance(item, WeaponInstance):
                slot["count"].setText(str(item.in_mag))
            elif isinstance(item, ConsumableStack):
                slot["count"].setText(str(item.count))
            else:
                slot["count"].setText("")
            sel = inv.selected == i
            slot["box"]["frameColor"] = (0.25, 0.2, 0.5, 0.85) if sel else (0.05, 0.06, 0.12, 0.7)
            slot["box"].setScale(1.12 if sel else 1.0)
        cur = inv.current
        if isinstance(cur, WeaponInstance):
            self.ammo_big.setText(str(cur.in_mag))
            self.ammo_small.setText(f"/ {inv.ammo.get(cur.wdef.ammo, 0)}")
            self.weapon_name.setText(f"{cur.rarity.title()} {cur.name}")
            self.weapon_name["fg"] = T.RARITY[cur.rarity]
        elif isinstance(cur, ConsumableStack):
            self.ammo_big.setText("")
            self.ammo_small.setText("")
            self.weapon_name.setText(self.sim.armory.consumables[cur.cid].name + "  [LMB] use")
            self.weapon_name["fg"] = T.TEXT
        else:
            self.ammo_big.setText("")
            self.ammo_small.setText("")
            self.weapon_name.setText("Pickaxe")
            self.weapon_name["fg"] = T.TEXT
        if p.reload_timer > 0:
            self.prompt.setText("Reloading...")
        elif p.use_timer > 0:
            self.prompt.setText(f"Using... {p.use_timer:.1f}s")
        else:
            self.prompt.setText(f"[E] {prompt}" if prompt else "")
        if interact_frac > 0:
            self.prompt_bar.back.show()
            self.prompt_bar.set(interact_frac)
        else:
            self.prompt_bar.back.hide()
        # crosshair
        gap = 0.012 + spread * 0.012
        for i, line in enumerate(self.cross_lines):
            line.setR(i * 90)
            line.setPos(0, 0, 0)
            a = math.radians(i * 90)
            line.setPos(math.sin(a) * gap, 0, math.cos(a) * gap)
        self.cross.setAlphaScale(0.0 if scoped or p.state != "ground" else 1.0)
        if sim.time - self.hit_time > 0.15:
            self.hitmarker.hide()
        # match info
        alive = len(sim.alive)
        self.info.setText(f"{alive} ALIVE    {p.stats.eliminations} ELIMS")
        st = sim.storm.state()
        if st.phase >= len(sim.storm.phases):
            self.storm_txt.setText("Final circle")
        elif st.shrinking:
            self.storm_txt.setText(f"Storm closing  {_fmt_time(st.time_left)}")
        else:
            self.storm_txt.setText(f"Storm shrinks in {_fmt_time(st.time_left)}")
        self._update_minimap(p)
        outside = sim.storm.outside(p.x, p.y) and p.alive
        self.storm_tint["frameColor"] = (0.45, 0.15, 0.8, 0.22 if outside else 0.0)
        fl = max(0.0, 0.35 - (sim.time - self.damage_flash_t)) * 0.8
        self.damage_flash["frameColor"] = (1, 0.1, 0.1, fl)
        if sim.time > self.msg_until:
            self.center_msg.setText("")
            self.sub_msg.setText("")
        if sim.time > self.notice_until:
            self.notice.setText("")
        while self.feed and sim.time - self.feed[0][0] > 8:
            self.feed.pop(0)[1].destroy()
            self._layout_feed()
        self.fps.setText(f"{fps:.0f} FPS" if fps else "")

    def set_scoped(self, scoped: bool) -> None:
        if scoped and self.scope is None:
            self.scope = self.app.aspect2d.attachNewNode("scope")
            ring = LineSegs()
            ring.setThickness(3)
            ring.setColor(0, 0, 0, 1)
            for i in range(97):
                a = 2 * math.pi * i / 96
                (ring.moveTo if i == 0 else ring.drawTo)(math.cos(a) * 0.7, 0, math.sin(a) * 0.7)
            ring.moveTo(-0.7, 0, 0)
            ring.drawTo(0.7, 0, 0)
            ring.moveTo(0, 0, -0.7)
            ring.drawTo(0, 0, 0.7)
            self.scope.attachNewNode(ring.create())
            for fs in ((-3, -0.7, -2, 2), (0.7, 3, -2, 2), (-0.7, 0.7, 0.7, 2), (-0.7, 0.7, -2, -0.7)):
                DirectFrame(parent=self.scope, frameSize=fs, frameColor=(0, 0, 0, 0.92))
        elif not scoped and self.scope is not None:
            self.scope.removeNode()
            self.scope = None

    def toggle_big_map(self, player) -> None:
        if self.big_map is not None:
            self.big_map.removeNode()
            self.big_map = None
            return
        root = self.app.aspect2d.attachNewNode("bigmap")
        frame(root, -0.88, 0.88, -0.88, 0.88, (0.03, 0.04, 0.08, 0.9))
        image(root, self.map_tex, (0, 0), (1.7, 1.7), fit=False)
        k = 1.7 / (2 * HALF_EXTENT)
        for p in self.sim.layout.pois:
            text(root, p.name.upper(), (p.x * k, p.y * k), 0.03, T.TEXT, "black", "center", shadow=True)
        ls = LineSegs()
        ls.setThickness(2)
        st = self.sim.storm
        for (cx, cy), r, col in ((st.center, st.radius, (0.75, 0.35, 1, 1)), (st.target_center, st.target_radius, (1, 1, 1, 1))):
            ls.setColor(*col)
            for i in range(97):
                a = 2 * math.pi * i / 96
                x, y = (cx + math.cos(a) * r) * k, (cy + math.sin(a) * r) * k
                x, y = max(-0.85, min(0.85, x)), max(-0.85, min(0.85, y))
                (ls.moveTo if i == 0 else ls.drawTo)(x, 0, y)
        if not self.sim.ship.finished:
            ls.setColor(0.2, 0.9, 1, 1)
            ls.moveTo(self.sim.ship.start[0] * k, 0, self.sim.ship.start[1] * k)
            ls.drawTo(self.sim.ship.end[0] * k, 0, self.sim.ship.end[1] * k)
        root.attachNewNode(ls.create())
        dot = DirectFrame(parent=root, frameSize=(-0.012, 0.012, -0.012, 0.012), frameColor=T.GOLD,
                          pos=(player.x * k, 0, player.y * k))
        text(root, "MAP  [M] close", (0, -0.84), 0.035, T.TEXT_DIM, "bold", "center")
        self.big_map = root

    def destroy(self) -> None:
        for n in (self.root, self.vitals, self.hotbar, self.map_root, self.feed_root):
            n.removeNode()
        self.fps.destroy()
        if self.big_map is not None:
            self.big_map.removeNode()
        if self.scope is not None:
            self.scope.removeNode()
