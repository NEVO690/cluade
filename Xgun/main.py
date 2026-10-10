"""Xgun — launch the game.

    python main.py                 start normally
    python main.py --windowed      ignore the fullscreen setting
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str]) -> int:
    from game.app import XgunApp, setup_logging
    from config.settings import Settings
    setup_logging()
    settings = Settings.load()
    if "--windowed" in argv:
        settings.fullscreen = False
    offscreen = bool(os.environ.get("XGUN_OFFSCREEN"))   # CI / headless smoke runs (software renderer)
    if offscreen:
        from panda3d.core import loadPrcFileData
        loadPrcFileData("offscreen", "load-display p3tinydisplay")
    app = XgunApp(settings, offscreen=offscreen)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
