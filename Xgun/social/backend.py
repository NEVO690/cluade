"""Social video network ("TIKTOK" tab) — backend interface + local implementation.

``SocialBackend`` is the contract the UI talks to. ``LocalSocialBackend``
stores everything in the local SQLite database and copies uploaded files
into the user folder: nothing is published to the internet. The online
version (``net.social_client.RemoteSocialBackend``) implements the same
interface against a shared server (``net.social_server``), which itself runs
``LocalSocialBackend`` on its own database.
"""
from __future__ import annotations

import abc
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from config import paths
from save_system.database import Database, now
from social import moderation
from social.errors import SocialError
from video.validation import UploadError, VideoInfo, validate_video_file

VISIBILITIES = ("public", "followers", "private")
VIEW_COOLDOWN = 30.0


@dataclass
class Video:
    id: str
    owner_id: int
    owner_username: str
    owner_display: str
    file_path: str
    title: str
    caption: str
    hashtags: list[str]
    duration: float
    width: int
    height: int
    visibility: str
    allow_comments: bool
    views: int
    likes: int
    comments: int
    saves: int
    status: str
    is_sample: bool
    created_at: float
    liked: bool = False
    saved: bool = False

    @property
    def abs_path(self) -> Path:
        p = Path(self.file_path)
        return p if p.is_absolute() else paths.ROOT / p


@dataclass
class Comment:
    id: int
    video_id: str
    account_id: int
    username: str
    display_name: str
    text: str
    created_at: float


@dataclass
class SocialProfile:
    account_id: int
    username: str
    display_name: str
    bio: str
    avatar_color: str
    is_demo: bool
    private_account: bool
    followers: int
    following: int
    total_likes: int
    video_count: int
    is_following: bool = False
    follows_you: bool = False
    blocked: bool = False


class SocialBackend(abc.ABC):
    """Everything the social UI needs. All methods take the acting account id."""

    @abc.abstractmethod
    def upload(self, actor: int, source: str | Path, title: str, caption: str = "", *,
               visibility: str = "public", allow_comments: bool = True) -> Video: ...
    @abc.abstractmethod
    def delete_video(self, actor: int, video_id: str) -> None: ...
    @abc.abstractmethod
    def update_video(self, actor: int, video_id: str, **changes) -> Video: ...
    @abc.abstractmethod
    def get_video(self, actor: int, video_id: str) -> Video: ...
    @abc.abstractmethod
    def feed(self, actor: int, kind: str = "for_you", limit: int = 30) -> list[Video]: ...
    @abc.abstractmethod
    def profile_videos(self, actor: int, owner_id: int) -> list[Video]: ...
    @abc.abstractmethod
    def saved_videos(self, actor: int) -> list[Video]: ...
    @abc.abstractmethod
    def liked_videos(self, actor: int) -> list[Video]: ...
    @abc.abstractmethod
    def search(self, actor: int, text: str) -> dict: ...
    @abc.abstractmethod
    def trending_hashtags(self, limit: int = 8) -> list[tuple[str, int]]: ...
    @abc.abstractmethod
    def set_like(self, actor: int, video_id: str, liked: bool) -> int: ...
    @abc.abstractmethod
    def set_saved(self, actor: int, video_id: str, saved: bool) -> None: ...
    @abc.abstractmethod
    def record_view(self, actor: int, video_id: str) -> bool: ...
    @abc.abstractmethod
    def add_comment(self, actor: int, video_id: str, text: str) -> Comment: ...
    @abc.abstractmethod
    def delete_comment(self, actor: int, comment_id: int) -> None: ...
    @abc.abstractmethod
    def comments(self, actor: int, video_id: str) -> list[Comment]: ...
    @abc.abstractmethod
    def set_follow(self, actor: int, target: int, follow: bool) -> None: ...
    @abc.abstractmethod
    def followers(self, account_id: int) -> list[int]: ...
    @abc.abstractmethod
    def following(self, account_id: int) -> list[int]: ...
    @abc.abstractmethod
    def follower_count(self, account_id: int) -> int: ...
    @abc.abstractmethod
    def profile(self, actor: int, account_id: int) -> SocialProfile: ...
    @abc.abstractmethod
    def report(self, actor: int, target_type: str, target_id: str, reason: str) -> None: ...
    @abc.abstractmethod
    def set_block(self, actor: int, target: int, blocked: bool) -> None: ...

    is_online = False

    def self_id(self, local_id: int) -> int:
        """The id this network knows the local player by (an online server has its own accounts)."""
        return local_id


class LocalSocialBackend(SocialBackend):
    def __init__(self, db: Database, probe: Callable[[Path], VideoInfo | None] | None = None,
                 storage_dir: Path | None = None):
        self.db = db
        self.probe = probe
        self._storage_dir = storage_dir

    @property
    def storage_dir(self) -> Path:
        path = self._storage_dir or paths.uploads_dir()
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- helpers --------------------------------------------------------
    _VIDEO_SELECT = """
        SELECT v.*, a.username AS owner_username, a.display_name AS owner_display,
               a.private_account AS owner_private,
               (SELECT COUNT(*) FROM video_likes l WHERE l.video_id = v.id) AS likes,
               (SELECT COUNT(*) FROM comments c WHERE c.video_id = v.id AND c.status = 'active') AS n_comments,
               (SELECT COUNT(*) FROM video_saves s WHERE s.video_id = v.id) AS n_saves,
               EXISTS(SELECT 1 FROM video_likes l WHERE l.video_id = v.id AND l.account_id = :actor) AS liked,
               EXISTS(SELECT 1 FROM video_saves s WHERE s.video_id = v.id AND s.account_id = :actor) AS saved
        FROM videos v JOIN accounts a ON a.id = v.owner_id
    """

    def _row_to_video(self, r) -> Video:
        return Video(r["id"], r["owner_id"], r["owner_username"], r["owner_display"], r["file_path"], r["title"],
                     r["caption"], [t for t in r["hashtags"].split(",") if t], r["duration"], r["width"],
                     r["height"], r["visibility"], bool(r["allow_comments"]), r["views"], r["likes"],
                     r["n_comments"], r["n_saves"], r["status"], bool(r["is_sample"]), r["created_at"],
                     bool(r["liked"]), bool(r["saved"]))

    def _query_videos(self, actor: int, where: str = "", params: dict | None = None,
                      order: str = "v.created_at DESC", limit: int = 200) -> list[Video]:
        sql = self._VIDEO_SELECT + (f" WHERE {where}" if where else "") + f" ORDER BY {order} LIMIT {int(limit)}"
        rows = self.db.all(sql, {"actor": actor, **(params or {})})
        return [self._row_to_video(r) for r in rows if self._can_view(actor, r)]

    def _is_blocked(self, a: int, b: int) -> bool:
        return self.db.one("SELECT 1 FROM blocks WHERE (blocker_id = ? AND blocked_id = ?) OR "
                           "(blocker_id = ? AND blocked_id = ?)", (a, b, b, a)) is not None

    def _follows(self, follower: int, followee: int) -> bool:
        return self.db.one("SELECT 1 FROM follows WHERE follower_id = ? AND followee_id = ?",
                           (follower, followee)) is not None

    def _can_view(self, actor: int, row) -> bool:
        owner = row["owner_id"]
        if owner == actor:
            return row["status"] != "removed"
        if row["status"] != "active" or self._is_blocked(actor, owner):
            return False
        if row["visibility"] == "private":
            return False
        if row["visibility"] == "followers" and not self._follows(actor, owner):
            return False
        if row["owner_private"] and not (self._follows(actor, owner) and self._follows(owner, actor)):
            return False
        return True

    def _video_row(self, video_id: str):
        row = self.db.one(self._VIDEO_SELECT + " WHERE v.id = :vid", {"actor": 0, "vid": video_id})
        if row is None:
            raise SocialError("Video not found.")
        return row

    # -- videos ---------------------------------------------------------
    def upload(self, actor, source, title, caption="", *, visibility="public", allow_comments=True,
               is_sample=False, copy_file=True) -> Video:
        title = moderation.clean_text(title, moderation.MAX_TITLE, required=True, field="Title")
        caption = moderation.clean_text(caption, moderation.MAX_CAPTION, field="Caption")
        if moderation.contains_blocked_language(title + " " + caption):
            raise SocialError("Please remove offensive language from the title or caption.")
        if visibility not in VISIBILITIES:
            raise SocialError("Unknown visibility setting.")
        source = Path(source)
        try:
            info = validate_video_file(source, self.probe)
        except UploadError as exc:
            raise SocialError(str(exc)) from exc
        video_id = uuid.uuid4().hex[:16]
        if copy_file:
            dest = self.storage_dir / f"{video_id}{source.suffix.lower()}"
            try:
                shutil.copyfile(source, dest)
            except OSError as exc:
                raise SocialError(f"Couldn't store the video: {exc.strerror or exc}") from exc
            stored = str(dest)
        else:
            try:
                stored = str(source.resolve().relative_to(paths.ROOT)).replace("\\", "/")
            except ValueError:
                stored = str(source.resolve())
        tags = moderation.extract_hashtags(title + " " + caption)
        self.db.execute(
            "INSERT INTO videos(id, owner_id, file_path, title, caption, hashtags, duration, width, height, "
            "size_bytes, visibility, allow_comments, is_sample, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (video_id, actor, stored, title, caption, ",".join(tags), info.duration, info.width, info.height,
             info.size_bytes, visibility, int(allow_comments), int(is_sample), now()))
        return self.get_video(actor, video_id)

    def delete_video(self, actor, video_id):
        row = self._video_row(video_id)
        if row["owner_id"] != actor:
            raise SocialError("You can only delete your own videos.")
        self.db.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        path = Path(row["file_path"])
        if not row["is_sample"] and path.is_absolute() and self.storage_dir in path.parents:
            path.unlink(missing_ok=True)

    def update_video(self, actor, video_id, **changes) -> Video:
        row = self._video_row(video_id)
        if row["owner_id"] != actor:
            raise SocialError("You can only edit your own videos.")
        title = moderation.clean_text(changes.get("title", row["title"]), moderation.MAX_TITLE, required=True,
                                      field="Title")
        caption = moderation.clean_text(changes.get("caption", row["caption"]), moderation.MAX_CAPTION,
                                        field="Caption")
        if moderation.contains_blocked_language(title + " " + caption):
            raise SocialError("Please remove offensive language from the title or caption.")
        visibility = changes.get("visibility", row["visibility"])
        if visibility not in VISIBILITIES:
            raise SocialError("Unknown visibility setting.")
        allow = int(changes.get("allow_comments", bool(row["allow_comments"])))
        self.db.execute("UPDATE videos SET title = ?, caption = ?, hashtags = ?, visibility = ?, allow_comments = ? "
                        "WHERE id = ?", (title, caption, ",".join(moderation.extract_hashtags(title + " " + caption)),
                                         visibility, allow, video_id))
        return self.get_video(actor, video_id)

    def get_video(self, actor, video_id) -> Video:
        videos = self._query_videos(actor, "v.id = :vid", {"vid": video_id}, limit=1)
        if not videos:
            raise SocialError("This video isn't available.")
        return videos[0]

    def feed(self, actor, kind="for_you", limit=30) -> list[Video]:
        if kind == "following":
            return self._query_videos(actor, "v.owner_id IN (SELECT followee_id FROM follows WHERE follower_id = :actor)",
                                      limit=limit)
        if kind == "mine":
            return self.profile_videos(actor, actor)
        videos = self._query_videos(actor, "v.owner_id != :actor OR v.is_sample = 1", limit=500)
        seen = {r["video_id"] for r in self.db.all("SELECT video_id FROM video_views WHERE account_id = ?", (actor,))}
        current = time.time()

        def score(v: Video) -> float:
            age_days = max(0.0, (current - v.created_at) / 86400)
            engagement = v.likes * 3 + v.comments * 4 + v.saves * 5 + v.views * 0.15
            return (engagement + 10) / (1 + age_days * 0.25) * (0.35 if v.id in seen else 1.0)
        videos.sort(key=score, reverse=True)
        return videos[:limit]

    def profile_videos(self, actor, owner_id) -> list[Video]:
        return self._query_videos(actor, "v.owner_id = :owner", {"owner": owner_id})

    def saved_videos(self, actor) -> list[Video]:
        return self._query_videos(actor, "v.id IN (SELECT video_id FROM video_saves WHERE account_id = :actor)")

    def liked_videos(self, actor) -> list[Video]:
        return self._query_videos(actor, "v.id IN (SELECT video_id FROM video_likes WHERE account_id = :actor)")

    def search(self, actor, text) -> dict:
        text = text.strip()
        if not text:
            return {"videos": [], "accounts": [], "hashtags": []}
        tag = text.lstrip("#").lower()
        like = f"%{text.lstrip('#')}%"
        videos = self._query_videos(actor, "v.title LIKE :q OR v.caption LIKE :q OR v.hashtags LIKE :q "
                                    "OR a.username LIKE :q OR a.display_name LIKE :q", {"q": like}, limit=60)
        accounts = [r["id"] for r in self.db.all(
            "SELECT id FROM accounts WHERE (username LIKE ? OR display_name LIKE ?) AND id != ? ORDER BY username "
            "LIMIT 20", (like, like, actor)) if not self._is_blocked(actor, r["id"])]
        hashtags = [h for h, _ in self.trending_hashtags(50) if tag in h]
        return {"videos": videos, "accounts": accounts, "hashtags": hashtags}

    def trending_hashtags(self, limit=8) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for r in self.db.all("SELECT hashtags FROM videos WHERE status = 'active' AND visibility = 'public'"):
            for tag in filter(None, r["hashtags"].split(",")):
                counts[tag] = counts.get(tag, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]

    # -- engagement -----------------------------------------------------
    def _require_visible(self, actor, video_id) -> Video:
        return self.get_video(actor, video_id)

    def set_like(self, actor, video_id, liked) -> int:
        self._require_visible(actor, video_id)
        if liked:
            self.db.execute("INSERT OR IGNORE INTO video_likes(account_id, video_id, created_at) VALUES (?,?,?)",
                            (actor, video_id, now()))
        else:
            self.db.execute("DELETE FROM video_likes WHERE account_id = ? AND video_id = ?", (actor, video_id))
        return int(self.db.scalar("SELECT COUNT(*) FROM video_likes WHERE video_id = ?", (video_id,), 0))

    def set_saved(self, actor, video_id, saved) -> None:
        self._require_visible(actor, video_id)
        if saved:
            self.db.execute("INSERT OR IGNORE INTO video_saves(account_id, video_id, created_at) VALUES (?,?,?)",
                            (actor, video_id, now()))
        else:
            self.db.execute("DELETE FROM video_saves WHERE account_id = ? AND video_id = ?", (actor, video_id))

    def record_view(self, actor, video_id) -> bool:
        """Count a view at most once per account every VIEW_COOLDOWN seconds."""
        self._require_visible(actor, video_id)
        last = self.db.scalar("SELECT last_viewed FROM video_views WHERE account_id = ? AND video_id = ?",
                              (actor, video_id))
        current = now()
        if last is not None and current - last < VIEW_COOLDOWN:
            return False
        with self.db.transaction():
            self.db.execute("INSERT INTO video_views(account_id, video_id, last_viewed) VALUES (?,?,?) "
                            "ON CONFLICT(account_id, video_id) DO UPDATE SET last_viewed = excluded.last_viewed",
                            (actor, video_id, current))
            self.db.execute("UPDATE videos SET views = views + 1 WHERE id = ?", (video_id,))
        return True

    def add_comment(self, actor, video_id, text) -> Comment:
        video = self._require_visible(actor, video_id)
        owner = self.db.one("SELECT allow_comments FROM accounts WHERE id = ?", (video.owner_id,))
        if not video.allow_comments or (owner and not owner["allow_comments"]):
            raise SocialError("Comments are turned off for this video.")
        text = moderation.clean_text(text, moderation.MAX_COMMENT, required=True, field="Comment")
        if moderation.contains_blocked_language(text):
            raise SocialError("Your comment contains language that isn't allowed.")
        cur = self.db.execute("INSERT INTO comments(video_id, account_id, text, created_at) VALUES (?,?,?,?)",
                              (video_id, actor, text, now()))
        return next(c for c in self.comments(actor, video_id) if c.id == cur.lastrowid)

    def delete_comment(self, actor, comment_id) -> None:
        row = self.db.one("SELECT c.account_id, v.owner_id FROM comments c JOIN videos v ON v.id = c.video_id "
                          "WHERE c.id = ?", (comment_id,))
        if row is None:
            raise SocialError("Comment not found.")
        if actor not in (row["account_id"], row["owner_id"]):
            raise SocialError("You can only delete your own comments or comments on your videos.")
        self.db.execute("UPDATE comments SET status = 'removed' WHERE id = ?", (comment_id,))

    def comments(self, actor, video_id) -> list[Comment]:
        self._require_visible(actor, video_id)
        rows = self.db.all("SELECT c.*, a.username, a.display_name FROM comments c JOIN accounts a ON "
                           "a.id = c.account_id WHERE c.video_id = ? AND c.status = 'active' ORDER BY c.id DESC",
                           (video_id,))
        return [Comment(r["id"], r["video_id"], r["account_id"], r["username"], r["display_name"], r["text"],
                        r["created_at"]) for r in rows if not self._is_blocked(actor, r["account_id"])]

    # -- graph ----------------------------------------------------------
    def set_follow(self, actor, target, follow) -> None:
        if actor == target:
            raise SocialError("You can't follow yourself.")
        if follow:
            if self._is_blocked(actor, target):
                raise SocialError("You can't follow this account.")
            self.db.execute("INSERT OR IGNORE INTO follows(follower_id, followee_id, created_at) VALUES (?,?,?)",
                            (actor, target, now()))
        else:
            self.db.execute("DELETE FROM follows WHERE follower_id = ? AND followee_id = ?", (actor, target))

    def followers(self, account_id) -> list[int]:
        return [r[0] for r in self.db.all("SELECT follower_id FROM follows WHERE followee_id = ? "
                                          "ORDER BY created_at DESC", (account_id,))]

    def following(self, account_id) -> list[int]:
        return [r[0] for r in self.db.all("SELECT followee_id FROM follows WHERE follower_id = ? "
                                          "ORDER BY created_at DESC", (account_id,))]

    def follower_count(self, account_id) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM follows WHERE followee_id = ?", (account_id,), 0))

    def profile(self, actor, account_id) -> SocialProfile:
        a = self.db.one("SELECT * FROM accounts WHERE id = ?", (account_id,))
        if a is None:
            raise SocialError("Profile not found.")
        following = int(self.db.scalar("SELECT COUNT(*) FROM follows WHERE follower_id = ?", (account_id,), 0))
        likes = int(self.db.scalar("SELECT COUNT(*) FROM video_likes l JOIN videos v ON v.id = l.video_id "
                                   "WHERE v.owner_id = ?", (account_id,), 0))
        return SocialProfile(a["id"], a["username"], a["display_name"], a["bio"], a["avatar_color"],
                             bool(a["is_demo"]), bool(a["private_account"]), self.follower_count(account_id),
                             following, likes, len(self.profile_videos(actor, account_id)),
                             self._follows(actor, account_id), self._follows(account_id, actor),
                             self.db.one("SELECT 1 FROM blocks WHERE blocker_id = ? AND blocked_id = ?",
                                         (actor, account_id)) is not None)

    # -- safety ---------------------------------------------------------
    def report(self, actor, target_type, target_id, reason) -> None:
        if target_type not in ("video", "comment", "account"):
            raise SocialError("Unknown report target.")
        if reason not in moderation.REPORT_REASONS:
            raise SocialError("Please choose a reason.")
        self.db.execute("INSERT OR IGNORE INTO reports(reporter_id, target_type, target_id, reason, created_at) "
                        "VALUES (?,?,?,?,?)", (actor, target_type, str(target_id), reason, now()))
        count = int(self.db.scalar("SELECT COUNT(DISTINCT reporter_id) FROM reports WHERE target_type = ? AND "
                                   "target_id = ?", (target_type, str(target_id)), 0))
        if count >= moderation.AUTO_HIDE_REPORTS:
            if target_type == "video":
                self.db.execute("UPDATE videos SET status = 'hidden' WHERE id = ? AND status = 'active'", (target_id,))
            elif target_type == "comment":
                self.db.execute("UPDATE comments SET status = 'hidden' WHERE id = ?", (int(target_id),))

    def set_block(self, actor, target, blocked) -> None:
        if actor == target:
            raise SocialError("You can't block yourself.")
        if blocked:
            with self.db.transaction():
                self.db.execute("INSERT OR IGNORE INTO blocks(blocker_id, blocked_id, created_at) VALUES (?,?,?)",
                                (actor, target, now()))
                self.db.execute("DELETE FROM follows WHERE (follower_id = ? AND followee_id = ?) OR "
                                "(follower_id = ? AND followee_id = ?)", (actor, target, target, actor))
                self.db.execute("DELETE FROM friends WHERE (account_id = ? AND friend_id = ?) OR "
                                "(account_id = ? AND friend_id = ?)", (actor, target, target, actor))
        else:
            self.db.execute("DELETE FROM blocks WHERE blocker_id = ? AND blocked_id = ?", (actor, target))

    def blocked_ids(self, actor) -> list[int]:
        return [r[0] for r in self.db.all("SELECT blocked_id FROM blocks WHERE blocker_id = ?", (actor,))]
