"""Video thumbnails extracted in-game (no ffmpeg needed on the player's PC).

Frames are read straight from Panda3D's FFmpeg decoder (no rendering, so it
works the same on every GPU and in the software renderer). One frame per
game frame is tried until a non-black one turns up; it is letterboxed to
9:16 and cached as a PNG in the user folder.
"""
from __future__ import annotations

import logging
from pathlib import Path

from panda3d.core import Filename, MovieVideo, PNMImage, Texture

from config import paths
from game.assets import fn

log = logging.getLogger(__name__)
THUMB_W, THUMB_H = 180, 320
MAX_TRIES = 60
MIN_BRIGHTNESS = 0.02


def thumb_path(video_id: str) -> Path:
    folder = paths.user_dir() / "thumbs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{video_id}.png"


class ThumbnailMaker:
    def __init__(self, app):
        self.app = app
        self.queue: list[tuple[str, Path]] = []
        self.failed: set[str] = set()
        self.version = 0                      # bumps whenever a new thumbnail is written
        self._current = None                  # (video_id, texture, card, frames_waited)
        app.taskMgr.add(self._task, "video-thumbnails")

    def get(self, video) -> Path | None:
        """Cached thumbnail path, or None (and queue it) if it doesn't exist yet."""
        p = thumb_path(video.id)
        if p.exists():
            return p
        if video.id not in self.failed and all(v != video.id for v, _ in self.queue) and \
                (self._current is None or self._current[0] != video.id):
            self.queue.append((video.id, video.abs_path))
        return None

    def _task(self, task):
        if self._current is None:
            if not self.queue:
                return task.cont
            video_id, source = self.queue.pop(0)
            try:
                cursor = MovieVideo.get(Filename.from_os_specific(str(source))).open()
            except Exception:
                cursor = None
            if cursor is None or cursor.size_x() <= 0:
                self.failed.add(video_id)
                return task.cont
            tex = Texture("thumb")
            tex.setup2dTexture(cursor.size_x(), cursor.size_y(), Texture.T_unsigned_byte,
                               Texture.F_rgba if cursor.getNumComponents() == 4 else Texture.F_rgb)
            length = cursor.length() if cursor.length() > 0 else 3.0
            # [video id, cursor, texture, seek time, step, tries]
            self._current = [video_id, cursor, tex, min(1.0, length * 0.3), max(0.1, length / 30), 0]
            return task.cont
        cur = self._current
        video_id, cursor, tex, t, step, tries = cur
        cur[5] += 1
        try:
            cursor.setTime(t, 0)
            buf = cursor.fetchBuffer()        # decoding is threaded: may need a frame or two
            if buf is not None:
                cursor.applyToTexture(buf, tex, 0)
                frame = PNMImage()
                if tex.store(frame) and frame.getAverageGray() > MIN_BRIGHTNESS:
                    self._write(video_id, frame)
                    self.version += 1
                    self._current = None
                    return task.cont
                cur[3] = t + step             # first frame after a seek can be blank: move on
        except Exception as exc:
            log.info("Thumbnail failed for %s: %s", video_id, exc)
            cur[5] = MAX_TRIES
        if cur[5] >= MAX_TRIES:
            self.failed.add(video_id)
            self._current = None
        return task.cont

    @staticmethod
    def _write(video_id: str, frame: PNMImage) -> None:
        vw, vh = frame.getXSize(), frame.getYSize()
        out = PNMImage(THUMB_W, THUMB_H)
        out.fill(0, 0, 0)
        scale = min(THUMB_W / vw, THUMB_H / vh)
        w, h = max(1, int(vw * scale)), max(1, int(vh * scale))
        small = PNMImage(w, h)
        small.gaussianFilterFrom(1.0, frame)
        out.copySubImage(small, (THUMB_W - w) // 2, (THUMB_H - h) // 2)
        out.write(fn(thumb_path(video_id)))

    def destroy(self):
        self.app.taskMgr.remove("video-thumbnails")
