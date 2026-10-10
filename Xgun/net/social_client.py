"""``RemoteSocialBackend``: the social tab talking to a shared Xgun social server.

Implements the same ``SocialBackend`` interface as the offline network, so
the UI doesn't change. Videos are downloaded once into a per-server cache in
the user folder so the regular video player and thumbnailer can open them.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

from config import paths
from net.protocol import DEFAULT_SOCIAL_PORT
from social.backend import Comment, SocialBackend, SocialProfile, Video
from social.errors import SocialError

log = logging.getLogger(__name__)
TIMEOUT = 8.0


def normalize_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        raise SocialError("Type the social server's address.")
    if "://" not in value:
        value = "http://" + value
    u = urlparse(value)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise SocialError("That doesn't look like a server address.")
    if u.port is None and u.scheme == "http":
        value = f"{u.scheme}://{u.hostname}:{DEFAULT_SOCIAL_PORT}"
    return value


def _opener(base_url: str):
    host = urlparse(base_url).hostname or ""
    try:
        local = host == "localhost" or ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = False
    # never send LAN / loopback traffic through a system proxy
    return urllib.request.build_opener(urllib.request.ProxyHandler({})) if local else urllib.request.build_opener()


def _request(opener, base, path, *, token=None, payload=None, data: bytes | None = None, raw=False,
             timeout: float | None = None):
    headers = {"User-Agent": "Xgun"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = data
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif data is not None:
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(base + path, data=body, headers=headers, method="POST" if body is not None else "GET")
    try:
        with opener.open(req, timeout=timeout or (TIMEOUT if data is None else 120)) as resp:
            content = resp.read()
            return (content, resp.headers) if raw else json.loads(content)
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read()).get("error")
        except Exception:
            msg = None
        raise SocialError(msg or f"The social server answered with an error ({exc.code}).") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        raise SocialError(f"Couldn't reach the social server ({reason}).") from None


def register(base_url: str, username: str, password: str, display_name: str | None = None) -> "RemoteSocialBackend":
    base = normalize_url(base_url)
    out = _request(_opener(base), base, "/api/register",
                   payload={"username": username, "password": password, "display_name": display_name or username})
    return RemoteSocialBackend(base, out["token"], out["account"])


def login(base_url: str, username: str, password: str) -> "RemoteSocialBackend":
    base = normalize_url(base_url)
    out = _request(_opener(base), base, "/api/login", payload={"username": username, "password": password})
    return RemoteSocialBackend(base, out["token"], out["account"])


def resume(base_url: str, token: str, timeout: float = 3.0) -> "RemoteSocialBackend":
    """Reconnect with a saved session token (raises SocialError if it's no longer valid)."""
    base = normalize_url(base_url)
    account = _request(_opener(base), base, "/api/me", token=token, timeout=timeout)
    return RemoteSocialBackend(base, token, account)


class RemoteSocialBackend(SocialBackend):
    is_online = True

    def __init__(self, base_url: str, token: str, account: dict):
        self.base = normalize_url(base_url)
        self.token = token
        self.account = account
        self.opener = _opener(self.base)
        key = hashlib.sha1(self.base.encode()).hexdigest()[:10]
        self.cache = paths.user_dir() / "online_cache" / key
        self.cache.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ plumbing
    @property
    def server_label(self) -> str:
        return urlparse(self.base).netloc

    def self_id(self, local_id: int) -> int:
        return self.account["id"]

    def _call(self, method: str, **args):
        return _request(self.opener, self.base, "/api/call", token=self.token,
                        payload={"method": method, "args": args})["result"]

    def _video_file(self, video_id: str) -> Path:
        for p in self.cache.glob(f"{video_id}.*"):
            return p
        content, headers = _request(self.opener, self.base, "/api/video/" + quote(video_id), token=self.token, raw=True)
        ext = headers.get("X-Extension", ".mp4")
        if not ext.startswith(".") or not ext[1:].isalnum() or len(ext) > 6:
            ext = ".mp4"
        path = self.cache / f"{video_id}{ext}"
        tmp = path.with_suffix(".part")
        tmp.write_bytes(content)
        tmp.replace(path)
        return path

    def _video(self, d: dict) -> Video:
        vid = str(d["id"])
        if not vid.isalnum():
            raise SocialError("The server sent an invalid video id.")
        d = dict(d)
        try:
            d["file_path"] = str(self._video_file(vid))
        except SocialError as exc:
            log.info("Video %s not downloaded: %s", vid, exc)
            d["file_path"] = str(self.cache / f"{vid}.missing")
        return Video(**{k: d[k] for k in Video.__dataclass_fields__})

    def _videos(self, items) -> list[Video]:
        return [self._video(d) for d in items]

    # ------------------------------------------------------------ SocialBackend
    def upload(self, actor, source, title, caption="", *, visibility="public", allow_comments=True) -> Video:
        source = Path(source)
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise SocialError(f"Couldn't read the file: {exc.strerror or exc}") from exc
        q = urlencode({"title": title, "caption": caption, "visibility": visibility,
                       "allow_comments": "1" if allow_comments else "0", "ext": source.suffix.lower()})
        out = _request(self.opener, self.base, "/api/upload?" + q, token=self.token, data=data)["result"]
        cached = self.cache / f"{out['id']}{source.suffix.lower()}"
        cached.write_bytes(data)                      # no need to download our own upload again
        return self._video(out)

    def delete_video(self, actor, video_id):
        self._call("delete_video", video_id=video_id)

    def update_video(self, actor, video_id, **changes) -> Video:
        return self._video(self._call("update_video", video_id=video_id, **changes))

    def get_video(self, actor, video_id) -> Video:
        return self._video(self._call("get_video", video_id=video_id))

    def feed(self, actor, kind="for_you", limit=30):
        return self._videos(self._call("feed", kind=kind, limit=limit))

    def profile_videos(self, actor, owner_id):
        return self._videos(self._call("profile_videos", owner_id=owner_id))

    def saved_videos(self, actor):
        return self._videos(self._call("saved_videos"))

    def liked_videos(self, actor):
        return self._videos(self._call("liked_videos"))

    def search(self, actor, text) -> dict:
        res = self._call("search", text=text)
        return {**res, "videos": self._videos(res.get("videos", []))}

    def trending_hashtags(self, limit=8):
        return [tuple(t) for t in self._call("trending_hashtags", limit=limit)]

    def set_like(self, actor, video_id, liked) -> int:
        return self._call("set_like", video_id=video_id, liked=liked)

    def set_saved(self, actor, video_id, saved) -> None:
        self._call("set_saved", video_id=video_id, saved=saved)

    def record_view(self, actor, video_id) -> bool:
        return self._call("record_view", video_id=video_id)

    def add_comment(self, actor, video_id, text) -> Comment:
        return Comment(**self._call("add_comment", video_id=video_id, text=text))

    def delete_comment(self, actor, comment_id) -> None:
        self._call("delete_comment", comment_id=comment_id)

    def comments(self, actor, video_id):
        return [Comment(**c) for c in self._call("comments", video_id=video_id)]

    def set_follow(self, actor, target, follow) -> None:
        self._call("set_follow", target=target, follow=follow)

    def followers(self, account_id):
        return self._call("followers", account_id=account_id)

    def following(self, account_id):
        return self._call("following", account_id=account_id)

    def follower_count(self, account_id) -> int:
        return self._call("follower_count", account_id=account_id)

    def profile(self, actor, account_id) -> SocialProfile:
        return SocialProfile(**self._call("profile", account_id=account_id))

    def report(self, actor, target_type, target_id, reason) -> None:
        self._call("report", target_type=target_type, target_id=target_id, reason=reason)

    def set_block(self, actor, target, blocked) -> None:
        self._call("set_block", target=target, blocked=blocked)

    def update_profile(self, actor, **fields) -> dict:
        self.account = self._call("update_profile", **fields)
        return self.account
