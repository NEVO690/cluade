"""Filesystem locations.

User data (database, settings, logs) lives in a per-user, writable directory
that is independent of the installation folder, so updating or reinstalling
the application never touches conversations:

* Windows: %APPDATA%\\AVEN AI
* macOS:   ~/Library/Application Support/AVEN AI
* Linux:   $XDG_DATA_HOME/aven-ai (default ~/.local/share/aven-ai)

``AVEN_DATA_DIR`` overrides the location (used by tests and portable setups).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.version import APP_DATA_FOLDER


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Directory containing ``main.py`` (or the unpacked bundle when frozen)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Absolute path of a bundled resource, independent of the working directory."""
    return project_root().joinpath("assets", *parts)


def user_data_dir() -> Path:
    override = os.environ.get("AVEN_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / APP_DATA_FOLDER
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_DATA_FOLDER
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "aven-ai"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return user_data_dir() / "conversations.db"


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def logs_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
