"""Centralized localization: JSON string tables per language, instant switching."""
import json
import os

from ilbrawl import config


class I18n:
    def __init__(self, language=config.DEFAULT_LANGUAGE):
        self.tables = {}
        for code in config.LANGUAGES:
            self.tables[code] = self._load(code)
        self.lang = language if language in self.tables else config.DEFAULT_LANGUAGE
        self.listeners = []

    @staticmethod
    def _load(code):
        path = os.path.join(config.LOCALE_DIR, code + ".json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    @property
    def rtl(self):
        return self.lang in config.RTL_LANGUAGES

    def set_language(self, code):
        if code not in self.tables or code == self.lang:
            return False
        self.lang = code
        for cb in list(self.listeners):
            cb(code)
        return True

    def has(self, key):
        return key in self.tables.get(self.lang, {})

    def raw(self, key, default=None):
        table = self.tables.get(self.lang, {})
        if key in table:
            return table[key]
        # fallback chain keeps the game usable if a key is missing
        en = self.tables.get("en", {})
        if key in en:
            return en[key]
        return default if default is not None else key

    def t(self, _key, **kwargs):
        key = _key
        s = self.raw(key)
        if isinstance(s, list):
            s = s[0] if s else key
        if kwargs:
            try:
                s = s.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                pass
        return s

    def t_list(self, key):
        v = self.raw(key, [])
        return v if isinstance(v, list) else [v]

    def language_name(self, code):
        return self.tables.get(code, {}).get("language.native_name", code)


_INSTANCE = None


def set_instance(i18n):
    global _INSTANCE
    _INSTANCE = i18n


def get():
    return _INSTANCE


def tr(_key, **kw):
    return _INSTANCE.t(_key, **kw) if _INSTANCE else _key


def key_label(name):
    """Localized display name of a keyboard key (single letters stay as printed on the key)."""
    if _INSTANCE is None:
        return name.upper()
    k = "key." + name
    if _INSTANCE.has(k):
        return _INSTANCE.t(k)
    return name.upper()
