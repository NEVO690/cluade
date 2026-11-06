"""Safe JSON persistence: atomic writes, rolling backup and corruption recovery."""
import copy
import json
import os
import shutil
import time

from ilbrawl import config


def deep_merge(defaults, data):
    """Return defaults updated with data, recursively, keeping unknown keys from data."""
    out = copy.deepcopy(defaults)
    if not isinstance(data, dict):
        return out
    for k, v in data.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class SaveManager:
    def __init__(self, directory=None):
        self.dir = directory or config.SAVE_DIR
        os.makedirs(self.dir, exist_ok=True)

    def path(self, name):
        return os.path.join(self.dir, name + ".json")

    def load(self, name, defaults):
        """Load a save file, falling back to its backup, then to defaults."""
        for candidate in (self.path(name), self.path(name) + ".bak"):
            if os.path.exists(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return deep_merge(defaults, data)
                except (OSError, ValueError):
                    # keep the damaged file for inspection, try the backup
                    try:
                        shutil.copy(candidate, candidate + ".corrupt-%d" % int(time.time()))
                    except OSError:
                        pass
        return copy.deepcopy(defaults)

    def save(self, name, data):
        """Atomic write: temp file + fsync + replace, previous version kept as .bak."""
        target = self.path(name)
        tmp = target + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(target):
                try:
                    shutil.copyfile(target, target + ".bak")
                except OSError:
                    pass
            os.replace(tmp, target)
            return True
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

    def delete(self, name):
        for p in (self.path(name), self.path(name) + ".bak"):
            if os.path.exists(p):
                os.remove(p)
