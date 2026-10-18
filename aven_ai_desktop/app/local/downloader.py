"""Resumable, verified model downloads."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from app.local.models import ModelFile
from app.paths import user_data_dir
from app.version import __version__

log = logging.getLogger(__name__)

CHUNK = 1024 * 1024
ProgressCallback = Callable[[int, int], None]  # (bytes done, total bytes)


class DownloadError(Exception):
    """User-facing download failure."""


class DownloadCancelledError(Exception):
    pass


def models_dir() -> Path:
    path = user_data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_path(file: ModelFile) -> Path:
    return models_dir() / file.filename


def is_downloaded(file: ModelFile) -> bool:
    path = model_path(file)
    return path.is_file() and path.stat().st_size == file.size


def _hash_existing(path: Path, digest: hashlib._Hash) -> int:
    done = 0
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
            done += len(block)
    return done


def download_model(
    file: ModelFile,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
    url: str | None = None,
    dest_dir: Path | None = None,
) -> Path:
    """Download ``file`` (resuming a partial download) and verify it. Returns the final path."""
    url = url or file.url
    if not (url.startswith("https://") or url.startswith("http://127.0.0.1")):
        raise DownloadError("Refusing to download over an insecure connection.")
    dest_dir = dest_dir or models_dir()
    final = dest_dir / file.filename
    if final.is_file() and final.stat().st_size == file.size:
        return final
    part = dest_dir / (file.filename + ".part")
    cancel = cancel or threading.Event()

    digest = hashlib.sha256()
    done = _hash_existing(part, digest) if part.exists() else 0
    if done > file.size:
        part.unlink()
        digest, done = hashlib.sha256(), 0

    if done < file.size:
        headers = {"User-Agent": f"AVEN-AI-Desktop/{__version__}"}
        if done:
            headers["Range"] = f"bytes={done}-"
        request = urllib.request.Request(url, headers=headers)  # noqa: S310 - scheme checked above
        try:
            response = urllib.request.urlopen(request, timeout=60)  # noqa: S310 - scheme checked above
        except urllib.error.HTTPError as exc:
            raise DownloadError(f"The download server returned an error (HTTP {exc.code}).") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DownloadError("Could not connect to the download server. Check your internet connection.") from exc
        with response:
            if done and response.status != 206:  # server ignored the range: start over
                digest, done = hashlib.sha256(), 0
                mode = "wb"
            else:
                mode = "ab" if done else "wb"
            try:
                with part.open(mode) as out:
                    while True:
                        if cancel.is_set():
                            raise DownloadCancelledError()
                        block = response.read(CHUNK)
                        if not block:
                            break
                        out.write(block)
                        digest.update(block)
                        done += len(block)
                        if progress:
                            progress(done, file.size)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                raise DownloadError("The download was interrupted. Try again to resume it.") from exc

    if done != file.size or digest.hexdigest() != file.sha256:
        part.unlink(missing_ok=True)
        raise DownloadError("The downloaded file failed its integrity check and was deleted. Please try again.")
    os.replace(part, final)
    log.info("Downloaded %s", file.filename)
    return final


def delete_model(file: ModelFile) -> None:
    for path in (model_path(file), models_dir() / (file.filename + ".part")):
        path.unlink(missing_ok=True)
