"""LOCKER tab: browse owned cosmetics by slot and equip them on the 3D preview."""
from __future__ import annotations

from ui import theme as T
from ui.lobby.common import ItemCard, Tab, header
from ui.widgets import Button, ScrollArea, frame, text

SLOT_LABELS = [("outfit", "OUTFIT"), ("backpack", "BACK BLING"), ("pickaxe", "PICKAXE"), ("glider", "GLIDER"),
               ("emote", "EMOTE"), ("wrap", "WRAP"), ("banner", "BANNER")]
COLS = 4
CARD = (0.3, 0.38)


class LockerTab(Tab):
    slot = "outfit"

    def build(self):
        r = self.root
        header(r, "LOCKER", "Cosmetics change how you look — never how you play.")
        equipped = self.svc.locker.equipped(self.account.id)
        self.slot_buttons = []
        for i, (slot, label) in enumerate(SLOT_LABELS):
            item = self.svc.catalog.items.get(equipped.get(slot))
            b = Button(r, f"{label}\n{item.name if item else '-'}", self._pick_slot, pos=(-1.42, 0.5 - i * 0.135),
                       size=(0.44, 0.115), text_scale=0.028, align="left", extra_args=(slot,))
            b.set_selected(slot == LockerTab.slot)
            self.slot_buttons.append(b)
        owned = self.svc.locker.owned(self.account.id, LockerTab.slot)
        all_items = self.svc.catalog.by_type(LockerTab.slot)
        text(r, f"{len(owned)} / {len(all_items)} OWNED", (-1.12, 0.565), 0.03, T.TEXT_DIM, "bold")
        rows = (len(all_items) + COLS - 1) // COLS
        area = ScrollArea(r, -1.15, 0.2, -0.88, 0.53, rows * (CARD[1] + 0.03) + 0.02)
        self.area = area
        owned_ids = {i.id for i in owned}
        for idx, item in enumerate(all_items):
            col, row = idx % COLS, idx // COLS
            x = -1.15 + 0.02 + CARD[0] / 2 + col * (CARD[0] + 0.03)
            y = -0.02 - CARD[1] / 2 - row * (CARD[1] + 0.03)
            has = item.id in owned_ids
            status = "EQUIPPED" if equipped.get(item.type) == item.id else ("OWNED" if has else _how_to_get(item))
            color = T.ACCENT if status == "EQUIPPED" else (T.TEXT_DIM if has else T.TEXT_MUTED)
            card = ItemCard(area.canvas, item, pos=(x, y), size=CARD, status=status, status_color=color,
                            on_click=self._select, selected=equipped.get(item.type) == item.id)
            if not has:
                card.node.setColorScale(0.55, 0.55, 0.6, 1)
        self.info = r.attachNewNode("info")
        self._show_info(self.svc.catalog.items.get(equipped.get(LockerTab.slot)))

    def _pick_slot(self, slot):
        LockerTab.slot = slot
        self.lobby.refresh_avatar()
        self.rebuild()

    def _select(self, item):
        if not self.svc.locker.owns(self.account.id, item.id):
            self._show_info(item)
            self.app.toasts.show(f"{item.name}: {_how_to_get(item)}", "info")
            if item.type in ("outfit", "backpack", "pickaxe"):
                self.lobby.refresh_avatar({item.type: item.id})
                self.lobby.preview_override = True
            return
        self.svc.locker.equip(self.account.id, item.id)
        self.app.audio.play("equip")
        self.lobby.refresh_avatar()
        if item.type == "emote":
            self.lobby.play_emote(item.extra.get("animation", "emote_wave"),
                                  item.extra.get("prop"))
        elif item.type == "glider":
            self.lobby.avatar.hold(None)
            self.lobby.avatar.show_glider(True)
            self.lobby.avatar.play("glide")
        self.rebuild()
        self._show_info(item)

    def _show_info(self, item):
        self.info.node().removeAllChildren()
        if item is None:
            return
        panel = frame(self.info, 0.3, 1.65, -0.88, -0.6, (0.05, 0.06, 0.12, 0.85))
        rar = self.svc.catalog.rarity(item)
        text(panel, item.name.upper(), (0.34, -0.66), 0.045, T.TEXT, "black")
        text(panel, f"{rar.label.upper()} {item.type_label.upper()}" + (f"  •  {item.set.upper()} SET" if item.set else ""),
             (0.34, -0.71), 0.026, T.RARITY[item.rarity], "bold")
        text(panel, item.description, (0.34, -0.77), 0.028, T.TEXT_DIM, "regular", wrap=44)
        if item.type == "emote":
            Button(panel, "PREVIEW", self.lobby.play_emote, pos=(1.5, -0.66), size=(0.22, 0.07), text_scale=0.026,
                   extra_args=(item.extra.get("animation", "emote_wave"), item.extra.get("prop")))


def _how_to_get(item) -> str:
    return {"shop": "In the XON Shop rotation", "battle_pass": "Battle Pass reward", "quest": "Quest milestone reward",
            "milestone": "Milestone reward", "default": "Default"}.get(item.source, "Locked")
