"""SKINS (locker) and SHOP screens, both with a live 3D preview of the selected skin."""

from direct.gui.DirectGui import DirectFrame

from ..theme import c
from ..widgets import Button, ScrollList, label, panel, tabs
from .common import BaseScreen


class _SkinBrowser(BaseScreen):
    scene_offset = -0.95  # character shown on the left of the list
    title = ""
    shop_mode = False

    def build(self):
        self.header(self.title, subtitle=self.subtitle)
        th = self.theme
        self.filter = "ALL"
        self.selected = None
        self.tab_holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        self.list = ScrollList(self.root, th, (-0.05, 1.65, -0.8, 0.52))
        self.detail = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        self.msg = label(self.root, th, "", (-0.95, -0.62), 0.045, "text", "bold")
        self.msg_t = 0.0

    def on_show(self, **kw):
        prof = self.app.profile
        if self.selected is None:
            self.selected = prof.skins.equipped
        self.refresh()

    def _set_filter(self, f):
        self.filter = f
        self.refresh()

    def skins(self):
        cat = self.app.profile.catalog
        items = cat.ordered()
        if self.filter != "ALL":
            items = [s for s in items if s.rarity == self.filter]
        return items

    def refresh(self):
        th = self.theme
        prof = self.app.profile
        self.refresh_coins()
        self.tab_holder.destroy()
        self.tab_holder = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        names = [("ALL", "ALL")] + [(r, r) for r in ("COMMON", "RARE", "EPIC", "LEGENDARY", "MYTHIC")]
        tabs(self.tab_holder, th, names, self.filter, self._set_filter, 0.64, x0=-0.05, w=0.26, gap=0.025)
        self.list.clear()
        for skin in self.skins():
            if not self.shop_mode and not prof.skins.is_owned(skin.id):
                continue
            row = self.list.add_row(0.13)
            rar = prof.catalog.rarity_of(skin)
            sel = skin.id == self.selected
            bg = panel(row, th, (0, self.list.width, -0.06, 0.06), "panel_hi" if sel else "panel", 0.92, 0.05,
                       shadow=False, pos=(-0.05, 0, 0))
            DirectFrame(parent=bg, frameColor=c(rar.color), frameSize=(0, 0.02, -0.06, 0.06)).setTransparency(1)
            # Colour swatches of the skin.
            for i, zone in enumerate(("body", "accent")):
                sw = DirectFrame(parent=bg, frameColor=c(skin.colors[zone]), frameSize=(-0.025, 0.025, -0.025, 0.025),
                                 frameTexture=th.rounded(1.0, 0.5, 0.0), pos=(0.07 + i * 0.06, 0, 0))
                sw.setTransparency(1)
            label(bg, th, skin.name, (0.19, 0.0), 0.045, "text", "bold", "left")
            label(bg, th, rar.id + ("  +  " + skin.accessory.replace("_", " ").upper() if skin.accessory else ""),
                  (0.19, -0.042), 0.027, rar.color, "bold", "left")
            status, col = self._status(skin)
            label(bg, th, status, (self.list.width - 0.4, -0.012), 0.035, col, "bold", "right")
            Button(bg, th, "VIEW", (self.list.width - 0.18, 0), (0.24, 0.08), self._select, [skin.id],
                   color="blue" if not sel else "primary", scale=0.034)
        self._detail()

    def _status(self, skin):
        prof = self.app.profile
        if prof.skins.equipped == skin.id:
            return "EQUIPPED", "success"
        if prof.skins.is_owned(skin.id):
            return "OWNED", "accent"
        if prof.unmet_skin_requirements(skin.id):
            return "LOCKED", "muted"
        return "{:,} COINS".format(skin.price), "secondary"

    def _select(self, skin_id):
        self.selected = skin_id
        self.app.menu_scene.set_skin(self.app.profile.catalog.get(skin_id))
        self.refresh()

    def _detail(self):
        th = self.theme
        prof = self.app.profile
        skin = prof.catalog.get(self.selected)
        self.app.menu_scene.set_skin(skin)
        self.detail.destroy()
        self.detail = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0))
        rar = prof.catalog.rarity_of(skin)
        # Dark backing panels keep the text readable over the bright 3D preview.
        top = panel(self.detail, th, (-0.5, 0.5, -0.1, 0.09), "bg", 0.8, 0.06, shadow=False, pos=(-0.95, 0, 0.57))
        label(top, th, skin.name, (0, 0.0), 0.065, "text", "title")
        label(top, th, rar.id, (0, -0.07), 0.04, rar.color, "title")
        info = panel(self.detail, th, (-0.55, 0.55, -0.08, 0.08), "bg", 0.8, 0.06, shadow=False, pos=(-0.95, 0, -0.42))
        label(info, th, skin.description, (0, 0.015), 0.036, "text", "body", wordwrap=28)
        owned = prof.skins.is_owned(skin.id)
        if owned:
            eq = prof.skins.equipped == skin.id
            b = Button(self.detail, th, "EQUIPPED" if eq else "EQUIP", (-0.95, -0.75), (0.6, 0.11), self._equip,
                       [skin.id], color="success")
            b.set_enabled(not eq)
        elif self.shop_mode:
            reasons = prof.unmet_skin_requirements(skin.id)
            if reasons:
                label(self.detail, th, "LOCKED: " + "; ".join(reasons), (-0.95, -0.5), 0.035, "danger", "bold",
                      wordwrap=30)
            afford = prof.currency.balance >= skin.price
            self.buy_btn = Button(self.detail, th, "BUY  {:,}".format(skin.price), (-0.95, -0.75), (0.6, 0.11),
                                  self._buy, [skin.id], color="secondary", text_color="dark")
            self.buy_btn.set_enabled(afford and not reasons)
        else:
            label(self.detail, th, "Not owned - get it in the SHOP", (-0.95, -0.75), 0.04, "muted", "bold")

    def _equip(self, skin_id):
        prof = self.app.profile
        prof.skins.equip(skin_id)
        if prof.save():
            self.flash("Equipped %s!" % prof.catalog.get(skin_id).name, "success")
        else:
            self.flash("Could not save - equip not stored.", "danger")
        self.refresh()

    def _buy(self, skin_id):
        btn = getattr(self, "buy_btn", None)
        if btn is not None:
            btn.set_enabled(False)  # no double charge from rapid clicks
        res = self.app.profile.shop.purchase(skin_id)
        if res.ok:
            self.app.sounds.play("coin")
            self.app.menu_scene.celebrate()
            self.flash(res.message, "success")
        else:
            self.app.sounds.play("error")
            self.flash(res.message, "danger")
        self.refresh()

    def flash(self, text, color):
        self.msg["text"] = text
        self.msg["text_fg"] = c(color)
        self.msg_t = 3.0

    def update(self, dt):
        if self.msg_t > 0:
            self.msg_t -= dt
            if self.msg_t <= 0:
                self.msg["text"] = ""

    def on_hide(self):
        self.selected = None
        self.app.menu_scene.set_skin(self.app.profile.catalog.get(self.app.profile.skins.equipped))


class SkinsScreen(_SkinBrowser):
    name = "skins"
    title = "SKINS"
    subtitle = "Your locker - pick an outfit to wear in every show"
    shop_mode = False


class ShopScreen(_SkinBrowser):
    name = "shop"
    title = "SHOP"
    subtitle = "Spend BONK COINS (earned by playing - no real money)"
    shop_mode = True
