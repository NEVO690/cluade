"""RAILBLAZE: City Run - launcher.

Run with:  python main.py
"""
import importlib.util
import sys

if sys.version_info < (3, 9):
    sys.exit("RAILBLAZE needs Python 3.9 or newer.")

if importlib.util.find_spec("pygame") is None:
    sys.exit("pygame-ce is not installed. Run:  pip install -r requirements.txt")

from game.main import main

if __name__ == "__main__":
    sys.exit(main())
