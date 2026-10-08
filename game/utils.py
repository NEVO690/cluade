"""Shared helpers: logging, safe JSON IO, maths and colour utilities."""
import copy
import datetime
import json
import logging
import os

from . import settings as S

log = logging.getLogger("ssc")

# Human readable problems found while loading data/assets/saves.
# The main menu shows them as toasts so the player knows something was wrong.
WARNINGS = []


def warn(message):
    log.warning(message)
    if message not in WARNINGS:
        WARNINGS.append(message)


def setup_logging():
    root = logging.getLogger("ssc")
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    try:
        os.makedirs(S.LOG_DIR, exist_ok=True)
        fh = logging.FileHandler(os.path.join(S.LOG_DIR, "game.log"), mode="w", encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)


def rel(path):
    try:
        return os.path.relpath(path, S.ROOT_DIR)
    except ValueError:
        return path


def load_json(path, default):
    """Load JSON, returning a copy of ``default`` (and recording a warning) on any problem."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        warn(f"Missing file {rel(path)} - using built-in defaults")
    except (OSError, ValueError) as e:  # JSONDecodeError / UnicodeDecodeError are ValueErrors
        warn(f"Invalid file {rel(path)} ({e.__class__.__name__}) - using built-in defaults")
    return copy.deepcopy(default)


def write_json_atomic(path, data):
    """Write JSON through a temp file so a crash never leaves a half-written save."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Maths
# --------------------------------------------------------------------------
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def approach(value, target, delta):
    if value < target:
        return min(value + delta, target)
    return max(value - delta, target)


def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


# --------------------------------------------------------------------------
# Colours
# --------------------------------------------------------------------------
def lerp_color(c1, c2, t):
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def shade(c, f):
    """Multiply a colour by ``f`` (f>1 brightens) and clamp to 0..255."""
    return (min(255, max(0, int(c[0] * f))),
            min(255, max(0, int(c[1] * f))),
            min(255, max(0, int(c[2] * f))))


def to_color(value, fallback=(255, 0, 255)):
    try:
        c = tuple(int(clamp(float(x), 0, 255)) for x in value[:3])
        if len(c) == 3:
            return c
    except (TypeError, ValueError):
        pass
    return tuple(fallback)


# --------------------------------------------------------------------------
# Misc
# --------------------------------------------------------------------------
def today():
    return datetime.date.today()


def parse_date(text):
    try:
        return datetime.date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def fmt_int(n):
    return f"{int(n):,}"
