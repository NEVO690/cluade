"""Local progress storage: one JSON file with a versioned, validated structure.

Safety measures:
  * atomic writes (temp file + fsync + os.replace) so a crash mid-save never
    leaves a half-written file;
  * the previous good save is kept as profile.json.bak;
  * a damaged or unreadable file is moved aside (profile.json.corrupt-<time>)
    and the game starts from the backup or from defaults instead of crashing;
  * every field is type-checked and clamped when loading.

No passwords, tokens or other secrets are stored here.  The file lives on the
player's machine and can be edited, so nothing in it is trusted for online
ranking (the server keeps its own records).
"""

import copy
import hashlib
import json
import logging
import os
import time

from ..paths import save_dir

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
FILE_NAME = "profile.json"

DEFAULT_SETTINGS = {
    "player_name": "Player",
    "master_volume": 0.8,
    "sfx_volume": 0.9,
    "music_volume": 0.6,
    "mouse_sensitivity": 1.0,
    "invert_y": False,
    "camera_distance": 7.5,
    "always_run": True,
    "fullscreen": False,
    "resolution": "1280x720",
    "shadows": True,
    "show_fps": False,
    "bot_count": 15,
    "bot_difficulty": "MIXED",
    "server_address": "127.0.0.1:7777",
}

SETTING_RULES = {
    # name: (type, min, max) or (type, allowed_values)
    "player_name": (str, 1, 16),
    "master_volume": (float, 0.0, 1.0),
    "sfx_volume": (float, 0.0, 1.0),
    "music_volume": (float, 0.0, 1.0),
    "mouse_sensitivity": (float, 0.2, 3.0),
    "invert_y": (bool,),
    "camera_distance": (float, 4.0, 12.0),
    "always_run": (bool,),
    "fullscreen": (bool,),
    "resolution": (str, ("1280x720", "1600x900", "1920x1080", "1024x600")),
    "shadows": (bool,),
    "show_fps": (bool,),
    "bot_count": (int, 1, 15),
    "bot_difficulty": (str, ("EASY", "NORMAL", "HARD", "CHAOTIC", "MIXED")),
    "server_address": (str, 3, 64),
}

DEFAULT_STATS = {
    "games_played": 0,
    "wins": 0,
    "finishes": 0,
    "rounds_played": 0,
    "rounds_qualified": 0,
    "jumps": 0,
    "obstacles": 0,
    "falls": 0,
    "hits": 0,
    "bonks": 0,
    "current_streak": 0,
    "best_streak": 0,
    "best_placement": 0,
    "best_times": {},
    "map_finishes": {},
}


def default_data():
    return {
        "version": SCHEMA_VERSION,
        "created": int(time.time()),
        "settings": copy.deepcopy(DEFAULT_SETTINGS),
        "wallet": {"coins": 0, "ledger": [], "processed": []},
        "progress": {"level": 1, "xp": 0, "total_xp": 0, "rewarded_levels": [1]},
        "rank": {"points": 0, "peak_points": 0},
        "cosmetics": {"owned_skins": ["classic"], "equipped_skin": "classic"},
        "titles": {"unlocked": [], "equipped": None},
        "achievements": {},
        "quests": {"day": None, "highest_seen": 0, "active": []},
        "stats": copy.deepcopy(DEFAULT_STATS),
        "matches_applied": [],
    }


class SaveError(Exception):
    pass


def _as_int(v, default=0, lo=None, hi=None):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def _as_float(v, default=0.0, lo=None, hi=None):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def _str_list(v, limit=500):
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, str)][:limit]


def validate(raw):
    """Return a clean copy of `raw` that matches the schema (missing parts -> defaults)."""
    d = default_data()
    if not isinstance(raw, dict):
        return d
    d["created"] = _as_int(raw.get("created"), d["created"], 0)

    s = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
    for key, default in DEFAULT_SETTINGS.items():
        d["settings"][key] = validate_setting(key, s.get(key, default))

    w = raw.get("wallet") if isinstance(raw.get("wallet"), dict) else {}
    d["wallet"]["coins"] = _as_int(w.get("coins"), 0, 0, 10_000_000)
    d["wallet"]["ledger"] = [e for e in w.get("ledger", []) if isinstance(e, dict)][-50:] \
        if isinstance(w.get("ledger"), list) else []
    d["wallet"]["processed"] = _str_list(w.get("processed"))[-200:]

    p = raw.get("progress") if isinstance(raw.get("progress"), dict) else {}
    d["progress"]["level"] = _as_int(p.get("level"), 1, 1, 50)
    d["progress"]["xp"] = _as_int(p.get("xp"), 0, 0)
    d["progress"]["total_xp"] = _as_int(p.get("total_xp"), 0, 0)
    rl = p.get("rewarded_levels", [1])
    d["progress"]["rewarded_levels"] = sorted({_as_int(x, 1, 1, 50) for x in rl}) if isinstance(rl, list) else [1]

    r = raw.get("rank") if isinstance(raw.get("rank"), dict) else {}
    d["rank"]["points"] = _as_int(r.get("points"), 0, 0)
    d["rank"]["peak_points"] = max(d["rank"]["points"], _as_int(r.get("peak_points"), 0, 0))

    c = raw.get("cosmetics") if isinstance(raw.get("cosmetics"), dict) else {}
    owned = _str_list(c.get("owned_skins"), 200)
    if "classic" not in owned:
        owned.insert(0, "classic")
    d["cosmetics"]["owned_skins"] = list(dict.fromkeys(owned))
    eq = c.get("equipped_skin")
    d["cosmetics"]["equipped_skin"] = eq if eq in d["cosmetics"]["owned_skins"] else "classic"

    t = raw.get("titles") if isinstance(raw.get("titles"), dict) else {}
    d["titles"]["unlocked"] = list(dict.fromkeys(_str_list(t.get("unlocked"), 100)))
    teq = t.get("equipped")
    d["titles"]["equipped"] = teq if teq in d["titles"]["unlocked"] else None

    a = raw.get("achievements") if isinstance(raw.get("achievements"), dict) else {}
    for aid, st in a.items():
        if isinstance(aid, str) and isinstance(st, dict):
            d["achievements"][aid] = {"completed": bool(st.get("completed")),
                                      "rewarded": bool(st.get("rewarded"))}

    q = raw.get("quests") if isinstance(raw.get("quests"), dict) else {}
    d["quests"]["day"] = q.get("day") if isinstance(q.get("day"), str) else None
    d["quests"]["highest_seen"] = _as_float(q.get("highest_seen"), 0.0, 0.0)
    active = []
    for e in q.get("active", []) if isinstance(q.get("active"), list) else []:
        if isinstance(e, dict) and isinstance(e.get("id"), str):
            active.append({
                "id": e["id"],
                "template": str(e.get("template", "")),
                "text": str(e.get("text", ""))[:80],
                "stat": str(e.get("stat", "")),
                "target": _as_int(e.get("target"), 1, 1, 10000),
                "progress": _as_int(e.get("progress"), 0, 0, 10000),
                "coins": _as_int(e.get("coins"), 0, 0, 10000),
                "xp": _as_int(e.get("xp"), 0, 0, 10000),
                "claimed": bool(e.get("claimed")),
            })
    d["quests"]["active"] = active[:5]

    st = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    for key, default in DEFAULT_STATS.items():
        if isinstance(default, dict):
            src = st.get(key) if isinstance(st.get(key), dict) else {}
            if key == "best_times":
                d["stats"][key] = {k: _as_float(v, None, 0.1) for k, v in src.items()
                                   if isinstance(k, str) and _as_float(v, None) is not None}
            else:
                d["stats"][key] = {k: _as_int(v, 0, 0) for k, v in src.items() if isinstance(k, str)}
        else:
            d["stats"][key] = _as_int(st.get(key), 0, 0)
    d["matches_applied"] = _str_list(raw.get("matches_applied"))[-100:]
    return d


def validate_setting(key, value):
    default = DEFAULT_SETTINGS[key]
    rule = SETTING_RULES[key]
    typ = rule[0]
    try:
        if typ is bool:
            return value if isinstance(value, bool) else default
        if typ is int:
            return _as_int(value, default, rule[1], rule[2])
        if typ is float:
            return round(_as_float(value, default, rule[1], rule[2]), 3)
        if typ is str:
            if not isinstance(value, str):
                return default
            if isinstance(rule[1], tuple):
                return value if value in rule[1] else default
            value = "".join(ch for ch in value if ch.isprintable()).strip()
            return value[: rule[2]] if len(value) >= rule[1] else default
    except Exception:  # defensive: never let a bad setting crash loading
        return default
    return default


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class SaveManager:
    def __init__(self, directory=None):
        self.directory = directory or save_dir()
        self.path = os.path.join(self.directory, FILE_NAME)
        self.backup_path = self.path + ".bak"
        self.data = None
        self.warnings = []  # human-readable notes shown by the UI (e.g. recovered from backup)
        self.last_save_ok = True

    def load(self):
        self.warnings.clear()
        if not os.path.exists(self.path):
            if os.path.exists(self.backup_path):
                data = self._read(self.backup_path)
                if data is not None:
                    self.warnings.append("Save file was missing; restored from backup.")
                    self.data = data
                    return self.data
            self.data = default_data()
            return self.data
        data = self._read(self.path)
        if data is None:
            moved = self._quarantine(self.path)
            backup = self._read(self.backup_path) if os.path.exists(self.backup_path) else None
            if backup is not None:
                self.warnings.append("Save file was damaged (kept as %s); restored the backup." % moved)
                self.data = backup
            else:
                self.warnings.append("Save file was damaged (kept as %s); starting fresh." % moved)
                self.data = default_data()
            return self.data
        self.data = data
        return self.data

    def _read(self, path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                wrapper = json.load(fh)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            log.warning("could not read save %s: %s", path, exc)
            return None
        if not isinstance(wrapper, dict) or "data" not in wrapper:
            return None
        payload = wrapper.get("data")
        if wrapper.get("sha256") and wrapper["sha256"] != _digest(payload):
            # Accidental corruption (or a hand edit).  Still loadable: validate it.
            self.warnings.append("Save checksum mismatch in %s; values were re-validated." %
                                 os.path.basename(path))
        version = payload.get("version") if isinstance(payload, dict) else None
        if version is not None and _as_int(version, 0) > SCHEMA_VERSION:
            self.warnings.append("Save was made by a newer BONK! version; unknown fields ignored.")
        return validate(payload)

    def _quarantine(self, path):
        target = "%s.corrupt-%d" % (path, int(time.time()))
        try:
            os.replace(path, target)
        except OSError:
            return path
        return os.path.basename(target)

    def save(self, data=None):
        """Atomically write the save.  Returns True on success, False otherwise."""
        if data is not None:
            self.data = data
        if self.data is None:
            raise SaveError("nothing to save")
        payload = validate(self.data)
        wrapper = {"format": "bonk-save", "sha256": _digest(payload), "data": payload}
        tmp = self.path + ".tmp"
        try:
            os.makedirs(self.directory, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(wrapper, fh, indent=1, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            if os.path.exists(self.path):
                try:
                    os.replace(self.path, self.backup_path)
                except OSError:
                    pass
            os.replace(tmp, self.path)
        except OSError as exc:
            log.error("saving failed: %s", exc)
            self.last_save_ok = False
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            return False
        # self.data is kept as-is: managers hold references into it.
        self.last_save_ok = True
        return True
