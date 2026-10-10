"""Central place for every filesystem path used by Xgun.

All game code resolves paths through this module so the project can be
moved anywhere (or packaged) without hunting for hard-coded strings.
User-generated state (database, uploaded videos, settings, logs) lives in
``USER_DIR`` which can be overridden with the ``XGUN_USER_DIR`` environment
variable — the automated tests use that to work in a throw-away folder.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ASSETS = ROOT / "assets"
MODELS = ASSETS / "models"
TEXTURES = ASSETS / "textures"
FONTS = ASSETS / "fonts"
AUDIO = ASSETS / "audio"
SFX = AUDIO / "sfx"
MUSIC = AUDIO / "music"
UI_ASSETS = ASSETS / "ui"
ICONS = UI_ASSETS / "icons"
THUMBS = UI_ASSETS / "thumbs"
SAMPLE_VIDEOS = ASSETS / "videos" / "samples"
BLENDER_SOURCES = ASSETS / "blender"
MODEL_MANIFEST = MODELS / "manifest.json"

DATA = ROOT / "data"
CATALOG_FILE = DATA / "catalog" / "cosmetics.json"
WEAPONS_FILE = DATA / "gameplay" / "weapons.json"
LOOT_FILE = DATA / "gameplay" / "loot.json"
QUESTS_FILE = DATA / "gameplay" / "quests.json"
BATTLE_PASS_FILE = DATA / "gameplay" / "battle_pass.json"


def user_dir() -> Path:
    """Folder for per-install, writable player data (never committed)."""
    override = os.environ.get("XGUN_USER_DIR")
    path = Path(override) if override else ROOT / "userdata"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_file() -> Path:
    return user_dir() / "xgun.db"


def settings_file() -> Path:
    return user_dir() / "settings.json"


def uploads_dir() -> Path:
    path = user_dir() / "videos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = user_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
