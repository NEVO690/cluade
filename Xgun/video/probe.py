"""Decode probe built on Panda3D's FFmpeg movie support (no window needed)."""
from __future__ import annotations

import logging
from pathlib import Path

from video.validation import VideoInfo

log = logging.getLogger(__name__)


def panda_probe(path: Path) -> VideoInfo | None:
    try:
        from panda3d.core import Filename, MovieVideo
    except ImportError:  # pragma: no cover - Panda3D is a hard dependency of the game
        return None
    try:
        cursor = MovieVideo.get(Filename.from_os_specific(str(path))).open()
        if cursor is None:
            return None
        width, height, length = cursor.size_x(), cursor.size_y(), cursor.length()
        # FFmpeg refuses to open truncated / garbled containers, so a cursor with a
        # picture size and a finite duration means the stream is playable.
        if length <= 0 or length != length:  # NaN guard
            return None
        return VideoInfo(int(width), int(height), float(length), path.stat().st_size)
    except Exception as exc:  # FFmpeg errors surface as assertions/exceptions
        log.info("Probe failed for %s: %s", path, exc)
        return None
