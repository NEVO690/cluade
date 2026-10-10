"""PROFILE tab: player card, stats, equipped cosmetics, TikTok followers, local accounts."""
from __future__ import annotations

from direct.gui.DirectGui import DirectFrame

from config.branding import SOCIAL_NAME
from social.accounts import AccountError
from ui import theme as T
from ui.lobby.common import Tab, header, icon, item_thumb
from ui.widgets import Button, Entry, Modal, ProgressBar, frame, image, text


class ProfileTab(Tab):
    viewing: int | None = None

    def build(self):
        r = self.root
        me = self.account.id
        target = ProfileTab.viewing or me
        ProfileTab.viewing = None
        acc = self.svc.accounts.get(target)
        own = target == me
        prog = self.svc.progression
        social = self.svc.social.profile(me, target)
        # player card
        loadout = self.svc.locker.equipped(target)
        banner = self.svc.catalog.items.get(loadout.get("banner"))
        card = frame(r, -1.65, -0.2, 0.05, 0.62, T.PANEL)
        if banner:
            image(card, item_thumb(banner), (-1.5, 0.48), (0.2, 0.2))
        text(card, acc.display_name, (-1.36, 0.51), 0.06, T.TEXT, "black")
        tags = [f"@{acc.username}", f"LEVEL {prog.level(target)}"]
        if acc.is_demo:
            tags.append("DEMO ACCOUNT")
        text(card, "  •  ".join(tags), (-1.36, 0.45), 0.028, T.TEXT_DIM, "bold")
        if acc.bio:
            text(card, acc.bio, (-1.6, 0.34), 0.028, T.TEXT_DIM, "regular", wrap=48)
        # TikTok follower count lives right on the Xgun profile
        DirectFrame(parent=card, frameSize=(-1.62, -0.23, 0.08, 0.27), frameColor=(0.12, 0.05, 0.12, 0.9))
        img = image(card, icon("heart"), (-1.55, 0.175), (0.06, 0.06))
        if img is not None:
            img.setColorScale(*T.PINK)
        text(card, f"{social.followers:,}", (-1.48, 0.17), 0.06, T.TEXT, "black")
        text(card, f"{SOCIAL_NAME} FOLLOWERS", (-1.48, 0.12), 0.024, T.PINK, "bold")
        text(card, f"{social.following:,} following   •   {social.total_likes:,} likes   •   {social.video_count} videos",
             (-0.9, 0.2), 0.024, T.TEXT_DIM, "semibold")
        Button(card, f"OPEN {SOCIAL_NAME} PROFILE", self._open_social, pos=(-0.58, 0.135), size=(0.62, 0.065), color=T.PINK,
               hover=(1, 0.45, 0.6, 1), text_scale=0.026, extra_args=(target,))
        # stats
        st = prog.stats(target)
        matches = max(1, st.get("matches", 0))
        stats = [("WINS", st.get("wins", 0)), ("MATCHES", st.get("matches", 0)), ("TOP 10", st.get("top10", 0)),
                 ("ELIMINATIONS", st.get("eliminations", 0)), ("DAMAGE", st.get("damage_dealt", 0)),
                 ("WIN RATE", f"{st.get('wins', 0) / matches:.0%}"), ("CHESTS", st.get("chests_opened", 0)),
                 ("TIME ALIVE", f"{int(st.get('time_alive', 0) // 60)}m")]
        for i, (label, value) in enumerate(stats):
            col, row = i % 4, i // 4
            x = -1.65 + col * 0.365
            y = -0.08 - row * 0.17
            frame(r, x, x + 0.34, y - 0.07, y + 0.07, T.PANEL)
            text(r, str(value), (x + 0.03, y), 0.05, T.TEXT, "black")
            text(r, label, (x + 0.03, y - 0.05), 0.022, T.TEXT_DIM, "bold")
        # equipped
        text(r, "EQUIPPED", (-1.62, -0.48), 0.03, T.TEXT_MUTED, "bold")
        for i, slot in enumerate(["outfit", "backpack", "pickaxe", "glider", "emote", "wrap"]):
            item = self.svc.catalog.items.get(loadout.get(slot))
            if item is None:
                continue
            x = -1.55 + i * 0.24
            frame(r, x - 0.11, x + 0.11, -0.78, -0.53, (*T.RARITY[item.rarity][:3], 0.25))
            image(r, item_thumb(item), (x, -0.63), (0.18, 0.16))
            text(r, item.name, (x, -0.76), 0.018, T.TEXT, "bold", "center", wrap=11)
        # right side: account management or social actions
        if own:
            text(r, "LOCAL ACCOUNTS", (-0.05, 0.55), 0.034, T.TEXT, "black")
            text(r, "Multiple profiles can share this PC (great for testing friends & follows).", (-0.05, 0.5), 0.022,
                 T.TEXT_DIM, "regular", wrap=30)
            y = 0.4
            for a in self.svc.accounts.list(include_demo=False)[:6]:
                b = Button(r, f"{a.display_name}  @{a.username}", self._switch, pos=(0.25, y), size=(0.6, 0.065),
                           text_scale=0.026, align="left", extra_args=(a.id,))
                b.set_selected(a.id == me)
                y -= 0.08
            self.new_name = Entry(r, pos=(-0.05, y - 0.02), width=0.42, placeholder="new_username", scale=0.028, max_chars=16)
            Button(r, "Create", self._create, pos=(0.47, y - 0.005), size=(0.16, 0.06), color=T.PRIMARY, text_scale=0.024)
            Button(r, "Edit profile", self._edit, pos=(0.25, y - 0.12), size=(0.6, 0.065), text_scale=0.026)
        else:
            Button(r, "Back to my profile", self.rebuild, pos=(0.25, 0.55), size=(0.6, 0.065), text_scale=0.026)
            if not self.svc.friends.are_friends(me, target):
                Button(r, "Add friend", self._add_friend, pos=(0.25, 0.46), size=(0.6, 0.065), color=T.PRIMARY,
                       text_scale=0.026, extra_args=(target,))
            else:
                text(r, "You're friends", (0.25, 0.45), 0.03, T.GREEN, "bold", "center")
        recent = prog.recent_matches(target, 5)
        text(r, "RECENT MATCHES", (-0.05, -0.48), 0.03, T.TEXT_MUTED, "bold")
        for i, m in enumerate(recent):
            text(r, f"#{m['placement']} of {m['players']}   {m['eliminations']} elims   +{m['xon_earned']} XON",
                 (-0.05, -0.55 - i * 0.05), 0.025, T.GOLD if m["placement"] == 1 else T.TEXT_DIM, "semibold")
        if not recent:
            text(r, "No matches yet.", (-0.05, -0.55), 0.025, T.TEXT_DIM)

    def _open_social(self, account_id):
        from ui.lobby.tiktok import TikTokTab
        TikTokTab.view = ("profile", account_id)
        self.lobby.select("TIKTOK")

    def _switch(self, account_id):
        if account_id != self.account.id:
            self.app.switch_account(account_id)

    def _create(self):
        name = self.new_name.get().strip()
        try:
            acc = self.svc.accounts.create(name, name)
        except AccountError as exc:
            self.app.toasts.show(str(exc), "error")
            return
        self.app.toasts.show(f"Created local account @{acc.username} (1,000 XON welcome gift)", "success")
        self.app.switch_account(acc.id)

    def _edit(self):
        from ui.lobby.tiktok import TikTokTab
        TikTokTab.view = ("profile", self.account.id)
        self.lobby.select("TIKTOK")
        self.lobby.tab_obj._edit_profile()

    def _add_friend(self, target):
        from social.friends import FriendError
        try:
            res = self.svc.friends.send_request(self.account.id, target)
        except FriendError as exc:
            self.app.toasts.show(str(exc), "error")
            return
        self.app.toasts.show("Friend request sent" if res else "You're now friends!", "success")
        ProfileTab.viewing = target
        self.rebuild()
