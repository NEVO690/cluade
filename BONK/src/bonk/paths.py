"""Filesystem locations.  Everything is relative to the BONK project folder."""

import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
MAPS_DIR = os.path.join(DATA_DIR, "maps")
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
MODELS_DIR = os.path.join(ASSETS_DIR, "models")
AUDIO_DIR = os.path.join(ASSETS_DIR, "audio")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")


def save_dir():
    """Where progress is stored.  Override with the BONK_SAVE_DIR environment variable."""
    return os.environ.get("BONK_SAVE_DIR") or os.path.join(PROJECT_DIR, "saves")
