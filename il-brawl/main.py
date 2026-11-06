"""IL Brawl - entry point. Run:  python main.py"""
import os
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import pygame  # noqa: F401
    except ImportError:
        print("IL Brawl needs pygame. Install it with:  pip install -r requirements.txt")
        sys.exit(1)
    from ilbrawl.engine.game import Game
    Game().run()
