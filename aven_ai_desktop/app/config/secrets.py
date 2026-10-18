"""API key handling.

Lookup order for a provider's key:

1. Environment variable (``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``) - development.
2. The operating system credential store via :mod:`keyring`
   (Windows Credential Manager on Windows).
3. A key entered in Settings for this session only (when no credential store
   is available it is kept in memory and forgotten on exit).

Keys are never written to the settings file, the database or the logs.

Limitations: a key stored in the Windows Credential Manager is protected by the
user's Windows login. Any program running as that same user can read it, so
this protects against casual disclosure and other users - not against malware
running in the user's own session.
"""

from __future__ import annotations

import contextlib
import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

KEYRING_SERVICE = "AVEN AI Desktop"

ENV_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


@dataclass(frozen=True)
class KeyLookup:
    key: str | None
    source: str  # "environment", "credential store", "session", or "none"


def mask_key(key: str | None) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return "•" * len(key)
    return f"{key[:6]}…{key[-4:]}"


class CredentialStore:
    def __init__(self, use_keyring: bool = True) -> None:
        self._session: dict[str, str] = {}
        self._keyring = None
        if use_keyring:
            try:
                import keyring
                from keyring.backends import fail

                backend = keyring.get_keyring()
                if not isinstance(backend, fail.Keyring):
                    self._keyring = keyring
            except Exception as exc:  # pragma: no cover - platform dependent
                log.warning("Credential store unavailable: %s", type(exc).__name__)

    @property
    def persistent_storage_available(self) -> bool:
        return self._keyring is not None

    def lookup(self, provider: str) -> KeyLookup:
        env_name = ENV_VARS.get(provider)
        if env_name and os.environ.get(env_name, "").strip():
            return KeyLookup(os.environ[env_name].strip(), "environment")
        if self._keyring is not None:
            try:
                stored = self._keyring.get_password(KEYRING_SERVICE, provider)
            except Exception as exc:  # pragma: no cover - platform dependent
                log.warning("Reading credential store failed: %s", type(exc).__name__)
                stored = None
            if stored:
                return KeyLookup(stored, "credential store")
        if self._session.get(provider):
            return KeyLookup(self._session[provider], "session")
        return KeyLookup(None, "none")

    def get_key(self, provider: str) -> str | None:
        return self.lookup(provider).key

    def save_key(self, provider: str, key: str) -> str:
        """Store a key. Returns where it was stored ("credential store" or "session")."""
        key = key.strip()
        if not key:
            raise ValueError("The API key is empty.")
        if any(ch.isspace() for ch in key) or len(key) > 512:
            raise ValueError("The API key contains invalid characters.")
        if self._keyring is not None:
            try:
                self._keyring.set_password(KEYRING_SERVICE, provider, key)
                self._session.pop(provider, None)
                return "credential store"
            except Exception as exc:  # pragma: no cover - platform dependent
                log.warning("Writing credential store failed: %s", type(exc).__name__)
        self._session[provider] = key
        return "session"

    def delete_key(self, provider: str) -> None:
        self._session.pop(provider, None)
        if self._keyring is not None:
            # Raises when nothing is stored, which is fine.
            with contextlib.suppress(Exception):
                self._keyring.delete_password(KEYRING_SERVICE, provider)
