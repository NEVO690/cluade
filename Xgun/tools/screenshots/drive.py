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
    if scenario == "midmatch":
        app.start_match()
        for _ in range(400):
            steps(1)
            if app.screen.__class__.__name__ == "MatchScreen":
                break
        m = app.screen
        sim = m.sim
        from game.match import TICK
        p = sim.player
        # fast-forward 70 s of simulation (bots drop, loot and start fighting)
        while sim.time < 70:
            sim.step(TICK, {p.id: m._gather_input()} if p.alive else {})
            m._events(sim.drain_events())
        poi = max(sim.layout.pois, key=lambda q: sum(1 for c in sim.alive if (c.x - q.x) ** 2 + (c.y - q.y) ** 2 < q.radius ** 2))
        p.state, p.on_ground = "ground", True
        p.health = 1e6
        p.x, p.y = poi.x + 3, poi.y + 3
        p.z = sim.collision.floor_height(p.x, p.y, 200, 0.4)
        p.prev = (p.x, p.y, p.z)
        w = sim.armory.roll_weapon(sim.rng, "supply")
        p.inventory.add_weapon(w)
        p.inventory.add_ammo(w.wdef.ammo, 200)
        near = sorted(sim.alive, key=lambda c: (c.x - p.x) ** 2 + (c.y - p.y) ** 2)
        tgt = near[1] if len(near) > 1 else near[0]
        import math as _m
        m.cam_yaw = _m.degrees(_m.atan2(-(tgt.x - p.x), tgt.y - p.y))
        m.cam_pitch = -6
        t0 = time.perf_counter()
        n = 90
        for _ in range(n):
            steps(1)
        dt = (time.perf_counter() - t0) / n
        print(f"avg frame {dt * 1000:.1f} ms (render on CPU llvmpipe included), alive {len(sim.alive)}", flush=True)
        import cProfile, pstats, io
        pr = cProfile.Profile()
        pr.enable()
        for _ in range(30):
            m._task(type("T", (), {"cont": 0})())
        pr.disable()
        st = io.StringIO()
        pstats.Stats(pr, stream=st).sort_stats("cumulative").print_stats(12)
        print(st.getvalue()[:2500])
        shot("mid_view")
        # let nearby bots engage the (invulnerable) player in real time
        for i in range(4):
            steps(20, 0.03)
            near = sorted((c for c in sim.alive if c is not p), key=lambda c: (c.x - p.x) ** 2 + (c.y - p.y) ** 2)
            if near:
                t = near[0]
                m.cam_yaw = _m.degrees(_m.atan2(-(t.x - p.x), t.y - p.y))
                print("nearest bot", t.name, round(_m.hypot(t.x - p.x, t.y - p.y), 1), "m", t.state, "target",
                      getattr(sim.brains.get(t.id), "target", None) is p, flush=True)
            shot(f"fight{i}")
    if scenario == "thumbs":
        app.screen.select("TIKTOK")
        steps(5)
        tab = app.screen.tab_obj
        acc = app.services.accounts.find_by_username("glide_guru")
        tab.show_profile(acc.id)
        steps(80)
        print("thumbs written", app.thumbs.version, "failed", len(app.thumbs.failed), flush=True)
        shot("social_profile_thumbs")
    if scenario == "build":
        app.start_match()
        for _ in range(400):
            steps(1)
            if app.screen.__class__.__name__ == "MatchScreen":
                break
        m = app.screen
        sim = m.sim
        from game import building as B
        from game.match import TICK
        p = sim.player
        poi = sim.layout.pois[0]
        p.state, p.on_ground = "ground", True
        p.x, p.y = B.cell_center(*B.cell_of(poi.x + 6, poi.y - 10))
        p.z = sim.collision.floor_height(p.x, p.y, poi.height + 1, 0.4)
        p.prev = (p.x, p.y, p.z)
        p.health = 1e6
        p.materials.update(wood=200, stone=200, metal=200)
        p.build_mode = True
        for yaw, piece, mat in ((0, "wall", "wood"), (90, "wall", "stone"), (270, "wall", "metal"), (180, "ramp", "wood")):
            p.yaw, p.build_material = yaw, mat
            sim.place_piece(p, piece)
        p.yaw = 180
        p.build_piece = "floor"
        m.cam_yaw, m.cam_pitch = 150, -18
        steps(20)
        shot("build_fort")
        # damage the wood wall and look at the ghost of a new ramp
        wall = next(b for b in sim.builds.values() if b.material == "wood")
        sim._damage_piece(p, wall.id, 100)
        p.build_piece = "ramp"
        m.cam_yaw, m.cam_pitch = 200, -12
        steps(20)
        shot("build_ghost")
    if scenario == "online":
        # host from the PLAY tab, a second (headless) player joins over TCP
        from game.entities import ControlInput
        from game.match import TICK
        from net.match_client import ClientMatch, MatchConnection
        from world.island import build_island
        app.host_online()
        steps(10)
        friend = MatchConnection("127.0.0.1", app.online_lobby.server.port, "RemoteFriend", {"outfit": "outfit_ember_ronin"})
        steps(20, 0.02)
        shot("online_lobby")
        app.online_lobby._start()
        start = friend.wait_for("start")
        fsim = ClientMatch(friend, start, build_island(7))
        for _ in range(600):
            steps(1)
            if app.screen.__class__.__name__ == "MatchScreen":
                break
        m = app.screen
        t_end = time.time() + 30
        while time.time() < t_end:
            m.pressed.add("space")
            fsim.step(TICK, {fsim.player.id: ControlInput(deploy=True, yaw=m.cam_yaw, move_y=0.0)})
            fsim.drain_events()
            steps(1, 0.01)
            if m.player.state == "glide" and fsim.player.state == "glide":
                break
        m.cam_pitch = -25
        steps(30, 0.02)
        print("server players:", [c.name for c in m.sim.combatants if not c.is_bot],
              "me", m.player.state, "friend", m.sim.combatants[1].state, round(m.sim.combatants[1].z), flush=True)
        shot("online_match")
        fsim.close()
        m._exit()
        steps(40)
        shot("online_results")
    if scenario == "social":
        # a shared social server with a second player who posts; we sign in through the dialog
        from net import social_client as SC
        from net.social_server import SocialServer
        srv = SocialServer(out / "server", "127.0.0.1", 0)
        srv.serve_in_background()
        url = f"127.0.0.1:{srv.port}"
        other = SC.register(url, "neon_friend", "pass1234", "Neon Friend")
        clip = ROOT / "assets" / "videos" / "samples" / "robot_sentinel.mp4"
        posted = other.upload(0, clip, "Posted from another PC #online", "hello from the server")
        app.screen.select("TIKTOK")
        steps(20)
        tab = app.screen.tab_obj
        tab._online_dialog()
        tab.o_server.set(url)
        tab.o_user.set("player_one")
        tab.o_pass.set("pass1234")
        steps(10)
        shot("social_signin")
        for m in list(app.aspect2d.findAllMatches("**/modal")):
            m.removeNode()
        tab._online(True)
        steps(10)
        tab = app.screen.tab_obj
        tab.show_search("online")
        steps(10)
        shot("social_search")
        tab.show_feed("search", posted.id, tab.social.search(tab.me, "online")["videos"])
        tab._toggle_like()
        steps(60, 0.03)
        shot("social_online_feed")
        print("likes on server:", other.get_video(0, posted.id).likes, flush=True)
        tab.show_profile(other.account["id"])
        steps(80, 0.03)
        shot("social_online_profile")
        srv.stop()
    if scenario == "results":
        app.start_match()
        for _ in range(400):
            steps(1)
            if app.screen.__class__.__name__ == "MatchScreen":
                break
        m = app.screen
        sim = m.sim
        from game.match import TICK
        p = sim.player
        p.inventory.add_weapon(sim.armory.roll_weapon(sim.rng, "chest"))
        while p.alive and not sim.over and sim.time < 1500:      # passive player: the storm or a bot gets us
            sim.step(TICK, {p.id: m._gather_input()} if p.alive else {})
            m._events(sim.drain_events())
        steps(100)
        shot("death_panel")
        m._exit()
        steps(40)
        shot("results")
    app.destroy() if hasattr(app, "destroy") else None


if __name__ == "__main__":
    main()
