"""Validation for player video uploads.

Checks happen in order of cost: extension → file size → container magic
bytes → a real decode probe. Renamed, truncated or corrupt files are
rejected with a readable message instead of crashing the lobby.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SUPPORTED_EXTENSIONS = {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".ogv"}
MAX_BYTES = 200 * 1024 * 1024
MIN_BYTES = 2 * 1024
MAX_DURATION = 180.0
MIN_DURATION = 0.5
MAX_DIMENSION = 4096


class UploadError(ValueError):
    pass


@dataclass
class VideoInfo:
    width: int
    height: int
    duration: float
    size_bytes: int

    @property
    def is_vertical(self) -> bool:
        return self.height > self.width


def _sniff_container(header: bytes) -> str | None:
    if len(header) >= 12 and header[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"):
        return "isobmff"     # mp4 / m4v / mov
    if header[:4] == b"\x1a\x45\xdf\xa3":
        return "matroska"    # webm / mkv
    if header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return "avi"
    if header[:4] == b"OggS":
        return "ogg"
    return None


_EXPECTED = {".mp4": "isobmff", ".m4v": "isobmff", ".mov": "isobmff", ".webm": "matroska",
             ".mkv": "matroska", ".avi": "avi", ".ogv": "ogg"}


def validate_video_file(path: str | Path,
                        probe: Callable[[Path], VideoInfo | None] | None = None) -> VideoInfo:
    """Validate a candidate upload. ``probe`` decodes the file and returns its
    dimensions/duration (or ``None`` if it can't be decoded)."""
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise UploadError("File not found.")
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UploadError(f"Unsupported format '{ext or 'none'}'. Use MP4, MOV, WEBM, MKV, AVI or OGV.")
    size = path.stat().st_size
    if size < MIN_BYTES:
        raise UploadError("The file is empty or too small to be a video.")
    if size > MAX_BYTES:
        raise UploadError(f"The file is {size / 1048576:.0f} MB. The limit is {MAX_BYTES // 1048576} MB.")
    try:
        with path.open("rb") as fh:
            header = fh.read(16)
    except OSError as exc:
        raise UploadError(f"Couldn't read the file: {exc.strerror or exc}") from exc
    container = _sniff_container(header)
    if container is None:
        raise UploadError("This doesn't look like a video file (unrecognised data).")
    if container != _EXPECTED[ext]:
        raise UploadError(f"The file content doesn't match its '{ext}' extension.")
    info = VideoInfo(0, 0, 0.0, size)
    if probe is not None:
        probed = probe(path)
        if probed is None:
            raise UploadError("The video couldn't be decoded. It may be corrupt or use an unsupported codec.")
        info = VideoInfo(probed.width, probed.height, probed.duration, size)
        if info.width <= 0 or info.height <= 0:
            raise UploadError("The video has no picture track.")
        if info.width > MAX_DIMENSION or info.height > MAX_DIMENSION:
            raise UploadError(f"Resolution {info.width}x{info.height} is above the {MAX_DIMENSION}px limit.")
        if info.duration < MIN_DURATION:
            raise UploadError("The video is too short.")
        if info.duration > MAX_DURATION:
            raise UploadError(f"Videos can be up to {int(MAX_DURATION // 60)} minutes long.")
    return info
