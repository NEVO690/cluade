"""Pack the playable project into dist/BONK.zip (no saves, caches or server data).

    python tools/make_zip.py
"""

import os
import zipfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKIP_DIRS = {"__pycache__", "saves", "server_data", "dist", ".venv", "venv", ".git"}
SKIP_EXT = {".pyc", ".tmp", ".zip"}


def main():
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "BONK.zip")
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("shots"))
            for f in sorted(files):
                if os.path.splitext(f)[1] in SKIP_EXT or ".corrupt-" in f:
                    continue
                path = os.path.join(base, f)
                zf.write(path, os.path.join("BONK", os.path.relpath(path, ROOT)))
                count += 1
    print("wrote %s (%d files, %.1f MB)" % (out, count, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
