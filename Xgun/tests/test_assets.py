"""Blender exports load in Panda3D with sockets, skeleton and animations."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_manifest_and_catalog_consistent():
    from tools.asset_validation.validate_assets import validate
    assert validate(load_models=False) == []


def test_every_model_loads_with_sockets_and_animations():
    # separate process: it needs its own ShowBase
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "asset_validation" / "validate_assets.py")],
                         capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stdout[-3000:] + out.stderr[-3000:]
    assert "0 problems" in out.stdout


def test_blender_sources_exist_for_models():
    import json
    from config import paths
    manifest = json.loads(paths.MODEL_MANIFEST.read_text())
    missing = [a for a, i in manifest.items() if not (ROOT / i["blend"]).exists()]
    assert not missing


def test_weapon_grip_frames_are_level_for_rifles():
    import json
    from config import paths
    manifest = json.loads(paths.MODEL_MANIFEST.read_text())
    for asset, info in manifest.items():
        if asset.startswith("outfit_"):
            q = info["hold_frames"]["rifle"]["quat"]
            assert abs(abs(q[0]) - 1.0) < 1e-3, f"{asset} rifle socket not level: {q}"
