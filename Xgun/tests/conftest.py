import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_user_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XGUN_USER_DIR", str(tmp_path / "userdata"))
    yield tmp_path / "userdata"


@pytest.fixture
def services(tmp_path):
    from game.services import Services
    svc = Services(tmp_path / "test.db", seed_demo=False)
    yield svc
    svc.close()


@pytest.fixture
def make_video(tmp_path):
    """Create small but genuinely decodable MP4 files with ffmpeg when available,
    else a structurally valid stub (enough for validation without a probe)."""
    import shutil
    import subprocess

    def _make(name="clip.mp4", seconds=1, size="180x320"):
        out = tmp_path / name
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            f"testsrc=size={size}:rate=15", "-t", str(seconds), "-pix_fmt", "yuv420p",
                            "-c:v", "libx264", str(out)], check=True)
        else:
            out.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4096)
        return out
    return _make
