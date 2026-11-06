"""Global constants and paths for IL Brawl."""
import os

GAME_TITLE = "IL Brawl"
VERSION = "1.0.0"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MAPS_DIR = os.path.join(DATA_DIR, "maps")
CUSTOM_MAPS_DIR = os.path.join(DATA_DIR, "maps", "custom")
LOCALE_DIR = os.path.join(BASE_DIR, "locales")
ASSET_DIR = os.path.join(BASE_DIR, "assets")
FONT_DIR = os.path.join(ASSET_DIR, "fonts")
SOUND_DIR = os.path.join(ASSET_DIR, "sounds")
MUSIC_DIR = os.path.join(ASSET_DIR, "music")
SAVE_DIR = os.environ.get("ILBRAWL_SAVE_DIR") or os.path.join(BASE_DIR, "saves")
LOG_DIR = os.path.join(SAVE_DIR, "logs")

# The whole game renders to a fixed virtual canvas that is scaled to the window.
VIRTUAL_W = 1280
VIRTUAL_H = 720
FPS_CAP = 60
SIM_HZ = 60  # fixed gameplay simulation rate

TILE = 48

LANGUAGES = ["he", "en", "ar", "ru"]
DEFAULT_LANGUAGE = "he"
RTL_LANGUAGES = {"he", "ar"}

RESOLUTIONS = [(1024, 576), (1280, 720), (1366, 768), (1600, 900), (1920, 1080)]

TEAM_COLORS = [(72, 146, 222), (214, 70, 64)]
SOLO_COLORS = [(64, 160, 255), (255, 72, 88), (255, 170, 40), (170, 90, 255), (60, 210, 120), (255, 110, 200)]
