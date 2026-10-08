"""Local JSON save system with automatic backup of corrupted saves.

* ``saves/savegame.json`` - player progress (coins, unlocks, missions ...)
* ``saves/settings.json`` - user settings (volume, graphics, key bindings)

Writes are atomic (temp file + rename).  A save that cannot be parsed is
moved to ``*.corrupt-<timestamp>.json`` and a fresh save is started, so the
game never crashes because of a bad file.
"""
import copy
import json
import os
import time

from . import settings as S
from .utils import log, warn, write_json_atomic, today

SAVE_VERSION = 1

DEFAULT_SAVE = {
    "version": SAVE_VERSION,
    "created": "",
    "coins": 0,
    "gems": 0,
    "xp": 0,
    "level": 1,
    "best_score": 0,
    "best_distance": 0,
    "character": "rex",
    "characters_owned": ["rex"],
    "board": "street_board",
    "boards_owned": ["street_board"],
    "outfit": "outfit_default",
    "outfits_owned": ["outfit_default"],
    "trail": "trail_none",
    "trails_owned": ["trail_none"],
    "effect": "fx_classic",
    "effects_owned": ["fx_classic"],
    "emote": "emote_none",
    "emotes_owned": ["emote_none"],
    "upgrades": {},
    "consumables": {"board_charge": 3, "head_start": 0, "score_booster": 0, "revive_key": 1},
    "missions": {"completed": [], "progress": {}},
    "daily_missions": {"date": "", "missions": [], "progress": {}, "completed": []},
    "achievements": {},
    "stats": {},
    "zones_seen": [],
    "daily_reward": {"last_claim": "", "day": 0},
    "events": {},
    "season": {},
    "offers": {"start": "", "bought": []},
    "tutorial_done": False,
}

# Category -> (owned list key, equipped key)
OWNERSHIP_KEYS = {
    "characters": ("characters_owned", "character"),
    "boards": ("boards_owned", "board"),
    "outfits": ("outfits_owned", "outfit"),
    "trails": ("trails_owned", "trail"),
    "effects": ("effects_owned", "effect"),
    "emotes": ("emotes_owned", "emote"),
}


def _compatible(default, value):
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, type(default))


def merge_defaults(default, loaded):
    """Return ``loaded`` with missing/invalid keys replaced by ``default`` values."""
    if not isinstance(loaded, dict):
        return copy.deepcopy(default)
    out = {}
    for key, dval in default.items():
        if key in loaded and _compatible(dval, loaded[key]):
            if isinstance(dval, dict) and dval:
                out[key] = merge_defaults(dval, loaded[key])
                # keep extra keys (e.g. upgrade levels, mission progress)
                for k, v in loaded[key].items():
                    out[key].setdefault(k, v)
            else:
                out[key] = copy.deepcopy(loaded[key])
        else:
            if key in loaded:
                log.warning("Save key '%s' had an invalid value - reset to default", key)
            out[key] = copy.deepcopy(dval)
    for key, val in loaded.items():
        out.setdefault(key, val)
    return out


class _JsonStore:
    def __init__(self, path, defaults, label):
        self.path = path
        self.defaults = defaults
        self.label = label
        self.data = copy.deepcopy(defaults)
        self.dirty = False
        self._last_write = 0.0

    def load(self):
        if not os.path.exists(self.path):
            self.data = self._fresh()
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raise ValueError("root is not an object")
        except (OSError, ValueError) as e:
            backup = f"{os.path.splitext(self.path)[0]}.corrupt-{int(time.time())}.json"
            try:
                os.replace(self.path, backup)
            except OSError:
                backup = "(could not back up)"
            warn(f"{self.label} was corrupted ({e.__class__.__name__}). Started fresh; old file kept as "
                 f"{os.path.basename(backup)}")
            self.data = self._fresh()
            self.save()
            return
        self.data = merge_defaults(self.defaults, raw)
        self._validate()

    def _fresh(self):
        return copy.deepcopy(self.defaults)

    def _validate(self):
        pass

    def save(self):
        try:
            write_json_atomic(self.path, self.data)
            self.dirty = False
            self._last_write = time.time()
            return True
        except (OSError, TypeError, ValueError) as e:
            log.error("Could not write %s: %s", self.path, e)
            return False

    def mark_dirty(self):
        self.dirty = True

    def autosave(self, interval=15.0):
        if self.dirty and time.time() - self._last_write > interval:
            self.save()

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.dirty = True

    def get(self, key, default=None):
        return self.data.get(key, default)


class SaveSystem(_JsonStore):
    def __init__(self, gamedata, path=None):
        super().__init__(path or os.path.join(S.SAVE_DIR, "savegame.json"), DEFAULT_SAVE, "Save file")
        self.gamedata = gamedata

    def _fresh(self):
        data = copy.deepcopy(DEFAULT_SAVE)
        data["created"] = today().isoformat()
        gd = self.gamedata
        first_char = gd.characters[0]["id"]
        data["character"] = first_char
        data["characters_owned"] = [first_char]
        for cat, (owned_key, eq_key) in OWNERSHIP_KEYS.items():
            if cat == "characters":
                continue
            first = gd.first_id(cat)
            data[eq_key] = first
            data[owned_key] = [first]
        return data

    def _validate(self):
        d = self.data
        gd = self.gamedata
        for key in ("coins", "gems", "xp", "best_score", "best_distance"):
            d[key] = max(0, int(d[key]))
        d["level"] = max(1, min(S.MAX_LEVEL, int(d["level"])))
        # Owned/equipped items must exist in the data files.
        for cat, (owned_key, eq_key) in OWNERSHIP_KEYS.items():
            valid_ids = ({c["id"] for c in gd.characters} if cat == "characters"
                         else {i["id"] for i in gd.items[cat]})
            first = gd.characters[0]["id"] if cat == "characters" else gd.first_id(cat)
            owned = [i for i in d[owned_key] if isinstance(i, str) and i in valid_ids]
            if first not in owned:
                owned.insert(0, first)
            d[owned_key] = owned
            if d[eq_key] not in owned:
                d[eq_key] = first
        d["consumables"] = {k: max(0, int(v)) for k, v in d["consumables"].items()
                            if isinstance(v, (int, float)) and not isinstance(v, bool)}
        d["upgrades"] = {k: max(0, int(v)) for k, v in d["upgrades"].items()
                         if isinstance(v, (int, float)) and not isinstance(v, bool)}
        d["stats"] = {k: v for k, v in d["stats"].items() if isinstance(v, (int, float))}

    # ------------------------------------------------------------------
    # Stats helpers
    # ------------------------------------------------------------------
    def stat(self, key):
        return self.data["stats"].get(key, 0)

    def stat_add(self, key, amount):
        self.data["stats"][key] = self.data["stats"].get(key, 0) + amount
        self.dirty = True

    def stat_max(self, key, value):
        if value > self.data["stats"].get(key, 0):
            self.data["stats"][key] = value
            self.dirty = True


class SettingsStore(_JsonStore):
    def __init__(self, defaults, path=None):
        super().__init__(path or os.path.join(S.SAVE_DIR, "settings.json"), defaults, "Settings file")

    def _validate(self):
        d = self.data
        d["music_volume"] = max(0.0, min(1.0, float(d["music_volume"])))
        d["sfx_volume"] = max(0.0, min(1.0, float(d["sfx_volume"])))
        if d["graphics_quality"] not in S.QUALITY_PRESETS:
            d["graphics_quality"] = "medium"
        keys = d.get("keys")
        default_keys = self.defaults["keys"]
        if not isinstance(keys, dict):
            keys = {}
        clean = {}
        for action, dflt in default_keys.items():
            v = keys.get(action)
            clean[action] = [str(k) for k in v] if isinstance(v, list) and v else list(dflt)
        d["keys"] = clean

    @property
    def quality(self):
        return S.QUALITY_PRESETS.get(self.data["graphics_quality"], S.QUALITY_PRESETS["medium"])
