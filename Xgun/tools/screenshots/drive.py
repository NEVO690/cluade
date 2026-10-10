"""Drive the real game headlessly (or windowed) and capture screenshots for QA.

    python tools/screenshots/drive.py <out_dir> [scenario]

Scenarios: lobby, tabs, match (default: all). Requires an OpenGL context
(e.g. run under xvfb-run on Linux).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "screens")
    scenario = sys.argv[2] if len(sys.argv) > 2 else "all"
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("XGUN_USER_DIR", str(out / "userdata"))
    from config.settings import Settings
    from game.app import XgunApp, setup_logging
    from panda3d.core import Filename
    setup_logging()
    s = Settings()
    s.window_width, s.window_height, s.fullscreen, s.vsync = 1600, 900, False, False
    s.bot_count = int(os.environ.get("XGUN_BOTS", "19"))
    app = XgunApp(s)

    def steps(n, dt_sleep=0.0):
        for _ in range(n):
            app.taskMgr.step()
            if dt_sleep:
                time.sleep(dt_sleep)

    def shot(name):
        steps(2)
        app.win.saveScreenshot(Filename.from_os_specific(str(out / f"{name}.png")))
        print("screenshot", name, flush=True)

    steps(30)
    if scenario in ("all", "lobby", "tabs"):
        shot("lobby_play")
    if scenario in ("all", "tabs"):
        for tab in ["LOCKER", "XON SHOP", "BATTLE PASS", "TIKTOK", "FRIENDS", "PROFILE", "QUESTS", "SETTINGS"]:
            app.screen.select(tab)
            steps(25)
            shot("lobby_" + tab.lower().replace(" ", "_"))
        app.screen.select("PLAY")
        steps(5)
    if scenario in ("all", "match"):
        app.start_match()
        for _ in range(400):
            steps(1)
            if app.screen.__class__.__name__ == "MatchScreen":
                break
        m = app.screen
        steps(20)
        shot("match_dropship")
        m._press("space")
        steps(60, 0.01)
        shot("match_skydive")
        # fast-forward the drop: keep holding forward
        m._key("w", True)
        t0 = time.time()
        while m.player.state != "ground" and time.time() - t0 < 240:
            steps(1)
        shot("match_landed")
        m._key("w", False)
        # teleport to the central town to inspect buildings and combat
        sim = m.sim
        poi = sim.layout.pois[0]
        p = sim.player
        p.x, p.y = poi.x + 4, poi.y - 4
        p.z = sim.collision.floor_height(p.x, p.y, 50, 0.4)
        p.prev = (p.x, p.y, p.z)
        m.cam_yaw = 35
        m.cam_pitch = -8
        steps(30)
        shot("match_town")
        # look around and walk
        m.cam_yaw += 120
        steps(30)
        shot("match_lookaround")
        # give the player a weapon to show HUD/weapon visuals
        sim = m.sim
        w = sim.armory.roll_weapon(sim.rng, "supply")
        sim.player.inventory.add_weapon(w)
        sim.player.inventory.add_ammo(w.wdef.ammo, 120)
        m._press("slot1") if False else m._press("slot1")
        steps(10)
        # place a bot 12 m in front of the camera to test hit feedback
        import math as _m
        bot = next(c for c in sim.combatants if c.is_bot and c.alive)
        bot.state = "ground"
        yaw = _m.radians(m.cam_yaw)
        bot.x, bot.y = p.x - _m.sin(yaw) * 12, p.y + _m.cos(yaw) * 12
        bot.z = sim.collision.floor_height(bot.x, bot.y, p.z + 2, 0.4)
        bot.prev = (bot.x, bot.y, bot.z)
        sim.brains[bot.id].target = None
        m.cam_pitch = -2
        steps(5)
        shot("match_hipfire_pose")
        m._key("mouse3", True)
        steps(20)
        shot("match_aim")
        m._key("mouse1", True)
        for _ in range(12):
            bot.x, bot.y = p.x - _m.sin(yaw) * 12, p.y + _m.cos(yaw) * 12   # hold the target still
            steps(1)
        shot("match_fire")
        print("player", round(p.x, 1), round(p.y, 1), round(p.z, 1), "bot", bot.name, bot.state, round(bot.x, 1),
              round(bot.y, 1), round(bot.z, 1), "hp", round(bot.health), "shield", round(bot.shield),
              "dmg dealt", p.stats.damage, "aim", m.player.yaw, m.player.pitch, flush=True)
        m._key("mouse1", False)
        m._key("mouse3", False)
        m._press("m")
        steps(3)
        shot("match_map")
        m._press("m")
        steps(3)
    app.destroy() if hasattr(app, "destroy") else None


if __name__ == "__main__":
    main()
