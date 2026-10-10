import os
import subprocess
import sys
from pathlib import Path


def test_game_boots_navigates_plays_and_saves(tmp_path):
    env = dict(os.environ, XGUN_USER_DIR=str(tmp_path / "ud"))
    runner = Path(__file__).with_name("ui_smoke_runner.py")
    out = subprocess.run([sys.executable, str(runner)], capture_output=True, text=True, timeout=900, env=env)
    assert out.returncode == 0 and "SMOKE OK" in out.stdout, out.stdout[-4000:] + out.stderr[-4000:]
