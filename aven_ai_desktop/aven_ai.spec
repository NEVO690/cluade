# PyInstaller spec for AVEN AI Desktop.
#
#   pyinstaller --noconfirm --clean aven_ai.spec            -> dist/AVEN AI/AVEN AI.exe (folder build)
#   set AVEN_ONEFILE=1 & pyinstaller ... aven_ai.spec       -> dist/AVEN AI.exe (single file)
#
# The folder build is the recommended distribution format: it starts faster and is
# less likely to be flagged by antivirus heuristics than a self-extracting single file.
# No API keys or user data are bundled. With assets/cloud.json (written by the build script from
# AVEN_CLOUD_URL) users chat through the AVEN Cloud server without needing a key.

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()
sys.path.insert(0, str(ROOT))

from app.version import APP_NAME, VERSION_TUPLE, __version__  # noqa: E402

ONEFILE = os.environ.get("AVEN_ONEFILE") == "1"
ICON = ROOT / "assets" / "aven.ico"

datas = [(str(ROOT / "assets" / "aven.ico"), "assets"), (str(ROOT / "assets" / "aven.png"), "assets")]
if (ROOT / "engine").is_dir():
    datas.append((str(ROOT / "engine"), "engine"))  # AVEN Local: llama.cpp llama-server (scripts/fetch_engine.py)
if (ROOT / "assets" / "cloud.json").exists():
    datas.append((str(ROOT / "assets" / "cloud.json"), "assets"))  # AVEN Cloud server address (public)

hiddenimports = []
if sys.platform == "win32":
    # keyring discovers backends via entry points; make sure the Windows one is bundled.
    hiddenimports += ["keyring.backends.Windows", "win32ctypes.core"]

excludes = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick", "PySide6.QtQml"]

version_info = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "AVEN AI"),
                            StringStruct("FileDescription", "AVEN AI Desktop"),
                            StringStruct("FileVersion", __version__),
                            StringStruct("InternalName", "AVEN AI"),
                            StringStruct("OriginalFilename", "AVEN AI.exe"),
                            StringStruct("ProductName", "AVEN AI Desktop"),
                            StringStruct("ProductVersion", __version__),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe_options = dict(
    name=APP_NAME,
    icon=str(ICON),
    version=version_info,
    console=False,  # windowed app: no console window
    debug=False,
    strip=False,
    upx=False,
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **exe_options)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_options)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=APP_NAME)
