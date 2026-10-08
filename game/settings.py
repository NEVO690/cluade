"""Global constants, paths and tunables for RAILBLAZE: City Run.

Everything that is a "magic number" for gameplay lives here so balancing the
game never requires hunting through the code.
"""
import os

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
IMAGES_DIR = os.path.join(ASSETS_DIR, "images")
SOUNDS_DIR = os.path.join(ASSETS_DIR, "sounds")
MUSIC_DIR = os.path.join(ASSETS_DIR, "music")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
# SSC_SAVE_DIR lets tests (or portable installs) keep saves elsewhere.
SAVE_DIR = os.environ.get("SSC_SAVE_DIR") or os.path.join(ROOT_DIR, "saves")
CACHE_DIR = os.path.join(ROOT_DIR, "cache")
LOG_DIR = os.path.join(ROOT_DIR, "logs")

# --------------------------------------------------------------------------
# Window
# --------------------------------------------------------------------------
TITLE = "RAILBLAZE: City Run"
VERSION = "1.0.0"
SCREEN_W, SCREEN_H = 1280, 720
FPS = 60

# --------------------------------------------------------------------------
# World layout (metres). x = sideways, y = up, z = forward.
# --------------------------------------------------------------------------
LANE_COUNT = 3
LANE_WIDTH = 2.6
LANE_X = (-LANE_WIDTH, 0.0, LANE_WIDTH)
LANE_HALF = 1.1             # half width of an obstacle that fills a lane
ROAD_HALF = 4.3             # half width of the track bed
SIDEWALK_HALF = 7.6         # half width of track bed + sidewalks
CHUNK_LENGTH = 40.0
START_SAFE_DISTANCE = 70.0  # no obstacles before this distance

# --------------------------------------------------------------------------
# Player physics
# --------------------------------------------------------------------------
GRAVITY = 38.0
FAST_FALL_GRAVITY = 120.0
JUMP_VELOCITY = 12.0
LANE_SWITCH_SPEED = 17.0
SLIDE_TIME = 0.72
PLAYER_HALF_W = 0.35
PLAYER_HALF_D = 0.3
PLAYER_HEIGHT = 1.75
PLAYER_SLIDE_HEIGHT = 0.85
STEP_HEIGHT = 0.6           # how far below a surface the feet may be and still land on it
STUMBLE_WINDOW = 4.0        # second stumble inside this window ends the run
INVULN_AFTER_SAVE = 1.4     # seconds of invulnerability after shield/board absorb a hit

START_SPEED = 15.0
MAX_SPEED = 33.0
SPEED_RAMP_DISTANCE = 4200.0

PHYSICS_STEP = 1.0 / 120.0
MAX_FRAME_DT = 0.05

# --------------------------------------------------------------------------
# Camera
# --------------------------------------------------------------------------
CAMERA_BACK = 7.6
CAMERA_HEIGHT = 3.9
CAMERA_HFOV = 70.0
HORIZON_RATIO = 0.28
NEAR_PLANE = 0.8

# --------------------------------------------------------------------------
# Graphics quality presets
# --------------------------------------------------------------------------
QUALITY_PRESETS = {
    "low": {"draw_distance": 125, "particles": 70, "windows": False, "glow": False,
            "ties": False, "decor_density": 0.55, "segment": 8.0, "weather": 25},
    "medium": {"draw_distance": 170, "particles": 170, "windows": True, "glow": True,
               "ties": True, "decor_density": 0.8, "segment": 6.0, "weather": 60},
    "high": {"draw_distance": 225, "particles": 300, "windows": True, "glow": True,
             "ties": True, "decor_density": 1.0, "segment": 5.0, "weather": 110},
}

# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
COIN_SCORE = 10
GEM_SCORE = 250
COMBO_DECAY_TIME = 2.6
COMBO_STEP = 12              # combo points per +0.5 multiplier
COMBO_MAX_MULT = 4.0
MAX_LEVEL = 50

# --------------------------------------------------------------------------
# UI palette
# --------------------------------------------------------------------------
UI_BG = (18, 22, 40)
UI_PANEL = (32, 38, 68)
UI_PANEL_LIGHT = (48, 58, 98)
UI_ACCENT = (255, 196, 40)
UI_ACCENT_2 = (60, 210, 255)
UI_GOOD = (70, 220, 120)
UI_BAD = (240, 80, 80)
UI_TEXT = (245, 245, 255)
UI_TEXT_DIM = (170, 175, 205)
COIN_COLOR = (255, 205, 40)
GEM_COLOR = (90, 230, 255)
