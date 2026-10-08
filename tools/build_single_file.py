"""Pack the whole game into ONE runnable Python file.

    python tools/build_single_file.py [output.py]

The generated file embeds game/, data/ and assets/ as a compressed archive.
When run it extracts them next to itself (folder "Railblaze_files"),
installs pygame-ce/numpy if they are missing, and starts the game.
"""
import base64
import hashlib
import io
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCLUDE_DIRS = ("game", "data", "assets")
INCLUDE_FILES = ("README.md", "requirements.txt")

TEMPLATE = r'''#!/usr/bin/env python3
"""RAILBLAZE: City Run - single-file edition.

Run:   python Railblaze.py

On first start the game files are unpacked into a folder next to this file
("Railblaze_files") and missing packages (pygame-ce, numpy) are
installed with pip. Saves are kept in that folder too.
"""
import base64
import io
import os
import shutil
import subprocess
import sys
import zipfile

VERSION = "__HASH__"
PAYLOAD = (
__PAYLOAD__
)


def ensure_packages():
    missing = []
    try:
        import pygame  # noqa: F401
    except ImportError:
        missing.append("pygame-ce")
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")
    if missing:
        print("Installing:", ", ".join(missing))
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])


def unpack():
    here = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(here, "Railblaze_files")
    stamp = os.path.join(target, ".version")
    try:
        with open(stamp, encoding="utf-8") as f:
            current = f.read().strip()
    except OSError:
        current = ""
    old_saves = os.path.join(here, "SubwaySurferCity_files", "saves")
    if os.path.isdir(old_saves) and not os.path.isdir(os.path.join(target, "saves")):
        # keep the progress made with the game's previous name
        shutil.copytree(old_saves, os.path.join(target, "saves"))
    if current != VERSION:
        print("Unpacking game files to", target)
        data = base64.b64decode("".join(PAYLOAD))
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(target)
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(VERSION)
    return target


def main():
    if sys.version_info < (3, 9):
        sys.exit("RAILBLAZE: City Run needs Python 3.9 or newer.")
    ensure_packages()
    target = unpack()
    sys.path.insert(0, target)
    os.chdir(target)
    from game.main import main as game_main
    return game_main()


if __name__ == "__main__":
    sys.exit(main())
'''


def build(out_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for d in INCLUDE_DIRS:
            for base, dirs, files in os.walk(os.path.join(ROOT, d)):
                dirs[:] = [x for x in dirs if x != "__pycache__"]
                for name in sorted(files):
                    if name.endswith(".pyc"):
                        continue
                    full = os.path.join(base, name)
                    zf.write(full, os.path.relpath(full, ROOT))
        for name in INCLUDE_FILES:
            zf.write(os.path.join(ROOT, name), name)
    raw = buf.getvalue()
    b64 = base64.b64encode(raw).decode("ascii")
    lines = "\n".join(f'    "{b64[i:i + 100]}"' for i in range(0, len(b64), 100))
    text = TEMPLATE.replace("__HASH__", hashlib.sha1(raw).hexdigest()[:12]).replace("__PAYLOAD__", lines)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"Wrote {out_path} ({len(text) // 1024} KB)")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "Railblaze.py"))
