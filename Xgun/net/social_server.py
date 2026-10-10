"""Shared online social server (the tab's videos, likes, comments, follows).

A small HTTP/JSON service. It keeps its own SQLite database and video store
and runs the same rules as the offline network (``LocalSocialBackend``):
visibility, privacy, blocks, moderation and upload validation all happen on
the server. Accounts sign in with a username + password (PBKDF2-hashed) and
then use a bearer token; the acting account always comes from the token.

    python -m net.social_server --port 47801 --data server_data

Endpoints:  POST /api/register, POST /api/login, GET /api/me,
            POST /api/call {"method", "args"}, POST /api/upload?title=...  (raw video bytes),
            GET  /api/video/<id>
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from config import paths
from net.protocol import DEFAULT_SOCIAL_PORT
from social import moderation
from social.accounts import AccountError
from social.errors import SocialError
from video.validation import MAX_BYTES, SUPPORTED_EXTENSIONS

log = logging.getLogger("xgun.social")
PBKDF2_ROUNDS = 200_000
MAX_JSON = 64 * 1024

# method -> (needs actor, allowed argument names)
METHODS = {
    "delete_video": (True, ("video_id",)),
    "update_video": (True, ("video_id", "title", "caption", "visibility", "allow_comments")),
    "get_video": (True, ("video_id",)),
    "feed": (True, ("kind", "limit")),
    "profile_videos": (True, ("owner_id",)),
    "saved_videos": (True, ()),
    "liked_videos": (True, ()),
    "search": (True, ("text",)),
    "trending_hashtags": (False, ("limit",)),
    "set_like": (True, ("video_id", "liked")),
    "set_saved": (True, ("video_id", "saved")),
    "record_view": (True, ("video_id",)),
    "add_comment": (True, ("video_id", "text")),
    "delete_comment": (True, ("comment_id",)),
    "comments": (True, ("video_id",)),
    "set_follow": (True, ("target", "follow")),
    "followers": (False, ("account_id",)),
    "following": (False, ("account_id",)),
    "follower_count": (False, ("account_id",)),
    "profile": (True, ("account_id",)),
    "report": (True, ("target_type", "target_id", "reason")),
    "set_block": (True, ("target", "blocked")),
}


def _jsonable(value):
    if dataclasses.is_dataclass(value):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS).hex()


class SocialService:
    """Server-side state: accounts + auth on top of the regular services."""

    def __init__(self, data_dir: Path, *, seed_demo: bool = True, probe=None):
        from game.services import Services
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if probe is None:
            from video.probe import panda_probe
            probe = panda_probe
        self.svc = Services(self.data_dir / "social.db", probe=probe, seed_demo=seed_demo)
        self.social = self.svc.social
        self.social._storage_dir = self.data_dir / "videos"
        self.db = self.svc.db
        self.lock = threading.RLock()       # SQLite connection is shared by the handler threads
        self.db.execute("CREATE TABLE IF NOT EXISTS server_auth (account_id INTEGER PRIMARY KEY, salt TEXT NOT NULL, "
                        "hash TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS server_tokens (token TEXT PRIMARY KEY, account_id INTEGER NOT NULL)")

    # -------------------------------------------------------------- auth
    def register(self, username: str, password: str, display_name: str | None = None) -> tuple[str, dict]:
        if len(password or "") < 6:
            raise SocialError("Passwords need at least 6 characters.")
        if moderation.contains_blocked_language(f"{username} {display_name or ''}"):
            raise SocialError("Please choose a different name.")
        with self.lock:
            try:
                acc = self.svc.accounts.create(username, display_name)
            except AccountError as exc:
                raise SocialError(str(exc).replace(" on this PC", " on this server")) from exc
            salt = secrets.token_bytes(16)
            self.db.execute("INSERT INTO server_auth(account_id, salt, hash) VALUES (?,?,?)",
                            (acc.id, salt.hex(), hash_password(password, salt)))
            return self._new_token(acc.id), self.account_info(acc.id)

    def login(self, username: str, password: str) -> tuple[str, dict]:
        with self.lock:
            acc = self.svc.accounts.find_by_username(username or "")
            row = self.db.one("SELECT salt, hash FROM server_auth WHERE account_id = ?", (acc.id,)) if acc else None
            # same work and same message whether or not the user exists
            salt = bytes.fromhex(row["salt"]) if row else b"\0" * 16
            ok = hmac.compare_digest(hash_password(password or "", salt), row["hash"] if row else "x")
            if not (row and ok):
                raise SocialError("Wrong username or password.")
            return self._new_token(acc.id), self.account_info(acc.id)

    def _new_token(self, account_id: int) -> str:
        token = secrets.token_urlsafe(32)
        self.db.execute("INSERT INTO server_tokens(token, account_id) VALUES (?,?)", (token, account_id))
        return token

    def account_for(self, token: str | None) -> int | None:
        if not token:
            return None
        with self.lock:
            row = self.db.one("SELECT account_id FROM server_tokens WHERE token = ?", (token,))
        return row["account_id"] if row else None

    def account_info(self, account_id: int) -> dict:
        a = self.svc.accounts.get(account_id)
        return {"id": a.id, "username": a.username, "display_name": a.display_name, "bio": a.bio,
                "private_account": a.private_account, "allow_comments": a.allow_comments}

    # -------------------------------------------------------------- calls
    def call(self, actor: int, method: str, args: dict):
        spec = METHODS.get(method)
        if spec is None:
            if method == "update_profile":
                return self.update_profile(actor, args)
            raise SocialError("Unknown request.")
        needs_actor, allowed = spec
        clean = {k: v for k, v in (args or {}).items() if k in allowed}
        if "limit" in clean:
            clean["limit"] = max(1, min(100, int(clean["limit"])))
        fn = getattr(self.social, method)
        with self.lock:
            if method == "update_video":
                video_id = clean.pop("video_id", None)
                result = fn(actor, video_id, **clean)
            else:
                result = fn(actor, **clean) if needs_actor else fn(**clean)
        return _jsonable(result)

    def update_profile(self, actor: int, args: dict) -> dict:
        name, bio = str(args.get("display_name", "")), str(args.get("bio", ""))
        if moderation.contains_blocked_language(name + " " + bio):
            raise SocialError("Please remove offensive language.")
        with self.lock:
            self.svc.accounts.update_profile(actor, display_name=name or None, bio=bio,
                                             private_account=bool(args.get("private_account")),
                                             allow_comments=bool(args.get("allow_comments", True)))
            return self.account_info(actor)

    def upload(self, actor: int, data_path: Path, meta: dict) -> dict:
        with self.lock:
            v = self.social.upload(actor, data_path, meta.get("title", ""), meta.get("caption", ""),
                                   visibility=meta.get("visibility", "public"),
                                   allow_comments=meta.get("allow_comments", "1") not in ("0", "false"))
        return _jsonable(v)

    def video_file(self, actor: int, video_id: str) -> Path:
        with self.lock:
            v = self.social.get_video(actor, video_id)      # raises if this account may not see it
        return v.abs_path


class _Handler(BaseHTTPRequestHandler):
    service: SocialService = None
    server_version = "XgunSocial/1"

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    # ---------------------------------------------------------- helpers
    def _send(self, code: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_JSON:
            raise SocialError("Request too large.")
        data = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(data, dict):
            raise SocialError("Bad request.")
        return data

    def _actor(self) -> int | None:
        auth = self.headers.get("Authorization", "")
        return self.service.account_for(auth[7:] if auth.startswith("Bearer ") else None)

    def _guarded(self, fn):
        try:
            fn()
        except SocialError as exc:
            self._send(400, {"error": str(exc)})
        except (ValueError, TypeError, KeyError) as exc:
            log.info("Bad request %s: %s", self.path, exc)
            self._send(400, {"error": "Bad request."})
        except Exception:
            log.exception("Server error on %s", self.path)
            self._send(500, {"error": "Server error."})

    # ---------------------------------------------------------- routes
    def do_GET(self):
        self._guarded(self._get)

    def do_POST(self):
        self._guarded(self._post)

    def _get(self):
        url = urlparse(self.path)
        actor = self._actor()
        if url.path == "/api/health":
            return self._send(200, {"ok": True, "service": "xgun-social", "version": 1})
        if actor is None:
            return self._send(401, {"error": "Please sign in again."})
        if url.path == "/api/me":
            return self._send(200, self.service.account_info(actor))
        if url.path.startswith("/api/video/"):
            path = self.service.video_file(actor, url.path.rsplit("/", 1)[1])
            size = path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.send_header("X-Extension", path.suffix.lower())
            self.end_headers()
            with path.open("rb") as fh:
                while chunk := fh.read(65536):
                    self.wfile.write(chunk)
            return None
        return self._send(404, {"error": "Not found."})

    def _post(self):
        url = urlparse(self.path)
        if url.path == "/api/register":
            body = self._json_body()
            token, acc = self.service.register(str(body.get("username", "")), str(body.get("password", "")),
                                               body.get("display_name"))
            return self._send(200, {"token": token, "account": acc})
        if url.path == "/api/login":
            body = self._json_body()
            token, acc = self.service.login(str(body.get("username", "")), str(body.get("password", "")))
            return self._send(200, {"token": token, "account": acc})
        actor = self._actor()
        if actor is None:
            return self._send(401, {"error": "Please sign in again."})
        if url.path == "/api/call":
            body = self._json_body()
            return self._send(200, {"result": self.service.call(actor, str(body.get("method")), body.get("args") or {})})
        if url.path == "/api/upload":
            meta = {k: v[0] for k, v in parse_qs(url.query).items()}
            ext = meta.get("ext", ".mp4").lower()
            if ext not in SUPPORTED_EXTENSIONS:
                raise SocialError(f"Unsupported format '{ext}'.")
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BYTES:
                raise SocialError(f"Uploads must be between 1 byte and {MAX_BYTES // 1048576} MB.")
            fd, tmp = tempfile.mkstemp(suffix=ext, dir=self.service.data_dir)
            try:
                with os.fdopen(fd, "wb") as fh:
                    left = n
                    while left > 0:
                        chunk = self.rfile.read(min(65536, left))
                        if not chunk:
                            raise SocialError("Upload interrupted.")
                        fh.write(chunk)
                        left -= len(chunk)
                return self._send(200, {"result": self.service.upload(actor, Path(tmp), meta)})
            finally:
                Path(tmp).unlink(missing_ok=True)
        return self._send(404, {"error": "Not found."})


class SocialServer:
    def __init__(self, data_dir: Path, host: str = "0.0.0.0", port: int = DEFAULT_SOCIAL_PORT, **kw):
        self.service = SocialService(data_dir, **kw)
        handler = type("Handler", (_Handler,), {"service": self.service})
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]

    def serve_in_background(self) -> threading.Thread:
        t = threading.Thread(target=self.httpd.serve_forever, name="xgun-social-server", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.service.svc.close()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Xgun shared social server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=DEFAULT_SOCIAL_PORT)
    ap.add_argument("--data", default=str(paths.ROOT / "server_data"), help="folder for the database and videos")
    ap.add_argument("--no-demo", action="store_true", help="don't add the demo accounts and sample clips")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = SocialServer(Path(args.data), args.host, args.port, seed_demo=not args.no_demo)
    log.info("Social server on http://%s:%d  (data in %s)", args.host, server.port, args.data)
    try:
        server.httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
