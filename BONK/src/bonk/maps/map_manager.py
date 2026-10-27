"""Discovers course files.  Dropping a new JSON file into data/maps adds a map."""

import glob
import logging
import os

from ..paths import MAPS_DIR
from .map_loader import MapFormatError, load_map_file

log = logging.getLogger(__name__)


class MapManager:
    def __init__(self, maps_dir=MAPS_DIR):
        self.maps_dir = maps_dir
        self.maps = {}
        self.errors = {}
        self.reload()

    def reload(self):
        self.maps.clear()
        self.errors.clear()
        for path in sorted(glob.glob(os.path.join(self.maps_dir, "*.json"))):
            try:
                m = load_map_file(path)
            except (MapFormatError, OSError, KeyError, TypeError, ValueError) as exc:
                # A broken map file must not take the whole game down.
                self.errors[os.path.basename(path)] = str(exc)
                log.error("Skipping map %s: %s", path, exc)
                continue
            if m.id in self.maps:
                self.errors[os.path.basename(path)] = "duplicate map id %r" % m.id
                continue
            self.maps[m.id] = m

    def get(self, map_id):
        return self.maps[map_id]

    def ordered(self):
        return sorted(self.maps.values(), key=lambda m: (m.order, m.name))

    def ids(self):
        return [m.id for m in self.ordered()]

    def show_playlist(self):
        """Default 3-round show: every map in order, the last one is the final."""
        return self.ids()
