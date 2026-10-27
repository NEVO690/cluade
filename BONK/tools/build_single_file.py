"""Pack the whole game into ONE runnable Python file: dist/BONK_game.py

    python tools/build_single_file.py

The generated file embeds the code, models, sounds, fonts and courses as a
compressed archive.  When run it:
  1. extracts the game to  ~/BONK_game/<version>/  (only the first time),
  2. installs Panda3D + panda3d-gltf with pip if they are missing,
  3. starts the game (any command-line arguments are passed on).
"""

import base64
import hashlib
import io
import os
import zipfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
INCLUDE = ["main.py", "run_server.py", "requirements.txt", "README.md", "assets", "data", "src"]
SKIP_DIRS = {"__pycache__"}
SKIP_EXT = {".pyc", ".blend"}  # the .blend is an editing source, not needed to play

LAUNCHER = r'''#!/usr/bin/env python3
"""BONK! - the whole game in one file.

Run it:   python BONK_game.py
(First start: unpacks the game to your home folder and installs Panda3D if needed.)
Server:   python BONK_game.py --server
"""

import base64
import io
import os
import subprocess
import sys
import zipfile

VERSION = "%(version)s"
PACKAGES = ["panda3d==1.10.16", "panda3d-gltf==1.3.0"]
PAYLOAD = (
%(payload)s
)


def unpack():
    target = os.path.join(os.path.expanduser("~"), "BONK_game", VERSION)
    marker = os.path.join(target, ".complete")
    if not os.path.exists(marker):
        print("Unpacking BONK! to", target)
        data = base64.b64decode("".join(PAYLOAD))
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(target)
        with open(marker, "w") as fh:
            fh.write(VERSION)
    return os.path.join(target, "BONK")


def ensure_packages():
    try:
        import panda3d  # noqa: F401
        import gltf  # noqa: F401
        return True
    except ImportError:
        pass
    print("Installing Panda3D (only needed once, this can take a minute)...")
    cmd = [sys.executable, "-m", "pip", "install", "--user"] + PACKAGES
    if subprocess.call(cmd) != 0:
        cmd.remove("--user")
        if subprocess.call(cmd) != 0:
            print("Could not install Panda3D automatically. Run:  pip install " + " ".join(PACKAGES))
            return False
    import site
    import importlib
    importlib.invalidate_caches()
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.append(user_site)
    return True


def main():
    game = unpack()
    if not ensure_packages():
        input("Press Enter to close...")
        return 1
    os.chdir(game)
    sys.path.insert(0, os.path.join(game, "src"))
    args = sys.argv[1:]
    if args[:1] == ["--server"]:
        from bonk.multiplayer.server import main as server_main
        server_main(args[1:])
        return 0
    from bonk.client.app import run
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for item in INCLUDE:
            path = os.path.join(ROOT, item)
            paths = [path] if os.path.isfile(path) else []
            for base, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                paths += [os.path.join(base, f) for f in sorted(files)]
            for p in paths:
                if os.path.splitext(p)[1] in SKIP_EXT:
                    continue
                zf.write(p, os.path.join("BONK", os.path.relpath(p, ROOT)))
                count += 1
    data = buf.getvalue()
    version = hashlib.sha256(data).hexdigest()[:12]
    b64 = base64.b64encode(data).decode("ascii")
    lines = ",\n".join('    "%s"' % b64[i:i + 100] for i in range(0, len(b64), 100))
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "BONK_game.py")
    with open(out, "w", encoding="ascii", newline="\n") as fh:
        fh.write(LAUNCHER % {"version": version, "payload": lines})
    print("wrote %s (%d files packed, %.1f MB)" % (out, count, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
