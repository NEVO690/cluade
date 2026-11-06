"""In-game shop (fictional currency only)."""
import pygame

from ilbrawl import config
from ilbrawl.characters import sprites
from ilbrawl.engine.scene import Scene
from ilbrawl.menus.main_menu import reward_text, skin_name
from ilbrawl.shop.shop import Shop
from ilbrawl.ui import cosmetic_art, icons, text, theme
from ilbrawl.ui.widgets import Button, Dialog, ScrollPanel, TabBar, Widget

VW, VH = config.VIRTUAL_W, config.VIRTUAL_H
TABS = ["daily", "special", "characters", "skins", "cosmetics", "coins"]


def price_label(scene, price):
    if not price:
        return scene.tr("shop.free")
    k, v = list(price.items())[0]
    return "%d %s" % (v, scene.tr("common." + k))


class ItemCard(Widget):
    def __init__(self, rect, scene, item):
        super().__init__(rect)
        self.scene = scene
        self.item = item
        r = self.rect
        owned = item.get("owned")
        price = item.get("price", {})
        col = theme.GREY if owned else (theme.GREEN if not price else
                                        (theme.ORANGE if "coins" in price else theme.CYAN))
        label = scene.tr("shop.owned") if owned else price_label(scene, price)
        self.btn = Button((r.x + 20, r.bottom - 66, r.w - 40, 54), label, lambda: scene.ask_buy(item), col, 20,
                          enabled=not owned, icon=None if owned or not price else
                          (icons.coin if "coins" in price else icons.gem))

    def _sync(self):
        self.btn.rect.topleft = (self.rect.x + 20, self.rect.bottom - 66)

    def handle_event(self, e):
        self._sync()
        return self.btn.handle_event(e)

    def update(self, dt, mouse_pos):
        super().update(dt, mouse_pos)
        self._sync()
        self.btn.update(dt, mouse_pos)

    def draw(self, surf):
        sc = self.scene
        gd = sc.game.data
        it = self.item
        r = self.rect
        self._sync()  # follow the scroll offset while drawing
        k = it["kind"]
        accent = {"character": theme.RARITY_COLORS.get(gd.characters.get(it["id"], {}).get("rarity"), theme.BLUE),
                  "skin": theme.PINK, "cosmetic": theme.PURPLE, "coins": theme.COIN, "bundle": theme.YELLOW,
                  "gift": theme.GREEN}.get(k, theme.BLUE)
        theme.draw_panel(surf, r, (30, 36, 46), accent, 18, True, 3)
        art = pygame.Rect(r.x + 10, r.y + 10, r.w - 20, 130)
        pygame.draw.rect(surf, theme.darken(accent, 0.55), art, border_radius=12)
        title = ""
        if k == "character":
            st = gd.characters[it["id"]]["style"]
            por = sprites.portrait(st, 130, key=(it["id"], None))
            surf.blit(por, (art.centerx - 65, art.y))
            title = sc.tr("char.%s.name" % it["id"])
        elif k == "skin":
            s = gd.skins[it["id"]]
            st = gd.skin_style(s["char"], it["id"])
            por = sprites.portrait(st, 130, key=(s["char"], it["id"]))
            surf.blit(por, (art.centerx - 65, art.y))
            title = skin_name(sc, it["id"])
        elif k == "cosmetic":
            d = it["def"]
            if it["group"] == "icons":
                cosmetic_art.draw_shape(surf, d["shape"], art.centerx, art.centery, 44, d["color"])
            elif it["group"] == "name_colors":
                text.draw(surf, sc.game.profile.display_name(sc.game.i18n), art.center, 30, tuple(d["color"]), "center",
                          "middle", outline=3, max_width=art.w - 10)
            else:
                text.draw(surf, sc.tr("cosmetic.%s" % it["id"]), art.center, 24, theme.YELLOW, "center", "middle",
                          outline=3, max_width=art.w - 10)
            title = sc.tr("shop.group.%s" % it["group"])
        elif k == "coins":
            for i in range(min(7, 2 + it["amount"] // 200)):
                theme.draw_coin(surf, (art.centerx - 40 + (i % 4) * 26, art.centery + 20 - (i // 4) * 26), 20)
            title = sc.tr("reward.coins", n=it["amount"])
        else:
            icons.gift(surf, pygame.Rect(art.centerx - 50, art.y + 6, 100, 100))
            title = sc.tr("shop.offer.%s" % it["id"])
            sub = ", ".join(reward_text(sc, c) for c in it["contents"])
            text.draw(surf, sub, (art.centerx, art.bottom - 14), 14, theme.WHITE, "center", "middle", max_width=art.w - 8)
        text.draw(surf, title, (r.centerx, r.y + 160), 19, theme.WHITE, "center", "middle", max_width=r.w - 16)
        if it.get("discount"):
            badge = pygame.Rect(r.right - 70, r.y - 8, 74, 30)
            pygame.draw.rect(surf, theme.INK, badge.inflate(4, 4), border_radius=12)
            pygame.draw.rect(surf, theme.RED, badge, border_radius=10)
            text.draw(surf, "-%d%%" % it["discount"], badge.center, 17, theme.WHITE, "center", "middle", rtl=False)
        if it.get("bonus"):
            text.draw(surf, sc.tr("shop.bonus", n=it["bonus"]), (r.centerx, r.y + 184), 15, theme.YELLOW, "center", "middle")
        self.btn.draw(surf)


class ShopScene(Scene):
    def __init__(self, game, tab=0):
        self.tab = tab
        self.shop = Shop(game.profile)
        super().__init__(game)

    def build(self):
        self.widgets = []
        self.add_header("shop.title")
        self.add(TabBar((30, 88, VW - 60, 52), [self.tr("shop.tab.%s" % t) for t in TABS], self.tab, self.set_tab,
                        self.rtl, theme.ORANGE))
        self.panel = self.add(ScrollPanel((20, 156, VW - 40, VH - 166)))
        items = self.items()
        cols, cw, ch, gap = 4, 286, 262, 22
        x0 = ((VW - 40) - (cols * cw + (cols - 1) * gap)) // 2
        for i, it in enumerate(items):
            c, rr = i % cols, i // cols
            if self.rtl:
                c = cols - 1 - c
            self.panel.add(ItemCard((x0 + c * (cw + gap), 14 + rr * (ch + 20), cw, ch), self, it))
        self.panel.content_size = 28 + ((len(items) + cols - 1) // cols) * (ch + 20)
        self.empty = not items

    def items(self):
        s = self.shop
        t = TABS[self.tab]
        if t == "daily":
            return s.daily_items()
        if t == "special":
            return s.special_items()
        if t == "characters":
            return s.character_items()
        if t == "skins":
            return s.skin_items()
        if t == "cosmetics":
            return s.cosmetic_items()
        return s.coin_items()

    def set_tab(self, i):
        self.tab = i
        self.build()

    def item_name(self, it):
        k = it["kind"]
        if k == "character":
            return self.tr("char.%s.name" % it["id"])
        if k == "skin":
            return skin_name(self, it["id"])
        if k == "cosmetic":
            return self.tr("cosmetic.%s" % it["id"])
        if k == "coins":
            return self.tr("reward.coins", n=it["amount"])
        return self.tr("shop.offer.%s" % it["id"])

    def ask_buy(self, it):
        ok, reason = self.shop.can_buy(it)
        if not ok:
            self.game.audio.play("deny")
            self.game.toasts.push(self.tr(reason), theme.RED)
            return

        def do():
            done, why = self.shop.buy(it)
            if done:
                self.game.audio.play("buy")
                self.game.toasts.push(self.tr("shop.bought", name=self.item_name(it)), theme.GREEN)
                keep = self.panel.target
                self.build()
                self.panel.scroll_to(keep, True)
            else:
                self.game.toasts.push(self.tr(why), theme.RED)

        self.open_dialog(Dialog(self.tr("shop.confirm_title"),
                                self.tr("shop.confirm_body", name=self.item_name(it), price=price_label(self, it["price"])),
                                [(self.tr("common.cancel"), theme.GREY, None), (self.tr("shop.buy"), theme.GREEN, do)]))

    def draw_content(self, surf):
        self.draw_header(surf)
        if self.empty:
            text.draw(surf, self.tr("shop.empty"), (VW // 2, 380), 26, theme.TEXT_DIM, "center", "middle")
