"""XON SHOP tab: daily rotation, item preview and purchase confirmation."""
from __future__ import annotations

import datetime as dt

from economy.shop import PurchaseError
from ui import theme as T
from ui.lobby.common import ItemCard, Tab, header
from ui.widgets import Button, Modal, frame, image, text


class ShopTab(Tab):
    def build(self):
        r = self.root
        front = self.svc.shop.storefront()
        self.front = front
        header(r, "XON SHOP", "Everything here is earned with XON from playing. No real money, ever.")
        self.timer = text(r, "", (1.62, 0.7), 0.032, T.TEXT_DIM, "bold", "right")
        owned = self.svc.locker.owned_ids(self.account.id)
        text(r, "FEATURED", (-1.62, 0.52), 0.035, T.GOLD, "black")
        for i, item in enumerate(front.featured):
            x = -1.32 + i * 0.64
            self._card(item, (x, 0.1), (0.6, 0.78), owned)
        text(r, "DAILY", (-0.25, 0.52), 0.035, T.ACCENT, "black")
        for i, item in enumerate(front.daily):
            col, row = i % 3, i // 3
            self._card(item, (-0.06 + col * 0.42, 0.29 - row * 0.44), (0.39, 0.41), owned)
        text(r, "Prices are in XON. Purchases are stored on this PC in your local profile.", (-1.62, -0.66), 0.028,
             T.TEXT_MUTED, "semibold")
        self.update(0)

    def _card(self, item, pos, size, owned):
        has = item.id in owned
        ItemCard(self.root, item, pos=pos, size=size, price=None if has else item.price,
                 status="OWNED" if has else "", status_color=T.GREEN, on_click=self._open)

    def update(self, dt_):
        secs = self.front.seconds_until_refresh()
        self.timer.setText(f"NEW ITEMS IN {secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}")

    def _open(self, item):
        acc = self.account.id
        owned = self.svc.locker.owns(acc, item.id)
        bal = self.svc.wallet.balance(acc)
        if item.type in ("outfit", "backpack", "pickaxe"):
            self.lobby.refresh_avatar({item.type: item.id})
            self.lobby.preview_override = True
        rar = self.svc.catalog.rarity(item)
        body = f"{rar.label} {item.type_label}" + (f" • {item.set} Set" if item.set else "") + f"\n\n{item.description}"
        if owned:
            buttons = [("Close", None, ()), ("Equip", self._equip, (item,))]
        elif bal >= item.price:
            buttons = [("Cancel", None, ()), (f"Buy for {item.price:,} XON", self._confirm, (item,))]
        else:
            body += f"\n\nYou need {item.price - bal:,} more XON. Play matches and finish quests to earn it."
            buttons = [("Close", None, ())]
        m = Modal(self.app, item.name.upper(), body, buttons, width=1.3, height=1.0)
        image(m.box, self.app.assets.thumb(item.id), (0, 0.05), (0.42, 0.42))

    def _confirm(self, item):
        Modal(self.app, "CONFIRM PURCHASE", f"Spend {item.price:,} XON on {item.name}?\nYou'll have "
              f"{self.svc.wallet.balance(self.account.id) - item.price:,} XON left.",
              [("Cancel", None, ()), ("Confirm", self._buy, (item,))], width=1.0, height=0.5)

    def _buy(self, item):
        try:
            self.svc.shop.purchase(self.account.id, item.id)
        except PurchaseError as exc:
            self.app.toasts.show(str(exc), "error")
            return
        self.app.audio.play("ui_purchase")
        self.app.toasts.show(f"{item.name} added to your Locker!", "success")
        self.lobby.refresh_wallet()
        self.rebuild()

    def _equip(self, item):
        self.svc.locker.equip(self.account.id, item.id)
        self.lobby.refresh_avatar()
        self.app.toasts.show(f"Equipped {item.name}", "success")
