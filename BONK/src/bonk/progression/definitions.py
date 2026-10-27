"""Loads data/progression.json (levels, rewards, ranks, titles, achievements, quests)."""

import json
import os

from ..paths import DATA_DIR


def load_progression(path=None):
    path = path or os.path.join(DATA_DIR, "progression.json")
    with open(path, "r", encoding="utf-8") as fh:
        d = json.load(fh)
    tiers = d["ranks"]["tiers"]
    if [t["min_points"] for t in tiers] != sorted(t["min_points"] for t in tiers):
        raise ValueError("rank tiers must be ordered by min_points")
    ids = [t["id"] for t in d["titles"]] + [a["id"] for a in d["achievements"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate title/achievement id")
    return d
