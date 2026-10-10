"""Xgun — launch the game.

    python main.py                 start normally
    python main.py --windowed      ignore the fullscreen setting
"""
from __future__ import annotations

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
    app = XgunApp(settings)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
