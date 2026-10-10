"""XGUN - the full 3D game (Panda3D), installed and started from one Python file.

Paste this into a desktop Python app (IDLE, Thonny, VS Code, PyCharm) on
Windows, Mac or Linux, save it as xgun_full_game.py and run it.

First run (needs internet, about 5 minutes):
  1. downloads the complete Xgun game - all code files, 3D models, sounds,
     textures and videos - from github.com/NEVO690/cluade (about 38 MB)
  2. unpacks it into an "Xgun" folder next to this file
  3. creates Xgun/.venv and installs Panda3D and the other libraries
  4. starts the game
Later runs start the game straight away. Every step is printed, and the
window stays open if something goes wrong.
"""
import io
import os
import platform
import shutil
import subprocess
import sys
import traceback
import urllib.request
import zipfile
from pathlib import Path

REPO_ZIP = "https://codeload.github.com/NEVO690/cluade/zip/refs/heads/claude/nice-albattani-2z4dnk"
HERE = Path(__file__).resolve().parent
GAME = HERE / "Xgun"


def say(msg):
    print("\n==> " + msg, flush=True)


def fail(msg):
    print("\n*** PROBLEM: " + msg)
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass
    sys.exit(1)


def download():
    say("Downloading the full game (about 38 MB)...")
    req = urllib.request.Request(REPO_ZIP, headers={"User-Agent": "xgun-launcher"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            buf, got = io.BytesIO(), 0
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                buf.write(chunk)
                got += len(chunk)
                mb = got / 1048576
                print(f"\r    {mb:5.1f} MB" + (f" of {total / 1048576:.1f} MB" if total else ""), end="", flush=True)
    except Exception as exc:
        fail(f"Couldn't download the game ({exc}). Check the internet connection and try again.")
    print()
    say("Unpacking to " + str(GAME))
    with zipfile.ZipFile(buf) as z:
        names = z.namelist()
        root = next((n[: -len("Xgun/main.py")] for n in names if n.endswith("Xgun/main.py")), None)
        if root is None:
            fail("The download doesn't contain the game.")
        prefix = root + "Xgun/"
        tmp = HERE / "Xgun_download_tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        for n in names:
            if n.startswith(prefix) and not n.endswith("/") and "/assets/blender/" not in n:
                dest = tmp / n[len(prefix):]
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(n) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
    keep = GAME / "userdata"                     # keep saves from an older install
    if keep.exists():
        shutil.move(str(keep), str(tmp / "userdata"))
    shutil.rmtree(GAME, ignore_errors=True)
    tmp.rename(GAME)


def venv_python():
    return GAME / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def install():
    py = venv_python()
    if not py.exists():
        say("Creating a private Python environment in Xgun/.venv")
        base = sys.executable
        if base.lower().endswith("pythonw.exe"):          # IDLE on Windows runs pythonw
            base = base[:-len("pythonw.exe")] + "python.exe"
        if subprocess.call([base, "-m", "venv", str(GAME / ".venv")]) != 0 or not py.exists():
            fail("Couldn't create the environment. Install Python from python.org (64-bit) and try again.")
    ok = subprocess.call([str(py), "-c", "import panda3d, gltf, simplepbr, numpy"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    if not ok:
        say("Installing Panda3D, glTF support and numpy (a few minutes)...")
        subprocess.call([str(py), "-m", "pip", "install", "--upgrade", "pip"])
        req = ["panda3d==1.10.16", "panda3d-gltf>=1.3,<2", "panda3d-simplepbr>=0.13,<1", "numpy>=1.26"]
        if subprocess.call([str(py), "-m", "pip", "install"] + req) != 0:
            fail("Installing the libraries failed (messages above).")
    return py


def main():
    print(f"XGUN launcher - Python {platform.python_version()} ({platform.architecture()[0]}) on {platform.system()}")
    if sys.version_info < (3, 10):
        fail("Python 3.10 or newer is needed. Install it from python.org.")
    if platform.architecture()[0] != "64bit":
        fail("64-bit Python is needed. Install the 64-bit version from python.org.")
    if "ANDROID_ROOT" in os.environ or "ANDROID_DATA" in os.environ:
        fail("Phones can't run the 3D game (Panda3D has no Android version). Use a Windows, Mac or Linux computer.")
    if not (GAME / "main.py").exists() or not (GAME / "assets" / "models" / "manifest.json").exists():
        download()
    py = install()
    say("Starting Xgun!")
    code = subprocess.call([str(py), "main.py", "--windowed"], cwd=str(GAME))
    if code != 0:
        log = GAME / "userdata" / "logs" / "xgun.log"
        if log.exists():
            print("\nLast lines of the game log:")
            print("".join(log.read_text(encoding="utf-8", errors="replace").splitlines(True)[-30:]))
        fail(f"The game closed with an error (code {code}).")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        fail("Unexpected problem (details above).")
