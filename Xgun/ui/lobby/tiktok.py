"""TIKTOK tab: local, offline short-video network inside the lobby.

Everything shown here is stored on this PC. Uploads are copied into the
user folder and are visible only to the local accounts on this computer.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

from direct.gui.DirectGui import DirectFrame

from config.branding import SOCIAL_NAME
from social.backend import SocialError, VISIBILITIES
from social.moderation import REPORT_REASONS
from ui import theme as T
from ui.lobby.common import Tab, icon
from ui.widgets import Button, Entry, Modal, ScrollArea, frame, image, text
from video.player import VideoPlayer, pick_video_file

FEEDS = [("for_you", "For You"), ("following", "Following"), ("saved", "Saved"), ("liked", "Liked")]
OFFLINE_NOTE = "Offline network: videos, likes and follows are stored on this PC only and are never published online."


def _count(n: int) -> str:
    return f"{n / 1_000_000:.1f}M" if n >= 1_000_000 else (f"{n / 1000:.1f}K" if n >= 1000 else str(n))


def _ago(ts: float) -> str:
    d = dt.datetime.now() - dt.datetime.fromtimestamp(ts)
    if d.days:
        return f"{d.days}d ago"
    if d.seconds >= 3600:
        return f"{d.seconds // 3600}h ago"
    return f"{max(1, d.seconds // 60)}m ago"


class TikTokTab(Tab):
    view = ("feed", "for_you")

    def build(self):
        r = self.root
        self.social = self.svc.social
        self.me = self.account.id
        self.player = None
        self.videos = []
        self.index = 0
        self.view_counted = False
        self.dynamic = r.attachNewNode("dynamic")
        self._sidebar()
        kind, arg = TikTokTab.view
        if kind == "feed":
            self.show_feed(arg)
        elif kind == "profile":
            self.show_profile(arg)
        elif kind == "upload":
            self.show_upload()
        elif kind == "search":
            self.show_search(arg)
        for key, fn_ in (("arrow_down", self.next), ("arrow_up", self.prev), ("space", self.toggle)):
            self.app.accept(key, fn_)

    # ------------------------------------------------------------ chrome
    def _sidebar(self):
        r = self.root
        text(r, SOCIAL_NAME, (-1.62, 0.68), 0.075, T.TEXT, "black")
        DirectFrame(parent=r, frameSize=(-1.62, -1.3, 0.645, 0.652), frameColor=T.PINK)
        self.side_buttons = {}
        y = 0.55
        for key, label in FEEDS:
            b = Button(r, label, self._goto_feed, pos=(-1.42, y), size=(0.44, 0.075), text_scale=0.03, align="left",
                       extra_args=(key,))
            self.side_buttons[key] = b
            y -= 0.085
        Button(r, "My Profile", self.show_profile, pos=(-1.42, y), size=(0.44, 0.075), text_scale=0.03, align="left",
               extra_args=(self.me,), icon=icon("user"))
        y -= 0.085
        Button(r, "Upload", self.show_upload, pos=(-1.42, y), size=(0.44, 0.075), text_scale=0.03, align="left",
               color=T.PINK, hover=(1, 0.45, 0.6, 1), icon=icon("upload"))
        y -= 0.13
        self.search = Entry(r, pos=(-1.62, y), width=0.38, placeholder="Search", scale=0.03, command=self.show_search)
        Button(r, "", lambda: self.show_search(self.search.get()), pos=(-1.17, y + 0.012), size=(0.06, 0.06),
               icon=icon("search"))
        y -= 0.1
        text(r, "TRENDING", (-1.62, y), 0.026, T.TEXT_MUTED, "bold")
        for tag, n in self.social.trending_hashtags(6):
            y -= 0.055
            Button(r, f"#{tag}", self.show_search, pos=(-1.42, y), size=(0.44, 0.05), text_scale=0.026, align="left",
                   color=(0, 0, 0, 0), hover=(1, 1, 1, 0.08), text_color=T.ACCENT, extra_args=("#" + tag,))
        text(r, OFFLINE_NOTE, (-1.62, -0.84), 0.022, T.TEXT_MUTED, "regular", wrap=19)

    def _clear(self):
        if self.player is not None:
            self.player.destroy()
            self.player = None
        self.dynamic.removeNode()
        self.dynamic = self.root.attachNewNode("dynamic")
        for b in self.side_buttons.values():
            b.set_selected(False, T.PINK)

    # ------------------------------------------------------------ feed
    def _goto_feed(self, key):
        self.show_feed(key)

    def show_feed(self, kind: str, start_id: str | None = None, videos=None):
        self._clear()
        TikTokTab.view = ("feed", kind)
        if kind in self.side_buttons:
            self.side_buttons[kind].set_selected(True, T.PINK)
        if videos is not None:
            self.videos = videos
        elif kind == "saved":
            self.videos = self.social.saved_videos(self.me)
        elif kind == "liked":
            self.videos = self.social.liked_videos(self.me)
        else:
            self.videos = self.social.feed(self.me, kind)
        self.index = 0
        if start_id:
            self.index = next((i for i, v in enumerate(self.videos) if v.id == start_id), 0)
        self.player = VideoPlayer(self.app, self.dynamic, center=(-0.35, -0.08), height=1.48)
        self.overlay = self.dynamic.attachNewNode("overlay")
        if not self.videos:
            msg = {"following": "Follow creators to fill this feed.", "saved": "Videos you save appear here.",
                   "liked": "Videos you like appear here."}.get(kind, "No videos yet. Be the first to upload!")
            text(self.dynamic, msg, (-0.35, 0.0), 0.04, T.TEXT_DIM, "semibold", "center", wrap=14)
            return
        self._load_current()

    def _load_current(self):
        v = self.videos[self.index]
        try:
            v = self.social.get_video(self.me, v.id)
            self.videos[self.index] = v
        except SocialError:
            pass
        self.current = v
        self.view_counted = False
        self.watch_time = 0.0
        if not self.player.load(v.abs_path):
            err = self.player.error
        else:
            err = None
        self._draw_overlay(v, err)

    def _draw_overlay(self, v, err=None):
        self.overlay.removeNode()
        self.overlay = self.dynamic.attachNewNode("overlay")
        o = self.overlay
        px, w = -0.35, self.player.width
        if err:
            text(o, err, (px, 0.0), 0.034, T.RED, "semibold", "center", wrap=12)
        # caption block over the bottom of the video
        frame(o, px - w / 2, px + w / 2, -0.82, -0.5, (0, 0, 0, 0.45))
        handle = Button(o, f"@{v.owner_username}", self.show_profile, pos=(px - w / 2 + 0.17, -0.55), size=(0.32, 0.05),
                        color=(0, 0, 0, 0), hover=(1, 1, 1, 0.1), text_scale=0.03, align="left", extra_args=(v.owner_id,))
        badge = []
        if self.svc.accounts.get(v.owner_id).is_demo:
            badge.append("DEMO")
        if v.is_sample:
            badge.append("SAMPLE CLIP")
        if badge:
            text(o, " • ".join(badge), (px + w / 2 - 0.02, -0.56), 0.02, T.GOLD, "bold", "right")
        text(o, v.title, (px - w / 2 + 0.02, -0.61), 0.028, T.TEXT, "bold", wrap=26)
        if v.caption:
            text(o, v.caption, (px - w / 2 + 0.02, -0.67), 0.024, T.TEXT_DIM, "regular", wrap=33)
        vis = {"public": "Public", "followers": "Followers only", "private": "Only me"}[v.visibility]
        text(o, f"{_count(v.views)} views • {_ago(v.created_at)} • {vis}", (px - w / 2 + 0.02, -0.79), 0.021, T.TEXT_MUTED, "semibold")
        text(o, f"{self.index + 1}/{len(self.videos)}   ↑/↓ or wheel to scroll  •  SPACE pause", (px, 0.71), 0.022, T.TEXT_MUTED,
             "semibold", "center")
        # action rail
        ax = px + w / 2 + 0.11
        prof = self.social.profile(self.me, v.owner_id)
        DirectFrame(parent=o, frameSize=(-0.05, 0.05, -0.05, 0.05), frameColor=T.rgba(prof.avatar_color), pos=(ax, 0, 0.42))
        text(o, prof.display_name[:1].upper(), (ax, 0.405), 0.045, T.TEXT, "black", "center")
        if v.owner_id != self.me:
            Button(o, "Following" if prof.is_following else "+ Follow", self._toggle_follow, pos=(ax, 0.32), size=(0.18, 0.05),
                   text_scale=0.022, color=T.PANEL_LIGHT if prof.is_following else T.PINK, extra_args=(v.owner_id,))
        self._action(o, ax, 0.18, "heart" if v.liked else "heart_outline", _count(v.likes), self._toggle_like,
                     T.PINK if v.liked else T.TEXT)
        self._action(o, ax, 0.04, "comment", _count(v.comments), lambda: None, T.TEXT)
        self._action(o, ax, -0.1, "bookmark" if v.saved else "bookmark_outline", _count(v.saves), self._toggle_save,
                     T.GOLD if v.saved else T.TEXT)
        self._action(o, ax, -0.24, "share", "Share", self._share, T.TEXT)
        if v.owner_id == self.me:
            self._action(o, ax, -0.38, "gear", "Edit", self._edit_video, T.TEXT)
        else:
            self._action(o, ax, -0.38, "flag", "Report", self._report_video, T.TEXT)
        self._comments(v)

    def _action(self, parent, x, y, icon_name, label, cmd, color):
        b = Button(parent, "", cmd, pos=(x, y), size=(0.1, 0.09), color=(1, 1, 1, 0.06), hover=(1, 1, 1, 0.16))
        img = image(b.node, icon(icon_name), (0, 0), (0.06, 0.06))
        if img is not None:
            img.setColorScale(*color)
        text(parent, label, (x, y - 0.075), 0.022, T.TEXT_DIM, "bold", "center")

    def _comments(self, v):
        o = self.overlay
        frame(o, 0.38, 1.65, -0.86, 0.66, T.PANEL)
        comments = self.social.comments(self.me, v.id)
        text(o, f"COMMENTS  {len(comments)}", (0.42, 0.6), 0.032, T.TEXT, "black")
        area = ScrollArea(o, 0.38, 1.65, -0.66, 0.56, max(0.1, len(comments) * 0.12 + 0.02))
        for i, c in enumerate(comments):
            y = -0.05 - i * 0.12
            Button(area.canvas, f"@{c.username}", self.show_profile, pos=(0.56, y + 0.02), size=(0.32, 0.04), color=(0, 0, 0, 0),
                   hover=(1, 1, 1, 0.08), text_scale=0.022, text_color=T.ACCENT, align="left", extra_args=(c.account_id,))
            text(area.canvas, c.text, (0.42, y - 0.025), 0.026, T.TEXT, "regular", wrap=40)
            text(area.canvas, _ago(c.created_at), (1.58, y + 0.012), 0.018, T.TEXT_MUTED, "semibold", "right")
            if self.me in (c.account_id, v.owner_id):
                Button(area.canvas, "", self._delete_comment, pos=(1.55, y - 0.03), size=(0.045, 0.04), color=(0, 0, 0, 0),
                       hover=(1, 0.3, 0.3, 0.3), icon=icon("trash"), extra_args=(c.id,))
            else:
                Button(area.canvas, "", self._report_comment, pos=(1.55, y - 0.03), size=(0.045, 0.04), color=(0, 0, 0, 0),
                       hover=(1, 1, 1, 0.15), icon=icon("flag"), extra_args=(c.id,))
        if not comments:
            text(o, "No comments yet." if v.allow_comments else "Comments are turned off.", (1.0, 0.3), 0.028, T.TEXT_MUTED,
                 "semibold", "center")
        if v.allow_comments:
            self.comment_entry = Entry(o, pos=(0.42, -0.79), width=0.95, placeholder="Add a comment...", scale=0.028,
                                       command=lambda t: self._post_comment(), max_chars=200)
            Button(o, "Post", self._post_comment, pos=(1.55, -0.775), size=(0.15, 0.06), color=T.PINK, text_scale=0.026)

    # -- actions -------------------------------------------------------------
    def _refresh_current(self):
        try:
            self.current = self.social.get_video(self.me, self.current.id)
            self.videos[self.index] = self.current
        except SocialError:
            pass
        self._draw_overlay(self.current, self.player.error)

    def _guard(self, fn_, *args):
        try:
            fn_(*args)
        except SocialError as exc:
            self.app.toasts.show(str(exc), "error")
            return False
        return True

    def _toggle_like(self):
        v = self.current
        if self._guard(self.social.set_like, self.me, v.id, not v.liked):
            self.app.audio.play("pickup" if not v.liked else "ui_click")
            self._refresh_current()

    def _toggle_save(self):
        v = self.current
        if self._guard(self.social.set_saved, self.me, v.id, not v.saved):
            self.app.toasts.show("Saved to your collection" if not v.saved else "Removed from saved", "success")
            self._refresh_current()

    def _toggle_follow(self, account_id):
        prof = self.social.profile(self.me, account_id)
        if self._guard(self.social.set_follow, self.me, account_id, not prof.is_following):
            self._refresh_current() if TikTokTab.view[0] == "feed" else self.show_profile(account_id)

    def _share(self):
        Modal(self.app, "SHARE", "Sharing to the internet isn't available in the offline build. Other local accounts on this "
              "PC can already see your public videos in their feed.", [("OK", None, ())])

    def _post_comment(self):
        txt = self.comment_entry.get()
        if not txt.strip():
            return
        if self._guard(self.social.add_comment, self.me, self.current.id, txt):
            self.app.audio.play("notify")
            self._refresh_current()

    def _delete_comment(self, comment_id):
        if self._guard(self.social.delete_comment, self.me, comment_id):
            self._refresh_current()

    def _report(self, target_type, target_id):
        buttons = [(reason, self._do_report, (target_type, target_id, reason)) for reason in REPORT_REASONS[:3]]
        buttons.append(("Other", self._do_report, (target_type, target_id, "Other")))
        Modal(self.app, "REPORT", "Why are you reporting this? Content reported by 3 local accounts is hidden automatically.",
              buttons, width=1.6, height=0.55)

    def _do_report(self, target_type, target_id, reason):
        if self._guard(self.social.report, self.me, target_type, target_id, reason):
            self.app.toasts.show("Thanks — your report was recorded.", "success")

    def _report_video(self):
        self._report("video", self.current.id)

    def _report_comment(self, comment_id):
        self._report("comment", comment_id)

    def _edit_video(self):
        v = self.current
        m = Modal(self.app, "EDIT VIDEO", "", [("Delete video", self._confirm_delete, (v.id,)), ("Cancel", None, ()),
                                               ("Save", lambda: self._save_edit(v.id), ())], width=1.4, height=0.95)
        text(m.box, "Title", (-0.62, 0.3), 0.028, T.TEXT_DIM, "bold")
        self.edit_title = Entry(m.box, pos=(-0.62, 0.22), width=1.24, initial=v.title, scale=0.03, max_chars=60)
        text(m.box, "Caption", (-0.62, 0.12), 0.028, T.TEXT_DIM, "bold")
        self.edit_caption = Entry(m.box, pos=(-0.62, 0.04), width=1.24, initial=v.caption, scale=0.03, max_chars=300)
        self.edit_vis = v.visibility
        self.edit_allow = v.allow_comments
        self.vis_buttons = []
        for i, vis in enumerate(VISIBILITIES):
            b = Button(m.box, {"public": "Public", "followers": "Followers", "private": "Only me"}[vis], self._set_vis,
                       pos=(-0.45 + i * 0.3, -0.07), size=(0.27, 0.065), text_scale=0.026, extra_args=(vis,))
            b.set_selected(vis == v.visibility, T.PINK)
            self.vis_buttons.append((vis, b))
        self.allow_btn = Button(m.box, "", self._toggle_allow, pos=(0, -0.17), size=(0.6, 0.065), text_scale=0.026)
        self._toggle_allow(refresh_only=True)

    def _set_vis(self, vis):
        self.edit_vis = vis
        for v, b in self.vis_buttons:
            b.set_selected(v == vis, T.PINK)

    def _toggle_allow(self, refresh_only=False):
        if not refresh_only:
            self.edit_allow = not self.edit_allow
        self.allow_btn.set_text("Comments: ON" if self.edit_allow else "Comments: OFF")

    def _save_edit(self, video_id):
        if self._guard(self.social.update_video, self.me, video_id, title=self.edit_title.get(),
                       caption=self.edit_caption.get(), visibility=self.edit_vis, allow_comments=self.edit_allow):
            self.app.toasts.show("Video updated", "success")
            self._refresh_current()

    def _confirm_delete(self, video_id):
        Modal(self.app, "DELETE VIDEO?", "This removes the video and its likes and comments from this PC.",
              [("Cancel", None, ()), ("Delete", self._delete_video, (video_id,))])

    def _delete_video(self, video_id):
        if self._guard(self.social.delete_video, self.me, video_id):
            self.app.toasts.show("Video deleted", "success")
            self.show_profile(self.me)

    # -- navigation ------------------------------------------------------------
    def next(self):
        if TikTokTab.view[0] == "feed" and self.videos and self.index < len(self.videos) - 1:
            self.index += 1
            self.app.audio.play("ui_swoosh", 0.5)
            self._load_current()

    def prev(self):
        if TikTokTab.view[0] == "feed" and self.videos and self.index > 0:
            self.index -= 1
            self.app.audio.play("ui_swoosh", 0.5)
            self._load_current()

    def toggle(self):
        if self.player is not None:
            self.player.toggle_pause()

    def wheel(self, direction):
        if direction < 0:
            self.next()
        else:
            self.prev()

    def update(self, dt_):
        if self.player is not None and self.player.tex is not None:
            self.player.update()
            if not self.player.paused:
                self.watch_time += dt_
            if not self.view_counted and self.watch_time > 1.0:
                self.view_counted = True
                try:
                    self.social.record_view(self.me, self.current.id)
                except SocialError:
                    pass
        mw = self.app.mouseWatcherNode
        # mouse wheel over the player scrolls the feed (handled via the global wheel hook)
        return None

    # ------------------------------------------------------------ profile
    def show_profile(self, account_id: int):
        self._clear()
        TikTokTab.view = ("profile", account_id)
        d = self.dynamic
        try:
            prof = self.social.profile(self.me, account_id)
        except SocialError as exc:
            text(d, str(exc), (0, 0), 0.04, T.RED, "bold", "center")
            return
        DirectFrame(parent=d, frameSize=(-0.09, 0.09, -0.09, 0.09), frameColor=T.rgba(prof.avatar_color), pos=(-0.92, 0, 0.55))
        text(d, prof.display_name[:1].upper(), (-0.92, 0.52), 0.09, T.TEXT, "black", "center")
        text(d, prof.display_name, (-0.78, 0.58), 0.055, T.TEXT, "black")
        tags = ["@" + prof.username]
        if prof.is_demo:
            tags.append("DEMO ACCOUNT (offline)")
        if prof.private_account:
            tags.append("PRIVATE")
        text(d, "   ".join(tags), (-0.78, 0.52), 0.03, T.TEXT_DIM, "bold")
        for i, (n, label) in enumerate(((prof.following, "Following"), (prof.followers, "Followers"), (prof.total_likes, "Likes"))):
            x = -0.78 + i * 0.3
            text(d, _count(n), (x, 0.43), 0.045, T.TEXT, "black")
            text(d, label, (x, 0.39), 0.025, T.TEXT_DIM, "semibold")
        if prof.bio:
            text(d, prof.bio, (-0.78, 0.33), 0.028, T.TEXT_DIM, "regular", wrap=40)
        bx = 0.35
        if account_id != self.me:
            Button(d, "Following" if prof.is_following else "Follow", self._toggle_follow, pos=(bx, 0.55), size=(0.28, 0.07),
                   color=T.PANEL_LIGHT if prof.is_following else T.PINK, text_scale=0.03, extra_args=(account_id,))
            Button(d, "Unblock" if prof.blocked else "Block", self._toggle_block, pos=(bx + 0.31, 0.55), size=(0.28, 0.07),
                   text_scale=0.03, extra_args=(account_id, prof.blocked))
            Button(d, "Report", self._report, pos=(bx + 0.62, 0.55), size=(0.28, 0.07), text_scale=0.03,
                   extra_args=("account", str(account_id)))
            if prof.follows_you:
                text(d, "Follows you", (bx, 0.47), 0.026, T.TEXT_DIM, "bold", "center")
        else:
            Button(d, "Edit profile", self._edit_profile, pos=(bx, 0.55), size=(0.28, 0.07), text_scale=0.03)
            Button(d, "Upload", self.show_upload, pos=(bx + 0.31, 0.55), size=(0.28, 0.07), color=T.PINK, text_scale=0.03)
        videos = self.social.profile_videos(self.me, account_id)
        text(d, f"VIDEOS  {len(videos)}", (-0.98, 0.22), 0.032, T.TEXT, "black")
        if not videos:
            msg = "No videos yet." if not prof.private_account or account_id == self.me else \
                "This account is private. Follow each other to see their videos."
            text(d, msg, (0.2, -0.1), 0.034, T.TEXT_MUTED, "semibold", "center")
        cols, w, h = 6, 0.4, 0.52
        area = ScrollArea(d, -1.0, 1.65, -0.9, 0.17, ((len(videos) + cols - 1) // cols) * (h + 0.03) + 0.02)
        for i, v in enumerate(videos):
            col, row = i % cols, i // cols
            x = -1.0 + 0.02 + w / 2 + col * (w + 0.03)
            y = -0.02 - h / 2 - row * (h + 0.03)
            self._tile(area.canvas, v, (x, y), (w, h), videos)

    def _tile(self, parent, v, pos, size, videos):
        x, y = pos
        w, h = size
        hue = int(hashlib.md5(v.id.encode()).hexdigest()[:6], 16)
        c = ((hue >> 16 & 255) / 255 * 0.5 + 0.15, (hue >> 8 & 255) / 255 * 0.4 + 0.1, (hue & 255) / 255 * 0.6 + 0.25, 1)
        b = Button(parent, "", self.show_feed, pos=(x, y), size=(w, h), color=c, hover=(c[0] * 1.3, c[1] * 1.3, c[2] * 1.3, 1),
                   extra_args=("profile", v.id, videos))
        image(b.node, icon("play"), (0, 0.04), (0.1, 0.1))
        text(b.node, v.title, (-w / 2 + 0.02, -h / 2 + 0.09), 0.024, T.TEXT, "bold", wrap=14)
        text(b.node, f"{_count(v.views)} views  •  {_count(v.likes)} likes", (-w / 2 + 0.02, -h / 2 + 0.025), 0.02, T.TEXT_DIM, "bold")
        if v.status != "active":
            text(b.node, "UNDER REVIEW", (0, h / 2 - 0.05), 0.022, T.RED, "black", "center")
        elif v.visibility != "public":
            text(b.node, v.visibility.upper(), (0, h / 2 - 0.05), 0.02, T.GOLD, "black", "center")

    def _toggle_block(self, account_id, blocked):
        if self._guard(self.social.set_block, self.me, account_id, not blocked):
            self.app.toasts.show("Account unblocked" if blocked else "Account blocked. You won't see each other's content.",
                                 "success")
            self.show_profile(account_id)

    def _edit_profile(self):
        acc = self.svc.accounts.get(self.me)
        m = Modal(self.app, "EDIT PROFILE", "", [("Cancel", None, ()), ("Save", self._save_profile, ())], width=1.4, height=1.0)
        text(m.box, "Display name", (-0.62, 0.3), 0.028, T.TEXT_DIM, "bold")
        self.e_name = Entry(m.box, pos=(-0.62, 0.22), width=1.24, initial=acc.display_name, scale=0.03, max_chars=24)
        text(m.box, "Bio", (-0.62, 0.12), 0.028, T.TEXT_DIM, "bold")
        self.e_bio = Entry(m.box, pos=(-0.62, 0.04), width=1.24, initial=acc.bio, scale=0.03, max_chars=150)
        self.e_private = acc.private_account
        self.e_comments = acc.allow_comments
        self.priv_btn = Button(m.box, "", self._flip_private, pos=(-0.3, -0.1), size=(0.56, 0.07), text_scale=0.026)
        self.com_btn = Button(m.box, "", self._flip_comments, pos=(0.3, -0.1), size=(0.56, 0.07), text_scale=0.026)
        self._flip_private(True)
        self._flip_comments(True)
        text(m.box, "Private accounts only show videos to people you follow back.", (0, -0.2), 0.024, T.TEXT_MUTED, "regular",
             "center")

    def _flip_private(self, refresh=False):
        if not refresh:
            self.e_private = not self.e_private
        self.priv_btn.set_text("Private account: " + ("ON" if self.e_private else "OFF"))

    def _flip_comments(self, refresh=False):
        if not refresh:
            self.e_comments = not self.e_comments
        self.com_btn.set_text("Allow comments: " + ("ON" if self.e_comments else "OFF"))

    def _save_profile(self):
        from social.moderation import contains_blocked_language
        name, bio = self.e_name.get(), self.e_bio.get()
        if contains_blocked_language(name + " " + bio):
            self.app.toasts.show("Please remove offensive language.", "error")
            return
        acc = self.svc.accounts.update_profile(self.me, display_name=name, bio=bio, private_account=self.e_private,
                                               allow_comments=self.e_comments)
        self.lobby.account = self.app.account = acc
        self.lobby.refresh_wallet()
        self.show_profile(self.me)

    # ------------------------------------------------------------ upload
    def show_upload(self):
        self._clear()
        TikTokTab.view = ("upload", None)
        d = self.dynamic
        text(d, "UPLOAD A VIDEO", (-0.98, 0.6), 0.06, T.TEXT, "black")
        text(d, "MP4, MOV, WEBM, MKV, AVI or OGV  •  up to 200 MB  •  up to 3 minutes  •  vertical looks best",
             (-0.98, 0.53), 0.028, T.TEXT_DIM, "semibold")
        text(d, "The file is copied into your Xgun user folder. It is not uploaded to the internet.", (-0.98, 0.48), 0.026,
             T.GOLD, "semibold")
        text(d, "Video file", (-0.98, 0.38), 0.028, T.TEXT_DIM, "bold")
        self.u_path = Entry(d, pos=(-0.98, 0.3), width=1.6, placeholder="Paste a file path or click Browse", scale=0.03,
                            max_chars=1000)
        Button(d, "Browse...", self._browse, pos=(0.85, 0.315), size=(0.28, 0.075), text_scale=0.03)
        text(d, "Title", (-0.98, 0.2), 0.028, T.TEXT_DIM, "bold")
        self.u_title = Entry(d, pos=(-0.98, 0.12), width=1.6, placeholder="Give it a title (#hashtags work)", scale=0.03,
                             max_chars=60)
        text(d, "Caption", (-0.98, 0.02), 0.028, T.TEXT_DIM, "bold")
        self.u_caption = Entry(d, pos=(-0.98, -0.06), width=1.6, placeholder="Say something about it", scale=0.03, max_chars=300)
        text(d, "Who can watch", (-0.98, -0.16), 0.028, T.TEXT_DIM, "bold")
        self.edit_vis = "public"
        self.vis_buttons = []
        for i, vis in enumerate(VISIBILITIES):
            b = Button(d, {"public": "Everyone", "followers": "Followers", "private": "Only me"}[vis], self._set_vis,
                       pos=(-0.83 + i * 0.32, -0.23), size=(0.3, 0.07), text_scale=0.028, extra_args=(vis,))
            b.set_selected(vis == "public", T.PINK)
            self.vis_buttons.append((vis, b))
        self.edit_allow = True
        self.allow_btn = Button(d, "", self._toggle_allow, pos=(0.35, -0.23), size=(0.4, 0.07), text_scale=0.028)
        self._toggle_allow(refresh_only=True)
        self.u_status = text(d, "", (-0.98, -0.36), 0.03, T.RED, "semibold", wrap=50)
        Button(d, "POST VIDEO", self._do_upload, pos=(-0.68, -0.5), size=(0.6, 0.1), color=T.PINK, hover=(1, 0.45, 0.6, 1),
               text_scale=0.04, font="black")

    def _browse(self):
        self.u_status.setText("Opening file browser...")
        self.app.graphicsEngine.renderFrame()
        path = pick_video_file()
        if path:
            self.u_path.set(path)
            self.u_status.setText("")
            if not self.u_title.get():
                self.u_title.set(Path(path).stem[:60])
        else:
            self.u_status.setText("No file chosen. You can also paste the full path above.")

    def _do_upload(self):
        path = self.u_path.get().strip().strip('"')
        if not path:
            self.u_status.setText("Choose a video file first.")
            return
        try:
            v = self.social.upload(self.me, path, self.u_title.get(), self.u_caption.get(), visibility=self.edit_vis,
                                   allow_comments=self.edit_allow)
        except SocialError as exc:
            self.u_status.setText(str(exc))
            self.app.audio.play("ui_error")
            return
        self.app.toasts.show("Video posted to your local profile!", "success")
        self.app.audio.play("ui_purchase")
        self.show_feed("mine", v.id, self.social.profile_videos(self.me, self.me))

    # ------------------------------------------------------------ search
    def show_search(self, query: str):
        query = (query or "").strip()
        if not query:
            return
        self._clear()
        TikTokTab.view = ("search", query)
        d = self.dynamic
        res = self.social.search(self.me, query)
        text(d, f'RESULTS FOR "{query}"', (-0.98, 0.6), 0.05, T.TEXT, "black")
        text(d, "ACCOUNTS", (-0.98, 0.5), 0.03, T.TEXT_MUTED, "bold")
        for i, acc_id in enumerate(res["accounts"][:6]):
            p = self.social.profile(self.me, acc_id)
            Button(d, f"{p.display_name}  @{p.username}  •  {_count(p.followers)} followers" + ("  •  DEMO" if p.is_demo else ""),
                   self.show_profile, pos=(-0.55, 0.43 - i * 0.075), size=(0.9, 0.065), text_scale=0.026, align="left",
                   extra_args=(acc_id,))
        if not res["accounts"]:
            text(d, "No accounts found.", (-0.98, 0.43), 0.028, T.TEXT_DIM)
        text(d, f"VIDEOS  {len(res['videos'])}", (0.05, 0.5), 0.03, T.TEXT_MUTED, "bold")
        for i, v in enumerate(res["videos"][:8]):
            Button(d, f"{v.title}  •  @{v.owner_username}", self.show_feed, pos=(0.85, 0.43 - i * 0.075), size=(1.55, 0.065),
                   text_scale=0.026, align="left", extra_args=("search", v.id, res["videos"]))
        if not res["videos"]:
            text(d, "No videos found.", (0.05, 0.43), 0.028, T.TEXT_DIM)

    def destroy(self):
        for key in ("arrow_down", "arrow_up", "space"):
            self.app.ignore(key)
        if self.player is not None:
            self.player.destroy()
        super().destroy()
