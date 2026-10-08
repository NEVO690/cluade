"""Loads every JSON data file, validates it and fills in defaults.

The rest of the game only talks to :class:`GameData`, so a broken or missing
data file never crashes the game - invalid entries are skipped with a warning
and minimal built-in fallbacks are used when a whole file is unusable.
"""
import os

from . import settings as S
from .utils import load_json, warn, to_color

# ---------------------------------------------------------------------------
# Minimal fallbacks (used only when a data file is missing or broken)
# ---------------------------------------------------------------------------
FALLBACK_CHARACTER = {
    "id": "rex", "name": "Rex", "description": "Default runner.", "price": 0, "currency": "coins",
    "unlock_level": 1, "hair_style": "spiky", "accessory": "cap", "build": 1.0,
    "colors": {"skin": [222, 170, 120], "hair": [70, 45, 30], "shirt": [232, 72, 52],
               "pants": [44, 62, 112], "shoes": [245, 245, 245], "accent": [255, 212, 60]},
    "ability": {"type": "none", "value": 0, "desc": "Balanced all-rounder"},
}

FALLBACK_ITEMS = {
    "boards": [{"id": "street_board", "name": "Street Board", "price": 0, "style": "street",
                "colors": {"deck": [200, 70, 40], "stripe": [255, 220, 80], "glow": [255, 160, 60]},
                "perk": {"type": "none", "value": 0, "desc": "No bonus"}}],
    "outfits": [{"id": "outfit_default", "name": "Signature Look", "price": 0, "colors": {}}],
    "trails": [{"id": "trail_none", "name": "No Trail", "price": 0, "style": "none", "color": [255, 255, 255]}],
    "effects": [{"id": "fx_classic", "name": "Classic Sparkle", "price": 0, "style": "sparkle", "color": [255, 230, 120]}],
    "emotes": [{"id": "emote_none", "name": "No Emote", "price": 0, "text": ""}],
    "consumables": [{"id": "board_charge", "name": "Board Charge", "price": 300, "icon": "board",
                     "desc": "Ride your board for 30s."}],
}

FALLBACK_POWERUPS = [
    {"id": "magnet", "name": "Coin Magnet", "effect": "magnet", "icon": "magnet", "color": [235, 60, 60],
     "durations": [8, 10, 12, 14, 16, 19], "upgrade_costs": [500, 1200, 2500, 5000, 9000], "params": {"radius": 8.0}},
    {"id": "shield", "name": "Shield", "effect": "shield", "icon": "shield", "color": [70, 170, 255],
     "durations": [10, 13, 16, 19, 22, 26], "upgrade_costs": [500, 1200, 2500, 5000, 9000], "params": {}},
]

FALLBACK_ZONE = {
    "id": "downtown", "name": "Downtown", "unlock_level": 1, "length": [700, 800],
    "sky_top": [64, 132, 218], "sky_bottom": [182, 216, 242], "fog": [178, 206, 232],
    "ground": [92, 98, 108], "road": [118, 104, 94], "sidewalk": [172, 172, 178],
    "ties": [92, 72, 56], "rail": [205, 205, 215],
    "buildings": {"palette": [[182, 192, 206], [150, 166, 188]], "height": [14, 30], "depth": [9, 16],
                  "width": [9, 18], "style": "office", "window": [64, 94, 132],
                  "window_lit": [255, 232, 150], "lit_chance": 0.1},
    "night": False, "tunnels": 0.0, "stations": False, "bridges": 0.2, "water": None,
    "decor": {"lamp": 0.5, "tree": 0.4},
    "obstacles": {"low": 3, "high": 2, "block": 2, "train": 3, "car": 1, "moving_train": 1, "moving_car": 0},
    "obstacle_style": "downtown", "skyline": "towers", "sun": [255, 250, 220],
    "music": {"tempo": 116, "root": 57, "scale": "major", "progression": [1, 5, 6, 4], "style": "pop", "lead": "square"},
}

FALLBACK_MISSIONS = {
    "active_slots": 3, "daily_count": 3,
    "regular": [{"id": "m01", "desc": "Collect 100 coins in total", "stat": "coins", "mode": "total",
                 "target": 100, "reward": {"coins": 150, "xp": 60}}],
    "daily_pool": [{"id": "d_runs", "desc": "Play {target} runs", "stat": "runs", "mode": "total",
                    "targets": [3], "reward": {"coins": 250, "xp": 100}}],
}

FALLBACK_REWARDS = {
    "daily_rewards": [{"day": d, "reward": {"coins": 100 * d}} for d in range(1, 8)],
    "level_rewards": {},
    "default_level_reward": {"coins_per_level": 150},
}

DEFAULT_SETTINGS = {
    "music_volume": 0.6, "sfx_volume": 0.8, "graphics_quality": "medium", "fullscreen": False,
    "vsync": True, "show_fps": False, "swipe_threshold": 40, "force_event": "",
    "keys": {"left": ["a", "left"], "right": ["d", "right"], "jump": ["w", "up", "space"],
             "slide": ["s", "down"], "board": ["b"], "pause": ["escape", "p"]},
}

ITEM_CATEGORIES = ("boards", "outfits", "trails", "effects", "emotes", "consumables")


def _path(name):
    return os.path.join(S.DATA_DIR, name)


def _num(value, default, lo=None, hi=None):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def _valid_entries(entries, required, file_name):
    """Keep dict entries that have all ``required`` keys and a unique id."""
    if not isinstance(entries, list):
        warn(f"{file_name}: expected a list - using defaults")
        return None
    seen = set()
    out = []
    for i, e in enumerate(entries):
        if not isinstance(e, dict) or any(k not in e for k in required):
            warn(f"{file_name}: entry #{i + 1} is missing {', '.join(required)} - skipped")
            continue
        if e["id"] in seen:
            warn(f"{file_name}: duplicate id '{e['id']}' - skipped")
            continue
        seen.add(e["id"])
        out.append(e)
    return out


def _norm_reward(r):
    if not isinstance(r, dict):
        return {}
    out = {}
    for key in ("coins", "gems", "xp", "tokens"):
        if key in r:
            out[key] = int(_num(r[key], 0, 0))
    if isinstance(r.get("item"), str):
        out["item"] = r["item"]
    if isinstance(r.get("consumable"), dict):
        out["consumable"] = {k: int(_num(v, 0, 0)) for k, v in r["consumable"].items()}
    return out


class GameData:
    """All static game content (characters, items, zones, missions ...)."""

    def __init__(self):
        self._load_characters()
        self._load_items()
        self._load_powerups()
        self._load_zones()
        self._load_missions()
        self._load_achievements()
        self._load_events()
        self._load_rewards()
        self.default_settings = self._load_settings()

    # ------------------------------------------------------------------
    def _load_characters(self):
        raw = load_json(_path("characters.json"), [FALLBACK_CHARACTER])
        chars = _valid_entries(raw, ("id", "name"), "characters.json") or [FALLBACK_CHARACTER]
        for c in chars:
            c.setdefault("description", "")
            c["price"] = int(_num(c.get("price"), 0, 0))
            c.setdefault("currency", "coins")
            c["unlock_level"] = int(_num(c.get("unlock_level"), 1, 1, S.MAX_LEVEL))
            c.setdefault("hair_style", "short")
            c.setdefault("accessory", "none")
            c["build"] = _num(c.get("build"), 1.0, 0.7, 1.3)
            colors = c.get("colors") if isinstance(c.get("colors"), dict) else {}
            base = FALLBACK_CHARACTER["colors"]
            c["colors"] = {k: to_color(colors.get(k, base[k]), base[k]) for k in base}
            ab = c.get("ability") if isinstance(c.get("ability"), dict) else {}
            c["ability"] = {"type": ab.get("type", "none"), "value": _num(ab.get("value"), 0),
                            "desc": ab.get("desc", "")}
        # The first character must always be free so a fresh save can play.
        if chars[0]["price"] != 0:
            chars[0]["price"] = 0
        self.characters = chars
        self.character_by_id = {c["id"]: c for c in chars}

    def _load_items(self):
        raw = load_json(_path("items.json"), FALLBACK_ITEMS)
        if not isinstance(raw, dict):
            warn("items.json: expected an object - using defaults")
            raw = FALLBACK_ITEMS
        self.items = {}
        self.item_index = {}
        for cat in ITEM_CATEGORIES:
            entries = _valid_entries(raw.get(cat, []), ("id", "name"), f"items.json/{cat}")
            if not entries:
                entries = [dict(e) for e in FALLBACK_ITEMS[cat]]
            for e in entries:
                e["price"] = int(_num(e.get("price"), 0, 0))
                e.setdefault("currency", "coins")
                e.setdefault("desc", "")
                e["category"] = cat
                if "color" in e:
                    e["color"] = to_color(e["color"], (255, 255, 255))
                if cat == "boards":
                    cols = e.get("colors") if isinstance(e.get("colors"), dict) else {}
                    e["colors"] = {k: to_color(cols.get(k, d), d) for k, d in
                                   (("deck", (200, 70, 40)), ("stripe", (255, 220, 80)), ("glow", (255, 160, 60)))}
                    perk = e.get("perk") if isinstance(e.get("perk"), dict) else {}
                    e["perk"] = {"type": perk.get("type", "none"), "value": _num(perk.get("value"), 0),
                                 "desc": perk.get("desc", "")}
                    e.setdefault("style", "street")
                if cat == "outfits":
                    cols = e.get("colors") if isinstance(e.get("colors"), dict) else {}
                    e["colors"] = {k: to_color(v) for k, v in cols.items()}
                if cat == "trails":
                    e.setdefault("style", "none")
                    e.setdefault("color", (255, 255, 255))
                if cat == "effects":
                    e.setdefault("style", "sparkle")
                    e.setdefault("color", (255, 230, 120))
                if cat == "emotes":
                    e["text"] = str(e.get("text", ""))[:12]
                self.item_index[e["id"]] = e
            self.items[cat] = entries
        for c in self.characters:
            self.item_index[c["id"]] = dict(c, category="characters")

    def _load_powerups(self):
        raw = load_json(_path("powerups.json"), FALLBACK_POWERUPS)
        pus = _valid_entries(raw, ("id", "name", "effect"), "powerups.json") or [dict(p) for p in FALLBACK_POWERUPS]
        for p in pus:
            p["color"] = to_color(p.get("color", (255, 255, 255)))
            p.setdefault("icon", p["id"])
            p.setdefault("desc", "")
            p.setdefault("sound", "powerup")
            p["spawn_weight"] = _num(p.get("spawn_weight"), 1, 0)
            durs = p.get("durations")
            if not isinstance(durs, list) or not durs:
                durs = [10]
            p["durations"] = [_num(d, 10, 0.5) for d in durs]
            costs = p.get("upgrade_costs") if isinstance(p.get("upgrade_costs"), list) else []
            p["upgrade_costs"] = [int(_num(c, 1000, 0)) for c in costs][:len(p["durations"]) - 1]
            p["upgradeable"] = bool(p.get("upgradeable", True)) and len(p["upgrade_costs"]) > 0
            p["params"] = p.get("params") if isinstance(p.get("params"), dict) else {}
        self.powerups = pus
        self.powerup_by_id = {p["id"]: p for p in pus}

    def _load_zones(self):
        raw = load_json(_path("zones.json"), [FALLBACK_ZONE])
        zones = _valid_entries(raw, ("id", "name"), "zones.json") or [dict(FALLBACK_ZONE)]
        for z in zones:
            for key, val in FALLBACK_ZONE.items():
                z.setdefault(key, val)
            for key in ("sky_top", "sky_bottom", "fog", "ground", "road", "sidewalk", "ties", "rail"):
                z[key] = to_color(z[key], FALLBACK_ZONE[key])
            for key in ("sun", "moon", "water_color"):
                if z.get(key) is not None:
                    z[key] = to_color(z[key])
            b = z["buildings"] if isinstance(z["buildings"], dict) else {}
            fb = FALLBACK_ZONE["buildings"]
            pal = b.get("palette") if isinstance(b.get("palette"), list) and b.get("palette") else fb["palette"]
            z["buildings"] = {
                "palette": [to_color(c) for c in pal],
                "height": b.get("height", fb["height"]), "depth": b.get("depth", fb["depth"]),
                "width": b.get("width", fb["width"]), "style": b.get("style", "office"),
                "window": to_color(b.get("window", fb["window"])),
                "window_lit": to_color(b.get("window_lit", fb["window_lit"])),
                "lit_chance": _num(b.get("lit_chance"), 0.1, 0, 1),
            }
            z["unlock_level"] = int(_num(z.get("unlock_level"), 1, 1))
            ln = z.get("length")
            if not (isinstance(ln, list) and len(ln) == 2):
                ln = [700, 800]
            z["length"] = [max(200, _num(ln[0], 700)), max(200, _num(ln[1], 800))]
            if not isinstance(z.get("decor"), dict):
                z["decor"] = {}
            if not isinstance(z.get("obstacles"), dict):
                z["obstacles"] = dict(FALLBACK_ZONE["obstacles"])
            if not isinstance(z.get("music"), dict):
                z["music"] = dict(FALLBACK_ZONE["music"])
        zones[0]["unlock_level"] = 1
        self.zones = zones
        self.zone_by_id = {z["id"]: z for z in zones}

    def _load_missions(self):
        raw = load_json(_path("missions.json"), FALLBACK_MISSIONS)
        if not isinstance(raw, dict):
            warn("missions.json: expected an object - using defaults")
            raw = FALLBACK_MISSIONS
        reg = _valid_entries(raw.get("regular", []), ("id", "desc", "stat", "target"), "missions.json/regular")
        pool = _valid_entries(raw.get("daily_pool", []), ("id", "desc", "stat"), "missions.json/daily_pool")
        reg = reg if reg is not None else FALLBACK_MISSIONS["regular"]
        pool = pool if pool else FALLBACK_MISSIONS["daily_pool"]
        for m in reg:
            m["mode"] = m.get("mode", "total") if m.get("mode") in ("total", "run") else "total"
            m["target"] = max(1, _num(m["target"], 1))
            m["reward"] = _norm_reward(m.get("reward"))
        for m in pool:
            m["mode"] = m.get("mode", "total") if m.get("mode") in ("total", "run") else "total"
            t = m.get("targets") if isinstance(m.get("targets"), list) and m.get("targets") else [m.get("target", 10)]
            m["targets"] = [max(1, _num(x, 10)) for x in t]
            m["reward"] = _norm_reward(m.get("reward"))
        self.missions_regular = reg
        self.missions_daily_pool = pool
        self.mission_slots = int(_num(raw.get("active_slots"), 3, 1, 6))
        self.daily_count = int(_num(raw.get("daily_count"), 3, 1, 6))

    def _load_achievements(self):
        raw = load_json(_path("achievements.json"), [])
        ach = _valid_entries(raw, ("id", "name", "stat", "target"), "achievements.json") or []
        for a in ach:
            a.setdefault("desc", "")
            a.setdefault("icon", "trophy")
            a["target"] = max(1, _num(a["target"], 1))
            a["reward"] = _norm_reward(a.get("reward"))
        self.achievements = ach

    def _load_events(self):
        raw = load_json(_path("events.json"), [])
        evs = _valid_entries(raw, ("id", "name", "start", "end"), "events.json") or []
        good = []
        for e in evs:
            try:
                for key in ("start", "end"):
                    mm, dd = (int(x) for x in str(e[key]).split("-"))
                    if not (1 <= mm <= 12 and 1 <= dd <= 31):
                        raise ValueError
            except ValueError:
                warn(f"events.json: event '{e['id']}' has invalid dates (use MM-DD) - skipped")
                continue
            e.setdefault("desc", "")
            cur = e.get("currency") if isinstance(e.get("currency"), dict) else {}
            e["currency"] = {"name": cur.get("name", "Tokens"), "color": to_color(cur.get("color", (255, 200, 60))),
                             "spawn_chance": _num(cur.get("spawn_chance"), 0.3, 0, 1)}
            th = e.get("theme") if isinstance(e.get("theme"), dict) else {}
            e["theme"] = {"tint": to_color(th.get("tint", (255, 255, 255))),
                          "tint_strength": _num(th.get("tint_strength"), 0.1, 0, 0.6),
                          "decor": th.get("decor", ""), "weather": th.get("weather", ""),
                          "banner": to_color(th.get("banner", (255, 160, 40))),
                          "banner_2": to_color(th.get("banner_2", (60, 40, 120)))}
            ms = _valid_entries(e.get("missions", []), ("id", "desc", "stat", "target"), f"events.json/{e['id']}") or []
            for m in ms:
                m["mode"] = m.get("mode", "total") if m.get("mode") in ("total", "run") else "total"
                m["target"] = max(1, _num(m["target"], 1))
                m["reward"] = _norm_reward(m.get("reward"))
            e["missions"] = ms
            rw = e.get("rewards") if isinstance(e.get("rewards"), list) else []
            e["rewards"] = sorted(({"tokens": int(_num(r.get("tokens"), 0, 0)), "reward": _norm_reward(r.get("reward"))}
                                   for r in rw if isinstance(r, dict)), key=lambda r: r["tokens"])
            good.append(e)
        self.events = good
        self.event_by_id = {e["id"]: e for e in good}

    def _load_rewards(self):
        raw = load_json(_path("rewards.json"), FALLBACK_REWARDS)
        if not isinstance(raw, dict):
            raw = FALLBACK_REWARDS
        daily = raw.get("daily_rewards")
        if not isinstance(daily, list) or not daily:
            daily = FALLBACK_REWARDS["daily_rewards"]
        self.daily_rewards = [_norm_reward(d.get("reward") if isinstance(d, dict) else {}) for d in daily][:7]
        while len(self.daily_rewards) < 7:
            self.daily_rewards.append({"coins": 100 * (len(self.daily_rewards) + 1)})
        lr = raw.get("level_rewards") if isinstance(raw.get("level_rewards"), dict) else {}
        self.level_rewards = {}
        for k, v in lr.items():
            try:
                self.level_rewards[int(k)] = _norm_reward(v)
            except ValueError:
                warn(f"rewards.json: level '{k}' is not a number - skipped")
        dlr = raw.get("default_level_reward") if isinstance(raw.get("default_level_reward"), dict) else {}
        self.coins_per_level = int(_num(dlr.get("coins_per_level"), 150, 0))

    def _load_settings(self):
        raw = load_json(_path("settings.json"), DEFAULT_SETTINGS)
        out = dict(DEFAULT_SETTINGS)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in out and (type(v) == type(out[k]) or (isinstance(out[k], float) and isinstance(v, int))):
                    out[k] = v
        return out

    # ------------------------------------------------------------------
    def item(self, item_id):
        return self.item_index.get(item_id)

    def character(self, cid):
        return self.character_by_id.get(cid) or self.characters[0]

    def first_id(self, category):
        return self.items[category][0]["id"]
