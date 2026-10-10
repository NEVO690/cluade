"""Video thumbnails extracted in-game (no ffmpeg needed on the player's PC).

A MovieTexture only decodes while it is being drawn, so each queued video is
shown on an invisible card for a few frames, then one frame is copied out,
letterboxed to 9:16 and cached as a PNG in the user folder.
"""
from __future__ import annotations

import logging
from pathlib import Path

from panda3d.core import CardMaker, MovieTexture, PNMImage, TransparencyAttrib

from config import paths
from game.assets import fn

log = logging.getLogger(__name__)
THUMB_W, THUMB_H = 180, 320
FRAMES_TO_WAIT = 4


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
            tex = MovieTexture("thumb")
            try:
                ok = tex.read(fn(source)) and tex.getVideoWidth() > 0
            except Exception:
                ok = False
            if not ok:
                self.failed.add(video_id)
                return task.cont
            tex.setLoop(False)
            tex.setTime(min(1.0, tex.getVideoLength() * 0.3))
            tex.play()
            cm = CardMaker("thumb-card")
            cm.setFrame(-0.001, 0.001, -0.001, 0.001)
            card = self.app.render2d.attachNewNode(cm.generate())
            card.setTexture(tex)
            card.setTransparency(TransparencyAttrib.M_alpha)
            card.setAlphaScale(0.0)           # drawn (so it decodes) but invisible
            self._current = [video_id, tex, card, 0]
            return task.cont
        self._current[3] += 1
        video_id, tex, card, waited = self._current
        if waited < FRAMES_TO_WAIT:
            return task.cont
        try:
            frame = PNMImage()
            if tex.store(frame) and frame.getXSize() > 0:
                self._write(video_id, frame, tex.getVideoWidth(), tex.getVideoHeight())
                self.version += 1
            else:
                self.failed.add(video_id)
        except Exception as exc:
            log.info("Thumbnail failed for %s: %s", video_id, exc)
            self.failed.add(video_id)
        tex.stop()
        card.removeNode()
        self._current = None
        return task.cont

    @staticmethod
    def _write(video_id: str, frame: PNMImage, vw: int, vh: int) -> None:
        # the texture may be padded to a power of two: crop to the real picture
        if frame.getXSize() != vw or frame.getYSize() != vh:
            crop = PNMImage(vw, vh)
            crop.copySubImage(frame, 0, 0, 0, frame.getYSize() - vh, vw, vh)
            frame = crop
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
