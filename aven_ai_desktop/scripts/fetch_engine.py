"""Download the pinned llama.cpp ``llama-server`` build into ./engine for bundling.

Usage:  python scripts/fetch_engine.py [--platform win-x64|linux-x64]

The archive is verified against its SHA-256 checksum before anything is extracted.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = ROOT / "engine"

LLAMA_CPP_TAG = "b11718"
ASSETS = {
    "win-x64": (
        "llama-b11718-bin-win-cpu-x64.zip",
        "92cc529b29a43f9a30e21d490cb2e95062acd0b59af6fee8b3b52b28074f838c",
    ),
    "linux-x64": (
        "llama-b11718-bin-ubuntu-x64.tar.gz",
        "99f83b15cea9a4fb8945516c276b5f42b11608f82104fc6fa98a541cac826de7",
    ),
}


def current_platform() -> str:
    return "win-x64" if sys.platform == "win32" else "linux-x64"


def fetch(platform: str) -> Path:
    name, sha256 = ASSETS[platform]
    url = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_TAG}/{name}"
    print(f"Downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "aven-ai-build"})
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310 - fixed https URL
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        raise SystemExit(f"Checksum mismatch for {name}: expected {sha256}, got {digest}")
    print(f"Verified {name} ({len(data) / 1e6:.1f} MB)")

    binary = "llama-server.exe" if platform.startswith("win") else "llama-server"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        if name.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                archive.extractall(tmp_path)  # noqa: S202 - checksum-verified official archive
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                archive.extractall(tmp_path, filter="data")
        found = next(tmp_path.rglob(binary), None)
        if found is None:
            raise SystemExit(f"{binary} not found in {name}")
        if ENGINE_DIR.exists():
            shutil.rmtree(ENGINE_DIR)
        # Keep the server and the libraries next to it; drop the other command-line tools.
        shutil.copytree(found.parent, ENGINE_DIR)
    for tool in ENGINE_DIR.iterdir():
        is_tool = tool.name.startswith("llama-") and tool.name != binary
        if is_tool or tool.name in ("test-backend-ops", "test-backend-ops.exe", "rpc-server", "rpc-server.exe"):
            tool.unlink()
    (ENGINE_DIR / binary).chmod(0o755)
    (ENGINE_DIR / "LLAMA_CPP_VERSION.txt").write_text(f"llama.cpp {LLAMA_CPP_TAG} ({name})\n", encoding="utf-8")
    print(f"Engine ready in {ENGINE_DIR}: {sorted(p.name for p in ENGINE_DIR.iterdir())}")
    return ENGINE_DIR / binary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=sorted(ASSETS), default=current_platform())
    fetch(parser.parse_args().platform)
    return 0


if __name__ == "__main__":
    sys.exit(main())
