"""FRIENDS tab: friend list, requests and finding local players."""
from __future__ import annotations

from social.friends import FriendError
from ui import theme as T
from ui.lobby.common import Tab, header, icon
from ui.widgets import Button, Entry, ScrollArea, frame, text


class FriendsTab(Tab):
    query = ""

    def build(self):
        r = self.root
        me = self.account.id
        f = self.svc.friends
        header(r, "FRIENDS", "Local accounts on this PC. Online friends will arrive with the future online service.")
        friends = [self.svc.accounts.get(i) for i in f.friend_ids(me)]
        incoming = f.incoming(me)
        outgoing = f.outgoing(me)
        # friend list
        text(r, f"FRIENDS  {len(friends)}", (-1.62, 0.52), 0.034, T.TEXT, "black")
        area = ScrollArea(r, -1.65, -0.45, -0.9, 0.47, max(0.1, len(friends) * 0.1 + 0.02))
        for i, acc in enumerate(friends):
            y = -0.05 - i * 0.1
            frame(area.canvas, -1.64, -0.5, y - 0.04, y + 0.04, T.PANEL)
            fol = self.svc.social.follower_count(acc.id)
            text(area.canvas, acc.display_name, (-1.6, y + 0.005), 0.032, T.TEXT, "bold")
            text(area.canvas, f"@{acc.username}  •  {fol} TikTok followers" + ("  •  DEMO" if acc.is_demo else ""),
                 (-1.6, y - 0.03), 0.022, T.TEXT_DIM, "semibold")
            Button(area.canvas, "Profile", self._profile, pos=(-0.82, y), size=(0.17, 0.055), text_scale=0.024,
                   extra_args=(acc.id,))
            Button(area.canvas, "Remove", self._remove, pos=(-0.63, y), size=(0.17, 0.055), text_scale=0.024,
                   extra_args=(acc.id,))
        if not friends:
            text(r, "No friends yet — find players on the right.", (-1.62, 0.4), 0.03, T.TEXT_MUTED, "semibold")
        # requests
        x0 = -0.35
        text(r, f"REQUESTS  {len(incoming)}", (x0, 0.52), 0.034, T.TEXT, "black")
        y = 0.43
        for req in incoming[:5]:
            acc = self.svc.accounts.get(req.from_id)
            frame(r, x0, 0.5, y - 0.04, y + 0.04, T.PANEL)
            text(r, f"{acc.display_name}  @{acc.username}", (x0 + 0.03, y - 0.01), 0.028, T.TEXT, "bold")
            Button(r, "Accept", self._accept, pos=(0.27, y), size=(0.14, 0.055), color=T.GREEN, text_color=(0, 0, 0, 1),
                   text_scale=0.024, extra_args=(req.id,))
            Button(r, "Decline", self._decline, pos=(0.42, y), size=(0.14, 0.055), text_scale=0.024, extra_args=(req.id,))
            y -= 0.1
        if outgoing:
            text(r, "SENT", (x0, y), 0.026, T.TEXT_MUTED, "bold")
            y -= 0.07
            for req in outgoing[:4]:
                acc = self.svc.accounts.get(req.to_id)
                text(r, f"{acc.display_name}  @{acc.username}  •  pending", (x0, y), 0.026, T.TEXT_DIM, "semibold")
                Button(r, "Cancel", self._cancel, pos=(0.42, y + 0.01), size=(0.14, 0.05), text_scale=0.022, extra_args=(req.id,))
                y -= 0.07
        # find players
        text(r, "FIND PLAYERS", (x0, -0.2), 0.034, T.TEXT, "black")
        self.search = Entry(r, pos=(x0, -0.29), width=0.65, initial=FriendsTab.query, placeholder="Search by username",
                            scale=0.03, command=self._search)
        Button(r, "Search", lambda: self._search(self.search.get()), pos=(0.43, -0.275), size=(0.16, 0.065),
               text_scale=0.026)
        results = self.svc.accounts.search(FriendsTab.query) if FriendsTab.query else self.svc.accounts.list()
        y = -0.4
        for acc in [a for a in results if a.id != self.account.id][:5]:
            text(r, f"{acc.display_name}  @{acc.username}" + ("  •  DEMO" if acc.is_demo else ""), (x0, y), 0.027, T.TEXT,
                 "semibold")
            if f.are_friends(self.account.id, acc.id):
                text(r, "Friends", (0.49, y), 0.024, T.GREEN, "bold", "right")
            else:
                Button(r, "Add", self._add, pos=(0.42, y + 0.01), size=(0.14, 0.05), color=T.PRIMARY, text_scale=0.024,
                       extra_args=(acc.id,))
            y -= 0.075
        text(r, "Tip: create a second local account in PROFILE to try friend requests, follows and comments.",
             (x0, -0.86), 0.024, T.TEXT_MUTED, "regular")

    def _guard(self, fn, *args, ok=None):
        try:
            fn(*args)
        except FriendError as exc:
            self.app.toasts.show(str(exc), "error")
            return
        if ok:
            self.app.toasts.show(ok, "success")
        self.rebuild()

    def _add(self, account_id):
        self._guard(self.svc.friends.send_request, self.account.id, account_id, ok="Friend request sent")

    def _accept(self, request_id):
        self._guard(self.svc.friends.accept, request_id, self.account.id, ok="You're now friends!")

    def _decline(self, request_id):
        self._guard(self.svc.friends.decline, request_id, self.account.id)

    def _cancel(self, request_id):
        self._guard(self.svc.friends.cancel, request_id, self.account.id)

    def _remove(self, account_id):
        self._guard(self.svc.friends.remove, self.account.id, account_id, ok="Friend removed")

    def _search(self, query):
        FriendsTab.query = query.strip()
        self.rebuild()

    def _profile(self, account_id):
        from ui.lobby.profile import ProfileTab
        ProfileTab.viewing = account_id
        self.lobby.select("PROFILE")
