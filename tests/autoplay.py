"""Headless autopilot play-test.

Runs the real game (dummy video/audio drivers) with a simple bot that
dodges obstacles, then prints statistics.  Useful to verify that runs work
end-to-end: movement, collisions, coins, power-ups, game over, rewards.

    python -m tests.autoplay --runs 3 --seconds 90 [--shots DIR]
"""
import argparse
import os
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
if "SSC_SAVE_DIR" not in os.environ:
    os.environ["SSC_SAVE_DIR"] = tempfile.mkdtemp(prefix="ssc_test_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from game import settings as S  # noqa: E402
from game.obstacles import LOW, HIGH, TRAIN, RAMP, CAR  # noqa: E402


def lane_blocked(world, lane, z0, z1, player):
    x = S.LANE_X[lane]
    for ob in world.obstacles_near(z0, z1):
        if abs(ob.x - x) > 0.5 or ob.kind in (RAMP,):
            continue
        if player.y >= ob.top_at(min(max(player.z, ob.z0), ob.z1)) - 0.2:
            continue
        if ob.kind in (LOW, HIGH):
            continue
        if ob.kind == TRAIN and ob.has_ramp and ob.vel == 0:
            continue  # reachable via its ramp
        if ob.kind == CAR and ob.vel == 0:
            continue  # can be jumped
        return True
    return False


def bot_decide(sess, skill=1.0):
    p = sess.player
    world = sess.world
    if p.flying or p.dead:
        return None
    speed = max(sess.speed, 1.0)
    look = max(10.0, speed * 0.75)
    lane_x = S.LANE_X[p.lane]
    if abs(p.x - lane_x) > 0.3:
        return None  # still switching
    ahead = sorted((ob for ob in world.obstacles_near(p.z + 0.2, p.z + look) if abs(ob.x - lane_x) < 0.5),
                   key=lambda o: o.z0)
    for ob in ahead:
        dist = ob.z0 - p.z
        if ob.kind == RAMP:
            return None
        if p.y >= ob.y1 - 0.2:
            continue  # already above it (train roof)
        if ob.kind in (LOW, CAR):
            if dist < speed * 0.2 + ob.vel * -0.2 and p.on_ground:
                return "jump"
            return None
        if ob.kind == HIGH:
            if dist < speed * 0.22 and not p.sliding:
                return "slide"
            return None
        # block / train: change lane
        options = []
        for d in (-1, 1):
            nl = p.lane + d
            if 0 <= nl < 3 and not lane_blocked(world, nl, p.z - 1.5, p.z + look * 1.3, p):
                options.append(d)
        if options:
            # prefer the lane with the most coins / centre
            d = min(options, key=lambda d: abs(p.lane + d - 1))
            return "left" if d < 0 else "right"
        if ob.kind == TRAIN and dist < speed * 0.25:
            return "jump"
        return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--seconds", type=float, default=90)
    ap.add_argument("--shots", default="")
    ap.add_argument("--quality", default="")
    args = ap.parse_args()

    import game.main as gm
    app = gm.App()
    if args.quality:
        app.settings["graphics_quality"] = args.quality
    # loading + menu
    for _ in range(60):
        app.step(1 / 60)
    assert app.scene_name == "menu", app.scene_name
    menu = app.scenes["menu"]
    if menu.popup:
        menu._claim_daily()
    results = []
    frame_times = []
    for run in range(args.runs):
        app.change_scene("game")
        for _ in range(20):
            app.step(1 / 60)
        scene = app.scenes["game"]
        sess = scene.session
        frames = int(args.seconds * 60)
        cooldown = 0
        shot_every = 600
        for f in range(frames):
            if scene.mode == "play" and sess.state == "running":
                if cooldown <= 0:
                    act = bot_decide(sess)
                    if act:
                        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key={
                            "left": pygame.K_LEFT, "right": pygame.K_RIGHT, "jump": pygame.K_UP,
                            "slide": pygame.K_DOWN}[act], mod=0, unicode="", scancode=0))
                        cooldown = 6
                cooldown -= 1
            if f == 120 and app.economy.consumable("board_charge") > 0 and run == 0:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_b, mod=0, unicode="b", scancode=0))
            t0 = time.perf_counter()
            app.step(1 / 60)
            frame_times.append(time.perf_counter() - t0)
            if args.shots and f % shot_every == 300:
                pygame.image.save(app.screen, os.path.join(args.shots, f"run{run}_{f}.png"))
            if scene.mode == "revive":
                scene._skip_revive()
            if scene.mode == "over":
                break
        if sess.result is None:
            sess.finalize()
        res = sess.result
        results.append(res)
        print(f"run {run}: dist={res['distance']}m score={res['score']} coins={res['coins']} gems={res['gems']} "
              f"xp={res['xp']} powerups={sess.stats['powerups']} jumps={sess.stats['jumps']} "
              f"slides={sess.stats['slides']} roofs={sess.stats['trains_landed']} died={sess.state != 'running'} "
              f"missions={len(res['missions'])}")
        if args.shots:
            for _ in range(30):
                app.step(1 / 60)
            pygame.image.save(app.screen, os.path.join(args.shots, f"run{run}_over.png"))
        app.change_scene("menu")
        for _ in range(30):
            app.step(1 / 60)
    frame_times.sort()
    n = len(frame_times)
    print(f"frames={n} avg={sum(frame_times) / n * 1000:.2f}ms p95={frame_times[int(n * 0.95)] * 1000:.2f}ms "
          f"max={frame_times[-1] * 1000:.1f}ms")
    print(f"save: coins={app.save['coins']} level={app.save['level']} best={app.save['best_score']}")
    app.shutdown()
    return results


if __name__ == "__main__":
    main()
