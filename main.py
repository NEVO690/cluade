"""SUBWAY SURFER CITY - launcher.

Run with:  python main.py
"""
import sys

if sys.version_info < (3, 9):
    sys.exit("SUBWAY SURFER CITY needs Python 3.9 or newer.")

try:
    import pygame  # noqa: F401
except ImportError:
    sys.exit("pygame-ce is not installed. Run:  pip install -r requirements.txt")

from game.main import main

if __name__ == "__main__":
    sys.exit(main())
