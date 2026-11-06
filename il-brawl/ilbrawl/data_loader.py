"""Loads all JSON game configuration into one object."""
import json
import os

from ilbrawl import config


def _read(name, default=None):
    path = os.path.join(config.DATA_DIR, name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default if default is not None else {}


class GameData:
    def __init__(self):
        self.characters = {}
        self.char_order = []
        self.level_bonus = 0.06
        self.max_level = 9
        self.upgrade_costs = []
        self.modes = {}
        self.mode_order = []
        self.maps = {}
        self.skins = {}
        self.skin_palettes = {}
        self.cosmetics = {}
        self.progression = {}
        self.shop = {}
        self.themes = {}

    @classmethod
    def load(cls):
        d = cls()
        ch = _read("characters.json")
        d.characters = ch.get("characters", {})
        for cid, c in d.characters.items():
            c["id"] = cid
        d.char_order = [c for c in ch.get("order", []) if c in d.characters]
        d.level_bonus = ch.get("level_bonus", 0.06)
        d.max_level = ch.get("max_level", 9)
        d.upgrade_costs = ch.get("upgrade_costs", [0] * 9)
        md = _read("modes.json")
        d.modes = md.get("modes", {})
        for mid, m in d.modes.items():
            m["id"] = mid
        d.mode_order = md.get("order", list(d.modes))
        sk = _read("skins.json")
        d.skin_palettes = sk.get("palettes", {})
        d.skins = {s["id"]: s for s in sk.get("skins", [])}
        d.cosmetics = _read("cosmetics.json")
        d.progression = _read("progression.json")
        d.shop = _read("shop.json")
        d.themes = _read("themes.json")
        d.reload_maps()
        return d

    def reload_maps(self):
        self.maps = {}
        for folder, custom in ((config.MAPS_DIR, False), (config.CUSTOM_MAPS_DIR, True)):
            if not os.path.isdir(folder):
                continue
            for fn in sorted(os.listdir(folder)):
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(folder, fn), "r", encoding="utf-8") as f:
                        m = json.load(f)
                    if not m.get("tiles"):
                        continue
                    m.setdefault("id", fn[:-5])
                    m["custom"] = custom
                    m["file"] = os.path.join(folder, fn)
                    self.maps[m["id"]] = m
                except (OSError, ValueError):
                    continue

    def maps_for_mode(self, mode_id):
        res = [m for m in self.maps.values() if mode_id in m.get("modes", [])]
        res.sort(key=lambda m: (m.get("custom", False), m["id"]))
        return res

    def skin_style(self, char_id, skin_id):
        """Return the body/accent palette for a character with the given skin (None = default)."""
        base = self.characters[char_id]["style"]
        if skin_id and skin_id in self.skins:
            pal = self.skin_palettes.get(self.skins[skin_id]["style"])
            if pal:
                st = dict(base)
                st.update(pal)
                return st
        return base
